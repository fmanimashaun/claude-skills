#!/usr/bin/env python3
"""Prove `pid_record` never hands a reader a torn record, and waits -- boundedly -- for a late one (#1556).

Run:  python3 scripts/pid_record_selftest.py

Every fixture is DETERMINISTIC: the race #1556 hit once in a full CI run (a gate killed between
`open(path, 'w')` truncating the file and its pid landing, read back as `int('')`) is reproduced
here by injecting a delay between the open and the write, not by hoping a loaded runner lines it up.
Costs a few seconds: stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pid_record as pr  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0
DELAY = 1.0     # seconds between the open and the content, in every slow write below


def _tick() -> None:
    global CHECKS
    CHECKS += 1


class _SlowFile:
    """A file whose content lands DELAY seconds after it was opened -- a writer descheduled mid-write."""

    def __init__(self, f):
        self.f = f

    def write(self, text: str) -> int:
        time.sleep(DELAY)
        return self.f.write(text)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.f.close()


def _slow_open(*args, **kwargs):
    return _SlowFile(open(*args, **kwargs))


def run() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # (1) A READER DURING A SLOW WRITE gets the whole record or none of it -- never the empty
        # file `open(path, 'w')` leaves between its truncate and its content (#1556's `int('')`).
        _tick()
        record = root / "torn.pid"
        pr.open = _slow_open                     # module global: shadows the builtin inside pid_record
        try:
            writer = threading.Thread(target=pr.write, args=(record, 111, 222))
            writer.start()
            time.sleep(DELAY / 4)                # the writer has opened, and not yet written
            try:
                got = pr.wait(record, timeout=10)
            except ValueError as exc:
                got = f"raised {exc}"
            writer.join()
        finally:
            del pr.open
        if got != [111, 222]:
            FAILURES.append(f"#1556: a reader during a slow write saw a torn pid record: {got!r}")

        # (2) A WRITER KILLED MID-WRITE -- the CI shape: a gate's timeout lands between the open and
        # the content. The record must be absent (no verdict: "did not start"), not empty.
        _tick()
        record = root / "killed.pid"
        child = (pr.import_line(pr.HERE) +
                 "import time\n"
                 "real = open\n"
                 "class Slow:\n"
                 "    def __init__(self, f): self.f = f\n"
                 "    def write(self, t): time.sleep(60); return self.f.write(t)\n"
                 "    def __enter__(self): return self\n"
                 "    def __exit__(self, *a): self.f.close()\n"
                 "pid_record.open = lambda *a, **k: Slow(real(*a, **k))\n"
                 f"pid_record.write({str(record)!r}, 333)\n")
        try:
            subprocess.run([sys.executable, "-c", child], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            pass
        try:
            got = pr.wait(record, timeout=0)
        except ValueError as exc:
            got = f"raised {exc}"
        if got != []:
            FAILURES.append(f"#1556: a writer killed mid-write left a torn pid record behind: {got!r}")

        # (3) A RECORD THAT COMES LATE is waited for, not read as missing (#1556: a gate slow to start).
        _tick()
        record = root / "late.pid"
        later = threading.Timer(DELAY, pr.write, args=(record, 444))
        later.start()
        got = pr.wait(record, timeout=30)
        later.join()
        if got != [444]:
            FAILURES.append(f"#1556: a pid record written {DELAY}s late was not waited for: {got!r}")

        # (4) NO RECORD AT ALL comes back as [] within the bound -- a miss is a verdict, never a hang.
        _tick()
        started = time.monotonic()
        got = pr.wait(root / "never.pid", timeout=0.5)
        took = time.monotonic() - started
        if got != [] or took > 5:
            FAILURES.append(f"#1556: a missing pid record must return [] within its bound, got {got!r} after {took:.1f}s")

        # (5) AN EMPTY RECORD is a broken writer, and says so -- it is not waited out as "did not start".
        _tick()
        record = root / "empty.pid"
        record.write_text("", encoding="utf-8")
        try:
            got = pr.wait(record, timeout=0)
        except ValueError:
            got = "raised"
        if got != "raised":
            FAILURES.append(f"#1556: an empty pid record must raise, not pass as no record: {got!r}")

        # (6) Nothing is left behind by a write that finished (the killed one in (2) is exempt): the
        # temporary sibling is replaced into place, not abandoned.
        _tick()
        leftovers = sorted(p.name for p in root.glob("*.tmp") if not p.name.startswith("killed."))
        if leftovers:
            FAILURES.append(f"#1556: a completed write left its temporary file behind: {leftovers}")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"pid_record selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
