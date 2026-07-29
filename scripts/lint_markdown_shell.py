#!/usr/bin/env python3
"""Verify the shell we ship INSIDE markdown.

The repo mandates `bash -n` for every `.sh` file, and then ships ~200 lines of bash in
fenced blocks inside command/skill markdown — the lines an agent copies and runs verbatim
in a user's project. Nothing checked those. Three review findings in one week lived there:

  * release.md ran `--check || echo`, swallowing the exit, so a stale artefact shipped
  * release.md's guard conflated "no data" with "no tool", silently skipping verification
  * setup.md resolved a script via ${CLAUDE_PLUGIN_ROOT} but passed a project-relative path

Each was a prose-reviewed, never-executed snippet. A rule saying "be careful with guards"
does not survive; a check does. Doctrine: put the guarantee in the deterministic layer.

What it does:
  1. SYNTAX — extracts every ```bash|sh|shell block and runs `bash -n` on it. Template
     placeholders (`<pack>`, `$ARGUMENTS`, `vX.Y.Z`) are substituted first, because `<pack>`
     is a redirect to bash and would otherwise fail every templated snippet.
  2. SWALLOWED VERDICT — flags `|| echo` / `|| true` on a verification command. This is the
     defect that shipped twice: a check whose failure is consumed is worse than no check,
     because the message makes it look like the gate ran.
  3. UNQUOTED TEST OPERANDS — `[ -f $VAR ]` word-splits on paths with spaces.

Exit: 0 clean · 1 findings · 2 usage/environment.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Leading whitespace is tolerated on BOTH fences: a block nested inside a numbered list is
# indented, and anchoring to column 1 made 11 blocks across 7 files invisible — including the
# one in doc-updater.md. A linter that silently skips input is the failure mode it exists to
# prevent, so `--audit-coverage` cross-checks this regex against a looser independent scan.
# (Second time this exact column-1 assumption has bitten: brand_pack_lint had it too.)
FENCE = re.compile(r"^[ \t]*```[ \t]*(bash|sh|shell|console|shell-session)[^\n]*\n(.*?)^[ \t]*```",
                   re.S | re.M)

# Substituted before `bash -n` so a TEMPLATE is not reported as a syntax error. `<pack>` is
# the important one: bash reads `<` as a redirect, so every placeholder path would fail.
PLACEHOLDERS = [
    (re.compile(r"<[A-Za-z][A-Za-z0-9 _./|-]*>"), "PLACEHOLDER"),
    (re.compile(r"\$ARGUMENTS"), "ARGS"),
    (re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}"), "/plugin/root"),
    (re.compile(r"\$\{CLAUDE_PROJECT_DIR\}"), "/project/dir"),
    (re.compile(r"\bvX\.Y\.Z\b"), "v0.0.0"),
    (re.compile(r"\$\{\{[^}]*\}\}"), "GHA_EXPR"),          # GitHub Actions expressions
]

# Commands whose exit code IS the verdict. Swallowing it defeats the purpose.
# (?<![\w-]) matters: a plain verify also matches inside `pipeline-verify`, which flagged
# `docker rm -f pipeline-verify || true` — an idempotent cleanup, not a swallowed verdict.
VERIFY_VERBS = (
    r"(--check\b|--dry-run\b|(?<![\w-])verify\b|(?<![\w-])lint\b"
    r"|\bbash -n\b|(?<![\w-])rspec\b|(?<![\w-])rubocop\b"
    r"|(?<![\w-])brakeman\b|--porcelain\b)"
)

SWALLOWED = re.compile(VERIFY_VERBS + r"[^\n|]*\|\|\s*(echo|true|:)\b")
UNQUOTED_TEST = re.compile(r"\[\s+-[a-z]\s+\$[A-Za-z_][A-Za-z0-9_]*\s+\]")


class Finding:
    def __init__(self, path: str, line: int, kind: str, detail: str, snippet: str):
        self.path, self.line, self.kind, self.detail, self.snippet = path, line, kind, detail, snippet


def iter_blocks(path: str):
    """Yield (start_line, code) for each fenced shell block."""
    src = open(path, encoding="utf-8", errors="replace").read()
    for match in FENCE.finditer(src):
        start = src[: match.start()].count("\n") + 2   # +1 for the fence line itself
        yield start, match.group(2)


def substitute(code: str) -> str:
    for pattern, repl in PLACEHOLDERS:
        code = pattern.sub(repl, code)
    return code


def syntax_check(code: str) -> str | None:
    """Return bash's complaint, or None when the block parses.

    The code goes in on STDIN rather than via a temp file: `bash -n /tmp/x.sh` broke under
    Git Bash, where a Windows temp path reaches bash with its separators eaten
    (`C:UsersFISAYO~1AppData…`), so EVERY block reported a false syntax error. With no
    filename there is no path to mangle — and nothing to clean up.

    Encoded explicitly as UTF-8 rather than via `text=True`: the default uses the locale
    codec, which is cp1252 on Windows and dies on any non-ASCII character in a snippet
    (a `✓` in an echo was enough to crash the whole run).
    """
    try:
        proc = subprocess.run(["bash", "-n"], input=substitute(code).encode("utf-8"),
                              capture_output=True, timeout=20)
        if proc.returncode == 0:
            return None
        err = (proc.stderr or proc.stdout).decode("utf-8", "replace")
        return err.strip().replace("stdin", "<block>")
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not run bash -n: {exc}"


def lint_file(path: str) -> list[Finding]:
    findings: list[Finding] = []
    for start, code in iter_blocks(path):
        problem = syntax_check(code)
        if problem:
            findings.append(Finding(path, start, "syntax", problem, code.strip().splitlines()[0] if code.strip() else ""))
        for offset, line in enumerate(code.splitlines()):
            if SWALLOWED.search(line):
                findings.append(Finding(
                    path, start + offset, "swallowed-verdict",
                    "a verification command's failure is consumed by `|| echo`/`|| true`, so the "
                    "check cannot block. Worse than no check — the message implies the gate ran.",
                    line.strip()))
            if UNQUOTED_TEST.search(line):
                findings.append(Finding(
                    path, start + offset, "unquoted-test",
                    "unquoted variable in a test operand word-splits on paths containing spaces; "
                    'quote it: [ -f "$VAR" ]',
                    line.strip()))
    return findings


def discover(roots: list[str]) -> list[str]:
    found = []
    for root in roots:
        if not os.path.exists(root):
            raise FileNotFoundError(root)
        if os.path.isfile(root):
            found.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.endswith(".md"):
                    found.append(os.path.join(dirpath, name))
    return sorted(set(p.replace(os.sep, "/") for p in found))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lint_markdown_shell.py",
        description="Syntax-check and pattern-scan the shell embedded in shipped markdown.")
    parser.add_argument("paths", nargs="*", default=["plugins", "skills", ".claude"],
                        help="files or directories (default: plugins skills .claude)")
    parser.add_argument("--quiet", action="store_true", help="only print findings")
    parser.add_argument("--audit-coverage", action="store_true",
                        help="cross-check the fence regex against a looser independent scan and "
                             "report any block it would skip (a silently-skipped block is the "
                             "failure mode this tool exists to prevent)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if subprocess.run(["bash", "-c", "true"], capture_output=True).returncode != 0:
        print("lint_markdown_shell: bash is not available.", file=sys.stderr)
        return 2

    try:
        files = discover(args.paths or ["plugins", "skills", ".claude"])
    except FileNotFoundError as exc:
        print(f"lint_markdown_shell: no such path: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("lint_markdown_shell: no markdown found in the given paths.", file=sys.stderr)
        return 2
    if args.audit_coverage:
        loose = re.compile(r"```[ \t]*(?:bash|sh|shell|console|shell-session)\b")
        gaps = []
        seen = missed = 0
        for path in files:
            src = open(path, encoding="utf-8", errors="replace").read()
            a, b = len(list(FENCE.finditer(src))), len(loose.findall(src))
            seen += a; missed += b
            if a != b:
                gaps.append((path, a, b))
        print(f"fence regex sees {seen} block(s); a looser scan finds {missed}")
        for path, a, b in gaps:
            print(f"  GAP {path}: parsed {a}, present {b}")
        if gaps:
            print("\nBlocks the linter would skip. Fix the fence regex — coverage gaps "
                  "make a clean report meaningless.")
            return 1
        print("coverage matches.")
        return 0

    # Reconcile coverage on EVERY run, not only under --audit-coverage. An extractor that
    # under-matches reports "no findings" for input it never read, which is indistinguishable
    # from a clean result — the exact failure this tool shipped with (11 blocks skipped by a
    # column-1 anchor). Checking it only on request means a future regex tweak can regress
    # coverage silently, so the reconciliation is not optional.
    loose_total = 0
    coverage_gaps: list[tuple[str, int, int]] = []
    loose_scan = re.compile(r"```[ \t]*(?:bash|sh|shell|console|shell-session)\b")

    findings: list[Finding] = []
    blocks = lines = 0
    for path in files:
        src = open(path, encoding="utf-8", errors="replace").read()
        parsed = len(list(FENCE.finditer(src)))
        present = len(loose_scan.findall(src))
        loose_total += present
        if parsed != present:
            coverage_gaps.append((path, parsed, present))
        for _, code in iter_blocks(path):
            blocks += 1
            lines += len(code.strip().splitlines())
        findings.extend(lint_file(path))

    if coverage_gaps:
        print(f"COVERAGE GAP — parsed {blocks} block(s) but {loose_total} appear present.\n"
              "Blocks below were NOT checked, so a clean result below would be meaningless:")
        for path, parsed, present in coverage_gaps:
            print(f"  {path}: parsed {parsed}, present {present}")
        print("\nFix the fence regex before trusting any report from this tool.")
        return 1

    if not args.quiet:
        print(f"checked {blocks} shell block(s) / {lines} line(s) across {len(files)} markdown file(s)")

    if not findings:
        if not args.quiet:
            print("no findings.")
        return 0

    by_kind: dict[str, int] = {}
    for f in sorted(findings, key=lambda f: (f.path, f.line)):
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        print(f"\n{f.path}:{f.line}  [{f.kind}]")
        if f.snippet:
            print(f"    {f.snippet}")
        print(f"    -> {f.detail}")
    print("\n" + ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items())))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
