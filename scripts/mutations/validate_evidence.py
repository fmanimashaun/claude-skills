"""Mutation guard: validate_evidence. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="validate_evidence",
    subject="plugins/qa-flow/scripts/validate_evidence.py",
    selftest="plugins/qa-flow/scripts/validate_evidence_selftest.py",
    # `plugins/qa-flow`: its selftest reads profile/agent files across the plugin.
    needs=("plugins/qa-flow",),
    mutations=(
        Mutation(
            # #578: a conformant app was flagged S1 on EVERY page because the pass looked up
            # `outline` while the ring lived in `box-shadow`. Requiring the method does not
            # verify the diff was done right -- it stops an unmethodical blocking S1 being
            # filed silently, which is the part that cost a morning.
            "a blocking S1 stops needing a method, so a property lookup can cry wolf again",
            '    if counts.get("No Focus Indicator", 0) > 0:',
            "    if False:",
            "keyboard: missing-indicator count with no method recorded",
        ),
        # #424: the modal-CRUD 422 assertion, and the carve-out that lets a valid modal row
        # exist at all. Both directions, because widening the carve-out is how it goes quiet.
        Mutation(
            "the modal-CRUD 422 assertion stops firing",
            '    elif surface == "modal" and exercised:',
            "    elif False:",
            "modal CRUD that navigated instead of re-rendering",
        ),
        Mutation(
            "the 422 carve-out widens past modal rows, so any non-2xx passes",
            '    modal_422 = row.get("Surface", "").lower() == "modal" and row["HTTP"].strip() == "422"',
            "    modal_422 = True",
            "exercised a form on a 500",
        ),
        Mutation(
            "a Pass on a non-2xx/3xx page is accepted (the #106 defect)",
            # Anchor updated by #424: the `elif` became an `if` with the modal-422 carve-out
            # beside it. The stale-anchor rule caught the drift rather than letting this
            # mutation quietly stop mutating anything.
            'if row["HTTP"] and not _http_ok(row["HTTP"]) and not modal_422:',
            "if False:",
            "not the page under test",
        ),
        Mutation(
            "duplicate finding signatures stop being rejected (#118's dedupe)",
            "        if sig in seen:",
            "        if False:",
            "repeated signature",
        ),
        Mutation(
            "runtime severity is trusted instead of recomputed",
            "    elif required == S1 and severity != S1:",
            "    elif False:",
            "downgraded to S2",
        ),
        # #114 -- the sampling guard is the whole profile. Without it a row that walked 3 of
        # 40 elements reads exactly like a clean page, which is the 25-of-72 defect returning.
        Mutation(
            "a keyboard walk may sample instead of covering the inventory (#114)",
            '        if accounted < counts["Interactive"]:',
            "        if False:",
            "sampled 3 of 40 interactive elements",
        ),
        Mutation(
            "a focus-indicator count may exceed the elements actually focused",
            '        counts["No Focus Indicator"] > counts["Tab Stops"]\n    ):',
            "        False\n    ):",
            "more missing indicators than elements focused",
        ),
        # The verified WebKit caveat. Removing it turns every link on a WebKit run into a
        # false S1 -- a platform default reported as an application defect.
        Mutation(
            "webkit unreachable counts stop needing Full Keyboard Access confirmed",
            "        if not any(token in note for token in FKA_TOKENS):",
            "        if False:",
            "unreachable on webkit without confirming Full Keyboard Access",
        ),
        # #115 -- both directions of the Submit Mode contract, because each alone leaves the
        # other half of the hole open.
        Mutation(
            "a forms row may claim verdicts on an error state it never triggered (#115)",
            '        elif not exercised and raw != "not run" and mode in FORM_MODES:',
            "        elif False:",
            "verdicts on an error state a dry-run never triggered",
        ),
        Mutation(
            "a submitted form may record no error-contract verdict at all",
            '        if exercised and raw == "not run":',
            "        if False:",
            "submitted an invalid form but recorded no verdict",
        ),
        # Both structural counters are bounded by the same denominator, and the loop is what
        # makes them one rule instead of two copies that can drift.
        Mutation(
            "a form may report more unlabelled controls than it has (#115)",
            '        if {"Controls", column} <= counts.keys() and counts[column] > counts["Controls"]:',
            "        if False:",
            "more unlabelled controls than the form has",
        ),
        # The shared recompute behind both new profiles: `_runtime_extra` spells its own
        # comparison out, so this mutation covers the keyboard/forms path specifically.
        Mutation(
            "keyboard/forms severity is trusted instead of recomputed",
            "    elif required == S1:",
            "    elif False:",
            "unreachable elements downgraded to S2",
        ),
        # #116 -- this profile's distinctive guarantee runs the OPPOSITE way to keyboard's and
        # forms': it stops a row grading an advisory UP into a defect. Both halves of that
        # boundary get a mutation, because each alone leaves the other criterion unguarded.
        Mutation(
            "motion ignoring the preference becomes gating (SC 2.3.3 is Level AAA) (#116)",
            '        gating=(("Autoplay No Control", S1), ("End State Committed", S1)),',
            '        gating=(("Autoplay No Control", S1), ("End State Committed", S1),'
            ' ("Motion Not Suppressed", S1)),',
            "recorded as advisory",
        ),
        Mutation(
            "a print nit becomes a release-blocking defect, with no WCAG upstream (#116)",
            "        gating=(),",
            '        gating=(("Ink Burning", S1),),',
            "print nit inflated",
        ),
        # The mode contract. Without it a row carries counts from a condition it never
        # emulated, which is the forms Submit Mode hole in a new dimension.
        Mutation(
            "an emulation row may carry counts from a mode it never emulated (#116)",
            "        if column in spec.numeric:\n            continue\n        if row[column]:",
            "        if column in spec.numeric:\n            continue\n        if False:",
            "carrying a forced-colors count",
        ),
        # The WebKit ceiling. Removing it lets a forced-colors run on an engine that applies
        # no forcing report CLEAN -- false confidence, not false defects.
        Mutation(
            "a forced-colors result on webkit stops being a platform ceiling (#116)",
            '    if mode == "forced-colors" and engine == "webkit":',
            "    if False:",
            "platform ceiling",
        ),
        Mutation(
            # Now anchored in the shared `_check_bounds` helper rather than in one profile:
            # perf (#117) was the third caller to want this rule, and a third textual copy
            # would have made this very anchor match twice -- a hard error, by design.
            "an emulation count may exceed the inventory it was drawn from (#116)",
            "        if {column, denominator} <= counts.keys() and counts[column] > "
            "counts[denominator]:",
            "        if False:",
            "more unsuppressed animations",
        ),
        # #117 -- every other profile's blind spot leaves a BLANK. This one's returns a
        # plausible number: `CLS 0` from an engine with no layout-shift observer, a byte total
        # summed from an API that reports 0 for cross-origin assets. So each mutation below
        # makes a fabricated measurement read as a real one.
        Mutation(
            "a metric may be recorded from an engine whose observer does not exist (#117)",
            "        for column in PERF_CHROMIUM_ONLY:\n            if row[column]:",
            "        for column in PERF_CHROMIUM_ONLY:\n            if False:",
            "CLS 0 on firefox",
        ),
        # The ceiling is this profile's distinctive direction -- #114/#115 stop a row grading a
        # defect down, #116 stops it grading an advisory up, and this stops it blocking a
        # release on a number no standard underwrites.
        Mutation(
            "a client-side timing may block a release (#117's severity ceiling)",
            '    if severity == S1:\n        findings.append(\n            f"{where}: '
            "Severity S1 on a perf row",
            '    if False:\n        findings.append(\n            f"{where}: '
            "Severity S1 on a perf row",
            "a client-side timing graded S1",
        ),
        Mutation(
            "LCP joins the gating counters, so a localhost timing becomes a defect (#117)",
            "PERF_GATING: tuple[tuple[str, str], ...] = (\n    (CLS_OVER_BUDGET, S2),",
            'PERF_GATING: tuple[tuple[str, str], ...] = (\n    ("LCP ms", S2),\n'
            "    (CLS_OVER_BUDGET, S2),",
            "a slow LCP graded S2",
        ),
        # The byte instrument. transferSize is 0 for a cross-origin asset with no
        # Timing-Allow-Origin and 0 for a cache hit, so without this a budget passes by
        # measuring nothing -- a gate that cannot fail, in the literal sense.
        Mutation(
            "a clean byte verdict may be reported over bytes nobody measured (#117)",
            '    if counts.get("Opaque Requests", 0) > 0 and counts.get('
            '"Oversized Requests") == 0:',
            "    if False:",
            "among the ones that reported a size",
        ),
        Mutation(
            "CLS stops being compared against the budget the row carries (#117)",
            "            cls_over = 1 if measured > budget else 0",
            "            cls_over = 0",
            "CLS over the row's own budget",
        ),
        # `float()` accepts nan and inf; both sail through the budget comparison as if they
        # were measurements, and nan compares false against everything.
        Mutation(
            "a non-finite or negative CLS is accepted as a measurement (#117)",
            "    if not math.isfinite(number) or number < 0:",
            "    if False:",
            "CLS recorded as nan",
        ),
        Mutation(
            "the interaction probe may run on the visit it is measuring (#117)",
            '    elif probe == "same-visit":',
            "    elif False:",
            "ran on the same visit as the metric read",
        ),
        # #117's own acceptance criteria, which the profile claims to ENFORCE rather than
        # describe: breaches carry an attributable cause, and metrics persist for trending.
        # A claim of "enforced" with no mutation behind it is the prose it replaced.
        Mutation(
            "an LCP time may be recorded with nothing to attribute it to (#117)",
            '    if "LCP ms" in counts and not row["LCP Element"]:',
            "    if False:",
            "nothing to attribute it to",
        ),
        Mutation(
            "a measured route may persist nothing to compare the next run against (#117)",
            '    if not row["Evidence"]:\n        findings.append(\n            f"{where}: '
            "measured without an Evidence path",
            '    if False:\n        findings.append(\n            f"{where}: '
            "measured without an Evidence path",
            "nothing persisted to compare",
        ),
    ),
)
