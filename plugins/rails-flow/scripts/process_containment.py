#!/usr/bin/env python3
"""Contain a process fixture: nothing it starts outlives it (#1582).

THE INCIDENT. A red-first reproduction of a process bug leaks by design -- leaking IS the bug. On
2026-10-03 one ran 74 times with no containment, left 74 STOPPED, orphaned trees, and the user hit
`kern.maxprocperuid`: every `fork()` on the machine failed with EAGAIN, and every session's gates read
`BlockingIOError` as a code failure.

OWNERSHIP IS THE ENVIRONMENT. A process group or session cannot hold the tree, because fixtures start
children with `start_new_session=True` on purpose. The parent-pid tree cannot either, because a child
whose parent dies is re-parented to pid 1 (exactly the 74). macOS has no subreaper. What survives a new
session AND re-parenting is the environment a process was started with, so every process started
inside `contained()` inherits `CLAUDE_CONTAIN_TOKEN=<uuid>`, and the teardown kills every process
carrying that token. (Read with `ps -E` on macOS, `/proc/<pid>/environ` on Linux. A process that
clears its own environment, `env -i`, escapes; that is the documented limit.)

NO PER-RUN PROCESS CAP. `RLIMIT_NPROC` counts EVERY process the user owns, not one tree. Measured
2026-10-03: with 500 already running, a cap of 64 made the next `fork()` fail with EAGAIN at once. So
there is no per-tree limit to set on macOS. Instead the teardown reports how many processes it had
to kill, and a fixture can assert that number.

    with contained() as box:
        ...                       # start processes; they inherit the token
    assert box.killed == []       # or: the expected leak, now cleaned up

    python3 process_containment.py -- <command> [args...]
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import uuid

TOKEN_VAR = "CLAUDE_CONTAIN_TOKEN"


def tagged(token: str) -> list[int]:
    """Every live process started with `TOKEN_VAR=token` in its environment, never this one."""
    needle, me = f"{TOKEN_VAR}={token}", os.getpid()
    found: list[int] = []
    if sys.platform.startswith("linux"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit() or int(entry) == me:
                continue
            try:
                with open(f"/proc/{entry}/environ", "rb") as f:
                    if needle.encode() in f.read().split(b"\0"):
                        found.append(int(entry))
            except OSError:
                pass
        return found
    out = subprocess.run(["ps", "-E", "-ww", "-A", "-o", "pid=,command="],
                         capture_output=True, text=True, check=False).stdout
    for line in out.splitlines():
        # A whole environment entry: the token is unique per run, and is followed by a space or the end.
        if f" {needle} " in f" {line} ":
            pid = int(line.split(None, 1)[0])
            if pid != me:
                found.append(pid)
    return found


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def sweep(token: str) -> list[int]:
    """Kill every process carrying `token`. Freeze first so none can fork past the sweep, then
    CONT and KILL each one (a stopped process is killed too, but CONT lets it see the signal at once),
    and reap our own children so they do not linger as zombies. Returns the pids it killed."""
    frozen: set[int] = set()
    for _ in range(20):                 # until a scan finds nothing new
        new = set(tagged(token)) - frozen
        if not new:
            break
        for pid in new:
            _signal(pid, signal.SIGSTOP)
        frozen |= new
    for pid in frozen:
        _signal(pid, signal.SIGCONT)
        _signal(pid, signal.SIGKILL)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:  # reap what is ours; the rest belongs to init now
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            if not set(tagged(token)) & frozen:
                break
            time.sleep(0.05)
    return sorted(frozen)


class Box:
    def __init__(self, token: str) -> None:
        self.token = token
        self.killed: list[int] = []


@contextlib.contextmanager
def contained():
    """Run the block with `TOKEN_VAR` set, so every process it starts is tagged. On ANY exit, a
    failure in the code under test included, sweep them all."""
    token = uuid.uuid4().hex
    box, saved = Box(token), os.environ.get(TOKEN_VAR)
    os.environ[TOKEN_VAR] = token
    try:
        yield box
    finally:
        if saved is None:
            os.environ.pop(TOKEN_VAR, None)
        else:
            os.environ[TOKEN_VAR] = saved
        box.killed = sweep(token)


# A BROKEN FIXTURE, the shape of the 2026-10-03 leak: it starts a child, that child starts a grandchild
# in a NEW session, the child SIGSTOPs itself, and the fixture's root exits -- so the stopped child and
# the grandchild are orphaned (parent pid 1) and nothing waits for them.
_LEAKY = ("import os, signal, subprocess, sys, time\n"
          "c = subprocess.Popen([sys.executable, '-c', "
          "'import os, signal, subprocess, sys, time; "
          "subprocess.Popen([sys.executable, \"-c\", \"import time; time.sleep(120)\"], start_new_session=True); "
          "time.sleep(0.3); os.kill(os.getpid(), signal.SIGSTOP); time.sleep(120)'])\n"
          "time.sleep(1.0)\n")


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    # 1. UNDER the helper: the broken fixture leaves nothing behind.
    with contained() as box:
        subprocess.run([sys.executable, "-c", _LEAKY], check=False)
        time.sleep(0.5)
        inside = tagged(box.token)
    left = tagged(box.token)
    check("a leaking fixture's processes are tagged while it runs (the helper can see them)", len(inside) >= 2,
          f"saw {inside}")
    check("under contained(), a leaking fixture leaves NOTHING behind", left == [], f"left {left}")
    check("the teardown reports what it killed", len(box.killed) >= 2, f"killed {box.killed}")

    # 2. WITHOUT the helper: the same fixture leaks. Tagged by hand so this test can clean up after itself.
    token = uuid.uuid4().hex
    subprocess.run([sys.executable, "-c", _LEAKY], env={**os.environ, TOKEN_VAR: token}, check=False)
    time.sleep(0.5)
    leaked = tagged(token)
    check("CONTROL: without contained(), the same fixture DOES leak (or the test above proves nothing)",
          len(leaked) >= 2, f"leaked {leaked}")
    states = subprocess.run(["ps", "-o", "stat=", "-p", ",".join(map(str, leaked))],
                            capture_output=True, text=True).stdout.split() if leaked else []
    check("CONTROL: ...including a STOPPED process, the shape of the incident", any(s.startswith("T") for s in states),
          f"states {states}")
    sweep(token)
    check("sweep() cleans up a hand-tagged leak", tagged(token) == [], f"left {tagged(token)}")

    # 3. An exception in the code under test still sweeps.
    try:
        with contained() as box2:
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            raise RuntimeError("the fixture itself broke")
    except RuntimeError:
        pass
    check("an exception inside contained() still sweeps", tagged(box2.token) == [] and len(box2.killed) == 1,
          f"left {tagged(box2.token)}, killed {box2.killed}")

    # 4. The environment is restored, and this process is never tagged or killed.
    check("contained() restores the environment", TOKEN_VAR not in os.environ, "token left in os.environ")

    # 5. The CLI: returns the command's status and kills its leftovers.
    cli = subprocess.run([sys.executable, __file__, "--", sys.executable, "-c", _LEAKY + "raise SystemExit(7)\n"],
                         capture_output=True, text=True, check=False)
    check("the CLI returns the command's own exit status", cli.returncode == 7, f"exit {cli.returncode}")
    check("the CLI reports the leftovers it killed", "killed" in cli.stderr, cli.stderr.strip()[:200])

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    print(f"process_containment selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] != ["--"] or len(argv) < 2:
        print("usage: process_containment.py -- <command> [args...]", file=sys.stderr)
        return 2
    with contained() as box:
        rc = subprocess.run(argv[1:], check=False).returncode
    if box.killed:
        print(f"process_containment: killed {len(box.killed)} leftover process(es): {box.killed}",
              file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
