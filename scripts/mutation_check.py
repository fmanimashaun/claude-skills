#!/usr/bin/env python3
"""Prove every selftest CAN fail — by breaking its subject and requiring it to notice.

Run:  python3 scripts/mutation_check.py            # all guards
      python3 scripts/mutation_check.py --guard lint_self_consistency
      python3 scripts/mutation_check.py --selftest  # prove this checker itself can fail

WHY THIS EXISTS (#233). The repo has six selftests and fourteen gates, and until now **nothing
checked that a selftest fails when the thing it guards breaks**. Two fixtures written in one
session were vacuous and passed for the wrong reason:

  * a `hasattr` on a function that never existed, so it compared `[] == []`
  * a cross-contamination scenario whose two classes shared one fenced block, leaving the second
    unregistered — the scenario never ran

Both looked right. One survived until a maintainer asked whether the fix was real. CLAUDE.md
already says to make every new check fail on purpose once; the failure mode is not ignorance of
that rule, it is skipping it under momentum. So it becomes a gate.

WHAT IT IS NOT. Not a general mutation framework — no AST rewriting, no operator taxonomy, no
survivor analysis. Each guard declares a short list of **named, hand-chosen mutations** to its own
subject, each with the fixture it is expected to trip. Guards live one per file under
`scripts/mutations/` (#866); this file runs them. A declared list is auditable and cheap; a
generated one produces survivors nobody triages, and an untriaged mutation report is
indistinguishable from a passing one.

HOW A MUTATION IS APPLIED. The subject is copied to a temp directory with one exact string
replaced, its selftest is copied beside it, and the selftest runs against the mutant. Nothing in
the working tree is touched — earlier hand-runs of this edited real files and relied on a `finally`
to restore them, which is one interrupted process away from leaving a mutated repo.

THE ASSERTION THAT MATTERS. A mutation must be *verified applied* before its result counts. An
anchor that no longer matches produces a mutant identical to the original, the selftest passes, and
that reads exactly like a caught mutation. So a stale anchor is a hard error, never a pass.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mutation_types import Guard, Mutation  # noqa: F401 -- re-exported: mutation_check_selftest and doctrine_map use mc.Guard / mc.Mutation

REPO = Path(__file__).resolve().parents[1]

MUTATIONS_DIR = Path(__file__).resolve().parent / "mutations"


def discover(directory: Path = MUTATIONS_DIR) -> tuple[Guard, ...]:
    """Every `GUARD` declared under scripts/mutations/, sorted by filename, names asserted unique.

    THE DECLARATION SPLIT; THE RUNNER DID NOT (#866). The table lived here as one 5,986-line tuple
    quoting subject source lines verbatim, so a refactor of any of 70 files needed a matching edit in
    this one -- 159 commits, the third most-edited file in the repo. Now a guard is a small module
    beside the change that needs it. Discovery is a glob, not a list: a hand-typed registry of the
    directory's contents goes quiet the day a file is added, which is the coverage-gap class this
    harness exists to catch (`docs/doctrine/harness-doctrine.md`, instance 4).
    """
    import importlib.util
    guards: list[Guard] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"mutations.{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        guard = getattr(module, "GUARD", None)
        if not isinstance(guard, Guard):
            raise RuntimeError(f"{path.relative_to(REPO)} declares no `GUARD = Guard(...)` -- a guard module that "
                               "declares nothing is a file the harness silently ignores")
        if guard.name != path.stem:
            raise RuntimeError(f"{path.relative_to(REPO)}: GUARD.name is {guard.name!r}; the filename is the "
                               "name, so `--guard <name>` and the file agree")
        guards.append(guard)
    names = [g.name for g in guards]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise RuntimeError(f"guard names declared more than once: {dupes}")
    return tuple(guards)


GUARDS: tuple[Guard, ...] = discover()


def stage(guard: Guard, workdir: Path) -> Path:
    """Copy subject + selftest + deps + needs into `workdir`, UNMUTATED. Returns the entry point.

    Mirrors the repo layout rather than flattening, so `parents[1]`-relative reads still work.
    """
    for relative in {guard.subject, guard.selftest, *guard.deps}:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / relative).read_text(encoding="utf-8"), encoding="utf-8")
    for relative in guard.needs:
        source, target = REPO / relative, workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # A whole directory, not just a file: `build_coverage_selftest` reads EVERY doc under
        # `references/`, and naming the 19 of them here would go quiet the day a 20th is added --
        # the coverage-gap class, in the harness that exists to catch it.
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, target)
    return workdir / guard.selftest


def apply_mutation(guard: Guard, mutation: Mutation, workdir: Path) -> Path:
    """Stage the guard into `workdir`, with the mutation applied to the subject.

    Raises if the anchor is absent or non-unique: a mutation that did not apply produces a mutant
    identical to the original, which passes and reads exactly like a caught mutation.
    """
    subject = REPO / guard.subject
    source = subject.read_text(encoding="utf-8")
    hits = source.count(mutation.old)
    if hits != 1:
        raise RuntimeError(
            f"{guard.name} / {mutation.name}: anchor matches {hits} time(s), need exactly 1 — "
            "the mutation list has drifted from the code it mutates"
        )
    mutated = source.replace(mutation.old, mutation.new)
    if mutated == source:
        raise RuntimeError(f"{guard.name} / {mutation.name}: replacement changed nothing")

    entry = stage(guard, workdir)
    (workdir / guard.subject).write_text(mutated, encoding="utf-8")
    return entry


def run_baseline(guard: Guard) -> list[str]:
    """The control: the UNMUTATED selftest must PASS in the same staged tempdir.

    Without this, `run_guard`'s "returncode != 0 means caught" reads a guard that cannot pass at
    all as a guard that catches everything. That is not hypothetical -- it was true of
    `build_coverage` for as long as its selftest read the reference docs, which are not part of
    the subject: the staged mutant had no `references/`, the unmutated selftest already exited 1,
    and all of its mutations were therefore "caught" without the mutation doing anything. A
    gate-that-cannot-fail inside the meta-gate whose whole job is proving gates can fail.

    Run once per guard rather than once per mutation: staging is identical, and the cost is one
    selftest run against N.
    """
    workdir = Path(tempfile.mkdtemp(prefix=f"mutbase-{guard.name}-"))
    try:
        entry = stage(guard, workdir)
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            argv.append("--selftest")
        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return [
                f"{guard.name}: INERT — the UNMUTATED selftest already fails in the staged "
                f"tempdir (exit {result.returncode}), so every mutation below is 'caught' whether "
                "or not it breaks anything. Add what it reads to the guard's `needs`.\n"
                + "\n".join(f"      {line}" for line in
                            (result.stdout + result.stderr).strip().splitlines()[-6:])
            ]
    except subprocess.TimeoutExpired:
        return [f"{guard.name}: the unmutated baseline timed out"]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return []


def run_guard(guard: Guard) -> list[str]:
    """Failures for one guard. Empty list = every mutation was caught by the right fixture.

    Serial, deliberately. Wall time is one subprocess per declared mutation and the list only
    grows -- 236 of them crossed `maintainer_doctor`'s 180s per-gate budget while #129 was being
    written. The fix is `SLOW_GATES` over there, which states the cost honestly, rather than a
    thread pool here: every mutation does run in its own temp directory against its own
    subprocess, so parallelising is safe and is the obvious next step, but it measured at only
    ~7% on a machine that was running other agents' sweeps at the same time. An unmeasurable
    speedup is not worth adding concurrency to the checker every other gate is judged by.
    """
    # The baseline runs the UNMUTATED selftest first. Without it a guard whose staged copy is
    # missing a dependency fails for that reason alone, and every mutation then reads as "caught"
    # by the breakage rather than by a fixture -- which is exactly what `build_coverage` was doing.
    problems: list[str] = run_baseline(guard)
    # AN INERT BASELINE ENDS THE GUARD. Running the mutations anyway is not merely wasted time: it
    # appends one "caught, but not by the expected fixture" line PER MUTATION, so a single cause is
    # reported as N+1 findings with the real one first and the noise last. That is what made this
    # miss-able -- the diagnosis and its fix are in the head of the output, and anything inspecting
    # the tail sees only the noise. Which happened three times before anyone noticed the header.
    #
    # It is also simply wrong to score them: with the selftest already failing, every mutation is
    # "caught" whether or not it breaks anything, so the verdicts are meaningless by construction.
    if problems:
        return problems
    for mutation in guard.mutations:
        workdir = Path(tempfile.mkdtemp(prefix=f"mutcheck-{guard.name}-"))
        try:
            entry = apply_mutation(guard, mutation, workdir)
            argv = [sys.executable, str(entry)]
            if guard.selftest == guard.subject:
                argv.append("--selftest")   # the selftest is a flag on the module itself
            result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
            output = result.stdout + result.stderr

            if result.returncode == 0:
                problems.append(
                    f"{guard.name}: SURVIVED — {mutation.name}. The selftest passed with this "
                    "broken, so nothing guards it."
                )
                continue
            if mutation.expects and mutation.expects.lower() not in output.lower():
                problems.append(
                    f"{guard.name}: caught {mutation.name!r} but not by the expected fixture "
                    f"(no mention of {mutation.expects!r}) — a coincidental catch would hide that "
                    "fixture going quiet"
                )
        except subprocess.TimeoutExpired:
            problems.append(f"{guard.name}: {mutation.name} timed out")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove each selftest fails when the thing it guards breaks."
    )
    parser.add_argument("--guard", help="run one guard by name")
    parser.add_argument("--selftest", action="store_true",
                        help="prove this checker itself detects a survivor and a stale anchor")
    args = parser.parse_args(argv)

    if args.selftest:
        import mutation_check_selftest as st

        return st.run()

    guards = [g for g in GUARDS if not args.guard or g.name == args.guard]
    if args.guard and not guards:
        print(f"no guard named {args.guard!r}; known: {[g.name for g in GUARDS]}", file=sys.stderr)
        return 2
    problems: list[str] = []
    total = 0
    for guard in guards:
        total += len(guard.mutations)
        found = run_guard(guard)
        status = "ok" if not found else "FAIL"
        print(f"  [{status:4}] {guard.name}: {len(guard.mutations)} mutation(s)")
        problems.extend(found)

    if problems:
        print(f"\nMUTATION CHECK FAILED — {len(problems)} of {total}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"\nmutation check: {total} mutation(s) across {len(guards)} guard(s), all caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
