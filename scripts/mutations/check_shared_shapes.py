"""Mutation guard: check_shared_shapes. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #360. Every mutation here makes a STALE NUMBER read as a fresh one, which is the only thing
# this checker can fail on. Note what is deliberately absent: no mutation asks whether a copy
# of a shape is justified, because the quality pass is advisory and a gate on taste would
# contradict the doctrine this guards.
GUARD = Guard(
    name="check_shared_shapes",
    subject="scripts/check_shared_shapes.py",
    selftest="scripts/check_shared_shapes.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "the count comparison stops comparing, so a stale number passes",
            "        if want_files != len(hits):",
            "        if False:",
            "a wrong count in the table is DRIFT",
        ),
        # A `continue` rather than `if False:`: disabling the membership test would index a
        # missing key and die with a KeyError, and a mutation that crashes before a labelled
        # assertion is caught by a traceback rather than by the fixture written for it.
        Mutation(
            "a measured shape with no row in the table goes unreported",
            '        if shape.label not in rows:\n'
            '            findings.append(\n'
            '                f"{shape.label}: measured in {len(hits)} file(s) and has NO row in'
            ' the table. A "\n'
            '                f"count nobody reads is not doctrine.")\n'
            "            continue\n",
            "        if shape.label not in rows:\n            continue\n",
            "a shape with no row is reported",
        ),
        Mutation(
            "the other direction of the join goes, so prose nothing measures passes",
            "    for label in rows:",
            "    for label in []:",
            "a table row nothing measures is reported",
        ),
        Mutation(
            "a pattern that matches nothing is accepted, so a rotted regex reads as a pass",
            "        if not hits:",
            "        if False:",
            "a pattern that matches nothing is reported",
        ),
        Mutation(
            "an empty marked table parses instead of raising",
            "    if not rows:",
            "    if False:",
            "an empty marked table parsed instead of raising",
        ),
        # The corpus guard. With no roots every count is 0, every comparison is vacuous, and a
        # gate over zero files reports exactly like a gate over a clean repo.
        Mutation(
            "the measured roots go empty, so every count is taken over no files",
            'ROOTS = ("plugins", "scripts")',
            "ROOTS = ()",
            "the source walk finds the corpus files",
        ),
        # #398. `reach` is a second, independent claim per row: how many copies share one
        # install root, which is the ceiling on what extracting the shape could remove. The
        # file count can be right while it is wrong, so it needs its own mutation.
        Mutation(
            "the reach comparison stops comparing, so a stale ceiling passes",
            "        if want_reach != got_reach:",
            "        if False:",
            "a wrong reach in the table is DRIFT",
        ),
        # The grouping, not the comparison. A `unit()` that answers the same thing for every
        # path makes reach == files everywhere: each row stays internally consistent and the
        # column silently stops meaning "one install root".
        Mutation(
            "every path groups into one install root, so reach collapses into the file count",
            '    if parts[0] == "plugins" and len(parts) > 1:',
            "    if False:",
            "every declared shape is measured at its known count and reach in the corpus",
        ),
        Mutation(
            "a plugin directory the manifest never installs stops being reported",
            "    return sorted(u for u in seen if u.startswith(\"plugins/\") and u not in roots)",
            "    return []",
            "a copy under an undeclared plugin directory is reported",
        ),
        # Both directions of the manifest read. Returning an empty set instead of raising
        # would make every measured plugin undeclared -- a rule that fires on everything is a
        # rule that gets switched off, which is the same defect as one that never fires.
        Mutation(
            "an unparseable manifest yields no roots instead of refusing to guess",
            "        raise Unreadable(f\"{MANIFEST}: not readable as JSON ({exc}), so no install root is known \"\n"
            "                         \"and `reach` would be grouping by a boundary nothing confirms\") from exc",
            "        return set()",
            "an unparseable manifest returned instead of raising",
        ),
    ),
)
