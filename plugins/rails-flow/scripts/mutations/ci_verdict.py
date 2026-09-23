"""Mutation guard: ci_verdict. Declared here, run by scripts/mutation_check.py (#1077)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="ci_verdict",
    subject="scripts/ci_verdict.py",
    selftest="scripts/ci_verdict.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # THE WHOLE TOOL. Without the step count, `conclusion` decides -- which is the state
            # that cost two sessions one morning on one repository.
            "the step count stops separating a real failure from a run that never started",
            "    if steps == 0 and conclusion in NEVER_STARTED_CONCLUSIONS:",
            "    if False:",
            "a completed failure that executed ZERO steps did not run",
        ),
        Mutation(
            # UNMEASURED IS NOT ZERO, and collapsing them is the inverted form of the same defect:
            # it would send someone to a billing page over a genuinely failing suite.
            "an unmeasured step count is treated as zero, so an unreadable run claims no runner",
            "    if steps == 0 and conclusion in NEVER_STARTED_CONCLUSIONS:",
            "    if not steps and conclusion in NEVER_STARTED_CONCLUSIONS:",
            "an UNMEASURED step count falls back to the conclusion",
        ),
        Mutation(
            # A success with no steps is not a thing. Reporting one as "did not run" is the
            # flattering error -- it invents an environment problem out of a green run.
            "a successful run with no recorded steps is reported as never having run",
            '    if conclusion == "success":',
            "    if False:",
            "a success is a pass even with no step count",
        ),
        Mutation(
            # THE EXIT CODES ARE THE CONTRACT. Collapsing 3 into 1 hands a caller back exactly
            # the ambiguity the tool exists to remove, while still looking like it works.
            "nothing-ran exits like a real failure, collapsing the two verdicts again",
            "    return 3 if buckets[DID_NOT_RUN] else 0",
            "    return 1 if buckets[DID_NOT_RUN] else 0",
            "nothing ran exits 3",
        ),
        Mutation(
            # Zero runs must not read as a clean bill of health -- reporting a repo healthy from
            # rows that were not there is half of what #1077 cost.
            "no runs at all reads as a clean run",
            '        print("NOT APPLICABLE: no runs matched — this check examined nothing.")\n        return 2',
            '        return 0',
            "no runs at all is exit 2, not a clean bill of health",
        ),
        Mutation(
            # #1208. Without the zero-jobs rule a workflow that never parsed falls through to the
            # step-count rule -- and lands wherever `steps` sends it, never on the truth.
            "a run with zero jobs is no longer recognised as never having started",
            '    if run.get("jobs") == 0 and conclusion in UNREADABLE_WORKFLOW_CONCLUSIONS:',
            "    if False:",
            "a completed failure with ZERO jobs never started",
        ),
        Mutation(
            # THE ORIGINAL DEFECT, restored exactly: a successful zero-job answer (`[] | add` is
            # null) collapses into the failed-call branch and reads as "could not measure".
            "a successful zero-job answer is read as a failed call again",
            "    return jobs, (steps if isinstance(steps, int) else 0 if jobs == 0 else None)",
            "    return (jobs, steps) if isinstance(steps, int) else (None, None)",
            "a successful zero-job answer is a measurement",
        ),
        Mutation(
            # A never-started run is about the diff. Letting it exit 0 or 3 tells a caller the
            # change is fine, or that the environment is at fault, over a YAML error in the change.
            "a workflow that never started no longer exits as a finding about the diff",
            "    if buckets[FAILED] or buckets[NEVER_STARTED]:",
            "    if buckets[FAILED]:",
            "a workflow that never started exits 1",
        ),
        Mutation(
            # #1218 restored: every never-started conclusion counts, so a cancelled run is blamed on
            # a workflow file nothing says is broken.
            "a zero-job cancelled run is blamed on the workflow file again",
            '    if run.get("jobs") == 0 and conclusion in UNREADABLE_WORKFLOW_CONCLUSIONS:',
            '    if run.get("jobs") == 0 and conclusion in NEVER_STARTED_CONCLUSIONS:',
            "a zero-job CANCELLED run is not blamed on the workflow file",
        ),
        Mutation(
            # The narrowing must not drop startup_failure, the other real unreadable-file conclusion.
            "startup_failure is no longer read as an unreadable workflow",
            'UNREADABLE_WORKFLOW_CONCLUSIONS = frozenset({"failure", "startup_failure"})',
            'UNREADABLE_WORKFLOW_CONCLUSIONS = frozenset({"failure"})',
            "...while a zero-job startup_failure still is",
        ),
    ),
)
