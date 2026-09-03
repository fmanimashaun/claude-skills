"""Mutation guard: classify_boot_failure. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="classify_boot_failure",
    subject="plugins/qa-flow/scripts/classify_boot_failure.py",
    selftest="plugins/qa-flow/scripts/classify_boot_failure.py",
    mutations=(
        Mutation(
            "category order stops mattering, so incidental noise can outvote the real cause",
            "    for name, patterns, action in CATEGORIES:",
            "    for name, patterns, action in reversed(CATEGORIES):",
            "the specific cause wins over incidental noise",
        ),
        Mutation(
            "everything classifies as an application error",
            "    for name, patterns, action in CATEGORIES:",
            "    for name, patterns, action in []:",
            "EADDRINUSE",
        ),
    ),
)
