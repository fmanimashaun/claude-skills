"""Mutation guard: check_frontmatter. Declared here, run by scripts/mutation_check.py (#1344).

Each mutation lets a frontmatter that YAML refuses, or reads differently, pass as valid.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_frontmatter",
    subject="scripts/check_frontmatter.py",
    selftest="scripts/check_frontmatter.py",   # --selftest lives in the module itself
    mutations=(
        # #1343: an agent that inherits every tool passes again.
        Mutation(
            "an agent with no tools declaration passes",
            '    if "tools" not in f and "disallowedTools" not in f:',
            "    if False:",
            "an agent with no tools or disallowedTools is a finding",
        ),
        Mutation(
            "disallowedTools no longer counts as a declaration",
            '    if "tools" not in f and "disallowedTools" not in f:',
            '    if "tools" not in f:',
            "CONTROL: disallowedTools alone is a declaration",
        ),
        Mutation(
            "only maintainer agents are checked, never the shipped ones",
            '        if path.parent.name == "agents" and path.parts[-3] != ".claude":',
            '        if path.parent.name == "agents" and path.parts[-3] == ".claude":',
            "a shipped agent with no tools declaration is named",
        ),
        Mutation(
            "an unquoted ': ' passes",
            '        if ": " in value:',
            "        if False:",
            "an unquoted ': ' in a plain scalar is a finding",
        ),
        Mutation(
            "an unquoted ' #' passes, so a value is silently truncated",
            '        elif " #" in value:',
            "        elif False:",
            "an unquoted ' #' in a plain scalar is a finding",
        ),
        Mutation(
            "quoted values are read as plain, so every quoted colon is a false finding",
            '        if not m or m.group("value").startswith(OPENERS):',
            "        if not m:",
            "CONTROL: the same text double-quoted is valid",
        ),
        Mutation(
            "an unterminated frontmatter reads as having none",
            '        return [(1, "frontmatter opened with --- but never closed")] if text.startswith("---") else []',
            "        return []",
            "an unterminated frontmatter is a finding",
        ),
        Mutation(
            "no files reads as clean",
            '        return 2, ["UNUSABLE: no frontmatter files found to check"]',
            '        return 0, ["nothing"]',
            "no files at all is UNUSABLE, never clean",
        ),
    ),
)
