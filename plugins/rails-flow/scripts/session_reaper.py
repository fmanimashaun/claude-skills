#!/usr/bin/env python3
"""Reap a finished session's own STOPPED ORPHANS (#1582 slice C).

THE LEAK. A session that starts a process and then stops it (SIGSTOP, a job-control stop, a debugger) and
exits leaves it re-parented to pid 1, stopped, for good: the 2026-10-03 incident left 74 and hit
`kern.maxprocperuid`. `process_containment.py` stops a fixture leaking; this reaps what a session left anyway.

WHOSE IT IS, DECIDED BY THE ENVIRONMENT, NEVER BY NAME. Claude Code sets `CLAUDE_CODE_SESSION_ID` in Bash and
PowerShell tool subprocesses and hook command subprocesses (v2.1.132+) and stdio MCP server subprocesses (v2.1.154+); it
matches the hook payload's `session_id` and is updated on `/clear` (https://code.claude.com/docs/en/env-vars). A process
started before a `/clear` carries the old id, and one the docs do not list may carry none. A process is reaped only if
ALL of these hold:
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
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_containment import holding, value_of  # noqa: E402

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
    if not targets:
        return []             # a clean session costs one scan, not three
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
    if argv[:1] == ["--owners"]:           # `pid session-id|?` per pid, read from the exact variable (the advisory's reader)
        for arg in argv[1:]:
            owner = value_of(int(arg), SESSION_VAR) if arg.isdigit() else None
            print(f"{arg} {owner if owner and _ID.match(owner) else '?'}")
        return 0
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
    # UNIQUE PER RUN: two guards run this selftest together under --jobs, and a shared id made each reap the other's
    # fixtures, so both went inert (#1646 review R2).
    mine, other = str(uuid.uuid4()), str(uuid.uuid4())
    started: list[int] = []
    # THIS PROCESS CARRIES ANOTHER SESSION'S ID (#1729). The reaper must read the id it is GIVEN, never its own environment. On a maintainer's machine
    # the selftest runs inside a session, so its environment already held a different id; on the hosted runner it held none, the fallback equalled the
    # argument, and the mutant that reads its own environment survived. Set explicitly, the check does not depend on where it runs.
    saved_id = os.environ.get(SESSION_VAR)
    os.environ[SESSION_VAR] = other

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    def state(pid: int) -> str:
        return subprocess.run(["ps", "-o", "stat=,ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.split()

    def alive(pid: int) -> bool:
        s = state(pid)
        return bool(s) and not s[0].startswith("Z")

    def spawn(name: str, env_id: str | None, mode: str, extra: tuple = (), orphan: bool = True, env_more: dict | None = None) -> int:
        """Start one leaf and return its pid. `env_id` None: no id in the environment at all."""
        path = os.path.join(work, name)
        env = {k: v for k, v in os.environ.items() if k != SESSION_VAR}
        if env_id is not None:
            env[SESSION_VAR] = env_id
        env = {**(env_more or {}), **env}       # the spoofing variables come FIRST: a reader that stops at a substring hit takes them
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
        # #1646 review R1: ANOTHER session's orphan whose environment has a different variable whose VALUE contains
        # " CLAUDE_CODE_SESSION_ID=<mine> ". Text-matching over `ps -E` killed it; an exact entry comparison cannot.
        spoof = spawn("other-session-spoof", other, "stop", env_more={"NOTE": f"x {SESSION_VAR}={mine} y", "TAIL": f"{SESSION_VAR}={mine}"})
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
                           ("another session's orphan with a variable whose VALUE contains this session's entry", spoof),
                           ("this session's RUNNING orphan", running),
                           ("a process whose id is the EMPTY string, reaped with an empty id", blank),
                           ("this session's stopped process that still has a parent", child)):
            check(f"survives: {label}", pid > 0 and alive(pid), f"pid {pid} was killed: {state(pid)}")
        check("value_of reads the exact variable: this session's id for its own, None for a spoofed one",
              value_of(running, SESSION_VAR) == mine and value_of(spoof, SESSION_VAR) == other and value_of(decoy, SESSION_VAR) is None,
              f"{value_of(running, SESSION_VAR)!r} {value_of(spoof, SESSION_VAR)!r} {value_of(decoy, SESSION_VAR)!r}")
        check("a second reap finds nothing left to reap", reap(mine) == [], "reaped again")
    finally:
        if saved_id is None:
            os.environ.pop(SESSION_VAR, None)
        else:
            os.environ[SESSION_VAR] = saved_id
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
