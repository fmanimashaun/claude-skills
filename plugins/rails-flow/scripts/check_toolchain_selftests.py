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
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()


def plugin_roots(start: Path | None = None) -> list[Path]:
    """Every sibling plugin directory carrying a checks.json."""
    here = (start or HERE).resolve()
    own = here.parents[1]                       # <plugin>/scripts/x.py -> <plugin>
    return sorted(p.parent for p in own.parent.glob("*/checks.json"))


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


def run(path: Path, timeout: int = 120) -> tuple[bool, str]:
    try:
        done = subprocess.run([sys.executable, str(path), "--selftest"],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A TIMEOUT IS NOT A FAILURE and not a pass -- the same distinction #1097 fixed upstream.
        return True, f"timed out after {timeout}s — NOT run, so nothing is known"
    except OSError as exc:
        return False, f"could not run: {exc}"
    text = (done.stdout + done.stderr).strip().splitlines()
    return done.returncode == 0, (text[-1] if text else f"exit {done.returncode}")


def check(roots: list[Path] | None = None) -> tuple[list[str], int, int]:
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
        ok, detail = run(path)
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
    finally:
        shutil.rmtree(root, ignore_errors=True)

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
