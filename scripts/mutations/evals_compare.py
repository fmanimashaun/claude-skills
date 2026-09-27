"""Mutation guard: evals/compare.py, the benchmark's arm comparison. Run by scripts/mutation_check.py.

The breaks that matter are the ones that make the comparison claim MORE than the data supports: a
win on an interval touching 0, an aggregate that hides a per-case regression, a doctrine edit
certified by the case it was written for (#1385), INVALID runs scored as failures, and runs from
different conditions pooled into one number (#1384).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="evals_compare",
    subject="evals/compare.py",
    selftest="evals/compare.py",
    mutations=(
        # THE OVERCLAIM. With >= an arm compared with itself (CI [0, 0]) is called a win.
        Mutation(
            "a CI touching 0 counts as a win",
            "    elif lo > 0:\n",
            "    elif lo >= 0:\n",
            "A/A is not a win",
        ),
        Mutation(
            "per-case regressions are dropped, so an aggregate win hides one",
            "    regressions = sorted(c for c, d in per_case.items() if d < 0)\n",
            "    regressions = []\n",
            "one-case regression is listed despite the win",
        ),
        Mutation(
            "motivating cases stay in the evidence",
            "    evidence = {c: d for c, d in per_case.items() if c not in motivated}\n",
            "    evidence = dict(per_case)\n",
            "the motivating case is removed from the evidence",
        ),
        Mutation(
            "an edit certified only by its motivating case is not flagged",
            "    if motivated and not any(evidence.values()):\n",
            "    if False:\n",
            "an effect only on the motivating case is unverified",
        ),
        Mutation(
            "a typo'd --motivated-by case silently excludes nothing",
            "    if unknown:\n",
            "    if False:\n",
            "an unknown --motivated-by case is refused",
        ),
        # The quiet version of dropping the valid filter: INVALID runs read as failures, which
        # invents a regression out of an infrastructure problem.
        Mutation(
            "INVALID runs are scored as failures",
            '        if run["arm"] == arm and run["valid"]:\n'
            '            buckets.setdefault(run["case_id"], []).append(run["passed"])\n',
            '        if run["arm"] == arm:\n'
            '            buckets.setdefault(run["case_id"], []).append(bool(run["passed"]))\n',
            "invalid runs do not dilute the rate",
        ),
        Mutation(
            "one case is resampled into an interval",
            "    if len(evidence) < 2:\n",
            "    if len(evidence) < 1:\n",
            "one case is insufficient",
        ),
        Mutation(
            "runs from different conditions are pooled",
            "        elif key != first:\n",
            "        elif False:\n",
            "main() refuses pooling different conditions",
        ),
    ),
)
