"""Mutation guard: audit_assertion_reachability. Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="audit_assertion_reachability",
    subject="scripts/audit_assertion_reachability.py",
    selftest="scripts/audit_assertion_reachability.py",   # --selftest lives in the module itself
    deps=("scripts/mutation_check.py", "scripts/mutation_types.py"),
    mutations=(
        Mutation(
            # The whole claim. If every label counted as reached, the report is empty forever and
            # reads exactly like a repository with no vacuous assertions in it -- which is the
            # failure mode this tool was written to find in OTHER checkers.
            "every label counts as reached, so nothing is ever reported",
            "    unreachable = sorted({lab for lab in labels if lab.lower() not in haystack})",
            "    unreachable = []",
            "the UNGUARDED assertion is reported",
        ),
        Mutation(
            # The other direction, and it needs its own mutation because the one above cannot see
            # it: reporting EVERY label would also "find" the unguarded one, and a test asserting
            # only that would pass. The control is the guarded label's ABSENCE.
            "no label counts as reached, so a guarded assertion is reported too",
            "    unreachable = sorted({lab for lab in labels if lab.lower() not in haystack})",
            "    unreachable = sorted(set(labels))",
            "the GUARDED assertion is NOT reported",
        ),
        Mutation(
            # A guard with no mutations reporting ZERO unreached labels is the vacuous pass
            # inverted -- a clean bill of health for a subject nothing guards at all.
            "a guard with no mutations reports nothing instead of everything",
            '        return {"guard": guard.name, "status": "NO-MUTATIONS", "labels": len(labels),\n'
            '                "unreachable": sorted(set(labels)), "problems": [],',
            '        return {"guard": guard.name, "status": "NO-MUTATIONS", "labels": len(labels),\n'
            '                "unreachable": [], "problems": [],',
            "a guard with no mutations reports ALL its labels, not none",
        ),
        Mutation(
            # A selftest whose labels cannot be enumerated must SKIP. Returning "ok" instead turns
            # an unexamined guard into a passing one, which is the denominator failure this repo
            # keeps hitting: a percentage over a set nobody checked.
            "an unreadable selftest reports ok instead of skipping",
            '        return {"guard": guard.name, "status": "UNREADABLE",\n'
            '                "reason": (f"no assertion labels could be enumerated from {guard.selftest} -- "',
            '        return {"guard": guard.name, "status": "ok",\n'
            '                "reason": (f"no assertion labels could be enumerated from {guard.selftest} -- "',
            "a selftest with no readable labels is UNREADABLE, not a pass",
        ),
        Mutation(
            # A non-literal label dropped rather than counted is a hole in the denominator that
            # makes the report read clean over something it never examined.
            "a non-literal label is dropped instead of recorded as unreadable",
            "            unreadable.append(node.lineno)",
            "            pass",
            "a non-literal label is reported unreadable rather than silently dropped",
        ),
        # #1048. The --against mode, and the three things it can get wrong.
        Mutation(
            # THE ONE FOUND IN THIS TOOL ON ITS FIRST REAL RUN. A selftest that dies on import
            # against the old revision emits no labels, so every label reads as "not in the
            # output" and the split reports 0-of-N discriminating -- a confident verdict over a
            # comparison that never happened, and indistinguishable from a suite that genuinely
            # cannot tell the two apart.
            "a selftest that could not RUN reports as a suite that does not discriminate",
            "    if result.returncode != 0 and not failing:",
            "    if False:",
            "a selftest that cannot RUN against the old revision skips",
        ),
        Mutation(
            # A case the old implementation FAILS is the evidence the suite works. Losing it makes
            # every suite look like decoration.
            "no case is ever counted as discriminating",
            "    failing = [lab for lab in rest if reported_as_failing(output, lab)]",
            "    failing = []",
            "the case the old implementation FAILS is reported as discriminating",
        ),
        Mutation(
            # ...and the other direction: counting every case as discriminating makes every suite
            # look like proof, which is the flattering answer and therefore the dangerous one.
            "every case is counted as discriminating, so no suite is ever decoration",
            "    passing = [lab for lab in rest if not reported_as_failing(output, lab)]",
            "    passing = []",
            "the case the old implementation PASSES is reported as non-discriminating",
        ),
        Mutation(
            # Without the regression-guard bucket the split drives people to delete cases that are
            # doing their job -- the predecessor is a sample of size one.
            "a declared regression guard is counted against the suite like any other case",
            "    guards_ = [lab for lab in unique if REGRESSION_GUARD_MARKER in lab.lower()]",
            "    guards_ = []",
            "a declared regression guard is excluded from the split",
        ),
        # The control-case precondition. Without it the exit-code preflight catches only the loud
        # failure ("the API is gone") and misses the quiet one ("the API means something else"),
        # where every case fails and the run reports a flattering, false "all discriminate".
        Mutation(
            "a failing control no longer refuses the split, so an unfit harness inflates it",
            "    if failed_controls:",
            "    if False:",
            "a failing control refuses the whole split",
        ),
        Mutation(
            # The other direction: refusing every run would also "pass" a test that only checked
            # the refusal, so the fixture pairs a failing control with a passing one.
            "every control counts as failing, so no split is ever reportable",
            "    failed_controls = [lab for lab in controls if reported_as_failing(output, lab)]",
            "    failed_controls = list(controls)",
            "a passing control lets the split through",
        ),
        Mutation(
            "the control is counted as a data point instead of a precondition",
            "    rest = [lab for lab in unique\n"
            "            if lab not in guards_ and CONTROL_MARKER not in lab.lower()]",
            "    rest = [lab for lab in unique if lab not in guards_]",
            "the control is a precondition, not a data point",
        ),
        # #1059 / #1060, the SHIPPED defect. A bare substring match counts a label the harness
        # never reported -- a traceback echoes the source line -- and a label merely a
        # prefix of a longer failing one. Both inflate the split in the flattering
        # direction, which is the one nobody audits. `failing` and `passing` are mutated
        # separately because each is caught by a DIFFERENT fixture: breaking only one
        # leaves the other's guard still anchored, and the pair would survive as a set.
        Mutation(
            'the FAILING side returns to a bare substring test',
            '    failing = [lab for lab in rest if reported_as_failing(output, lab)]',
            '    failing = [lab for lab in rest if lab.lower() in output.lower()]',
            'a crash on a LABELLED line still skips',
        ),
        # The companion. With only `failing` broken, a prefix label still lands in `passing` via
        # the anchored test and the prefix fixture stays green -- measured, not assumed.
        Mutation(
            'the PASSING side returns to a bare substring test',
            '    passing = [lab for lab in rest if not reported_as_failing(output, lab)]',
            '    passing = [lab for lab in rest if lab.lower() not in output.lower()]',
            'a label that is merely a PREFIX of a failing one is NOT counted',
        ),
        # The anchor's two halves guard DIFFERENT collisions and neither fixture catches the
        # other's break. The LEADING half stops a label matching inside a longer one --
        # `'is refused'` within `'- a splat is refused'`.
        Mutation(
            'the leading anchor is dropped, so a SUFFIX of a longer label counts',
            '    pattern = re.compile(r"(?:^|[-*]\\s|/\\s)" + re.escape(label.strip().lower()) + r"(?=$|:)")',
            '    pattern = re.compile(re.escape(label.strip().lower()) + r"(?=$|:)")',
            'a label that is merely a SUFFIX of a failing one is NOT counted',
        ),
        # The TRAILING half stops a PREFIX riding on the longer label's failure. Measured on dev:
        # 11 such collisions across two shipped tools, 5 and 6, and two files an earlier
        # account named have none at all.
        Mutation(
            "the trailing anchor is dropped, so a PREFIX rides on a longer label's failure",
            '    pattern = re.compile(r"(?:^|[-*]\\s|/\\s)" + re.escape(label.strip().lower()) + r"(?=$|:)")',
            '    pattern = re.compile(r"(?:^|[-*]\\s|/\\s)" + re.escape(label.strip().lower()))',
            'a label that is merely a PREFIX of a failing one is NOT counted',
        ),
        # #1061. The holes are computed either way; printing them is the entire fix, and a report
        # that records a caveat nobody sees is a report without the caveat.
        Mutation(
            "the denominator's holes are recorded but never printed",
            '        if r.get("unreadable_label_lines"):\n            print(f"         ! {len(r[\'unreadable_label_lines\'])} label(s) not literal strings, "\n                  f"at line(s) {r[\'unreadable_label_lines\']} -- not counted either way")\n        if r["old_selftest_passed"]:',
            '        if r["old_selftest_passed"]:',
            'the report PRINTS it rather than only recording it',
        ),
    ),
)
