"""Mutation guard: check_hook_gates (the harness itself). Declared here, run by scripts/mutation_check.py (#1469).

The hook guards mutate the HOOKS and use check_hook_gates.py as their selftest; nothing mutated the
harness. #1469 was a harness defect: a subprocess timeout raised and crashed the suite, so fixtures
after it never printed, and under parallel load a mutation read as "caught by the wrong fixture".
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_hook_gates_harness",
    subject="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Its mutations target --only/run_groups (checked at the start of EVERY run) and the timeout
    # handling (the `timeout` group). The doctor's `hook gates` gate still runs every group (#1497).
    selftest_args=("--only", "timeout", "--fail-fast"),
    # The same staging as hook_guard_bash: the suite drives every plugin's hooks. A literal, because
    # lint_self_consistency's harness-dependency-undeclared rule reads it statically -- and that rule is
    # what keeps this copy honest when a hook gains a script (it caught exactly that on #1477).
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        # #1599: `--match` runs only the fixtures a label names. Each mutation undoes one half of that.
        Mutation(
            "--match selects every check, so a narrowed mutant still runs the whole group",
            "_WANTED = {i for i, label in enumerate(_SURVEYED) if match.lower() in label.lower()}",
            "_WANTED = set(range(len(_SURVEYED)))",
            "--match runs only the fixture whose label matches",
        ),
        Mutation(
            "the code before an unwanted check still runs for real, so --match saves nothing",
            "        _SKIP = _INDEX not in _WANTED",
            "        _SKIP = False",
            "--match runs only the fixture whose label matches",
        ),
        Mutation(
            "the survey runs the fixtures for real instead of only listing them",
            'return _MATCH_MODE == "survey" or (_MATCH_MODE == "run" and _SKIP)',
            'return _MATCH_MODE == "run" and _SKIP',
            "--match runs only the fixture whose label matches",
        ),
        Mutation(
            "a run pass that disagrees with the survey is accepted, so --match can name the wrong check",
            "if _INDEX >= len(_SURVEYED) or _SURVEYED[_INDEX] != _stable(label):",
            "if False:",
            "--match raises when a fixture's result steers which checks follow",
        ),
        Mutation(
            "a nested selftest runs the real groups, so a broken --only refusal runs the whole suite inside the proof of it",
            "    return not nested and not (fail_fast and bool(failures))",
            "    return not (fail_fast and bool(failures))",
            "a nested selftest, which only proves a refusal, never runs the real groups",
        ),
        Mutation(
            "--fail-fast never skips the groups, so a mutant of the group machinery still runs the whole suite",
            "    return not nested and not (fail_fast and bool(failures))",
            "    return not nested",
            "--fail-fast skips the real groups once a meta-check has failed",
        ),
        Mutation(
            "a --match that selects nothing passes, so a mutant whose label is stale is never judged",
            "        if ran_matching == 0:",
            "        if False:",
            "main() exits 2 for --match that selects nothing",
        ),
        Mutation(
            "an unexpected timeout is not recorded, so a setup step that times out passes silently",
            "            if not _EXPECTING_TIMEOUT:\n                record_failure(note)",
            "            if False:\n                record_failure(note)",
            "an UNEXPECTED timeout is recorded as a failure",
        ),
        Mutation(
            "a subprocess timeout raises again, crashing the suite before later fixtures print",
            "        except subprocess.TimeoutExpired:\n            try:\n                os.killpg(proc.pid, signal.SIGKILL)",
            "        except OSError:\n            try:\n                os.killpg(proc.pid, signal.SIGKILL)",
            "a timed-out hook fixture fails by name and the suite still finishes",
        ),
        Mutation(
            "the hook shares the suite's process group, so its stubs outlive a timeout",
            "    with subprocess.Popen(*args, start_new_session=True, **kw) as proc:",
            "    with subprocess.Popen(*args, **kw) as proc:",
            "returns promptly, because nothing it started still holds the output pipe",
        ),
        Mutation(
            "a timeout kills only the direct child, orphaning the stubs it started",
            "                os.killpg(proc.pid, signal.SIGKILL)",
            "                proc.kill()",
            "leaving no orphaned stub",
        ),
        Mutation(
            # #1497
            "--only accepts an unknown group, so a guard's selection can silently run nothing",
            '    if any(g not in GROUPS for g in groups) or len(set(groups)) != len(groups):',
            '    if len(set(groups)) != len(groups):',
            "--only 'nope' is refused",
        ),
        Mutation(
            # #1497
            '--only runs every group whatever it names',
            'def run_groups(groups: list[str] | None, table: dict) -> None:\n    for name in (groups or list(table)):',
            'def run_groups(groups: list[str] | None, table: dict) -> None:\n    for name in list(table):',
            '--only runs exactly the groups it names',
        ),
        Mutation(
            # review of PR #1506
            '--only accepts a group named twice',
            '    if any(g not in GROUPS for g in groups) or len(set(groups)) != len(groups):',
            '    if any(g not in GROUPS for g in groups):',
            "--only 'timeout,timeout' is refused",
        ),
        Mutation(
            # #1596
            "a label's temp path is not masked, so a group that surveys clean on a Mac is refused on the Linux runner",
            '    return _TEMP_PATH.sub("<tmp>", label)',
            '    return label',
            "a label's temp path is masked",
        ),
        Mutation(
            # review of PR #1506
            "a bare run executes no group, so the doctor's hook gates pass on nothing",
            'def run_groups(groups: list[str] | None, table: dict) -> None:\n    for name in (groups or list(table)):',
            'def run_groups(groups: list[str] | None, table: dict) -> None:\n    for name in (groups or []):',
            'a bare run (no --only) runs every group',
        ),
        Mutation(
            # review of PR #1506
            'main() stops refusing a bad --only',
            '                  f"known: {\', \'.join(GROUPS)}", file=sys.stderr)\n            return 2',
            '                  f"known: {\', \'.join(GROUPS)}", file=sys.stderr)',
            'main() exits 2 for --only nope',
        ),
        Mutation(
            "a fixture group is left out of every part, so the doctor would never run it",
            '"b": ["release_gate", "release_gate_effects"],',
            '"b": ["release_gate"],',
            "every fixture group is in exactly one PART",
        ),
        Mutation(
            "an unknown --part is accepted instead of refused",
            "    return list(PARTS[value]) if value in PARTS else None",
            "    return list(PARTS.get(value, PARTS['a']))",
            "any other part is refused",
        ),

        # #1638: a hook's wall budget scales with how much slower than idle the machine is, so a loaded machine is not read as a hung hook.
        Mutation(
            "the budget ignores the machine's slowdown, so a loaded machine is read as a hung hook again",
            "    return max(base, min(HOOK_BUDGET_CAP, base * max(1.0, slowdown)))",
            "    return base",
            "a slower machine gets proportionally more",
        ),
        Mutation(
            "the cap is gone, so a hang under load waits for ever longer",
            "    return max(base, min(HOOK_BUDGET_CAP, base * max(1.0, slowdown)))",
            "    return max(base, base * max(1.0, slowdown))",
            "the budget stops at the cap",
        ),
        Mutation(
            "the floor drops to 60 s, which a loaded machine outran (#1469)",
            "HOOK_BUDGET_FLOOR = 180.0",
            "HOOK_BUDGET_FLOOR = 60.0",
            "an idle machine gets the floor",
        ),
        Mutation(
            "a fixture's own larger bound is ignored",
            "    base = max(float(requested or 0), HOOK_BUDGET_FLOOR)",
            "    base = HOOK_BUDGET_FLOOR",
            "a fixture's own larger bound is kept",
        ),
        Mutation(
            "the machine is measured once per subprocess, so the calibration becomes the load",
            '    if _CALIBRATION["at"] is None or t - _CALIBRATION["at"] >= CALIBRATION_REFRESH:',
            "    if True:",
            "measured once per refresh window",
        ),
        Mutation(
            "a calibration that cannot finish reads as idle",
            "            return CALIBRATION_IDLE * (HOOK_BUDGET_CAP / HOOK_BUDGET_FLOOR)",
            "            return CALIBRATION_IDLE",
            "a calibration that cannot finish reads as the heaviest load",
        ),
        Mutation(
            "the calibration takes one sample, so one stall sets the budget for a whole refresh window",
            "    runs = sorted(sample() for _ in range(CALIBRATION_SAMPLES))\n    return runs[len(runs) // 2]",
            "    return sample()",
            "one outlier among calm samples does not set the budget",
        ),
        Mutation(
            "the median becomes the largest sample, so an outlier is not ignored",
            "    return runs[len(runs) // 2]",
            "    return runs[-1]",
            "one outlier among calm samples does not set the budget",
        ),
        Mutation(
            "the calibration's own commands lose their timeout, so a hung calibration is the hang it guards against",
            "stderr=subprocess.DEVNULL, timeout=CALIBRATION_TIMEOUT,",
            "stderr=subprocess.DEVNULL,",
            "the calibration is itself bounded",
        ),
        Mutation(
            "a subprocess's bound bypasses hook_limit and is a bare number again",
            "limit = float(override) if override else hook_limit(requested, machine_slowdown())",
            "limit = float(override) if override else max(float(requested or 0), 180.0)",
            "every subprocess's bound goes through hook_limit",
        ),
    ),
)
