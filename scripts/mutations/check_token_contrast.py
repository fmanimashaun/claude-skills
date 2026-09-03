"""Mutation guard: check_token_contrast. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #129. Two subjects, one feature: the CANONICAL contrast instrument in scripts/, and the
# SHIPPED one inside design-flow that a user runs on their own pack. They carry the same maths
# for a stated reason (a plugin cannot import from maintainer tooling), so the parity fixture
# that compares them is itself mutated — a parity check that stopped comparing would let the
# two drift in exactly the silence it exists to prevent.
GUARD = Guard(
    name="check_token_contrast",
    subject="scripts/check_token_contrast.py",
    selftest="scripts/check_token_contrast.py",
    # It reads the doctrine file and every shipped pack, and its parity fixtures import the
    # shipped module. Without these the mutant dies on a missing file and every mutation reads
    # as "caught" by a traceback rather than by the fixture named below.
    needs=("skills/design-system/references/foundations-tokens.md",
           "plugins/design-flow/brands/fidara/theme.css",
           "plugins/design-flow/brands/_template/theme.css",
           "plugins/design-flow/scripts/palette_candidates.py",
           "plugins/design-flow/scripts/brand_pack_lint.py"),
    mutations=(
        # #775. The two-tier split. WCAG has two thresholds; using one for both is taste
        # wearing a count, and using the WRONG one fails a shipped pack for a rule no clause
        # states.
        Mutation(
            "the two tiers collapse, so a focus ring is held to the text threshold",
            "AA_LARGE = 3.0",
            "AA_LARGE = 4.5",
            "the two tiers are actually different numbers",
        ),
        Mutation(
            # The `floors` fixtures read PAIRS directly, so they prove the tier is DECLARED and
            # not that anything USES it -- this survived every one of them until the assertion
            # moved onto measure()'s own output. Proving the table is not proving the reader.
            "measure() ignores the per-pair floor and judges everything at 4.5",
            "floor = pair[4] if len(pair) > 4 else AA_NORMAL",
            "floor = AA_NORMAL",
            "measure() gives a focus-ring row the 3:1 floor",
        ),
        Mutation(
            # A pack predating a role, or a template with placeholder refs, must SKIP -- and a
            # skip must never be counted as a pass, which is the whole three-state doctrine.
            "an undeclared role reports a perfect ratio instead of skipping",
            '            rows.append((mode, label, fg, bg, "", "", 0.0, 0.0))',
            '            rows.append((mode, label, fg, bg, "#000", "#fff", 21.0, AA_NORMAL))',
            "an undeclared role is skipped, not raised",
        ),
        Mutation(
            "the dark half of the ink enumeration is dropped, leaving only the half that passed",
            '    ("success ink on the page",       "--success-ink",        "--background", "dark"),',
            '    ("xx ink on the page",       "--success-ink",        "--background", "light"),',
            "every pair is measured in light AND dark",
        ),
        Mutation(
            "the gate narrows back to the doctrine file, so the packs go unmeasured (#129)",
            "    return [repo / TOKENS.relative_to(REPO), *packs]",
            "    return [repo / TOKENS.relative_to(REPO)]",
            "every shipped brand pack is measured",
        ),
        Mutation(
            "an empty pack glob becomes a clean pass instead of a hard error",
            "    if not packs:\n        raise Unparseable(",
            "    if False:\n        raise Unparseable(",
            "a tree with no brand pack enumerated sources",
        ),
        Mutation(
            "the sRGB breakpoint reverts to WCAG 2.0's 0.03928",
            "SRGB_LINEAR_BREAKPOINT = 0.04045",
            "SRGB_LINEAR_BREAKPOINT = 0.03928",
            "the sRGB linearisation breakpoint is WCAG 2.2's 0.04045",
        ),
        Mutation(
            "the parity check with the shipped implementation stops comparing",
            "    return max(abs(left(a, b) - right(a, b)) for a in probes for b in probes)",
            "    return 0.0",
            "the parity comparison can actually detect a disagreement",
        ),
        Mutation(
            "the two token parsers may disagree without anyone noticing",
            "        if ours is None or ours.upper() != value.upper():",
            "        if False:",
            "the parser comparison can actually detect a disagreement",
        ),
        Mutation(
            "the muted-text pair is dropped again (it was the missing one, at 2.71:1)",
            '    ("muted text on a muted surface", "--muted-foreground",   "--muted",      "light"),\n',
            "",
            "the muted-text pair is measured in both modes",
        ),
    ),
)
