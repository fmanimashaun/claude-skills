#!/usr/bin/env python3
"""Prove the toolchain's own gates still discriminate IN THIS PROJECT (#1109).

Run:  python3 check_toolchain_selftests.py
      python3 check_toolchain_selftests.py --selftest

WHY THIS EXISTS. A project gets the gates and no proof they work. Measured on the marketplace the
day this was written: **33 consumer gate entries, 20 shipped check scripts, 20 of 20 carrying a
`--selftest`, and 0 of 33 entries running one.** Upstream, `mutation coverage` runs 1000 mutations
across 97 guards and is the only reason any of it is trusted -- and on that same day it caught
**four gates written that day being partly vacuous**, every one of which looked right and passed its
own fixtures. None of that machinery crosses into a project.

So a shipped check whose regex stops matching after a Rails or Tailwind upgrade reports clean for
ever, and the project reads it as health. That is "0 findings over input it never read", which is
the one failure this toolchain is organised to refuse.

WHAT THIS ADDS THAT UPSTREAM CI CANNOT. Our CI proves a check discriminates **on our machine, on our
tree, on our Python**. It can never prove it discriminates on yours. A selftest run here answers the
question our CI is structurally unable to answer, which is why it is worth the seconds.

ONE GATE, NOT TWENTY-NINE. Every selftest could have been its own consumer gate entry. That would
nearly double the gate count with checks that almost always pass, and a report nobody finishes
reading is one nobody acts on. This runs them all and names only what failed.

A CHECK WITH NO SELFTEST IS REPORTED, NOT SKIPPED. It is a check nobody has proved, and silence
about it would be the same vacuous pass this file exists to refuse.

EXIT CODES follow the consumer-gate contract: 0 every selftest passed, 1 one or more FAILED (the
gate is broken here -- ours to fix, not the project's), 3 nothing could be discovered.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()


def plugin_roots(start: Path | None = None) -> list[Path]:
    """One directory per installed PLUGIN that ships a checks.json, never one per cached version: `project_gates.plugin_roots`, the one walk (#2137).

    This used to be its own flat walk (`parents[1].parent.glob("*/checks.json")`), right in a source checkout and wrong where the toolchain runs, the installed
    `<cache>/<plugin>/<version>/` layout, where `parents[1]` is a VERSION: it ran the selftests of every cached version of rails-flow and none of the sibling plugins'
    (qa-flow, pipeline, design-flow). An older cached `docs_layout.py` without the fixture marker then failed its `git add -A` under the current git shim, which
    blocked every Retask `gh pr ready`. `project_gates` fixed the same walk in #706; this reuses it so the two cannot disagree again."""
    import project_gates                        # a sibling script: this file is run from the same scripts directory
    return project_gates.plugin_roots((start or HERE).resolve())


def declared_checks(roots: list[Path]) -> list[tuple[str, str, Path]]:
    """(plugin, check id, script path) for every consumer gate naming a python script."""
    out = []
    for root in roots:
        try:
            data = json.loads((root / "checks.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        plugin = data.get("plugin", root.name)
        for raw in data.get("checks", []):
            script = next((c for c in raw.get("command", []) if str(c).endswith(".py")), None)
            if not script:
                continue                        # runs another tool; nothing of ours to prove
            path = Path(str(script).replace("{plugin}", str(root)))
            out.append((plugin, raw.get("id", "?"), path))
    return out


def supports_selftest(path: Path) -> bool:
    return path.is_file() and "--selftest" in path.read_text(encoding="utf-8", errors="replace")


SESSION_TOP = "CLAUDE_SESSION_PROJECT_TOP"


def selftest_env(base: dict | None = None, cwd: Path | str | None = None) -> dict:
    """The environment a shipped selftest runs under: the caller's, plus the session's project when the caller has none (#2111).

    A selftest that stages a fixture repository whole (`git add -A`: docs_layout, docs_due, ...) is let through by the rails-flow git shim only when the shim
    knows the session's project, from `CLAUDE_SESSION_PROJECT_TOP`, so it can refuse to treat THAT repository as a fixture. The SessionStart hook exports it only
    when it started in a repository; without it the shim fails closed and the selftest fails on `git add -A` for a reason that is the environment's, not the
    gate's or the project's (every Retask `gh pr ready` was blocked this way). This check runs IN the project, so it names the project: its git toplevel, never
    overriding a value the caller set. It only supplies what the variable exists to say, so the shim's exemption gets no wider."""
    env = dict(os.environ if base is None else base)
    if env.get(SESSION_TOP):
        return env
    try:
        done = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return env
    top = done.stdout.strip()
    if done.returncode == 0 and top:
        env[SESSION_TOP] = top
    return env


def run(path: Path, timeout: int = 120, cwd: Path | str | None = None) -> tuple[bool, str]:
    try:
        done = subprocess.run([sys.executable, str(path), "--selftest"],
                              capture_output=True, text=True, timeout=timeout, cwd=cwd,
                              env=selftest_env(cwd=cwd))
    except subprocess.TimeoutExpired:
        # A TIMEOUT IS NOT A FAILURE and not a pass -- the same distinction #1097 fixed upstream.
        return True, f"timed out after {timeout}s — NOT run, so nothing is known"
    except OSError as exc:
        return False, f"could not run: {exc}"
    text = (done.stdout + done.stderr).strip().splitlines()
    return done.returncode == 0, (text[-1] if text else f"exit {done.returncode}")


def check(roots: list[Path] | None = None, cwd: Path | str | None = None) -> tuple[list[str], int, int]:
    """(findings, selftests run, checks with no selftest)."""
    roots = roots if roots is not None else plugin_roots()
    findings, ran, unproven = [], 0, 0
    for plugin, ident, path in declared_checks(roots):
        if not path.is_file():
            findings.append(
                f"{plugin}/{ident}: the script it names is not there ({path.name}) — this gate "
                f"cannot have run, and a missing gate is not a passing one")
            continue
        if not supports_selftest(path):
            unproven += 1
            continue
        ran += 1
        ok, detail = run(path, cwd=cwd)
        if not ok:
            findings.append(
                f"{plugin}/{ident}: its own selftest FAILED here — {detail}. The gate is broken in "
                f"this project, which is not the same as your code being wrong: it may have rotted "
                f"against a framework or Python version this repo has and the toolchain's CI does "
                f"not. Report it upstream rather than chasing your own code")
    return findings, ran, unproven


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="toolchain-selftests-"))
    try:
        plug = root / "demo"
        (plug / "scripts").mkdir(parents=True)
        (plug / "scripts" / "good.py").write_text(
            "import sys\nif '--selftest' in sys.argv:\n    print('ran 3')\n    raise SystemExit(0)\n",
            encoding="utf-8")
        (plug / "scripts" / "broken.py").write_text(
            "import sys\nif '--selftest' in sys.argv:\n    print('1 FAILED')\n    raise SystemExit(1)\n",
            encoding="utf-8")
        (plug / "scripts" / "unproven.py").write_text("print('no selftest here')\n", encoding="utf-8")
        def manifest(*ids):
            return json.dumps({"plugin": "demo", "checks": [
                {"id": i, "why": "w", "command": ["python3", "{plugin}/scripts/" + s]}
                for i, s in ids]})

        (plug / "checks.json").write_text(manifest(("a", "good.py")), encoding="utf-8")
        f, ran, unproven = check([plug])
        expect("a passing selftest is silent, and counted as run", not f and ran == 1)

        (plug / "checks.json").write_text(manifest(("a", "good.py"), ("b", "broken.py")),
                                          encoding="utf-8")
        f, ran, _ = check([plug])
        expect("a FAILING selftest is reported", len(f) == 1 and "demo/b" in f[0])
        # THE MUST-PASS CONTROL on the same run: the healthy check beside it stays silent, so
        # "reports a failure" is not satisfied by a gate that reports everything.
        expect("...and the passing one beside it is NOT reported",
               not any("demo/a" in x for x in f))
        # THE DISTINCTION THAT KEEPS THIS USABLE. A broken gate is not a broken app, and saying so
        # is what stops a team chasing their own code -- or learning to ignore the gate.
        # `f and` so an EMPTY list fails this assertion instead of raising IndexError -- a
        # traceback is caught by the harness as "something went wrong", which hides WHICH fixture
        # was meant to notice. The mutation check says so by name.
        expect("...and says the gate is broken here, not that the project's code is wrong",
               bool(f) and "not the same as your code being wrong" in f[0])
        expect("the passing one still counted", ran == 2)

        # A check with NO selftest is nobody's proof. Counted, never silently accepted.
        (plug / "checks.json").write_text(manifest(("a", "good.py"), ("c", "unproven.py")),
                                          encoding="utf-8")
        f, ran, unproven = check([plug])
        expect("a check with no selftest is counted as unproven, not as a pass",
               not f and ran == 1 and unproven == 1)

        # A manifest naming a script that is not there: the gate never ran at all.
        (plug / "checks.json").write_text(manifest(("d", "missing.py")), encoding="utf-8")
        f, ran, _ = check([plug])
        expect("a manifest naming a missing script is a finding", len(f) == 1 and "not there" in f[0])

        f, ran, unproven = check([])
        expect("no plugin at all reports nothing AND says it ran nothing",
               not f and ran == 0 and unproven == 0)

        # #2111: THE SELFTEST'S ENVIRONMENT NAMES THE PROJECT when the caller did not. A real repository and a plain directory, both physical.
        repo, plain = root / "repo", root / "plain"
        repo.mkdir(); plain.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        top = str(repo.resolve())
        expect("an environment without the session's project gets the git toplevel of the cwd",
               selftest_env({}, cwd=repo).get(SESSION_TOP) == top)
        expect("an EMPTY value counts as not set", selftest_env({SESSION_TOP: ""}, cwd=repo).get(SESSION_TOP) == top)
        expect("a value the caller set is never overridden",
               selftest_env({SESSION_TOP: "/preset/project"}, cwd=repo).get(SESSION_TOP) == "/preset/project")
        expect("outside a repository nothing is invented", SESSION_TOP not in selftest_env({}, cwd=plain))
        expect("the rest of the caller's environment is kept", selftest_env({"KEEP": "1"}, cwd=repo).get("KEEP") == "1")
        # ...and it REACHES the child: a selftest that reports the variable it sees, run through `run()` itself, with the parent's value removed and then preset.
        (plug / "scripts" / "showenv.py").write_text(
            f"import os, sys\nif '--selftest' in sys.argv:\n    print('top=' + os.environ.get({SESSION_TOP!r}, '(unset)'))\n    raise SystemExit(0)\n", encoding="utf-8")
        saved = os.environ.pop(SESSION_TOP, None)
        try:
            ok_run, seen = run(plug / "scripts" / "showenv.py", cwd=repo)
            os.environ[SESSION_TOP] = "/preset/project"
            ok_preset, seen_preset = run(plug / "scripts" / "showenv.py", cwd=repo)
        finally:
            os.environ.pop(SESSION_TOP, None)
            if saved is not None:
                os.environ[SESSION_TOP] = saved
        expect("a selftest run by the check SEES the project it runs in, with none in the caller's environment",
               ok_run and seen == f"top={top}")
        expect("...and sees the caller's own value when there is one", ok_preset and seen_preset == "top=/preset/project")

        # #2137: THE INSTALLED LAYOUT, `<cache>/<plugin>/<version>/`, where `parents[1]` of a script is a VERSION directory. Two versions of rails-flow (the older one's selftest
        # FAILS, as docs_layout's did under the new git shim) and a sibling plugin; the walk must pick one directory per plugin, the invoked version, and the sibling.
        cache = root / "cache" / "claude-skills"

        def install(name: str, version: str, selftest_ok: bool) -> Path:
            d = cache / name / version
            (d / ".claude-plugin").mkdir(parents=True)
            (d / "scripts").mkdir()
            (d / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
            (d / "checks.json").write_text(json.dumps({"plugin": name, "checks": [{"id": "g", "why": "w", "command": ["python3", "{plugin}/scripts/g.py"]}]}), encoding="utf-8")
            (d / "scripts" / "g.py").write_text(f"import sys\nif '--selftest' in sys.argv:\n    print('{name} {version}')\n    raise SystemExit({0 if selftest_ok else 1})\n", encoding="utf-8")
            return d.resolve()

        old_v, new_v, sibling = install("rails-flow", "1.0.0", False), install("rails-flow", "1.1.0", True), install("qa-flow", "2.0.0", True)
        got = plugin_roots(new_v / "scripts" / "check_toolchain_selftests.py")
        expect("the installed layout: ONE directory per plugin, the invoked version, and the sibling plugin, never an older cached version",
               sorted(got) == sorted([new_v, sibling]))
        f, ran, _ = check(got)
        expect("an older cached version's FAILING selftest is not run, so it is not reported, and the sibling plugin's selftest IS run",
               not f and ran == 2)
        f_old, _, _ = check([old_v])
        expect("...while that same older version, asked for directly, does fail (the fixture can fail)", len(f_old) == 1)

        # the source-checkout layout still works through the same walk: `plugins/<name>/scripts/x.py`, siblings are the other plugins
        src = root / "src" / "plugins"
        for name in ("rails-flow", "qa-flow"):
            (src / name / "scripts").mkdir(parents=True)
            (src / name / "checks.json").write_text(json.dumps({"plugin": name, "checks": []}), encoding="utf-8")
        flat = plugin_roots(src.resolve() / "rails-flow" / "scripts" / "check_toolchain_selftests.py")
        expect("a source checkout still finds the sibling plugins", sorted(p.name for p in flat) == ["qa-flow", "rails-flow"])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # #1873: main()'s EXIT CODE when no selftest ran at all: not applicable (3), never a pass.
    import contextlib, io
    g, argv = globals(), sys.argv
    real_check = g["check"]
    g["check"], sys.argv = (lambda *a, **k: ([], 0, 0)), ["check_toolchain_selftests.py"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = main()
    finally:
        g["check"], sys.argv = real_check, argv
    expect("no shipped selftest found is not applicable (exit 3), never a pass", code == 3)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a failing selftest is reported as a broken GATE, never as a finding about the project")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    findings, ran, unproven = check()
    if ran == 0 and not findings:
        # NOT a pass. Zero selftests run reads exactly like a healthy toolchain.
        print("NOT APPLICABLE: no shipped check with a --selftest was found — this proved nothing.")
        return 3
    for f in findings:
        print(f"  {f}")
    print(f"\n{ran} toolchain selftest(s) run in this project; {len(findings)} finding(s).")
    if unproven:
        print(f"{unproven} shipped check(s) carry no --selftest, so nothing proves they still "
              f"discriminate here. That is a gap in the toolchain, not in your repo.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
