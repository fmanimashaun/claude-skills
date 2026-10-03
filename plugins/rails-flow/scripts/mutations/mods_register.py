"""Mutation guard: mods_register. Declared here, run by scripts/mutation_check.py (#1547)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1547. hooks.json names ONE module, hooks/register.js, and Claude Code refuses two hooks on the same event
# with no matcher. Calling a mod twice, or none, are the two ways this file goes wrong while every mod's own
# test still passes. Each mod is staged beside it because register.js imports it.
GUARD = Guard(
    name="mods_register",
    subject="hooks/register.js",
    selftest="scripts/check_mods.py",
    selftest_args=("register",),
    needs=("tests/register.unit.mjs", "hooks/context-nudge.mjs", "hooks/lane-band.js"),
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
        Mutation(
            "no mod is registered at all",
            "  contextNudge(on, options)\n  laneBand(on, options)\n",
            "  void contextNudge\n  void laneBand\n",
            "registered no hook at all",
        ),
    ),
)
