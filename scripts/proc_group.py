"""Run a subprocess in its own session, and on a timeout or an interrupt kill EVERYTHING it started (#1459).

`subprocess.run(timeout=...)` kills only the direct child. A gate or a mutant's selftest that started
children of its own -- a thread pool of selftests, a hook's stubs, git -- leaves them running, orphaned,
and a child still holding the output pipe can keep the caller blocked long after the "timeout"
(check_hook_gates measured 43 orphans before it moved to this pattern, #1469).

Here the child starts a new session, so its pid is its group id. A group kill alone is not enough,
though, because the runners NEST: the doctor runs `mutation_check` through `run`, `mutation_check`
runs every baseline and mutant through `run`, and `check_hook_gates` (under a mutant) starts each hook
in a session of its own. Every one of those inner sessions is a group the outer `killpg` cannot reach
(review of #1525: both mutants alive after the gate's timeout). So `kill_tree` walks the DESCENDANTS by
parent pid, stops each one before looking further (so nothing forks or is reparented mid-walk), then
SIGKILLs every process found and every group one of them leads.

A child in a new session never sees the terminal's Ctrl-C either, so `run` kills the tree on ANY
exception out of the wait (KeyboardInterrupt, SystemExit), and `pool` -- the thread pool
`mutation_check` runs its baselines and mutants in -- kills every live child from the main thread on
an interrupt, cancels what has not started, and refuses to start anything new.

What escapes: a process whose parent has already exited (a double fork) is no longer anyone's
descendant and leads a group of its own. Such an escapee holding the pipe is waited for at most
ESCAPEE_WAIT seconds, so a miss is a survivor, never a hang, and what the child printed still rides
on the TimeoutExpired.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading

ESCAPEE_WAIT = 5        # seconds to keep reading after the kill, for a pipe an escapee still holds

_lock = threading.Lock()
_live: set[subprocess.Popen] = set()
_closing = threading.Event()   # set by kill_all: an interrupted run starts nothing new


def _ps_rows() -> list[tuple[int, int, int]] | None:
    """(pid, ppid, pgid) for every process, or None when `ps` cannot be run (the group kill remains)."""
    ps = shutil.which("ps") or next((p for p in ("/bin/ps", "/usr/bin/ps") if os.path.exists(p)), None)
    if ps is None:
        return None
    try:
        out = subprocess.run([ps, "-A", "-o", "pid=,ppid=,pgid="], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows


def _signal(pid: int, sig: int, group: bool = False) -> None:
    try:
        (os.killpg if group else os.kill)(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def kill_tree(root: int) -> None:
    """SIGKILL `root`, every process descending from it, and every process group one of them leads.

    Each process found is SIGSTOPped before the next look, so a parent cannot fork past the walk or
    die and hand its children to init; the walk repeats until it finds nothing new.
    """
    own = os.getpgrp()
    frozen, groups = {root}, {root}
    # THE KILL IS IN `finally` (#1548). Every process the walk finds is SIGSTOPped, so an exception
    # between the freeze and the kill -- Ctrl-C, a `ps` that fails -- used to leave the whole tree
    # stopped for good, still holding the caller's pipe. Freezing is only safe if killing is certain.
    try:
        _signal(root, signal.SIGSTOP)
        for _ in range(20):
            rows = _ps_rows()
            if rows is None:
                break
            children: dict[int, list[tuple[int, int]]] = {}
            for pid, ppid, pgid in rows:
                children.setdefault(ppid, []).append((pid, pgid))
            found, stack = set(), list(frozen)
            while stack:
                for pid, pgid in children.get(stack.pop(), ()):
                    if pid not in found:
                        found.add(pid)
                        groups.add(pgid)
                        stack.append(pid)
            new = found - frozen
            if not new:
                break
            for pid in new:
                _signal(pid, signal.SIGSTOP)
            frozen |= new
    finally:
        _kill_frozen(groups, frozen, own)


def _kill_frozen(groups: set[int], frozen: set[int], own: int) -> None:
    """SIGKILL every group a frozen process leads (never our own) and every frozen process.

    PID REUSE IS NOT GUARDED, deliberately (#1548 item 2). A pid in `frozen` was SIGSTOPped by us a
    moment ago, so it cannot exit and be reaped before this SIGKILL unless something else SIGCONTs it
    first, and its parent is in the same tree, frozen too. Re-checking parentage here would add a
    second `ps` and a second race for a window that, in practice, does not open.
    """
    for pgid in groups - {own}:
        _signal(pgid, signal.SIGKILL, group=True)
    for pid in frozen:
        _signal(pid, signal.SIGKILL)


def kill_all() -> None:
    """Kill every live child of every `run` in this process, and start no new one. For an interrupt
    in the main thread while pool workers wait on children that never saw it."""
    with _lock:
        _closing.set()
        live = list(_live)
    for proc in live:
        kill_tree(proc.pid)


@contextlib.contextmanager
def pool(max_workers: int):
    """A ThreadPoolExecutor whose workers run children through `run`. On any exception out of the
    block -- Ctrl-C in the main thread above all -- every live child is killed and every queued task
    cancelled before the pool is joined, so the join returns in seconds, not at the slowest mutant."""
    from concurrent.futures import ThreadPoolExecutor
    # A NEW pool starts open (#1548): `kill_all` sets `_closing` for the pool it interrupts, and nothing
    # cleared it, so every later pool in the same process refused all of its children. `_closing` is
    # process-wide, so this assumes pools run ONE AT A TIME (the only caller, mutation_check, does):
    # a second pool opened while another is mid-interrupt would re-open the first.
    _closing.clear()
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield executor
    except BaseException:
        kill_all()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True)


def _drain(proc: subprocess.Popen):
    """What the killed child printed. Bounded: an escapee holding the pipe would bring the hang back."""
    try:
        out, err = proc.communicate(timeout=ESCAPEE_WAIT)
    except subprocess.TimeoutExpired as again:
        # The second TimeoutExpired carries everything read so far, both calls included; dropping
        # it reported "printed nothing" for a child that had printed (review of #1525).
        out, err = again.output, again.stderr
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
    proc.wait()
    return out, err


def run(argv, *, timeout: float, input=None, **kw) -> subprocess.CompletedProcess:
    """`subprocess.run(argv, capture_output=True, timeout=timeout, **kw)`, but a timeout or an
    interrupt kills everything the child started, and a timeout's partial output rides on the
    TimeoutExpired."""
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    with _lock:
        if _closing.is_set():
            raise KeyboardInterrupt("proc_group: interrupted, so no new child is started")
        proc = subprocess.Popen(argv, start_new_session=True, **kw)
        _live.add(proc)
    try:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            out, err = _drain(proc)
            raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err) from None
        except BaseException:
            # Ctrl-C or SystemExit: the child is in a session of its own and never saw the signal.
            kill_tree(proc.pid)
            _drain(proc)
            raise
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)
    finally:
        with _lock:
            _live.discard(proc)


# THE COST OF A RUN IS ITS CPU TIME, NOT ITS WALL TIME (#1635). `mutation_check`'s cost ratchet compared wall seconds to a record, so a
# machine at load 30 to 80 read every guard 2x to 4x over its record whatever the code was (the v1.154.0 local release failed 15 of 2688
# mutations, every one the ratchet). CPU seconds do not stretch with other processes' load. A run is wrapped in a small interpreter that
# starts the real command, waits for it, and writes user + system seconds of everything it waited for to a file.
_CPU_WRAPPER = (
    "import os, resource, subprocess, sys\n"
    "rc = subprocess.call(sys.argv[2:])\n"
    "ru = resource.getrusage(resource.RUSAGE_CHILDREN)\n"
    "with open(sys.argv[1], 'w') as f:\n"
    "    f.write(repr(ru.ru_utime + ru.ru_stime))\n"
    "sys.exit(rc if rc >= 0 else 128 - rc)\n"
)


def run_cpu(argv, *, timeout: float, input=None, **kw) -> tuple[subprocess.CompletedProcess, float | None]:
    """`run(...)`, plus the CPU seconds (user + system) of the command and every descendant it waited for, or None when
    the run was killed before it could say (a timeout raises, as `run` does; the caller bills its wall time instead).
    The return code is the command's own; a signal death maps to 128 + signal, as a shell reports it."""
    import tempfile
    fd, path = tempfile.mkstemp(prefix="cpu-seconds-")
    os.close(fd)
    try:
        result = run([sys.executable, "-c", _CPU_WRAPPER, path, *map(str, argv)], timeout=timeout, input=input, **kw)
        try:
            with open(path) as f:
                cpu = float(f.read())
        except (OSError, ValueError):
            cpu = None
        return result, cpu
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
