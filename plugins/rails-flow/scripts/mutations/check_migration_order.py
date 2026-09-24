"""Mutation guard: check_migration_order. Declared here, run by scripts/mutation_check.py (#1248)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_migration_order",
    subject="scripts/check_migration_order.py",
    selftest="scripts/check_migration_order.py",
    deps=("scripts/session_coordinator.py",),
    mutations=(
        Mutation(
            "the findings are computed and then ignored",
            "    if not findings:\n",
            "    if True:\n",
            "a branch migration below dev's newer schema version FAILS, even after merging dev",
        ),
        Mutation(
            "an unreadable base reads as clean",
            "        return 2, [f\"cannot read db/schema.rb",
            "        return 0, [f\"cannot read db/schema.rb",
            "an unreadable base is exit 2, never clean",
        ),
        Mutation(
            "a project without a schema is checked instead of n/a",
            "        return 3, [\"not applicable",
            "        return 0, [\"not applicable",
            "a project with no db/schema.rb is n/a",
        ),
    ),
)
