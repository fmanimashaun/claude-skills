#!/usr/bin/env python3
"""Drive the REAL `guard-bash.sh` through the adversarial cases that found #1645's bypasses, and assert each one.

Run:  python3 scripts/check_guard_bash_cases.py --tier fast       # ~40 cases, inside the --fast sweep
      python3 scripts/check_guard_bash_cases.py --tier full       # every case: the full sweep only
      python3 scripts/check_guard_bash_cases.py --selftest        # prove each way of failing fires, and stays silent on a pass
      python3 scripts/check_guard_bash_cases.py --list            # the cases, one per line, with their expectations
      python3 scripts/check_guard_bash_cases.py --tier fast --match "fish -c"   # one row, by a fragment of its id

WHY (#1667). #1645 took five adversarial review rounds and every round found a real defect (a comment
swallowing the create after it, a verb trigger that needed a `gh` word, an exponential scan). They came from a
harness that lived on one reviewer's machine; `check_hook_gates.py` covers only a hand-picked subset of what it
tried. This commits the cases, so the next change to `guard-bash.sh` or `lib/issue_labels.py` meets them.

EVERY CASE CARRIES AN EXPECTATION: `block` or `allow`. A case the guard gets wrong TODAY (an unlabelled create
that passes, #1656) is recorded with `open` set, and `want` is what the guard does now. The gate fails in BOTH
directions: a `block` case that passes is a bypass, and an `open` case that changes is progress, which has to be
recorded ("update the expectation") or a later change could quietly undo it.

THE STUB. A `gh` and a `git` stub sit first on PATH and log every call. The hook only READS the command, so the
log must stay 0 bytes in both tiers: a byte in it means a command a case describes actually ran, which for a
create would be a real issue filed on a real repository. The gate fails on a non-empty log.

DEADLINE. The hook fails closed after 6 s. On a loaded machine that turns an `allow` case into a block that says
nothing about the guard, so a deadline outcome is retried once and, if it repeats, reported as "not a verdict"
(#1664), never as a regression.

Exit codes:  0 clean · 1 a finding · 2 unusable (no hook, no python3, or the case table is inconsistent)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import guard_bash_cases as data  # noqa: E402  (the case table; a sibling module)

HOOK = ROOT / "plugins/rails-flow/hooks/scripts/guard-bash.sh"
DEADLINE_TEXT = "took longer than"       # guard-bash.sh's own fail-closed message
MODES = ("full", "nogrep", "notr")
TIERS = ("fast", "full")
DECLARATION = {"groups": [{"one_of": ["comp:*"]}, {"one_of": ["type:*"]}, {"one_of": ["prio:*"]}]}
FAST_RANGE = (30, 60)                    # the fast tier has to stay a handful: it runs on every pull request


class StageError(RuntimeError):
    pass


def sub(text: str, fx: Path) -> str:
    """The placeholders the table uses, so a literal create never sits in a shell the table is typed into."""
    return (text.replace("@G@", "gh").replace("@I@", "issue").replace("@C@", "create")
                .replace("@N@", "new").replace("@FX@", str(fx)))


class Env:
    """A staged world: stubs first on PATH, a project that declares comp/type/prio, the fixtures."""

    def __init__(self, td: Path, hook: Path = HOOK):
        self.hook = hook
        self.log = td / "stub-calls.log"
        self.log.write_bytes(b"")
        self.fx = td / "fx"
        self.work = td / "work"
        stub = td / "stub"
        for d in (self.fx, self.work, stub):
            d.mkdir(parents=True, exist_ok=True)
        real_git = shutil.which("git") or "/usr/bin/git"
        (stub / "gh").write_text(f'#!/bin/sh\necho "STUB gh called: $*" >> "{self.log}"\nexit 0\n')
        (stub / "git").write_text(
            f'#!/bin/sh\nwhile [ "$1" = "-C" ]; do shift 2; done\ncase "$1" in\n'
            f'  rev-parse|remote|config|ls-files|status) exec "{real_git}" "$@" ;;\n'
            f'  *) echo "STUB git refused: $*" >> "{self.log}"; exit 99 ;;\nesac\n')
        for name in ("gh", "git"):
            (stub / name).chmod(0o755)
        (self.work / ".rails-flow").mkdir()
        (self.work / ".rails-flow" / "issue-labels.json").write_text(json.dumps(DECLARATION))
        subprocess.run([real_git, "init", "-q", str(self.work)], check=True, capture_output=True)
        python = shutil.which("python3")
        if not python:
            raise StageError("no python3 on PATH: the hook fails closed without it, so every case would read as a block")
        self._tail = str(Path(python).parent)
        self._stub = stub
        self._farm: dict[str, Path] = {}
        self._td = td
        data.materialise(self.fx, lambda s: sub(s, self.fx))

    def path(self, mode: str) -> str:
        if mode == "full":
            return os.pathsep.join([str(self._stub), "/usr/bin", "/bin", self._tail])
        if mode not in self._farm:
            skip = {"nogrep": {"grep", "egrep", "fgrep"}, "notr": {"tr"}}[mode]
            farm = self._td / f"path_{mode}"
            farm.mkdir()
            for src in ("/usr/bin", "/bin"):
                for name in os.listdir(src) if os.path.isdir(src) else ():
                    if name not in skip and not (farm / name).exists():
                        try:
                            os.symlink(f"{src}/{name}", farm / name)
                        except OSError:
                            pass
            self._farm[mode] = farm
        return os.pathsep.join([str(self._stub), str(self._farm[mode]), self._tail])

    def decide(self, case, timeout: int = 60) -> tuple[int, str]:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sub(case.cmd, self.fx)}})
        env = {"PATH": self.path(case.mode), "HOME": str(self._td), "LANG": "C"}
        done = subprocess.run(["bash", str(self.hook)], input=payload.encode("utf-8", "surrogateescape"), cwd=self.work,
                              env=env, capture_output=True, timeout=timeout)
        err = done.stderr.decode("utf-8", "replace").strip().splitlines()
        return done.returncode, (err[0] if err else "")


def validate(cases) -> list[str]:
    """The table's own consistency: the things a typo would otherwise turn into a case that cannot fail."""
    problems: list[str] = []
    ids = [c.id for c in cases]
    problems += [f"duplicate id {i!r}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for c in cases:
        if c.want not in ("block", "allow"):
            problems.append(f"{c.id}: want is {c.want!r}, not block or allow")
        if c.tier not in TIERS:
            problems.append(f"{c.id}: tier is {c.tier!r}")
        if c.mode not in MODES:
            problems.append(f"{c.id}: mode is {c.mode!r}")
    fast = [c for c in cases if c.tier == "fast"]
    if not FAST_RANGE[0] <= len(fast) <= FAST_RANGE[1]:
        problems.append(f"the fast tier has {len(fast)} cases, outside {FAST_RANGE[0]}..{FAST_RANGE[1]}")
    for why in sorted({c.open for c in cases if c.open}):
        if not any(c.open == why and c.tier == "fast" for c in cases):
            problems.append(f"no case of the open group {why!r} is in the fast tier, so progress on it is recorded only on a release")
    names = set(data.FIXTURES) | set(data.SPECIAL)
    for c in cases:
        for ref in data.fixture_refs(c.cmd):
            if ref not in names:
                problems.append(f"{c.id}: names fixture {ref!r}, which the table does not build")
    return problems


def judge(case, rc: int, why: str) -> str | None:
    """The finding for one outcome, or None when the guard did what the table says."""
    got = "block" if rc == 2 else "allow"
    if got == case.want:
        return None
    if case.open:
        return (f"{case.id}: an OPEN row changed: recorded as {case.want}, the guard now {got}s it ({case.open}). "
                f"If that is progress, update the expectation: set want={got!r} and clear open")
    kind = "BYPASS (an unlabelled create passes)" if case.want == "block" else "OVER-BLOCK"
    return f"{case.id}: {kind}: wanted {case.want}, got {got} (rc {rc}) {why[:120]}"


def run(cases, *, jobs: int = 4, hook: Path = HOOK, timeout: int = 60) -> tuple[list[str], dict]:
    findings: list[str] = []
    stats = {"cases": len(cases), "block": 0, "allow": 0, "open": 0, "seconds": 0.0}
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="guard-bash-cases-") as tmp:
        env = Env(Path(tmp), hook)

        def one(case):
            rc, why = env.decide(case, timeout)
            if rc == 2 and DEADLINE_TEXT in why:         # load, not a verdict: once more, alone (#1664)
                rc, why = env.decide(case, timeout)
                if rc == 2 and DEADLINE_TEXT in why and case.want == "allow":
                    return case, None, f"{case.id}: the hook's 6 s deadline hit twice: not a verdict (machine load?), re-run when idle"
            return case, judge(case, rc, why), None

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for case, finding, infra in pool.map(one, cases):
                stats["open" if case.open else case.want] += 1
                if infra:
                    findings.append(infra)
                elif finding:
                    findings.append(finding)
        called = env.log.read_bytes()
        if called:
            lines = called.decode("utf-8", "replace").strip().splitlines()
            findings.append(f"the stub log is {len(called)} bytes, not 0: a command a case describes RAN "
                            f"({len(lines)} call(s), first: {lines[0][:120]})")
    stats["seconds"] = round(time.monotonic() - began, 1)
    return findings, stats


# ---- selftest ------------------------------------------------------------------------------------
def selftest() -> int:
    failures: list[str] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"FAIL {label}" + (f": {detail}" if detail else ""))

    C = data.Case
    with tempfile.TemporaryDirectory(prefix="guard-bash-cases-selftest-") as tmp:
        counter = Path(tmp) / "flaky-count"
        fake = Path(tmp) / "fake-hook.sh"
        # BLOCKME blocks, RUNGH lets the stub be called, DEADLINE always trips the deadline, FLAKY trips it once.
        fake.write_text(
            '#!/bin/bash\nin=$(cat)\n'
            'case "$in" in\n'
            '  *RUNGH*) gh --version >/dev/null ;;\n'
            '  *DEADLINE*) echo "BLOCKED: this command took longer than 6s" >&2; exit 2 ;;\n'
            f'  *FLAKY*) n=$(cat "{counter}" 2>/dev/null || echo 0); echo $((n+1)) > "{counter}"\n'
            '      if [ "$n" = 0 ]; then echo "BLOCKED: took longer than 6s" >&2; exit 2; fi ;;\n'
            '  *BLOCKME*) echo "BLOCKED by fake" >&2; exit 2 ;;\n'
            'esac\nexit 0\n')

        def go(cases):
            return run(cases, jobs=1, hook=fake, timeout=20)

        ok_block = C("t:b", "fast", "full", "BLOCKME", "block")
        ok_allow = C("t:a", "fast", "full", "fine", "allow")
        found, stats = go([ok_block, ok_allow])
        expect("a block case that blocks and an allow case that allows are clean", not found, str(found))
        expect("...and the stats count them", (stats["block"], stats["allow"], stats["open"]) == (1, 1, 0), str(stats))
        found, _ = go([C("t:bypass", "fast", "full", "fine", "block")])
        expect("a block case the guard allows is a BYPASS", len(found) == 1 and "BYPASS" in found[0] and "t:bypass" in found[0], str(found))
        found, _ = go([C("t:over", "fast", "full", "BLOCKME", "allow")])
        expect("an allow case the guard blocks is an OVER-BLOCK", len(found) == 1 and "OVER-BLOCK" in found[0], str(found))
        found, stats = go([C("t:open", "fast", "full", "fine", "allow", "#1656 a runtime verb")])
        expect("an open row that still behaves as recorded is clean, and counted as open", not found and stats["open"] == 1, f"{found} {stats}")
        found, _ = go([C("t:open-flip", "fast", "full", "BLOCKME", "allow", "#1656 a runtime verb")])
        expect("an open row that CHANGES fails, and says to update the expectation",
               len(found) == 1 and "update the expectation" in found[0] and "t:open-flip" in found[0], str(found))
        found, _ = go([C("t:open-flip2", "fast", "full", "fine", "block", "an over-block")])
        expect("...in the other direction too (a recorded block that now allows)", len(found) == 1 and "OPEN row changed" in found[0], str(found))
        found, _ = go([C("t:ran", "fast", "full", "RUNGH", "allow")])
        expect("a case whose command RAN (the stub was called) fails on the log, even if the verdict is right",
               len(found) == 1 and "stub log" in found[0] and "RAN" in found[0], str(found))
        found, _ = go([C("t:deadline", "fast", "full", "DEADLINE", "allow")])
        expect("an allow case whose deadline repeats is 'not a verdict', never a regression",
               len(found) == 1 and "not a verdict" in found[0] and "OVER-BLOCK" not in found[0], str(found))
        found, _ = go([C("t:deadline-block", "fast", "full", "DEADLINE", "block")])
        expect("...while a block case that hit the deadline is still a block (the guard fails closed)", not found, str(found))
        counter.write_text("0")
        found, _ = go([C("t:flaky", "fast", "full", "FLAKY", "allow")])
        expect("a deadline that clears on the retry is judged on the retry", not found, str(found))

    # The table's own validator must be able to fail.
    good = [C(f"v:{i}", "fast", "full", "x", "block") for i in range(40)]
    expect("a consistent table validates", not validate(good), str(validate(good)))
    expect("a duplicate id is refused", any("duplicate" in p for p in validate(good + [good[0]])))
    expect("a want that is neither block nor allow is refused",
           any("not block or allow" in p for p in validate(good + [C("v:w", "fast", "full", "x", "deny")])))
    expect("an open group with no fast case is refused",
           any("open group" in p for p in validate(good + [C("v:o", "full", "full", "x", "allow", "#1656")])))
    expect("...and one with a fast case is not",
           not any("open group" in p for p in validate(good + [C("v:o", "full", "full", "x", "allow", "#1656"), C("v:p", "fast", "full", "x", "allow", "#1656")])))
    expect("a fast tier of 5 is refused", any("fast tier has 5" in p for p in validate(good[:5])))
    expect("a case naming a fixture the table does not build is refused",
           any("nosuch.sh" in p for p in validate(good + [C("v:f", "fast", "full", "bash @FX@/nosuch.sh", "block")])))
    # The shipped table.
    shipped = data.cases()
    problems = validate(shipped)
    expect("the shipped table validates", not problems, "; ".join(problems[:3]))
    expect("the shipped table covers a placeholder-free control and a known-open row",
           any(c.want == "allow" and not c.open for c in shipped) and any(c.open for c in shipped))
    if failures:
        print("\n".join(failures))
        print(f"check_guard_bash_cases selftest: {len(failures)} failure(s)")
        return 1
    print("check_guard_bash_cases selftest: 0 failure(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tier", choices=TIERS, help="fast: the ~40 cases a pull request runs; full: every case")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--match", metavar="FRAGMENT", help="only the cases whose id contains FRAGMENT (a mutation run narrows the table to the row it broke)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    cases = data.cases()
    problems = validate(cases)
    if problems:
        print("the case table is inconsistent:\n  " + "\n  ".join(problems))
        return 2
    if args.list:
        for c in cases:
            print(f"{c.tier:4s} {c.mode:6s} {'open ' if c.open else '     '}{c.want:5s} {c.id}")
        return 0
    if not args.tier:
        ap.error("give --tier fast|full, --selftest or --list")
    chosen = [c for c in cases if args.tier == "full" or c.tier == "fast"]
    if args.match:
        chosen = [c for c in chosen if args.match.lower() in c.id.lower()]
        if not chosen:
            print(f"--match {args.match!r} names no case in the {args.tier} tier")
            return 2
    if not HOOK.is_file():
        print(f"no hook at {HOOK}")
        return 2
    try:
        findings, stats = run(chosen, jobs=args.jobs)
    except StageError as exc:
        print(exc)
        return 2
    print(f"check_guard_bash_cases ({args.tier}): {stats['cases']} cases, {stats['block']} block, {stats['allow']} allow, "
          f"{stats['open']} open, {stats['seconds']} s, {len(findings)} finding(s)")
    for f in findings:
        print(f"  {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
