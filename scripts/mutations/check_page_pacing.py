"""Mutation guard: check_page_pacing. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_page_pacing",
    subject="scripts/check_page_pacing.py",
    selftest="scripts/check_page_pacing.py",   # --selftest lives in the module itself
    # The LAY-017 fixture (#476) re-derives its measurement from the REAL band table, so the
    # doc has to be staged. Without it the baseline selftest fails in the tempdir and every
    # mutation below is INERT -- which run_baseline reported rather than passing silently.
    needs=("skills/design-system/references/page-anatomies.md",
           "skills/design-system/references/coverage.md",
           "skills/design-system/references/foundations-tokens.md",
           # #639. It now imports the band parser from the shipped plugin rather than
           # keeping a second copy, so the plugin module and its own import are needs.
           # Third time this rule has bitten in one session: an added import is an
           # added need, and without it every mutation dies on ModuleNotFoundError.
           "plugins/design-flow/scripts/compose_brief.py",
           "plugins/design-flow/scripts/doctrine_path.py"),
    mutations=(
        Mutation(
            "the measured row count stops being compared, so a stale 14 passes",
            "    if measured != pacing.identical_rows:",
            "    if False:",
            "a wrong identical-row count is reported",
        ),
        Mutation(
            "the band range stops bounding the table that prints it",
            "    if not pacing.band_min <= len(pacing.bands) <= pacing.band_max:",
            "    if False:",
            "a band count outside the stated range is reported",
        ),
        Mutation(
            "a band may compose from a row that does not exist",
            "        if band.composed not in names:",
            "        if False:",
            "a band naming no coverage row is reported",
        ),
        Mutation(
            "the tone vocabulary stops being joined to the token file",
            "        if band.tone not in roles:",
            "        if False:",
            "a tone naming no role is reported",
        ),
        Mutation(
            "tone may stop alternating, so bands lose their edges",
            "        if prev.tone == nxt.tone:",
            "        if False:",
            "two consecutive bands on one tone are reported",
        ),
        Mutation(
            "consecutive bands may share a shape — the fourteen-stacks defect itself",
            "        if prev.shape == nxt.shape:",
            "        if False:",
            "two consecutive bands of the same shape are reported",
        ),
        # The corpus guard. With headers and separators counted as components, the join is over
        # rows that are not rows, and a name could match a table heading.
        Mutation(
            "the coverage walk stops skipping headers, so the join runs over non-rows",
            '        if cells[1] in {"Kind", "---"}:',
            "        if False:",
            "the coverage walk finds both tables' component rows",
        ),
        # The measurement guard. Counting every marketing row instead of the largest identical
        # group answers a different question, and it drifts in the direction that looks right.
        Mutation(
            "the identical-string measurement widens to every marketing row",
            "    return max(counts.values())",
            "    return len(marketing)",
            "the identical-Build-from count is measured over marketing rows only",
        ),
        Mutation(
            "a marked block with no bands parses instead of raising",
            "    if not bands:",
            "    if False:",
            "a marked block with no band rows parsed instead of raising",
        ),
        # The silence direction: inverted, the rule fires on the shipped sequence.
        Mutation(
            "the tone rule inverts and demands two consecutive bands share a tone",
            "        if prev.tone == nxt.tone:",
            "        if prev.tone != nxt.tone:",
            "a correct section is silent",
        ),
    ),
)
