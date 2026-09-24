"""Mutation guard: check_unauthenticated_writes. Declared here, run by scripts/mutation_check.py (#1300).

The mutations that matter make the gate VACUOUS (nothing counts as public, or everything counts as
limited) or turn it against the wrong routes (the graph's controller-wide tag trusted over the code).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_unauthenticated_writes",
    subject="scripts/check_unauthenticated_writes.py",
    selftest="scripts/check_unauthenticated_writes.py",
    mutations=(
        Mutation(
            "a wrapped %i[ ] list is read as its first line only",
            '        while (stmt.count("[") > stmt.count("]") or stmt.rstrip().endswith(",")) and j + 1 < len(lines):',
            "        while False:",
            "a %i[ ] list wrapped onto the next line is read whole",
        ),
        Mutation(
            "only: is ignored, so one limited action covers the whole controller",
            "        if only is not None:\n            if action in only:\n                return True",
            "        if only is not None:\n            return True",
            "...and not magic_link",
        ),
        Mutation(
            "publicness is taken from nothing, so no route is ever public",
            '        if not covers(statements(src, "allow_unauthenticated_access"), action):\n            continue',
            "        continue",
            "the unlimited public writes are findings",
        ),
        Mutation(
            "the graph's controller-wide tag is trusted, so every write in a public controller is public",
            '        if not covers(statements(src, "allow_unauthenticated_access"), action):\n            continue',
            '        if "public" not in n.get("tags", []):\n            continue',
            "a write that is not public (destroy, outside only:) is not a finding",
        ),
        Mutation(
            "an exemption without a reason is accepted",
            "        if not route or not reason:",
            "        if not route:",
            "an exemption without a reason is a finding",
        ),
        Mutation(
            "a missing graph reads as clean",
            "        return 2, [f\"UNUSABLE: {exc}\"]",
            "        return 0, [f\"UNUSABLE: {exc}\"]",
            "no graph: UNUSABLE (exit 2), never clean",
        ),
        Mutation(
            "the null_store warning is never raised",
            "    if uses_rate_limit and test_env.is_file() and re.search(",
            "    if False and re.search(",
            "null_store with rate_limit is a WARNING on a clean result",
        ),
    ),
)
