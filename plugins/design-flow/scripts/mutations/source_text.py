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
            "    source = HTML_COMMENT.sub(_blank, source)",
            "    source = source",
            "an HTML comment's text is gone",
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
