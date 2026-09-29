"""Mutation guard: check_shipped_erb_forms. Declared here, run by scripts/mutation_check.py (#1383).

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
            "            for rule, line, what in scan(str(f), m.group(1)):",
            "            for rule, line, what in []:",
            "a raw <form> in a shipped ERB block is a finding",
        ),
        Mutation(
            "the primitive marker excuses every block in the file",
            "            if PRIMITIVE in m.group(1):",
            "            if PRIMITIVE in text:",
            "the marker excuses its own block only",
        ),
        Mutation(
            "a declared primitive is refused like any block",
            "            if PRIMITIVE in m.group(1):\n                continue\n",
            "",
            "CONTROL: a block declared a primitive is excused",
        ),
        Mutation(
            "the finding's line is the block's, not the doc's",
            "                out.append(f\"{f.relative_to(root)}:{start + line}",
            "                out.append(f\"{f.relative_to(root)}:{line}",
            "...with the doc's own line number",
        ),
    ),
)
