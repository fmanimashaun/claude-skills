"""Mutation guard: findings. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="findings",
    subject="scripts/findings.py",
    selftest="scripts/findings.py",
    mutations=(
        Mutation(
            # Dependency edges must outrank severity, or a fix is ordered before the thing it
            # depends on and the "ordered" list cannot actually be followed.
            "edges stop constraining order, so a fix is scheduled before its prerequisite",
            "    if after not in successors[before]:",
            "    if False:",
            "an edge outranks severity",
        ),
        # #1689: a list or object where an id belongs is refused at load, naming the field, not left to crash.
        Mutation(
            "an id-shaped field holding a list is let through, so the command dies with a TypeError",
            '            if isinstance(record.get(field), (list, dict)):',
            "            if False:",
            "a list id is UNUSABLE (2) for validate, not a TypeError",
        ),
        Mutation(
            "a list inside `blocks` is let through, so the command dies with a TypeError",
            "                if isinstance(target, (list, dict)):",
            "                if False:",
            "a list inside blocks is UNUSABLE (2) for validate, not a TypeError",
        ),
    ),
)
