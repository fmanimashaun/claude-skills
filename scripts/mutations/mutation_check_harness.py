"""Mutation guard: mutation_check itself. Run by scripts/mutation_check.py (#1129).

THE HARNESS HAD NO GUARD. Every other checker here must prove it can fail; the tool that enforces
that did not, because no guard named it as a subject. Its own selftest is the fixture, and the
invariants that read the REAL repo's guards still do so from the staged tempdir -- so mutating the
staged `mutation_check.py` flips them exactly as it would in production.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="mutation_check_harness",
    subject="scripts/mutation_check.py",
    selftest="scripts/mutation_check_selftest.py",
    deps=("scripts/mutation_types.py", "scripts/hermetic_git.py", "scripts/proc_group.py", "plugins/rails-flow/scripts/process_containment.py",),
    mutations=(
        # #1599: the cost ratchet. Each mutation undoes one of its rules; the selftest's section 1f must notice.
        Mutation(
            "a NEW guard over the floor is accepted, so a new expensive guard never has to be made cheaper",
            "        elif secs > RATCHET_FLOOR:",
            "        elif False:",
            "the ratchet must report a NEW guard over the floor",
        ),
        Mutation(
            "a recorded guard may grow without limit",
            "            if secs > limit:",
            "            if False:",
            "the ratchet must report a recorded guard past growth and slack",
        ),
        Mutation(
            "a record that names a guard no longer in the tree is ignored",
            "    for name in sorted(set(recorded) - set(cost)):",
            "    for name in []:",
            "the ratchet must report a record naming a guard that no longer exists",
        ),
        Mutation(
            "no record at all passes the ratchet",
            "    if baseline is None:\n        return [",
            "    if False:\n        return [",
            "with no record at all the ratchet must say so once",
        ),
        Mutation(
            "the record keeps every guard, so it never shrinks or stays readable",
            "if secs > RATCHET_FLOOR}",
            "}",
            "the record must hold only guards over the floor",
        ),
        Mutation(
            "a malformed record reads as empty, which passes everything",
            "        raise ValueError(f\"{path}: not valid JSON ({exc})\") from exc",
            "        return None",
            "a malformed record must raise",
        ),
        # #1599: a mutant runs only the fixture its `expects` names, after a control run of the unmutated code.
        Mutation(
            "a narrowed mutant that is refused (exit 2) counts as caught, because the refusal quotes its label",
            "        if narrow and result.returncode != 1:",
            "        if False:",
            "#1599: a narrowed mutant that is REFUSED (exit 2) must be a problem",
        ),
        Mutation(
            "a narrowing guard's mutants run the whole selftest anyway",
            "            argv.extend(narrow)",
            "            pass",
            "#1599: a narrowing guard must run its baseline whole",
        ),
        Mutation(
            "the unmutated control is skipped, so a fixture that fails alone counts as catching every mutant",
            "            problems = narrow_control(guard, mutation, narrow, timeout)",
            "            problems = []",
            "#1599: a fixture that fails alone, unmutated, must be reported",
        ),
        Mutation(
            "a mutation with no expects is narrowed to an empty fragment",
            "    if guard.narrow_with and mutation.narrow and mutation.expects:",
            "    if guard.narrow_with and mutation.narrow:",
            "#1599: a mutation with no expects must run the whole selftest",
        ),
        Mutation(
            "a mutation that opts out with narrow=False is narrowed anyway",
            "    if guard.narrow_with and mutation.narrow and mutation.expects:",
            "    if guard.narrow_with and mutation.expects:",
            "#1599: a mutation with narrow=False must run the whole selftest",
        ),
        # #1459: progress per guard as it finishes, and a timeout says what it knows.
        Mutation(
            'the per-guard progress line waits for the whole pool again',
            '            print(f"  [done] {name}: {sum(1 for g, _ in live if g.name == name)} mutation(s), "',
            '            (lambda *a, **k: None)(f"  [done] {name}: {sum(1 for g, _ in live if g.name == name)} mutation(s), "',
            "#1459: a guard's progress line prints once",
        ),
        # #1510: baselines and mutants run with git auto-maintenance off.
        Mutation(
            "a BASELINE runs with git's own auto-maintenance",
            '                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=BASELINE_TIMEOUT)',
            '                                timeout=BASELINE_TIMEOUT)',
            '#1510: the baseline and the mutant must run with git maintenance off',
        ),
        Mutation(
            "a MUTANT runs with git's own auto-maintenance",
            '                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=timeout)',
            '                                timeout=timeout)',
            '#1510: the baseline and the mutant must run with git maintenance off',
        ),
        # The wrong-fixture report's tail (#1493): present, 12 lines, 300 characters wide, decoded.
        Mutation(
            "a wrong-fixture report drops the mutant's output",
            '                    + tail_block(output, 12)]',
            '                    + ""]',
            "a wrong-fixture report does not carry the mutant's exit and output",
        ),
        Mutation(
            'the tail is no longer bounded to 12 lines',
            '                    + tail_block(output, 12)]',
            '                    + tail_block(output, 1200)]',
            'a wrong-fixture report does not carry exactly the last 12 lines of output',
        ),
        Mutation(
            "the tail's lines are no longer cut to 300 characters",
            'TAIL_WIDTH = 300\n',
            'TAIL_WIDTH = 300000\n',
            'a wrong-fixture report does not cut each output line to 300 characters',
        ),
        Mutation(
            'a non-UTF-8 byte raises before the report prints',
            '                                text=True, errors="replace",\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=timeout)',
            '                                text=True,\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=timeout)',
            "a non-UTF-8 byte in a mutant's output raised before the report printed",
        ),
        Mutation(
            # #1129: the import-completeness invariant. Adding an import to a shipped module orphans
            # every neighbouring guard that stages it without the new dependency -- the mutant dies
            # on ModuleNotFoundError, which is an ENVIRONMENTAL failure, not a caught mutation.
            # Three occurrences (#1113, #1114, #1133) and all three surfaced only in the sweep.
            "a module-scope import is no longer seen, so an unstaged dependency passes",
            "            if isinstance(node, ast.Import):",
            "            if False:",
            "",
        ),
        Mutation(
            # THE CARVE-OUT, and it is what keeps the rule usable: a `def`-scope import is optional
            # at load time. Counting those flagged SIX correct guards on the first run -- every
            # shipped script that imports its own selftest inside `if args.selftest:`.
            "function-scope imports count again, so correct guards are reported",
            "    scan(tree.body)",
            "    scan([n for n in ast.walk(tree)])",
            "",
        ),
        Mutation(
            # #1444: main's pool must keep run_guard's rule -- an INERT baseline scores nothing.
            "the pool runs mutations of a guard whose baseline failed",
            "zip(guards, baselines) if not b for m",
            "zip(guards, baselines) for m",
            "an INERT baseline must end its guard",
        ),
        Mutation(
            # #1444: the transitive scan. check_slices went INERT through an import made by a need.
            "the import scan stops at one level again",
            "            pending.append(str(sibling.relative_to(base)))",
            "            pass",
            "an unstaged import's own imports must be reported too",
        ),
        Mutation(
            # #1444: THE check_slices case -- a need's own imports went unread.
            "needs files are no longer scanned for imports",
            "    pending = sorted(staged | {n for n in guard.needs if (base / n).is_file()})",
            "    pending = sorted(staged)",
            "a need no staged file imports must still be scanned",
        ),
        Mutation(
            # #1486
            'the per-mutation limit is fixed again, ignoring the baseline',
            '    return min(MUTATION_CAP, max(MUTATION_FLOOR, MUTATION_SCALE * baseline_seconds))',
            '    return MUTATION_FLOOR',
            "#1486: a slow guard's mutant must get a limit scaled from its baseline",
        ),
        Mutation(
            # #1486
            "main's pool gives every guard the floor",
            '    return {g.name: mutation_timeout(secs) for g, (_, secs) in zip(guards, timed)}',
            '    return {g.name: MUTATION_FLOOR for g in guards}',
            "#1486: main's pool must give each guard max(floor, 3x baseline)",
        ),
        Mutation(
            # #1486
            'run_guard ignores the limit it derived',
            '        problems.extend(run_mutation(guard, mutation, limit))',
            '        problems.extend(run_mutation(guard, mutation))',
            '#1486 CONTROL: with no scaling, the fixed floor must time the mutant out',
        ),
        Mutation(
            # review of PR #1491
            "main's pool drops the derived limit (the path CI runs)",
            '    futures = {pool.submit(timed_run, run_mutation, g, m, limits[g.name]): i for i, (g, m) in enumerate(live)}',
            '    futures = {pool.submit(timed_run, run_mutation, g, m): i for i, (g, m) in enumerate(live)}',
            "#1486 CONTROL: main()'s pool with no scaling must time the mutant out",
        ),
        Mutation(
            # review of PR #1491
            'the per-mutation cap is dropped, so one mutant can outlast the whole gate',
            '    return min(MUTATION_CAP, max(MUTATION_FLOOR, MUTATION_SCALE * baseline_seconds))',
            '    return max(MUTATION_FLOOR, MUTATION_SCALE * baseline_seconds)',
            "#1486: main's pool must give each guard max(floor, 3x baseline)",
        ),
        Mutation(
            # #1497
            "the baseline drops a guard's selftest_args",
            '        argv.extend(guard.selftest_args)\n        started',
            '        started',
            "#1497: a guard's selftest_args must reach its baseline and mutants",
        ),
        Mutation(
            # #1493, baseline half
            "a non-UTF-8 byte in a BASELINE's output raises before the INERT report prints",
            '                                text=True, errors="replace",\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=BASELINE_TIMEOUT)',
            '                                text=True,\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=BASELINE_TIMEOUT)',
            "a non-UTF-8 byte in a BASELINE's output raised before the INERT report printed",
        ),
        Mutation(
            # #1532: one interleaved stream. The old `capture_output` + `stdout + stderr` put 12+ lines
            # of stderr after a label printed to stdout, and the label fell off the tail.
            "the mutant's stdout and stderr are concatenated, not interleaved",
            'cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,\n                                text=True, errors="replace",\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=timeout)\n        output = result.stdout',
            'cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,\n                                text=True, errors="replace",\n                                env=hermetic_git.env(),  # no detached git maintenance (#1510)\n                                timeout=timeout)\n        output = result.stdout + result.stderr',
            "a wrong-fixture tail hides a label printed to stdout behind 12+ stderr lines",
        ),
        Mutation(
            # #1531: the INERT report shares the 300-character cut.
            "the INERT report is no longer cut to 300 characters",
            '                + tail_block(result.stdout, 6)',
            '                + "\\n" + "\\n".join(f"      {r}" for r in result.stdout.strip().splitlines()[-6:])',
            "the INERT report does not cut each output line to 300 characters",
        ),
        Mutation(
            # #1530: both timeout branches keep what the child printed before the limit.
            "a BASELINE's timeout drops what it printed",
            '                + tail_block(exc.stdout, 12)], BASELINE_TIMEOUT',
            '                ], BASELINE_TIMEOUT',
            "a BASELINE's timeout report drops what it printed before the limit",
        ),
        Mutation(
            "a MUTANT's timeout drops what it printed",
            '-{MUTATION_CAP:.0f}s)"\n                + tail_block(exc.stdout, 12)]',
            '-{MUTATION_CAP:.0f}s)"]',
            "a MUTANT's timeout report drops what it printed before the limit",
        ),
        Mutation(
            # review of PR #1506
            "a mutant drops its guard's selftest_args",
            '        argv.extend(guard.selftest_args)\n        narrow = narrowing(guard, mutation)',
            '        narrow = narrowing(guard, mutation)',
            "#1497: a guard's selftest_args must reach its baseline and mutants",
        ),
        Mutation(
            # review of #1525, blocker 2: the pool joined at the slowest running mutant
            "Ctrl-C under main's pool leaves its baselines and mutants running",
            '    with proc_group.pool(jobs) as pool:',
            '    with __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=jobs) as pool:',
            "#1459: Ctrl-C under mutation_check's pool left work running",
        ),
    ),
)
