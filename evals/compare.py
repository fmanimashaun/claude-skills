#!/usr/bin/env python3
"""Compare two arms of the doctrine-effect benchmark, and say how sure the comparison can be.

`run.py` prints a pass rate per (case, arm). A rate is not a comparison: "real 67%, weak 33%" over
six cases can be noise, and nothing said so (#1384). This reads one or more `aggregate-result.json`
files and, for each pair of arms:

  * pairs the arms BY CASE. Runs of one case share a prompt and a scaffold, so they are not
    independent samples; each case's valid runs are averaged into one rate, and the CASE is the
    unit every statistic below is computed over. Treating 18 runs as 18 samples would manufacture
    certainty the data has not earned.
  * decides with an EXACT SIGN-FLIP TEST on the per-case deltas (B - A). Under the null the two
    arms are interchangeable, so each case's delta is as likely to carry either sign; the p-value
    is the share of all 2^n sign assignments whose mean is at least as far from 0 as the observed
    one. It is exact up to 16 cases (a seeded Monte Carlo above, whose (k+1)/(M+1) form can never
    report p = 0), so its false-win rate is bounded by alpha -- which a percentile
    bootstrap is not: at n=2 it called every same-sign pair a win, and at 6 cases x 3 runs under
    the null it named a winner 12% of the time against a nominal 5% (independent review of #1394).
  * names a winner ONLY when p <= alpha. A case whose delta is 0 flips to itself, so with k cases
    that MOVED the smallest possible p is 2 / 2^k: fewer than 6 moving cases can NEVER reach 0.05,
    and that is reported as UNDERPOWERED rather than "not detectable".
  * reports a percentile-bootstrap CI on the mean delta as DESCRIPTION only. It never decides.
  * lists every case B did worse on, even when the mean improves -- an aggregate win must not
    hide a regression on one case (the same reason SkillOpt-Sleep's gate reports task deltas).
  * `--motivated-by CASE` (#1385): a case that led to a doctrine edit cannot certify that edit,
    because the edit was written to make it pass. Those cases leave the evidence; if the result
    is a win only WITH them, the verdict is UNVERIFIED.

A "not detectable" verdict is not evidence the arms are equal. How large an effect this design can
see is a simulation question, answered in evals/README.md (Comparing arms), not a number this tool
can print from one run.

Usage:
  python3 evals/compare.py results/<stamp>/aggregate-result.json [more.json ...]
          [--a weak --b real] [--motivated-by CASE ...] [--boot N] [--seed S] [--json]
  python3 evals/compare.py <results.json> --aa real     # identity smoke check: must report 0
  python3 evals/compare.py --selftest

Stdlib only. Costs nothing: it reads committed results, never runs `claude`.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import itertools
import json
import math
import random
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ALPHA = 0.05
DEFAULT_BOOT = 10_000
# A bootstrap of 1 resample is one number labelled as an interval (#1394 review: --boot 1 named a
# winner in 110 of 200 seeds). The floor keeps each tail at least 25 draws deep.
MIN_BOOT = 1_000
MAX_BOOT = 1_000_000
# Exact enumeration of 2^n sign assignments up to this many cases; beyond it, a seeded Monte Carlo
# with the (count + 1) / (draws + 1) form, which can never report p = 0 and keeps the test valid.
EXACT_MAX_CASES = 16
MC_DRAWS = 100_000
_TOL = 1e-12

# The condition keys two result files must agree on before their runs may be pooled. A number
# without its conditions is not evidence (evals/README.md); a number from two conditions averaged
# together is worse, because it looks like one. `claude_version` is one of them: the README lists
# it as a condition of every result.
#
# Deliberately NOT pooled on: per-run budget and timeout. They decide which runs end INVALID (and
# INVALID runs are excluded), not whether a valid run passes, so pooling across them changes the
# denominator of valid runs, never a verdict on one. Declined on the #1422 review, recorded here.
POOLED_CONDITIONS = ("model", "marketplace_version", "tools", "claude_version")


class CompareError(ValueError):
    """Input that cannot be compared honestly. Refused, never coerced."""


@dataclass
class Comparison:
    a: str
    b: str
    n_cases: int
    mean_delta: float | None
    p_value: float | None        # exact (or corrected Monte Carlo) two-sided sign-flip p
    min_p: float | None          # the smallest p these n cases could ever produce
    ci_low: float | None         # descriptive percentile bootstrap; never decides
    ci_high: float | None
    verdict: str                 # b_better | b_worse | not_detectable | underpowered | unverified | insufficient
    per_case: dict[str, float] = field(default_factory=dict)       # case -> B rate - A rate
    regressions: list[str] = field(default_factory=list)           # cases where B < A
    excluded_no_data: list[str] = field(default_factory=list)      # no valid run in one arm
    excluded_motivated: list[str] = field(default_factory=list)    # #1385
    n_moving: int = 0            # cases whose delta is not 0 -- the count min_p is computed from


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_runs(paths: list[Path]) -> list[dict]:
    """Every run from every file, after refusing files whose conditions differ."""
    if not paths:
        raise CompareError("no results file given")
    runs: list[dict] = []
    first: tuple | None = None
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CompareError(f"{path}: unreadable results ({exc})") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
            raise CompareError(f"{path}: not an aggregate-result.json (no `runs` list)")
        conditions = payload.get("conditions", {})
        if not isinstance(conditions, dict):
            raise CompareError(f"{path}: `conditions` must be an object")
        key = tuple(json.dumps(conditions.get(k), sort_keys=True) for k in POOLED_CONDITIONS)
        if first is None:
            first = key
        elif key != first:
            raise CompareError(
                f"{path}: conditions differ from the first file on "
                f"{[k for k, x, y in zip(POOLED_CONDITIONS, key, first) if x != y]} -- "
                f"runs from different conditions cannot be pooled")
        for i, run in enumerate(payload["runs"]):
            runs.append(_check_run(run, f"{path} runs[{i}]"))
    return runs


def _check_run(run: object, where: str) -> dict:
    if not isinstance(run, dict):
        raise CompareError(f"{where}: not an object")
    for key in ("case_id", "arm"):
        if not isinstance(run.get(key), str) or not run[key]:
            raise CompareError(f"{where}: `{key}` must be a non-empty string")
    if not isinstance(run.get("valid"), bool):
        raise CompareError(f"{where}: `valid` must be true or false")
    # A VALID run with no verdict would otherwise read as a fail and invent a regression.
    if run["valid"] and not isinstance(run.get("passed"), bool):
        raise CompareError(f"{where}: a valid run needs `passed` true or false")
    return run


def case_rates(runs: list[dict], arm: str) -> dict[str, float]:
    """Mean pass over VALID runs, per case. INVALID runs are infrastructure, not doctrine."""
    buckets: dict[str, list[bool]] = {}
    for run in runs:
        if run["arm"] == arm and run["valid"]:
            buckets.setdefault(run["case_id"], []).append(run["passed"])
    return {case: sum(v) / len(v) for case, v in buckets.items()}


# --------------------------------------------------------------------------
# Statistics -- all over per-case deltas, one number per case
# --------------------------------------------------------------------------

def min_possible_p(n: int) -> float:
    """The smallest two-sided sign-flip p that n MOVING cases can produce: the observed signs and
    their mirror image are the only two assignments as extreme as a unanimous result. A case with
    delta 0 is not moving -- flipping it changes nothing -- so it must not be counted in n."""
    return min(1.0, 2.0 / (2 ** n)) if n else 1.0


def moving(deltas: list[float]) -> int:
    """How many cases moved at all. Only these can carry a sign (#1422 review)."""
    return sum(1 for d in deltas if abs(d) > _TOL)


def sign_flip_p(deltas: list[float], *, seed: int = 0,
                exact_max: int = EXACT_MAX_CASES) -> float:
    """Two-sided p for H0: each case's delta is symmetric about 0 (the arms are exchangeable)."""
    n = len(deltas)
    observed = abs(sum(deltas))
    if n <= exact_max:
        extreme = sum(
            1 for signs in itertools.product((1, -1), repeat=n)
            if abs(sum(s * d for s, d in zip(signs, deltas))) >= observed - _TOL
        )
        return extreme / (2 ** n)
    rng = random.Random(seed)
    extreme = sum(
        1 for _ in range(MC_DRAWS)
        if abs(sum(d if rng.random() < 0.5 else -d for d in deltas)) >= observed - _TOL
    )
    return (extreme + 1) / (MC_DRAWS + 1)


def bootstrap_ci(deltas: list[float], *, boot: int, seed: int,
                 alpha: float = ALPHA) -> tuple[float, float]:
    """Descriptive percentile CI on the mean, resampling whole cases with replacement.

    Symmetric nearest-rank tails: floor(alpha/2 * boot) draws below `lo` and the same number above
    `hi`. It describes; it does not decide, because at few cases it under-covers.
    """
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    tail = int((alpha / 2) * boot)
    return means[tail], means[boot - 1 - tail]


def exact_power(cases: int, runs: int, weak: float, lift: float) -> dict[str, float]:
    """The probability of each verdict for a design, computed EXACTLY, not simulated (#1432).

    The README's power model: every case's weak arm passes with probability `weak` and the strong
    arm with `weak + lift`, `runs` runs each. A case's delta takes one of 2*runs+1 values, so the
    design has finitely many outcomes; each multiset of deltas is weighted by its multinomial
    probability and judged by `_verdict` itself, so the figure is this script's behaviour, not a
    model of it. Feasible for the small designs where simulation noise matters most (6 x 3: 924
    multisets).
    """
    def pmf(p: float) -> list[float]:
        return [math.comb(runs, k) * p ** k * (1 - p) ** (runs - k) for k in range(runs + 1)]
    pa, pb = pmf(weak), pmf(weak + lift)
    dist: dict[int, float] = {}
    for ka, qa in enumerate(pa):
        for kb, qb in enumerate(pb):
            dist[kb - ka] = dist.get(kb - ka, 0.0) + qa * qb
    out: dict[str, float] = {}
    for combo in itertools.combinations_with_replacement(sorted(dist), cases):
        weight, prob = math.factorial(cases), 1.0
        for v in set(combo):
            weight //= math.factorial(combo.count(v))
            prob *= dist[v] ** combo.count(v)
        verdict = _verdict([v / runs for v in combo], seed=0)[0]
        out[verdict] = out.get(verdict, 0.0) + weight * prob
    return out


def _verdict(deltas: list[float], *, seed: int) -> tuple[str, float | None, float]:
    """(verdict, p, min_p) for a list of per-case deltas."""
    n = len(deltas)
    floor = min_possible_p(moving(deltas))
    if n < 2:
        return "insufficient", None, floor
    if moving(deltas) == 0:
        # Nothing moved: the arms agree exactly (the A/A case). p is 1 by construction.
        return "not_detectable", 1.0, floor
    if floor > ALPHA:
        return "underpowered", None, floor
    p = sign_flip_p(deltas, seed=seed)
    mean = sum(deltas) / n
    if p <= ALPHA and mean > 0:
        return "b_better", p, floor
    if p <= ALPHA and mean < 0:
        return "b_worse", p, floor
    return "not_detectable", p, floor


def compare(runs: list[dict], a: str, b: str, *, motivated: tuple[str, ...] = (),
            boot: int = DEFAULT_BOOT, seed: int = 0) -> Comparison:
    rates_a, rates_b = case_rates(runs, a), case_rates(runs, b)
    every_case = sorted({r["case_id"] for r in runs})
    unknown = sorted(set(motivated) - set(every_case))
    if unknown:
        # A typo'd case id would silently exclude nothing and certify the edit anyway.
        raise CompareError(f"--motivated-by names cases not in the results: {unknown}")

    per_case: dict[str, float] = {}
    no_data: list[str] = []
    for case in every_case:
        if case in rates_a and case in rates_b:
            per_case[case] = rates_b[case] - rates_a[case]
        else:
            no_data.append(case)
    regressions = sorted(c for c, d in per_case.items() if d < 0)
    evidence = {c: d for c, d in per_case.items() if c not in motivated}
    excluded_motivated = sorted(c for c in per_case if c in motivated)

    deltas = [evidence[c] for c in sorted(evidence)]
    verdict, p, floor = _verdict(deltas, seed=seed)
    result = Comparison(a=a, b=b, n_cases=len(deltas), n_moving=moving(deltas),
                        mean_delta=None, p_value=p, min_p=floor,
                        ci_low=None, ci_high=None, verdict=verdict,
                        per_case=per_case, regressions=regressions,
                        excluded_no_data=no_data, excluded_motivated=excluded_motivated)
    if deltas:
        result.mean_delta = sum(deltas) / len(deltas)
    if len(deltas) >= 2:
        result.ci_low, result.ci_high = bootstrap_ci(deltas, boot=boot, seed=seed)

    # #1385: the edit is certified only by cases it was not written for. If the result is a win
    # WITH the motivating cases and not without them, the win rests on them -- circular, so abstain.
    # Only a NON-result on the independent cases can be "resting on" the motivating ones. A
    # significant b_worse there is its own finding and must not be relabelled (#1422 review).
    if excluded_motivated and verdict in {"not_detectable", "underpowered", "insufficient"}:
        full_verdict, _, _ = _verdict([per_case[c] for c in sorted(per_case)], seed=seed)
        if full_verdict == "b_better":
            result.verdict = "unverified"
    return result


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

VERDICT_TEXT = {
    "b_better": "{b} beats {a}: {test} sign-flip p <= 0.05",
    "b_worse": "{b} is worse than {a}: {test} sign-flip p <= 0.05",
    "not_detectable": "no detectable difference -- NOT evidence that the arms are equal",
    "underpowered": "UNDERPOWERED -- with this few cases no result could reach p <= 0.05; "
                    "run more cases before reading anything into the deltas",
    "unverified": "UNVERIFIED -- a win only when the cases the edit was written for are counted "
                  "(--motivated-by), so it cannot certify the edit",
    "insufficient": "insufficient data -- fewer than 2 comparable cases",
}


def format_text(c: Comparison) -> str:
    # Above EXACT_MAX_CASES the p is a seeded Monte Carlo estimate; calling it exact overstates it (#1432).
    test = "exact" if c.n_cases <= EXACT_MAX_CASES else f"Monte Carlo ({MC_DRAWS:,} draws)"
    lines = [f"{c.b} vs {c.a}: {VERDICT_TEXT[c.verdict].format(a=c.a, b=c.b, test=test)}"]
    if c.mean_delta is not None:
        stats = f"  mean per-case delta {c.mean_delta:+.3f} over {c.n_cases} case(s)"
        if c.p_value is not None:
            stats += f"  p = {c.p_value:.4f}"
        # The floor is set by the cases that MOVED, not by n: name that count (#1432).
        stats += f"  (smallest possible p with {c.n_moving} moving case(s): {c.min_p:.4f})"
        lines.append(stats)
        if c.ci_low is not None:
            lines.append(f"  descriptive 95% bootstrap CI [{c.ci_low:+.3f}, {c.ci_high:+.3f}] "
                         f"-- describes the spread, does not decide")
    for case, delta in sorted(c.per_case.items()):
        mark = "  (motivated -- not evidence)" if case in c.excluded_motivated else ""
        lines.append(f"    {case:<24} {delta:+.3f}{mark}")
    if c.regressions:
        lines.append(f"  REGRESSED in {c.b}: {', '.join(c.regressions)}")
    if c.excluded_no_data:
        lines.append(f"  no valid run in one arm, excluded: {', '.join(c.excluded_no_data)}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", nargs="*", type=Path)
    parser.add_argument("--a", default=None, help="baseline arm (default: every pair present)")
    parser.add_argument("--b", default=None, help="treatment arm")
    parser.add_argument("--aa", metavar="ARM", help="identity smoke check: ARM against itself")
    parser.add_argument("--motivated-by", action="append", default=[], metavar="CASE")
    parser.add_argument("--boot", type=int, default=DEFAULT_BOOT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--exact-power", nargs=2, type=int, metavar=("CASES", "RUNS"),
                        help="print the exact verdict probabilities for a design (README power table)")
    args = parser.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    if args.exact_power:
        cases, runs = args.exact_power
        for lift in (0.0, 0.2, 0.3):
            got = exact_power(cases, runs, 0.4, lift)
            print(f"{cases} cases x {runs} runs, +{round(lift * 100)}-point lift: "
                  f"b_better {got.get('b_better', 0.0):.2%}")
        return 0

    try:
        if not MIN_BOOT <= args.boot <= MAX_BOOT:
            raise CompareError(f"--boot must be between {MIN_BOOT} and {MAX_BOOT}")
        runs = load_runs(args.results)
        arms = sorted({r["arm"] for r in runs})
        if args.aa:
            pairs = [(args.aa, args.aa)]
        elif args.a or args.b:
            if not (args.a and args.b):
                raise CompareError("--a and --b go together")
            pairs = [(args.a, args.b)]
        else:
            # The README's order of importance: real vs weak is the comparison that separates
            # "our doctrine helps" from "any instructions help".
            order = [("weak", "real"), ("none", "real"), ("none", "weak")]
            pairs = [p for p in order if p[0] in arms and p[1] in arms]
        for pa, pb in pairs:
            if pa not in arms or pb not in arms:
                raise CompareError(f"arm not in results: {sorted({pa, pb} - set(arms))}; "
                                   f"present: {arms}")
        if not pairs:
            raise CompareError(f"need two of none/weak/real; present: {arms}")
        results = [compare(runs, pa, pb, motivated=tuple(args.motivated_by),
                           boot=args.boot, seed=args.seed) for pa, pb in pairs]
    except CompareError as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print("\n\n".join(format_text(r) for r in results))
    return 0


# --------------------------------------------------------------------------
# Selftest
# --------------------------------------------------------------------------

def _runs(table: dict[str, dict[str, list[bool | None]]]) -> list[dict]:
    """{arm: {case: [passed, ...]}} -> run records. None means an INVALID run."""
    out = []
    for arm, cases in table.items():
        for case, results in cases.items():
            for i, passed in enumerate(results, 1):
                out.append({"case_id": case, "arm": arm, "run_index": i,
                            "valid": passed is not None, "passed": passed})
    return out


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def close(x: float | None, y: float) -> bool:
        return x is not None and abs(x - y) < 1e-9

    cases = [f"c{i}" for i in range(8)]
    ten_cases = [f"c{i}" for i in range(10)]

    # -- the exact test, pinned to hand-computed values ---------------------------------------
    # Unanimous sign over n cases: only the observed signs and their mirror are as extreme.
    check("exact p: 6 unanimous cases = 2/64", close(sign_flip_p([1.0] * 6), 2 / 64),
          sign_flip_p([1.0] * 6))
    check("exact p: 8 unanimous cases = 2/256", close(sign_flip_p([0.5] * 8), 2 / 256))
    # [1,1,1,1,1,-1]: |sum| >= 4 needs at most one minus sign -> 1 + 6, doubled for the mirror = 14.
    check("exact p: one dissent in six = 14/64",
          close(sign_flip_p([1, 1, 1, 1, 1, -1]), 14 / 64), sign_flip_p([1, 1, 1, 1, 1, -1]))
    check("exact p: all-zero deltas = 1", close(sign_flip_p([0.0] * 6), 1.0))
    check("min p: 5 cases cannot reach 0.05", min_possible_p(5) > ALPHA, min_possible_p(5))
    check("min p: 6 cases can", min_possible_p(6) <= ALPHA, min_possible_p(6))
    # #1422 review blocker: a tied case flips to itself. Five up and one tie cannot reach 0.05, so
    # it is underpowered, not "not detectable" -- the floor counts MOVING cases.
    check("zero deltas: 5 up + 1 tie has p = 2/32", close(sign_flip_p([1, 1, 1, 1, 1, 0]), 2 / 32))
    check("zero deltas: 5 up + 1 tie is underpowered",
          _verdict([1, 1, 1, 1, 1, 0], seed=0)[0] == "underpowered", _verdict([1, 1, 1, 1, 1, 0], seed=0))
    check("zero deltas: 6 up + 1 tie can still win",
          _verdict([1, 1, 1, 1, 1, 1, 0], seed=0)[0] == "b_better", _verdict([1, 1, 1, 1, 1, 1, 0], seed=0))

    # The Monte Carlo branch (above EXACT_MAX_CASES), forced on a vector small enough to enumerate:
    # it must agree with the exact answer, never report 0, and be seeded.
    ten = [1, 1, 1, 1, 1, 1, 1, -1, 0.5, -0.5]
    exact10 = sign_flip_p(ten, exact_max=16)
    mc10 = sign_flip_p(ten, exact_max=0, seed=3)
    check("monte carlo: agrees with exact within 0.01", abs(mc10 - exact10) < 0.01, (mc10, exact10))
    check("monte carlo: unanimous is never p = 0",
          sign_flip_p([1.0] * 20, exact_max=0) > 0, sign_flip_p([1.0] * 20, exact_max=0))
    check("monte carlo: unanimous 20 is tiny but not below one draw",
          close(sign_flip_p([1.0] * 20, exact_max=0), 1 / (MC_DRAWS + 1)))
    check("monte carlo: seeded", sign_flip_p(ten, exact_max=0, seed=3) == mc10)
    # A LITERAL, not a recomputation (#1432): 5,655 of 100,000 seeded draws are as extreme, and the
    # +1 correction makes it 5,656 / 100,001. A changed denominator, or MC_DRAWS = 1000, moves it.
    check("monte carlo: the seeded value is pinned", mc10 == 5656 / 100_001, mc10)

    # The README's power table, 6 cases x 3 runs, computed exactly (#1432): literal figures.
    for lift, want in ((0.0, 0.0015), (0.2, 0.0260), (0.3, 0.0738)):
        got = exact_power(6, 3, 0.4, lift)
        check(f"exact power, 6 x 3 at +{round(lift * 100)}: b_better {want:.2%}",
              round(got.get("b_better", 0.0), 4) == want and abs(sum(got.values()) - 1) < 1e-9, got)

    # -- verdicts ---------------------------------------------------------------------------
    strong = _runs({"weak": {c: [False] * 3 for c in cases},
                    "real": {c: [True] * 3 for c in cases}})
    r = compare(strong, "weak", "real", boot=2000)
    check("strong effect is detected", r.verdict == "b_better", r)
    check("strong effect p is exact", close(r.p_value, 2 / 256), r.p_value)
    check("strong effect delta is 1.0", r.mean_delta == 1.0, r.mean_delta)
    r = compare(strong, "real", "weak", boot=2000)
    check("reversed strong effect reads worse", r.verdict == "b_worse", r.verdict)

    # A/A: an arm against itself must be exactly zero, and must NOT be a win.
    r = compare(strong, "real", "real", boot=2000)
    check("A/A delta is 0", r.mean_delta == 0.0, r.mean_delta)
    check("A/A p is 1", close(r.p_value, 1.0), r.p_value)
    check("A/A is not a win", r.verdict == "not_detectable", r.verdict)

    # #1394 review F1: two same-sign cases were called a win with a zero-width "95% CI".
    two = _runs({"weak": {"c0": [True, False, False], "c1": [True, False, False]},
                 "real": {"c0": [True, True, False], "c1": [True, True, False]}})
    r = compare(two, "weak", "real", boot=2000)
    check("two same-sign cases are underpowered, not a win", r.verdict == "underpowered", r)

    # #1394 review F2: THE CASE IS THE UNIT. Two cases x 30 runs, every run favouring real, is 60
    # agreeing runs but only two independent cases. Counting runs would make it a certain win.
    many_runs = _runs({"weak": {"c0": [False] * 30, "c1": [False] * 30},
                       "real": {"c0": [True] * 30, "c1": [True] * 30}})
    r = compare(many_runs, "weak", "real", boot=2000)
    check("runs are not cases: 2 cases x 30 runs stays underpowered",
          r.verdict == "underpowered" and r.n_cases == 2, r)
    # The six-case strong effect must report p for SIX cases -- a runs-as-samples count would give
    # a far smaller p for the same data.
    six = _runs({"weak": {c: [False] * 3 for c in cases[:6]},
                 "real": {c: [True] * 3 for c in cases[:6]}})
    r = compare(six, "weak", "real", boot=2000)
    check("p is computed over cases (6), not runs (18)", close(r.p_value, 2 / 64), r.p_value)

    # Mixed direction: a positive mean that is not significant.
    mixed = _runs({"weak": {"c0": [False] * 3, "c1": [True] * 3, "c2": [False] * 3,
                            "c3": [True] * 3, "c4": [False] * 3, "c5": [True] * 3},
                   "real": {"c0": [True] * 3, "c1": [False] * 3, "c2": [True] * 3,
                            "c3": [True] * 3, "c4": [True] * 3, "c5": [False] * 3}})
    r = compare(mixed, "weak", "real", boot=2000)
    check("mixed effect is not a win", r.verdict in {"not_detectable", "underpowered"}, r)
    # c3 ties (delta 0): a tie is not a regression. Only c1 and c5 got worse.
    check("a tied case is not listed as a regression", r.regressions == ["c1", "c5"], r.regressions)

    # THE CI DOES NOT DECIDE. Six moving cases, deltas +1/3 +1/3 +1/3 +2/3 +2/3 -1/3: the bootstrap
    # CI is [0.056, 0.556] -- it excludes 0 -- while the exact p is 0.156. Not a win.
    leans = _runs({"weak": {"c0": [False] * 3, "c1": [False] * 3, "c2": [False] * 3,
                            "c3": [False] * 3, "c4": [False] * 3, "c5": [True, False, False]},
                   "real": {"c0": [True, False, False], "c1": [True, False, False],
                            "c2": [True, False, False], "c3": [True, True, False],
                            "c4": [True, True, False], "c5": [False, False, False]}})
    r = compare(leans, "weak", "real", boot=MIN_BOOT, seed=0)
    check("a CI that excludes 0 is not a win when the exact p is not",
          r.verdict == "not_detectable" and r.ci_low > 0 and close(r.p_value, 10 / 64), r)

    # The false-win rate under the null is bounded by alpha. 6 cases x 3 runs, both arms 0.4: the
    # percentile-bootstrap verdict it replaces measured 12% two-sided here.
    rng = random.Random(1384)
    sims, wins = 400, 0
    for s in range(sims):
        null = [{"case_id": f"c{i}", "arm": arm, "valid": True, "passed": rng.random() < 0.4}
                for i in range(6) for arm in ("weak", "real") for _ in range(3)]
        wins += compare(null, "weak", "real", boot=MIN_BOOT, seed=s).verdict in {"b_better", "b_worse"}
    check("null 6x3: false-win rate <= alpha", wins / sims <= ALPHA, f"{wins}/{sims}")

    # -- the descriptive CI, pinned so a narrower interval cannot slip in unseen -----------------
    lo, hi = bootstrap_ci([1.0, 0.0, 0.0, 0.0], boot=MIN_BOOT, seed=0)
    check("CI: pinned 95% bounds for [1,0,0,0] at seed 0", (lo, hi) == (0.0, 0.75), (lo, hi))
    # Both tails non-trivial, so moving EITHER one is caught (the 25th percentile would be 0.1).
    pinned = bootstrap_ci([1.0, 0.5, 0.0, -0.5, 0.5], boot=MIN_BOOT, seed=0)
    check("CI: pinned both tails for a mixed vector", tuple(round(x, 9) for x in pinned) == (-0.2, 0.7),
          pinned)
    lo90, hi90 = bootstrap_ci([1.0, 0.0, 0.0, 0.0], boot=MIN_BOOT, seed=0, alpha=0.5)
    check("CI: a 50% interval is narrower than the 95% one", lo90 >= lo and hi90 <= hi and
          (lo90, hi90) != (lo, hi), (lo90, hi90))

    # -- regressions, invalid runs, one-sided data ------------------------------------------
    # Nine up and one down over ten cases: p = 22/1024, a win, with one case worse.
    ten = [f"c{i}" for i in range(10)]
    hidden = _runs({"weak": {**{c: [False] * 3 for c in ten[:9]}, "c9": [True] * 3},
                    "real": {**{c: [True] * 3 for c in ten[:9]}, "c9": [False] * 3}})
    r = compare(hidden, "weak", "real", boot=2000)
    check("aggregate still wins", r.verdict == "b_better" and close(r.p_value, 22 / 1024), r)
    check("one-case regression is listed despite the win", r.regressions == ["c9"], r.regressions)

    invalid = _runs({"weak": {"c0": [False, None, None], "c1": [False] * 3},
                     "real": {"c0": [True, None, None], "c1": [True] * 3}})
    check("invalid runs do not dilute the rate",
          case_rates(invalid, "real") == {"c0": 1.0, "c1": 1.0}, case_rates(invalid, "real"))

    one_sided = _runs({"weak": {"c0": [False] * 3, "c1": [False] * 3, "c2": [None] * 3},
                       "real": {"c0": [True] * 3, "c1": [True] * 3, "c2": [True] * 3}})
    r = compare(one_sided, "weak", "real", boot=2000)
    check("a case with no valid run in one arm is excluded",
          r.excluded_no_data == ["c2"] and "c2" not in r.per_case, r)

    single = _runs({"weak": {"c0": [False] * 3}, "real": {"c0": [True] * 3}})
    r = compare(single, "weak", "real", boot=2000)
    check("one case is insufficient", r.verdict == "insufficient" and r.ci_low is None, r)

    # -- #1385 ------------------------------------------------------------------------------
    # Seven unanimous cases win (p = 2/128). Two of them motivated the edit; the remaining five
    # cannot reach 0.05 on their own, so the win rests on the motivating cases.
    seven = _runs({"weak": {c: [False] * 3 for c in cases[:7]},
                   "real": {c: [True] * 3 for c in cases[:7]}})
    r = compare(seven, "weak", "real", motivated=("c0", "c1"), boot=2000)
    check("a win only with the motivating cases is unverified", r.verdict == "unverified", r)
    check("the motivating cases are removed from the evidence",
          r.excluded_motivated == ["c0", "c1"] and r.n_cases == 5, r)
    # The other two non-results the relabel covers (#1432): each was unguarded by any fixture.
    # INSUFFICIENT: one independent case, seven motivated; all eight together are unanimous.
    eight = _runs({"weak": {f"c{i}": [False] * 3 for i in range(8)},
                   "real": {f"c{i}": [True] * 3 for i in range(8)}})
    r = compare(eight, "weak", "real", motivated=tuple(f"c{i}" for i in range(7)), boot=2000)
    check("insufficient independent evidence behind a full win is unverified",
          r.verdict == "unverified" and r.n_cases == 1, r)
    # NOT_DETECTABLE: six independent cases, one of them worse (p = 14/64); six motivated wins
    # added make the full set 11 up and 1 down, p = 26/4096.
    nd_table = {f"i{i}": ([False] * 3, [True] * 3) for i in range(5)}
    nd_table["i5"] = ([True] * 3, [False] * 3)
    nd_table.update({f"m{i}": ([False] * 3, [True] * 3) for i in range(6)})
    nd_runs = _runs({"weak": {c: w for c, (w, _) in nd_table.items()},
                        "real": {c: r_ for c, (_, r_) in nd_table.items()}})
    r = compare(nd_runs, "weak", "real", motivated=tuple(f"m{i}" for i in range(6)), boot=2000)
    check("a not-detectable independent result behind a full win is unverified",
          r.verdict == "unverified" and r.n_cases == 6, r)
    r = compare(nd_runs, "weak", "real", boot=2000)
    check("CONTROL: the same twelve cases, none motivated, are a win", r.verdict == "b_better", r.verdict)
    # Control on the same shape: excluding ONE still leaves six unanimous cases, a win on its own.
    r = compare(seven, "weak", "real", motivated=("c0",), boot=2000)
    check("other cases alone still certify the edit", r.verdict == "b_better", r.verdict)
    # A significant LOSS on the independent cases is a finding of its own, not "unverified" -- even
    # when the full set, motivating cases included, is a significant WIN. 17 motivating cases up
    # (full: 23 cases, 17 up 6 down, p ~= 0.035) and 6 independent cases down (p = 2/64).
    up = [f"m{i}" for i in range(17)]
    down = [f"d{i}" for i in range(6)]
    worse = _runs({"weak": {**{c: [False] * 3 for c in up}, **{c: [True] * 3 for c in down}},
                   "real": {**{c: [True] * 3 for c in up}, **{c: [False] * 3 for c in down}}})
    full = compare(worse, "weak", "real", boot=MIN_BOOT)
    r = compare(worse, "weak", "real", motivated=tuple(up), boot=MIN_BOOT)
    check("a significant b_worse on independent cases is not relabelled",
          full.verdict == "b_better" and r.verdict == "b_worse", (full.verdict, full.p_value, r.verdict))
    # A motivated case with no comparable data excludes nothing, so it must not relabel anything.
    gap = _runs({"weak": {**{c: [False] * 3 for c in cases[:7]}, "c7": [None] * 3},
                 "real": {c: [True] * 3 for c in cases}})
    r = compare(gap, "weak", "real", motivated=("c7",), boot=2000)
    check("a motivated case with no data leaves the verdict alone",
          r.verdict == "b_better" and r.excluded_motivated == [], r)
    try:
        compare(strong, "weak", "real", motivated=("c99",), boot=2000)
        check("an unknown --motivated-by case is refused", False, "accepted")
    except CompareError:
        check("an unknown --motivated-by case is refused", True)

    a1 = compare(mixed, "weak", "real", boot=MIN_BOOT, seed=7)
    a2 = compare(mixed, "weak", "real", boot=MIN_BOOT, seed=7)
    check("seeded result is reproducible", (a1.ci_low, a1.ci_high, a1.p_value) ==
          (a2.ci_low, a2.ci_high, a2.p_value))

    for label, bad in (("valid run with no verdict", {"case_id": "c0", "arm": "real",
                                                      "valid": True, "passed": None}),
                       ("non-bool valid", {"case_id": "c0", "arm": "real",
                                           "valid": 1, "passed": True})):
        try:
            _check_run(bad, "fixture")
            check(f"refuses {label}", False, "accepted")
        except CompareError:
            check(f"refuses {label}", True)

    # -- through the real entry point ---------------------------------------------------------
    base_conditions = {"model": "sonnet", "marketplace_version": "1.0.0", "tools": "Read",
                       "claude_version": "2.0.0"}
    with tempfile.TemporaryDirectory() as tmp:
        def write(name: str, runs: list[dict], **override) -> Path:
            path = Path(tmp) / name
            path.write_text(json.dumps({"conditions": {**base_conditions, **override},
                                        "runs": runs}), encoding="utf-8")
            return path

        half = len(strong) // 2
        f1, f2 = write("a.json", strong[:half]), write("b.json", strong[half:])
        # The split puts every weak run in one file and every real run in the other, so a
        # comparison succeeds only if the two files really were pooled.
        pair = [str(f1), str(f2)]
        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            check("main() compares pooled files", main(["compare", *pair, "--json"]) == 0)
            verdicts = json.loads(quiet.getvalue())
            check("main() reports the pooled verdict",
                  [v["verdict"] for v in verdicts] == ["b_better"], verdicts)
            # Every pooled condition is refused on its own -- not only the one tested first. The
            # keys are LITERAL: looping over POOLED_CONDITIONS would shrink with it and prove nothing.
            for key in ("model", "marketplace_version", "tools", "claude_version"):
                other = write(f"diff-{key}.json", strong[half:], **{key: "DIFFERENT"})
                check(f"main() refuses pooling across a different {key}",
                      main(["compare", str(f1), str(other)]) == 2)
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"conditions": "oops", "runs": []}), encoding="utf-8")
            try:
                rc = main(["compare", str(bad)])
            except Exception as exc:  # a traceback is not a refusal
                rc = f"raised {exc!r}"
            check("main() refuses a non-object conditions", rc == 2, rc)
            check("main() refuses a missing arm",
                  main(["compare", *pair, "--a", "none", "--b", "real"]) == 2)
            check("main() refuses a bootstrap too small to be an interval",
                  main(["compare", *pair, "--boot", str(MIN_BOOT - 1)]) == 2)
            check("main() runs the A/A check", main(["compare", *pair, "--aa", "real"]) == 0)
        check("pooling keeps every run", len(load_runs([f1, f2])) == len(strong))

    print(f"compare selftest: {checks} check(s)")
    if failures:
        print(f"{len(failures)} FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all comparisons behave as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
