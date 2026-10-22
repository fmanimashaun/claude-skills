"""Mutation guard: check_security_review (#2119). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_security_review",
    subject="scripts/check_security_review.py",
    selftest="scripts/check_security_review.py",
    selftest_args=("--selftest",),
    needs=("scripts/check_threat_model.py", "scripts/classify_door.py", "scripts/risky_diff.py", "scripts/advisory_scope.py", "scripts/detect_stack.py", "scripts/fixture_git.py"),  # risky_diff imports advisory_scope (#2264)  # detect_stack: the stack code_syntax (#2119)
    mutations=(
        Mutation(
            "a record for an earlier commit stops being refused",
            '    if kind in ("missing", "no-head", "stale", "no-verdict"):',
            '    if kind in ("missing", "no-head", "no-verdict"):',
            "a record for another commit is stale",
        ),
        Mutation(
            "a mitigate row answered `not implemented` stops being BLOCKING",
            '            if verdict == "not implemented":',
            "            if False:",
            "a mitigate row not implemented is BLOCKING, exit 1 (never 3, which the gates read as not applicable)",
        ),
        Mutation(
            "evidence past the end of the file is accepted",
            "                elif int(ev.group(2)) < 1 or int(ev.group(2)) > len(src):",
            "                elif int(ev.group(2)) < 1 or int(ev.group(2)) > 10**9:",
            "evidence past the end of the file is incomplete",
        ),
        Mutation(
            "a stale accept row stops being a finding",
            '            if verdict == "stale":',
            "            if False:",
            "a stale accept row is a BLOCKING finding, exit 1",
        ),
        Mutation(
            "a row the record leaves out stops being incomplete",
            '        if got is None:\n            incomplete.append(f"{label}: no answer in the record")\n            continue',
            "        if got is None:\n            continue",
            "a mitigate row with no answer is incomplete",
        ),
        Mutation(
            "a record that answers a row the model lacks is accepted",
            "    for n in sorted(set(answers) - known):",
            "    for n in []:",
            "a row the model does not have is another model",
        ),
        Mutation(
            "a model with no readable table stops being exit 2",
            "    if not threat_rows(model_text):",
            "    if False:",
            "an unreadable model is exit 2",
        ),
        Mutation(
            "a comment, blank or block-comment line is accepted as the line that implements a control",
            '                elif int(ev.group(2)) in non_code_lines(src, *rules_for(ev.group(1), code_syntax(root), data_markers(root)),\n                                                         line_comments=line_comments_for(ev.group(1), code_syntax(root))):',
            "                elif False:",
            "evidence on a comment line is incomplete",
        ),
        Mutation(
            # #2119 stack-neutral: a stack's own block comments and heredocs come from its descriptor's code_syntax.
            "the stack's code_syntax is ignored, so a line inside the stack's own block comment counts as code",
            '                elif int(ev.group(2)) in non_code_lines(src, *rules_for(ev.group(1), code_syntax(root), data_markers(root)),\n                                                         line_comments=line_comments_for(ev.group(1), code_syntax(root))):',
            "                elif int(ev.group(2)) in non_code_lines(src):",
            "evidence inside a stack block comment is incomplete",
        ),
        Mutation(
            "a block comment never closes, so the code after it reads as comment",
            "            elif close in raw:\n                again",
            "            elif False:\n                again",
            "code after every span closes passes",
        ),
        Mutation(
            "a heredoc body counts as code",
            '            heredocs = [(m.group("id"), bool(re.match(r"<<[~-]", m.group(0)))) for m in heredoc.finditer(raw)]',
            "            heredocs = []",
            "evidence inside a heredoc body is incomplete",
        ),
        Mutation(
            "only the first of several heredocs on one line is tracked",
            '            heredocs = [(m.group("id"), bool(re.match(r"<<[~-]", m.group(0)))) for m in heredoc.finditer(raw)]',
            '            heredocs = [(m.group("id"), bool(re.match(r"<<[~-]", m.group(0)))) for m in heredoc.finditer(raw)][:1]',
            "evidence in the second of two heredocs opened on one line is incomplete",
        ),
        Mutation(
            "a committed symlink is read through, so its target path reads as code",
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] not in ("100644", "100755"):',
            "    if tree.returncode != 0 or not tree.stdout.strip():",
            "a committed symlink is refused, never read through its target",
        ),
        Mutation(
            "the middle of a /* */ span counts as code",
            "        if closing is not None:\n            out.add(n)",
            "        if False:\n            out.add(n)",
            "evidence in the middle of a /* */ span with no leading star is incomplete",
        ),
        Mutation(
            "an evidence path with `..` is normalised into the repository instead of refused",
            '    if p.is_absolute() or ".." in p.parts:\n        return None\n    tree = subprocess.run(',
            '    import os\n\n    p = PurePosixPath(os.path.normpath(p.as_posix()))\n    tree = subprocess.run(',
            "a `..` evidence path is refused",
        ),
        Mutation(
            "the evidence file is read from the working tree, not HEAD",
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] not in ("100644", "100755"):\n        return None  # not in HEAD, a symlink (`git show` prints its target, which would read as code), a directory or a submodule\n    proc = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{p.as_posix()}"], capture_output=True)',
            '    proc = type("P", (), {"returncode": 0 if (root / p).is_file() else 1, "stdout": (root / p).read_bytes() if (root / p).is_file() else b""})()',
            "evidence in a file that exists only in the working tree is refused",
        ),
        Mutation(
            # #2214 review: a column0 opener (a language that honours it only there) matched after indentation and hid real code.
            "a column0 block opener is matched after indentation again",
            "        opened = next(((o, c, col0) for o, c, col0 in blocks if (raw if col0 else t).startswith(o)), None)",
            "        opened = next(((o, c, col0) for o, c, col0 in blocks if t.startswith(o)), None)",
            "an indented column0 opener is code",
        ),
        Mutation(
            # #2214 adversary: a mid-line or indented closer closed a column0 block.
            "a column0 block closes anywhere on a line again",
            "            if col0:\n                if raw.startswith(close):\n                    closing = None",
            "            if col0:\n                if close in raw:\n                    closing = None",
            "an indented closer does not close a column0 block",
        ),
        Mutation(
            "a span opener after code on the same line is ignored again",
            "        left = _open_after(raw, blocks)\n        if left:\n            closing = (left, False)",
            "        left = None",
            "a span opened after code hides the lines below",
        ),
        Mutation(
            "a bare heredoc ends at an indented terminator again",
            "            if (t if indented else raw) == ident:",
            "            if t == ident:",
            "an indented line is not a bare heredoc's terminator",
        ),
        Mutation(
            "a data marker stops ending code",
            "        if raw in end_markers:",
            "        if False:",
            "lines after a data marker are not code",
        ),
        Mutation(
            "a directory or other non-file mode is read again",
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] not in ("100644", "100755"):',
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] == "120000":',
            "a directory is never read as a cited file",
        ),
        Mutation(
            "an undeclared file type falls back to neutral rules again",
            "                elif not declared(ev.group(1), code_syntax(root)):",
            "                elif False:",
            "a file type no stack declares is refused",
        ),
        Mutation(
            "a row answered twice is last-wins again",
            "            if n in answers:",
            "            if False:",
            "a row answered twice is refused",
        ),
        Mutation(
            # #2214 adversary pass 4: only the first opener on a line was seen, so `<%# a %> t <%# b` left the next line as code.
            "only the first span on a line is walked again",
            "        pos = end + len(c)",
            "        return None",
            "a second span opened after a closed one hides the next line",
        ),
        Mutation(
            "a span reopened on its closing line is missed again",
            "                again = _open_after(raw, blocks, raw.find(close) + len(close))",
            "                again = None",
            "a span reopened on its closing line hides the next line",
        ),
        Mutation(
            "a column0 block never closes, so the code after it reads as comment",
            "                if raw.startswith(close):\n                    closing = None",
            "                if False:\n                    closing = None",
            "evidence on code after a block comment passes",
        ),
        Mutation(
            "#2260: a row's line-comment marker is ignored, so a `<!--` line reads as code",
            '        if not t or t.startswith(("#", "//", *line_comments)):',
            '        if not t or t.startswith(("#", "//")):',
            "a line starting with the row's own line-comment marker is not code",
        ),
        Mutation(
            "#2260: the refusal is not applied when a citation is judged",
            "                elif refusal_for(ev.group(1), src, code_syntax(root)):",
            "                elif False:",
            "a file the row's refuse_when matches is refused whole",
        ),
        Mutation(
            "#2260: refuse_when never matches, so a template literal's body lines read as code",
            '                    if pattern.search(line.lstrip("\\ufeff") if n == 1 else line):',
            "                    if False:",
            "a file the row's refuse_when matches is refused whole",
        ),
        Mutation(
            "#2260: every file type counts as declared, so .ts, .jsx and .tsx are read with neutral rules",
            '    return any(path.endswith(ext) for row in rows for ext in row.get("extensions") or [])',
            "    return True",
            "a file type no stack declares is refused, not read with neutral rules",
        ),
        Mutation(
            "#2260: a row's line-comment markers apply to every file type, not only the row's extensions",
            '    return tuple(m for row in rows if any(path.endswith(ext) for ext in row.get("extensions") or []) for m in row.get("line_comments") or [])',
            '    return tuple(m for row in rows for m in row.get("line_comments") or [])',
            "a row's line-comment marker does not apply to another file type",
        ),
        Mutation(
            "#2260: a row's refuse_when applies to every file type, so a .rb file with a lone backtick is refused",
            '        if any(path.endswith(ext) for ext in row.get("extensions") or []):\n            for refusal in',
            '        if True:\n            for refusal in',
            "a row's refuse_when does not apply to another file type",
        ),
        Mutation(
            "#2260: a file is decoded as plain UTF-8, so a byte-order mark stays in line 1 and `\\ufeff// comment` reads as code",
            'proc.stdout.decode("utf-8-sig", errors="replace").splitlines()',
            'proc.stdout.decode("utf-8", errors="replace").splitlines()',
            "a byte-order mark is stripped when a file is read at HEAD",
        ),
        Mutation(
            "#2260: a byte-order mark is kept in line 1 when the lines are judged",
            '        if n == 1:\n            raw = raw.lstrip("\\ufeff")',
            '        if False:\n            raw = raw.lstrip("\\ufeff")',
            "a byte-order mark is not part of line 1",
        ),
        Mutation(
            "#2260: a byte-order mark counts as text before `<!--` on line 1, so a refuse_when pattern misreads it",
            'pattern.search(line.lstrip("\\ufeff") if n == 1 else line)',
            "pattern.search(line)",
            "a byte-order mark is not text before `<!--` on line 1",
        ),
    ),
)
