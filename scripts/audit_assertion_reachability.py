#!/usr/bin/env python3
"""Report selftest assertions that no declared mutation can make fail (#1040).

Run:  python3 scripts/audit_assertion_reachability.py                  # every guard
      python3 scripts/audit_assertion_reachability.py --guard route_coverage
      python3 scripts/audit_assertion_reachability.py --selftest       # prove THIS can fail

WHY THIS EXISTS. `scripts/mutation_check.py` proves every **declared mutation** is caught by the
right fixture. That is a strong guarantee and it is not this one: it says the mutations we wrote
down are caught, not that every assertion we wrote down is capable of failing. An assertion no
mutation reaches is invisible to it.

The instance that prompted it (#1037, generalised by #1040). `route_coverage_selftest.py` carried
what read as the guard for the covered axis:

    check("attribution: never-visited route uncovered", cov["DELETE /users/:id"].covered, False)

It passed **vacuously**. The fixture's evidence held `/users/42/edit` and `/users`; neither matches
`/users/:id`, so the route was uncovered because it was never a *candidate*, not because its verb
was weighed. It read identically before and after the fix, while the real defect credited 78 of 201
routes on a live app. `skills/code-review/SKILL.md` already names the class --
`gate-that-cannot-fail` -- but only as something a human reviewer should notice.

HOW REACHABILITY IS DECIDED, AND THE TRAP THAT SHAPED IT. The first attempt at this asked, for each
negative assertion, whether any fixture path matched the route pattern -- and judged that using
`compile_pattern`, the matcher under test. Every assertion guarding the matcher itself then looked
vacuous, producing a false positive on a genuine negative. That is the same shape as a fixture that
recomputes the filter it is checking.

So reachability is not computed. It is **observed**: a label is reachable if the selftest, run
against a mutant, actually reported that label as failing. Nothing here re-implements any subject's
logic, and nothing parses a subject at all -- only the declared mutation list and the selftest's own
output, both of which are data this repo already keeps.

A label is matched in the output by substring, case-insensitively -- the same test
`mutation_check.py` already applies to `Mutation.expects`. Reusing its rule rather than inventing a
second one matters: two derivations of "did this fixture fire" would drift, and the one that drifted
would be the one nobody was reading.

WHAT A FINDING MEANS, AND WHY THIS DOES NOT GATE. A label reported here is *unreached by any
declared mutation*. That is two different things wearing one face:

  * genuinely vacuous -- the assertion cannot fail, and is a gate that cannot fail
  * merely unguarded -- the assertion is fine and nobody has written the mutation that trips it

**This tool cannot tell them apart, and says so rather than guessing.** A first run lists mostly the
second kind, and that list is the useful output. Turning it into a gate before anyone has read the
baseline would produce a carve-out, so it exits 0 on findings by design. Ratchet it once the
baseline is known, per this repo's own rule that a floor is ratcheted and never set.

THE DENOMINATOR IS REPORTED, NOT ASSUMED. A guard whose selftest declares labels this parser cannot
read would otherwise report "0 unreachable" and look perfect. Every guard states how many labels
were enumerated, and a guard where that is **zero** is reported as `UNREADABLE` -- a skip, not a
pass. Percentages over a denominator nobody checked is the failure this repo keeps hitting.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_check as mc  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# The three call shapes this repo's selftests use to name an assertion. Each maps to where the
# human-readable label sits: a positional index, or a keyword.
#
# Deliberately a closed list. A generated guess at "which argument is the label" would quietly
# enumerate the wrong strings for a shape it had not seen, and an inventory that is wrong in the
# silent direction is exactly what makes a reachability report read clean over nothing examined.
LABEL_CALLS: dict[str, object] = {
    "scenario": 0,        # scripts/lint_self_consistency.py    scenario("label", files=..., ...)
    "check": 0,           # *_selftest.py                       check("label", got, want)
    "expect": "label",    # plugins/rails-flow/...selftest.py    expect(rule, files, label="...")
}


def labels_in(source: str) -> tuple[list[str], list[int]]:
    """Every assertion label declared in one selftest, plus the lines it could not read.

    Structural, via `ast` -- not a regex over the text. A label is a STRING LITERAL argument, so an
    f-string or a name is reported as unreadable rather than skipped: a call this cannot enumerate
    is a hole in the denominator and has to be visible.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    labels, unreadable = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        where = LABEL_CALLS.get(node.func.id)
        if where is None:
            continue
        arg = None
        if isinstance(where, int):
            if len(node.args) > where:
                arg = node.args[where]
        else:
            arg = next((k.value for k in node.keywords if k.arg == where), None)
        if arg is None:
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            labels.append(arg.value)
        else:
            unreadable.append(node.lineno)
    return labels, unreadable


def mutant_outputs(guard: mc.Guard) -> tuple[list[str], list[str]]:
    """Run every declared mutation; return each mutant's combined output, plus any problems.

    The BASELINE is not re-checked here. `mutation_check.py` owns that verdict and runs in the same
    sweep; duplicating it would be a second derivation of the same fact, and an inert baseline shows
    up there as a hard failure rather than as silence here.
    """
    outputs, problems = [], []
    for mutation in guard.mutations:
        workdir = Path(tempfile.mkdtemp(prefix=f"reach-{guard.name}-"))
        try:
            entry = mc.apply_mutation(guard, mutation, workdir)
            argv = [sys.executable, str(entry)]
            if guard.selftest == guard.subject:
                argv.append("--selftest")
            result = subprocess.run(argv, cwd=workdir, capture_output=True,
                                    text=True, timeout=300)
            outputs.append(result.stdout + result.stderr)
        except subprocess.TimeoutExpired:
            problems.append(f"{guard.name}: {mutation.name!r} timed out")
        except RuntimeError as exc:
            # A stale anchor. mutation_check reports this as a hard error; here it means one
            # mutation contributed no evidence, which would make labels look unreachable that
            # simply were not exercised. Naming it keeps that distinction visible.
            problems.append(f"{guard.name}: {mutation.name!r} could not be applied -- {exc}")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return outputs, problems


# ---------------------------------------------------------------------------------------
# Discrimination: does this suite tell a RIGHT implementation from a WRONG one? (#1048)
# ---------------------------------------------------------------------------------------
# The reachability audit above measures a suite against **the mutations somebody wrote**, so it
# carries whoever's imagination wrote them. That is the same objection it exists to raise, one
# level up. This mode answers a different question with no imagination in it at all:
#
#     run the CURRENT selftest against the implementation it REPLACED.
#
# A case that fails there **discriminates** -- it can tell a right implementation from a known-wrong
# one. A case that passes there does not, at least not against that particular wrongness. The old
# implementation is already in git, so no wrong version has to be constructed: `git show
# <rev>:<subject>` is the entire cost.
#
# WORKED EXAMPLE, measured by hand before this tool existed (#1048). A code generator's parser was
# replaced after it was found able to emit a wrong answer with exit 0, and a six-case selftest was
# written alongside. Run against the old parser: **5 of 6 failed, 1 passed.** A suite that passed
# for every implementation would have proved nothing; five cases that fail against a known-wrong
# one is what makes it evidence rather than decoration.
#
# The five failures were five DIFFERENT wrong answers, which is better evidence than the count:
# a key invented from a multi-line keyword argument, a list truncated 4 -> 1 by a closing brace in
# a comment, the same truncation from a brace in a string, keys hoisted out of a heredoc body, and
# a `**splat` dropped silently with exit 0. A suite whose failures are all the same shape is
# probing one bug six ways; these probe distinct behaviours.
#
# THE TRAP, AND WHY THIS REPORTS RATHER THAN GATES. "1 of 6 does not discriminate" reads as "delete
# it", and in that example it was **wrong**. The sixth asserted that a nested hash is not hoisted
# --- `{a:, nested: {inner_one:, inner_two:}, b:}` must yield `[a, nested, b]`. The old parser got
# that right **by accident of construction** (it tracked brace depth, so nested keys were already
# below depth 0); the new one gets it right **by construction** (it reads the AST and asks for the
# hash's own elements). The two are correct there for unrelated reasons, and a third implementation
# --- a line-oriented reader matching `^\s*(\w+):` --- would fail it immediately.
#
# So the case is not measuring the difference between THESE two. It holds a property any future
# implementation could plausibly break, which generalises to the rule this mode has to be read
# with:
#
#     A non-discriminating case is one the predecessor also satisfied,
#     and the predecessor is a sample of size one.
#
# Deleting a case on this number alone selects the suite against the only wrong implementation you
# happen to have had. Nothing mechanical separates "decoration" from "guards a regression this
# comparison cannot see", so a gate here would fail honest guards --- which is how a useful
# instrument gets switched off in a week.
#
# So the convention ships WITH the number, printed by the report rather than described in a
# changelog nobody re-reads: a case whose label carries the marker below is counted in its own
# bucket instead of against the suite.
REGRESSION_GUARD_MARKER = "[regression guard]"

# THE PRECONDITION THAT MAKES A PER-CASE RESULT MEAN ANYTHING. A split is only trustworthy if the
# current selftest HARNESS still fits the old subject. When it does not, cases fail for the wrong
# reason and the number inflates -- and you cannot tell afterwards which case was inapplicable and
# which genuinely failed, so a per-case "inapplicable" bucket would be a guess.
#
# The exit-code preflight below catches the loud version: the old subject is missing API the cases
# call, so nothing runs. It does NOT catch the quiet one. A real migration changed a function from
# taking file CONTENTS to taking a PATH -- same name, same arity, different meaning. No static
# check sees that; every case fails, and the run reports a flattering, false "all discriminate".
#
# So: mark ONE case in the suite as the control -- the canonical shape the subject exists to
# handle, whose expected outcome is the same under any implementation worth comparing. Run order is
# not the point; the control's OUTCOME is. If the control fails against the old revision, the
# harness does not fit and no split from that run is reportable. If it passes, the harness fits,
# and every other case's outcome is a real result rather than an artefact. The inapplicable bucket
# is then empty BY CONSTRUCTION rather than by assumption.
#
# The control must be a case the subject genuinely handles, never a tautology: one that passes for
# every implementation including a broken one tells you nothing.
CONTROL_MARKER = "[control]"


def reported_as_failing(output: str, label: str) -> bool:
    """Did the HARNESS report this label as a failing case? Anchored, never a substring test.

    TWO DEFECTS, ONE CAUSE (#1059, #1060). The original test was `label.lower() in output`, and a
    bare substring match is wrong in both directions at once:

      * **It counts a label the harness never reported.** A Python traceback prints the offending
        SOURCE LINE, so when the old revision dies on an `AttributeError` inside
        `check('some label', new_api(...))`, that label appears in stderr. `failing` becomes
        non-empty, the "did it run at all" preflight is skipped because it keys off `failing` being
        empty, and the tool reports `1 of 2 discriminate` over a run in which **not one case
        executed** -- the exact false verdict that preflight exists to prevent (#1059).
      * **It counts a label that is merely a PREFIX of another.** `'an unprobed target is named'`
        is a substring of `'an unprobed target is named as unprobed'`, so the shorter case reads as
        failing -- and therefore as discriminating -- whenever the longer one does, whether or not
        it ran. Measured on `dev`: 11 such collisions across two shipped tools (#1060).

    Both inflate the split in the flattering direction, which is the dangerous one: nobody audits a
    number that says their tests are good.

    So the match is anchored to the SHAPE A HARNESS REPORTS A FAILURE IN, which a traceback cannot
    forge: the label begins a reported unit -- at line start, after a `- ` bullet, or after a
    `<rule> / ` prefix -- and ENDS the unit, at end-of-line or immediately before the `:` that
    introduces the failure detail. A label sitting inside a source line, inside quotes, or in the
    middle of a longer label matches none of those.
    """
    pattern = re.compile(r"(?:^|[-*]\s|/\s)" + re.escape(label.strip().lower()) + r"(?=$|:)")
    return any(pattern.search(line.strip().lower()) for line in output.splitlines())


def subject_at(guard: mc.Guard, rev: str) -> str | None:
    """The guard's subject as it was at `rev`, or None if it cannot be read there."""
    r = subprocess.run(("git", "show", f"{rev}:{guard.subject}"),
                       cwd=REPO, capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def discriminate(guard: mc.Guard, rev: str) -> dict:
    """Split this guard's selftest labels by whether they fail against `rev`'s implementation.

    Only the SUBJECT is rolled back. The selftest stays current, because the question is whether
    **today's cases** can tell today's implementation from the old one -- rolling both back would
    just re-run the old suite against the old code and report what it reported then.
    """
    selftest = REPO / guard.selftest
    if not selftest.is_file():
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": f"selftest {guard.selftest} not found"}
    labels, unreadable_lines = labels_in(selftest.read_text(encoding="utf-8"))
    if not labels:
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": (f"no assertion labels could be enumerated from {guard.selftest}, so a "
                           f"split over them would mean nothing")}
    old = subject_at(guard, rev)
    if old is None:
        # NOT a pass. The subject may be newer than `rev`, renamed since, or `rev` may not exist.
        # Reporting "0 non-discriminating" here would be a clean bill of health for a comparison
        # that never happened.
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": f"{guard.subject} cannot be read at {rev} (new file, renamed, or bad rev)"}

    workdir = Path(tempfile.mkdtemp(prefix=f"discrim-{guard.name}-"))
    try:
        entry = mc.stage(guard, workdir)
        (workdir / guard.subject).write_text(old, encoding="utf-8")
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            # The selftest lives IN the subject, so rolling the subject back rolls the cases back
            # too and the comparison is meaningless. Say so rather than print a split of nothing.
            return {"guard": guard.name, "status": "UNREADABLE",
                    "reason": ("subject and selftest are the same file, so rolling the subject "
                               "back rolls the cases back with it — there is nothing to compare")}
        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": f"the selftest timed out against {rev}"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    output = result.stdout + result.stderr
    unique = sorted(set(labels))
    guards_ = [lab for lab in unique if REGRESSION_GUARD_MARKER in lab.lower()]
    rest = [lab for lab in unique
            if lab not in guards_ and CONTROL_MARKER not in lab.lower()]
    # `reported_as_failing`, never `in`. See its docstring: a substring test counts labels the
    # harness never reported (a traceback echoing a source line) and labels that are merely a
    # prefix of a longer one, and both inflate the split in the flattering direction.
    failing = [lab for lab in rest if reported_as_failing(output, lab)]
    passing = [lab for lab in rest if not reported_as_failing(output, lab)]

    # THE TRAP THIS TOOL EXISTS TO FIND, FOUND IN THIS TOOL ON ITS FIRST REAL RUN. A selftest that
    # CRASHES against the old subject -- because today's cases call functions that did not exist
    # then, so it dies on an AttributeError before a single case runs -- emits no labels at all.
    # Every label is then "not in the output", and the split reads **0 of 55 discriminate**: a
    # confident verdict over a comparison that never happened. That is indistinguishable from a
    # suite that genuinely cannot tell the two apart, and it is the more likely of the two.
    #
    # The three states, separated by whether the selftest RAN:
    #
    #   exit 0                        -> the old implementation passed wholesale. Legitimate, and
    #                                    the loudest possible result: the suite proves nothing.
    #   exit != 0, some label present -> a real split; the cases ran and some failed.
    #   exit != 0, NO label present   -> it never ran. Not a split, and not a pass.
    #
    # An old subject missing today's API is the ORDINARY case when the change added functions, so
    # this is the common path, not an edge one.
    controls = [lab for lab in unique if CONTROL_MARKER in lab.lower()]
    failed_controls = [lab for lab in controls if reported_as_failing(output, lab)]
    if failed_controls:
        # The harness does not fit this revision. Refuse the whole split rather than report one
        # that cannot be trusted per case -- this is the quiet failure the exit code cannot see.
        return {"guard": guard.name, "status": "UNREADABLE", "rev": rev,
                "reason": (f"the control case failed against {rev}, so the current selftest's "
                           f"harness does not fit that revision: cases would fail for the wrong "
                           f"reason and the split would inflate. Failing control(s): "
                           f"{failed_controls}")}
    if result.returncode != 0 and not failing:
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": (f"the selftest did not run against {rev} — it exited "
                           f"{result.returncode} without reporting a single case, which means it "
                           f"failed to load rather than failing to discriminate. Today's cases "
                           f"probably call API that {rev} does not have. Comparing these two "
                           f"revisions needs a rev where the selftest can at least execute."),
                "rev": rev}
    return {
        "guard": guard.name,
        "status": "ok",
        "rev": rev,
        # A selftest that PASSES wholesale against the old implementation is the headline result,
        # not a footnote: it means the suite cannot tell the two apart at all.
        "old_selftest_passed": result.returncode == 0,
        "labels": len(unique),
        "discriminating": failing,
        "non_discriminating": passing,
        "declared_regression_guards": guards_,
        # No control means the split is unverified rather than wrong. Saying so is the difference
        # between a caveat and a silent assumption.
        "controls": controls,
        "unreadable_label_lines": unreadable_lines,
    }


def report_discrimination(results: list[dict], as_json: bool) -> int:
    if as_json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for r in sorted(results, key=lambda x: x["guard"]):
        if r["status"] == "UNREADABLE":
            print(f"[skip] {r['guard']}: {r['reason']}")
            continue
        d, n = len(r["discriminating"]), len(r["non_discriminating"])
        print(f"[note] {r['guard']}: {d} of {d + n} case(s) discriminate against {r['rev']}")
        if not r.get("controls"):
            print(f"         ! no case is marked {CONTROL_MARKER}, so nothing verified that the "
                  f"current harness still fits {r['rev']} — this split is unverified, not wrong")
        # #1061. Computed at the top of `discriminate` and, until now, never printed here -- so a
        # suite whose labels are f-strings got a confident "3 of 4 discriminate" over a denominator
        # with holes nobody was told about. The uncounted cases are precisely the ones a reader
        # wants flagged. Same shape `report()` already uses, because two renderings of one fact
        # drift and the drifted one is what somebody reads.
        if r.get("unreadable_label_lines"):
            print(f"         ! {len(r['unreadable_label_lines'])} label(s) not literal strings, "
                  f"at line(s) {r['unreadable_label_lines']} -- not counted either way")
        if r["old_selftest_passed"]:
            print("         ! the OLD implementation passed this selftest WHOLESALE — the suite "
                  "cannot tell the two apart at all")
        for lab in r["non_discriminating"]:
            print(f"         does not discriminate: {lab}")
        if r["declared_regression_guards"]:
            print(f"         {len(r['declared_regression_guards'])} case(s) declared "
                  f"{REGRESSION_GUARD_MARKER} and excluded from the split:")
            for lab in r["declared_regression_guards"]:
                print(f"           {lab}")
    print(f"\nA case that does NOT discriminate is EITHER decoration OR a regression guard the old\n"
          f"implementation also satisfied — a different claim, not a weaker one. Nothing here can\n"
          f"separate those, so deleting a case on this number alone will remove real guards. Mark a\n"
          f"case with '{REGRESSION_GUARD_MARKER}' in its label and it moves to its own bucket.\n"
          f"Report-only by design — it never fails the build.")
    return 0


def audit(guard: mc.Guard) -> dict:
    """One guard's reachability report."""
    selftest = REPO / guard.selftest
    if not selftest.is_file():
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": f"selftest {guard.selftest} not found", "labels": 0,
                "unreachable": [], "problems": []}
    labels, unreadable_lines = labels_in(selftest.read_text(encoding="utf-8"))
    if not labels:
        return {"guard": guard.name, "status": "UNREADABLE",
                "reason": (f"no assertion labels could be enumerated from {guard.selftest} -- "
                           f"its selftest names assertions in a shape this tool does not read, so "
                           f"'0 unreachable' here would mean nothing"),
                "labels": 0, "unreachable": [], "problems": []}
    if not guard.mutations:
        return {"guard": guard.name, "status": "NO-MUTATIONS", "labels": len(labels),
                "unreachable": sorted(set(labels)), "problems": [],
                "unreadable_label_lines": unreadable_lines}

    outputs, problems = mutant_outputs(guard)
    haystack = "\n".join(outputs).lower()
    unreachable = sorted({lab for lab in labels if lab.lower() not in haystack})
    return {
        "guard": guard.name,
        "status": "ok" if not unreachable else "UNREACHED",
        "labels": len(set(labels)),
        "mutations": len(guard.mutations),
        "unreachable": unreachable,
        "problems": problems,
        "unreadable_label_lines": unreadable_lines,
    }


def report(results: list[dict], as_json: bool) -> int:
    if as_json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    total_labels = sum(r.get("labels", 0) for r in results)
    total_unreached = sum(len(r.get("unreachable", [])) for r in results)
    unreadable = [r for r in results if r["status"] == "UNREADABLE"]

    for r in sorted(results, key=lambda x: (x["status"] == "ok", x["guard"])):
        if r["status"] == "UNREADABLE":
            print(f"[skip] {r['guard']}: {r['reason']}")
            continue
        if r["status"] == "ok":
            print(f"[ ok ] {r['guard']}: all {r['labels']} labelled assertion(s) fail under "
                  f"at least one of {r['mutations']} declared mutation(s)")
            continue
        print(f"[note] {r['guard']}: {len(r['unreachable'])} of {r['labels']} labelled "
              f"assertion(s) fail under NO declared mutation")
        for lab in r["unreachable"]:
            print(f"         {lab}")
        for problem in r.get("problems", []):
            print(f"         ! {problem}")
        if r.get("unreadable_label_lines"):
            print(f"         ! {len(r['unreadable_label_lines'])} label(s) not literal strings, "
                  f"at line(s) {r['unreadable_label_lines']} -- not counted either way")

    print(f"\n{total_unreached} of {total_labels} labelled assertion(s) across "
          f"{len(results) - len(unreadable)} readable guard(s) are unreached by any declared "
          f"mutation.")
    if unreadable:
        print(f"{len(unreadable)} guard(s) could not be enumerated and are NOT counted above — "
              f"a skip is not a pass.")
    print("An unreached assertion is EITHER vacuous (it cannot fail) OR merely unguarded (nobody\n"
          "has written the mutation that trips it). This tool cannot tell those apart; that is a\n"
          "person's judgement. Report-only by design — it never fails the build.")
    return 0


def _selftest() -> int:
    """Prove this tool reports an unreached assertion AND stays silent on a reached one.

    Both directions against ONE fixture, because a tool that only ever reported findings and a tool
    that only ever reported none would each pass a one-sided test. The fixture subject has two
    labelled assertions and exactly ONE declared mutation, so the only correct answer is "report the
    other one" -- not both, and not none. That is the verdict a `.covered` pattern-match would have
    got wrong, and it is the whole claim this tool makes.

    `REPO` is repointed at a temp root in both modules for the duration, so the audit runs end to
    end -- staging, mutating, running the mutant -- without writing a byte into the working tree. A
    selftest that only exercised the label parser would prove the cheap half and leave the claim
    untested.
    """
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # -- the label parser, in the direction that keeps the denominator honest ----------------
    flabels, funread = labels_in(
        "def f():\n    check(f'computed {1}', True)\n    check('literal', True)\n")
    check("a non-literal label is reported unreadable rather than silently dropped",
          flabels == ["literal"] and len(funread) == 1)

    # -- the end-to-end verdict --------------------------------------------------------------
    root = Path(tempfile.mkdtemp(prefix="reach-selftest-"))
    saved_mc, saved_here = mc.REPO, globals()["REPO"]
    try:
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "subject.py").write_text(
            "GREETING = 'hello'\n"
            "FAREWELL = 'bye'\n"
            "\n"
            "def _selftest():\n"
            "    bad = []\n"
            "    def check(label, cond):\n"
            "        if not cond:\n"
            "            bad.append(label)\n"
            "    check('the greeting is hello', GREETING == 'hello')\n"
            "    check('the farewell is bye', FAREWELL == 'bye')\n"
            "    for b in bad:\n"
            "        print('  - ' + b)\n"
            "    return 1 if bad else 0\n"
            "\n"
            "import sys\n"
            "sys.exit(_selftest())\n", encoding="utf-8")

        mc.REPO = root
        globals()["REPO"] = root
        guard = mc.Guard(
            name="fixture",
            subject="scripts/subject.py",
            selftest="scripts/subject.py",
            mutations=(mc.Mutation("the greeting breaks",
                                   "GREETING = 'hello'", "GREETING = 'nope'",
                                   "the greeting is hello"),),
        )
        result = audit(guard)

        check("both labelled assertions are enumerated", result["labels"] == 2)
        check("the guard is reported as having an unreached assertion",
              result["status"] == "UNREACHED")
        # THE DISCRIMINATING PAIR. One label is reached by the declared mutation and one is not,
        # and the report has to separate them. Asserting only the count would pass for a tool that
        # picked the wrong one of the two.
        check("the UNGUARDED assertion is reported",
              result["unreachable"] == ["the farewell is bye"])
        check("the GUARDED assertion is NOT reported -- the control, proving the mutation ran "
              "and its failure was observed",
              "the greeting is hello" not in result["unreachable"])

        # A guard with NO mutations must report every label, not zero. Zero would read as a clean
        # bill of health for a subject nothing guards at all -- the vacuous pass inverted.
        bare = audit(mc.Guard(name="fixture", subject="scripts/subject.py",
                              selftest="scripts/subject.py", mutations=()))
        check("a guard with no mutations reports ALL its labels, not none",
              bare["status"] == "NO-MUTATIONS" and len(bare["unreachable"]) == 2)

        # A selftest naming assertions in a shape this tool cannot read must SKIP, not pass.
        (root / "scripts" / "opaque.py").write_text(
            "def _selftest():\n    assert 1 == 1\n", encoding="utf-8")
        opaque = audit(mc.Guard(name="opaque", subject="scripts/opaque.py",
                                selftest="scripts/opaque.py", mutations=()))
        check("a selftest with no readable labels is UNREADABLE, not a pass",
              opaque["status"] == "UNREADABLE")

        # -- --against: does the suite tell a right implementation from a wrong one? (#1048) ----
        # A REAL two-revision git history, because the whole mode is `git show <rev>:<subject>`
        # and a fixture that stubbed that out would test everything except the part that fails.
        # Modelled on the hand measurement in #1048: a suite where SOME cases catch the old
        # implementation and one does not, so the correct answer is a SPLIT -- not all, not none.
        def _g(*a):
            subprocess.run(("git", *a), cwd=root, capture_output=True, text=True, check=False)

        _g("init", "-q")
        _g("config", "user.email", "selftest@example.invalid")
        _g("config", "user.name", "selftest")
        # OLD: returns every token. Right on the plain case by luck, wrong on the splat.
        (root / "scripts" / "widget.py").write_text(
            "def keys(text):\n"
            "    return text.split()\n", encoding="utf-8")
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            "check('a comment brace does not truncate', widget.keys('a: b:') == ['a:', 'b:'])\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        _g("add", "-A")
        _g("commit", "-qm", "old")
        old_rev = subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, capture_output=True,
                                 text=True, check=False).stdout.strip()
        # NEW: only key-shaped tokens. Both cases now pass, so exactly ONE discriminates --
        # which is the split this mode has to be able to report, and the shape of #1048's 5-of-6.
        (root / "scripts" / "widget.py").write_text(
            "def keys(text):\n"
            "    return [w for w in text.split() if w.endswith(':')]\n", encoding="utf-8")
        _g("add", "-A")
        _g("commit", "-qm", "new")

        wg = mc.Guard(name="widget", subject="scripts/widget.py",
                      selftest="scripts/widget_selftest.py", mutations=())
        split = discriminate(wg, old_rev)
        check("the two revisions can be compared at all", split["status"] == "ok")
        # THE DISCRIMINATING PAIR, and the reason a count alone would not do. One case catches the
        # old implementation and one does not; a tool reporting "all" or "none" passes any test
        # that only checks a total.
        check("the case the old implementation FAILS is reported as discriminating",
              split.get("discriminating") == ["a splat is refused"])
        check("the case the old implementation PASSES is reported as non-discriminating",
              split.get("non_discriminating") == ["a comment brace does not truncate"])
        check("a suite that still fails the old implementation is not reported as wholesale-passing",
              split.get("old_selftest_passed") is False)

        # THE CRASH CASE, found in this tool on its first real run against this repo. Today's cases
        # calling API the old revision lacks makes the selftest die on import, emitting no labels --
        # so every label reads as "not in the output" and the split reports 0-of-N discriminating:
        # a confident verdict over a comparison that never happened. It must SKIP, not report.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "widget.function_that_did_not_exist_then()\n"
            "check('unreachable', True)\n", encoding="utf-8")
        crashed = discriminate(wg, old_rev)
        check("a selftest that cannot RUN against the old revision skips rather than reporting "
              "0 discriminating",
              crashed["status"] == "UNREADABLE" and "did not run" in crashed.get("reason", ""))

        # -- #1059: the crash must land on a LABELLED line -------------------------------------
        # The shipped crash fixture called `widget.function_that_did_not_exist_then()` on a line
        # carrying NO label, so nothing reached `failing` and the preflight fired correctly. The
        # real shape is the opposite: the old subject is missing API that today's cases CALL, so
        # the traceback prints a source line WITH a label in it. A substring match then counts that
        # label as failing, the preflight is skipped because it keys off `failing` being empty, and
        # the tool reports a split over a run in which not one case executed.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            "check('a splat is refused', widget.brand_new_api('**splat') == [])\n"
            "check('a comment brace does not truncate', widget.keys('a: b:') == ['a:', 'b:'])\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        crashed_labelled = discriminate(wg, old_rev)
        check("a crash on a LABELLED line still skips rather than reporting a split",
              crashed_labelled["status"] == "UNREADABLE"
              and "did not run" in crashed_labelled.get("reason", ""))

        # -- #1060: a label that is a PREFIX of another must not ride on its failure ------------
        # 11 such collisions were measured across two shipped tools. The shorter case reads as
        # failing -- and so as discriminating -- whenever the longer one does, whether or not it
        # ran. The split inflates in the flattering direction, which is the one nobody audits.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            # The LONGER label fails against the old subject; the shorter one passes against both.
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "check('a splat', True)\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        prefixed = discriminate(wg, old_rev)
        check("the LONGER failing label is reported as discriminating",
              prefixed.get("discriminating") == ["a splat is refused"])
        check("a label that is merely a PREFIX of a failing one is NOT counted as discriminating",
              prefixed.get("non_discriminating") == ["a splat"])

        # ...and the SUFFIX case, which is a different guard. The leading half of the anchor is
        # what stops `'is refused'` matching inside `'- a splat is refused'`; the trailing half
        # stops `'a splat'` matching. Neither fixture catches the other's mutation, so the anchor
        # needs one of each or half of it is unguarded.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "check('is refused', True)\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        suffixed = discriminate(wg, old_rev)
        check("a label that is merely a SUFFIX of a failing one is NOT counted as discriminating",
              suffixed.get("non_discriminating") == ["is refused"])

        # -- #1061: the denominator's holes are printed, not merely recorded -------------------
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "check(f'computed {1}', True)\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        holed = discriminate(wg, old_rev)
        check("a non-literal label is recorded as a hole in the denominator",
              len(holed.get("unreadable_label_lines") or []) == 1)
        check("...and excluded from the labels counted", holed.get("labels") == 1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report_discrimination([holed], as_json=False)
        check("...and the report PRINTS it rather than only recording it",
              "not literal strings" in buf.getvalue())

        # A case marked as a regression guard is counted in its own bucket, not against the suite.
        # Without this the split drives people to delete guards that are doing their job.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "check('[regression guard] nesting is not hoisted', True)\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        marked = discriminate(wg, old_rev)
        check("a declared regression guard is excluded from the split",
              marked.get("declared_regression_guards")
              == ["[regression guard] nesting is not hoisted"]
              and "[regression guard] nesting is not hoisted"
              not in marked.get("non_discriminating", []))

        # -- the control case: the precondition that makes a per-case result mean anything -----
        # The exit-code preflight above catches "the API is gone". It cannot catch "the API means
        # something else" -- a function changed from taking file CONTENTS to taking a PATH keeps
        # its name and arity, every case fails, and the run reports a flattering, false "all
        # discriminate". A control that the old subject FAILS is the only signal for that.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            # The control is the canonical shape -- keys picked out of surrounding text -- which
            # the OLD implementation gets wrong (it returns every token, including `noise`), so
            # the harness reads as unfit and the whole split is refused.
            "check('[control] the real shape', widget.keys('noise a:') == ['a:'])\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        unfit = discriminate(wg, old_rev)
        check("a failing control refuses the whole split rather than reporting a per-case one",
              unfit["status"] == "UNREADABLE" and "control case failed" in unfit.get("reason", ""))

        # THE CONTROL FOR THE CONTROL. The same suite whose control PASSES against the old subject
        # must produce a real split -- otherwise "a failing control refuses" would also pass for an
        # implementation that refused every run, which is the flattering-versus-damning asymmetry
        # this tool is about.
        (root / "scripts" / "widget_selftest.py").write_text(
            "import sys\n"
            "sys.path.insert(0, 'scripts')\n"
            "import widget\n"
            "bad = []\n"
            "def check(label, cond):\n"
            "    if not cond:\n"
            "        bad.append(label)\n"
            # 'a:' is a token AND key-shaped, so old and new agree -- a fitting harness.
            "check('[control] the real shape', widget.keys('a:') == ['a:'])\n"
            "check('a splat is refused', widget.keys('**splat') == [])\n"
            "for b in bad:\n"
            "    print('  - ' + b)\n"
            "sys.exit(1 if bad else 0)\n", encoding="utf-8")
        fit = discriminate(wg, old_rev)
        check("a passing control lets the split through",
              fit["status"] == "ok" and fit.get("discriminating") == ["a splat is refused"])
        check("the control is a precondition, not a data point — it is kept out of the split",
              "[control] the real shape" not in fit.get("non_discriminating", [])
              and fit.get("controls") == ["[control] the real shape"])
    finally:
        mc.REPO, globals()["REPO"] = saved_mc, saved_here
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"ran {ok} assertion(s)")
    print("the auditor separates a reached assertion from an unreached one, and reports a "
          "selftest it cannot enumerate as a skip")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guard", help="audit one guard by name")
    ap.add_argument("--against", metavar="REV",
                    help="instead of the reachability audit, run each guard's CURRENT selftest "
                         "against the implementation at REV and report which cases discriminate")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true", help="prove this checker can fail")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    guards = mc.discover()
    if args.guard:
        guards = tuple(g for g in guards if g.name == args.guard)
        if not guards:
            print(f"no guard named {args.guard!r}", file=sys.stderr)
            return 2
    if args.against:
        return report_discrimination([discriminate(g, args.against) for g in guards], args.json)
    return report([audit(g) for g in guards], args.json)


if __name__ == "__main__":
    raise SystemExit(main())
