"""Mutation guard: derive_tenancy_cop. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1361. The cop is DERIVED from rails-8's multi-tenancy.md §7 and committed beside its checker,
    # because a runtime read would cross a plugin boundary. This guard covers the derivation; the
    # drift gate covers the artifact.
    name="derive_tenancy_cop",
    subject="scripts/derive_tenancy_cop.py",
    selftest="scripts/derive_tenancy_cop.py",
    needs=("skills/rails-8/references/multi-tenancy.md",),
    mutations=(
        Mutation(
            "a hollow cop fence (no lookup list) derives as if it were the cop",
            '    if "RESTRICT_ON_SEND" not in cop or "def on_send" not in cop:',
            "    if False:",
            "a cop fence with no lookup list refuses",
        ),
        Mutation(
            "a duplicated anchor picks one silently instead of refusing",
            "    if len(hits) != 1:",
            "    if not hits:",
            "an duplicated anchor refuses",
        ),
    ),
)
