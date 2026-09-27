#!/usr/bin/env python3
"""Compare two arms of the doctrine-effect benchmark, and say how sure the comparison can be.

`run.py` prints a pass rate per (case, arm). A rate is not a comparison: "real 67%, weak 33%" over
six cases can be noise, and nothing said so (#1384). This reads one or more `aggregate-result.json`
files and, for each pair of arms:

  * pairs the arms BY CASE. Runs of one case share a prompt and a scaffold, so they are not
    independent samples; each case's valid runs are averaged into one rate, and the case is the
    unit the bootstrap resamples. Treating 18 runs as 18 samples would shrink the interval by a
    factor the data has not earned.
  * reports the mean per-case delta (B - A) and a percentile-bootstrap CI over cases.
  * names a winner ONLY when the CI excludes 0. Otherwise it says the difference is not
    detectable, and prints the CI half-width as the resolution: an effect smaller than that is
    indistinguishable from none at this n. A null from an underpowered design is not a finding
    that the doctrine is inert.
  * lists every case B did worse on, even when the mean improves -- an aggregate win must not
    hide a regression on one case (the same reason SkillOpt-Sleep's gate reports task deltas).
  * `--motivated-by CASE` (#1385): a case that led to a doctrine edit cannot certify that edit,
    because the edit was written to make it pass. Those cases are removed from the evidence, and
    if no remaining case moved, the verdict is UNVERIFIED rather than a win.

Known limitation, stated rather than discovered: a percentile bootstrap over few clusters runs
NARROW (under-covers), so at n=6 the reported CI is optimistic. It errs toward claiming an effect,
which is why the verdict also needs the CI to exclude 0 rather than merely lean.

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
import json
import random
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ALPHA = 0.05
DEFAULT_BOOT = 10_000
MAX_BOOT = 1_000_000

# The condition keys two result files must agree on before their runs may be pooled. A number
# without its conditions is not evidence (evals/README.md); a number from two conditions averaged
# together is worse, because it looks like one.
POOLED_CONDITIONS = ("model", "marketplace_version", "tools")


class CompareError(ValueError):
    """Input that cannot be compared honestly. Refused, never coerced."""


@dataclass
class Comparison:
    a: str
    b: str
    n_cases: int
    mean_delta: float | None
    ci_low: float | None
    ci_high: float | None
    resolution: float | None     # CI half-width
    verdict: str                 # b_better | b_worse | not_detectable | unverified | insufficient
    per_case: dict[str, float] = field(default_factory=dict)       # case -> B rate - A rate
    regressions: list[str] = field(default_factory=list)           # cases where B < A
    excluded_no_data: list[str] = field(default_factory=list)      # no valid run in one arm
    excluded_motivated: list[str] = field(default_factory=list)    # #1385


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
        conditions = payload.get("conditions") or {}
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
# Comparing
# --------------------------------------------------------------------------

def bootstrap_ci(deltas: list[float], *, boot: int, seed: int,
                 alpha: float = ALPHA) -> tuple[float, float]:
    """Percentile CI on the mean, resampling whole cases with replacement."""
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    lo = means[int((alpha / 2) * boot)]
    hi = means[min(boot - 1, int((1 - alpha / 2) * boot))]
    return lo, hi


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

    result = Comparison(a=a, b=b, n_cases=len(evidence), mean_delta=None, ci_low=None,
                        ci_high=None, resolution=None, verdict="insufficient",
                        per_case=per_case, regressions=regressions,
                        excluded_no_data=no_data, excluded_motivated=excluded_motivated)
    if len(evidence) < 2:
        return result  # one case cannot be resampled into an interval

    deltas = [evidence[c] for c in sorted(evidence)]
    lo, hi = bootstrap_ci(deltas, boot=boot, seed=seed)
    result.mean_delta = sum(deltas) / len(deltas)
    result.ci_low, result.ci_high = lo, hi
    result.resolution = (hi - lo) / 2
    if motivated and not any(evidence.values()):
        # #1385: every case that moved is one the edit was written for. Circular, so abstain.
        result.verdict = "unverified"
    elif lo > 0:
        result.verdict = "b_better"
    elif hi < 0:
        result.verdict = "b_worse"
    else:
        result.verdict = "not_detectable"
    return result


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

VERDICT_TEXT = {
    "b_better": "{b} beats {a}: the CI excludes 0",
    "b_worse": "{b} is worse than {a}: the CI excludes 0",
    "not_detectable": "no detectable difference -- NOT evidence that the arms are equal; "
                      "an effect under the resolution is invisible at this n",
    "unverified": "UNVERIFIED -- every case that moved is one the edit was written for "
                  "(--motivated-by), so it cannot certify the edit",
    "insufficient": "insufficient data -- fewer than 2 comparable cases",
}


def format_text(c: Comparison) -> str:
    lines = [f"{c.b} vs {c.a}: {VERDICT_TEXT[c.verdict].format(a=c.a, b=c.b)}"]
    if c.mean_delta is not None:
        lines.append(f"  mean per-case delta {c.mean_delta:+.3f}  "
                     f"95% CI [{c.ci_low:+.3f}, {c.ci_high:+.3f}]  "
                     f"resolution +/-{c.resolution:.3f}  over {c.n_cases} case(s)")
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
    args = parser.parse_args(argv[1:])
    if args.selftest:
        return selftest()

    try:
        if not 1 <= args.boot <= MAX_BOOT:
            raise CompareError(f"--boot must be between 1 and {MAX_BOOT}")
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

    cases = [f"c{i}" for i in range(8)]

    # A large, uniform effect: every case fails under weak and passes under real.
    strong = _runs({"weak": {c: [False] * 3 for c in cases},
                    "real": {c: [True] * 3 for c in cases}})
    r = compare(strong, "weak", "real", boot=2000)
    check("strong effect is detected", r.verdict == "b_better", r)
    check("strong effect delta is 1.0", r.mean_delta == 1.0, r.mean_delta)

    # The same effect reversed is a regression, not a win.
    r = compare(strong, "real", "weak", boot=2000)
    check("reversed strong effect reads worse", r.verdict == "b_worse", r.verdict)

    # A/A: an arm against itself must be exactly zero with a CI containing 0 -- and must NOT be
    # called a win. (A `lo >= 0` verdict would.)
    r = compare(strong, "real", "real", boot=2000)
    check("A/A delta is 0", r.mean_delta == 0.0, r.mean_delta)
    check("A/A CI contains 0", r.ci_low <= 0 <= r.ci_high, (r.ci_low, r.ci_high))
    check("A/A is not a win", r.verdict == "not_detectable", r.verdict)

    # Mixed direction: the mean is positive but the CI straddles 0.
    mixed = _runs({"weak": {"c0": [False] * 3, "c1": [True] * 3, "c2": [False] * 3,
                            "c3": [True] * 3, "c4": [False] * 3, "c5": [True] * 3},
                   "real": {"c0": [True] * 3, "c1": [False] * 3, "c2": [True] * 3,
                            "c3": [True] * 3, "c4": [True] * 3, "c5": [False] * 3}})
    r = compare(mixed, "weak", "real", boot=2000)
    check("mixed effect is not a win", r.verdict == "not_detectable", r)
    check("resolution is reported", r.resolution is not None and r.resolution > 0, r.resolution)

    # A regression on one case survives an aggregate win.
    hidden = _runs({"weak": {**{c: [False] * 3 for c in cases[:7]}, "c7": [True] * 3},
                    "real": {**{c: [True] * 3 for c in cases[:7]}, "c7": [False] * 3}})
    r = compare(hidden, "weak", "real", boot=2000)
    check("aggregate still wins", r.verdict == "b_better", r.verdict)
    check("one-case regression is listed despite the win", r.regressions == ["c7"], r.regressions)

    # INVALID runs are excluded, not scored as failures.
    invalid = _runs({"weak": {"c0": [False, None, None], "c1": [False] * 3},
                     "real": {"c0": [True, None, None], "c1": [True] * 3}})
    check("invalid runs do not dilute the rate",
          case_rates(invalid, "real") == {"c0": 1.0, "c1": 1.0}, case_rates(invalid, "real"))

    # A case with no valid run in one arm is excluded and named, not counted as 0.
    one_sided = _runs({"weak": {"c0": [False] * 3, "c1": [False] * 3, "c2": [None] * 3},
                       "real": {"c0": [True] * 3, "c1": [True] * 3, "c2": [True] * 3}})
    r = compare(one_sided, "weak", "real", boot=2000)
    check("a case with no valid run in one arm is excluded",
          r.excluded_no_data == ["c2"] and "c2" not in r.per_case, r)

    # Fewer than two comparable cases cannot make an interval.
    single = _runs({"weak": {"c0": [False] * 3}, "real": {"c0": [True] * 3}})
    r = compare(single, "weak", "real", boot=2000)
    check("one case is insufficient", r.verdict == "insufficient" and r.ci_low is None, r)

    # #1385: the effect lives only on the case that motivated the edit.
    only_motivated = _runs({"weak": {c: [False] * 3 for c in cases},
                            "real": {"c0": [True] * 3, **{c: [False] * 3 for c in cases[1:]}}})
    r = compare(only_motivated, "weak", "real", motivated=("c0",), boot=2000)
    check("an effect only on the motivating case is unverified", r.verdict == "unverified", r)
    check("the motivating case is removed from the evidence",
          r.excluded_motivated == ["c0"] and r.n_cases == 7, r)
    # Control on the same shape of input: the motivating case excluded, but others moved too.
    r = compare(strong, "weak", "real", motivated=("c0",), boot=2000)
    check("other cases moving still certify the edit", r.verdict == "b_better", r.verdict)
    try:
        compare(strong, "weak", "real", motivated=("c99",), boot=2000)
        check("an unknown --motivated-by case is refused", False, "accepted")
    except CompareError:
        check("an unknown --motivated-by case is refused", True)

    # Same seed, same interval.
    a1 = compare(mixed, "weak", "real", boot=500, seed=7)
    a2 = compare(mixed, "weak", "real", boot=500, seed=7)
    check("seeded bootstrap is reproducible", (a1.ci_low, a1.ci_high) == (a2.ci_low, a2.ci_high))

    # Malformed runs are refused rather than read as failures.
    for label, bad in (("valid run with no verdict", {"case_id": "c0", "arm": "real",
                                                      "valid": True, "passed": None}),
                       ("non-bool valid", {"case_id": "c0", "arm": "real",
                                           "valid": 1, "passed": True})):
        try:
            _check_run(bad, "fixture")
            check(f"refuses {label}", False, "accepted")
        except CompareError:
            check(f"refuses {label}", True)

    # Through the real entry point: files on disk, pooling, and condition refusal.
    with tempfile.TemporaryDirectory() as tmp:
        def write(name: str, runs: list[dict], model: str = "sonnet") -> Path:
            path = Path(tmp) / name
            path.write_text(json.dumps({"conditions": {"model": model,
                                                       "marketplace_version": "1.0.0",
                                                       "tools": "Read"},
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
            f3 = write("c.json", strong[half:], model="opus")
            check("main() refuses pooling different conditions",
                  main(["compare", str(f1), str(f3)]) == 2)
            check("main() refuses a missing arm",
                  main(["compare", *pair, "--a", "none", "--b", "real"]) == 2)
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
