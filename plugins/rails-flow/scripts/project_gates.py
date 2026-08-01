#!/usr/bin/env python3
"""Run every shipped check that applies to THIS project — one command, locally and in CI.

Run:  python3 project_gates.py            # run what applies; exit 1 on any failure
      python3 project_gates.py --list      # say what applies and what does not, run nothing
      python3 project_gates.py --selftest  # prove the states and the applicability rules

WHY (#334). The plugins ship eleven checks that run against a *user's* repo, and no way to run them
together. A user had to know each script existed, know which applied, and invoke each by hand — which
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


def report(results: list[Result], problems: list[str]) -> int:
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        mark = {PASS: "ok  ", FAIL: "FAIL", NA: "n/a ", ERROR: "ERR "}[r.status]
        line = f"  [{mark}] {r.check.plugin}/{r.check.id}"
        print(f"{line:44} {r.detail}" if r.detail else line)
    for p in problems:
        print(f"  [ERR ] {p}", file=sys.stderr)
    bad = [r for r in results if r.status in (FAIL, ERROR)]
    na = [r for r in results if r.status == NA]
    print(f"\n{len(results) - len(bad) - len(na)} passed, {len(bad)} failed, "
          f"{len(na)} not applicable, {len(problems)} manifest problem(s).")
    if na:
        # Said every run, not only when it is convenient: a not-applicable check did NOT verify
        # anything, and a summary that lets it read as a pass is the defect this tool exists to stop.
        print("Not applicable is NOT a pass — those checks verified nothing:")
        for r in na:
            print(f"  - {r.check.plugin}/{r.check.id}: {r.detail}")
    return 1 if bad or problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run every shipped check that applies to this project.")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="repo to check (default: cwd)")
    ap.add_argument("--list", action="store_true", help="report applicability, run nothing")
    ap.add_argument("--selftest", action="store_true", help="prove the states and the rules")
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
    return report([run_check(c, project) for c in checks], problems)


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

    # The SHIPPED manifests must be loadable and name scripts that exist -- otherwise this runner
    # reports ERROR on a user's first run, which is the worst possible first impression.
    checks, problems = load_checks(plugin_roots(Path(__file__)))
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
        usage = helped.stdout.split("\n\n", 1)[0]
        group = re.search(r"\{([a-z,]+)\}\s*\.\.\.", usage)
        if not group:
            continue                       # no subcommands: a bare invocation is legitimate
        options = set(group.group(1).split(","))
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
