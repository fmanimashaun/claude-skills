"""Mutation guard: hook_session_start_resume. Declared here, run by scripts/mutation_check.py (#1581).

The RESUME pointer (the worktree a session was working in), not #1585's coordinator pointer, which has its own guard, `hook_session_start_pointer`. Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree_pointer`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_session_start_resume",
    subject="plugins/rails-flow/hooks/scripts/session-start.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree_pointer"),
    # Each mutant runs only the fixture its `expects` names (#1599); the ones marked `narrow=False` depend on state an
    # earlier fixture builds, cannot run alone, and run the whole sub-group (#1581, surveyed one by one).
    narrow_with="--match",
    needs=(
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by session-start.sh / release-gate.sh
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            'the resume pointer is never asked for',
            '  python3 "${BASH_SOURCE[0]%/*}/lib/worktree_guard.py" resume --session-id "$_sid" 2>/dev/null',
            '  true',
            'the session that holds a lane is told where to resume',
            narrow=False,
        ),
        Mutation(
            'the session id is dropped, so no session matches a lane',
            '--session-id "$_sid"',
            '--session-id ""',
            'the session that holds a lane is told where to resume',
            narrow=False,
        ),
    ),
)
