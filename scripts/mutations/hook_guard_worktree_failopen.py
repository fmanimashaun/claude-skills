"""Mutation guard: hook_guard_worktree_failopen. Declared here, run by scripts/mutation_check.py (#1581).

The wrapper: every way the hook or git can misbehave must be a refusal. Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree_failopen`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_worktree_failopen",
    subject="plugins/rails-flow/hooks/scripts/guard-worktree.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree_failopen"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by session-start.sh / release-gate.sh
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            'the degraded match stays anchored, so an unreadable payload is waved through',
            '[ "$degraded" = 1 ] && re=\'git[[:space:]]+worktree[[:space:]]+add([[:space:]]|$)\'',
            'true',
            'with no python3 a worktree add is refused',
        ),
        Mutation(
            'a helper that crashes lets the command run',
            '  *) deny "the guard\'s helper failed (exit $rc)',
            '  *) exit 0 ;; # (exit $rc)',
            'a crashing helper fails CLOSED',
        ),
        Mutation(
            'a missing python3 lets the command run',
            '  || deny "python3 is not available,',
            '  || exit 0 #',
            'with no python3 a worktree add is refused',
        ),
    ),
)
