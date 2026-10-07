#!/usr/bin/env python3
"""Every shipped plugin script must parse on Python 3.9, the python3 stock macOS ships (#1597).

Hooks run as `python3` on the USER's machine. CI pins 3.12, where `f"{x!r:{'\\n'}}"`-style
code parses, so a newer-syntax change was invisible until a user on stock macOS hit a SyntaxError
and a fail-closed hook denied everything. Measured 2026-10-06 on /usr/bin/python3 (3.9.6): 2 of 227
shipped `.py` files failed, `check_hook_gates.py` and `project_gates.py`, both a backslash inside an
f-string expression (legal only from 3.12, PEP 701).

WHAT IS CHECKED, over `plugins/**/*.py` and every `python3 -c '...'` block in a plugin hook shell:

1. `ast.parse(..., feature_version=(3, 9))`. Rejects `match`, `except*`, type parameters and the
   rest of what the grammar flag covers. On an interpreter older than 3.12 it is the real parser.
2. The PEP 701 f-string forms, which `feature_version` does NOT reject (measured: it parses a
   backslash in an f-string expression under feature_version=(3, 9) on 3.14): a backslash, a
   newline in a single-quoted f-string, the enclosing quote character, or a `#` comment, inside an expression.
3. When a real Python 3.9 is on the machine, `compile()` under it: the authority, and reported as
   a note when there is none, because a check that silently ran only the approximation would read
   as the same claim.

NOT CHECKED: what 3.9 only reveals at RUN time (`int | None` in an evaluated annotation, a stdlib
name or argument added after 3.9: measured on 2026-10-07 by running each of the 125 non-mutation shipped scripts with `--help` on
3.9.6, exactly one, `validate_evidence_selftest.py`'s `Path.write_text(newline=)`, a 3.10+ argument, fixed here). A SyntaxError is what
crashes a hook before it can fail open or closed, which is why it is the part gated.

Exit 0 clean, 1 findings, 2 unusable (nothing to check). `--selftest` proves each rule can fail.
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = (3, 9)
EMBEDDED = re.compile(r"python3 -c '((?:[^'\\]|\\.)*)'", re.S)


def _quote_of(opening: str) -> str:
    """The delimiter in an f-string's opening token, after its prefix letters: three quotes, or one."""
    body = opening.lstrip("rRfFbBuU")
    for q in ('"' * 3, "'" * 3, '"', "'"):
        if body.startswith(q):
            return q
    return ""


def _fstring_tokens(source: str):
    """From the 3.12 tokenizer: (ranges, comments). `ranges` is (start, end, quote) of every f-string LITERAL PIECE; a JoinedStr built by
    implicit concatenation (`"a" f'{x}'`) has one quote per piece, so the AST node alone cannot say which one encloses an expression.
    `comments` is the start of every COMMENT token that falls INSIDE an f-string: only an expression can hold one, because a `#` in the
    literal text is FSTRING_MIDDLE and a `#` in a string inside the expression is a STRING token, which 3.9 accepts (so a bare `'#' in text`
    test would be a false positive)."""
    import io
    import tokenize

    ranges, comments, stack = [], [], []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.FSTRING_START:
            stack.append((tok.start, _quote_of(tok.string)))
        elif tok.type == tokenize.FSTRING_END and stack:
            start, quote = stack.pop()
            ranges.append((start, tok.end, quote))
        elif tok.type == tokenize.COMMENT and stack:
            comments.append(tok.start)
    return ranges, comments


def pep701_findings(source: str, tree: ast.AST) -> list[tuple[int, str]]:
    """Expressions inside an f-string that only 3.12+ parses. Needed only where the interpreter is 3.12+;
    an older one rejects them in `ast.parse` already."""
    found: list[tuple[int, str]] = []
    ranges, comments = _fstring_tokens(source)
    found.extend((row, "a # comment inside an f-string expression (3.12+)") for row, _ in comments)
    lines = source.splitlines()
    for part in ast.walk(tree):
        if not isinstance(part, ast.FormattedValue):
            continue
        expr = ast.get_source_segment(source, part.value) or ""
        row = part.value.lineno
        col = len(lines[row - 1].encode("utf-8")[: part.value.col_offset].decode("utf-8")) if row <= len(lines) else 0
        enclosing = [r for r in ranges if r[0] <= (row, col) < r[1]]
        quote = min(enclosing, key=lambda r: (r[1][0] - r[0][0], r[1][1] - r[0][1]))[2] if enclosing else ""
        if "\\" in expr:
            found.append((row, "a backslash inside an f-string expression (3.12+)"))
        elif quote and quote in expr:
            found.append((row, f"the f-string's own quote {quote} reused inside its expression (3.12+)"))
        elif "\n" in expr and len(quote) == 1:
            found.append((row, "a newline inside a single-quoted f-string expression (3.12+)"))
    return found


def parse_findings(source: str, filename: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(source, filename, feature_version=FLOOR)
    except SyntaxError as err:
        return [(err.lineno or 0, f"SyntaxError on the {FLOOR[0]}.{FLOOR[1]} grammar: {err.msg}")]
    return pep701_findings(source, tree) if sys.version_info >= (3, 12) else []


def real_interpreter() -> str | None:
    """A genuine Python 3.9, if the machine has one: python3.9 on PATH, or the stock macOS /usr/bin/python3."""
    for candidate in (shutil.which("python3.9"), "/usr/bin/python3"):
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run([candidate, "-c", "import sys;print(sys.version_info[:2]==(3,9))"],
                               capture_output=True, text=True, timeout=30)
        if probe.returncode == 0 and probe.stdout.strip() == "True":
            return candidate
    return None


def compile_on(interpreter: str, source: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(source)
        name = handle.name
    try:
        run = subprocess.run([interpreter, "-c", f"compile(open({name!r}, encoding='utf-8').read(), 'shipped', 'exec')"],
                             capture_output=True, text=True, timeout=60)
    finally:
        Path(name).unlink(missing_ok=True)
    return None if run.returncode == 0 else (run.stderr.strip().splitlines() or ["failed to compile"])[-1]


def units(root: Path) -> list[tuple[str, str]]:
    """(label, source) for every shipped python: each plugins/**/*.py, each `python3 -c '...'` in a plugin hook shell."""
    found: list[tuple[str, str]] = []
    for path in sorted((root / "plugins").rglob("*.py")):
        if "__pycache__" not in path.parts:
            found.append((str(path.relative_to(root)), path.read_text(encoding="utf-8")))
    for path in sorted((root / "plugins").glob("*/hooks/scripts/**/*.sh")):
        for index, block in enumerate(EMBEDDED.finditer(path.read_text(encoding="utf-8")), start=1):
            found.append((f"{path.relative_to(root)} (python3 -c block {index})", block.group(1)))
    return found


def scan(root: Path, interpreter: str | None = None) -> tuple[list[str], int]:
    findings: list[str] = []
    checked = units(root)
    for label, source in checked:
        findings += [f"{label}:{line}: {why}" for line, why in parse_findings(source, label)]
        if interpreter and not any(f.startswith(label + ":") for f in findings):
            error = compile_on(interpreter, source)
            if error:
                findings.append(f"{label}: does not compile on the real Python {FLOOR[0]}.{FLOOR[1]}: {error}")
    return findings, len(checked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true", help="prove every rule can fail")
    parser.add_argument("--root", default=str(ROOT), help="repo root to scan (default: this repo)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    root = Path(args.root)
    interpreter = real_interpreter()
    findings, count = scan(root, interpreter)
    if count == 0:
        print("UNUSABLE: no plugins/**/*.py to check", file=sys.stderr)
        return 2
    for line in findings:
        print(line)
    where = f"the real {interpreter}" if interpreter else "no real Python 3.9 on this machine (the grammar check alone ran)"
    print(f"{count} shipped python units checked on the {FLOOR[0]}.{FLOOR[1]} floor; authority: {where}")
    return 1 if findings else 0


def selftest() -> int:
    failures: list[str] = []

    def expect(label: str, ok: bool) -> None:
        print(("ok    " if ok else "FAIL  ") + label)
        if not ok:
            failures.append(label)

    expect("a clean script has no findings", parse_findings("x = 1\nprint(f'{x!r}')\n", "t.py") == [])
    expect("a match statement is refused on the 3.9 grammar",
           bool(parse_findings("match 1:\n    case 1:\n        pass\n", "t.py")))
    expect("a backslash in an f-string expression is refused",
           bool(parse_findings("n = 'a'\nprint(f\"{n.replace('a', '\\\\n')}\")\n", "t.py")))
    expect("the f-string's own quote reused in its expression is refused",
           bool(parse_findings("d = {'k': 1}\nprint(f\"{d[\"k\"]}\")\n", "t.py")))
    expect("a backslash OUTSIDE the expression is fine", parse_findings("print(f'line\\n{1}')\n", "t.py") == [])
    expect("a different quote inside the expression is fine", parse_findings("d = {'k': 1}\nprint(f\"{d['k']}\")\n", "t.py") == [])
    expect("a # comment inside an f-string expression is refused",
           bool(parse_findings('x = 1\nprint(f"""{x # note\n}""")\n', "t.py")))
    expect("a # comment inside a parenthesised f-string expression is refused",
           bool(parse_findings('x = 1\nprint(f"""{(x # note\n)}""")\n', "t.py")))
    expect("a # inside a string literal in the expression is fine (3.9 accepts it)", parse_findings("print(f\"{'#'}\")\n", "t.py") == [])
    expect("a # in an f-string's literal text is fine", parse_findings('x = 1\nprint(f"# {x}")\n', "t.py") == [])
    expect("a multi-line expression in a triple-quoted f-string with NO comment is fine",
           parse_findings('x = 1\nprint(f"""{x\n}""")\n', "t.py") == [])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        expect("no plugins at all is UNUSABLE, never clean", main(["--root", tmp]) == 2)
        (root / "plugins" / "p" / "scripts").mkdir(parents=True)
        (root / "plugins" / "p" / "hooks" / "scripts").mkdir(parents=True)
        (root / "plugins" / "p" / "scripts" / "ok.py").write_text("x = 1\n", encoding="utf-8")
        expect("a clean tree exits 0", main(["--root", tmp]) == 0)
        (root / "plugins" / "p" / "hooks" / "scripts" / "h.sh").write_text(
            "#!/bin/bash\nv=\"$(python3 -c 'match 1:\n  case 1: pass')\"\n", encoding="utf-8")
        expect("a bad python3 -c block inside a hook shell is found", main(["--root", tmp]) == 1)
        (root / "plugins" / "p" / "hooks" / "scripts" / "h.sh").unlink()
        (root / "plugins" / "p" / "scripts" / "bad.py").write_text("match 1:\n    case 1:\n        pass\n", encoding="utf-8")
        expect("a bad script in the tree exits 1", main(["--root", tmp]) == 1)

    interpreter = real_interpreter()
    if interpreter:
        expect("the real 3.9 refuses a backslash in an f-string expression",
               compile_on(interpreter, "print(f\"{'a'.replace('a', '\\\\n')}\")\n") is not None)
        expect("the real 3.9 accepts a clean script", compile_on(interpreter, "print(1)\n") is None)
    else:
        print("note  no real Python 3.9 here: the compile-on-3.9 rule was not exercised")

    print(f"{'FAIL' if failures else 'ok'}: check_python_floor selftest")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
