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
import json
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
    return report([audit(g) for g in guards], args.json)


if __name__ == "__main__":
    raise SystemExit(main())
