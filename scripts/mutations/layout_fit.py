"""Mutation guard: layout_fit. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #953. This layer exists because every boundary assertion passes on content crushed INSIDE the
# viewport. Its two most dangerous directions are opposite: a rule that stops firing (and reports a
# clean page that hides 82% of a table) and an exemption that stops exempting (and reports every
# `.sr-only` span in the app, which is how the layer gets switched off in a week). Both are mutated.
GUARD = Guard(
    name="layout_fit",
    subject="plugins/qa-flow/scripts/layout_fit.py",
    selftest="plugins/qa-flow/scripts/layout_fit.py",
    # The selftest imports the shared config reader AND cross-checks the collector field by field,
    # so both must be staged. Without them the unmutated selftest fails in the tempdir and every
    # mutation below reads as "caught" whether or not it broke anything — which the runner refuses.
    needs=(
        "plugins/qa-flow/scripts/qa_config.py",
        "plugins/qa-flow/scripts/crawl_collector.js",
    ),
    mutations=(
        # ---- the rules must keep firing --------------------------------------------------------
        Mutation(
            "clipped content stops being unreachable, so `overflow: hidden` is silent",
            '        return "clipped-unreachable"',
            "        return None",
            "hidden overflow is unreachable",
        ),
        Mutation(
            "a spill stops being reported, so text overlapping its neighbour passes",
            '    if overflow in SPILLS:\n        return "spilled-content"',
            "    if overflow in SPILLS:\n        return None",
            "visible overflow spills",
        ),
        Mutation(
            # The exact shape of the assertion this layer was written to replace.
            "the scroll-container exemption comes back, blanket, the way it was before",
            '        return None if has_affordance(row) else "scroll-without-affordance"',
            "        return None",
            "auto with no affordance is reported",
        ),
        Mutation(
            "an unrecognised `overflow-x` value falls into silence instead of being reported",
            '    # before and an allowlist that fails open is how a rule stops finding anything.\n'
            '    return "spilled-content"',
            '    # before and an allowlist that fails open is how a rule stops finding anything.\n'
            "    return None",
            "an unknown overflow value is still reported",
        ),

        # ---- the affordance evidence must stay evidence -----------------------------------------
        Mutation(
            "a 0px gutter counts as a scrollbar, so an overlay-scrollbar strip is silent",
            "GUTTER_IS_VISIBLE_PX = 3",
            "GUTTER_IS_VISIBLE_PX = 0",
            "a scrolling strip with no reserved gutter is reported",
        ),
        Mutation(
            "an empty `data-qa-scroll-affordance` silences a finding — a claim with nothing behind it",
            '    return isinstance(declared, str) and declared.strip() != ""',
            "    return isinstance(declared, str)",
            "an empty declared affordance does not silence it",
        ),

        # ---- the visually-hidden exemption must stay narrow -------------------------------------
        Mutation(
            # The state the layer was in on its first real run: four findings, all `.sr-only`.
            "the sr-only exemption goes, so every visually-hidden span is a finding",
            "        if isinstance(size, (int, float)) and size <= VISUALLY_HIDDEN_PX:\n            return True",
            "        if False:\n            return True",
            # NOT the sr-only fixture: that row carries a total clip as well, so the clip branch
            # still exempts it. The size-only variants are the ones this half of the predicate owns.
            "a 1px-wide box alone is visually hidden",
        ),
        Mutation(
            "the exemption widens past hidden text and starts swallowing ordinary boxes",
            "VISUALLY_HIDDEN_PX = 4",
            "VISUALLY_HIDDEN_PX = 400",
            "an ordinary box is still reported",
        ),

        # ---- the threshold ---------------------------------------------------------------------
        Mutation(
            "the threshold goes, so a 1px rounding artefact is reported as a defect",
            "            if ratio < min_hidden:",
            "            if False:",
            "a 1% strip is rounding, not a finding",
        ),

        # ---- and an unmeasured page must never read as a clean one ------------------------------
        Mutation(
            "a probe that threw is treated as `nothing hidden` instead of unverified",
            "        if rows is None:\n            out.unverified.append(route)\n            continue",
            "        if rows is None:\n            rows = []",
            "a null probe is unverified, not clean",
        ),
        Mutation(
            # Measured on a real app: the interaction sweep clicked sign-out and five admin routes
            # were filed under the routes asked for while showing the landing page.
            "a route measured somewhere else stops being reported, so a signed-out crawl reads clean",
            "            out.redirected.append(f\"{route} measured at {landed}\")\n            continue",
            "            pass",
            "a route measured somewhere else is unverified",
        ),
        Mutation(
            "unverified stops failing, so a run that measured nothing exits 0",
            "    return 1 if (result.findings or result.unverified or result.redirected) else 0",
            "    return 1 if result.findings else 0",
            "an unverified route exits 1",
        ),
        Mutation(
            "a row with no measurement is judged as 0% hidden rather than refused",
            '            if not isinstance(ratio, (int, float)):\n'
            '                raise Unusable(f"{route}: {ref} has no numeric hiddenRatio — the collector\'s own "\n'
            '                               "measurement is missing, so nothing here can be judged")',
            "            if not isinstance(ratio, (int, float)):\n                ratio = 0.0",
            "a row with no hiddenRatio is refused",
        ),

        # ---- grouping must not swallow a second defect ------------------------------------------
        Mutation(
            "grouping drops the ref, so every finding on a page merges into one",
            "            key = (rule, ref)",
            "            key = (rule, rule)",
            "two distinct refs are two findings",
        ),
        Mutation(
            "grouping keeps the FIRST ratio rather than the worst, understating the defect",
            '            if float(ratio) > float(bucket["worst"].get("hiddenRatio") or 0):',
            "            if False:",
            "grouping keeps the WORST ratio",
        ),
    ),
)
