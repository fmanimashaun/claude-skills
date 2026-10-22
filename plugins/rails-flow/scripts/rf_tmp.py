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

PREFIX = "rf-"
_DIRS: list[str] = []
_INSTALLED = False


def _clean() -> None:
    while _DIRS:
        shutil.rmtree(_DIRS.pop(), ignore_errors=True)


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


def mkdtemp(tag: str = "tmp", dir: str | None = None) -> str:  # noqa: A002 -- the same keyword tempfile.mkdtemp takes
    """A new `rf-<tag>-XXXXXX` directory, removed when this process ends (at exit, or on SIGTERM, SIGHUP or Ctrl-C)."""
    d = tempfile.mkdtemp(prefix=f"{PREFIX}{tag.strip('-') or 'tmp'}-", dir=dir)
    _DIRS.append(d)
    _install()
    return d


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
    keep = subprocess.run([sys.executable, "-c", "import signal, sys; sys.path.insert(0, %r); import rf_tmp; h = lambda s, f: None; "
                           "signal.signal(signal.SIGTERM, h); rf_tmp.mkdtemp('x'); print(signal.getsignal(signal.SIGTERM) is h)" % here],
                          capture_output=True, text=True)
    if keep.stdout.strip() != "True":
        bad += 1
        print(f"FAIL a script's own SIGTERM handler is kept: {keep.stdout!r} {keep.stderr[-200:]!r}")
    if bad == 0:
        print("rf_tmp selftest: rf- prefix; removed at exit, on SIGTERM and on Ctrl-C; a script's own handler is kept")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
