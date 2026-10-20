"""Mutation guard: rails_assumptions. Declared here, run by scripts/mutation_check.py (#2164)."""
from mutation_types import Guard, Mutation  # noqa: F401

# Every mutation here lets an UNDECIDED or STALE row read as a decided one, which is what the inventory exists to refuse.
GUARD = Guard(
    name="rails_assumptions",
    subject="scripts/rails_assumptions.py",
    selftest="scripts/rails_assumptions.py",   # --selftest lives in the module itself
    needs=("scripts/hermetic_git.py", "plugins/rails-flow/scripts/fixture_git.py"),   # imported by the module: git for the real read and for the temp-repo fixtures
    mutations=(
        Mutation(
            "the scan is narrowed to one flow, so a Rails reference in the other three is never read",
            '    SCOPE = tuple(f"plugins/{flow}" for flow in FLOWS)'.lstrip(),
            'SCOPE = ("plugins/rails-flow",)',
            "every flow is scanned",
        ),
        Mutation(
            "a committed page that differs from a clean build passes --check",
            "            elif blob != built:",
            "            elif False:",
            "--check on a stale committed page is a finding",
        ),
        Mutation(
            "a page that was never committed passes --check",
            "            if blob is None:",
            "            if False:",
            "--check on a page that was built but never committed is a finding",
        ),
        Mutation(
            "a file with hits and no rule is no longer reported",
            "            findings.append(f\"{path}: {len(row['lines'])} line(s) name Rails and no rule in {POLICY} decides this file\")",
            "            pass",
            "an unresolved file is a finding",
        ),
        Mutation(
            "a neutral file may gain a Rails line without a new decision",
            '            if recorded != len(row["lines"]):',
            "            if False:",
            "a neutral file that gains a Rails line is a finding",
        ),
        Mutation(
            "the tool patterns go back to lowercase only",
            '"RuboCop", re.I),',
            '"RuboCop"),',
            "RuboCop in any case is a tool hit",
        ),
        Mutation(
            "the gem pattern goes back to lowercase only",
            '"a named Ruby gem", re.I),',
            '"a named Ruby gem"),',
            "Brakeman, Capybara and Bundler in any case are hits",
        ),
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
