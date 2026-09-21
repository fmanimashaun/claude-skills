"""Mutation guard: walkthrough_plan (#993). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="walkthrough_plan",
    subject="scripts/walkthrough_plan.py",
    selftest="scripts/walkthrough_plan.py",   # --selftest lives in the module
    # It reads the config through the one reader; without it the staged tempdir fails at import.
    needs=("scripts/qa_config.py",),
    mutations=(
        Mutation(
            "an unknown sign-in recipe is accepted, so the walker invents the steps",
            "            if chosen not in RECIPES:",
            "            if False:",
            "a recipe the plugin cannot drive",
        ),
        Mutation(
            "a journey document that does not exist is accepted",
            "        if not (root / j).is_file():",
            "        if False:",
            "a journey file that does not exist",
        ),
        Mutation(
            "the three-band rule is switched off, so two desktop widths pass as three widths",
            '        if viewports and band not in bands:',
            "        if False:",
            "two desktop widths and no phone",
        ),
        Mutation(
            "the compact edge moves to 1023, so 820 reads as compact and a phone is never required",
            "COMPACT_MAX, EXPANDED_MIN = 639, 1024",
            "COMPACT_MAX, EXPANDED_MIN = 1023, 1024",
            # 820 then reads as compact, so the whole block loses its medium band and is refused.
            "a whole block yields a plan",
        ),
        Mutation(
            "a plan is produced despite findings",
            "    if findings:\n        return None, findings\n    return {",
            "    if False:\n        return None, findings\n    return {",
            "a plan was produced despite findings",
        ),
        Mutation(
            "an absent block reads as an empty walk instead of a refusal",
            "    if not block:",
            "    if False:",
            "no block",
        ),
    ),
)
