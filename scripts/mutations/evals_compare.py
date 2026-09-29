"""Mutation guard: evals/compare.py, the benchmark's arm comparison. Run by scripts/mutation_check.py.

The breaks that matter make the comparison claim MORE than the data supports. The #1394 review
found four of them surviving the first version: two same-sign cases called a win, runs counted as
independent samples, a narrowed percentile, and pooling across an unchecked condition. Each is a
mutation below, with the fixture that now catches it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="evals_compare",
    subject="evals/compare.py",
    selftest="evals/compare.py",
    mutations=(
        # THE CASE IS THE UNIT (#1394 review F2). Counting each run as a sample turns 6 cases x 3
        # runs into 18 and shrinks p by orders of magnitude on the same data.
        Mutation(
            "runs are counted as independent samples instead of cases",
            "    deltas = [evidence[c] for c in sorted(evidence)]\n",
            "    deltas = [evidence[c] for c in sorted(evidence) for _ in range(3)]\n",
            "p is computed over cases (6), not runs (18)",
        ),
        # #1394 review F1. With the floor gone, two unanimous cases are judged as if they could win.
        Mutation(
            "too few cases to ever reach alpha are judged anyway",
            "    if floor > ALPHA:\n",
            "    if floor > 1.0:\n",
            "two same-sign cases are underpowered, not a win",
        ),
        # The verdict the review measured at 12% false wins: decide from the bootstrap CI.
        Mutation(
            "the verdict is taken from the descriptive bootstrap CI instead of the exact test",
            "    if p <= ALPHA and mean > 0:\n        return \"b_better\", p, floor\n",
            "    if bootstrap_ci(deltas, boot=1000, seed=seed)[0] > 0:\n        return \"b_better\", p, floor\n",
            "a CI that excludes 0 is not a win when the exact p is not",
        ),
        Mutation(
            "the exact test counts only strictly more extreme assignments",
            "            if abs(sum(s * d for s, d in zip(signs, deltas))) >= observed - _TOL\n",
            "            if abs(sum(s * d for s, d in zip(signs, deltas))) > observed + _TOL\n",
            "exact p: 6 unanimous cases = 2/64",
        ),
        Mutation(
            "the CI tails are cut twice as deep, so the interval narrows",
            "    return means[tail], means[boot - 1 - tail]\n",
            "    return means[2 * tail], means[boot - 1 - 2 * tail]\n",
            "CI: pinned 95% bounds",
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
            "the motivating cases are removed from the evidence",
        ),
        Mutation(
            "a win resting only on its motivating cases is not flagged",
            "        if full_verdict == \"b_better\":\n",
            "        if False:\n",
            "a win only with the motivating cases is unverified",
        ),
        # #1422 review blocker: tied cases counted toward the floor, so "underpowered" became
        # "not detectable" in most 6x3 runs.
        Mutation(
            "tied (zero-delta) cases count toward the p floor",
            "    floor = min_possible_p(moving(deltas))\n",
            "    floor = min_possible_p(len(deltas))\n",
            "zero deltas: 5 up + 1 tie is underpowered",
        ),
        Mutation(
            "a significant loss on the independent cases is relabelled unverified",
            '    if excluded_motivated and verdict in {"not_detectable", "underpowered", "insufficient"}:\n',
            '    if excluded_motivated and verdict != "b_better":\n',
            "a significant b_worse on independent cases is not relabelled",
        ),
        Mutation(
            "the Monte Carlo branch drops the +1 correction, so a unanimous result reports p = 0",
            "    return (extreme + 1) / (MC_DRAWS + 1)\n",
            "    return extreme / MC_DRAWS\n",
            "monte carlo: unanimous is never p = 0",
        ),
        Mutation(
            "a tie is listed as a regression",
            "    regressions = sorted(c for c, d in per_case.items() if d < 0)\n",
            "    regressions = sorted(c for c, d in per_case.items() if d <= 0)\n",
            "a tied case is not listed as a regression",
        ),
        Mutation(
            "the lower CI tail is cut at the 25th percentile",
            "    return means[tail], means[boot - 1 - tail]\n",
            "    return means[boot // 4], means[boot - 1 - tail]\n",
            "CI: pinned both tails for a mixed vector",
        ),
        Mutation(
            "a typo'd --motivated-by case silently excludes nothing",
            "    if unknown:\n",
            "    if False:\n",
            "an unknown --motivated-by case is refused",
        ),
        # INVALID runs read as failures invent a regression out of an infrastructure problem.
        Mutation(
            "INVALID runs are scored as failures",
            '        if run["arm"] == arm and run["valid"]:\n'
            '            buckets.setdefault(run["case_id"], []).append(run["passed"])\n',
            '        if run["arm"] == arm:\n'
            '            buckets.setdefault(run["case_id"], []).append(bool(run["passed"]))\n',
            "invalid runs do not dilute the rate",
        ),
        Mutation(
            "one case is judged instead of reported insufficient",
            "    if n < 2:\n",
            "    if n < 1:\n",
            "one case is insufficient",
        ),
        # #1394 review F5: only `model` was ever tested; the other refusals were unguarded.
        Mutation(
            "pooling checks the model only",
            '    POOLED_CONDITIONS = ("model", "marketplace_version", "tools", "claude_version")\n'[4:],
            'POOLED_CONDITIONS = ("model",)\n',
            "refuses pooling across a different marketplace_version",
        ),
        Mutation(
            "a bootstrap of 1 resample is accepted as an interval",
            "        if not MIN_BOOT <= args.boot <= MAX_BOOT:\n",
            "        if not 1 <= args.boot <= MAX_BOOT:\n",
            "a bootstrap too small to be an interval",
        ),
        Mutation(
            "a non-object `conditions` crashes instead of being refused",
            "        if not isinstance(conditions, dict):\n",
            "        if False:\n",
            "refuses a non-object conditions",
        ),
        # #1432 (final #1422 review): the relabel set, the Monte Carlo pin, the printed test and floor,
        # and the exact power figures, each unguarded before.
        Mutation(
            'insufficient independent evidence is no longer relabelled',
            '{"not_detectable", "underpowered", "insufficient"}',
            '{"not_detectable", "underpowered"}',
            'insufficient independent evidence behind a full win is unverified',
        ),
        Mutation(
            'not-detectable independent evidence is no longer relabelled',
            '{"not_detectable", "underpowered", "insufficient"}',
            '{"underpowered", "insufficient"}',
            'a not-detectable independent result behind a full win is unverified',
        ),
        Mutation(
            'the Monte Carlo +1 correction is dropped from the denominator',
            '    return (extreme + 1) / (MC_DRAWS + 1)',
            '    return (extreme + 1) / MC_DRAWS',
            'monte carlo: the seeded value is pinned',
        ),
        Mutation(
            'the Monte Carlo draw count falls to 1000',
            'MC_DRAWS = 100_000',
            'MC_DRAWS = 1000',
            'monte carlo: the seeded value is pinned',
        ),
        Mutation(
            'the Monte Carlo branch is called exact again',
            '    test = "exact" if c.n_cases <= EXACT_MAX_CASES else f"Monte Carlo ({MC_DRAWS:,} draws)"',
            '    test = "exact"',
            'above 16 cases the verdict says Monte Carlo',
        ),
        Mutation(
            'the floor is labelled with n instead of the moving count',
            '(smallest possible p with {c.n_moving} moving case(s)',
            '(smallest possible p with {c.n_cases} moving case(s)',
            'the floor names the MOVING count',
        ),
        Mutation(
            'exact power drops the multinomial weight',
            '            weight //= math.factorial(combo.count(v))',
            '            weight = 1',
            'exact power, 6 x 3 at +30',
        ),
        Mutation(
            '16 cases is called Monte Carlo (the boundary moves)',
            '    test = "exact" if c.n_cases <= EXACT_MAX_CASES else',
            '    test = "exact" if c.n_cases < EXACT_MAX_CASES else',
            'CONTROL: at exactly 16 cases the verdict says exact',
        ),
        Mutation(
            'exact power accepts a pass rate above 1',
            '0.0 <= weak + lift <= 1.0):',
            '0.0 <= weak + lift):',
            'exact power refuses (6, 3, 0.4, 0.7)',
        ),
        Mutation(
            'exact power accepts a weak-arm pass rate above 1',
            '0.0 <= weak <= 1.0 and',
            '0.0 <= weak and',
            'exact power refuses (6, 3, 1.2, -0.3)',
        ),
    ),
)
