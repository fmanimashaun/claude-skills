"""Mutation guard: check_mockup_gate. Declared here, run by scripts/mutation_check.py (#1376).

Each mutation lets a user-visible change through with no approved mock-up, or holds work it should not.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_mockup_gate",
    subject="scripts/check_mockup_gate.py",
    selftest="scripts/check_mockup_gate.py",   # --selftest lives in the module itself
    # The selftest also reads the scaffolded opt-out from setup-flow.md (#1496 review R8).
    needs=("scripts/classify_door.py", "commands/setup-flow.md"),
    mutations=(
        Mutation(
            "a UI change with no record passes",
            "    if not records:\n        return 1, [",
            "    if not records:\n        return 0, [",
            "a UI change with no mock-up record is held",
        ),
        Mutation(
            "views stop counting as UI scope",
            're.compile(r"^app/views/"), ',
            're.compile(r"^app/NEVER/"), ',
            "a view is UI scope",
        ),
        Mutation(
            "locale copy stops counting as user-visible",
            '            re.compile(r"^config/locales/"),\n',
            "",
            "a locale file (visible copy) is UI scope",
        ),
        # Its control: a JSON template is an API contract, not a screen.
        Mutation(
            "API templates are held as if they were screens",
            "or not NOT_UI.search(p)",
            "or True",
            "CONTROL: a JSON template is read by a client, not seen",
        ),
        Mutation(
            "an approval needs no link",
            "    if approval and not APPROVAL_URL.match(approval):",
            "    if False:",
            "an approval that is not a comment link is held",
        ),
        Mutation(
            "a desktop-only mock-up passes",
            "any(w <= 480 for w in widths) and any(w >= 1024 for w in widths)",
            "any(w >= 1024 for w in widths)",
            "a mock-up with no phone width is held",
        ),
        Mutation(
            "a mock-up file that does not exist passes",
            '    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):',
            "    elif False:",
            "a mock-up file that does not exist is held",
        ),
        Mutation(
            "a record missing its approval line passes",
            '    out = [f"{rel}: no `{k}:` line" for k in RECORD_KEYS if not fields.get(k)]',
            "    out = []",
            "a record with no approval line is held",
        ),
        Mutation(
            "the opt-out is ignored, so a project that declared it off is still held",
            "    if declared_off(root):",
            "    if False:",
            "a project that declared the gate off is not held",
        ),
        # Its control: prose that mentions the key is not a declaration.
        Mutation(
            "any mention of the key reads as an opt-out",
            'OPT_OUT = re.compile(r"^[ \\t]*(?:[-*+][ \\t]*)?`?mockup-gate:[ \\t]*off`?[ \\t]*$", re.M | re.I)',
            'OPT_OUT = re.compile(r".*mockup-gate:[ \\t]*off", re.M | re.I)',
            "CONTROL: prose mentioning the key is not a declaration",
        ),
        # Pre-release review of #1381.
        Mutation(
            "public error pages and icons stop counting as UI scope",
            '            re.compile(r"^public/[^/]+\\.(html|png|svg|ico|webmanifest)$"))',
            '            re.compile(r"^NEVER/"))',
            "a public error page is UI scope",
        ),
        Mutation(
            "the PWA manifest is dropped as an API template",
            "                  and (SEEN_ANYWAY.match(p) or not NOT_UI.search(p)))",
            "                  and not NOT_UI.search(p))",
            "the PWA manifest is UI scope although it is JSON",
        ),
        Mutation(
            "a bare https:// counts as a mock-up",
            '        if not re.match(r"^https://[^/\\s]+\\.[^/\\s]+", mock):',
            "        if False:",
            "a bare https:// is not a mock-up",
        ),
        Mutation(
            "any repo file counts as a mock-up",
            '    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):',
            "    elif mock and not (root / mock).is_file():",
            'an arbitrary NON-Markdown repo file outside the folder is not a mock-up',
        ),
        Mutation(
            "a record need not name its issue",
            "    if issue and not ISSUE_REF.match(issue):",
            "    if False:",
            "a record that names no issue is held",
        ),
        Mutation(
            "a README in the records folder is judged as a record",
            '                                             and Path(p).name.lower() != "readme.md")',
            "                                             )",
            "CONTROL: a README in the records folder is not a record",
        ),
        Mutation(
            # #1430
            'a record may name itself as its mock-up again',
            '    elif mock and ((root / mock).resolve() == path.resolve()\n                   or ((root / mock).exists() and (root / mock).samefile(path))):',
            '    elif False:',
            'a record naming itself is held',
        ),
        Mutation(
            # #1430
            'an .svg is not a mock-up file',
            'MOCK_FILE = re.compile(r"\\.(html?|png|jpe?g|webp|pdf|svg)$", re.I)',
            'MOCK_FILE = re.compile(r"\\.(html?|png|jpe?g|webp|pdf)$", re.I)',
            'an .svg mock-up OUTSIDE the records folder is a mock-up file',
        ),
        Mutation(
            # review of PR #1478
            'a record may name another record (or a symlink onto one) as its mock-up',
            '    elif mock and (root / mock).resolve().suffix.lower() == ".md":',
            '    elif False:',
            'a record naming another record is held',
        ),
        # #1479 (after #1478): the remainder #1478 did not cover.
        Mutation(
            'a hard link to the record is not the record',
            '                   or ((root / mock).exists() and (root / mock).samefile(path))):',
            '                   or False):',
            'a record naming itself by another name is held',
        ),
        # #1490: the CommonMark indented-code scanner, one rule per mutation.
        Mutation(
            'a non-breaking space indents the opt-out again',
            'OPT_OUT = re.compile(r"^[ \\t]*(?:[-*+][ \\t]*)?`?mockup-gate:[ \\t]*off`?[ \\t]*$", re.M | re.I)',
            'OPT_OUT = re.compile(r"^\\s*(?:[-*+][ \\t]*)?`?mockup-gate:[ \\t]*off`?[ \\t]*$", re.M | re.I)',
            '#1490: a non-breaking space is not indentation',
        ),
        Mutation(
            'a `+` bullet does not declare',
            'OPT_OUT = re.compile(r"^[ \\t]*(?:[-*+][ \\t]*)?`?mockup-gate:[ \\t]*off`?[ \\t]*$", re.M | re.I)',
            'OPT_OUT = re.compile(r"^[ \\t]*(?:[-*][ \\t]*)?`?mockup-gate:[ \\t]*off`?[ \\t]*$", re.M | re.I)',
            '#1490: CONTROL: a `+` bullet declares',
        ),
        # #1496 review: one mutation per rule the differential fuzz found missing.
        # #1496 round 2: a dropped block keeps its column.
        # #1501: the block scanner, one mutation per rule.
        Mutation(
            'code and HTML lines declare again',
            '    return any(OPT_OUT.match(line) and cls == "text"',
            '    return any(OPT_OUT.match(line) and True',
            '#1490: an indented code block after a blank line is an example',
        ),
        Mutation(
            'tabs count one column',
            '        s = raw.expandtabs(4)',
            '        s = raw.replace("\\t", " ")',
            '#1490: a tab indents to column 4',
        ),
        # Quote continuation was first recorded as an equivalent mutant; PR #1512's review disproved it.
        Mutation(
            'a quote marker no longer continues a quote',
            '                if n <= 3 and j < len(s) and s[j] == ">":',
            '                if False:',
            "#1512 B4: quote continuation keeps the quote's paragraph open",
        ),
        Mutation(
            'a blank-started item survives a second blank line',
            '                if c.blank_start and not c.has_content:\n                    break',
            '                if False:\n                    break',
            '#1490: R3: an item that starts blank',
        ),
        Mutation(
            'any line continues an open item',
            '            if n >= c.width:\n                pos += c.width',
            '            if True:\n                pos += c.width',
            '#1490: a list ends at a top-level paragraph',
        ),
        Mutation(
            'a fence closes on any fence line',
            '                if m and m.group(1)[0] == leaf[1] and len(m.group(1)) >= leaf[2]:',
            '                if m:',
            '#1501: a ~~~ line does not close a backtick fence',
        ),
        Mutation(
            'a closing fence indented 4+ closes',
            '                m = re.match(r"(`{3,}|~{3,})[ \\t]*$", s[j:]) if n <= 3 else None',
            '                m = re.match(r"(`{3,}|~{3,})[ \\t]*$", s[j:])',
            '#1490: R5: a closing fence indented further',
        ),
        Mutation(
            'a fence outlives its container',
            '            leaf = None                       # the container closed: the fence ends with it',
            '            pass',
            '#1501 CONTROL: a fence in a quote ends when a blank line closes the quote',
        ),
        Mutation(
            'an HTML block never ends at a blank line',
            '                if end is None and rest_blank:',
            '                if False:',
            '#1490: CONTROL: after an HTML block and a blank line',
        ),
        Mutation(
            'a lazy line is never lazy',
            '        if not all_matched and leaf == "para" and not rest_blank and _lazy(s, pos, stack[matched:]):',
            '        if False:',
            '#1501 CONTROL: a lazy `    - e` under `   - d` is paragraph text',
        ),
        Mutation(
            'a line 4+ past the matched containers may open a block',
            '    if n >= 4:\n        return True\n    return not _starts_block',
            '    return not _starts_block',
            '#1501 CONTROL: a lazy `    - e` under `   - d` is paragraph text',
        ),
        Mutation(
            'indented code may interrupt a paragraph',
            '                if leaf == "para":\n                    cls = "text"',
            '                if False:\n                    cls = "text"',
            '#1490: CONTROL: 4 spaces directly under a paragraph continue it',
        ),
        Mutation(
            'a quote never opens',
            '                stack.append("quote")',
            '                pass',
            '#1501: a quote holding a list, then an indented <pre>',
        ),
        Mutation(
            'a fence never opens',
            '            f = FENCE.match(s, j)',
            '            f = None',
            '#1501: a fence indented one space still opens',
        ),
        Mutation(
            "a backtick fence's info string may hold a backtick",
            'FENCE = re.compile(r"(`{3,})(?!.*`)|(~{3,})")',
            'FENCE = re.compile(r"(`{3,})|(~{3,})")',
            'code span',
        ),
        Mutation(
            'a lone tag interrupts a paragraph',
            '    if not in_para and HTML7.match(s, at):',
            '    if HTML7.match(s, at):',
            '#1501: a lone tag cannot interrupt a paragraph',
        ),
        Mutation(
            'a type-1 block ends only at its own closing tag',
            'HTML_START = [',
            'HTML_START = [\n    (re.compile(r"<pre(?:[ \\t>]|$)", re.I), re.compile(r"</pre>", re.I)),',
            '#1501: a type-1 block ends at ANY of the four closing tags',
        ),
        Mutation(
            'a setext underline is a paragraph line',
            '            if leaf == "para" and SETEXT.match(s, j) and not refs_only:',
            '            if False:',
            '#1490: R2: a setext `===` underline',
        ),
        Mutation(
            'a thematic break is a paragraph',
            '            if last >= 0 and s[last] in "*-_" and THEMATIC.match(s, j):',
            '            if False:',
            '#1501: an indented line after a thematic break is code',
        ),
        Mutation(
            '5+ columns after a marker are the content column',
            '            width = (after - pos) + (1 if empty or spaces >= 5 else spaces)',
            '            width = (after - pos) + (1 if empty else spaces)',
            '#1490: an item opening with 5+ columns',
        ),
        Mutation(
            'any item may interrupt a paragraph',
            '                if leaf == "para" and (empty or (m.group(2) is not None and int(m.group(2)) != 1)):',
            '                if False:',
            '#1501: `2.` cannot interrupt a paragraph',
        ),
        Mutation(
            'an ATX heading is a paragraph',
            '            if ATX.match(s, j):\n                leaf, cls = None, "text"',
            '            if False:\n                leaf, cls = None, "text"',
            '#1490: an indented line after a heading is code',
        ),
        Mutation(
            'blankness is judged on the whole line again',
            '        blank = rest_blank',
            '        blank = not s.strip()',
            '#1501: a quote line holding only `>` and spaces',
        ),
        # #1512 review: commonmark.js's blank, digit and whitespace sets.
        Mutation(
            "blankness uses Python's strip() again",
            '        last = len(s.rstrip(BLANK_CHARS)) - 1',
            '        last = len(s.rstrip()) - 1',
            '#1512 B1: a no-break-space line is not blank',
        ),
        Mutation(
            'an ordered marker accepts any Unicode digit',
            'MARKER = re.compile(r"([-+*]|([0-9]{1,9})[.)])(?=[ \\t]|$)")',
            'MARKER = re.compile(r"([-+*]|(\\d{1,9})[.)])(?=[ \\t]|$)")',
            '#1512 B2: an Arabic-Indic digit opens no list item',
        ),
        Mutation(
            'a lone tag may be followed only by space and tab',
            'HTML7 = re.compile(r"(?:<[A-Za-z][A-Za-z0-9-]*" + ATTR + r"*[ \\t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \\t]*>)" + JS_WS + r"*$")',
            'HTML7 = re.compile(r"(?:<[A-Za-z][A-Za-z0-9-]*" + ATTR + r"*[ \\t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \\t]*>)[ \\t]*$")',
            '#1512 B3: a lone tag followed by a no-break space',
        ),
        Mutation(
            'a reference-definition paragraph takes a setext underline',
            '            if leaf == "para" and SETEXT.match(s, j) and not refs_only:',
            '            if leaf == "para" and SETEXT.match(s, j):',
            '#1512 S1: a paragraph of only reference definitions',
        ),
        Mutation(
            'a lazy line keeps a definitions-only paragraph definitions-only',
            '            refs_only = refs_only and bool(REFDEF.match(s, ind(pos)[1]))\n            out.append("text")',
            '            out.append("text")',
            '#1512 R1: a lazy line ends a definitions-only paragraph',
        ),
        Mutation(
            'an HTML comment never ends',
            '    (re.compile(r"<!--"), "-->"),',
            '    (re.compile(r"<!--"), "never-ends"),',
            '#1512 CONTROL: a comment ends at `-->` on a later line',
        ),
        Mutation(
            'an end condition is never met on the start line',
            '                if h is not None and _ends(h, s, j + 1):',
            '                if False:',
            '#1512 CONTROL: a comment that closes on its own line ends there',
        ),
    ),
)
