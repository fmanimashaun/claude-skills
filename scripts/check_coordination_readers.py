#!/usr/bin/env python3
"""The status board reads the coordination record's field names. Check they are the ones it is written with.

Run:  python3 scripts/check_coordination_readers.py            # exit 0 in step, 1 drift, 3 could not check
      python3 scripts/check_coordination_readers.py --selftest

THE TWO SIDES (#1585). `plugins/rails-flow/hooks/scripts/lib/coordination.py` WRITES the per-repo
record (#1581) and owns its format. `plugins/pipeline/scripts/status_board.py` READS it. `pipeline`
cannot import rails-flow's module (each plugin resolves its own `${CLAUDE_PLUGIN_ROOT}`), so the reader
repeats the field names, and a repeated name is a claim that nothing makes true. This check does:

  * every name the reader lists as WRITTEN (`RECORD_KEYS_WRITTEN`) is a key `coordination.py` ASSIGNS
    (a dict-literal key, an `x["k"] = ...` store, or a `setdefault`), found with `ast`, so a rename on
    the write side fails here even when a `.get("k")` read elsewhere kept the old spelling;
  * every name the reader lists as PLANNED (`RECORD_KEYS_PLANNED`: read before any writer exists) is
    NOT assigned by `coordination.py`. The day a writer adds one, this check fails and says to move it to
    WRITTEN: the list cannot go stale in either direction;
  * every listed name is actually read by the reader as a quoted key, so the list is not a dead
    declaration.

It is a name check, not a schema check: it does not compare value shapes. The reader tolerates a
missing or wrong-typed value by showing UNKNOWN (`status_board_selftest.py` proves that).
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = "plugins/pipeline/scripts/status_board.py"
WRITER = "plugins/rails-flow/hooks/scripts/lib/coordination.py"


def quoted(text: str, key: str) -> bool:
    """The key appears as a quoted string anywhere. Right for the READER (any read of it counts)."""
    return re.search(r'["\']' + re.escape(key) + r'["\']', text) is not None


def _const(node: "ast.AST | None") -> "str | None":
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def write_keys(source: str) -> set:
    """The record keys the WRITER assigns: dict-literal keys (which cover `row.update({...})` and
    `{"version": ...}`), `x["k"] = ...` stores, and `.setdefault("k", ...)`. A `.get("k")` read does not
    count, so renaming the write site alone cannot hide behind a read that kept the old spelling."""
    found: set = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            found |= {k for k in map(_const, node.keys) if k}
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            idx = node.slice.value if isinstance(node.slice, ast.Index) else node.slice      # 3.8 wraps the index
            if _const(idx):
                found.add(_const(idx))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault" and node.args:
            if _const(node.args[0]):
                found.add(_const(node.args[0]))
    return found


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
    written_by_writer = write_keys(w_text)
    for k in written:
        if k not in written_by_writer:
            out.append(f"`{k}` is listed as WRITTEN in {READER} but {WRITER} no longer assigns it as a key: "
                       "the writer renamed it, or the reader's list is wrong")
    for k in planned:
        if k in written_by_writer:
            out.append(f"`{k}` is listed as PLANNED in {READER} but {WRITER} now writes it: "
                       "move it from RECORD_KEYS_PLANNED to RECORD_KEYS_WRITTEN")
    # The reader's own use: a listed name that the reader never reads is a dead declaration. The
    # declaration lines themselves are removed first, or each name would find itself.
    body = re.sub(r"RECORD_KEYS_(?:WRITTEN|PLANNED) = \([^)]*\)", "", r_text)
    for k in (*written, *planned):
        if not quoted(body, k):
            out.append(f"`{k}` is listed in {READER} but the reader never reads it as a key")
    if not written:
        out.append(f"{READER} lists no WRITTEN names: the check would pass over nothing")
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
        writer = 'row = {"session_id": 1, "branch": 2}\nprint(row.get("branch"))\n'
        (d / "r.py").write_text(reader)
        (d / "w.py").write_text(writer)
        expect("a reader and writer in step are silent", check(d / "r.py", d / "w.py"), "")
        (d / "w.py").write_text('row = {"session_id": 1, "branch_name": 2}\n')
        expect("a rename on the write side is drift", check(d / "r.py", d / "w.py"), "`branch` is listed as WRITTEN")
        # the case a quoted-anywhere check passes: the write site renamed, a READ kept the old spelling
        (d / "w.py").write_text('row = {"session_id": 1, "branch_name": 2}\nprint(row.get("branch"))\n')
        expect("a write-site-only rename passes a stale read: still drift", check(d / "r.py", d / "w.py"), "`branch` is listed as WRITTEN")
        (d / "w.py").write_text('row = {}\nrow["session_id"] = 1\nrow["branch"] = 2\n')
        expect("a key assigned with a subscript store counts as written", check(d / "r.py", d / "w.py"), "")
        (d / "w.py").write_text('row = {"session_id": 1}\nrow.setdefault("branch", 2)\n')
        expect("a key written with setdefault counts as written", check(d / "r.py", d / "w.py"), "")
        (d / "w.py").write_text('row = {"session_id": 1, "branch": 2}\nprint(row.get("asks"))\n')
        expect("near miss: a planned name that is only READ by the writer is not drift", check(d / "r.py", d / "w.py"), "")
        (d / "w.py").write_text('row = {"session_id": 1, "branch": 2, "asks": []}\n')
        expect("a planned name that the writer now writes is drift", check(d / "r.py", d / "w.py"), "move it from")
        (d / "w.py").write_text(writer)
        (d / "r.py").write_text(reader.replace('r.get("asks")', "None"))
        expect("a listed name the reader never reads is a dead declaration", check(d / "r.py", d / "w.py"),
               "never reads it")
        (d / "r.py").write_text('RECORD_KEYS_WRITTEN = ()\nRECORD_KEYS_PLANNED = ()\n')
        expect("an empty WRITTEN list is refused, not passed over", check(d / "r.py", d / "w.py"), "would pass over nothing")
        (d / "r.py").write_text('RECORD_KEYS_WRITTEN = ("session_id", "branch")\nRECORD_KEYS_PLANNED = ()\n'
                                'def f(r):\n    return r.get("session_id"), r.get("branch")\n')
        expect("an EMPTY planned list is fine: every key has a writer", check(d / "r.py", d / "w.py"), "")
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
