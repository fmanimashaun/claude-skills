#!/usr/bin/env python3
"""Temp dirs that are ours by name and gone when the process ends, on a signal too (#2306, owner rule 2026-10-22: "temp folder should be
monitored and cleared out").

    import rf_tmp
    d = rf_tmp.mkdtemp("mut")          # -> <tmp>/rf-mut-XXXXXX, removed at exit, on SIGTERM and SIGHUP, and on Ctrl-C (KeyboardInterrupt)

WHY NOT tempfile.mkdtemp: nothing removes it, so every selftest, guard and hook that made one left it in the system temp dir (#2306
counted 64 such calls). WHY NOT TemporaryDirectory alone: it cleans up only when the object is dropped or at a normal exit; its
finalizer does not run on SIGTERM, which is how a guard run and a timed-out hook end. And both name their dirs freely (about 40 prefixes
in this repository), so a cleaner cannot tell ours from another program's. Everything here starts `rf-`, which is what
`maintainer_doctor.py` reports and `--fix` clears (only entries older than 24 h that no live process holds).

A signal handler is installed only where none is (the default action), so a script that handles SIGTERM itself keeps its own. On the
signal, the dirs are removed, the default action is restored and the signal is re-raised, so the exit status still says how it ended.

ONE COPY PER PLUGIN that needs it: each plugin installs alone and cannot import another's code. The copies are byte-identical to this
one; `lint_self_consistency.py` (rf-tmp-drift) refuses a copy that differs.
"""
from __future__ import annotations

import atexit
import os
import shutil
import signal
import sys
import tempfile
import time

PREFIX = "rf-"
# PROOF OF OWNERSHIP (#2316 review): every dir carries this file, `rf_tmp v1`, then the creating pid, then the creation time. A cleaner
# removes only a DIRECTORY holding a valid marker, whose pid is gone: a name starting `rf-` alone proves nothing.
MARKER = ".rf_tmp-owner"
MAGIC = "rf_tmp v1"
_DIRS: list[tuple[int, str]] = []          # (the pid that made it, the WRAPPER): a forked child never removes its parent's dirs
_INSTALLED = False


def _clean() -> None:
    me = os.getpid()
    for pid, d in [x for x in _DIRS if x[0] == me]:
        shutil.rmtree(d, ignore_errors=True)
        _DIRS.remove((pid, d))


def release(path: str) -> None:
    """Hand `path` over: this process will not remove it at exit. For a dir made here and inspected by ANOTHER process after this one
    ends (a fixture built in a subprocess); that process then owns its removal. Nothing else changes, the marker included."""
    target = os.path.realpath(path)
    for pid, d in [x for x in _DIRS if target in (os.path.realpath(x[1]), os.path.realpath(_inner(x[1])))]:
        _DIRS.remove((pid, d))


def owner_pid(path: str) -> int | None:
    """The pid in `path`'s marker, or None when `path` is not a directory carrying a valid one (then it is not ours)."""
    if os.path.islink(path) or not os.path.isdir(path):
        return None
    try:
        with open(os.path.join(path, MARKER), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    return int(lines[1]) if len(lines) >= 3 and lines[0] == MAGIC and lines[1].isdigit() else None


def _on_signal(signum, _frame) -> None:
    _clean()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    atexit.register(_clean)
    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if sig is None:
            continue
        try:
            if signal.getsignal(sig) in (signal.SIG_DFL, None):
                signal.signal(sig, _on_signal)
        except (ValueError, OSError):      # not the main thread, or a platform without it: atexit still runs at a normal exit
            pass


def _inner(wrapper: str) -> str:
    return os.path.join(wrapper, os.path.basename(wrapper))


def mkdtemp(tag: str = "tmp", dir: str | None = None) -> str:  # noqa: A002 -- the same keyword tempfile.mkdtemp takes
    """A new, EMPTY `rf-<tag>-XXXXXX` directory, removed when this process ends (at exit, or on SIGTERM, SIGHUP or Ctrl-C).

    It sits inside a wrapper of the same name that holds the owner marker (#2316 review): a caller gets an empty dir it may list,
    copy or `rmdir`, as tempfile.mkdtemp gives, and the marker never shows up in what it reads. The wrapper is what a cleaner sees."""
    wrapper = tempfile.mkdtemp(prefix=f"{PREFIX}{tag.strip('-') or 'tmp'}-", dir=dir)
    with open(os.path.join(wrapper, MARKER), "w", encoding="utf-8") as f:
        f.write(f"{MAGIC}\n{os.getpid()}\n{int(time.time())}\n")
    os.mkdir(_inner(wrapper), 0o700)
    _DIRS.append((os.getpid(), wrapper))
    _install()
    return _inner(wrapper)


def selftest() -> int:
    import subprocess
    import time

    bad = 0
    here = os.path.dirname(os.path.abspath(__file__))
    child = ("import sys, time; sys.path.insert(0, %r); import rf_tmp; d = rf_tmp.mkdtemp('selftest'); print(d, flush=True); "
             "time.sleep(%s)")
    for label, wait, how in (("removed at a normal exit", "0", None), ("removed on SIGTERM", "30", signal.SIGTERM),
                             ("removed on Ctrl-C (SIGINT)", "30", signal.SIGINT)):
        p = subprocess.Popen([sys.executable, "-c", child % (here, wait)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        path = p.stdout.readline().strip()
        if how is not None:
            time.sleep(0.2)
            p.send_signal(how)
        p.wait(timeout=20)
        ok = bool(path) and os.path.basename(path).startswith("rf-selftest-") and not os.path.exists(path)
        if not ok:
            bad += 1
            print(f"FAIL {label}: {path!r} exists={os.path.exists(path) if path else None}")
    fork = subprocess.run([sys.executable, "-c", "import os, sys; sys.path.insert(0, %r); import rf_tmp; d = rf_tmp.mkdtemp('fork'); "
                           "pid = os.fork()\n"
                           "if pid == 0: sys.exit(0)\n"
                           "os.waitpid(pid, 0); print(os.path.isdir(d), rf_tmp.owner_pid(os.path.dirname(d)) == os.getpid())" % here],
                          capture_output=True, text=True)
    if fork.stdout.strip() != "True True":
        bad += 1
        print(f"FAIL a forked child's exit leaves the parent's dir and its marker: {fork.stdout!r} {fork.stderr[-200:]!r}")
    handed = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import rf_tmp; d = rf_tmp.mkdtemp('handed'); "
                             "rf_tmp.release(d); print(d)" % here], capture_output=True, text=True)
    path = handed.stdout.strip()
    if not path or not os.path.isdir(path):
        bad += 1
        print(f"FAIL a released dir outlives the process that made it: {path!r} {handed.stderr[-200:]!r}")
    else:
        shutil.rmtree(path, ignore_errors=True)
    empty = subprocess.run([sys.executable, "-c", "import os, sys; sys.path.insert(0, %r); import rf_tmp; d = rf_tmp.mkdtemp('empty'); "
                            "print(os.listdir(d) == [], os.path.basename(d).startswith('rf-empty-'), rf_tmp.owner_pid(os.path.dirname(d)) == os.getpid())"
                            % here], capture_output=True, text=True)
    if empty.stdout.strip() != "True True True":
        bad += 1
        print(f"FAIL the dir handed out is empty, rf- named, and its wrapper carries the marker: {empty.stdout!r} {empty.stderr[-200:]!r}")
    keep = subprocess.run([sys.executable, "-c", "import signal, sys; sys.path.insert(0, %r); import rf_tmp; h = lambda s, f: None; "
                           "signal.signal(signal.SIGTERM, h); rf_tmp.mkdtemp('x'); print(signal.getsignal(signal.SIGTERM) is h)" % here],
                          capture_output=True, text=True)
    if keep.stdout.strip() != "True":
        bad += 1
        print(f"FAIL a script's own SIGTERM handler is kept: {keep.stdout!r} {keep.stderr[-200:]!r}")
    if bad == 0:
        print("rf_tmp selftest: rf- prefix and owner marker; removed at exit, on SIGTERM and on Ctrl-C; a forked child leaves the parent's "
              "dirs; a script's own handler is kept")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
