#!/usr/bin/env python3
"""Reap a finished session's own STOPPED ORPHANS (#1582 slice C).

THE LEAK. A session that starts a process and then stops it (SIGSTOP, a job-control stop, a debugger) and
exits leaves it re-parented to pid 1, stopped, for good: the 2026-10-03 incident left 74 and hit
`kern.maxprocperuid`. `process_containment.py` stops a fixture leaking; this reaps what a session left anyway.

WHOSE IT IS, DECIDED BY THE ENVIRONMENT, NEVER BY NAME. Claude Code starts every process of a session with
`CLAUDE_CODE_SESSION_ID=<session id>` in its environment, and the SessionEnd payload names the same id (the
transcript file is `<id>.jsonl`). A process is reaped only if ALL of these hold:
  1. its environment holds the WHOLE entry `CLAUDE_CODE_SESSION_ID=<this session's id>`;
  2. its parent is pid 1 (an orphan: nothing is waiting on it);
  3. it is STOPPED (state T): a running orphan may be a server the session meant to leave.
A command line that mentions the id, another session's process, a stopped child that still has a parent and a
running orphan all survive; the selftest holds a fixture for each. Matching a process by what it is called
(`pkill -f rspec`) killed other sessions' runs twice on 2026-10-04, and is what this refuses to do.
A process that clears its environment (`env -i`) is not found: the documented limit, as in process_containment.

ADVISORY: it ALWAYS exits 0 (a failed cleanup must not turn a session end into an error). SessionEnd cannot
block, and shares a 1.5 s budget unless the hook sets a `timeout`; this finishes in well under a second.

    echo '{"session_id": "<id>"}' | python3 session_reaper.py
    python3 session_reaper.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_containment import holding  # noqa: E402

SESSION_VAR = "CLAUDE_CODE_SESSION_ID"
_ID = re.compile(r"^[0-9A-Fa-f][0-9A-Fa-f-]{7,63}$")     # a uuid; never empty, never a prefix of everything


def stopped_orphans(session_id: str) -> list[int]:
    """The session's own processes that are orphaned (ppid 1) and stopped, by environment; [] on a bad id."""
    if not _ID.match(session_id or ""):
        return []
    pids = holding(SESSION_VAR, session_id)
    if not pids:
        return []
    out = subprocess.run(["ps", "-o", "pid=,ppid=,stat=", "-p", ",".join(map(str, pids))],
                         capture_output=True, text=True, check=False).stdout
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "1" and parts[2].startswith("T"):
            found.append(int(parts[0]))
    return found


def reap(session_id: str) -> list[int]:
    """CONT then TERM each stopped orphan, then KILL any still holding the id. Returns the pids it signalled."""
    targets = stopped_orphans(session_id)
    for pid in targets:
        for sig in (signal.SIGCONT, signal.SIGTERM):        # CONT first: a stopped process only sees TERM once resumed
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                break
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and set(holding(SESSION_VAR, session_id)) & set(targets):
        time.sleep(0.05)
    for pid in set(holding(SESSION_VAR, session_id)) & set(targets):    # still there after TERM, and still ours
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return targets


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    try:
        session_id = json.loads(sys.stdin.read() or "{}").get("session_id", "")
        killed = reap(session_id) if isinstance(session_id, str) else []
    except Exception:           # noqa: BLE001 -- advisory: a failed cleanup never fails a session end
        return 0
    if killed:
        print(f"session_reaper: stopped {len(killed)} orphan(s) of this session: {killed}", file=sys.stderr)
    return 0


# A LEAF records its pid and (optionally) stops itself; its PARENT exits at once, so the leaf is a stopped orphan.
_LEAF = ("import os, signal, sys, time\n"
         "open(sys.argv[1], 'a').write(f'{os.getpid()}\\n')\n"
         "if sys.argv[2] == 'stubborn':\n    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
         "if sys.argv[2] in ('stop', 'stubborn'):\n    os.kill(os.getpid(), signal.SIGSTOP)\n"
         "time.sleep(120)\n")
_PARENT = ("import subprocess, sys\n"
           "N = subprocess.DEVNULL\n"
           f"subprocess.Popen([sys.executable, '-c', {_LEAF!r}] + sys.argv[1:], start_new_session=True, stdin=N, stdout=N, stderr=N)\n")


def selftest() -> int:
    failures: list[str] = []
    work = tempfile.mkdtemp(prefix="reaper-selftest-")
    mine, other = "11111111-2222-3333-4444-555555555555", "99999999-8888-7777-6666-555555555555"
    started: list[int] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    def state(pid: int) -> str:
        return subprocess.run(["ps", "-o", "stat=,ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.split()

    def alive(pid: int) -> bool:
        s = state(pid)
        return bool(s) and not s[0].startswith("Z")

    def spawn(name: str, env_id: str | None, mode: str, extra: tuple = (), orphan: bool = True) -> int:
        """Start one leaf and return its pid. `env_id` None: no id in the environment at all."""
        path = os.path.join(work, name)
        env = {k: v for k, v in os.environ.items() if k != SESSION_VAR}
        if env_id is not None:
            env[SESSION_VAR] = env_id
        if orphan:
            subprocess.run([sys.executable, "-c", _PARENT, path, mode, *extra], env=env, check=False)
        else:
            subprocess.Popen([sys.executable, "-c", _LEAF, path, mode, *extra], env=env, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(path) and open(path).read().strip():
                pid = int(open(path).read().split()[0])
                s = state(pid)
                if s and (mode == "run" or s[0].startswith("T")) and (not orphan or s[1] == "1"):
                    started.append(pid)
                    return pid
            time.sleep(0.05)
        failures.append(f"{name}: fixture never reached its shape (stopped orphan or not)")
        return -1

    try:
        target = spawn("mine-stopped-orphan", mine, "stop")
        decoy = spawn("decoy-in-argv", None, "stop", extra=(f"{SESSION_VAR}={mine}", mine))
        foreign = spawn("other-session", other, "stop")
        running = spawn("mine-running-orphan", mine, "run")
        stubborn = spawn("mine-ignores-term", mine, "stubborn")
        blank = spawn("empty-id", "", "stop")      # SESSION_VAR set to the empty string: must not match an empty id
        child = spawn("mine-stopped-with-parent", mine, "stop", orphan=False)
        # The not-orphan fixture is stopped by its own `kill -STOP`, with its parent (this selftest) alive: ppid is not 1.
        check("fixture: the stopped child has a live parent", child > 0 and state(child)[1] != "1", f"{state(child)}")

        check("finds exactly the session's stopped orphan, by environment",
              sorted(stopped_orphans(mine)) == sorted([target, stubborn]), f"got {stopped_orphans(mine)}, want [{target}, {stubborn}]")
        check("a bad id finds nothing (empty, short, a shell glob)",
              all(stopped_orphans(bad) == [] for bad in ("", "1", "*", "11111111;")), "a malformed id matched")
        check("an empty id reaps nothing, even beside a process holding an empty id", reap("") == [] and alive(blank), "")
        reaped = reap(mine)
        time.sleep(0.2)
        check("the reaper returns the pids it signalled", sorted(reaped) == sorted([target, stubborn]), f"{reaped}")
        check("the session's stopped orphan is gone", not alive(target), f"{state(target)}")
        check("an orphan that IGNORES SIGTERM is killed too", not alive(stubborn), f"{state(stubborn)}")
        for label, pid in (("a command line that only MENTIONS the id (not its environment)", decoy),
                           ("another session's stopped orphan", foreign),
                           ("this session's RUNNING orphan", running),
                           ("a process whose id is the EMPTY string, reaped with an empty id", blank),
                           ("this session's stopped process that still has a parent", child)):
            check(f"survives: {label}", pid > 0 and alive(pid), f"pid {pid} was killed: {state(pid)}")
        check("a second reap finds nothing left to reap", reap(mine) == [], "reaped again")
    finally:
        for pid in started:                     # the safety net, by the pids the fixtures recorded
            for sig in (signal.SIGCONT, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass
    if failures:
        print("session_reaper selftest FAILED:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    print("session_reaper selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
