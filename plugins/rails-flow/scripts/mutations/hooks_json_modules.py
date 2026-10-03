"""Mutation guard: hooks_json_modules. Declared here, run by scripts/mutation_check.py (#1557)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1557. hooks.json takes ONE `modules` path, and the whole of tests/register.unit.mjs assumes it is
# ./register.js. The guard mutates hooks.json itself: the file the check is about, which `mods_register`
# (it mutates register.js) cannot reach. Each mod is staged because register.unit.mjs imports them all.
GUARD = Guard(
    name="hooks_json_modules",
    subject="hooks/hooks.json",
    selftest="scripts/check_mods.py",
    selftest_args=("register",),
    needs=(
        "tests/register.unit.mjs",
        "hooks/register.js",
        "hooks/context-nudge.mjs",
        "hooks/lane-band.js",
    ),
    mutations=(
        Mutation(
            "a second module path is added, so two modules would register events",
            '  "modules": ["./register.js"],\n',
            '  "modules": ["./register.js", "./lane-band.js"],\n',
            'hooks.json "modules" is',
        ),
        Mutation(
            "a mod is named directly, bypassing the aggregator",
            '  "modules": ["./register.js"],\n',
            '  "modules": ["./context-nudge.mjs"],\n',
            'hooks.json "modules" is',
        ),
        Mutation(
            "the modules entry is removed, so no mod loads at all",
            '  "modules": ["./register.js"],\n',
            "",
            'hooks.json "modules" is',
        ),
    ),
)
