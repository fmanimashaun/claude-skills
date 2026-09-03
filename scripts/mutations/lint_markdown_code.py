"""Mutation guard: lint_markdown_code. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="lint_markdown_code",
    subject="scripts/lint_markdown_code.py",
    selftest="scripts/lint_markdown_code_selftest.py",
    mutations=(
        Mutation(
            "the language boundary is dropped, so ```json parses as JavaScript again (#248)",
            r'FENCE = re.compile(r"^[ \t]*```[ \t]*(" + _LANG_ALT + r")\b[^\n]*\n(.*?)^[ \t]*```",',
            r'FENCE = re.compile(r"^[ \t]*```[ \t]*(" + _LANG_ALT + r")[^\n]*\n(.*?)^[ \t]*```",',
            "```json is NOT javascript",
        ),
        Mutation(
            "a stalled interpreter is reported as a syntax error again",
            '        raise InterpreterStalled(f"{cmd[0]} did not answer within 30s") from exc',
            '        return 127, "", f"could not run {cmd[0]}: {exc}"',
            "a stalled interpreter did not raise",
        ),
        Mutation(
            "the ERB block-tag normalisation is removed (20 false positives return)",
            '    code = ERB_BLOCK_TAG.sub(r"<%\\1%>", ERB_RAW_TAG.sub("<%=", code))',
            "    code = ERB_RAW_TAG.sub(\"<%=\", code)",
            "erb: <%= … do %> block tag",
        ),
        Mutation(
            "the unterminated-tag check is removed — ERB will not catch it",
            "    line = _unterminated_erb_tag(code)",
            "    line = None",
            "erb: unterminated tag",
        ),
        Mutation(
            "`<%%` stops being treated as an escaped literal",
            '        if code[i + 2:i + 3] == "%":      # `<%%` — an escaped literal, not a tag',
            "        if False:",
            "erb: `<%%` is an escaped literal, not an unterminated tag",
        ),
        Mutation(
            "elision substitution is dropped, so documentation `...` reads as code",
            "    normalised = substitute(code, lang)",
            "    normalised = code",
            "ruby: (...) argument elision",
        ),
    ),
)
