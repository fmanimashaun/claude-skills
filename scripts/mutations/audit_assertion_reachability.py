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
            "    failing = [lab for lab in rest if lab.lower() in output]",
            "    failing = []",
            "the case the old implementation FAILS is reported as discriminating",
        ),
        Mutation(
            # ...and the other direction: counting every case as discriminating makes every suite
            # look like proof, which is the flattering answer and therefore the dangerous one.
            "every case is counted as discriminating, so no suite is ever decoration",
            "    passing = [lab for lab in rest if lab.lower() not in output]",
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
    ),
)
