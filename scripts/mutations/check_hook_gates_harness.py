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
    selftest_args=("--only", "timeout"),
    # The same staging as hook_guard_bash: the suite drives every plugin's hooks. A literal, because
    # lint_self_consistency's harness-dependency-undeclared rule reads it statically -- and that rule is
    # what keeps this copy honest when a hook gains a script (it caught exactly that on #1477).
    needs=(
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
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            "an unexpected timeout is not recorded, so a setup step that times out passes silently",
            "            if not _EXPECTING_TIMEOUT:\n                check(note, False)",
            "            if False:\n                check(note, False)",
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
            '    for name in (groups or list(table)):',
            '    for name in list(table):',
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
            # review of PR #1506
            "a bare run executes no group, so the doctor's hook gates pass on nothing",
            '    for name in (groups or list(table)):',
            '    for name in (groups or []):',
            'a bare run (no --only) runs every group',
        ),
        Mutation(
            # review of PR #1506
            'main() stops refusing a bad --only',
            '                  f"known: {\', \'.join(GROUPS)}", file=sys.stderr)\n            return 2',
            '                  f"known: {\', \'.join(GROUPS)}", file=sys.stderr)',
            'main() exits 2 for --only nope',
        ),
    ),
)
