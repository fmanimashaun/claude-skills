"""Mutation guard: findings. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="findings",
    subject="plugins/rails-flow/scripts/findings.py",
    selftest="plugins/rails-flow/scripts/findings.py",
    mutations=(
        Mutation(
            # Dependency edges must outrank severity, or a fix is ordered before the thing it
            # depends on and the "ordered" list cannot actually be followed.
            "edges stop constraining order, so a fix is scheduled before its prerequisite",
            "    if after not in successors[before]:",
            "    if False:",
            "an edge outranks severity",
        ),
    ),
)
