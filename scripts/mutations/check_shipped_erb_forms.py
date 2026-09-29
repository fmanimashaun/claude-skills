"""Mutation guard: check_shipped_erb_forms. Declared here, run by scripts/mutation_check.py (#1383, #1443).

Each mutation lets our own doctrine ship an ERB block the simple-form-only gate we ship would refuse.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_shipped_erb_forms",
    subject="scripts/check_shipped_erb_forms.py",
    selftest="scripts/check_shipped_erb_forms.py",
    needs=("plugins/rails-flow/scripts/check_simple_form_only.py",),
    mutations=(
        Mutation(
            "shipped blocks are never scanned",
            "            for rule, line, what in scan(str(f), body):",
            "            for rule, line, what in []:",
            "a raw <form> in a shipped ERB block is a finding",
        ),
        # #1443: the marker excuses what it NAMES, not the block.
        Mutation(
            "the primitive marker excuses its whole block again",
            "                if named and not named.startswith(\"--\") and what.lower().startswith(named.lower()):",
            "                if marker:",
            "the marker excuses only what it names: a later raw <select> is a finding",
        ),
        Mutation(
            "a named primitive construct is refused like any other",
            "                if named and not named.startswith(\"--\") and what.lower().startswith(named.lower()):\n                    continue\n",
            "",
            "CONTROL: the construct a primitive marker names is excused",
        ),
        Mutation(
            "a marker that names nothing is silently accepted",
            "            if marker and (not named or named.startswith(\"--\")):",
            "            if False:",
            "a marker that names nothing excuses nothing",
        ),
        # #1443: every fence, indented or not.
        Mutation(
            "indented fences are skipped again",
            'BLOCK = re.compile(r"^([ \\t]*)```erb[^\\n]*\\n(.*?)^\\1```", re.S | re.M)',
            'BLOCK = re.compile(r"^()```erb[^\\n]*\\n(.*?)^\\1```", re.S | re.M)',
            "an INDENTED fence is read",
        ),
        Mutation(
            "an indented fence closes at any later fence",
            'BLOCK = re.compile(r"^([ \\t]*)```erb[^\\n]*\\n(.*?)^\\1```", re.S | re.M)',
            'BLOCK = re.compile(r"^([ \\t]*)```erb[^\\n]*\\n(.*?)^[ \\t]*```", re.S | re.M)',
            "a fence line at ANOTHER indent does not close an indented block",
        ),
        Mutation(
            "the finding's line is the block's, not the doc's",
            "                out.append(f\"{f.relative_to(root)}:{start + line}",
            "                out.append(f\"{f.relative_to(root)}:{line}",
            "...with the doc's own line number",
        ),
    ),
)
