#!/usr/bin/env python3
"""Say whose red each failing example is: NEW, PREEXISTING or PASSED ALONE, with the evidence for a PR (#1567).

Run:  python3 triage_failures.py --output rspec-output.txt --ref origin/dev
      python3 triage_failures.py --output run.txt --rerun-cmd "bundle exec rspec --no-color {id}"
      python3 triage_failures.py --selftest

WHY THIS EXISTS. `test-runner` lists failures; it cannot say whether the branch caused one. This reads the
run's failing example ids and `dev_baseline.py`'s record of what was already red on dev, then:

    PREEXISTING  the id is in the baseline, the baseline is fresh (measured at this branch's merge base), AND this
                 branch did not change that spec file (`git diff --name-only <merge-base>`, committed or not)
    PASSED ALONE not in the baseline, and it PASSED on every one of `--reruns` reruns (default 2), each one a
                 run of that single example whose output says `1 example, 0 failures`
    NEW          everything else: not in the baseline, or it failed again, or the baseline cannot be trusted

NEW IS THE DEFAULT, AND PASSED ALONE IS NOT A PASS. Every rule here errs toward calling a failure the branch's
own, because the opposite error hides a regression behind a label:

  * A STALE baseline claims nothing. A failure "already red on some other commit" is not evidence about this
    one, so with a stale baseline no failure is PREEXISTING, and the header says so.
  * A baseline entry is only evidence about a spec this branch did not edit. A spec the branch changed may be
    red because of that change, whatever dev's record says; it is rerun like any other id.
  * PASSED ALONE is not "flaky". An example that failed in the suite and passes by itself is also what an
    ORDER-DEPENDENT regression looks like (state one example leaks into the next), and a lone rerun cannot tell
    the two apart. It is reported with its rerun count (`2/2 reruns passed`), listed in the evidence block,
    and it FAILS THE RUN like NEW: someone has to look. A failure that fails ONE of two reruns is NEW.
  * A rerun passes only when it exits 0 AND says `1 example, 0 failures`. A rerun that matched no example
    (`0 examples, 0 failures`: a renamed spec, a bad id) exits 0 and proves nothing.
  * Ids are compared WHOLE. `./spec/a_spec.rb:1` in the baseline says nothing about `./spec/a_spec.rb:12`.
  * A run with errors outside of examples (a spec file failed to load) is refused, not triaged: its examples
    never ran, so nothing in it can be called PREEXISTING or PASSED ALONE.
  * Reruns are foreground and one at a time, in `--cwd`, never in parallel: two reruns racing the same
    database turn an order problem into a pair of fresh failures.

WHAT THIS DELIBERATELY DOES NOT DO. It does not retry NEW to turn it green, does not rerun PREEXISTING
(that costs time to learn nothing), and does not decide what a PASSED ALONE example means: it names it.

EXIT CODES:  0 no NEW and no PASSED ALONE failure   1 at least one of either   2 bad usage / unreadable input

Stdlib only. `--selftest` runs reruns through a local python one-liner, never a real suite.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_baseline as db  # noqa: E402

NEW, PREEXISTING, PASSED_ALONE = "NEW", "PREEXISTING", "PASSED ALONE"
# The classes that fail the run. PASSED ALONE is one of them: it is not evidence the failure was nothing.
BLOCKING = (NEW, PASSED_ALONE)
# NOTHING MAY FOLLOW THE SUMMARY'S FAILURE COUNT: `1 example, 0 failures, 1 pending` exits 0 and matches a bare
# prefix, but a pending example never ran its body (#1830). The same goes for `, 1 error occurred outside of examples`.
PASS_LINE = re.compile(r"\b1 example, 0 failures?(?![\w,])")
DEFAULT_RERUN = "bundle exec rspec --no-color {id}"


def rerun_passes(template: str, example_id: str, cwd: str | None) -> bool:
    """One foreground rerun of ONE example; True only when it exits 0 AND its output says `1 example, 0 failures`. The id is one argv entry, so an id
    like `./spec/a_spec.rb[1:2]` is never re-split or interpreted by a shell."""
    argv = [example_id if part == "{id}" else part for part in shlex.split(template)]
    done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return done.returncode == 0 and bool(PASS_LINE.search(db.ANSI.sub("", done.stdout + "\n" + done.stderr)))


def classify(failures: list[str], baseline: dict | None, fresh: bool, rerun, reruns: int,
             touched: set[str] | None = None) -> list[dict]:
    """One row per failing id: {id, klass, reruns, passed, note}. `rerun(id) -> bool`."""
    known = {db.normalise(i) for i in baseline["failures"]} if baseline else set()
    # `touched` None means the branch's changed files could not be read: nothing is then provably untouched.
    rows = []
    for example_id in failures:
        if fresh and example_id in known and touched is not None and db.file_of(example_id) not in touched:
            rows.append({"id": example_id, "klass": PREEXISTING, "reruns": 0, "passed": 0, "note": ""})
            continue
        passed = 0
        for _ in range(reruns):
            if rerun(example_id):
                passed += 1
        if reruns and passed == reruns:
            rows.append({"id": example_id, "klass": PASSED_ALONE, "reruns": reruns, "passed": passed, "note": ""})
            continue
        note = ""
        if example_id in known:
            note = ("in the baseline, but the baseline is stale" if not fresh
                    else "in the baseline, but this branch changed that spec file" if touched is not None
                    and db.file_of(example_id) in touched else "in the baseline, but the branch's changed files are unknown")
        rows.append({"id": example_id, "klass": NEW, "reruns": reruns, "passed": passed, "note": note})
    return rows


def render(rows: list[dict], baseline: dict | None, fresh: bool, why: str) -> str:
    counts = {k: sum(1 for r in rows if r["klass"] == k) for k in (NEW, PASSED_ALONE, PREEXISTING)}
    head = ("baseline FRESH: " + why) if fresh else ("baseline STALE, so nothing is PREEXISTING: " + why)
    if baseline is None:
        head = "NO BASELINE, so nothing is PREEXISTING: " + why
    out = [f"### Failure triage: {counts[NEW]} NEW, {counts[PASSED_ALONE]} PASSED ALONE, {counts[PREEXISTING]} PREEXISTING", "", head, ""]
    for klass in (NEW, PASSED_ALONE, PREEXISTING):
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
        if db.has_outside_errors(output):
            return None, ("the run had errors outside of examples (a spec file failed to load), so some examples "
                          "never ran: nothing in it can be called PREEXISTING or PASSED ALONE")
        return None, "could not read an RSpec result from that output"
    baseline = db.read_baseline(baseline_path)
    fresh, why = False, f"no readable baseline at {baseline_path}"
    if baseline is not None:
        try:
            fresh, why = db.freshness(baseline, ref, cwd=cwd)
        except RuntimeError as err:
            fresh, why = False, str(err)
    touched = db.touched_files(ref, cwd=cwd) if fresh else None
    rows = classify(failures, baseline, fresh, lambda i: rerun_passes(template, i, cwd), reruns, touched)
    return render(rows, baseline, fresh, why), (1 if any(r["klass"] in BLOCKING for r in rows) else 0)


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # The cases the issue names, plus the review's. One baseline, one rerun function that passes only the lone id.
    baseline = {"version": 1, "commit": "c1", "failures": ["./spec/old_spec.rb:5", "./spec/sub_spec.rb:1"]}
    failures = ["./spec/new_spec.rb:9", "./spec/old_spec.rb:5", "./spec/lone_spec.rb:3", "./spec/sub_spec.rb:12"]
    seen = []

    def rerun(example_id: str) -> bool:
        seen.append(example_id)
        return example_id == "./spec/lone_spec.rb:3"

    untouched: set[str] = {"./README.md"}
    rows = {r["id"]: r for r in classify(failures, baseline, True, rerun, 2, untouched)}
    expect("an id that fails again and is not in the baseline is NEW", rows["./spec/new_spec.rb:9"]["klass"] == NEW)
    expect("an id in a fresh baseline, in a spec the branch did not touch, is PREEXISTING",
           rows["./spec/old_spec.rb:5"]["klass"] == PREEXISTING)
    expect("an id that passes both reruns is PASSED ALONE", rows["./spec/lone_spec.rb:3"]["klass"] == PASSED_ALONE)
    expect("PASSED ALONE carries its rerun count", rows["./spec/lone_spec.rb:3"]["passed"] == 2
           and rows["./spec/lone_spec.rb:3"]["reruns"] == 2)
    expect("an id that is only a substring-prefix of a baseline id is NEW, not PREEXISTING",
           rows["./spec/sub_spec.rb:12"]["klass"] == NEW)
    expect("PREEXISTING is not rerun (it costs time and proves nothing)", "./spec/old_spec.rb:5" not in seen)
    expect("each NEW/PASSED ALONE id is rerun exactly `reruns` times", seen.count("./spec/new_spec.rb:9") == 2)

    stale = {r["id"]: r for r in classify(failures, baseline, False, rerun, 2, untouched)}
    expect("with a STALE baseline nothing is PREEXISTING", all(r["klass"] != PREEXISTING for r in stale.values()))
    expect("...and an id the stale baseline names is NEW with the reason shown",
           stale["./spec/old_spec.rb:5"]["klass"] == NEW and "stale" in stale["./spec/old_spec.rb:5"]["note"])

    # #1567 review (3): a baseline entry says nothing about a spec the branch edited.
    edited = {r["id"]: r for r in classify(["./spec/old_spec.rb:5"], baseline, True, lambda _i: False, 2,
                                           {"./spec/old_spec.rb"})}
    expect("a baseline id in a spec file the branch changed is NOT PREEXISTING",
           edited["./spec/old_spec.rb:5"]["klass"] == NEW and "changed that spec file" in edited["./spec/old_spec.rb:5"]["note"])
    unknown = classify(["./spec/old_spec.rb:5"], baseline, True, lambda _i: False, 2, None)[0]
    expect("when the branch's changed files are unknown nothing is PREEXISTING", unknown["klass"] == NEW)

    # One of two reruns passing is not stable. It must stay NEW, with the count.
    half = {"n": 0}

    def once(_id: str) -> bool:
        half["n"] += 1
        return half["n"] == 1

    only = classify(["./spec/half_spec.rb:1"], None, False, once, 2)[0]
    expect("a failure that fails one of two reruns is NEW, with 1/2 shown", only["klass"] == NEW and only["passed"] == 1)
    expect("no baseline at all claims no PREEXISTING",
           classify(["./spec/old_spec.rb:5"], None, False, lambda _i: False, 2)[0]["klass"] == NEW)
    expect("zero reruns never calls anything PASSED ALONE",
           classify(["./spec/x_spec.rb:1"], None, False, lambda _i: True, 0)[0]["klass"] == NEW)

    text = render(list(rows.values()), baseline, True, "measured at the merge base c1")
    expect("the evidence block names every class and the rerun count",
           "NEW" in text and "PASSED ALONE" in text and "PREEXISTING" in text and "2/2 reruns passed" in text)
    expect("a stale header says nothing is PREEXISTING",
           "STALE, so nothing is PREEXISTING" in render(list(stale.values()), baseline, False, "x"))

    # The reruns really are one argv entry per id and really judged by their OUTPUT: a python one-liner stands in
    # for rspec. (4) a rerun passes only when it says `1 example, 0 failures`, not on an exit code alone.
    py = shlex.quote(sys.executable)
    good = f"{py} -c 'print(\"1 example, 0 failures\")' {{id}}"
    nothing_ran = f"{py} -c 'print(\"0 examples, 0 failures\")' {{id}}"
    exits_one = f"{py} -c 'import sys; print(\"1 example, 0 failures\"); sys.exit(1)' {{id}}"
    expect("a rerun that exits 0 and says `1 example, 0 failures` passes", rerun_passes(good, "./a[1:2]", None))
    expect("a rerun that exits 0 but matched no example does NOT pass", not rerun_passes(nothing_ran, "./a[1:2]", None))
    expect("a rerun that exits 1 fails whatever it printed", not rerun_passes(exits_one, "./a[1:2]", None))
    # #1830: a pending example exits 0 and prints the same prefix, but did not pass.
    pending = f"{py} -c 'print(\"1 example, 0 failures, 1 pending\")' {{id}}"
    expect("a rerun whose only example is pending does NOT pass", not rerun_passes(pending, "./a[1:2]", None))
    load_err = f"{py} -c 'print(\"1 example, 0 failures, 1 error occurred outside of examples\")' {{id}}"
    expect("a rerun with an error outside of examples does NOT pass", not rerun_passes(load_err, "./a[1:2]", None))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            result, _ = triage("Segmentation fault\n", Path(tmp) / "none.json", "main", DEFAULT_RERUN, 2, tmp)
        except Exception:  # a crash on unreadable input is the same failure, reported under its own label
            result = "crashed"
        expect("unreadable output is refused, not triaged as clean", result is None)
        # (1) a dev that fails to LOAD: refused, and the message says why.
        load_error = ("An error occurred while loading ./spec/x_spec.rb.\n"
                      "0 examples, 0 failures, 1 error occurred outside of examples\n")
        try:
            text_lo, _ = triage(load_error, Path(tmp) / "none.json", "main", good, 2, tmp)
        except Exception:
            text_lo = "crashed"
        expect("a run with errors outside of examples is refused, not triaged as clean", text_lo is None)
        one = "Failed examples:\n\nrspec ./spec/e_spec.rb:2 # e\n"
        _, code_new = triage(one, Path(tmp) / "none.json", "main", exits_one, 2, tmp)
        _, code_alone = triage(one, Path(tmp) / "none.json", "main", good, 2, tmp)
        expect("the exit code is 1 when a NEW failure exists", code_new == 1)
        expect("a PASSED ALONE-only run exits 1, not 0", code_alone == 1)

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
