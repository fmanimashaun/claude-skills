"""Mutation guard: check_python_floor. Declared here, run by scripts/mutation_check.py (#1597).

Each mutation lets a shipped script that is a SyntaxError on the stock macOS python3 (3.9) read as clean.
The rule that compiles under a real 3.9 is not mutated: it runs only where a 3.9 exists, and a guard that
passes on one machine and survives on another is worse than none.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_python_floor",
    subject="scripts/check_python_floor.py",
    selftest="scripts/check_python_floor.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "the grammar floor is 3.12, so newer syntax parses",
            "FLOOR = (3, 9)",
            "FLOOR = (3, 12)",
            "a match statement is refused on the 3.9 grammar",
        ),
        Mutation(
            "a backslash in an f-string expression is allowed",
            '        if "\\\\" in expr:',
            "        if False:",
            "a backslash in an f-string expression is refused",
        ),
        Mutation(
            "the f-string's own quote reused in its expression is allowed",
            "        elif quote and quote in expr:",
            "        elif False:",
            "the f-string's own quote reused in its expression is refused",
        ),
        Mutation(
            "an empty tree reads clean",
            "    if count == 0:",
            "    if False:",
            "no plugins at all is UNUSABLE, never clean",
        ),
        Mutation(
            "the python3 -c blocks inside hook shells are never read",
            '    for path in sorted((root / "plugins").glob("*/hooks/scripts/**/*.sh")):',
            '    for path in sorted((root / "plugins").glob("*/hooks/scripts/**/*.nothing")):',
            "a bad python3 -c block inside a hook shell is found",
        ),
        Mutation(
            "a SyntaxError from the 3.9 grammar is swallowed",
            "        return [(err.lineno or 0, f\"SyntaxError on the {FLOOR[0]}.{FLOOR[1]} grammar: {err.msg}\")]",
            "        return []",
            "a bad script in the tree exits 1",
        ),
    ),
)
