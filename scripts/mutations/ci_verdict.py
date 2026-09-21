"""Mutation guard: ci_verdict. Declared here, run by scripts/mutation_check.py (#1077)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="ci_verdict",
    subject="plugins/rails-flow/scripts/ci_verdict.py",
    selftest="plugins/rails-flow/scripts/ci_verdict.py",   # --selftest lives in the module
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
    ),
)
