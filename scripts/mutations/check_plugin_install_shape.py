"""Mutation guard: check_plugin_install_shape. Declared here, run by scripts/mutation_check.py (#2182).

The mutations that matter make the gate VACUOUS: a root source passing (the pre-#2182 rails-stack, which
installed the whole repository), `.claude/` inside a plugin passing, or the file ceiling never firing.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_plugin_install_shape",
    subject="scripts/check_plugin_install_shape.py",
    selftest="scripts/check_plugin_install_shape.py",
    mutations=(
        Mutation(
            "a repository-root source is no longer a finding",
            '        if rel in ("", "."):\n',
            '        if False:\n',
            "a root source is a finding (the pre-#2182 rails-stack)",
        ),
        Mutation(
            "a .claude/ directory inside a plugin is no longer a finding",
            "        if claude:\n",
            "        if False:\n",
            ".claude/ inside a plugin is a finding",
        ),
        Mutation(
            "the file ceiling never fires",
            "        if len(inside) > CEILING:\n",
            "        if False:\n",
            "too many files is a finding",
        ),
        Mutation(
            "a prefix match counts a sibling directory as inside",
            '        inside = [f for f in files if f.startswith(rel + "/")]\n',
            "        inside = [f for f in files if f.startswith(rel)]\n",
            "a sibling directory sharing a prefix is not inside",
        ),
    ),
)
