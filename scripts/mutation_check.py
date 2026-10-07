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
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import proc_group  # noqa: E402 -- a timeout kills the whole process group (#1459)
import hermetic_git  # noqa: E402 -- the runner's subprocesses start no detached git (#1510)
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


# THE COST RATCHET (#1599). `mutation coverage` reached 3490 s of its 3600 s budget and the CI log could not say which
# guard had grown: the doctor kept one summary line. A guard over RATCHET_NEW CPU seconds of work (#1635; baseline plus every
# mutant, summed over all jobs) must be on record in COST_BASELINE, which holds every guard over RATCHET_FLOOR; a recorded one may cost RATCHET_GROWTH times its
# record plus RATCHET_SLACK, which keeps a runner's speed from reading as growth; a record naming a guard that is gone
# is drift. A new expensive guard therefore fails until it is made cheaper (`narrow_with`) or recorded from a measured
# run with `--rebaseline`, a diff somebody reviews. Seconds depend on the runner, so the record is measured where the gate
# runs (CI) and enforced only with `--ratchet`, which the doctor passes on the run whose job is to prove this gate.
COST_BASELINE = REPO / "docs" / "evidence" / "mutation-cost-baseline.json"
RATCHET_FLOOR = 60.0
# A guard NOT on record fails only over RATCHET_NEW, twice the floor that decides what gets recorded. The record holds the
# guards that cost over 60 s; one that cost 55 s when it was made is not in it, and a runner that is 1.5x slower on the day
# reads it as 82 s without anyone having made it more expensive. Measured on the runner (run 37183258895): the CI's
# runner speed moved the whole gate between 967 s and 1536 s for the same work.
RATCHET_NEW = 120.0
# GROWTH IS TWICE THE RECORD, NOT 1.5x: a tolerance below the runner's own noise fails on a guard nobody touched. MEASURED: `hook_coordination`,
# whose guard, subject and selftest are byte-identical between the two runs, cost 840 s in run 37273819948 and 1301 s in run 37279335358
# (1.55x), the whole gate had moved 967 s to 1536 s (1.59x) before, and 1.5x tripped it. Twice the record plus the slack still refuses a
# guard that has MORE than doubled.
RATCHET_GROWTH = 2.0
RATCHET_SLACK = 30.0
# WHAT A FAILING RUN TELLS THE AUTHOR TO DO. The rule is that whoever adds or grows a heavy guard re-records it in the SAME PR, so the
# cost lands as a reviewed one-line diff and a later PR's dispatched run is never the one to trip on it (#1599).
RECORD_INSTRUCTION = ("re-record docs/evidence/mutation-cost-baseline.json in this PR from this run's cost "
                      "(`python3 scripts/mutation_check.py --rebaseline` writes it)")
# THE LOAD A RECORD IS FAIR AT (#1652). CPU seconds are steadier than wall seconds but not load-independent on a machine with
# efficiency cores: MEASURED on the 10-core maintainer machine, `lint_self_consistency` (178 mutations, byte-identical between the
# record and the failing run) cost 688 s at jobs 10 and ambient load, 528 s at jobs 4, 826 s and 1010 s with five busy loops added, and
# 1418 s in a `--record-proof` run under heavy load (record 669 s): a growth failure that was the machine. So a failure prints the 5-minute
# load and the job count it ran at, and says whether they are what the record was made at (a load under this, and the recorded jobs).
RATCHET_QUIET_LOAD = 10.0


def five_minute_load() -> float | None:
    """The 5-minute load average, or None where the platform has none: a figure that is missing must read as missing, not as 0."""
    try:
        return float(os.getloadavg()[1])
    except (AttributeError, OSError):
        return None


def ratchet_context(load: float | None, jobs: int, recorded_jobs: int | None) -> str:
    """One sentence for a ratchet failure: the load and job count it ran at, and whether that is a fair comparison with the record.

    A quiet machine at the recorded job count makes the failure growth; anything else makes it a question to re-run first."""
    seen = (f"the 5-minute load was {load:.1f} at the start and jobs={jobs}" if load is not None
            else f"the load average is unavailable here and jobs={jobs}")
    if load is not None and load <= RATCHET_QUIET_LOAD and recorded_jobs == jobs:
        return (f"ratchet context: {seen}, the conditions the record was made at (a load under {RATCHET_QUIET_LOAD:g}), "
                "so read this as growth.")
    return (f"ratchet context: {seen}; the record was made at jobs={recorded_jobs if recorded_jobs is not None else '?'} and a load "
            f"under {RATCHET_QUIET_LOAD:g}. CPU seconds rise with load and with the job count (about 1.5x with half the cores busy, "
            "1.3x from 4 to 10 jobs; #1652), so re-run on a quiet machine at the recorded job count before treating this as growth, "
            "and do not re-record from this run: a record made under load would hide real growth later.")


# THE COST IS CPU SECONDS (#1635). Each baseline, narrowing control and mutant run reports the CPU time (user + system) of itself and
# every process it waited for; those are summed per guard here. Wall time is still used for the per-mutation LIMITS (a hung run
# must still be killed on the clock), but it is no measure of cost: it stretches with the machine's load, so a loaded laptop failed
# the ratchet on guards nobody had touched. A run killed on its limit bills its wall time, the one figure it has.
_COST: dict[str, float] = {}
_COST_LOCK = threading.Lock()


def bill(guard_name: str, seconds: float) -> None:
    with _COST_LOCK:
        _COST[guard_name] = _COST.get(guard_name, 0.0) + seconds


def run_costed(guard_name: str, argv, *, timeout: float, **kw) -> subprocess.CompletedProcess:
    """`proc_group.run`, billing the run's CPU seconds to `guard_name`."""
    started = time.monotonic()
    try:
        result, cpu = proc_group.run_cpu(argv, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        bill(guard_name, time.monotonic() - started)
        raise
    bill(guard_name, cpu if cpu is not None else time.monotonic() - started)
    return result


def load_cost_baseline(path: Path = COST_BASELINE) -> dict | None:
    """The record, or None when there is no file. A file that is not a record RAISES: read as empty it would pass."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc})") from exc
    guards = data.get("guards") if isinstance(data, dict) else None
    if not isinstance(guards, dict) or not all(isinstance(v, (int, float)) for v in guards.values()):
        raise ValueError(f"{path}: needs a 'guards' object mapping a guard name to its seconds of work")
    return data


def write_cost_baseline(path: Path, cost: dict[str, float], jobs: int) -> None:
    """Record every guard over the floor, rounded and in a stable order, so a re-baseline is a reviewable diff."""
    heavy = {name: round(secs, 1) for name, secs in sorted(cost.items()) if secs > RATCHET_FLOOR}
    record = {"note": "CPU seconds (user + system) of work per guard (baseline plus every mutant, summed over all jobs) from a measured "
                      "full run; re-set with `python3 scripts/mutation_check.py --rebaseline` (#1599)",
              "jobs": jobs, "floor": RATCHET_FLOOR, "guards": heavy}
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_problems(guard_names: set[str], baseline: dict | None) -> list[str]:
    """What is wrong with the cost record itself, with no run needed: it is missing, or it names a guard that is gone.
    The full ratchet and the cheap `--check-record` gate both read it here, so the two cannot disagree."""
    if baseline is None:
        return ["the cost ratchet has no cost record (docs/evidence/mutation-cost-baseline.json): run "
                "`python3 scripts/mutation_check.py --rebaseline` from a measured full run and commit it"]
    return [f"{name}: the cost record names a guard that no longer exists; re-set the record (--rebaseline)"
            for name in sorted(set(baseline["guards"]) - guard_names)]


def cost_problems(cost: dict[str, float], baseline: dict) -> list[str]:
    """The cost refusals alone: a recorded guard past its growth, a new guard over the new-guard limit."""
    problems = []
    recorded = baseline["guards"]
    for name, secs in sorted(cost.items()):
        if name in recorded:
            limit = recorded[name] * RATCHET_GROWTH + RATCHET_SLACK
            if secs > limit:
                problems.append(f"{name}: costs {secs:.0f}s of work, past {RATCHET_GROWTH:g}x its recorded "
                                f"{recorded[name]:.0f}s plus {RATCHET_SLACK:g}s = {limit:.0f}s; make it cheaper, "
                                f"or {RECORD_INSTRUCTION}")
        elif secs > RATCHET_NEW:
            problems.append(f"{name}: a NEW guard costing {secs:.0f}s of work, over the {RATCHET_NEW:g}s new-guard limit "
                            "and not on record; make it cheaper (`narrow_with` runs each mutant on one fixture), or "
                            f"{RECORD_INSTRUCTION}")
    return problems


def ratchet_problems(cost: dict[str, float], baseline: dict | None) -> list[str]:
    """What the cost ratchet refuses, as sentences; an empty list is within budget."""
    problems = record_problems(set(cost), baseline)
    if baseline is None:
        return problems
    return problems + cost_problems(cost, baseline)


def ratchet_notes(cost: dict[str, float], baseline: dict | None, context: str) -> list[str]:
    """What to print AFTER the refusals (#1652): the load and job count context, once, and only when a COST was refused.

    A note is not a problem (the failure header counts problems), and a clean run or a record-only refusal (a missing record, a guard that
    is gone) has no cost to explain, so it carries no extra line."""
    return [context] if baseline is not None and cost_problems(cost, baseline) else []


def failure_report(problems: list[str], notes: list[str], total: int) -> str:
    """The text of a failing run: the header counts the PROBLEMS (a note is not one), each on its own line, then the notes."""
    lines = [f"\nMUTATION CHECK FAILED — {len(problems)} of {total}:"]
    lines += [f"  - {problem}" for problem in problems]
    lines += [f"  {note}" for note in notes]
    return "\n".join(lines)


# PER-MUTATION LIMITS COME FROM THE GUARD'S OWN BASELINE (#1486). A fixed 300 s bound was shorter than
# the hook suite takes under load (60 s idle, 367 s at load ~149), so 10 of 12 `hook_guard_bash`
# mutations "timed out" on one run and all 12 were caught on the next. A mutant runs the same
# selftest as its baseline and usually stops sooner, so its limit scales with what the baseline
# actually took on THIS machine, now. The baseline itself runs once per guard and must finish.
#
# BOTH CAPS STAY WELL UNDER THE GATE'S TOTAL (`SLOW_GATES["mutation coverage"]`, maintainer_doctor.py):
# a hung guard must be reported HERE, by name, before the doctor kills the whole gate with a message
# that names no guard (review of PR #1491). maintainer_doctor_selftest asserts the relation.
BASELINE_TIMEOUT = 600
MUTATION_FLOOR = 300.0
MUTATION_SCALE = 3.0
MUTATION_CAP = 900.0


def mutation_timeout(baseline_seconds: float) -> float:
    return min(MUTATION_CAP, max(MUTATION_FLOOR, MUTATION_SCALE * baseline_seconds))


def mutation_limits(guards: list[Guard], timed: list[tuple[list[str], float]]) -> dict[str, float]:
    """`main`'s pool: each guard's per-mutation limit, from its own timed baseline."""
    return {g.name: mutation_timeout(secs) for g, (_, secs) in zip(guards, timed)}


TAIL_WIDTH = 300


def tail_block(output: str | bytes | None, lines: int) -> str:
    """The last `lines` lines of a child's output as an indented report block, each cut to
    `TAIL_WIDTH` characters so one huge line cannot flood a CI log (#1493, #1531).

    Empty when the child printed nothing, so a report never ends in a bare newline. Accepts bytes
    and None because `TimeoutExpired.stdout` is either, whatever `text=True` said (#1530); bytes
    are decoded with `errors="replace"` for the reason the two `subprocess.run` calls below are.
    """
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    rows = (output or "").strip().splitlines()[-lines:]
    return "".join(f"\n      {row[:TAIL_WIDTH]}" for row in rows)


def run_baseline(guard: Guard) -> list[str]:
    return run_baseline_timed(guard)[0]


def run_baseline_timed(guard: Guard) -> tuple[list[str], float]:
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
        argv.extend(guard.selftest_args)
        started = time.monotonic()                # after staging: the limit is the selftest's time
        # `errors="replace"` here too (#1493 applied it to mutants only): a non-UTF-8 byte in a
        # BASELINE's output raised before the INERT report could print.
        # stderr folded into stdout: one stream in the order it was written, so a tail of it is
        # what a person watching would have seen (#1532). Its own process group (#1459).
        result = run_costed(guard.name, argv, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace",
                                env=hermetic_git.env(),  # no detached git maintenance (#1510)
                                timeout=BASELINE_TIMEOUT)
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            return [
                f"{guard.name}: INERT — the UNMUTATED selftest already fails in the staged "
                f"tempdir (exit {result.returncode}), so every mutation below is 'caught' whether "
                "or not it breaks anything. Add what it reads to the guard's `needs`."
                + tail_block(result.stdout, 6)
            ], elapsed
    except subprocess.TimeoutExpired as exc:
        # The whole process group is killed (#1459), and what it printed before the limit is in
        # hand; without it a CI-only timeout has no clue (#1530).
        return [f"{guard.name}: the unmutated baseline timed out after {BASELINE_TIMEOUT}s"
                + tail_block(exc.stdout, 12)], BASELINE_TIMEOUT
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return [], elapsed



def narrowing(guard: Guard, mutation: Mutation) -> tuple[str, ...]:
    """`<flag> <expects>` when this mutant is to run only the fixture that must catch it (#1599), else `()`.

    A mutant has to be caught by the fixture its `expects` names, so that fixture is the only one it needs; the
    guards that adopt this went from about 116 s to about 4 s per mutant. A mutation without an `expects`, or one
    that sets `narrow=False`, still runs the whole selftest."""
    if guard.narrow_with and mutation.narrow and mutation.expects:
        return (guard.narrow_with, mutation.expects)
    return ()


def narrow_control(guard: Guard, mutation: Mutation, narrow: tuple[str, ...], timeout: float) -> list[str]:
    """The UNMUTATED selftest, run with the same narrowing, must PASS (#1599).

    Without it a fixture that cannot pass on its own (it leans on state another fixture sets up) fails every
    mutant for that reason and reads as a catch, and an `expects` that selects nothing would read as one too.
    Problems, or an empty list."""
    workdir = Path(tempfile.mkdtemp(prefix=f"mutctl-{guard.name}-"))
    try:
        entry = stage(guard, workdir)
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            argv.append("--selftest")
        argv.extend(guard.selftest_args)
        argv.extend(narrow)
        result = run_costed(guard.name, argv, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", env=hermetic_git.env(), timeout=timeout)
        if result.returncode == 0:
            return []
        return [f"{guard.name}: {mutation.name!r} cannot be narrowed: the UNMUTATED selftest fails (exit "
                f"{result.returncode}) when run only for {mutation.expects!r}. Either that fixture leans on state "
                "another fixture sets up, or `expects` selects no check; fix the fixture or the label, or set "
                "`narrow=False` on this mutation." + tail_block(result.stdout, 8)]
    except subprocess.TimeoutExpired as exc:
        return [f"{guard.name}: {mutation.name!r} cannot be narrowed: the unmutated control timed out after "
                f"{timeout:.0f}s" + tail_block(exc.stdout, 8)]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_mutation(guard: Guard, mutation: Mutation, timeout: float = MUTATION_FLOOR) -> list[str]:
    """One mutation, in its own tempdir. Independent of every other mutation, so the suite can run
    them in parallel (#1444). `run_guard` and `main` both come through here: one implementation."""
    workdir = Path(tempfile.mkdtemp(prefix=f"mutcheck-{guard.name}-"))
    started = time.monotonic()
    try:
        entry = apply_mutation(guard, mutation, workdir)
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            argv.append("--selftest")   # the selftest is a flag on the module itself
        argv.extend(guard.selftest_args)
        narrow = narrowing(guard, mutation)
        if narrow:
            problems = narrow_control(guard, mutation, narrow, timeout)
            if problems:
                return problems
            argv.extend(narrow)
        # `errors="replace"`: a non-UTF-8 byte must not raise before the report can print (#1493).
        # stderr folded into stdout, as in the baseline: `stdout + stderr` put the last 12 lines of
        # stderr in front of a label printed to stdout, and 12+ stderr lines hid it (#1532).
        started = time.monotonic()
        result = run_costed(guard.name, argv, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace",
                                env=hermetic_git.env(),  # no detached git maintenance (#1510)
                                timeout=timeout)
        output = result.stdout
        if result.returncode == 0:
            return [f"{guard.name}: SURVIVED — {mutation.name}. The selftest passed with this "
                    "broken, so nothing guards it."]
        if narrow and result.returncode != 1:
            # A refusal (exit 2) quotes the very label `expects` names, so the label check below would score it as a
            # catch; a crash is no catch either. Only the selftest's own failure, exit 1, is one (review of #1603, F1).
            return [f"{guard.name}: {mutation.name!r} was refused or crashed under narrowing (exit "
                    f"{result.returncode}), which is not a catch: only the selftest's own failure (exit 1) counts"
                    + tail_block(output, 8)]
        if mutation.expects and mutation.expects.lower() not in output.lower():
            # The mutant's own last lines, as the INERT report prints: a wrong-fixture catch seen
            # only on CI was undiagnosable without them, because CI keeps nothing else (#1493). The
            # last 12 lines, each cut to 300 characters, so one huge line cannot flood the log.
            return [f"{guard.name}: caught {mutation.name!r} but not by the expected fixture "
                    f"(no mention of {mutation.expects!r}, exit {result.returncode}) — a coincidental "
                    "catch would hide that fixture going quiet"
                    + tail_block(output, 12)]
        return []
    except subprocess.TimeoutExpired as exc:
        # The whole process group is killed (#1459), so nothing it started is left running; the
        # report carries the guard, the mutation, the elapsed time and the mutant's last lines (#1530).
        return [f"{guard.name}: {mutation.name} timed out after {time.monotonic() - started:.0f}s "
                f"(limit {timeout:.0f}s: {MUTATION_SCALE:g}x its baseline, within "
                f"{MUTATION_FLOOR:.0f}-{MUTATION_CAP:.0f}s)"
                + tail_block(exc.stdout, 12)]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_live(pool, live: list[tuple[Guard, Mutation]], limits: dict[str, float]) -> list[tuple[list[str], float]]:
    """Every live mutation through `pool`, outcomes in `live`'s order. Each guard's progress line is
    printed the moment its LAST mutation finishes, so a run the doctor kills on a timeout still shows
    how far it got -- since #1444 the per-guard lines waited for the whole pool (#1459)."""
    from concurrent.futures import as_completed
    remaining: dict[str, int] = {}
    for guard, _ in live:
        remaining[guard.name] = remaining.get(guard.name, 0) + 1
    found_by: dict[str, int] = {name: 0 for name in remaining}
    futures = {pool.submit(timed_run, run_mutation, g, m, limits[g.name]): i for i, (g, m) in enumerate(live)}
    outcomes: list[tuple[list[str], float] | None] = [None] * len(live)
    for future in as_completed(futures):
        i = futures[future]
        outcomes[i] = future.result()
        name = live[i][0].name
        found_by[name] += len(outcomes[i][0])
        remaining[name] -= 1
        if remaining[name] == 0:
            print(f"  [done] {name}: {sum(1 for g, _ in live if g.name == name)} mutation(s), "
                  f"{found_by[name]} problem(s)", flush=True)
    return outcomes  # type: ignore[return-value]


def timed_run(fn, *args):
    """`fn(*args)` and the wall seconds it took, for the per-guard cost line (#1497)."""
    started = time.monotonic()
    return fn(*args), time.monotonic() - started


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
    problems, baseline_seconds = run_baseline_timed(guard)
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
    limit = mutation_timeout(baseline_seconds)
    for mutation in guard.mutations:
        problems.extend(run_mutation(guard, mutation, limit))
    return problems


def main(argv: list[str] | None = None) -> int:
    proc_group.restore_sigint()   # #1635: see its docstring; the Ctrl-C selftests need a SIGINT that arrives
    parser = argparse.ArgumentParser(
        description="Prove each selftest fails when the thing it guards breaks."
    )
    parser.add_argument("--guard", action="append", help="run one guard by name (repeatable)")
    parser.add_argument("--jobs", type=int, default=0,
                        help="mutations run in parallel (default: the CPU count). Every baseline and "
                             "every mutation stages its own tempdir, so they are independent (#1444).")
    parser.add_argument("--selftest", action="store_true",
                        help="prove this checker itself detects a survivor and a stale anchor")
    parser.add_argument("--ratchet", action="store_true",
                        help="also fail when a guard's cost has grown past the committed record, or a new guard is "
                             "over the floor (#1599); a full run only")
    parser.add_argument("--check-record", action="store_true",
                        help="check only that the committed cost record exists, parses, and names no guard that is gone; "
                             "runs no guard, so a pull request can afford it (#1599)")
    parser.add_argument("--rebaseline", action="store_true",
                        help="after a full run, rewrite the committed cost record from it (#1599)")
    args = parser.parse_args(argv)
    if args.check_record:
        try:
            found = record_problems({g.name for g in GUARDS}, load_cost_baseline())
        except ValueError as exc:
            found = [f"the cost record is unreadable: {exc}"]
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        if not found:
            print(f"cost record: ok ({len(load_cost_baseline()['guards'])} guard(s) on record, none gone)")
        return 1 if found else 0
    if (args.ratchet or args.rebaseline) and args.guard:
        print("--ratchet and --rebaseline compare a FULL run; --guard runs a part of one", file=sys.stderr)
        return 2

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
    #
    # `proc_group.pool`, not a bare ThreadPoolExecutor: each baseline and mutant runs in a session of
    # its own, so Ctrl-C reaches only this process, and a bare pool's join waited for the slowest
    # running mutant while every one of them kept going (review of #1525: 24 s, survivors).
    jobs = max(1, args.jobs or os.cpu_count() or 1)
    start_load = five_minute_load()     # BEFORE the pool starts: this run's own work is not the load it ran under (#1652)
    started = time.monotonic()
    with proc_group.pool(jobs) as pool:
        timed = list(pool.map(run_baseline_timed, guards))
        baselines = [problems for problems, _ in timed]
        limits = mutation_limits(guards, timed)
        live = live_mutations(guards, baselines)
        outcomes = run_live(pool, live, limits)
    by_guard: dict[str, list[str]] = {g.name: list(b) for g, b in zip(guards, baselines)}
    # Seconds each guard cost, in CPU time (#1635): its baseline plus every mutant run (#1497). The CI log printed only
    # the gate total, so where the budget went could not be read from it.
    for (g, _m), (found, _secs) in zip(live, outcomes):
        by_guard[g.name].extend(found)
    with _COST_LOCK:
        cost: dict[str, float] = {g.name: _COST.get(g.name, 0.0) for g in guards}
    problems: list[str] = []
    notes: list[str] = []
    total = 0
    for guard in guards:
        total += len(guard.mutations)
        found = by_guard[guard.name]
        status = "ok" if not found else "FAIL"
        print(f"  [{status:4}] {guard.name}: {len(guard.mutations)} mutation(s), {cost[guard.name]:.0f}s")
        problems.extend(found)

    over_floor = sorted(((n, s) for n, s in cost.items() if s > RATCHET_FLOOR), key=lambda kv: -kv[1])
    if args.rebaseline:
        write_cost_baseline(COST_BASELINE, cost, jobs)
        print(f"cost record rewritten: {COST_BASELINE.relative_to(REPO)} ({len(over_floor)} guard(s) over the "
              f"{RATCHET_FLOOR:g}s floor)")
    elif args.ratchet:
        try:
            baseline = load_cost_baseline()
            problems.extend(ratchet_problems(cost, baseline))
            notes = ratchet_notes(cost, baseline, ratchet_context(start_load, jobs, (baseline or {}).get("jobs")))
        except ValueError as exc:
            problems.append(f"the cost record is unreadable: {exc}")
    if problems:
        print(failure_report(problems, notes, total), file=sys.stderr)
        return 1
    print(f"\nmutation check: {total} mutation(s) across {len(guards)} guard(s), all caught "
          f"(jobs={jobs}, {time.monotonic() - started:.0f}s)")
    heaviest = sorted(cost.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print("heaviest guards (seconds of work, all jobs): "
          + ", ".join(f"{name} {secs:.0f}s" for name, secs in heaviest))
    # The table the cost record is made from, in the log of the run that measured it: before #1599 the CI log held
    # only the two lines above, so no one could see which guard had grown.
    print(f"total work: {sum(cost.values()):.0f}s across {len(guards)} guard(s)")
    print(f"work by guard over the {RATCHET_FLOOR:g}s floor (seconds, all jobs): "
          + (", ".join(f"{name} {secs:.0f}" for name, secs in over_floor) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
