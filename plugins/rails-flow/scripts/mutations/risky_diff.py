"""Mutation guard: risky_diff (#1819). Declared here, run by scripts/mutation_check.py.

Each mutation lets a risky diff through without the adversarial pass, makes a stale or hand-waved record count, swallows a BLOCKED
verdict, or holds a harmless change. The named fixture in `risky_diff.py --selftest` must go red for each.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="risky_diff",
    subject="scripts/risky_diff.py",
    selftest="scripts/risky_diff.py",   # --selftest lives in the module itself
    needs=("scripts/fixture_git.py", "scripts/classify_door.py"),   # its git goes through fixture_git (#1588); it imports classify_door's diff
    mutations=(
        Mutation(
            "a spec or test file counts as risky, so every spec that parses JSON holds the PR",
            '        if path.startswith(("spec/", "test/")) or "/spec/" in path or "/test/" in path:',
            "        if False:",
            "CONTROL: a spec that parses JSON is not risky",
        ),
        Mutation(
            "a policy file is not on the access surface",
            '    ("access", re.compile(r"^app/policies/|',
            '    ("access", re.compile(r"^app/NEVER/|',
            "a policy is risky",
        ),
        Mutation(
            "an initializer named author_names is read as an auth initializer (the substring, not the word)",
            "(?:[^/]*[_-])?(?:auth|authentication|devise",
            "[^/]*(?:auth|authentication|devise",
            "author_names",
        ),
        Mutation(
            "strong parameters are not a parsing surface",
            r"|\bNokogiri::|\bparams\.(?:require|permit)\b",
            r"|\bNokogiri::",
            "strong parameters are risky",
        ),
        Mutation(
            "a risky diff with no --record is not asked for the pass",
            "    if record is None or head is None:\n        return 1,",
            "    if record is None or head is None:\n        return 0,",
            "a risky diff with no --record asks for the pass",
        ),
        Mutation(
            "a record for another commit is accepted, so a pass on an old head stands in for this one",
            "    if not any(head.startswith(h) for h in heads):",
            "    if False:",
            "a record for another commit is stale",
        ),
        Mutation(
            "a record with no Head line is accepted",
            "    if not heads:\n",
            "    if False:\n",
            "a record with no Head line is refused",
        ),
        Mutation(
            "a BLOCKED verdict exits 0, so the finding never reaches the human",
            "        return 3, [f\"RISKY",
            "        return 0, [f\"RISKY",
            "a BLOCKED record is a finding for a human",
        ),
        Mutation(
            "the FIRST verdict decides, so a later BLOCKED is not seen",
            "    return verdicts[-1], f",
            "    return verdicts[0], f",
            "the LAST verdict decides",
        ),
        Mutation(
            "a verdict quoted inside a sentence counts as the verdict line",
            'VERDICT = re.compile(r"^VERDICT:\\s*(CLEAN|BLOCKED)\\s*$")',
            'VERDICT = re.compile(r".*VERDICT:\\s*(CLEAN|BLOCKED)\\s*$")',
            "a verdict quoted inside a sentence",
        ),
    ),
)
