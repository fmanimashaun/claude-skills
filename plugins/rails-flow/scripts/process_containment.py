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


def environ_of(pid: int) -> list[bytes] | None:
    """The process's environment as SEPARATE entries (`NAME=value`, bytes), or None when it cannot be read.

    Exact on both platforms, never a search over printed text: Linux reads `/proc/<pid>/environ`; macOS asks the kernel
    (`sysctl kern.procargs2`, which returns argv and environment as NUL-separated strings, argv counted off). `ps -E`
    cannot be used: it joins the command line and every variable with spaces, so a VALUE containing ` VAR=x ` is
    indistinguishable from the variable (#1646 review R1: another session's orphan was killed that way)."""
    if sys.platform.startswith("linux"):
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                return [e for e in f.read().split(b"\0") if e]
        except OSError:
            return None
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        mib = (ctypes.c_int * 3)(1, 49, pid)                  # CTL_KERN, KERN_PROCARGS2, pid
        size = ctypes.c_size_t(0)
        if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
            return None
        data = buf.raw[:size.value]
        argc, rest = int.from_bytes(data[:4], "little"), data[4:]
        i = rest.index(b"\0")                                 # the executable path, then NUL padding
        while i < len(rest) and rest[i] == 0:
            i += 1
        for _ in range(argc):
            i = rest.index(b"\0", i) + 1
        entries = []
        for e in rest[i:].split(b"\0"):
            if not e:
                break                                         # the environment ends at the first empty string
            entries.append(e)
        return entries
    except (OSError, ValueError, AttributeError):
        return None


def _all_pids() -> list[int]:
    if sys.platform.startswith("linux"):
        return [int(e) for e in os.listdir("/proc") if e.isdigit()]
    out = subprocess.run(["ps", "-A", "-o", "pid="], capture_output=True, text=True, check=False).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def value_of(pid: int, var: str) -> str | None:
    """The value of the variable named EXACTLY `var` in that process's environment, or None."""
    prefix = f"{var}=".encode()
    for entry in environ_of(pid) or []:
        if entry.startswith(prefix):
            return entry[len(prefix):].decode("utf-8", "surrogateescape")
    return None


def holding(var: str, value: str) -> list[int]:
    """Every live process whose environment has an entry that IS `var=value`, never this one. Entries are compared whole
    and separately: a command line, or another variable's value, that merely contains the text does not match, and where
    the environment cannot be read at all nothing matches (refuse, never guess)."""
    needle, me = f"{var}={value}".encode(), os.getpid()
    if environ_of(me) is None:
        return []
    return [pid for pid in _all_pids() if pid != me and needle in (environ_of(pid) or [])]


def tagged(token: str) -> list[int]:
    """Every live process started with `TOKEN_VAR=token` in its environment, never this one."""
    return holding(TOKEN_VAR, token)


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
    # REAP ONLY WHAT WE KILLED, by pid (#1589 review F2). `waitpid(-1)` reaps ANY child of this process,
    # so a caller's unrelated child that exited during the block had its status stolen: measured, an
    # exit 3 came back to the caller as 0. A pid that is not our child raises, and belongs to init.
    pending = set(frozen)
    deadline = time.monotonic() + 5
    while pending and time.monotonic() < deadline:
        for pid in list(pending):
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pending.discard(pid)        # not ours to reap
                continue
            if done:
                pending.discard(pid)
        if pending:
            time.sleep(0.05)
    return sorted(frozen)


class Box:
    def __init__(self, token: str) -> None:
        self.token = token
        self.killed: list[int] = []


@contextlib.contextmanager
def _deferred_signals():
    """HOLD SIGTERM, SIGHUP AND SIGINT UNTIL THE SWEEP HAS FINISHED (#1582 slice B, #1589 re-review S1). The CLI turns
    those signals into an exception, and a second one that landed while `contained()`'s `finally` was sweeping raised
    AGAIN inside it: the sweep stopped partway and the tree survived (measured 5 of 5, a 0.3 s gap between the two).
    Blocked, a signal waits pending (equal signals coalesce) and is delivered when the mask is restored, after the sweep,
    to whatever handler the caller installed -- so the interrupt still ends the caller, just not the cleanup."""
    held = {signal.SIGTERM, signal.SIGHUP, signal.SIGINT}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, held)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextlib.contextmanager
def contained():
    """Run the block with `TOKEN_VAR` set, so every process it starts is tagged. On any exit that
    reaches `finally` -- a return, an exception, Ctrl-C -- sweep them all. A library installs no signal
    handlers, so a SIGTERM or SIGHUP to the CALLER sweeps only if the caller turns it into an exception
    (the CLI below does). A SIGKILL can never be caught."""
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
        with _deferred_signals():
            box.killed = sweep(token)


# A BROKEN FIXTURE, the shape of the 2026-10-03 leak. The fixture starts a CHILD; the child starts a
# grandchild in a NEW session, records both pids, and SIGSTOPs itself; the fixture exits. Both are left
# orphaned (parent pid 1), one of them STOPPED. Every process opens /dev/null for stdio, so a leaked one
# never holds the selftest's or the CLI's pipe: a broken sweep must FAIL the run, not hang it.
# The PIDS GO TO A FILE THE SELFTEST OWNS (#1589 review F1). The safety net and the "nothing remains"
# checks read that file, never the token: a mutant that stops TAGGING left an untagged stopped orphan
# that a token-only net could not see -- once per guard run, the very leak this helper exists to stop.
_CHILD = ("import os, signal, subprocess, sys, time\n"
          "N = subprocess.DEVNULL\n"
          "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True,"
          " stdin=N, stdout=N, stderr=N)\n"
          "open(sys.argv[1], 'a').write(f'{os.getpid()} {g.pid}\\n')\n"
          "time.sleep(0.3)\n"
          "os.kill(os.getpid(), signal.SIGSTOP)\n"
          "time.sleep(120)\n")
_LEAKY = ("import os, subprocess, sys, time\n"
          "open(sys.argv[1] + '.root', 'w').write(str(os.getpid()))\n"   # the root records itself too
          "N = subprocess.DEVNULL\n"
          f"subprocess.Popen([sys.executable, '-c', {_CHILD!r}, sys.argv[1]], stdin=N, stdout=N, stderr=N)\n"
          "time.sleep(1.0)\n")


def _recorded(pidfile: str) -> list[int]:
    try:
        return [int(p) for p in open(pidfile).read().split()]
    except (OSError, ValueError):
        return []


def _tree(pidfile: str) -> list[int]:
    """Every pid a leaking fixture recorded: its child and grandchild, and the fixture's own root."""
    return _recorded(pidfile) + _recorded(pidfile + ".root")


def _alive(pid: int) -> bool:
    """Alive and not a zombie: a zombie is dead, only not yet reaped."""
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(out) and not out.startswith("Z")


def selftest() -> int:
    import tempfile
    failures: list[str] = []
    work = tempfile.mkdtemp(prefix="containment-selftest-")
    pidfiles: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    def pidfile(name: str) -> str:
        path = os.path.join(work, name)
        pidfiles.append(path)
        return path

    def wait_for(path: str, n: int = 2, timeout: float = 10.0) -> list[int]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(_recorded(path)) < n:
            time.sleep(0.05)
        return _recorded(path)

    try:
        # 1. UNDER the helper: the broken fixture leaves nothing behind, checked by RECORDED PID.
        f1 = pidfile("contained.pids")
        with contained() as box:
            subprocess.run([sys.executable, "-c", _LEAKY, f1], check=False)
            pids = wait_for(f1)
            inside = tagged(box.token)
        time.sleep(0.3)
        check("a leaking fixture's processes are tagged while it runs (the helper can see them)",
              len(pids) == 2 and set(pids) <= set(inside), f"recorded {pids}, tagged {inside}")
        check("under contained(), a leaking fixture leaves NOTHING behind (by recorded pid)",
              len(pids) == 2 and not any(_alive(p) for p in pids), f"alive {[p for p in pids if _alive(p)]}")
        check("the teardown reports what it killed", set(pids) <= set(box.killed), f"killed {box.killed}")

        # 2. WITHOUT the helper: the same fixture leaks -- or the test above proves nothing.
        f2 = pidfile("uncontained.pids")
        subprocess.run([sys.executable, "-c", _LEAKY, f2], check=False)
        leaked = wait_for(f2)
        check("CONTROL: without contained(), the same fixture DOES leak", len(leaked) == 2 and all(map(_alive, leaked)),
              f"recorded {leaked}")
        states = [subprocess.run(["ps", "-o", "stat=", "-p", str(p)], capture_output=True, text=True).stdout.strip()
                  for p in leaked]
        check("CONTROL: ...including a STOPPED process, the shape of the incident", any(x.startswith("T") for x in states),
              f"states {states}")

        # 3. An exception in the code under test still sweeps.
        f3 = pidfile("exception.pids")
        try:
            with contained():
                subprocess.run([sys.executable, "-c", _LEAKY, f3], check=False)
                wait_for(f3)
                raise RuntimeError("the fixture itself broke")
        except RuntimeError:
            pass
        time.sleep(0.3)
        check("an exception inside contained() still sweeps", not any(_alive(p) for p in _recorded(f3)),
              f"alive {[p for p in _recorded(f3) if _alive(p)]}")

        # 4. The environment is restored.
        check("contained() restores the environment", TOKEN_VAR not in os.environ, "token left in os.environ")

        # 5. F2: the sweep reaps only what it killed, never a caller's other child (its status is the caller's).
        other = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
        f5 = pidfile("sleeper.pids")
        with contained():
            sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            open(f5, "w").write(str(sleeper.pid))   # recorded, so the safety net reaches it under any mutant
            time.sleep(1.0)              # `other` exits while the block runs
        rc = other.wait()
        check("the sweep leaves a caller's OTHER child alone: its exit status is still 3", rc == 3, f"got {rc}")

        # 6. The CLI: returns the command's status, and kills what it left.
        f6 = pidfile("cli.pids")
        cli = subprocess.run([sys.executable, __file__, "--", sys.executable, "-c",
                              _LEAKY + "raise SystemExit(7)\n", f6], capture_output=True, text=True, check=False)
        time.sleep(0.3)
        check("the CLI returns the command's own exit status", cli.returncode == 7, f"exit {cli.returncode}")
        check("the CLI kills what the command left", len(_recorded(f6)) == 2 and not any(_alive(p) for p in _recorded(f6)),
              f"recorded {_recorded(f6)}, alive {[p for p in _recorded(f6) if _alive(p)]}")

        # 7. F3: SIGTERM and SIGHUP to the CLI still tear the tree down (SIGINT already did).
        for sig in (signal.SIGTERM, signal.SIGHUP):
            fs = pidfile(f"cli-{sig.name}.pids")
            w = subprocess.Popen([sys.executable, __file__, "--", sys.executable, "-c",
                                  _LEAKY + "time.sleep(60)\n", fs],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(fs)
            w.send_signal(sig)
            try:
                w.wait(timeout=15)
            except subprocess.TimeoutExpired:
                w.kill()
                w.wait()
            time.sleep(0.3)
            check(f"a {sig.name} to the CLI still kills the command's tree",
                  len(_recorded(fs)) == 2 and not any(_alive(p) for p in _tree(fs)),
                  f"recorded {_tree(fs)}, alive {[p for p in _tree(fs) if _alive(p)]}")

        # 8. #1582 slice B (from #1589's re-review S1): A SECOND SIGNAL DURING THE TEARDOWN MUST NOT ABORT THE SWEEP.
        # The CLI turns SIGTERM into an exception, and a second one arriving while `contained()`'s `finally` runs the
        # sweep raised again INSIDE it: the sweep stopped partway and the tree survived (5 of 5 with a 0.3 s gap).
        # Each pair below is sent to a fresh CLI whose command leaks the stopped-orphan shape.
        # The SECOND signal varies too (#1642 review): dropping SIGHUP or SIGINT from the held set must fail a fixture, not only dropping SIGTERM.
        for first, second in ((signal.SIGTERM, signal.SIGTERM), (signal.SIGHUP, signal.SIGTERM), (signal.SIGINT, signal.SIGTERM),
                              (signal.SIGTERM, signal.SIGHUP), (signal.SIGTERM, signal.SIGINT)):
            fd = pidfile(f"cli-twice-{first.name}-{second.name}.pids")
            w = subprocess.Popen([sys.executable, __file__, "--", sys.executable, "-c",
                                  _LEAKY + "time.sleep(60)\n", fd],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(fd)
            w.send_signal(first)
            time.sleep(0.3)                  # the first is in the teardown, the second lands inside the sweep
            w.send_signal(second)
            try:
                w.wait(timeout=20)
            except subprocess.TimeoutExpired:
                w.kill()
                w.wait()
            time.sleep(0.3)
            check(f"a {second.name} {0.3}s after a {first.name} does not abort the sweep: the tree is gone",
                  len(_recorded(fd)) == 2 and not any(_alive(p) for p in _tree(fd)),
                  f"recorded {_tree(fd)}, alive {[p for p in _tree(fd) if _alive(p)]}")
    finally:
        # SAFETY NET by RECORDED PID, never by token and never through `sweep()`: under a mutant either may
        # be the broken part, and running this guard must not leak what it tests.
        for path in pidfiles:
            for pid in _tree(path):
                _signal(pid, signal.SIGCONT)
                _signal(pid, signal.SIGKILL)
        time.sleep(0.3)
        remaining = [p for path in pidfiles for p in _tree(path) if _alive(p)]
        if remaining:
            failures.append(f"the selftest's own safety net left processes behind: {remaining}")
        import shutil
        shutil.rmtree(work, ignore_errors=True)

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    print(f"process_containment selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def _raise_on(signum, _frame):
    """SIGTERM and SIGHUP end the wrapper the way Ctrl-C does, so `contained()`'s teardown runs (#1589
    review F3: measured, SIGINT left 0 trees, SIGTERM 1 and SIGHUP 2). SIGKILL cannot be caught by
    anything, so a SIGKILLed wrapper leaves its tree -- the one case this cannot cover."""
    raise KeyboardInterrupt(f"signal {signum}")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] != ["--"] or len(argv) < 2:
        print("usage: process_containment.py -- <command> [args...]", file=sys.stderr)
        return 2
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_on)
    rc, box = 130, None
    try:
        with contained() as box:
            rc = subprocess.run(argv[1:], check=False).returncode
    except KeyboardInterrupt:
        pass
    if box is not None and box.killed:
        print(f"process_containment: killed {len(box.killed)} leftover process(es): {box.killed}",
              file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
