"""Mutation guard: check_always_on_cost. Declared here, run by scripts/mutation_check.py (#866). A ratchet that cannot fail on growth,
or that counts what the listing does not hold, is a number nobody can act on (#1881)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_always_on_cost",
    subject="scripts/check_always_on_cost.py",
    selftest="scripts/check_always_on_cost.py",
    mutations=(
        Mutation(
            "growth past the baseline passes",
            "        if chars > was:",
            "        if False:",
            "gate: one character of growth fails",
        ),
        Mutation(
            "a plugin with no baseline passes silently",
            "        if name not in recorded:\n            findings.append(",
            "        if name not in recorded:\n            continue\n            findings.append(",
            "gate: a plugin with no baseline fails",
        ),
        Mutation(
            "a disable-model-invocation command is still counted",
            "    if fm.get(\"disable-model-invocation\", \"\").lower() == \"true\":\n        return 0\n",
            "",
            "measure: disable-model-invocation: true is not in context",
        ),
        Mutation(
            "the 1,536-character listing cap is ignored",
            ")[:LISTING_CAP]",
            ")",
            "measure: the listing truncates at 1,536 characters",
        ),
        Mutation(
            "when_to_use is not counted",
            "(\" \" + fm[\"when_to_use\"] if fm.get(\"when_to_use\") else \"\")",
            "\"\"",
            "measure: a folded description and when_to_use are both counted",
        ),
    ),
)
