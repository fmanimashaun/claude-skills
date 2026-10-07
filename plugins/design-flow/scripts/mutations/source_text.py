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
            'a quoted attribute value is not opaque, so a `<!--` inside one is read as markup',
            '        elif source[j] in "\\"\'" and source[i:j].rstrip().endswith("="):',
            '        elif False:',
            '`<!--` inside a quoted attribute value starts no comment',
        ),
        Mutation(
            'a <script>/<style> body is read as markup',
            '            elif name in RAW_TEXT:',
            '            elif False:',
            '`<!--` inside a <style> body starts no comment',
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
            '                if html:\n                    blank(c, i)\n        elif _ascii_alpha(nxt):',
            '                if False:\n                    blank(c, i)\n        elif _ascii_alpha(nxt):',
            "`</` followed by a non-letter is a bogus comment",
        ),
        Mutation(
            "the bogus rule applies to Ruby too, so a regex lookbehind `(?<![` blanks a model's code",
            '                if html:\n                    blank(c, i)\n        elif nxt == "/":',
            '                if True:\n                    blank(c, i)\n        elif nxt == "/":',
            "a `(?<!` lookbehind is not a bogus comment",
        ),
        # #1651 review R1 and R2.
        Mutation(
            "Unicode letters start a tag again, so `<é` crashes on the ASCII tag-name pattern",
            '    return ch.isascii() and ch.isalpha()',
            '    return ch.isalpha()',
            "a non-ASCII letter after `<` does not crash",
        ),
        Mutation(
            "ERB outside a quote inside a tag is not skipped, so its `>` ends the tag",
            '        if source.startswith("<%", j):\n            j = _skip_erb(source, j)\n        elif source[j] in',
            '        if False:\n            j = _skip_erb(source, j)\n        elif source[j] in',
            "ERB in a tag OUTSIDE any quote is opaque",
        ),
        Mutation(
            "<textarea> is no longer a raw-text element",
            'RAW_TEXT = ("script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes")',
            'RAW_TEXT = ("script", "style", "title", "xmp", "iframe", "noembed", "noframes")',
            "inside a <textarea> body starts no comment",
        ),
        Mutation(
            'the close tag needs no terminator, so `</scripts>` ends a <script>',
            '                close = re.compile(rf"</{name}[\\s/>]", re.I).search(source, end)',
            '                close = re.compile(rf"</{name}", re.I).search(source, end)',
            '`</styles>` does not close a <style>',
        ),
        Mutation(
            'a single quote no longer opens an attribute value',
            '        elif source[j] in "\\"\'" and source[i:j].rstrip().endswith("="):',
            '        elif source[j] in "\\"" and source[i:j].rstrip().endswith("="):',
            'a single-quoted attribute value is opaque too',
        ),
        Mutation(
            'DOCTYPE is matched case-sensitively, so `<!doctype` is blanked as a bogus comment',
            '            elif source[c + 2:c + 9].upper() == "DOCTYPE":',
            '            elif source[c + 2:c + 9] == "DOCTYPE":',
            '`<!doctype` is a doctype in any case',
        ),
        Mutation(
            'a trailing `/` closes a raw-text element again, so `<script/>` is read as markup',
            '            if name == "script":',
            '            if source[c:end].rstrip(">").endswith("/"):\n                pass\n            elif name == "script":',
            '`<script/>` still opens a raw-text body',
        ),
        Mutation(
            '`<![CDATA[` is blanked as a bogus comment',
            '            if source.startswith("<![CDATA[", c):\n                i = _section_end(source, c, "]]>")',
            '            if False:\n                i = _section_end(source, c, "]]>")',
            '`<![CDATA[` is left live',
        ),
        Mutation(
            'whitespace no longer terminates a close tag, so `</script >` does not close the script',
            '                close = re.compile(rf"</{name}[\\s/>]", re.I).search(source, end)',
            '                close = re.compile(rf"</{name}[/>]", re.I).search(source, end)',
            '`</style >` (a space before `>`) closes the style',
        ),
        Mutation(
            "the bogus rule is on by default, so a caller that forgets html= blanks Ruby",
            'def blank_html_comments(source: str, *, html: bool = False) -> str:',
            'def blank_html_comments(source: str, *, html: bool = True) -> str:',
            "blank_html_comments keeps the bogus rule off by default",
        ),
        Mutation(
            "a lone `</` at the end of input is blanked as a bogus comment",
            '            if _ascii_alpha(after) or after == ">" or after == "":',
            '            if _ascii_alpha(after) or after == ">":',
            "a lone `</` at the end of input is left as it is",
        ),
        Mutation(
            'a doctype is blanked as a bogus comment',
            '            elif source[c + 2:c + 9].upper() == "DOCTYPE":',
            '            elif False:',
            'is not a comment and is left as it is',
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
        # #1653: N1 to N3.
        Mutation(
            'N1: a nested `<script>` in an escaped run no longer double-escapes, so the inner `</script>` ends the body',
            '            state = "double"',
            '            state = "escaped"',
            'N1: a script double-escaped by `<!-- <script>` ends only at its real `</script>`',
        ),
        Mutation(
            'N2: CDATA ends at the first `>` again',
            '                i = _section_end(source, c, "]]>")',
            '                i = _bogus_end(source, c)',
            'N2: CDATA runs to `]]>`',
        ),
        Mutation(
            'N2: a processing instruction is plain text again, so a `<!--` inside it is a comment',
            '        elif nxt == "?":\n            i = _section_end(source, c, "?>")',
            '        elif False:\n            i = _section_end(source, c, "?>")',
            'N2: a processing instruction runs to `?>`',
        ),
        Mutation(
            'N3: a quote anywhere in a tag opens a value again',
            '        elif source[j] in "\\"\'" and source[i:j].rstrip().endswith("="):',
            '        elif source[j] in "\\"\'":',
            'N3: a quote outside a value (not after `=`) opens nothing',
        ),
        Mutation(
            'the script close needs no terminator, so `</scripts>` ends a <script>',
            'SCRIPT_TOKEN = re.compile(r"<!--|-->|</?script[\\s/>]", re.I)',
            'SCRIPT_TOKEN = re.compile(r"<!--|-->|</?script", re.I)',
            '`</scripts>` does not close a <script>',
        ),
        Mutation(
            'whitespace no longer terminates a script close, so `</script >` does not close the script',
            'SCRIPT_TOKEN = re.compile(r"<!--|-->|</?script[\\s/>]", re.I)',
            'SCRIPT_TOKEN = re.compile(r"<!--|-->|</?script[/>]", re.I)',
            '`</script >` (a space before `>`) closes the script',
        ),
    ),
)
