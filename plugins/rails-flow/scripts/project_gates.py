#!/usr/bin/env python3
"""Run every shipped check that applies to THIS project — one command, locally and in CI.

Run:  python3 project_gates.py            # run what applies; exit 1 on any failure
      python3 project_gates.py --list      # say what applies and what does not, run nothing
      python3 project_gates.py --json      # the same run, machine-readable, with the routing
      python3 project_gates.py --selftest  # prove the states, the applicability rules, the routing

WHY (#334). The plugins shipped eleven checks that ran against a *user's* repo, and no way to run
them together. (Past tense, and no current count: this said "ship eleven" while the manifests
declared fifteen. The manifests are the count; a number restated here only goes stale.)
A user had to know each script existed, know which applied, and invoke each by hand — which
in practice meant **an agent ran them when it remembered.** That is the claims-vs-enforcement defect
this toolchain warns about, in the toolchain itself.

It matters most at **`dev → main`**, because that is the branch a project deploys from. `setup-flow`
§8 already puts the hosted CI at exactly that trigger; what runs there is the project's own test
matrix, and nothing verified the doctrine we shipped them before the deploy branch moved.

THE STATE MODEL, WHICH IS THE WHOLE DESIGN. Four outcomes, not two:

    pass            the check ran and was clean
    FAIL            the check ran and found something, or its dependency is missing
    not applicable  this repo has nothing for it to read -- REPORTED, never counted as a pass
    ERROR           the check could not be run at all (bad manifest, missing script)

`not applicable` is the one that has to be loud. A project with no `qa/` directory genuinely has no
QA evidence to validate, and calling that "passed" would let a repo with zero evidence report the
same green as a repo with complete evidence. The summary always prints how many were skipped and
why, for the same reason `maintainer_doctor` does.

A MISSING DEPENDENCY IS A FAILURE, NOT A SKIP. In CI a skip is indistinguishable from a pass unless
something asserts the dependency is there, so `requires` is checked and its absence FAILS.

NO BROWSER CHECKS HERE, deliberately. `rendered_conformance.py` needs Playwright, which is the user's
dependency and not installable from a plugin. A gate that quietly skips when the browser is absent is
worse than no gate; those stay in the agent-driven browser pass, where absence is visible.

REGISTRATION IS THE MANIFEST. Each plugin ships `checks.json` declaring its own; this runner never
hardcodes a list, so adding a check is one manifest entry and a new plugin needs no change here.

AND THEN: WHOSE TRACKER (#485). The four states say what happened, not where the fix goes, and the
summary used to add ERRORs into the same "failed" total as real findings. An ERROR is a manifest of
OURS naming a script that does not exist — a user reading "2 failed" files two bugs against their
own app, one of which is ours. So every non-pass outcome is now routed:

    app          the detector ran against this project's content and found something -> their tracker
    doctrine     the check produced no verdict at all, which project content cannot cause -> ours,
                 reportable with /rails-flow:report
    environment  a required binary is absent -> neither their code nor our doctrine; install it
    unrouted     `not applicable` -- reported, and deliberately routed NOWHERE

WHAT THE ROUTING DOES NOT CLAIM, stated because the omission is the interesting part. A FAIL routes
to `app` because the detector ran and worked. That is correct for every check shipped today and it
is a **default, not a proof**: a check that catches the toolchain scaffolding half a pattern — its
own doctrine mandates a container, its own setup never emits one — is a FAIL that belongs upstream,
and no rule here can tell that apart from a defect in the project's code. Such detectors do not
exist yet, and `checks.json` therefore carries **no** destination field: a field with one
hypothetical consumer is indirection, not a seam. The check that needs it adds it, and until then
the default must not be widened to guess — a confidently wrong route is worse than no route.

`unrouted` is the routing layer's version of "not applicable is not a pass". One run cannot tell a
project that genuinely has no `qa/` from a check aimed at a path nothing writes — that second case
is a doctrine gap, and reconciling it needs the whole plugin, not one project. It has its own
maintainer-side gate upstream and is not re-derived here.

Exit codes:  0 all applicable checks passed · 1 at least one FAIL or ERROR · 2 nothing discovered

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PASS, FAIL, NA, ERROR = "pass", "FAIL", "n/a", "ERROR"

# Destinations. See the module docstring for why each outcome routes where it does.
APP, DOCTRINE, ENVIRONMENT, UNROUTED = "app", "doctrine", "environment", "unrouted"

# The headline printed once per destination, and the action it asks for. Kept beside the constants
# so a new destination cannot be added without saying where its findings are supposed to go.
DESTINATIONS: dict[str, tuple[str, str]] = {
    APP: ("this project's own tracker",
          "the detector ran against this project's content and found something"),
    DOCTRINE: ("upstream, via /rails-flow:report",
               "the check produced no verdict at all, and this project's content cannot cause that"),
    ENVIRONMENT: ("nobody's tracker — install the binary",
                  "a required dependency is absent, so neither this code nor our doctrine is at fault"),
}


@dataclass
class Check:
    plugin: str
    id: str
    why: str
    command: list[str]
    applies_when: list[str]
    requires: list[str]
    root: Path            # the plugin directory this came from


@dataclass
class Result:
    check: Check
    status: str
    detail: str = ""


def plugin_roots(start: Path) -> list[Path]:
    """Every installed plugin directory that ships a `checks.json`.

    Siblings are discovered rather than configured: plugins are installed independently, so a repo
    may have rails-flow and not design-flow. A plugin that is not installed contributes nothing --
    which is different from a check that is installed and does not apply, and the report says which.
    """
    own = start.resolve().parents[1]          # <plugin>/scripts/x.py -> <plugin>
    roots = {own} if (own / "checks.json").is_file() else set()
    for sibling in own.parent.iterdir():
        if sibling.is_dir() and (sibling / "checks.json").is_file():
            roots.add(sibling)
    return sorted(roots)


def load_checks(roots: list[Path]) -> tuple[list[Check], list[str]]:
    checks: list[Check] = []
    problems: list[str] = []
    for root in roots:
        path = root / "checks.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: unreadable manifest ({exc})")
            continue
        for raw in data.get("checks", []):
            missing = [k for k in ("id", "why", "command") if k not in raw]
            if missing:
                problems.append(f"{path}: a check is missing {missing}")
                continue
            checks.append(Check(
                plugin=data.get("plugin", root.name), id=raw["id"], why=raw["why"],
                command=list(raw["command"]), applies_when=list(raw.get("applies_when", [])),
                requires=list(raw.get("requires", [])), root=root))
    return checks, problems


def expand(command: list[str], check: Check, project: Path) -> list[list[str]]:
    """Resolve `{plugin}` and `{match:glob}` into concrete argv lists.

    A `{match:...}` command runs ONCE PER MATCHING FILE, because the underlying scripts take a single
    path. Returning a list of argvs rather than one keeps that in the runner instead of asking every
    script to grow multi-path handling it does not need.
    """
    argvs: list[list[str]] = [[]]
    for token in command:
        if token.startswith("{match:") and token.endswith("}"):
            pattern = token[len("{match:"):-1]
            hits = sorted(str(p) for p in project.glob(pattern))
            if not hits:
                return []          # applicability is decided by the caller; no files means nothing to run
            argvs = [a + [h] for a in argvs for h in hits]
        else:
            argvs = [a + [token.replace("{plugin}", str(check.root))] for a in argvs]
    return argvs


def applicability(check: Check, project: Path) -> str | None:
    """None if the check applies; otherwise the reason it does not."""
    absent = [p for p in check.applies_when if not (project / p).exists()]
    if absent:
        return f"no {', '.join(absent)} in this project"
    for token in check.command:
        if token.startswith("{match:") and token.endswith("}"):
            if not list(project.glob(token[len("{match:"):-1])):
                return f"nothing matches {token[len('{match:'):-1]}"
    return None


def required_subcommand(help_text: str) -> set[str]:
    """The subparser choices a script REQUIRES, or an empty set if it takes none.

    Two signals together, because either alone is wrong: the group must sit in the `usage:` block,
    and argparse follows a subparser group with ` ...`. Matching `{a,b}` anywhere in the help fired a
    false positive on a `--format {json,md}` choice list in the options body.

    Extracted from its caller so a fixture can exercise it directly. Inline, a mutation that neutered
    it deleted the only assertion that would have noticed -- a check that cannot fail.
    """
    usage = help_text.split("\n\n", 1)[0]
    found = re.search(r"\{([a-z,]+)\}\s*\.\.\.", usage)
    return set(found.group(1).split(",")) if found else set()


def missing_dependencies(check: Check) -> list[str]:
    """Required binaries absent from PATH.

    A named query so the router asks the same question `run_check` asks, rather than recognising a
    dependency failure by the wording of its message. Recognising it by text is how a message edit
    silently re-routes findings to the wrong tracker.

    `run_check` asks it inline rather than calling this, so the two must be held in agreement by
    test rather than by construction — the selftest pins both directions.
    """
    return [b for b in check.requires if shutil.which(b) is None]


def route_of(result: Result) -> tuple[str, str]:
    """Whose tracker this outcome belongs to, and why. `("", "")` when there is nothing to route.

    Derived from the outcome, never declared per check -- see the module docstring for the one case
    this deliberately cannot decide and does not pretend to.
    """
    if result.status == PASS:
        return "", ""
    if result.status == NA:
        return UNROUTED, ("not applicable verified nothing, so it is nobody's finding yet — but it "
                          "is also not a pass")
    if result.status == ERROR:
        return DOCTRINE, DESTINATIONS[DOCTRINE][1]
    if missing_dependencies(result.check):
        return ENVIRONMENT, DESTINATIONS[ENVIRONMENT][1]
    return APP, DESTINATIONS[APP][1]


def run_check(check: Check, project: Path) -> Result:
    why_not = applicability(check, project)
    if why_not:
        return Result(check, NA, why_not)
    for binary in check.requires:
        if shutil.which(binary) is None:
            # NOT a skip. See the module docstring: in CI a skip reads as a pass.
            return Result(check, FAIL, f"`{binary}` is not on PATH, so this check could not run")
    argvs = expand(check.command, check, project)
    if not argvs:
        return Result(check, ERROR, "command expanded to nothing")
    for argv in argvs:
        script = Path(argv[1]) if len(argv) > 1 else None
        if script is not None and script.suffix == ".py" and not script.is_file():
            return Result(check, ERROR, f"{script} does not exist — manifest and plugin disagree")
        try:
            done = subprocess.run(argv, cwd=project, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return Result(check, ERROR, f"{type(exc).__name__}: {exc}")
        if done.returncode != 0:
            first = (done.stdout + done.stderr).strip().splitlines()
            return Result(check, FAIL, (first[0][:160] if first else f"exit {done.returncode}"))
    return Result(check, PASS, f"{len(argvs)} invocation(s)")


def routed(results: list[Result], problems: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Non-pass outcomes grouped by destination, as (what, detail) pairs.

    `unrouted` is absent by design: the not-applicable block already lists those, and printing one
    list twice trains people to skim both.
    """
    groups: dict[str, list[tuple[str, str]]] = {d: [] for d in DESTINATIONS}
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        destination = route_of(r)[0]
        if destination in groups:
            groups[destination].append((f"{r.check.plugin}/{r.check.id}", r.detail))
    # A manifest that will not parse is ours by the same argument an ERROR is: the project did not
    # write it. It never reaches `run_check`, so it has no Result to route.
    groups[DOCTRINE].extend(("checks.json", p) for p in problems)
    return groups


def report(results: list[Result], problems: list[str]) -> int:
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        mark = {PASS: "ok  ", FAIL: "FAIL", NA: "n/a ", ERROR: "ERR "}[r.status]
        line = f"  [{mark}] {r.check.plugin}/{r.check.id}"
        print(f"{line:44} {r.detail}" if r.detail else line)
    for p in problems:
        print(f"  [ERR ] {p}", file=sys.stderr)
    fails = [r for r in results if r.status == FAIL]
    errors = [r for r in results if r.status == ERROR]
    na = [r for r in results if r.status == NA]
    # ERRORs are counted SEPARATELY from failures, not folded into one "failed" total. An ERROR is
    # this toolchain's manifest disagreeing with this toolchain's own scripts; adding it to the
    # number a user reads as "defects in my app" is how our bug becomes their bug report (#485).
    print(f"\n{len(results) - len(fails) - len(errors) - len(na)} passed, {len(fails)} failed, "
          f"{len(errors)} errored, {len(na)} not applicable, {len(problems)} manifest problem(s).")
    if na:
        # Said every run, not only when it is convenient: a not-applicable check did NOT verify
        # anything, and a summary that lets it read as a pass is the defect this tool exists to stop.
        print("Not applicable is NOT a pass — those checks verified nothing, and they are routed "
              "to no tracker:")
        for r in na:
            print(f"  - {r.check.plugin}/{r.check.id}: {r.detail}")
    groups = routed(results, problems)
    if any(groups.values()):
        print("\nWhere each finding goes — a gap this toolchain caused is not a gap in your app:")
        for destination, entries in groups.items():
            where, why = DESTINATIONS[destination]
            print(f"  {destination.upper()} ({len(entries)}) → {where} — {why}")
            for what, detail in entries:
                print(f"    - {what}: {detail}")
        if groups[DOCTRINE]:
            print("  Hand the DOCTRINE list to /rails-flow:report — one observation per report.")
    return exit_code(results, problems)


def as_json(results: list[Result], problems: list[str]) -> str:
    """The same run as `report`, for an agent that has to act on it rather than read it.

    Routing exists so a finding reaches the right tracker without a human re-deciding each time; a
    destination an agent must recover by parsing prose is the same defect one step later.
    """
    rows = []
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        destination, why = route_of(r)
        rows.append({"plugin": r.check.plugin, "id": r.check.id, "why": r.check.why,
                     "status": r.status, "detail": r.detail,
                     "destination": destination or None, "routed_because": why or None})
    return json.dumps({
        "results": rows,
        "manifest_problems": problems,
        "summary": {status: sum(1 for r in results if r.status == status)
                    for status in (PASS, FAIL, NA, ERROR)},
    }, indent=2, sort_keys=False)


def exit_code(results: list[Result], problems: list[str]) -> int:
    """0 all applicable checks passed, 1 at least one FAIL or ERROR. Shared so the text and JSON
    paths cannot drift into disagreeing about whether the same run failed."""
    return 1 if problems or any(r.status in (FAIL, ERROR) for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run every shipped check that applies to this project.")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="repo to check (default: cwd)")
    ap.add_argument("--list", action="store_true", help="report applicability, run nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable results, with the routing")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the states, the applicability rules and the routing")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    checks, problems = load_checks(plugin_roots(Path(__file__)))
    if not checks and not problems:
        print("No plugin shipped a checks.json — nothing to run, and that is not a pass.",
              file=sys.stderr)
        return 2
    project = args.project.resolve()
    if args.list:
        for c in sorted(checks, key=lambda c: (c.plugin, c.id)):
            why_not = applicability(c, project)
            print(f"  [{'n/a ' if why_not else 'runs'}] {c.plugin}/{c.id:24} "
                  f"{why_not or c.why}")
        return 0
    results = [run_check(c, project) for c in checks]
    if args.json:
        print(as_json(results, problems))
        return exit_code(results, problems)
    return report(results, problems)


def selftest() -> int:
    import tempfile
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "plug"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "ok.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        (root / "scripts" / "bad.py").write_text(
            "import sys; print('a finding'); sys.exit(1)\n", encoding="utf-8")
        project = Path(tmp) / "proj"
        (project / "docs").mkdir(parents=True)
        (project / "docs" / "a.md").write_text("x\n", encoding="utf-8")

        def mk(**kw):
            base = dict(plugin="p", id="c", why="w", command=["python3", str(root / "scripts/ok.py")],
                        applies_when=[], requires=[], root=root)
            base.update(kw)
            return Check(**base)

        check("a passing check reports pass", run_check(mk(), project).status == PASS)
        r = run_check(mk(command=["python3", str(root / "scripts/bad.py")]), project)
        check("a failing check reports FAIL", r.status == FAIL, f"got {r.status}")
        check("a failure carries the finding's first line", "a finding" in r.detail, r.detail)
        # NOT APPLICABLE, and the two ways it arises.
        r = run_check(mk(applies_when=["qa"]), project)
        check("a missing directory is n/a, not pass", r.status == NA, f"got {r.status}")
        check("n/a says WHY", "qa" in r.detail, f"got {r.detail!r}")
        r = run_check(mk(command=["python3", str(root / "scripts/ok.py"), "{match:qa/*.csv}"]), project)
        check("an empty glob is n/a, not pass", r.status == NA, f"got {r.status}")
        # A MISSING DEPENDENCY FAILS. This is the one that would otherwise read as a pass in CI.
        r = run_check(mk(requires=["definitely-not-a-real-binary-xyz"]), project)
        check("a missing dependency FAILS rather than skipping", r.status == FAIL, f"got {r.status}")
        check("and says which binary", "definitely-not-a-real-binary-xyz" in r.detail, r.detail)
        # A manifest naming a script that does not exist is an ERROR, never a quiet pass.
        r = run_check(mk(command=["python3", str(root / "scripts/gone.py")]), project)
        check("a missing script is ERROR", r.status == ERROR, f"got {r.status}")
        # {match:} runs once per file.
        (project / "docs" / "b.md").write_text("y\n", encoding="utf-8")
        r = run_check(mk(command=["python3", str(root / "scripts/ok.py"), "{match:docs/*.md}"]), project)
        check("a match runs once per file", r.status == PASS and "2 invocation" in r.detail, r.detail)
        # THE SUMMARY MUST NOT COUNT n/a AS PASSED. The near-miss that matters: a repo where
        # everything is inapplicable must not exit 0 looking like a repo where everything passed.
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report([Result(mk(), NA, "no qa in this project")], [])
        out = buf.getvalue()
        check("an all-n/a run says so loudly", "NOT a pass" in out, out[:120])
        check("an all-n/a run reports 0 passed", "0 passed" in out, out[:120])
        check("an all-n/a run still exits 0 (nothing failed)", code == 0, f"got {code}")

        # ROUTING (#485). Every assertion below is paired with its negative, because the value of a
        # destination is entirely in what it REFUSES to send to the app's tracker. A router that
        # answers `app` to everything is indistinguishable from no router at all, and it is the
        # shape this would naturally decay into.
        passing = run_check(mk(), project)
        check("a pass routes nowhere", route_of(passing) == ("", ""), f"got {route_of(passing)}")

        found = run_check(mk(command=["python3", str(root / "scripts/bad.py")]), project)
        check("a check that ran and found something routes to the app",
              route_of(found)[0] == APP, f"got {route_of(found)}")

        errored = run_check(mk(command=["python3", str(root / "scripts/gone.py")]), project)
        check("an ERROR routes to DOCTRINE, not the app",
              route_of(errored)[0] == DOCTRINE,
              "a manifest naming a script we do not ship is our bug; routing it to the project's "
              f"tracker files our defect against their code (got {route_of(errored)})")

        absent = run_check(mk(requires=["definitely-not-a-real-binary-xyz"]), project)
        check("a missing dependency routes to ENVIRONMENT, not the app",
              route_of(absent)[0] == ENVIRONMENT,
              f"it FAILS (correctly) but no code is at fault (got {route_of(absent)})")
        # THE NEAR MISS, which is the whole value of the carve-out. `environment` is an exemption
        # from `app`, and an exemption keyed on "the check declares requires" instead of "a required
        # binary is actually absent" would divert every real finding from every check that declares
        # a dependency -- which is all of them.
        declared = run_check(mk(command=["python3", str(root / "scripts/bad.py")],
                                requires=["python3"]), project)
        check("a real finding from a check whose dependencies are PRESENT still routes to the app",
              route_of(declared)[0] == APP,
              f"declaring `requires` must not exempt a check from its own findings "
              f"(got {route_of(declared)})")
        # `run_check` asks `shutil.which` inline and the router asks `missing_dependencies`. Nothing
        # makes them the same code, so pin that they answer alike -- in both directions.
        check("missing_dependencies agrees with run_check on an absent binary",
              missing_dependencies(absent.check) == ["definitely-not-a-real-binary-xyz"] and
              absent.status == FAIL, f"{missing_dependencies(absent.check)}, {absent.status}")
        check("missing_dependencies agrees with run_check on a present binary",
              missing_dependencies(declared.check) == [] and "not on PATH" not in declared.detail,
              f"{missing_dependencies(declared.check)}, {declared.detail!r}")

        skipped = run_check(mk(applies_when=["qa"]), project)
        check("not applicable routes NOWHERE, and specifically not to the app",
              route_of(skipped)[0] == UNROUTED, f"got {route_of(skipped)}")
        check("unrouted is not a destination anything is filed against",
              UNROUTED not in DESTINATIONS,
              "a headline for `unrouted` would print a tracker to send non-findings to")
        check("a not-applicable check appears in NO destination group",
              not any(routed([skipped], []).values()), f"{routed([skipped], [])}")
        check("every destination declares where its findings go and why",
              all(len(v) == 2 and all(v) for v in DESTINATIONS.values()), f"{DESTINATIONS}")

        # THE SUMMARY MUST NOT ADD ERRORS INTO THE FAILURE COUNT. This is the defect the routing
        # was written for: before #485 an ERROR was folded into "N failed", so a user read our
        # broken manifest as a defect in their own app and had no way to tell.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report([found, errored], [])
        out = buf.getvalue()
        check("an ERROR is counted apart from a failure", "1 failed, 1 errored" in out, out[:200])
        check("the report says where each finding goes", "Where each finding goes" in out, out[:200])
        check("a doctrine gap names the upstream route", "/rails-flow:report" in out, out[:400])
        check("a mixed run still exits 1", code == 1, f"got {code}")

        # A manifest that will not parse has no Result, and must still reach the doctrine list.
        check("a manifest problem routes to DOCTRINE",
              routed([], ["checks.json: unreadable manifest"])[DOCTRINE] ==
              [("checks.json", "checks.json: unreadable manifest")],
              f"{routed([], ['checks.json: unreadable manifest'])}")
        check("a manifest problem alone still exits 1", exit_code([], ["boom"]) == 1)

        # THE MACHINE PATH MUST CARRY THE ROUTING, or an agent re-derives it by parsing prose.
        payload = json.loads(as_json([passing, found, errored, skipped], ["boom"]))
        destinations = [row["destination"] for row in payload["results"]]
        check("--json routes every non-pass row",
              destinations.count(None) == 1 and set(destinations) ==
              {None, APP, DOCTRINE, UNROUTED}, f"got {destinations}")
        check("--json states why each row was routed",
              all(row["routed_because"] for row in payload["results"] if row["destination"]),
              "a destination with no reason cannot be argued with")
        check("--json carries the manifest problems", payload["manifest_problems"] == ["boom"])
        check("--json counts every state", payload["summary"] == {PASS: 1, FAIL: 1, NA: 1, ERROR: 1},
              f"{payload['summary']}")

    # The SHIPPED manifests must be loadable and name scripts that exist -- otherwise this runner
    # reports ERROR on a user's first run, which is the worst possible first impression.
    checks, problems = load_checks(plugin_roots(Path(__file__)))
    # The subparser detector, fixtured directly. Both directions, because the false positive is what
    # would get this rule deleted and the true positive is what it exists for.
    check("a subparser group is detected",
          required_subcommand("usage: p [-h] {completed,derive,validate} ...\n\noptions:\n") ==
          {"completed", "derive", "validate"})
    check("a --format choice list is NOT a subcommand",
          required_subcommand("usage: p [-h] [--out OUT]\n\noptions:\n  --format {json,md}\n") == set(),
          "a choice list in the options body must not read as a required subcommand")
    check("a script with no subparsers reports none",
          required_subcommand("usage: p [-h] [--selftest] [path]\n\noptions:\n") == set())

    check("shipped manifests parse", not problems, f"{problems}")
    check("shipped manifests declare checks", len(checks) >= 5, f"got {len(checks)}")

    # EVERY SHIPPED COMMAND MUST SUPPLY A REQUIRED SUBCOMMAND. I declared `evidence_manifest.py`
    # bare; it requires one of {completed,derive,validate,index,prune}, so it exited on a usage error
    # and the runner reported FAIL. The runner was right and the MANIFEST was wrong, and nothing
    # would have caught it before a user's first run.
    #
    # An earlier version of this assertion ran `<prefix> --help` and was VACUOUS: argparse prints the
    # top-level help and exits 0 whether or not a subcommand is required, so re-introducing the bug
    # sailed through. Caught by mutating the manifest and watching the check stay silent. It now
    # reads the usage line for a `{a,b,c}` group and requires the manifest to have chosen one.
    for c in checks:
        argv = [tok.replace("{plugin}", str(c.root)) for tok in c.command
                if not tok.startswith("{match:")]
        script = argv[1] if len(argv) > 1 else None
        if not script or not script.endswith(".py"):
            continue
        try:
            helped = subprocess.run([argv[0], script, "--help"], capture_output=True,
                                    text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            check(f"{c.plugin}/{c.id} help runs", False, str(exc)[:90])
            continue
        check(f"{c.plugin}/{c.id} help runs", helped.returncode == 0, f"exit {helped.returncode}")
        # Only a SUBPARSER group counts, and it is identified by two things together: it sits in the
        # `usage:` block, and argparse follows it with ` ...`. Matching `{a,b}` anywhere in the help
        # produced a false positive on `architecture_graph.py`, whose `{json,md}` is a --format
        # choice list in the options body -- a rule that fires on a correct manifest gets deleted,
        # so the pattern is narrowed rather than the finding excused.
        options = required_subcommand(helped.stdout)
        if not options:
            continue                       # no subcommands: a bare invocation is legitimate
        supplied = [tok for tok in argv[2:] if not tok.startswith("-")]
        check(f"{c.plugin}/{c.id} supplies a required subcommand",
              bool(supplied) and supplied[0] in options,
              f"needs one of {sorted(options)}, manifest supplies {supplied[:1] or 'nothing'}")
    for c in checks:
        target = Path(c.command[1].replace("{plugin}", str(c.root))) if len(c.command) > 1 else None
        if target and target.suffix == ".py":
            check(f"{c.plugin}/{c.id} names a real script", target.is_file(), f"{target} missing")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"project_gates selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
