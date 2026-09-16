"""Mutation guard: check_structural_grid (#976). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_structural_grid",
    subject="scripts/check_structural_grid.py",
    selftest="scripts/check_structural_grid.py",   # --selftest lives in the module itself
    # The selftest builds its fixtures in memory and in a tempdir, so it needs no repo file staged.
    mutations=(
        Mutation(
            "the divisibility test is switched off, so a 236px rail passes",
            "        if px % GRID_PX:",
            "        if False:",
            "236px rail",
        ),
        Mutation(
            "a clamp() in the structural block is accepted as structure",
            "        if px is None:",
            "        if False:",
            "clamp in the block",
        ),
        Mutation(
            "a reference may use a structural token the block never declares — the #750 class",
            "        for name in sorted(uses_in(outside, prefixes) - set(tokens)):",
            "        for name in ():",
            "undeclared --shell-toolbar",
        ),
        Mutation(
            "a block that declares nothing reads as clean",
            "    if not tokens:",
            "    if False:",
            "empty block",
        ),
        # The silence direction: inverted, the rule fires on a correct block.
        Mutation(
            "the divisibility test inverts and refuses every on-grid value",
            "        if px % GRID_PX:",
            "        if not px % GRID_PX:",
            "clean block is silent",
        ),
        # The unit conversion: rem read as px makes 4rem = 4px, off-grid, so a correct block fails —
        # and 0.5rem would pass as 8. Both directions wrong; the clean fixture catches it.
        Mutation(
            "rem stops being converted to px",
            '    return number * 16 if unit == "rem" else number',
            "    return number",
            "clean block is silent",
        ),
    ),
)
