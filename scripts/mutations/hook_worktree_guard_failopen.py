"""Mutation guard: hook_worktree_guard_failopen. Declared here, run by scripts/mutation_check.py (#1581).

The judgement: every way the hook or git can misbehave must be a refusal. Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree_failopen`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_worktree_guard_failopen",
    subject="plugins/rails-flow/hooks/scripts/lib/worktree_guard.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree_failopen"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by release-gate.sh
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            'a command that moves into a repository from outside one is allowed',
            '        if MOVES.search(command):',
            '        if False:',
            '`cd <repo> && git worktree add` from a cwd outside any repository',
        ),
        Mutation(
            "a git that did not answer reads as 'not a repository', so the guard goes dormant",
            '    if inside == UNAVAILABLE:',
            '    if False:',
            'with git missing a worktree add cannot be judged',
        ),
        Mutation(
            "a git worktree list that fails reads as 'no worktrees'",
            '    if existing is None:',
            '    if False:',
            'could not list the worktrees',
            narrow=False,
        ),
        Mutation(
            'git is given a fixed long timeout instead of what is left of the budget',
            'timeout=min(5, remaining))',
            'timeout=60)',
            'a slow git is cut off within the budget',
        ),
        Mutation(
            "a record that cannot be located is read as 'no lanes'",
            '        if rp is None:\n            return deny(',
            '        if False:\n            return deny(',
            'could not locate the coordination record',
            narrow=False,
        ),
    ),
)
