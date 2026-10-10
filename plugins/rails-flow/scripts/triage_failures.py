#!/usr/bin/env python3
"""Say whose red each failing example is: NEW, PREEXISTING or FLAKY, with the evidence for a PR (#1567).

Run:  python3 triage_failures.py --output rspec-output.txt --ref origin/dev
      python3 triage_failures.py --output run.txt --rerun-cmd "bundle exec rspec --no-color {id}"
      python3 triage_failures.py --selftest

WHY THIS EXISTS. `test-runner` lists failures; it cannot say whether the branch caused one. This reads the
run's failing example ids and `dev_baseline.py`'s record of what was already red on dev, then:

    PREEXISTING  the id is in the baseline AND the baseline is fresh (measured at this branch's merge base)
    FLAKY        not in the baseline, and it PASSED on every one of `--reruns` reruns (default 2)
    NEW          everything else: not in the baseline, or it failed again, or the baseline cannot be trusted

NEW IS THE DEFAULT, AND THE ONLY THING THAT FAILS THE RUN. Every rule here errs toward calling a failure
the branch's own, because the opposite error hides a regression behind a label:

  * A STALE baseline claims nothing. A failure "already red on some other commit" is not evidence about
    this one, so with a stale baseline no failure is PREEXISTING, and the header says so.
  * FLAKY is never a quiet pass. It is reported with its rerun count (`2/2 reruns passed`) and listed
    in the evidence block; it does not turn the exit code green, it just stops being NEW. A failure that
    fails ONE of two reruns is NEW, with the count shown: it is not stable enough to call either way.
  * Ids are compared WHOLE. `./spec/a_spec.rb:1` in the baseline says nothing about `./spec/a_spec.rb:12`.
  * Reruns are foreground and one at a time, in `--cwd`, never in parallel: two reruns racing the same
    database turn a flake into a pair of fresh failures.

WHAT THIS DELIBERATELY DOES NOT DO. It does not retry NEW to turn it green, does not rerun PREEXISTING
(that costs time to learn nothing), and does not decide what to do about a flake: it names it.

EXIT CODES:  0 no NEW failure   1 at least one NEW failure   2 bad usage / unreadable input

Stdlib only. `--selftest` runs reruns through a local python one-liner, never a real suite.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_baseline as db  # noqa: E402

NEW, PREEXISTING, FLAKY = "NEW", "PREEXISTING", "FLAKY"
DEFAULT_RERUN = "bundle exec rspec --no-color {id}"


def rerun_passes(template: str, example_id: str, cwd: str | None) -> bool:
    """One foreground rerun of ONE example; True only when it exits 0. The id is one argv entry, so an id
    like `./spec/a_spec.rb[1:2]` is never re-split or interpreted by a shell."""
    argv = [example_id if part == "{id}" else part for part in shlex.split(template)]
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True).returncode == 0


def classify(failures: list[str], baseline: dict | None, fresh: bool, rerun, reruns: int) -> list[dict]:
    """One row per failing id: {id, klass, reruns, passed, note}. `rerun(id) -> bool`."""
    known = {db.normalise(i) for i in baseline["failures"]} if baseline else set()
    rows = []
    for example_id in failures:
        if fresh and example_id in known:
            rows.append({"id": example_id, "klass": PREEXISTING, "reruns": 0, "passed": 0, "note": ""})
            continue
        passed = 0
        for _ in range(reruns):
            if rerun(example_id):
                passed += 1
        if reruns and passed == reruns:
            rows.append({"id": example_id, "klass": FLAKY, "reruns": reruns, "passed": passed, "note": ""})
            continue
        note = "in the baseline, but the baseline is stale" if example_id in known else ""
        rows.append({"id": example_id, "klass": NEW, "reruns": reruns, "passed": passed, "note": note})
    return rows


def render(rows: list[dict], baseline: dict | None, fresh: bool, why: str) -> str:
    counts = {k: sum(1 for r in rows if r["klass"] == k) for k in (NEW, PREEXISTING, FLAKY)}
    head = ("baseline FRESH: " + why) if fresh else ("baseline STALE, so nothing is PREEXISTING: " + why)
    if baseline is None:
        head = "NO BASELINE, so nothing is PREEXISTING: " + why
    out = [f"### Failure triage: {counts[NEW]} NEW, {counts[PREEXISTING]} PREEXISTING, {counts[FLAKY]} FLAKY", "", head, ""]
    for klass in (NEW, FLAKY, PREEXISTING):
        group = [r for r in rows if r["klass"] == klass]
        if not group:
            continue
        out.append(f"**{klass}**")
        for r in group:
            extra = f" ({r['passed']}/{r['reruns']} reruns passed)" if r["reruns"] else ""
            note = f" [{r['note']}]" if r["note"] else ""
            out.append(f"- `{r['id']}`{extra}{note}")
        out.append("")
    if not rows:
        out.append("No failing examples in this run.")
    return "\n".join(out).rstrip() + "\n"


def triage(output: str, baseline_path: Path, ref: str, template: str, reruns: int, cwd: str | None):
    failures = db.parse_failures(output)
    if failures is None:
        return None, "could not read an RSpec result from that output"
    baseline = db.read_baseline(baseline_path)
    fresh, why = False, f"no readable baseline at {baseline_path}"
    if baseline is not None:
        try:
            fresh, why = db.freshness(baseline, ref, cwd=cwd)
        except RuntimeError as err:
            fresh, why = False, str(err)
    rows = classify(failures, baseline, fresh, lambda i: rerun_passes(template, i, cwd), reruns)
    return render(rows, baseline, fresh, why), (1 if any(r["klass"] == NEW for r in rows) else 0)


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # The five cases the issue names. One baseline, one rerun function that passes only the flaky id.
    baseline = {"version": 1, "commit": "c1", "failures": ["./spec/old_spec.rb:5", "./spec/sub_spec.rb:1"]}
    failures = ["./spec/new_spec.rb:9", "./spec/old_spec.rb:5", "./spec/flaky_spec.rb:3", "./spec/sub_spec.rb:12"]
    seen = []

    def rerun(example_id: str) -> bool:
        seen.append(example_id)
        return example_id == "./spec/flaky_spec.rb:3"

    rows = {r["id"]: r for r in classify(failures, baseline, True, rerun, 2)}
    expect("an id that fails again and is not in the baseline is NEW", rows["./spec/new_spec.rb:9"]["klass"] == NEW)
    expect("an id in a fresh baseline is PREEXISTING", rows["./spec/old_spec.rb:5"]["klass"] == PREEXISTING)
    expect("an id that passes both reruns is FLAKY", rows["./spec/flaky_spec.rb:3"]["klass"] == FLAKY)
    expect("FLAKY carries its rerun count", rows["./spec/flaky_spec.rb:3"]["passed"] == 2
           and rows["./spec/flaky_spec.rb:3"]["reruns"] == 2)
    expect("an id that is only a substring-prefix of a baseline id is NEW, not PREEXISTING",
           rows["./spec/sub_spec.rb:12"]["klass"] == NEW)
    expect("PREEXISTING is not rerun (it costs time and proves nothing)", "./spec/old_spec.rb:5" not in seen)
    expect("each NEW/FLAKY id is rerun exactly `reruns` times", seen.count("./spec/new_spec.rb:9") == 2)

    stale = {r["id"]: r for r in classify(failures, baseline, False, rerun, 2)}
    expect("with a STALE baseline nothing is PREEXISTING", all(r["klass"] != PREEXISTING for r in stale.values()))
    expect("...and an id the stale baseline names is NEW with the reason shown",
           stale["./spec/old_spec.rb:5"]["klass"] == NEW and "stale" in stale["./spec/old_spec.rb:5"]["note"])

    # One of two reruns passing is not stable enough to call a flake. It must stay NEW, with the count.
    half = {"n": 0}

    def once(_id: str) -> bool:
        half["n"] += 1
        return half["n"] == 1

    only = classify(["./spec/half_spec.rb:1"], None, False, once, 2)[0]
    expect("a failure that fails one of two reruns is NEW, with 1/2 shown", only["klass"] == NEW and only["passed"] == 1)
    expect("no baseline at all claims no PREEXISTING",
           classify(["./spec/old_spec.rb:5"], None, False, lambda _i: False, 2)[0]["klass"] == NEW)
    expect("zero reruns never calls anything FLAKY",
           classify(["./spec/x_spec.rb:1"], None, False, lambda _i: True, 0)[0]["klass"] == NEW)

    text = render(list(rows.values()), baseline, True, "measured at the merge base c1")
    expect("the evidence block names every class and the rerun count",
           "NEW" in text and "FLAKY" in text and "PREEXISTING" in text and "2/2 reruns passed" in text)
    expect("a stale header says nothing is PREEXISTING",
           "STALE, so nothing is PREEXISTING" in render(list(stale.values()), baseline, False, "x"))

    # The reruns really are one argv entry per id and really exit-coded: a python one-liner stands in for rspec.
    expect("a rerun that exits 0 passes",
           rerun_passes(f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(0)' {{id}}", "./a[1:2]", None))
    expect("a rerun that exits 1 fails",
           not rerun_passes(f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(1)' {{id}}", "./a[1:2]", None))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            result, _ = triage("Segmentation fault\n", Path(tmp) / "none.json", "main", DEFAULT_RERUN, 2, tmp)
        except Exception:  # a crash on unreadable input is the same failure, reported under its own label
            result = "crashed"
        expect("unreadable output is refused, not triaged as clean", result is None)
        failing = f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(1)' {{id}}"
        passing = f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(0)' {{id}}"
        one = "Failed examples:\n\nrspec ./spec/e_spec.rb:2 # e\n"
        _, code_new = triage(one, Path(tmp) / "none.json", "main", failing, 2, tmp)
        _, code_flaky = triage(one, Path(tmp) / "none.json", "main", passing, 2, tmp)
        expect("the exit code is 1 when a NEW failure exists", code_new == 1)
        expect("a FLAKY-only run exits 0 (named in the block, not a failure)", code_flaky == 0)

    if bad:
        print(f"triage_failures selftest FAILED ({len(bad)} of {ok + len(bad)}):", file=sys.stderr)
        for label in bad:
            print(f"  - {label}", file=sys.stderr)
        return 1
    print(f"triage_failures selftest ok: {ok} checks")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    ap.add_argument("--output", help="the RSpec output to triage (a file)")
    ap.add_argument("--baseline", default=db.DEFAULT_BASELINE)
    ap.add_argument("--ref", default="origin/dev")
    ap.add_argument("--rerun-cmd", default=DEFAULT_RERUN, help="one example per run; {id} is the example id")
    ap.add_argument("--reruns", type=int, default=2)
    ap.add_argument("--cwd", default=None)
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.output:
        ap.print_usage(sys.stderr)
        return 2
    try:
        output = Path(args.output).read_text()
    except OSError as err:
        print(f"triage_failures: {err}", file=sys.stderr)
        return 2
    text, code = triage(output, Path(args.baseline), args.ref, args.rerun_cmd, args.reruns, args.cwd)
    if text is None:
        print(f"triage_failures: {code}", file=sys.stderr)
        return 2
    print(text, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
