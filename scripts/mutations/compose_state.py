"""Mutation guard: compose_state. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="compose_state",
    subject="plugins/rails-flow/scripts/compose_state.py",
    selftest="plugins/rails-flow/scripts/compose_state.py",   # --selftest lives in the module
    # No `needs`: the fixtures are literals and a tempdir. Both mutations target a decision the
    # driver previously made by accident -- what order the backlog is in, and what it refuses to
    # start -- because "first element wins" IS a prioritisation policy, just an unstated one.
    mutations=(
        Mutation(
            "the actionability filter goes, so blocked work is picked and burns attempts",
            "        if blocked:",
            "        if False:",
            "blocked issues excluded",
        ),
        Mutation(
            # Ordering was previously whatever the caller typed. Unsorting it puts an
            # unprioritised issue first, which is how forgetting a label promotes work.
            "the stated order goes, so priority stops deciding what is next",
            '    actionable.sort(key=lambda e: (priority_rank(set(e["labels"])), e["number"]))',
            "    pass",
            "priority then age",
        ),
    ),
)
