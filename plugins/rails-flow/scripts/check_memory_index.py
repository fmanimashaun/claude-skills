#!/usr/bin/env python3
"""Measure the auto-memory index against what Claude Code loads of it (#1828, slice 2 of #1685).

    python3 check_memory_index.py                        # the index of the project at the current directory
    python3 check_memory_index.py --index FILE           # a MEMORY.md anywhere
    python3 check_memory_index.py --project DIR          # the project at DIR
    python3 check_memory_index.py --baseline FILE        # fail only on GROWTH past the limit, against a recorded size
    python3 check_memory_index.py --index FILE --baseline FILE --record   # write the measured size as the baseline
    python3 check_memory_index.py --hook-line            # SessionStart: print ONE line when near or past the limit, nothing otherwise
    python3 check_memory_index.py --selftest

Exit codes: 0 ok, warning, or over-but-not-growing . 1 over the limit (or grown past its baseline) . 2 unusable (an index that cannot be read).
`--hook-line` always exits 0: an advisory never blocks a session start.

THE LIMIT, from the official page (read live by `doctrine-verifier` on 2026-10-10, verdict CONFIRMED; registry row `auto-memory-index-load-limit`
in `docs/evidence/upstream/claude-code.json` re-reads it weekly). https://code.claude.com/docs/en/memory: "The first 200 lines of `MEMORY.md`, or
the first 25KB, whichever comes first, are loaded at the start of every conversation. Content beyond that threshold is not loaded at session
start." And: "If the file is over a limit, the write still succeeds, but Claude Code returns an error telling Claude to rewrite the index, because
everything past the limit is dropped on the next load."

THE UNIT IS INFERRED. The page says "25KB" and does not say whether that is 25,000 or 25,600 bytes. Measured on one index (157 lines, 25,248 bytes):
its last entry was loaded in full, which a 25,000-byte cut would have dropped. One data point, so this is an inference, and it is why the limit
here is 25,600 and why a file between the two readings is reported with both.

A RATCHET, NOT A FIXED RED. An index that is already over the limit would fail on day one, so `--baseline FILE` records the size and the check fails
only when the index GROWS past it. It never writes a file unless `--record` is given.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_LINES = 200
MAX_BYTES = 25 * 1024          # "25KB", read as KiB (see THE UNIT IS INFERRED)
STRICT_BYTES = 25_000          # the other reading of "25KB"
WARN_LINES = 160               # 80% of each limit
WARN_BYTES = 20_480


class Unusable(Exception):
    pass


def slug(path: Path) -> str:
    """Claude Code's per-project directory name: the absolute path with every non-alphanumeric character as `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _setting(file: Path, key: str):
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get(key) if isinstance(data, dict) else None


def main_checkout(project: Path) -> Path:
    """Auto memory is per repository, shared across worktrees: the main checkout, not a linked worktree."""
    try:
        done = subprocess.run(["git", "-C", str(project), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return project
    common = done.stdout.strip()
    if done.returncode != 0 or not common:
        return project
    return Path(common).parent if Path(common).name == ".git" else project


def default_index(project: Path, home: Path) -> Path:
    """Where the project's auto-memory index lives: `autoMemoryDirectory` from project then user settings, else the default under ~/.claude."""
    for f in (project / ".claude" / "settings.local.json", project / ".claude" / "settings.json", home / ".claude" / "settings.json"):
        d = _setting(f, "autoMemoryDirectory")
        if isinstance(d, str) and d:
            p = Path(os.path.expanduser(d))
            return (p if p.is_absolute() else project / p) / "MEMORY.md"
    return home / ".claude" / "projects" / slug(main_checkout(project).resolve()) / "memory" / "MEMORY.md"


def measure(index: Path) -> dict:
    try:
        raw = index.read_bytes()
    except OSError as exc:
        raise Unusable(f"{index}: cannot be read: {exc}")
    lines = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    kept, used = 0, 0
    for line in raw.splitlines(keepends=True):
        if kept >= MAX_LINES or used + len(line) > MAX_BYTES:
            break
        kept += 1
        used += len(line)
    return {"lines": lines, "bytes": len(raw), "kept": kept, "past_cut": lines - kept}


def verdict(m: dict) -> str:
    if m["lines"] > MAX_LINES or m["bytes"] > MAX_BYTES:
        return "over"
    if m["lines"] >= WARN_LINES or m["bytes"] >= WARN_BYTES:
        return "warn"
    return "ok"


def describe(m: dict, index: Path) -> str:
    pct = max(m["lines"] / MAX_LINES, m["bytes"] / MAX_BYTES) * 100
    base = f"{m['lines']} lines of {MAX_LINES}, {m['bytes']:,} bytes of {MAX_BYTES:,} ({pct:.0f}% of the nearer limit)"
    extra = ""
    if m["past_cut"]:
        extra = f"; {m['past_cut']} line(s) past the cut are NOT loaded at session start"
    if STRICT_BYTES < m["bytes"] <= MAX_BYTES:
        extra += f"; if 25KB means {STRICT_BYTES:,} bytes it is already over"
    return f"{index}: {base}{extra}"


def run(index: Path, baseline: Path | None, record: bool) -> tuple[int, str, str]:
    """(exit code, status, message). status is one of ok, warn, over, none."""
    if not index.exists():
        return 0, "none", f"no index at {index} (nothing to measure)"
    m = measure(index)
    status = verdict(m)
    msg = describe(m, index)
    if record:
        if baseline is None:
            raise Unusable("--record needs --baseline FILE")
        baseline.write_text(json.dumps({"lines": m["lines"], "bytes": m["bytes"]}) + "\n", encoding="utf-8")
        return 0, status, f"{msg}; recorded as the baseline in {baseline}"
    if status != "over":
        return 0, status, msg
    if baseline is None:
        return 1, status, f"over the limit: {msg}"
    try:
        base = json.loads(baseline.read_text(encoding="utf-8"))
        bl, bb = int(base["lines"]), int(base["bytes"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Unusable(f"{baseline}: not a usable baseline ({exc})")
    if m["lines"] > bl or m["bytes"] > bb:
        return 1, status, f"over the limit AND grown past its baseline ({bl} lines, {bb:,} bytes): {msg}"
    return 0, status, f"over the limit, not growing past its baseline ({bl} lines, {bb:,} bytes): {msg}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_memory_index.py", description=__doc__.splitlines()[0])
    ap.add_argument("--index", type=Path)
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--hook-line", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    index = args.index or default_index(args.project, Path.home())
    try:
        code, status, msg = run(index, args.baseline, args.record)
    except Unusable as exc:
        if args.hook_line:
            return 0
        print(f"unusable: {exc}", file=sys.stderr)
        return 2
    if args.hook_line:
        if status in ("warn", "over"):
            m = measure(index)
            past = f"; {m['past_cut']} line(s) past the cut are not loaded" if m["past_cut"] else ""
            print(f"- memory index: {m['lines']}/{MAX_LINES} lines, {m['bytes']:,}/{MAX_BYTES:,} bytes{past}. Only the first {MAX_LINES} lines or 25KB load: trim it.")
        return 0
    print(f"{status}: {msg}")
    return code


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    with tempfile.TemporaryDirectory() as t:
        base = Path(t)

        def index(name: str, lines: int = 0, width: int = 10, exact_bytes: int | None = None) -> Path:
            p = base / name
            if exact_bytes is not None:
                k = 150 if exact_bytes <= 25_000 else 200          # a fixed line count under the line limit, so only the BYTE boundary varies
                sizes = [exact_bytes // k] * k
                sizes[-1] += exact_bytes - sum(sizes)
                body = "".join("x" * (n - 1) + "\n" for n in sizes)
            else:
                body = "".join(f"{'a' * (width - 1)}\n" for _ in range(lines))
            p.write_text(body, encoding="utf-8")
            return p

        def go(p: Path, baseline: Path | None = None, record: bool = False):
            return run(p, baseline, record)

        check("a short index is ok", go(index("s", 10))[:2] == (0, "ok"))
        check("159 lines is ok", go(index("l159", 159))[1] == "ok")
        check("160 lines is a warning, exit 0", go(index("l160", 160))[:2] == (0, "warn"))
        check("200 lines is still loaded whole: a warning, not over", go(index("l200", 200))[:2] == (0, "warn"))
        code, status, msg = go(index("l201", 201))
        check("201 lines is over, exit 1, and says how many lines are not loaded", (code, status) == (1, "over") and "1 line(s) past the cut" in msg, msg)
        check("20,479 bytes is ok", go(index("b1", exact_bytes=20_479))[1] == "ok")
        check("20,480 bytes is a warning", go(index("b2", exact_bytes=20_480))[1] == "warn")
        check("25,600 bytes is still loaded whole: a warning", go(index("b3", exact_bytes=25_600))[1] == "warn")
        check("25,601 bytes is over", go(index("b4", exact_bytes=25_601))[:2] == (1, "over"))
        code, status, msg = go(index("b5", exact_bytes=25_248))
        check("a file between the two readings of 25KB says it may already be over", status == "warn" and "25,000 bytes" in msg, msg)
        check("a file under 25,000 bytes does not carry that note", "25,000 bytes" not in go(index("b6", exact_bytes=24_000))[2])
        wide = base / "wide"
        wide.write_text(("w" * 199 + "\n") * 150, encoding="utf-8")     # 150 lines of 200 bytes: the BYTE limit binds first, at 128 lines
        code, status, msg = go(wide)
        check("a byte-bound index counts the lines past the byte cut", (code, status) == (1, "over") and "22 line(s) past the cut" in msg, msg)
        check("no index is not an error", go(base / "absent")[:2] == (0, "none"))
        try:
            go(base)
            check("an index that cannot be read is unusable", False, "no Unusable raised")
        except Unusable:
            check("an index that cannot be read is unusable", True)
        # the ratchet
        over = index("over", 250)
        bl = base / "baseline.json"
        code, status, msg = go(over, bl, record=True)
        check("--record writes the measured size and exits 0", code == 0 and json.loads(bl.read_text())["lines"] == 250 and "recorded" in msg, msg)
        check("over the limit but not grown past the baseline is exit 0", go(over, bl)[:2] == (0, "over"))
        grown = index("grown", 251)
        check("grown past the baseline is exit 1", go(grown, bl)[:2] == (1, "over"))
        check("over the limit with no baseline is exit 1", go(over)[:2] == (1, "over"))
        bad = base / "bad.json"
        bad.write_text("{nope", encoding="utf-8")
        try:
            go(over, bad)
            check("an unreadable baseline is unusable, not a pass", False, "no Unusable raised")
        except Unusable:
            check("an unreadable baseline is unusable, not a pass", True)
        try:
            go(over, None, record=True)
            check("--record without --baseline is refused", False, "no Unusable raised")
        except Unusable:
            check("--record without --baseline is refused", True)
        check("an ok index with a baseline is untouched by it", go(index("ok2", 5), bl)[:2] == (0, "ok"))
        # the hook line
        out = _capture(["--index", str(index("h-ok", 5)), "--hook-line"])
        check("--hook-line is silent when the index is fine", out == (0, ""), repr(out))
        out = _capture(["--index", str(index("h-warn", 170)), "--hook-line"])
        check("--hook-line prints exactly one line on a warning and exits 0", out[0] == 0 and out[1].count("\n") == 1 and "memory index" in out[1], repr(out))
        out = _capture(["--index", str(index("h-over", 260)), "--hook-line"])
        check("--hook-line prints one line when over, and still exits 0", out[0] == 0 and out[1].count("\n") == 1 and "not loaded" in out[1], repr(out))
        out = _capture(["--index", str(base), "--hook-line"])
        check("--hook-line never fails a session start, even on an unreadable index", out == (0, ""), repr(out))
        # where the index lives
        home = base / "home"
        proj = base / "proj"
        (proj / ".claude").mkdir(parents=True)
        (home / ".claude").mkdir(parents=True)
        check("the default index is under ~/.claude/projects, named by the path with non-alphanumerics as dashes",
              default_index(proj, home) == home / ".claude" / "projects" / slug(proj.resolve()) / "memory" / "MEMORY.md", str(default_index(proj, home)))
        check("the slug matches a real one", slug(Path("/Users/fmanimashaun/projects/claude-skills")) == "-Users-fmanimashaun-projects-claude-skills")
        (home / ".claude" / "settings.json").write_text(json.dumps({"autoMemoryDirectory": str(base / "mem-user")}), encoding="utf-8")
        check("autoMemoryDirectory in user settings is honoured", default_index(proj, home) == base / "mem-user" / "MEMORY.md", str(default_index(proj, home)))
        (proj / ".claude" / "settings.local.json").write_text(json.dumps({"autoMemoryDirectory": str(base / "mem-proj")}), encoding="utf-8")
        check("and a project setting wins over the user setting", default_index(proj, home) == base / "mem-proj" / "MEMORY.md", str(default_index(proj, home)))
    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_memory_index selftest: {checks} checks passed")
    return 0


def _capture(argv: list[str]) -> tuple[int, str]:
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
