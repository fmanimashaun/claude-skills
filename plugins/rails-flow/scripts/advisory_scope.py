#!/usr/bin/env python3
"""Say whether a unit's PLAN needs a Fable `advisor` pass before it is built, and whether that pass is recorded and disposed (#2262).

Run:  advisory_scope.py [--slug S] [--root DIR]                 classify the unit's plan; when required, check its record
      advisory_scope.py --begin [--slug S] [--root DIR]         write the record header and the reviewed-plan snapshot, before the pass
      advisory_scope.py --stamp [--slug S] [--root DIR]         accept a revised plan after every finding has a disposition
      advisory_scope.py --selftest
Exit: 0 not required, or required and the record is usable: every finding disposed, VERDICT PROCEED (or RETHINK with an override),
        and it covers the plan as it is now
      1 required and the record is missing, incomplete, stale, or RETHINK with no override: run `advisor` (model: fable) and record it
      2 cannot classify: no plan files for the unit, or an unreadable record. An unknown plan is not "not required"

WHY (#2262, owner direction 2026-10-21: "we should make fable advisory a standard flow in our plugin"). The `adversary` attacks a
finished diff. Nothing challenged a PLAN before it was built, and the plan advisories that were run by hand caught real defects
(#2220's layer order, #2178's layout). This is the plan-time sibling of `security_scope.py`, as `risky_diff.py` is the diff-time one.

THE PLAN is the unit's plan files that exist, in this order: its acceptance criteria, work order, spec and threat model
(`PLAN_FILES`). Their PLANNED PATHS are every backticked path in them (a token with a `/`), and a backticked root dependency manifest such as `Gemfile.lock`.

REQUIRED when any category fires (each is the whole definition of its category):
  * security    `security_scope.py` names a boundary in the plan text or the planned paths (reused, never copied)
  * structure   the plan adds, moves or removes a plugin, agent, command, skill, hook, gate or descriptor/schema key
  * data-model  a planned path under the detected stack's `layout.migrations`, or its `layout.schema`
  * dependency  a planned dependency manifest or lockfile, or the plan says it adds a gem, package or dependency
  * breadth     the planned paths span BREADTH or more components (a component is a path's first two segments). Measured
                2026-10-21 on the 30 most recent PRs merged into dev, bookkeeping paths excluded: 0-3 components 11, 4: 4, 5: 6,
                6+: 9. At 6, the 30% most cross-cutting fire.

THE RECORD, `docs/evidence/reviews/plans/<slug>/advisor.md`:
  * `--begin` writes `Plan: <file>` per plan file, `Plan-SHA256: <hash>`, `Categories: <...>`, and a snapshot of the plan beside the
    record (`reviewed-plan.txt`); the advisor's answer is appended verbatim. Its findings are `A-n` lines; its last
    `VERDICT:` line is PROCEED or RETHINK.
  * one `Disposition A-n: accepted|rejected|deferred | <reason>` per finding: no finding undisposed, none twice, none that names a
    finding the answer lacks, no filler reason, and a `deferred` cites an issue `#n`.
  * RETHINK means the premise is wrong. It blocks (exit 1) until a fresh pass on the revised plan says PROCEED, or an
    `Override: <who> | <reason, 20+ characters, not filler> | #<issue>` line records who decided (coordinator ruling, #2262).
  * THE PLAN MOVES ON. Accepting a finding changes the plan, so the reviewed hash goes stale on purpose. `--stamp` accepts the
    revised plan (`Disposed-SHA256`) only when every finding is disposed, its categories are a subset of the reviewed ones, and at
    most RESTAMP_MAX of its lines changed against the snapshot. Measured 2026-10-21 on 66 revisions of 53 acceptance files
    (Retask): changed share 25th percentile 4%, median 9%, 75th 22%, 90th 52%. Above 30%, about one revision in seven, a new pass is
    owed even in the same categories.

LIMITS. A classifier over the plan's words and backticked paths: a plan worded unlike every pattern, or one naming no path, is
missed. The snapshot and the record are files the session writes, so nothing here stops a hand-written record; it makes the pass,
its findings and their dispositions checkable, as `risky_diff.py` does for the adversary.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PLAN_FILES = ("docs/product/acceptance/{slug}.md", "docs/product/handoff/{slug}.md", "docs/product/specs/{slug}.md",
              "docs/security/threat-models/{slug}.md")
RECORD = "docs/evidence/reviews/plans/{slug}/advisor.md"
SNAPSHOT = "reviewed-plan.txt"
BREADTH = 6
RESTAMP_MAX = 0.30
REASON_MIN = 20

PATH_RE = re.compile(r"`([A-Za-z0-9_.@-][\w.@/-]*/[\w.@/-]+)`")
STRUCTURE_PATHS = re.compile(r"(?:^|/)(?:\.claude-plugin/|agents/|commands/|skills/[^/]+/SKILL\.md$|hooks/|checks\.json$|stacks\.json$|marketplace\.json$)")
STRUCTURE_TEXT = re.compile(r"\b(?:add|adds|adding|new|move|moves|moving|remove|removes|removing|rename|renames|split|merge|retire)\b[^.\n]{0,40}"
                            r"\b(?:plugin|agent|command|skill|hook|gate|descriptor key|schema key|check)s?\b", re.I)
DEPENDENCY_PATHS = re.compile(r"(?:^|/)(?:Gemfile(?:\.lock)?|package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|"
                              r"requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|go\.mod|go\.sum|Cargo\.(?:toml|lock)|importmap\.rb)$")
DEPENDENCY_TEXT = re.compile(r"\b(?:add|adds|adding|new|bump|upgrade|install)\b[^.\n]{0,30}\b(?:gem|package|dependency|dependencies|library|npm module)\b", re.I)
BOOKKEEPING = re.compile(r"^(?:changelog\.d|dist|docs/architecture|docs/wiki|docs/evidence|\.claude/skills)/")
FINDING_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(A-\d+)\b")
DISPOSITION_RE = re.compile(r"^\s*Disposition\s+(A-\d+)\s*:\s*(\w+)\s*\|\s*(.*)$", re.I)
OVERRIDE_RE = re.compile(r"^\s*Override\s*:\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*(#\d+)\s*$", re.I)


def plan_files(root: Path, slug: str) -> list[str]:
    return [p.format(slug=slug) for p in PLAN_FILES if (root / p.format(slug=slug)).is_file()]


def plan_text(root: Path, files: list[str]) -> str:
    return "".join(f"== {f}\n" + (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in files)


def plan_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def planned_paths(text: str) -> list[str]:
    """Every backticked path (a token with a `/`), plus a bare backticked dependency manifest at the root (`Gemfile.lock`)."""
    paths = {m.group(1).strip("/") for m in PATH_RE.finditer(text) if not m.group(1).startswith(("http", "//"))}
    paths |= {m.group(1) for m in re.finditer(r"`([\w.-]+)`", text) if DEPENDENCY_PATHS.search(m.group(1))}
    return sorted(paths)


def _layout(root: Path) -> tuple[str, str]:
    try:
        import detect_stack  # noqa: E402  (a sibling script)
        _, report = detect_stack.run(root, detect_stack.manifest_dirs(Path(__file__).resolve()))
        layout = (report.get("descriptor") or {}).get("layout") or {}
        return str(layout.get("migrations") or ""), str(layout.get("schema") or "")
    except Exception:  # noqa: BLE001 -- no detector, or a project it cannot judge: the data-model category then reads nothing
        return "", ""


def categories(root: Path, text: str, paths: list[str], layout: tuple[str, str] | None = None) -> dict[str, str]:
    """{category: what named it}; empty when the advisory is optional."""
    import security_scope  # noqa: E402

    found: dict[str, str] = {}
    try:
        rows, _ = security_scope.stack_rows(root)
    except Exception:  # noqa: BLE001 -- the neutral signals still run
        rows = []
    sec = security_scope.classify(text, paths, rows)
    if sec:
        found["security"] = sec[0]
    for p in paths:
        if STRUCTURE_PATHS.search(p):
            found.setdefault("structure", f"planned path `{p}`")
    if (m := STRUCTURE_TEXT.search(text)):
        found.setdefault("structure", f"plan says `{m.group(0).strip()}`")
    migrations, schema = layout if layout is not None else _layout(root)
    for p in paths:
        if (migrations and p.startswith(migrations.rstrip("/") + "/")) or (schema and p == schema):
            found.setdefault("data-model", f"planned path `{p}`")
        if DEPENDENCY_PATHS.search(p):
            found.setdefault("dependency", f"planned path `{p}`")
    if (m := DEPENDENCY_TEXT.search(text)):
        found.setdefault("dependency", f"plan says `{m.group(0).strip()}`")
    components = sorted({"/".join(p.split("/")[:2]) for p in paths if not BOOKKEEPING.match(p)})
    if len(components) >= BREADTH:
        found["breadth"] = f"{len(components)} components ({', '.join(components[:8])})"
    return found


def _filler(reason: str) -> bool:
    import check_threat_model  # noqa: E402

    return check_threat_model._is_filler(reason)


def judge_record(record: str, current_hash: str, current_files: list[str], current_cats: set[str]) -> list[str]:
    """Why the record does not cover the plan as it is now; empty when it does."""
    lines = record.splitlines()
    problems: list[str] = []
    files = [ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Plan:")]
    reviewed = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Plan-SHA256:")), "")
    disposed = [ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Disposed-SHA256:")]
    cats = next((ln.split(":", 1)[1] for ln in lines if ln.startswith("Categories:")), None)
    if not files or not reviewed or cats is None:
        return ["the record has no `Plan:`, `Plan-SHA256:` or `Categories:` header: write it with `advisory_scope.py --begin`"]
    if missing := [f for f in current_files if f not in files]:
        problems.append(f"plan files written after the review are not covered: {', '.join(missing)}: run a new advisor pass")
    if current_hash != reviewed and (not disposed or disposed[-1] != current_hash):
        problems.append("the plan changed since it was reviewed and the change is not stamped: run `advisory_scope.py --stamp`, "
                        "or a new advisor pass")
    reviewed_cats = {c.strip() for c in cats.split(",") if c.strip()}
    if new := sorted(current_cats - reviewed_cats):
        problems.append(f"the plan now triggers {', '.join(new)}, which the review did not see: run a new advisor pass")
    verdicts = [ln.split(":", 1)[1].strip().upper() for ln in lines if re.match(r"^\s*VERDICT\s*:", ln)]
    if not verdicts or verdicts[-1] not in ("PROCEED", "RETHINK"):
        problems.append("the record has no `VERDICT: PROCEED` or `VERDICT: RETHINK` line: save the advisor's answer verbatim")
    findings = []
    for ln in lines:
        m = FINDING_RE.match(ln)
        if m and not DISPOSITION_RE.match(ln) and m.group(1) not in findings:
            findings.append(m.group(1))
    disposed_ids: dict[str, int] = {}
    for ln in lines:
        m = DISPOSITION_RE.match(ln)
        if not m:
            continue
        fid, kind, reason = m.group(1).upper(), m.group(2).lower(), m.group(3).strip()
        disposed_ids[fid] = disposed_ids.get(fid, 0) + 1
        if fid not in findings:
            problems.append(f"Disposition {fid} names a finding the advisor's answer does not have")
        if kind not in ("accepted", "rejected", "deferred"):
            problems.append(f"Disposition {fid}: `{kind}` is not accepted, rejected or deferred")
        if _filler(reason):
            problems.append(f"Disposition {fid}: the reason is empty or only a filler word")
        if kind == "deferred" and not re.search(r"#\d+", reason):
            problems.append(f"Disposition {fid}: a deferral names the issue it waits on (`#n`)")
    for fid in findings:
        if fid not in disposed_ids:
            problems.append(f"finding {fid} has no disposition: accepted, rejected or deferred, with a reason")
        elif disposed_ids[fid] > 1:
            problems.append(f"finding {fid} is disposed twice: one disposition per finding")
    if verdicts and verdicts[-1] == "RETHINK":
        overrides = [OVERRIDE_RE.match(ln) for ln in lines if ln.strip().lower().startswith("override")]
        good = [m for m in overrides if m and len(m.group(2)) >= REASON_MIN and not _filler(m.group(2))]
        if not good:
            problems.append("VERDICT: RETHINK blocks until a fresh advisor pass on the revised plan says PROCEED, or an "
                            f"`Override: <who> | <reason, {REASON_MIN}+ characters> | #<issue>` line records who decided")
    return problems


def changed_share(before: str, after: str) -> float:
    a, b = before.splitlines(), after.splitlines()
    same = sum(blk.size for blk in difflib.SequenceMatcher(None, a, b).get_matching_blocks())
    return 1 - same / max(len(a), len(b), 1)


def slug_of(root: Path) -> str:
    # symbolic-ref, not rev-parse: it names the branch before its first commit too (a plan is often written before any).
    out = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True).stdout.strip()
    return out.split("/", 1)[1].replace("/", "-") if "/" in out else ""


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(prog="advisory_scope.py", description=__doc__.splitlines()[0])
    ap.add_argument("--slug", default="")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--begin", action="store_true")
    ap.add_argument("--stamp", action="store_true")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    slug = a.slug or slug_of(root)
    files = plan_files(root, slug) if slug else []
    if not files:
        if a.begin or a.stamp or a.slug:
            print(f"no plan for `{slug or '(no slug)'}`: none of {', '.join(p.format(slug=slug or '<slug>') for p in PLAN_FILES)} exists",
                  file=sys.stderr)
            return 2
        print("no plan on this branch: no advisory owed")
        return 0
    text = plan_text(root, files)
    cats = categories(root, text, planned_paths(text))
    record = root / RECORD.format(slug=slug)
    if a.begin:
        record.parent.mkdir(parents=True, exist_ok=True)
        (record.parent / SNAPSHOT).write_text(text, encoding="utf-8")
        record.write_text("".join(f"Plan: {f}\n" for f in files) + f"Plan-SHA256: {plan_hash(text)}\n"
                          f"Categories: {', '.join(sorted(cats))}\n\n", encoding="utf-8")
        print(f"{record}: header written; run `advisor` on the plan and append its answer verbatim")
        return 0
    if not cats:
        print("advisory optional: the plan names no security boundary, structure, data-model or dependency change, "
              f"and spans fewer than {BREADTH} components")
        return 0
    if not record.is_file():
        print(f"advisory REQUIRED ({'; '.join(f'{k}: {v}' for k, v in sorted(cats.items()))}), and no record at {record}.\n"
              f"Run `advisory_scope.py --begin`, then the `advisor` agent on the plan, append its answer, dispose each finding.",
              file=sys.stderr)
        return 1
    try:
        body = record.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{record}: unreadable: {exc}", file=sys.stderr)
        return 2
    if a.stamp:
        snap = record.parent / SNAPSHOT
        if not snap.is_file():
            print(f"no reviewed-plan snapshot at {snap}: run `--begin` before the advisor pass", file=sys.stderr)
            return 1
        share = changed_share(snap.read_text(encoding="utf-8"), text)
        open_ = [p for p in judge_record(body + f"\nDisposed-SHA256: {plan_hash(text)}\n", plan_hash(text), files, set(cats))]
        if share > RESTAMP_MAX:
            open_.append(f"{share:.0%} of the plan changed since review, over {RESTAMP_MAX:.0%}: run a new advisor pass")
        if open_:
            print("cannot stamp:\n" + "\n".join(f"  - {p}" for p in open_), file=sys.stderr)
            return 1
        record.write_text(body.rstrip("\n") + f"\nDisposed-SHA256: {plan_hash(text)}\nChanged: {share:.0%}\n", encoding="utf-8")
        print(f"stamped: {share:.0%} of the plan changed since review")
        return 0
    problems = judge_record(body, plan_hash(text), files, set(cats))
    if problems:
        print(f"{record} does not cover the plan:\n" + "\n".join(f"  - {p}" for p in problems), file=sys.stderr)
        return 1
    print(f"advisory recorded and disposed for {slug} ({', '.join(sorted(cats))})")
    return 0


def selftest() -> int:  # noqa: C901 -- one fixture table, read top to bottom
    import contextlib
    import io
    import tempfile

    bad = 0

    def check(ok: bool, label: str) -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL {label}")

    lay = ("db/migrate", "db/schema.rb")
    # An EMPTY project directory: the stack detector reads the project tree, and the system temp root holds every other run's files.
    empty = Path(tempfile.mkdtemp(prefix="advisory-empty-"))
    for label, text, want in (
            ("a plain plan triggers nothing", "Add a notes field to `app/views/notes/show.html.erb`.", set()),
            ("a webhook is security", "Receive the partner webhook at `app/controllers/hooks_controller.rb`.", {"security"}),
            ("a new agent path is structure", "Write `plugins/x/agents/advisor.md`.", {"structure"}),
            ("plan text adding a hook is structure", "Add a hook that refuses the push.", {"structure"}),
            ("a migration path is data-model", "Write `db/migrate/20261021_add_x.rb`.", {"data-model"}),
            ("the schema path is data-model", "Regenerate `db/schema.rb`.", {"data-model"}),
            ("a lockfile is dependency", "Update `Gemfile.lock`.", {"dependency"}),
            ("adding a gem is dependency", "Add the pagy gem.", {"dependency"}),
            ("six components is breadth", " ".join(f"`{c}/x/y.rb`" for c in ("a", "b", "c", "d", "e", "f")), {"breadth"}),
            ("five components is not breadth", " ".join(f"`{c}/x/y.rb`" for c in ("a", "b", "c", "d", "e")), set()),
            ("bookkeeping paths do not count toward breadth",
             " ".join(f"`{c}/y.md`" for c in ("changelog.d", "dist", "docs/wiki", "docs/evidence", "docs/architecture", "a/x")), set()),
    ):
        got = set(categories(empty, text, planned_paths(text), lay))
        check(got == want, f"{label}: got {sorted(got)}, expected {sorted(want)}")

    good = ("Plan: docs/product/acceptance/u.md\nPlan-SHA256: H\nCategories: security\n\n"
            "Findings:\n- A-1 the token outlives logout\n- A-2 the layer order is backwards\n"
            "VERDICT: PROCEED\n"
            "Disposition A-1: accepted | the plan now expires tokens on logout\n"
            "Disposition A-2: deferred | layer order moves to #77\n")
    files, cats = ["docs/product/acceptance/u.md"], {"security"}
    for label, rec, h, cur_cats, needle in (
            ("a complete record covers the plan", good, "H", cats, None),
            ("an undisposed finding is refused", good.replace("Disposition A-2: deferred | layer order moves to #77\n", ""), "H", cats, "A-2 has no disposition"),
            ("a finding disposed twice is refused", good + "Disposition A-2: rejected | not a real problem at all here\n", "H", cats, "disposed twice"),
            ("a disposition for a finding that does not exist is refused", good + "Disposition A-9: rejected | nothing to see in this one\n", "H", cats, "does not have"),
            ("a filler reason is refused", good.replace("the plan now expires tokens on logout", "TBD"), "H", cats, "filler"),
            ("a deferral without an issue is refused", good.replace("layer order moves to #77", "layer order moves later on"), "H", cats, "names the issue"),
            ("an unknown disposition kind is refused", good.replace("Disposition A-1: accepted", "Disposition A-1: ignored"), "H", cats, "not accepted, rejected"),
            ("no verdict is refused", good.replace("VERDICT: PROCEED\n", ""), "H", cats, "no `VERDICT"),
            ("a changed plan with no stamp is refused", good, "H2", cats, "not stamped"),
            ("a changed plan with its stamp is covered", good + "Disposed-SHA256: H2\n", "H2", cats, None),
            ("a new category is refused", good, "H", {"security", "breadth"}, "breadth"),
            ("RETHINK with no override is refused", good.replace("VERDICT: PROCEED", "VERDICT: RETHINK"), "H", cats, "RETHINK blocks"),
            ("RETHINK with a short override is refused", good.replace("VERDICT: PROCEED", "VERDICT: RETHINK") + "Override: owner | fine | #9\n", "H", cats, "RETHINK blocks"),
            ("RETHINK with an override and no issue is refused",
             good.replace("VERDICT: PROCEED", "VERDICT: RETHINK") + "Override: owner | the premise is deliberate, see the ruling\n", "H", cats, "RETHINK blocks"),
            ("RETHINK with a full override is covered",
             good.replace("VERDICT: PROCEED", "VERDICT: RETHINK") + "Override: owner | the premise is deliberate, per the ruling | #9\n", "H", cats, None),
            ("a header-less record is refused", "VERDICT: PROCEED\n", "H", cats, "--begin"),
    ):
        problems = judge_record(rec, h, files, cur_cats)
        ok = (not problems) if needle is None else any(needle in p for p in problems)
        check(ok, f"{label}: {problems}")
    check(any("not covered" in p for p in judge_record(good, "H", files + ["docs/security/threat-models/u.md"], cats)),
          "a plan file written after the review is not covered")
    check(abs(changed_share("a\nb\nc\nd\n", "a\nb\nc\nX\n") - 0.25) < 1e-9, "a quarter of the lines changed is 25%")

    # main(), end to end in a scratch repo: --begin, the record, --stamp under and over the threshold, and the exits.
    import fixture_git  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixture_git.init(td, "-b", "feature/u")
        acc = root / "docs/product/acceptance/u.md"
        acc.parent.mkdir(parents=True)
        lines = [f"- **AC-{i}** Given a user, when they post to the partner webhook, then it answers {i}" for i in range(1, 11)]
        acc.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def run(*args: str) -> tuple[int, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--root", td, *args])
            return code, out.getvalue() + err.getvalue()

        code, out = run()
        check(code == 1 and "REQUIRED" in out, f"a required advisory with no record is exit 1: {code} {out[:120]}")
        check(run("--slug", "nope")[0] == 2, "a slug with no plan files is exit 2")
        check(run("--begin")[0] == 0, "--begin writes the header")
        rec = root / RECORD.format(slug="u")
        rec.write_text(rec.read_text() + "- A-1 the webhook trusts the body\nVERDICT: PROCEED\n"
                       "Disposition A-1: accepted | the plan now verifies the signature first\n", encoding="utf-8")
        code, out = run()
        check(code == 0, f"a disposed record for the unchanged plan is exit 0: {code} {out[:160]}")
        acc.write_text("\n".join(lines[:9] + [lines[9] + " and is signed"]) + "\n", encoding="utf-8")
        code, out = run()
        check(code == 1 and "not stamped" in out, f"an edited plan with no stamp is exit 1: {code} {out[:160]}")
        code, out = run("--stamp")
        check(code == 0 and "stamped" in out, f"a small edit stamps: {code} {out[:160]}")
        check(run()[0] == 0, "the stamped plan is covered")
        acc.write_text("\n".join(lines[:5] + [ln + " differently" for ln in lines[5:]]) + "\n", encoding="utf-8")
        code, out = run("--stamp")
        check(code == 1 and "over 30%" in out, f"a rewrite over 30% cannot be stamped: {code} {out[:160]}")
    if bad == 0:
        print("advisory_scope selftest: every case passes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
