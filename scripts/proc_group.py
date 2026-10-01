"""Run a subprocess in its own process group, and kill the WHOLE group when it times out (#1459).

`subprocess.run(timeout=...)` kills only the direct child. A gate or a mutant's selftest that started
children of its own -- a thread pool of selftests, a hook's stubs, git -- leaves them running, orphaned,
and a child still holding the output pipe can keep the caller blocked long after the "timeout"
(check_hook_gates measured 43 orphans before it moved to this pattern, #1469). Here the child starts a
new session, so its pid is its group id, and a timeout `killpg`s everything it started.

On a timeout this raises `subprocess.TimeoutExpired` carrying whatever output was written before the
kill, so a caller can print what it knows instead of nothing.
"""
from __future__ import annotations

import os
import signal
import subprocess


def run(argv, *, timeout: float, input=None, **kw) -> subprocess.CompletedProcess:
    """`subprocess.run(argv, capture_output=True, timeout=timeout, **kw)`, but a timeout kills the
    child's whole process group and the partial output rides on the TimeoutExpired."""
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    with subprocess.Popen(argv, start_new_session=True, **kw) as proc:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # The direct child too, whatever happened to the group: the caller must come back
            # promptly even if the group kill missed, so a miss shows up as a survivor, not a hang.
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            # Bounded: a process that LEFT the group (its own setsid) would hold the pipe open and
            # bring the hang back, so after a short wait stop reading.
            try:
                out, err = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                out, err = None, None
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if pipe:
                        pipe.close()
            proc.wait()
            raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err) from None
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)
