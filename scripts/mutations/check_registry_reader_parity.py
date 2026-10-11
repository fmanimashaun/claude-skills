"""Mutation guard: check_registry_reader_parity. Declared here, run by scripts/mutation_check.py (#1857)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_registry_reader_parity",
    subject="scripts/check_registry_reader_parity.py",
    selftest="scripts/check_registry_reader_parity.py",   # --selftest lives in the module itself
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "the comparison looks only at the problems, so two readers that return different entries read as the same",
            "        if a != b:",
            "        if a[1] != b[1]:",
            "a reader that disagrees is not reported on every sample",
        ),
        Mutation(
            "the comparison looks only at the entries, so a difference in the problems is missed",
            "        if a != b:",
            "        if a[0] != b[0]:",
            "a difference only in the problems is not reported",
        ),
        Mutation(
            "the comparison never reports a difference",
            "        if a != b:",
            "        if False:",
            "a reader that disagrees is not reported on every sample",
        ),
    ),
)
