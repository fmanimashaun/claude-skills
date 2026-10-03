"""A child records the pids it started in a file; a fixture waits for that record, complete (#1556).

The process-group fixtures (#1459) start a gate that starts a grandchild, then ask whether the
grandchild survived a kill. They learn its pid from a file the gate writes. Two races sat in that
hand-off, and one turned a full `mutation coverage` run red for no reason (#1556):

- A TORN RECORD. `open(path, 'w').write(pid)` truncates the file first and fills it later, so a reader
  in between -- or a kill in between -- finds an EMPTY file, and `int('')` raises. The reader saw a
  file that existed and was not yet written. `write` therefore writes a temporary sibling and
  `os.replace`s it in: the path names either nothing or the whole record, never part of one.
- A RECORD READ BEFORE IT EXISTS. A gate killed by a one-second timeout on a loaded runner may not
  have got as far as writing at all. `wait` polls for the record up to a deadline and returns `[]`
  when it never came, so the caller reports "did not start" instead of a traceback.

The child scripts are `python -c` strings, so they reach `write` by putting this directory on
`sys.path` -- `import_line(directory)` builds that line.
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def write(path: str | os.PathLike, *pids: int) -> None:
    """Record `pids` at `path` atomically: a reader sees no file, or every pid -- never a part."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(" ".join(str(p) for p in pids))
    os.replace(tmp, path)


def wait(path: str | os.PathLike, timeout: float = 30.0) -> list[int]:
    """The pids recorded at `path`, waiting up to `timeout` seconds for the record to appear.

    `[]` means no record came in time. An existing record that does not parse is a defect in the
    writer, not a race, so it raises rather than being waited out.
    """
    path = Path(path)
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    if not text.strip():
        raise ValueError(f"{path}: the pid record exists but is empty -- a torn write (#1556)")
    return [int(p) for p in text.split()]


def import_line(directory: str | os.PathLike) -> str:
    """The `python -c` prelude that makes `pid_record` importable from a child script."""
    return f"import sys; sys.path.insert(0, {str(directory)!r}); import pid_record\n"


HERE = str(Path(__file__).resolve().parent)
