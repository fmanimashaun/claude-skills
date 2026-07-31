#!/usr/bin/env python3
"""Syntax-check the JavaScript, Ruby and ERB we ship inside markdown fences (#248).

    python3 scripts/lint_markdown_code.py
    python3 scripts/lint_markdown_code.py --audit-coverage
    python3 scripts/lint_markdown_code.py --selftest

WHY. `lint_markdown_shell.py` exists because ~200 lines of bash live in fenced blocks and an agent
copies them into a user's project verbatim. That argument was never specific to bash, and the other
languages are the larger surface: **151 ruby, 81 erb and 22 js blocks** against 79 bash. A syntax
error in a fenced `focus_trap.js` reaches a user's browser exactly the way a bad `bash` block reaches
their shell — and until this existed, nothing executed a single one of them.

It is not hypothetical. While documenting #95's dialog batch I edited `focus_trap.js` and wrote

    if (!document.body.style.overflow) { ... }
    (nodes()[0] || container).focus()

which starts a line with `(` directly after a block. It parses, but it is the classic ASI footgun and
I only caught it by running `node --check` by hand. Nothing in 27 gates would have.

THE HARD PART IS NOT PARSING, IT IS FRAGMENTS. Reference docs are full of deliberate elision
(`def perform(account) ... end`, `upvote({ params: { id, url } }) { ... }`) and of fragments that are
correct but not standalone — a method body with no class around it, an object literal with no
assignment. A checker that reports those is a checker nobody keeps. So each block is:

  1. **normalised** — documentation elisions become syntactically neutral tokens, exactly as the
     shell linter substitutes `<pack>` before `bash -n`; then
  2. tried in a **ladder of contexts** — bare, then wrapped in the enclosing shapes a reader would
     obviously supply (a class body, a method, an object literal). It passes if ANY context parses.

The ladder is deliberately shallow and named. It answers the question that matters — *can a reader
paste this into the obvious place and have it parse* — without becoming a checker that accepts
anything. Widening it to make a failure go away is how this tool stops finding defects.

FAIL-OPEN, AND SAY SO. `node` and `ruby` are not guaranteed on a maintainer's machine the way
`python3` is. A missing interpreter yields **skip**, never ok, per `maintainer_doctor.py`'s
three-state rule: a check that did not run is not a pass.

Stdlib only.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Indented fences are real (nested lists in crud-modal-pattern.md), and anchoring to column 1 made
# 11 blocks invisible to the shell linter. Same regex shape, same reason. `--audit-coverage` and the
# every-run reconciliation below cross-check it against a looser independent scan.
# ORDER AND THE `\b` BOTH MATTER, and getting either wrong is silent. Without the boundary, `js`
# matches the `js` in ```json and `[^\n]*` swallows the `on` — so every JSON block in the repo was
# being handed to `node --check` as JavaScript. Longest-first ordering keeps `ruby` from being
# truncated to `rb`. The coverage audit is what caught this: the loose control already had a `\b`,
# the strict regex did not, and the two disagreed by 5 blocks in 4 files. An over-matching extractor
# is as dishonest as an under-matching one — it reports on input that was never that language.
# Distinct from 0 (clean) and 1 (findings): the run was INCOMPLETE because an interpreter
# was missing. maintainer_doctor.py maps this to SKIP, never to ok.
EXIT_INCOMPLETE = 3

LANGS = ("javascript", "js", "ruby", "rb", "erb")
_LANG_ALT = "|".join(LANGS)
FENCE = re.compile(r"^[ \t]*```[ \t]*(" + _LANG_ALT + r")\b[^\n]*\n(.*?)^[ \t]*```",
                   re.S | re.M)
LOOSE = re.compile(r"```[ \t]*(?:" + _LANG_ALT + r")\b")

# Documentation elisions. These are PROSE inside code, not code — the same class as `<pack>` in a
# shell template. Substituted before the interpreter sees the block.
_ELLIPSIS = r"(?:\.\.\.|…)"
RUBY_SUBS = [
    # `Order.create!(...)` / `def perform(account) ... end` — argument forwarding is only legal
    # inside a def that declares it, so at the top level these are elisions, not code.
    (re.compile(r"\(\s*" + _ELLIPSIS + r"\s*\)"), "()"),
    (re.compile(r"(?<![\w.])" + _ELLIPSIS + r"(?![\w.])"), "nil"),
]
JS_SUBS = [
    (re.compile(r"(?<![.\w])" + _ELLIPSIS + r"(?![.\w])"), "/* elided */"),
]

# `<%= form_with … do |f| %>` is THE most common Rails view idiom and stdlib ERB cannot parse it:
# it compiles to `_erbout << (form_with … do).to_s`, which is a syntax error. Rails compiles views
# with **erubi**, which handles the block form. Erubi is a gem, so depending on it would make this
# check pass or fail by machine — and for SYNTAX purposes the output-capture is immaterial. So the
# `=` is dropped from a tag that opens a block. Without this, 20 correct blocks were reported as
# broken: a false positive on the repo's single most common idiom, which is how a linter gets
# deleted rather than fixed.
ERB_BLOCK_TAG = re.compile(r"<%=((?:(?!%>).)*?\bdo\b\s*(?:\|[^|]*\|)?\s*-?)%>", re.S)
# `<%== raw_html %>` is erubi's raw-output tag, also valid in Rails views. Stdlib ERB reads it as
# `<%` plus a literal `=`, compiling to `((= expr))` — a syntax error. Same situation, same fix.
ERB_RAW_TAG = re.compile(r"<%==(?!=)")

# The ladder. Ordered cheapest-first; a block passes if ANY context parses. Each entry is named so a
# report can say WHICH shape accepted it, and so adding one is a visible decision.
JS_CONTEXTS = [
    ("bare", "{code}"),
    ("class body", "class __Probe {{\n{code}\n}}"),
    ("function body", "function __probe() {{\n{code}\n}}"),
    ("object literal", "const __probe = {{\n{code}\n}}"),
]
RUBY_CONTEXTS = [
    ("bare", "{code}"),
    ("class body", "class Probe\n{code}\nend"),
    ("method body", "def probe\n{code}\nend"),
]


class Finding:
    def __init__(self, path: str, line: int, lang: str, detail: str, snippet: str):
        self.path, self.line, self.lang = path, line, lang
        self.detail, self.snippet = detail, snippet


def substitute(code: str, lang: str) -> str:
    for pattern, repl in (JS_SUBS if lang in ("js", "javascript") else RUBY_SUBS):
        code = pattern.sub(repl, code)
    return code


def _run(cmd: list[str], payload: str) -> tuple[int, str, str]:
    """Run an interpreter over `payload` on stdin. Returns (rc, stdout, stderr-or-stdout).

    Encoded explicitly as UTF-8 rather than via `text=True`, for the reason the shell linter records:
    the default uses the locale codec, which is cp1252 on Windows and dies on the first non-ASCII
    character in a snippet. Our blocks are full of `—` and `…`.
    """
    try:
        proc = subprocess.run(cmd, input=payload.encode("utf-8"),
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", f"could not run {cmd[0]}: {exc}"
    out = proc.stdout.decode("utf-8", "replace")
    err = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
    return proc.returncode, out, err


def _check_js(code: str) -> tuple[str | None, str]:
    """None when some context parses; otherwise the BARE context's complaint.

    A module is only valid as .mjs, so `import`/`export` decides the extension. There is no stdin
    mode for `node --check`, so this is the one checker that needs a temp file — written under the
    repo's own temp handling, never a path that leaves the process.
    """
    import tempfile
    module = re.search(r"^\s*(?:import|export)\b", code, re.M) is not None
    first_error = ""
    for name, template in JS_CONTEXTS:
        # A module's import/export is a SyntaxError inside EVERY wrapper, so only `bare` can
        # host one. This skip is therefore an optimisation — three fewer `node` spawns — and
        # not a correctness guard; removing it cannot change a verdict. Said plainly because a
        # line that reads like a guarantee invites a mutation that can only pass vacuously.
        if module and name != "bare":
            continue
        payload = template.format(code=code)
        suffix = ".mjs" if module else ".js"
        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            rc, _out, err = _run(["node", "--check", path], "")
        finally:
            os.unlink(path)
        if rc == 0:
            return None, name
        if not first_error:
            first_error = err.replace(path, "<block>")
    return first_error or "did not parse in any context", ""


def _check_ruby(code: str) -> tuple[str | None, str]:
    first_error = ""
    for name, template in RUBY_CONTEXTS:
        rc, _out, err = _run(["ruby", "-c", "-"], template.format(code=code))
        if rc == 0:
            return None, name
        if not first_error:
            first_error = err.replace("-:", "<block>:")
    return first_error or "did not parse in any context", ""


def _unterminated_erb_tag(code: str) -> int | None:
    """Line number of an ERB tag that is never closed, or None.

    Checked EXPLICITLY because ERB will not do it: given `<%= foo` with no `%>`, stdlib ERB compiles
    happily and emits the remainder as a **literal string** — the expression silently never runs, so a
    view renders the source text (or nothing) where a value belongs. A compile that succeeds while
    discarding the code is worse than one that fails, and it is invisible to `ruby -c` afterwards.
    `<%%` is ERB's escape for a literal `<%` and is not a tag.
    """
    i = 0
    while True:
        i = code.find("<%", i)
        if i == -1:
            return None
        if code[i + 2:i + 3] == "%":      # `<%%` — an escaped literal, not a tag
            i += 3
            continue
        close = code.find("%>", i + 2)
        if close == -1:
            return code[:i].count("\n") + 1
        i = close + 2


def _check_erb(code: str) -> tuple[str | None, str]:
    """Compile the template to Ruby, then run the Ruby ladder over the result.

    `trim_mode: "-"` matches Rails' own ERB handling.
    """
    line = _unterminated_erb_tag(code)
    if line is not None:
        return (f"unterminated ERB tag at block line {line} — ERB does NOT error on this: it emits "
                "the rest of the template as a literal string, so the expression silently never "
                "runs and the view renders text where a value belongs"), ""
    code = ERB_BLOCK_TAG.sub(r"<%\1%>", ERB_RAW_TAG.sub("<%=", code))
    rc, compiled, err = _run(
        ["ruby", "-e", 'require "erb"; print ERB.new($stdin.read, trim_mode: "-").src'], code)
    if rc != 0:
        return f"ERB would not compile: {err}", ""
    return _check_ruby(compiled)


def check_block(code: str, lang: str) -> tuple[str | None, str]:
    """(problem, accepting-context-name). problem is None when the block parses."""
    normalised = substitute(code, lang)
    if lang in ("js", "javascript"):
        return _check_js(normalised)
    if lang == "erb":
        return _check_erb(normalised)
    return _check_ruby(normalised)


def iter_blocks(path: str):
    """Yield (start_line, lang, code) for every fenced code block in a supported language."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        src = handle.read()
    for match in FENCE.finditer(src):
        start = src[: match.start()].count("\n") + 2   # +1 for the fence line itself
        yield start, match.group(1).lower(), match.group(2)


def discover(roots: list[str]) -> list[str]:
    found: list[str] = []
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


def interpreters() -> tuple[list[str], list[str]]:
    """(available, missing) — a missing one means SKIP, never a silent pass."""
    available, missing = [], []
    for name, probe in (("node", ["node", "--version"]), ("ruby", ["ruby", "--version"])):
        try:
            ok = subprocess.run(probe, capture_output=True, timeout=20).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        (available if ok else missing).append(name)
    return available, missing


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lint_markdown_code.py",
        description="Syntax-check the JS, Ruby and ERB embedded in shipped markdown.")
    parser.add_argument("paths", nargs="*", default=["plugins", "skills", ".claude"],
                        help="files or directories (default: plugins skills .claude)")
    parser.add_argument("--quiet", action="store_true", help="only print findings")
    parser.add_argument("--audit-coverage", action="store_true",
                        help="cross-check the fence regex against a looser independent scan; a "
                             "silently-skipped block is the failure mode this tool prevents")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the checker fires on a real error AND stays silent on the "
                             "fragments and elisions our docs are full of")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if args.selftest:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lint_markdown_code_selftest as st
        return st.run()

    try:
        files = discover(args.paths or ["plugins", "skills", ".claude"])
    except FileNotFoundError as exc:
        print(f"lint_markdown_code: no such path: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("lint_markdown_code: no markdown found in the given paths.", file=sys.stderr)
        return 2

    if args.audit_coverage:
        gaps, seen, present_total = [], 0, 0
        for path in files:
            with open(path, encoding="utf-8", errors="replace") as handle:
                src = handle.read()
            a, b = len(list(FENCE.finditer(src))), len(LOOSE.findall(src))
            seen += a
            present_total += b
            if a != b:
                gaps.append((path, a, b))
        print(f"fence regex sees {seen} block(s); a looser scan finds {present_total}")
        for path, a, b in gaps:
            print(f"  GAP {path}: parsed {a}, present {b}")
        if gaps:
            print("\nBlocks the linter would skip. Fix the fence regex — coverage gaps make a "
                  "clean report meaningless.")
            return 1
        print("coverage matches.")
        return 0

    available, missing = interpreters()
    # EXIT 3 == "ran, but could not check everything". Exit 0 would make a partial run
    # indistinguishable from a clean one, and maintainer_doctor.py would print `ok` for a gate
    # that skipped most of its input — a skip masquerading as a pass, which is the exact failure
    # this repo's three-state rule exists to prevent. A container without Ruby skips 242 of 276
    # blocks; that must never read as green.
    if missing and not available:
        print(f"lint_markdown_code: SKIP — none of node/ruby available ({', '.join(missing)}). "
              "This is a skip, NOT a pass: no block was checked.", file=sys.stderr)
        return EXIT_INCOMPLETE
    if missing:
        print(f"lint_markdown_code: SKIP for {', '.join(missing)} — not installed. Blocks in "
              "that language were NOT checked.", file=sys.stderr)

    # Reconciled on EVERY run, not only under --audit-coverage: an extractor that under-matches
    # reports "no findings" for input it never read, which is indistinguishable from a clean result.
    findings: list[Finding] = []
    coverage_gaps: list[tuple[str, int, int]] = []
    counts: dict[str, int] = {}
    accepted_by: dict[str, int] = {}
    blocks = lines = loose_total = 0

    for path in files:
        with open(path, encoding="utf-8", errors="replace") as handle:
            src = handle.read()
        parsed, present = len(list(FENCE.finditer(src))), len(LOOSE.findall(src))
        loose_total += present
        if parsed != present:
            coverage_gaps.append((path, parsed, present))

        for start, lang, code in iter_blocks(path):
            if lang in ("js", "javascript") and "node" in missing:
                continue
            if lang in ("ruby", "rb", "erb") and "ruby" in missing:
                continue
            blocks += 1
            lines += len(code.strip().splitlines())
            counts[lang] = counts.get(lang, 0) + 1
            problem, context = check_block(code, lang)
            if problem:
                snippet = next((ln.strip() for ln in code.splitlines() if ln.strip()), "")
                findings.append(Finding(path, start, lang, problem, snippet))
            else:
                accepted_by[context] = accepted_by.get(context, 0) + 1

    if coverage_gaps:
        print(f"COVERAGE GAP — parsed {blocks} block(s) but {loose_total} appear present.\n"
              "Blocks below were NOT checked, so a clean result would be meaningless:")
        for path, parsed, present in coverage_gaps:
            print(f"  {path}: parsed {parsed}, present {present}")
        print("\nFix the fence regex before trusting any report from this tool.")
        return 1

    if not args.quiet:
        breakdown = ", ".join(f"{n} {lang}" for lang, n in sorted(counts.items()))
        print(f"checked {blocks} code block(s) / {lines} line(s) across {len(files)} file(s)"
              + (f" — {breakdown}" if breakdown else ""))
        # Which context accepted each block is the number to watch: if `bare` collapses and the
        # wrappers absorb everything, the ladder has stopped discriminating.
        if accepted_by:
            print("  accepted as: " + ", ".join(f"{n} {k}" for k, n in sorted(accepted_by.items())))

    if not findings:
        if not args.quiet:
            print("no findings.")
        # Clean, but only over what could be checked — see EXIT_INCOMPLETE.
        return EXIT_INCOMPLETE if missing else 0

    for finding in sorted(findings, key=lambda f: (f.path, f.line)):
        print(f"\n{finding.path}:{finding.line}  [{finding.lang}]")
        if finding.snippet:
            print(f"    {finding.snippet}")
        detail = finding.detail if len(finding.detail) < 400 else finding.detail[:400] + " …"
        print(f"    -> {detail}")
    print(f"\n{len(findings)} block(s) do not parse in any documented context.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
