#!/usr/bin/env python3
"""Refuse a slice plan that cannot be worked in order: a cycle, a dangling edge, a slice with no criteria (#1369).

Run:  python3 check_slices.py docs/product/slices/<slug>.md              # check (exit 0/1/2)
      python3 check_slices.py docs/product/slices/<slug>.md --order      # slice ids, blockers first
      python3 check_slices.py docs/product/slices/<slug>.md --issue-body S3 --filed S1=101,S2=102
      python3 check_slices.py --selftest

WHY. `/rails-flow:brief` ended by pointing at "the first slice", and nothing produced the slices.
`/rails-flow:slice` drafts them. This file is what makes the draft safe to file: a plan with a cycle
has no first slice, an edge to a slice that does not exist is a blocker nobody will ever close, and
a slice without criteria is a hope, not a task (`check_criteria.py`'s rule, one level up).

THE SHAPE (a contract, like `check_brief.py`'s headings):

    # Slices: <what is being built>
    Source: docs/product/specs/<slug>.md

    ## S1 — Sign in with an email link
    Mock-up: no visible change
    - **AC-1** Given a registered address, when the user submits it, then an email with a link is sent
    - **AC-2** Given an unknown address, when the user submits it, then the same message shows [error]

    ## S2 — Remember the device
    depends-on: S1
    Mock-up: docs/design/remember-device.png
    - **AC-3** ...

  * `## S<n> — <title>` opens a slice. No deeper headings inside one: `check_criteria.py` treats a
    heading as a unit, so a `### Criteria` would detach the criteria from their slice.
  * `depends-on:` names other slices (`S2`) or existing issues (`#93`), comma-separated, on one
    strict line. A line that starts `depends-on:` and does not match is REFUSED rather than read
    loosely, because a dropped edge is how a blocked slice gets started first.
  * Every slice carries a Mock-up declaration, in `check_issue_mockup.py`'s shape (#1376): a link to
    the mock-up, or "no visible change".
  * The criteria are `check_criteria.py`'s, checked by `check_criteria.py`, including its rule that
    every unit has an error-path criterion. One reader, not two.

FILED, THE EDGES KEEP THE SAME SYNTAX `check_issue_ready.py` ALREADY READS. `--issue-body S3 --filed
S1=101` prints the issue body with `depends-on: S1` rewritten to `depends-on: #101`, so
`/rails-flow:issues` works the frontier through the existing `check_issue_ready.py --queue` rather
than a new reader. It refuses while any blocker is still unfiled: filing in `--order` guarantees the
number exists when a dependent needs it.

WHAT IT DOES NOT: judge whether a slice is truly vertical (complete through every layer and
demoable), or sized to one context. That is the command's advice, reviewed by the owner at the
approval step. It checks only what a script can check.

Exit: 0 clean · 1 findings · 2 unusable (no file, or no slices in it).
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_criteria  # noqa: E402 -- the criteria reader and rules, not a second copy
import check_issue_mockup  # noqa: E402 -- the Mock-up declaration reader (#1376)

SLICE_RE = re.compile(r"^##\s+(S\d+)\s*[—–:-]\s*(\S.*?)\s*$")
EDGE_LINE = re.compile(r"^\s*depends-on\s*:", re.I)
EDGE_STRICT = re.compile(r"^\s*depends-on\s*:\s*((?:S\d+|#\d+)(?:\s*,\s*(?:S\d+|#\d+))*)\s*$")
TOKEN = re.compile(r"S\d+|#\d+")


class Unusable(Exception):
    """The plan cannot be checked -- never report clean for it."""


@dataclass
class Slice:
    sid: str
    title: str
    line_no: int
    body: list[str] = field(default_factory=list)
    slices: list[str] = field(default_factory=list)   # edges to other slices
    issues: list[str] = field(default_factory=list)   # edges to existing issues, as "#n"
    malformed: list[int] = field(default_factory=list)


def parse(text: str) -> tuple[list[Slice], list[int]]:
    """Slices in file order, and the line numbers of AC definitions outside any slice."""
    slices: list[Slice] = []
    orphans: list[int] = []
    current: Slice | None = None
    fence: str | None = None     # the info string of the open fence, "" for a plain one
    for no, raw in enumerate(text.splitlines(), start=1):
        f = re.match(r"^[ \t]*```[ \t]*(\w*)", raw)
        if f:
            fence = None if fence is not None else f.group(1)
        m = SLICE_RE.match(raw) if fence is None else None
        if m:
            current = Slice(m.group(1), m.group(2), no)
            slices.append(current)
            continue
        if raw.startswith("## "):
            current = None          # a non-slice section ends the slice before it
        if current is None:
            if check_criteria.BOLD_ID_RE.search(raw) or check_criteria.DEF_RE.match(raw):
                orphans.append(no)
            continue
        current.body.append(raw)
        # A `depends-on:` inside a plain or code fence is a SAMPLE, not an edge. check_issue_ready.py
        # strips every non-`deps` fence, so counting it here would put an edge in the plan that the
        # filed issue drops (pre-release review of #1397).
        if fence not in (None, "deps"):
            continue
        if EDGE_LINE.match(raw):
            strict = EDGE_STRICT.match(raw)
            if not strict:
                current.malformed.append(no)
                continue
            for tok in TOKEN.findall(strict.group(1)):
                (current.issues if tok.startswith("#") else current.slices).append(tok)
    return slices, orphans


def order(slices: list[Slice]) -> list[str]:
    """Blockers first; ties broken by slice number so the order is stable. Assumes no cycle."""
    known = {s.sid for s in slices}
    deps = {s.sid: {d for d in s.slices if d in known and d != s.sid} for s in slices}
    done: list[str] = []
    while len(done) < len(deps):
        ready = sorted((sid for sid, d in deps.items() if sid not in done and d <= set(done)),
                       key=lambda sid: int(sid[1:]))
        if not ready:
            break
        done.append(ready[0])
    return done


def _cycle(slices: list[Slice]) -> list[str] | None:
    known = {s.sid for s in slices}
    graph = {s.sid: [d for d in s.slices if d in known] for s in slices}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(v: str) -> list[str] | None:
        state[v] = 1
        stack.append(v)
        for w in graph[v]:
            if state.get(w) == 1:
                return stack[stack.index(w):] + [w]
            if w not in state:
                found = visit(w)
                if found:
                    return found
        stack.pop()
        state[v] = 2
        return None

    for v in sorted(graph, key=lambda s: int(s[1:])):
        if v not in state:
            found = visit(v)
            if found:
                return found
    return None


def check(path: Path) -> tuple[list[Slice], list[str]]:
    if not path.is_file():
        raise Unusable(f"no such file: {path}")
    text = path.read_text(encoding="utf-8")
    slices, orphans = parse(text)
    if not slices:
        raise Unusable(f"{path} has no `## S<n> — <title>` slices — nothing to check is not a pass")
    findings: list[str] = []

    seen: dict[str, Slice] = {}
    for s in slices:
        if s.sid in seen:
            findings.append(f"{s.sid} (line {s.line_no}) is defined twice (first on line "
                            f"{seen[s.sid].line_no}) — an edge to it would be ambiguous")
        seen.setdefault(s.sid, s)
    for no in orphans:
        findings.append(f"line {no}: a criterion outside any slice belongs to nothing that gets filed")

    for s in slices:
        for no in s.malformed:
            findings.append(f"{s.sid} line {no}: a `depends-on:` line that is not "
                            "`depends-on: S2, #93` — refused, because a dropped edge starts a "
                            "blocked slice first")
        for d in s.slices:
            if d == s.sid:
                findings.append(f"{s.sid} depends on itself, so it can never start")
            elif d not in seen:
                findings.append(f"{s.sid} depends on {d}, which no slice defines — a blocker "
                                "nobody will ever close")
        ok, why = check_issue_mockup.verdict("\n".join(s.body))
        if not ok:
            findings.append(f"{s.sid}: Mock-up — {why}")

    cyc = _cycle(slices)
    if cyc:
        findings.append("cycle: " + " -> ".join(cyc) + " — nothing in it can ever be the first slice")

    # Criteria: check_criteria's reader and rules, attributed back to the slice.
    try:
        criteria = check_criteria.parse(path)
    except check_criteria.Unusable as err:
        # "No criteria at all" is reported per slice below. Any OTHER refusal names a real defect
        # (two ids on one line, a Given/When/Then with a buried id) and must reach the author, not be
        # replaced by "every slice has no criteria", which would send them looking in the wrong place.
        criteria = []
        if "contains no `AC-n` criteria" not in str(err):
            findings.append(f"criteria: {err}")
    by_unit: dict[str, list] = {}
    for c in criteria:
        by_unit.setdefault(c.unit, []).append(c)
    # check_criteria names a unit by its heading text, so a slice's unit is "S<n> — <title>".
    covered = {m.group(1) for unit in by_unit if (m := SLICE_RE.match(f"## {unit}"))}
    for s in slices:
        if s.sid not in covered:
            findings.append(f"{s.sid} has no `AC-n` criteria — a slice with nothing to prove is a "
                            "hope, not a task")
    for problem in check_criteria.check(criteria) if criteria else []:
        findings.append(f"criteria: {problem}")
    return slices, findings


def issue_body(slices: list[Slice], sid: str, filed: dict[str, int], source: str | None) -> str:
    target = next((s for s in slices if s.sid == sid), None)
    if target is None:
        raise Unusable(f"{sid} is not a slice in this plan")
    unfiled = [d for d in target.slices if d not in filed]
    if unfiled:
        raise Unusable(f"{sid} depends on {', '.join(unfiled)}, not filed yet — file in `--order`, "
                       "so every blocker has a number before its dependent is written")
    lines = []
    for raw in target.body:
        if EDGE_STRICT.match(raw):
            refs = [f"#{filed[t]}" if t in filed else t for t in TOKEN.findall(raw)]
            lines.append(f"depends-on: {', '.join(refs)}")
        else:
            lines.append(raw)
    head = [f"Slice {sid} of `{source}`." if source else f"Slice {sid}.", ""]
    return "\n".join(head + lines).strip() + "\n"


def _parse_filed(raw: str | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(S\d+)=#?(\d+)", part)
        if not m:
            raise Unusable(f"--filed entry {part!r} is not S<n>=<issue number>")
        out[m.group(1)] = int(m.group(2))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a slice plan before it is filed.")
    ap.add_argument("plan", nargs="?", type=Path, help="docs/product/slices/<slug>.md")
    ap.add_argument("--order", action="store_true", help="print slice ids, blockers first")
    ap.add_argument("--issue-body", metavar="SLICE", help="print the issue body for one slice")
    ap.add_argument("--filed", help="slices already filed, as S1=101,S2=102")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.plan is None:
        ap.error("a slice plan is required (or --selftest)")
    try:
        slices, findings = check(args.plan)
        if findings:
            for f in findings:
                print(f"  {f}", file=sys.stderr)
            print(f"check_slices: {len(findings)} finding(s) in {args.plan} — fix before filing",
                  file=sys.stderr)
            return 1
        if args.issue_body:
            source = next((ln.split(":", 1)[1].strip()
                           for ln in args.plan.read_text(encoding="utf-8").splitlines()
                           if ln.lower().startswith("source:")), None)
            print(issue_body(slices, args.issue_body, _parse_filed(args.filed), source), end="")
            return 0
        seq = order(slices)
        if args.order:
            print("\n".join(seq))
            return 0
        print(f"check_slices: {len(slices)} slice(s), file in this order: {', '.join(seq)}")
        return 0
    except Unusable as err:
        print(f"UNUSABLE: {err}", file=sys.stderr)
        return 2


# ------------------------------------------------------------------------------------ selftest

AC_OK = ("- **AC-{a}** Given a registered address, when the user submits the sign-in form, then an "
         "email with a one-time link is sent\n"
         "- **AC-{b}** Given an unknown address, when the user submits the sign-in form, then the "
         "same confirmation message is shown and no email is sent [error]\n")


def _slice(n: int, *, deps: str = "", mock: str = "Mock-up: no visible change", ac: bool = True) -> str:
    parts = [f"## S{n} — Slice number {n}"]
    if deps:
        parts.append(deps)
    if mock:
        parts.append(mock)
    if ac:
        parts.append(AC_OK.format(a=n * 10 + 1, b=n * 10 + 2).rstrip("\n"))
    return "\n".join(parts) + "\n\n"


def selftest() -> int:  # noqa: PLR0915 -- a fixture list; each firing case sits beside its control
    failures: list[str] = []
    n = 0

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail else ''}")

    head = "# Slices: magic-link sign-in\nSource: docs/product/specs/sign-in.md\n\n"
    with tempfile.TemporaryDirectory() as tmp:
        def plan(*parts: str) -> Path:
            p = Path(tmp) / f"plan{len(list(Path(tmp).iterdir()))}.md"
            p.write_text(head + "".join(parts), encoding="utf-8")
            return p

        def findings(*parts: str) -> list[str]:
            return check(plan(*parts))[1]

        def has(fs: list[str], needle: str) -> bool:
            return any(needle in f for f in fs)

        # ---- the clean plan, and its order -------------------------------------------------------
        clean = plan(_slice(1), _slice(2, deps="depends-on: S1"), _slice(3, deps="depends-on: S1, S2, #93"))
        sl, fs = check(clean)
        check_that("a well-formed plan has no findings", fs == [], fs)
        check_that("...and orders blockers first", order(sl) == ["S1", "S2", "S3"], order(sl))
        # Pre-release review of #1397: a `depends-on:` inside a plain fence is a sample, not an edge,
        # exactly as check_issue_ready.py reads the filed body; a `deps` fence is an edge.
        sample = "## S1 — First\n\n```\ndepends-on: S9\n```\n"
        check_that("a depends-on inside a plain fence is not an edge",
                   parse(sample)[0][0].slices == [], parse(sample)[0][0].slices)
        deps = "## S1 — First\n\n```deps\ndepends-on: #93\n```\n"
        check_that("CONTROL: a depends-on inside a deps fence is an edge",
                   parse(deps)[0][0].issues == ["#93"], parse(deps)[0][0].issues)
        check_that("CONTROL: a bare depends-on line is an edge",
                   parse("## S1 — First\n\ndepends-on: #93\n")[0][0].issues == ["#93"])
        # Order follows the edges, not the numbering.
        sl2, _ = check(plan(_slice(1, deps="depends-on: S3"), _slice(2), _slice(3)))
        check_that("a slice numbered first but blocked by a later one is filed after it",
                   order(sl2) == ["S2", "S3", "S1"], order(sl2))
        check_that("an edge to an existing issue (#93) is accepted", not has(fs, "#93"))

        # ---- the three the issue names ---------------------------------------------------------------
        check_that("a cycle is refused",
                   has(findings(_slice(1, deps="depends-on: S2"), _slice(2, deps="depends-on: S1")),
                       "cycle: S1 -> S2 -> S1"))
        check_that("a dangling edge is refused",
                   has(findings(_slice(1, deps="depends-on: S9")), "S1 depends on S9, which no slice defines"))
        check_that("a slice with no criteria is refused",
                   has(findings(_slice(1), _slice(2, ac=False)), "S2 has no `AC-n` criteria"))
        # The control for it: the OTHER slice, which has criteria, is not named.
        check_that("...and only that slice is named",
                   not has(findings(_slice(1), _slice(2, ac=False)), "S1 has no"))

        # ---- the rest of the contract -----------------------------------------------------------------
        check_that("a slice depending on itself is refused",
                   has(findings(_slice(1, deps="depends-on: S1")), "depends on itself"))
        check_that("a loose `depends-on:` line is refused, not read loosely",
                   has(findings(_slice(1), _slice(2, deps="depends-on: S1 and maybe the login page")),
                       "not `depends-on: S2, #93`"))
        check_that("a slice defined twice is refused", has(findings(_slice(1), _slice(1)), "defined twice"))
        check_that("a slice with no Mock-up declaration is refused",
                   has(findings(_slice(1, mock="")), "S1: Mock-up"))
        check_that("a Mock-up link is accepted",
                   findings(_slice(1, mock="Mock-up: https://example.com/mock.png")) == [])
        check_that("a criterion outside any slice is refused",
                   has(findings("- **AC-99** Given x y z, when the user does a thing, then a thing "
                                "is visible [error]\n\n", _slice(1)), "outside any slice"))
        # check_criteria's own rules reach the slices: a happy-path-only slice is refused.
        happy = ("## S1 — Happy only\nMock-up: no visible change\n- **AC-1** Given a registered "
                 "address, when the user submits the sign-in form, then an email with a link is sent\n")
        check_that("check_criteria's error-path rule applies to each slice", has(findings(happy), "error-path"))
        two_ids = ("## S1 — Two ids\nMock-up: no visible change\n- AC-1 AC-2 Given a thing, when the "
                   "user acts on it, then a result is shown [error]\n")
        check_that("a criteria file check_criteria refuses says why, not just 'no criteria'",
                   has(findings(two_ids), "one definition line"), findings(two_ids))

        # ---- filing: the edges become the syntax check_issue_ready.py reads -------------------------
        body = issue_body(sl, "S3", {"S1": 101, "S2": 102}, "docs/product/specs/sign-in.md")
        check_that("a filed slice's edges are rewritten to issue numbers",
                   "depends-on: #101, #102, #93" in body, body)
        import check_issue_ready
        check_that("...in exactly the syntax check_issue_ready.py parses",
                   check_issue_ready.parse_edges(body).get("depends-on") == {101, 102, 93},
                   check_issue_ready.parse_edges(body))
        check_that("...and the Mock-up declaration survives into the issue",
                   check_issue_mockup.verdict(body)[0])
        try:
            issue_body(sl, "S3", {"S1": 101}, None)
            check_that("a slice whose blocker is not filed yet is refused", False)
        except Unusable as err:
            check_that("a slice whose blocker is not filed yet is refused", "S2" in str(err), err)

        # ---- the exit code carries the verdict -------------------------------------------------------
        import contextlib
        import io

        def code(args: list[str]) -> int:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main(args)
        check_that("a clean plan exits 0", code([str(clean)]) == 0)
        check_that("a plan with findings exits 1", code([str(plan(_slice(1, deps="depends-on: S9")))]) == 1)
        check_that("a file with no slices exits 2", code([str(plan("just prose\n"))]) == 2)
        check_that("a missing file exits 2", code([str(Path(tmp) / "absent.md")]) == 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(clean), "--order"])
        check_that("--order prints one id per line, blockers first", out.getvalue().split() == ["S1", "S2", "S3"])

    for f in failures:
        print(f"selftest FAIL: {f}", file=sys.stderr)
    print(f"check_slices selftest: {'FAILED' if failures else 'ok'} ({n} checks, {len(failures)} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
