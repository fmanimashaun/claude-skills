"""Mutation guard: check_toolchain_mutations. Run by scripts/mutation_check.py (#1109).

Lives HERE, not in the plugin, because its subject reasons about where guards are discovered
across every plugin -- exactly the cross-plugin shape that stays in the marketplace.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_toolchain_mutations",
    subject="plugins/rails-flow/scripts/check_toolchain_mutations.py",
    selftest="plugins/rails-flow/scripts/check_toolchain_mutations.py",
    mutations=(
        Mutation(
            # MUTATE THE SUBJECT, NOT THE SELFTEST. A first version neutered an assertion inside
            # the selftest, which makes the selftest PASS by construction -- so it survived, and
            # the harness said so. `_`-prefixed files are package plumbing; counting them as
            # guards would report a number nobody can run.
            "package plumbing is counted as a shipped guard",
            '            if not path.name.startswith("_"):',
            "            if True:",
            "a leading-underscore file is not a guard",
        ),
        Mutation(
            # Discovery is this script's whole job; if it stops finding the plugins that ship
            # guards, it reports "nothing to run" and the project believes it.
            "plugins carrying shipped guards stop being found",
            '    return sorted(p.parent.parent for p in own.parent.glob("*/scripts/mutations"))',
            "    return []",
            "plugins carrying shipped guards are found",
        ),
    ),
)
