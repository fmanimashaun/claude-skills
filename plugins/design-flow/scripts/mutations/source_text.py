"""Mutation guard: source_text. Run by scripts/mutation_check.py (#1128)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="source_text",
    subject="scripts/source_text.py",
    selftest="scripts/source_text.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # The reported form: a component explaining why the wrapper was REMOVED was reported
            # for having it, so the fix's own documentation re-tripped the gate.
            "ERB comments are left in the source",
            "    source = ERB_COMMENT.sub(_blank, source)",
            "    source = source",
            "an ERB comment's text is gone",
        ),
        Mutation(
            "HTML comments are left in the source",
            "    source = blank_html_comments(source, html=html)",
            "    source = source",
            "an HTML comment's text is gone",
        ),
        # CodeQL py/bad-tag-filter on #1451: the spec's other endings.
        Mutation(
            "`--!>` no longer ends a comment",
            'HTML_COMMENT = re.compile(r"<!--(?:-?>|[\\s\\S]*?(?:--!?>|\\Z))")',
            'HTML_COMMENT = re.compile(r"<!--(?:-?>|[\\s\\S]*?(?:-->|\\Z))")',
            "...and the markup after it is live, not swallowed up to a later `-->`",
        ),
        Mutation(
            "an unterminated comment is left live",
            'HTML_COMMENT = re.compile(r"<!--(?:-?>|[\\s\\S]*?(?:--!?>|\\Z))")',
            'HTML_COMMENT = re.compile(r"<!--(?:-?>|[\\s\\S]*?(?:--!?>))")',
            "an unterminated comment runs to the end of input",
        ),
        Mutation(
            "the abrupt `<!-->` / `<!--->` forms swallow what follows",
            'HTML_COMMENT = re.compile(r"<!--(?:-?>|[\\s\\S]*?(?:--!?>|\\Z))")',
            'HTML_COMMENT = re.compile(r"<!--(?:[\\s\\S]*?(?:--!?>|\\Z))")',
            "`<!-->` and `<!--->` are complete empty comments",
        ),
        # #1466: a comment starts only in the data state, and the two bogus openers are comments.
        Mutation(
            "context-blind again: `<!--` anywhere starts a comment, hiding the markup after a quoted one",
            '    out, n, i, last = [], len(source), 0, 0',
            '    return HTML_COMMENT.sub(_blank, source)\n    out, n, i, last = [], len(source), 0, 0',
            "`<!--` inside a quoted attribute value starts no comment",
        ),
        Mutation(
            "a quoted attribute value is not opaque, so a `<!--` inside one is read as markup",
            '        elif source[j] in "\\"\'":',
            '        elif False:',
            "`<!--` inside a quoted attribute value starts no comment",
        ),
        Mutation(
            "a <script>/<style> body is read as markup",
            '            if name in RAW_TEXT and not source[c:end].rstrip(">").endswith("/"):',
            '            if False:',
            "`<!--` inside a <script> body starts no comment",
        ),
        Mutation(
            "ERB in the data state is read as markup",
            '        if source.startswith("<%", c):\n            i = _skip_erb(source, c)',
            '        if False:\n            i = _skip_erb(source, c)',
            "`<!--` inside ERB starts no comment",
        ),
        Mutation(
            "ERB inside a quoted value is not skipped, so its quotes end the value early",
            '                j = _skip_erb(source, j) if source.startswith("<%", j) else j + 1',
            '                j = j + 1',
            "ERB with quotes inside a quoted value does not end the value early",
        ),
        Mutation(
            "`<!x` is left live instead of being blanked as a bogus comment",
            '                if html:\n                    blank(c, i)\n        elif nxt == "/":',
            '                if False:\n                    blank(c, i)\n        elif nxt == "/":',
            "`<!` not followed by `--` is a bogus comment",
        ),
        Mutation(
            "`</ x` is left live instead of being blanked as a bogus comment",
            '                if html:\n                    blank(c, i)\n        elif nxt.isalpha():',
            '                if False:\n                    blank(c, i)\n        elif nxt.isalpha():',
            "`</` followed by a non-letter is a bogus comment",
        ),
        Mutation(
            "the bogus rule applies to Ruby too, so a regex lookbehind `(?<![` blanks a model's code",
            '                if html:\n                    blank(c, i)\n        elif nxt == "/":',
            '                if True:\n                    blank(c, i)\n        elif nxt == "/":',
            "a `(?<!` lookbehind is not a bogus comment",
        ),
        Mutation(
            "a doctype is blanked as a bogus comment",
            '            if source[c + 2:c + 9].upper() == "DOCTYPE" or source.startswith("<![CDATA[", c):',
            '            if False:',
            "is not a comment and is left as it is",
        ),
        Mutation(
            "Ruby whole-line comments are left in the source",
            "    return RUBY_LINE_COMMENT.sub(lambda m: m.group(1), source)",
            "    return source",
            "a Ruby whole-line comment's text is gone",
        ),
        Mutation(
            # Two callers report `file:line`. Deleting a comment instead of blanking it in place
            # trades a false positive for a wrong citation, which is harder to notice.
            "a multi-line comment is deleted rather than blanked, shifting every later line",
            '    return "\\n" * match.group(0).count("\\n")',
            '    return ""',
            "a multi-line comment keeps its newlines",
        ),
        Mutation(
            # THE CARVE-OUT, and it is load-bearing: `#` is legal inside a string and begins
            # `#{}` interpolation, so stripping from the first `#` on a line eats real code --
            # including the `class: "..."` values these gates exist to read.
            "a trailing `#` is treated as a comment, so a `#` inside a string is eaten",
            r'RUBY_LINE_COMMENT = re.compile(r"^([ \t]*)#.*$", re.M)',
            r'RUBY_LINE_COMMENT = re.compile(r"^([ \t]*).*?#.*$", re.M)',
            "a `#` inside a string is not a comment",
        ),
    ),
)
