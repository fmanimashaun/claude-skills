#!/usr/bin/env python3
"""Prove the mutation checker itself can fail — otherwise it is the very thing it exists to catch.

Run:  python3 scripts/mutation_check.py --selftest

A checker whose job is "prove your guards can fail" is worthless if IT cannot fail. So this pins the
three ways it could silently pass:

  1. a **survivor** — the selftest passes with its subject broken — must be reported, not shrugged off
  2. a **stale anchor** — a mutation that no longer matches — must be a hard error, because a mutation
     that did not apply produces a mutant identical to the original, which passes and looks exactly
     like a caught mutation
  3. a **coincidental catch** — the selftest fails, but for an unrelated reason — must not count, or a
     fixture going quiet is masked by its neighbour

It also asserts every guard's declared anchors still match exactly once in the real tree, so the
mutation list cannot drift away from the code it mutates and start reporting vacuous passes.

Stdlib only.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_check as mc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


# A trivial subject + selftest pair, so the three failure modes can be exercised without depending
# on any real guard's behaviour.
SUBJECT = '''
def is_even(n):
    return n % 2 == 0
'''

SELFTEST = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import subject_under_test as s

failures = []
if s.is_even(4) is not True:
    failures.append("fixture-even: expected True for 4")
if s.is_even(3) is not False:
    failures.append("fixture-odd: expected False for 3")
if failures:
    print("SELFTEST FAILED", file=sys.stderr)
    for f in failures:
        print("  - " + f, file=sys.stderr)
    sys.exit(1)
print("ok")
'''


def _fixture_guard(mutations: tuple[mc.Mutation, ...]) -> tuple[mc.Guard, Path]:
    """A real Guard pointing at a throwaway subject/selftest pair inside a temp 'repo'."""
    root = Path(tempfile.mkdtemp(prefix="mutcheck-selftest-"))
    (root / "scripts").mkdir()
    (root / "scripts" / "subject_under_test.py").write_text(SUBJECT, encoding="utf-8")
    (root / "scripts" / "subject_selftest.py").write_text(SELFTEST, encoding="utf-8")
    guard = mc.Guard(
        name="fixture",
        subject="scripts/subject_under_test.py",
        selftest="scripts/subject_selftest.py",
        mutations=mutations,
    )
    return guard, root


def run() -> int:
    original_repo = mc.REPO

    # ---- 1. a real break must be CAUGHT, and attributed to the right fixture ------------
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if problems:
            FAILURES.append(f"a genuine break was not accepted as caught: {problems}")
    finally:
        mc.REPO = original_repo

    # ---- 2. a SURVIVOR must be reported ------------------------------------------------
    # This mutation changes the subject in a way neither fixture observes, so the selftest still
    # passes. That is exactly the vacuous-fixture situation, and it must not read as success.
    guard, root = _fixture_guard((
        mc.Mutation("adds an unobserved helper", "def is_even(n):",
                    "def unobserved():\n    return 1\n\n\ndef is_even(n):", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("SURVIVED" in p for p in problems):
            FAILURES.append(
                "a survivor was not reported — the checker would pass a guard whose fixtures "
                f"observe nothing; got {problems}"
            )
    finally:
        mc.REPO = original_repo

    # ---- 3. a STALE ANCHOR must be a hard error, never a pass --------------------------
    guard, root = _fixture_guard((
        mc.Mutation("anchor that no longer exists", "this_text_is_absent", "x", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        try:
            mc.apply_mutation(guard, guard.mutations[0], Path(tempfile.mkdtemp()))
            FAILURES.append(
                "a stale anchor did not raise — a mutation that cannot apply yields a mutant "
                "identical to the original, which passes and reads exactly like a caught mutation"
            )
        except RuntimeError as exc:
            if "anchor matches 0" not in str(exc):
                FAILURES.append(f"stale anchor raised the wrong message: {exc}")
    finally:
        mc.REPO = original_repo

    # A NON-UNIQUE anchor is equally unsafe: it would mutate more than intended, so the result
    # cannot be attributed to the change under test.
    guard, root = _fixture_guard((
        mc.Mutation("ambiguous anchor", "return", "pass", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        (root / "scripts" / "subject_under_test.py").write_text(
            SUBJECT + "\n\ndef other():\n    return 2\n", encoding="utf-8")
        try:
            mc.apply_mutation(guard, guard.mutations[0], Path(tempfile.mkdtemp()))
            FAILURES.append("a non-unique anchor did not raise")
        except RuntimeError as exc:
            if "need exactly 1" not in str(exc):
                FAILURES.append(f"non-unique anchor raised the wrong message: {exc}")
    finally:
        mc.REPO = original_repo

    # ---- 4. a COINCIDENTAL catch must not count ----------------------------------------
    # The break is real and the selftest fails — but on the *other* fixture. Expecting the wrong
    # one must be reported, or a fixture going quiet is masked by its neighbour.
    guard, root = _fixture_guard((
        mc.Mutation("even numbers reported odd", "n % 2 == 0", "False", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("not by the expected fixture" in p for p in problems):
            FAILURES.append(
                "a catch by the WRONG fixture was accepted — that hides the intended fixture "
                f"going quiet; got {problems}"
            )
    finally:
        mc.REPO = original_repo

    # ---- 5. every real guard's anchors still match exactly once ------------------------
    # Without this the mutation list rots silently: an anchor that drifts raises at run time, but
    # only for whoever runs the checker. Asserting it here makes drift a selftest failure.
    for real_guard in mc.GUARDS:
        source = (original_repo / real_guard.subject).read_text(encoding="utf-8")
        for mutation in real_guard.mutations:
            _tick()
            hits = source.count(mutation.old)
            if hits != 1:
                FAILURES.append(
                    f"{real_guard.name} / {mutation.name}: anchor matches {hits} time(s) in "
                    f"{real_guard.subject}, need exactly 1 — the mutation list has drifted"
                )

    # ---- 6. every guard names a real subject and selftest, and declares mutations ------
    for real_guard in mc.GUARDS:
        _tick()
        missing = [p for p in (real_guard.subject, real_guard.selftest, *real_guard.deps,
                               *real_guard.needs) if not (original_repo / p).is_file()]
        if missing:
            FAILURES.append(f"{real_guard.name}: declares files that do not exist: {missing}")
        if not real_guard.mutations:
            FAILURES.append(
                f"{real_guard.name}: declares no mutations — a guard with an empty list passes "
                "vacuously, which is the failure this checker exists to prevent"
            )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"mutation_check selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
