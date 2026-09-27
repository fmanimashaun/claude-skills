"""Mutation guard: classify_door. Declared here, run by scripts/mutation_check.py (#1338).

Each mutation lets an irreversible change merge into dev with no human, or holds a reversible one.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="classify_door",
    subject="scripts/classify_door.py",
    selftest="scripts/classify_door.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "untracked files are invisible again, so a brand-new destructive migration is two-way",
            '    for rel in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():',
            "    for rel in []:",
            "remove_column is one-way",
        ),
        Mutation(
            "the word boundary goes, so change_column_default is read as change_column",
            'change_column|"',
            'change_column|change_column_default|"',
            "CONTROL: change_column_default is two-way",
        ),
        Mutation(
            "policy changes are not access changes",
            're.compile(r"^app/policies/"),',
            're.compile(r"^app/NEVER/"),',
            "a policy change is one-way",
        ),
        Mutation(
            "a removed route is not noticed",
            "            gone = [l.strip() for l in removed if ROUTE_LINE.match(l)]",
            "            gone = []",
            "a removed route is one-way",
        ),
        Mutation(
            "added routes count as removals",
            "            gone = [l.strip() for l in removed if ROUTE_LINE.match(l)]",
            "            gone = [l.strip() for l in removed + added if ROUTE_LINE.match(l)]",
            "CONTROL: an added route is two-way",
        ),
        Mutation(
            "outbound calls in specs count, holding every PR that stubs HTTP",
            '        if path.endswith(".rb") and not path.startswith(("spec/", "test/")):',
            '        if path.endswith(".rb"):',
            "CONTROL: an HTTP client in a spec is two-way",
        ),
        Mutation(
            "a new outside call is not noticed",
            "            if any(OUTBOUND.search(l) for l in added):",
            "            if False:",
            "a new outside HTTP call is one-way",
        ),
        Mutation(
            "an unresolvable base reads as an empty diff",
            '    _git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}")',
            "    return {}",
            "an unresolvable base is UNUSABLE, never two-way",
        ),
    ),
)
