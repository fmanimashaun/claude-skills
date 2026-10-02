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
