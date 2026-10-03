#!/usr/bin/env python3
"""The status board reads the coordination record's field names. Check they are the ones it is written with.

Run:  python3 scripts/check_coordination_readers.py            # exit 0 in step, 1 drift, 3 could not check
      python3 scripts/check_coordination_readers.py --selftest

THE TWO SIDES (#1585). `plugins/rails-flow/hooks/scripts/lib/coordination.py` WRITES the per-repo
record (#1581) and owns its format. `plugins/pipeline/scripts/status_board.py` READS it. `pipeline`
cannot import rails-flow's module (each plugin resolves its own `${CLAUDE_PLUGIN_ROOT}`), so the reader
repeats the field names, and a repeated name is a claim that nothing makes true. This check does:

  * every name the reader lists as WRITTEN (`RECORD_KEYS_WRITTEN`) appears as a quoted key in
    `coordination.py`, so a rename on the write side fails here, not on a user's board;
  * every name the reader lists as PLANNED (`RECORD_KEYS_PLANNED`: read before any writer exists) is
    ABSENT from `coordination.py`. The day a writer adds one, this check fails and says to move it to
    WRITTEN: the list cannot go stale in either direction;
  * every listed name is actually read by the reader as a quoted key, so the list is not a dead
    declaration.

It is a name check, not a schema check: it does not compare value shapes. The reader tolerates a
missing or wrong-typed value by showing UNKNOWN (`status_board_selftest.py` proves that).
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = "plugins/pipeline/scripts/status_board.py"
WRITER = "plugins/rails-flow/hooks/scripts/lib/coordination.py"


def quoted(text: str, key: str) -> bool:
    return re.search(r'["\']' + re.escape(key) + r'["\']', text) is not None


def keys_of(reader_path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    spec = importlib.util.spec_from_file_location("status_board_under_check", reader_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return tuple(mod.RECORD_KEYS_WRITTEN), tuple(mod.RECORD_KEYS_PLANNED)


def check(reader: Path, writer: Path) -> list[str]:
    written, planned = keys_of(reader)
    w_text, r_text = writer.read_text(encoding="utf-8"), reader.read_text(encoding="utf-8")
    out = []
    for k in written:
        if not quoted(w_text, k):
            out.append(f"`{k}` is listed as WRITTEN in {READER} but {WRITER} no longer writes it: "
                       "the writer renamed it, or the reader's list is wrong")
    for k in planned:
        if quoted(w_text, k):
            out.append(f"`{k}` is listed as PLANNED in {READER} but {WRITER} now writes it: "
                       "move it from RECORD_KEYS_PLANNED to RECORD_KEYS_WRITTEN")
    # The reader's own use: a listed name that the reader never reads is a dead declaration. The
    # declaration lines themselves are removed first, or each name would find itself.
    body = re.sub(r"RECORD_KEYS_(?:WRITTEN|PLANNED) = \([^)]*\)", "", r_text)
    for k in (*written, *planned):
        if not quoted(body, k):
            out.append(f"`{k}` is listed in {READER} but the reader never reads it as a key")
    if not written or not planned:
        out.append(f"{READER} lists no WRITTEN or no PLANNED names: the check would pass over nothing")
    return out


def _quiet_main(argv: list[str]) -> int:
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return main(argv)


def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def expect(label: str, got: list[str], want: str) -> None:
        ran[0] += 1
        ok = (not got) if want == "" else any(want in g for g in got)
        if not ok:
            failures.append(f"{label}: wanted {want!r}, got {got}")

    real = check(ROOT / READER, ROOT / WRITER)
    expect("the real reader and the real writer are in step", real, "")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        reader = ('RECORD_KEYS_WRITTEN = ("session_id", "branch")\nRECORD_KEYS_PLANNED = ("asks",)\n'
                  'def f(r):\n    return r.get("session_id"), r.get("branch"), r.get("asks")\n')
        writer = 'row = {"session_id": 1, "branch": 2}\n'
        (d / "r.py").write_text(reader)
        (d / "w.py").write_text(writer)
        expect("a reader and writer in step are silent", check(d / "r.py", d / "w.py"), "")
        (d / "w.py").write_text('row = {"session_id": 1, "branch_name": 2}\n')
        expect("a rename on the write side is drift", check(d / "r.py", d / "w.py"), "`branch` is listed as WRITTEN")
        (d / "w.py").write_text('row = {"session_id": 1, "branch": 2, "asks": []}\n')
        expect("a planned name that the writer now writes is drift", check(d / "r.py", d / "w.py"), "move it from")
        (d / "w.py").write_text(writer)
        (d / "r.py").write_text(reader.replace('r.get("asks")', "None"))
        expect("a listed name the reader never reads is a dead declaration", check(d / "r.py", d / "w.py"),
               "never reads it")
        (d / "r.py").write_text('RECORD_KEYS_WRITTEN = ()\nRECORD_KEYS_PLANNED = ()\n')
        expect("an empty list is refused, not passed over", check(d / "r.py", d / "w.py"), "would pass over nothing")
        # The exit codes, end to end through main(): a tree laid out like the repo.
        tree = d / "tree"
        for rel, text in ((READER, reader), (WRITER, writer)):
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_text(text)
        quiet = _quiet_main(["--root", str(tree)])
        expect("main exits 0 when the two sides are in step", [] if quiet == 0 else [f"exit {quiet}"], "")
        (tree / WRITER).write_text('row = {"session_id": 1}\n')
        drift = _quiet_main(["--root", str(tree)])
        expect("main exits 1 on drift", [f"exit {drift}"], "exit 1")
        (tree / WRITER).unlink()
        gone = _quiet_main(["--root", str(tree)])
        expect("a missing file exits 3, never 0", [f"exit {gone}"], "exit 3")
    for f in failures:
        print(f"SELFTEST FAILED: {f}", file=sys.stderr)
    print(f"check_coordination_readers selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    root = Path(argv[1]) if argv[:1] == ["--root"] and len(argv) > 1 else ROOT
    for rel in (READER, WRITER):
        if not (root / rel).is_file():
            print(f"could not check: {rel} is missing (exit 3, not a pass)", file=sys.stderr)
            return 3
    findings = check(root / READER, root / WRITER)
    for f in findings:
        print(f"coordination-reader-drift: {f}")
    print(f"coordination readers: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
