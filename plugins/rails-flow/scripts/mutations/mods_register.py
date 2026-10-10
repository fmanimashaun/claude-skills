"""Mutation guard: mods_register. Declared here, run by scripts/mutation_check.py (#1547)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1547. hooks.json names ONE module, hooks/register.js, and Claude Code refuses two hooks on the same event
# with no matcher. Calling a mod twice, or none, are the two ways this file goes wrong while every mod's own
# test still passes. Each mod is staged beside it because register.js imports it. A third way (#1557): a mod's
# call is dropped, which no mod's own test can see, so tests/register.unit.mjs finds every mod by its export
# and fails when one of them is not registered.
GUARD = Guard(
    name="mods_register",
    subject="hooks/register.js",
    selftest="scripts/check_mods.py",
    selftest_args=("register",),
    needs=("tests/register.unit.mjs", "hooks/context-nudge.mjs", "hooks/lane-band.js", "hooks/budget-guard.mjs", "hooks/hooks.json"),
    mutations=(
        Mutation(
            "a mod is registered twice, so its events are registered twice",
            "  contextNudge(on, options)\n",
            "  contextNudge(on, options)\n  contextNudge(on, options)\n",
            "registered twice",
        ),
        Mutation(
            "the lane band is registered twice, so its events are registered twice",
            "  laneBand(on, options)\n",
            "  laneBand(on, options)\n  laneBand(on, options)\n",
            "registered twice",
        ),
        # #1557: a mod dropped from register.js leaves every mod's own test green and the mod dead.
        Mutation(
            "the context-nudge call is dropped, so that mod is never registered",
            "  contextNudge(on, options)\n  laneBand(on, options)\n",
            "  laneBand(on, options)\n",
            "context-nudge.mjs: its hook",
        ),
        Mutation(
            "the lane band call is dropped, so that mod is never registered",
            "  contextNudge(on, options)\n  laneBand(on, options)\n",
            "  contextNudge(on, options)\n",
            "lane-band.js: its hook",
        ),
        Mutation(
            "register.js throws while registering, which the test must report by file name",
            "  contextNudge(on, options)\n  laneBand(on, options)\n",
            "  throw new Error('boom')\n",
            "register.js: register() threw",
        ),
        Mutation(
            "no mod is registered at all",
            "  contextNudge(on, options)\n  laneBand(on, options)\n  budgetGuard(on, options)\n",
            "  void contextNudge\n  void laneBand\n  void budgetGuard\n",
            "registered no hook at all",
        ),
    ),
)
