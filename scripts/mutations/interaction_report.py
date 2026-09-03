"""Mutation guard: interaction_report. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #105 criterion 4. Two of these break the rule by making it fire MORE, which is the
# direction that gets a rule switched off: a false 'dead control' on a working button is
# worse than no rule at all.
GUARD = Guard(
    name="interaction_report",
    subject="plugins/qa-flow/scripts/interaction_report.py",
    selftest="plugins/qa-flow/scripts/interaction_report.py",
    # Without this the collector is absent from the mutant's directory, and every fixture that
    # cross-checks it -- including the `dismiss.*` field checks and the syntax gate's own
    # negative test -- silently does not run. `visual_baseline` below needs it for the same
    # reason.
    needs=("plugins/qa-flow/scripts/crawl_collector.js",),
    mutations=(
        # #829. The skip returned 0, which the doctor renders as PASS.
        Mutation(
            "an absent node exits 0 again, so the doctor prints ok for a check that did not run",
            "        # Exit 3, not 0 (#829): the doctor maps 0 to PASS; 3 renders as SKIP with this reason.\n        return 3",
            "        return 0",
            "a missing node is a SKIP, not a failure",
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
            "an effect kind is dropped, so a working control reports dead",
            'EFFECT_KEYS = ("domChanged", "navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")',
            'EFFECT_KEYS = ("navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")',
            "domChanged counts as an effect",
        ),
        Mutation(
            "the constraint-validation exclusion goes, so every validated form reports dead (#357)",
            '    if control.get("constraintBlocked"):',
            '    if False:',
            "a submit blocked by constraint validation is not dead",
        ),
        Mutation(
            "the href exclusion goes, so every link on the site reports dead",
            '        return "link with href — navigation is its effect and is not observed here"',
            '        pass',
            "a link with href is not dead",
        ),
        Mutation(
            "an unexercised control is judged instead of named",
            '        if not control.get("exercised", False):',
            '        if False:',
            "an unexercised control is not judged clean",
        ),
        # #105 criterion 4, second half. The first of these is the one that decides whether the
        # focus-restore rule is usable: APG's base Disclosure pattern has no Escape row, so
        # dropping the scope guard fires on every accordion on the internet.
        Mutation(
            "the APG scope guard goes, so every ordinary accordion reports a focus-restore bug",
            '    if kind not in RESTORE_REQUIRED:',
            '    if False:',
            "an ordinary disclosure that keeps focus is NOT a finding",
        ),
        Mutation(
            "the combobox discriminator goes, so combobox popups stop being judged",
            '    if trigger_role == "combobox":',
            '    if False:',
            "a combobox that keeps focus fires focus-restore-missing",
        ),
        Mutation(
            "the menu discriminator goes, so menu popups stop being judged",
            '    if haspopup == "menu" or popup_role == "menu":',
            '    if False:',
            "a menu that keeps focus fires focus-restore-missing",
        ),
        Mutation(
            "a probe that never completed is graded instead of named",
            '    if closed is None or restored is None:',
            '    if False:',
            "a probe with focusRestored=null is not judged clean",
        ),
        # Ordering, not presence: moving the calls BELOW the exclusions silently drops every
        # overlay opened by a link -- which is a large share of the real ones.
        Mutation(
            "the dismissal is judged after the exclusions, so links lose their overlays",
            '        judge_dismissal(result, ref, control)\n'
            '        judge_containment(result, ref, control)\n'
            '        if excluded_reason(control):\n'
            '            result.excluded += 1\n'
            '            continue',
            '        if excluded_reason(control):\n'
            '            result.excluded += 1\n'
            '            continue\n'
            '        judge_dismissal(result, ref, control)\n'
            '        judge_containment(result, ref, control)',
            "a link with href is still judged on focus restore",
        ),
        # #114's overlay criterion (a), the half that stayed an agent-typed number for eight
        # releases. Every mutation below except the last two makes the rule fire MORE, and the
        # scope guard is the one that decides whether it is usable: APG specifies the OPPOSITE
        # of containment for menus and comboboxes, so a rule that ignores modality files S1s
        # against behaviour the spec describes the other way.
        Mutation(
            "the modality scope guard goes, so every non-modal dialog is judged on containment",
            "    if not is_modal(containment):",
            "    if False:",
            "that leaks Tab is NOT a finding",
        ),
        Mutation(
            "modality is read by attribute PRESENCE, so aria-modal=\"false\" reads as modal",
            '    return str(containment.get("ariaModal") or "").strip().lower() == "true"',
            '    return containment.get("ariaModal") is not None',
            "is_modal reads aria-modal by VALUE, not by presence",
        ),
        Mutation(
            "the backward direction is dropped, so half of APG's mandate stops being checked",
            '    leaked = [name for name, escaped in (("Tab", forward), ("Shift+Tab", backward)) if escaped]',
            '    leaked = [name for name, escaped in (("Tab", forward),) if escaped]',
            "Shift+Tab alone leaking is still a finding",
        ),
        Mutation(
            "a walk that never completed is graded instead of named",
            "    if forward is None or backward is None:",
            "    if False:",
            "a walk with forwardEscaped=null is not judged clean",
        ),
        Mutation(
            "a layer the walk could not start in is judged anyway",
            '    if not containment.get("containerFound"):',
            "    if False:",
            "a dialog that opened without taking focus is not judged contained",
        ),
        Mutation(
            "the empty-layer guard goes, so a modal with nothing tabbable reports as leaky",
            '    if not containment.get("tabbables"):',
            "    if False:",
            "a modal with no tabbable element inside is not a containment finding",
        ),
        # The vacuous-pass mutation. Nothing about the OUTPUT changes -- the same findings are
        # printed -- but the denominator beside them goes to zero, so a sweep that walked
        # nothing becomes indistinguishable from an app with no leaky modals.
        Mutation(
            "the containment denominator stops counting, so a vacuous pass reads as a clean one",
            "    result.containment_judged += 1",
            "    pass",
            "counts toward the denominator",
        ),
        # The syntax gate's own negative test. `node --check <path>` exits 0 on a broken ESM
        # file, so this gate is one careless edit away from being unable to fail at all.
        Mutation(
            "the collector syntax gate always reports success",
            '    return proc.returncode, proc.stderr.decode("utf-8", "replace")',
            '    return 0, ""',
            "the module-mode check FAILS on a broken ES module",
        ),
    ),
)
