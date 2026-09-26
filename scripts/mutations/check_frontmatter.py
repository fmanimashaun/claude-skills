"""Mutation guard: check_frontmatter. Declared here, run by scripts/mutation_check.py (#1344).

Each mutation lets a frontmatter that YAML refuses, or reads differently, pass as valid.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_frontmatter",
    subject="scripts/check_frontmatter.py",
    selftest="scripts/check_frontmatter.py",   # --selftest lives in the module itself
    mutations=(
        # #1335: the user-only declaration drifts in either direction.
        Mutation(
            "a declared user-only command may drop its flag",
            "            if rel in USER_ONLY and not flagged:",
            "            if False:",
            "a declared user-only command without the flag is a finding",
        ),
        Mutation(
            "any command may set the flag without being declared",
            "            elif flagged and rel not in USER_ONLY:",
            "            elif False:",
            "a user-only flag on an undeclared command is a finding",
        ),
        # #1345: an agent told to use a skill it cannot load passes again.
        Mutation(
            "an agent that cannot load the skill it names passes",
            '    if named and not can_invoke and "skills" not in f:',
            "    if False:",
            "an agent told to consult a skill it cannot load is a finding",
        ),
        Mutation(
            "path-style mentions (`skills/<name>/...`) are not recognised",
            '                         r"|skills/(" + "|".join(map(re.escape, OUR_SKILLS)) + r")/", re.I)',
            '                         r"|skills/(NEVER)/", re.I)',
            "...including a path-style mention",
        ),
        Mutation(
            "a Skill in disallowedTools still counts as able to load",
            '    can_invoke = ("tools" not in f and not blocked) or "Skill" in tools',
            '    can_invoke = "tools" not in f or "Skill" in tools',
            "...and a Skill in disallowedTools blocks it",
        ),
        Mutation(
            "a skills: preload is ignored, so a preloaded agent is a false finding",
            '    if named and not can_invoke and "skills" not in f:',
            "    if named and not can_invoke:",
            "CONTROL: a skills: preload can load it",
        ),
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
