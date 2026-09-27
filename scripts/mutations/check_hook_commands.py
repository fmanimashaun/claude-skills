"""Mutation guard: check_hook_commands. Declared here, run by scripts/mutation_check.py (#1334).

Each mutation lets a hook command that splits on a spaced install path read as safe.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_hook_commands",
    subject="scripts/check_hook_commands.py",
    selftest="scripts/check_hook_commands.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "quoted segments are not removed, so every placeholder reads as bare",
            '    return PLACEHOLDER in QUOTED.sub("", command)',
            "    return PLACEHOLDER in command",
            "CONTROL: a quoted placeholder is not flagged",
        ),
        Mutation(
            "the static unquoted check never fires",
            "            if unquoted(command):",
            "            if False:",
            "an unquoted command is refused statically",
        ),
        Mutation(
            "the spaced-path expansion is never consulted",
            "            if not ok:",
            "            if False:",
            "...and the spaced-path expansion catches it on its own",
        ),
        Mutation(
            "the install path has no space, so nothing can split",
            '        spaced = Path(td) / "Application Support" / plugin.name',
            '        spaced = Path(td) / "ApplicationSupport" / plugin.name',
            "...and the spaced-path expansion catches it on its own",
        ),
        Mutation(
            "a missing script is accepted as long as it is one word",
            "        ok = bool(words) and Path(words[0]).is_file()",
            "        ok = len(words) == 1",
            "a quoted path to a script that does not exist is refused",
        ),
        Mutation(
            "no hooks.json reads as clean",
            '        return 2, ["UNUSABLE: no plugins/*/hooks/hooks.json to check"]',
            '        return 0, ["nothing to check"]',
            "no hooks.json anywhere is UNUSABLE, never clean",
        ),
    ),
)
