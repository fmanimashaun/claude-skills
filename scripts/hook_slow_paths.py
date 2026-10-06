#!/usr/bin/env python3
"""Time guard-bash.sh against inputs that make it slow, one process group per case (#1575, #1570).

A hook that spins is worse than a hook that is wrong: it blocks every Bash call and, when a timeout
kills only the parent `bash`, leaves its `awk` child computing. Measured 2026-10-03 on 9a3d9dc: 500
chained `echo hi;` segments inside `bash -c` cost 5.9 CPU-seconds and 1000 cost 40.6; 1000 lines of
`echo $(true) N` cost 25.5. A first attacker run killed only the parent and left orphans.

Each case therefore runs in its OWN process group (`start_new_session`) and a deadline kills the whole
group (`killpg`), awk included. A case is OVER when it hit the deadline or used more CPU than its bound.

#1519 made the two shapes above linear (0.1-0.3 CPU s at N=2000, from 5.9 -> 40.6), so no case is marked known-slow today.
#1575's deadline is the BACKSTOP for the next pathological input, and `check_hook_gates.py --only deadline` tests it.

The check is a ratchet in both directions, like `check_hook_output_budget.py`:
  * a case NOT marked known-slow that is over its bound is a FAIL (a regression);
  * a case marked known-slow that is NOT over its bound is a FAIL too -- the defect is fixed, so the
    marker must go, or nothing would ever notice it come back.
CPU seconds, not wall time: the machine this was measured on was at load average 130.

    python3 scripts/hook_slow_paths.py             # time the real hook (takes minutes; maintainer-run)
    python3 scripts/hook_slow_paths.py --selftest  # prove the harness itself (fast; a doctor gate)
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "plugins/rails-flow/hooks/scripts/guard-bash.sh"


@dataclass(frozen=True)
class Case:
    name: str
    command: str
    expected_rc: int          # the hook's own verdict: 2 = blocked, 0 = allowed
    cpu_bound: float          # CPU-seconds the hook may use on it
    known_slow: str = ""      # the issue that tracks it; empty = must stay within the bound


def run_case(hook: Path, command: str, deadline: float) -> tuple[object, float, float]:
    """(returncode or "TIMEOUT", wall seconds, CPU seconds of the reaped children)."""
    proc = subprocess.Popen(["/bin/bash", str(hook)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.time()
    try:
        proc.communicate(json.dumps({"tool_input": {"command": command}}).encode(), timeout=deadline)
        rc: object = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)       # the WHOLE group: a bare proc.kill() orphans awk
        proc.communicate()
        rc = "TIMEOUT"
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    return rc, round(time.time() - start, 1), round(cpu, 1)


def verdict(case: Case, rc: object, cpu: float) -> str:
    """"" when the case is as expected, else the reason it is not."""
    over = rc == "TIMEOUT" or cpu > case.cpu_bound
    if over and not case.known_slow:
        return f"over its bound ({cpu}s CPU > {case.cpu_bound}s, rc={rc}) and not marked known-slow"
    if case.known_slow and not over:
        return f"stale marker: {case.known_slow} says it is slow but it ran in {cpu}s CPU -- remove the marker"
    if rc != "TIMEOUT" and rc != case.expected_rc:
        return f"wrong verdict: exit {rc}, expected {case.expected_rc}"
    return ""


def cases() -> list[Case]:
    n = 1000
    return [
        Case("`git add -A` + 10k plain lines", "git add -A\n" + "".join(f"echo line {i}\n" for i in range(10000)), 2, 5.0),
        Case("`git status` + 10k plain lines (control)", "git status\n" + "".join(f"echo line {i}\n" for i in range(10000)), 0, 5.0),
        Case("10k-line heredoc inside $( ", "echo $(cat <<EOF\n" + "".join(f"line {i}\n" for i in range(10000)) + "EOF\n)\ngit add -A", 2, 5.0),
        Case(f"{n} lines of `echo $(true) N`", "".join(f"echo $(true) {i}\n" for i in range(n)) + "git add -A", 2, 5.0),
        Case(f"bash -c with {n} chained `echo hi;`", "bash -c '" + "echo hi; " * n + "git add -A'", 2, 5.0),
    ]


def real_run(deadline: float) -> int:
    bad = 0
    for case in cases():
        rc, wall, cpu = run_case(HOOK, case.command, deadline)
        why = verdict(case, rc, cpu)
        bad += bool(why)
        print(f"[{'FAIL' if why else ' ok '}] {case.name}: rc={rc} wall={wall}s cpu={cpu}s"
              + (f" -- {why}" if why else (f" (known slow: {case.known_slow})" if case.known_slow else "")))
    print(f"{len(cases())} cases, {bad} failed (deadline {deadline}s per case, one process group each)")
    return 1 if bad else 0


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as td:
        # A hook that forks a long sleeper and waits: the shape of bash plus an awk child. The sleeper
        # is detached from the pipes, so a parent-only kill ends the case at once and the survivor is
        # SEEN, instead of communicate() blocking on it until it exits.
        pidfile = Path(td) / "child.pid"
        hang = Path(td) / "hang.sh"
        hang.write_text(f"#!/bin/bash\nsleep 300 >/dev/null 2>&1 &\necho $! > {pidfile}\nwait\n")
        rc, wall, _ = run_case(hang, "x", deadline=1.0)
        check("a hung hook is reported as TIMEOUT", rc == "TIMEOUT", f"rc={rc}")
        check("the deadline is honoured", wall < 10, f"{wall}s")
        child = int(pidfile.read_text().strip()) if pidfile.exists() else 0
        alive = False
        for _ in range(40):                      # the kill is asynchronous; give it 2s
            try:
                os.kill(child, 0)
                alive = True
                time.sleep(0.05)
            except ProcessLookupError:
                alive = False
                break
        check("the whole process group is killed, so no orphaned child survives", child and not alive,
              f"child {child} still running: a bare kill() of the parent orphans it")
        if alive:
            os.kill(child, signal.SIGKILL)       # never leave our own orphan behind
        quick = Path(td) / "quick.sh"
        quick.write_text("#!/bin/bash\ncat > /dev/null\nexit 2\n")
        rc, _, cpu = run_case(quick, "x", deadline=10.0)
        check("a quick hook returns its own exit status", rc == 2, f"rc={rc}")

    ok = Case("ok", "", 2, 5.0)
    slow = Case("slow", "", 2, 5.0, "#1575")
    check("within bound and as expected is clean", verdict(ok, 2, 0.4) == "", verdict(ok, 2, 0.4))
    check("over the bound is a failure", "over its bound" in verdict(ok, 2, 9.0), verdict(ok, 2, 9.0))
    check("a timeout is over the bound", "over its bound" in verdict(ok, "TIMEOUT", 0.1), "")
    check("a known-slow case that is over is accepted", verdict(slow, "TIMEOUT", 0.1) == "", verdict(slow, "TIMEOUT", 0.1))
    check("a known-slow case that got fast is a stale marker", "stale marker" in verdict(slow, 2, 0.4),
          verdict(slow, 2, 0.4))
    check("the wrong verdict is a failure", "wrong verdict" in verdict(ok, 0, 0.4), verdict(ok, 0, 0.4))

    if failures:
        print("hook_slow_paths selftest FAILED:\n  - " + "\n  - ".join(failures))
        return 1
    print("hook_slow_paths selftest: all checks passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true", help="prove the harness itself (fast)")
    ap.add_argument("--deadline", type=float, default=30.0, help="wall-clock seconds before a case's process group is killed")
    args = ap.parse_args()
    return selftest() if args.selftest else real_run(args.deadline)


if __name__ == "__main__":
    sys.exit(main())
