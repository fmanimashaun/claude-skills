"""Mutation guard: rails_assumptions. Declared here, run by scripts/mutation_check.py (#2164)."""
from mutation_types import Guard, Mutation  # noqa: F401

# Every mutation here lets an UNDECIDED or STALE row read as a decided one, which is what the inventory exists to refuse.
GUARD = Guard(
    name="rails_assumptions",
    subject="scripts/rails_assumptions.py",
    selftest="scripts/rails_assumptions.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a rule left behind after its file moved is accepted",
            "        if not used[index]:",
            "        if False:",
            "a rule matching nothing is a finding",
        ),
        Mutation(
            "a decision outside the four is accepted",
            '        if rule.get("decision") not in DECISIONS:',
            "        if False:",
            "a decision outside the four is a finding",
        ),
        Mutation(
            "a rails-stack rule may name a move nobody declared",
            "            if move not in moves:",
            "            if False:",
            "a rails-stack rule with an undeclared move is a finding",
        ),
        Mutation(
            "a move with no issue filed is accepted",
            '        if not isinstance(move.get("issue"), int):',
            "        if False:",
            "a move with no issue is a finding",
        ),
        Mutation(
            "a mutation guard stops following its script, so it is decided on its own path",
            '    if kind == "mutation":',
            "    if False:",
            "a mutation guard follows its script",
        ),
        Mutation(
            "a setup-flow hit line in no section, or two, is accepted",
            "        if len(owners) != 1:",
            "        if False:",
            "a hit line in no section is a finding",
        ),
        Mutation(
            "a binary file is scanned as text",
            '        if b"\\0" in raw[:8000]:',
            "        if False:",
            "a binary file is skipped",
        ),
    ),
)
