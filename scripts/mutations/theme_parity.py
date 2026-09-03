"""Mutation guard: theme_parity. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #105 criterion 3. The XOR is the whole rule: a page equally bad in BOTH themes belongs to
# rendered_conformance, and reporting it here would double-count. Mutating it to `or` is the
# difference between a parity check and a second contrast checker.
GUARD = Guard(
    name="theme_parity",
    subject="plugins/qa-flow/scripts/theme_parity.py",
    selftest="plugins/qa-flow/scripts/theme_parity.py",
    mutations=(
        # #830. Two shipped plugins used different sRGB breakpoints; design-flow had 2.2's.
        Mutation(
            "the luminance breakpoint regresses to WCAG 2.0's 0.03928",
            "SRGB_LINEAR_BREAKPOINT = 0.04045",
            "SRGB_LINEAR_BREAKPOINT = 0.03928",
            "luminance uses the WCAG 2.2 breakpoint",
        ),

        Mutation(
            # The dangerous direction for a de-duplicator: a shorter report that hid a defect.
            "grouping drops `detail`, so two different defects merge under one rule name",
            "        refs = out.setdefault((f.rule, f.detail), [])",
            "        refs = out.setdefault((f.rule, f.rule), [])",
            "same rule, different detail stays two groups",
        ),
        Mutation(
            "a repeated ref is counted twice, inflating the occurrence claim",
            "        if f.ref not in refs:",
            "        if True:",
            "a repeated ref is counted once",
        ),
        Mutation(
            "parity becomes a second contrast checker, firing on both-themes-bad",
            '                if (l_ratio >= AA_NORMAL) != (d_ratio >= AA_NORMAL):',
            '                if (l_ratio >= AA_NORMAL) or not (d_ratio >= AA_NORMAL):',
            "bad in BOTH themes is not a parity finding",
        ),
        Mutation(
            "a frozen colour fires even when the surface never moved",
            '            if lc == dc and lbg != dbg:',
            '            if lc == dc:',
            "a frozen colour on an unmoved surface is silent",
        ),
        Mutation(
            "a translucent colour gets a fabricated ratio instead of being refused",
            '    if a[3] < 1.0 or b[3] < 1.0:',
            '    if False:',
            "a translucent foreground yields no ratio",
        ),
    ),
)
