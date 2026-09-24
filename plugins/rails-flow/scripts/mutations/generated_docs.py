"""Mutation guard: generated_docs. Declared here, run by scripts/mutation_check.py (#1230)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="generated_docs",
    subject="scripts/generated_docs.py",
    selftest="scripts/generated_docs.py",
    mutations=(
        Mutation(
            # With no policy file every branch must enforce: the opt-in is what makes it safe to ship.
            "no policy file relaxes a feature branch",
            "    if policy is None:\n        return True, f\"no {POLICY_FILE}: every branch enforces\"\n",
            "    if policy is None:\n        return False, \"relaxed\"\n",
            "no policy enforces on a feature branch (today's behaviour)",
        ),
        Mutation(
            "an unknown branch is relaxed instead of enforced",
            "    if not branch:\n        return True,",
            "    if not branch:\n        return False,",
            "decide('') enforces=True",
        ),
        Mutation(
            "the guard stops looking at the diff",
            "    touched = sorted(p for p in paths if p.startswith(tuple(policy[\"generated\"])))\n",
            "    touched = []\n",
            "guard: a feature branch changing graph.json FAILS",
        ),
        Mutation(
            "an unresolvable base reads as clean",
            "    if paths is None:\n        return 2,",
            "    if paths is None:\n        return 0,",
            "guard: an unresolvable base is exit 2, never clean",
        ),
    ),
)
