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
import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mutation_types import Guard, Mutation  # noqa: F401 -- re-exported: mutation_check_selftest and doctrine_map use mc.Guard / mc.Mutation

REPO = Path(__file__).resolve().parents[1]

MUTATIONS_DIR = Path(__file__).resolve().parent / "mutations"


def discover(directory: Path = MUTATIONS_DIR, base: str = ".") -> tuple[Guard, ...]:
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
        # Stamp where this guard's paths resolve from. `replace` rather than asking each module
        # to declare it: the location IS the fact, and a declared copy could disagree with it.
        guards.append(dataclasses.replace(guard, base=base) if base != "." else guard)
    names = [g.name for g in guards]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise RuntimeError(f"guard names declared more than once: {dupes}")
    return tuple(guards)


def discover_all() -> tuple[Guard, ...]:
    """Guards from BOTH roots: this repo's, and the ones shipped inside each plugin (#1109).

    A guard whose subject and every dependency live in one plugin ships WITH that plugin, written
    plugin-relative, so a consumer project can run it against the copy it actually installed. A
    guard that spans plugins -- `project_gates` reading three manifests, `hook_normalize_cmd`
    proving qa-flow and rails-flow share one normaliser -- stays here, because a project that
    installed one plugin could not verify the claim anyway.
    """
    found = list(discover(MUTATIONS_DIR))
    for manifest in sorted(REPO.glob("plugins/*/scripts/mutations")):
        found += discover(manifest, base=str(manifest.relative_to(REPO).parents[1]))
    # The "every declared path resolves from its base" invariant lives in the SELFTEST, not here.
    # At import time this module is also loaded inside a STAGED tempdir -- `doctrine_map`'s own
    # selftest copies the repo and re-imports it -- where a file a guard legitimately needs (say
    # `CHANGELOG.md`) is simply not staged. Raising there broke two guards that were correct, which
    # is the "gate red on correct code" shape. Import stays cheap and tolerant; validation is a
    # check that runs against the real tree (#1109).
    names = [g.name for g in found]
    duplicated = {n for n in names if names.count(n) > 1}
    if duplicated:
        raise RuntimeError(
            f"guard name(s) declared in two places: {sorted(duplicated)} -- `--guard <name>` "
            f"could not say which, and one of them would never run")
    return tuple(found)


GUARDS: tuple[Guard, ...] = discover_all()


def sibling_imports(source: Path) -> set[str]:
    """Modules this file imports AT MODULE SCOPE, by bare name. Empty on a syntax error.

    MODULE SCOPE ONLY, and that is the whole difference between a rule and noise. A `def`-scope
    import runs when the function is CALLED, so it is optional at load time -- `validate_evidence`
    imports its own selftest inside `if args.selftest:`, which a mutant never invokes. Walking the
    whole tree flagged six such pairs on the first run, every one of them correct code. Module-level
    `if`/`try`/`with` DO execute on import, so those are descended into; a function or class body
    never is.
    """
    import ast

    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    found: set[str] = set()

    def scan(body: list) -> None:
        for node in body:
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                scan(node.body)
                scan(getattr(node, "orelse", []))
                for handler in getattr(node, "handlers", []):
                    scan(handler.body)

    scan(tree.body)
    return found


def unstaged_sibling_imports(guard: Guard, base: Path) -> list[str]:
    """Sibling modules a guard's staged files import at module scope but do not stage.

    Takes `base` rather than reading `REPO`, because this runs INSIDE the staged tempdir when the
    harness guards itself -- and a version reading ambient state answered over an empty repo there
    and every assertion about it passed vacuously. Same class as the `head` injection in
    `stale_inventory`, and as the defect this function exists to find.
    """
    staged = {guard.subject, guard.selftest, *guard.deps}
    stems = {Path(r).stem for r in staged} | {Path(n).stem for n in guard.needs}
    need_dirs = [n for n in guard.needs if (base / n).is_dir()]
    out: list[str] = []
    # Transitive, and seeded from `needs` files too (#1444): check_slices staged
    # check_mockup_gate as a need, which imported classify_door, and a one-level scan of the
    # staged trio never read the file that held the import -- the guard went INERT in CI.
    pending = sorted(staged | {n for n in guard.needs if (base / n).is_file()})
    seen: set[Path] = set()
    while pending:
        relative = pending.pop(0)
        source = base / relative
        if source in seen or not source.is_file() or source.suffix != ".py":
            continue
        seen.add(source)
        for name in sorted(sibling_imports(source)):
            sibling = source.parent / f"{name}.py"
            if not sibling.is_file():
                continue              # stdlib or third-party; not this harness's business
            # A `needs` DIRECTORY covers anything beneath it, at any depth -- `plugins/qa-flow`
            # stages `plugins/qa-flow/scripts/evidence_app_tie.py`. Testing `base/d/<name>.py`
            # instead reported a guard that was already correct, on this rule's first run.
            covered = name in stems or any(sibling.is_relative_to(base / d) for d in need_dirs)
            if not covered:
                out.append(f"{relative} imports `{name}`, which is in neither deps nor needs")
            pending.append(str(sibling.relative_to(base)))
    return out


def stage(guard: Guard, workdir: Path) -> Path:
    """Copy subject + selftest + deps + needs into `workdir`, UNMUTATED. Returns the entry point.

    Mirrors the repo layout rather than flattening, so `parents[1]`-relative reads still work.
    """
    for relative in {guard.subject, guard.selftest, *guard.deps}:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / guard.base / relative).read_text(encoding="utf-8"), encoding="utf-8")
    for relative in guard.needs:
        source, target = REPO / guard.base / relative, workdir / relative
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
    subject = REPO / guard.base / guard.subject
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


def run_mutation(guard: Guard, mutation: Mutation) -> list[str]:
    """One mutation, in its own tempdir. Independent of every other mutation, so the suite can run
    them in parallel (#1444). `run_guard` and `main` both come through here: one implementation."""
    workdir = Path(tempfile.mkdtemp(prefix=f"mutcheck-{guard.name}-"))
    try:
        entry = apply_mutation(guard, mutation, workdir)
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            argv.append("--selftest")   # the selftest is a flag on the module itself
        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr
        if result.returncode == 0:
            return [f"{guard.name}: SURVIVED — {mutation.name}. The selftest passed with this "
                    "broken, so nothing guards it."]
        if mutation.expects and mutation.expects.lower() not in output.lower():
            # The mutant's own last lines, as the INERT report prints: a wrong-fixture catch seen
            # only on CI was undiagnosable without them, because CI keeps nothing else (#1428).
            return [f"{guard.name}: caught {mutation.name!r} but not by the expected fixture "
                    f"(no mention of {mutation.expects!r}, exit {result.returncode}) — a coincidental "
                    "catch would hide that fixture going quiet\n"
                    + "\n".join(f"      {line}" for line in output.strip().splitlines()[-12:])]
        return []
    except subprocess.TimeoutExpired:
        return [f"{guard.name}: {mutation.name} timed out"]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def live_mutations(guards: list[Guard], baselines: list[list[str]]) -> list[tuple[Guard, Mutation]]:
    """The mutations `main`'s pool still runs: every one of every guard whose baseline passed.

    A baseline with findings ends its guard unscored -- the same rule `run_guard` applies serially.
    """
    return [(g, m) for g, b in zip(guards, baselines) if not b for m in g.mutations]


def run_guard(guard: Guard) -> list[str]:
    """Failures for one guard. Empty list = every mutation was caught by the right fixture.

    Serial within the guard; `main` parallelises ACROSS mutations instead (#1444), which is
    safe because every mutation runs in its own temp directory against its own subprocess. This
    serial form is what the selftest drives, and it must stay equivalent to `main`'s pool.
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
        problems.extend(run_mutation(guard, mutation))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove each selftest fails when the thing it guards breaks."
    )
    parser.add_argument("--guard", action="append", help="run one guard by name (repeatable)")
    parser.add_argument("--jobs", type=int, default=0,
                        help="mutations run in parallel (default: the CPU count). Every baseline and "
                             "every mutation stages its own tempdir, so they are independent (#1444).")
    parser.add_argument("--selftest", action="store_true",
                        help="prove this checker itself detects a survivor and a stale anchor")
    args = parser.parse_args(argv)

    if args.selftest:
        import mutation_check_selftest as st

        return st.run()

    wanted = set(args.guard or [])
    guards = [g for g in GUARDS if not wanted or g.name in wanted]
    unknown = wanted - {g.name for g in guards}
    if unknown:
        print(f"no guard named {sorted(unknown)!r}; known: {[g.name for g in GUARDS]}", file=sys.stderr)
        return 2
    # TWO PHASES, ONE POOL (#1444). The suite outgrew CI's 900 s allowance, and every dev push run
    # reported the gate as a skip. Parallel across guards alone measured 1.6x on 8 guards, capped by
    # the largest, and lint_self_consistency alone has 137 mutations. So every baseline runs first
    # (an INERT baseline still ends its guard, unscored), then every remaining mutation of every
    # guard runs in the same pool. Output is printed in declaration order, so it reads as a serial run.
    from concurrent.futures import ThreadPoolExecutor
    jobs = max(1, args.jobs or os.cpu_count() or 1)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        baselines = list(pool.map(run_baseline, guards))
        live = live_mutations(guards, baselines)
        outcomes = list(pool.map(lambda gm: run_mutation(*gm), live))
    by_guard: dict[str, list[str]] = {g.name: list(b) for g, b in zip(guards, baselines)}
    for (g, _m), found in zip(live, outcomes):
        by_guard[g.name].extend(found)
    problems: list[str] = []
    total = 0
    for guard in guards:
        total += len(guard.mutations)
        found = by_guard[guard.name]
        status = "ok" if not found else "FAIL"
        print(f"  [{status:4}] {guard.name}: {len(guard.mutations)} mutation(s)")
        problems.extend(found)

    if problems:
        print(f"\nMUTATION CHECK FAILED — {len(problems)} of {total}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"\nmutation check: {total} mutation(s) across {len(guards)} guard(s), all caught "
          f"(jobs={jobs}, {time.monotonic() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
