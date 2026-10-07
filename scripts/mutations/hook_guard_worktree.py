"""Mutation guard: hook_guard_worktree. Declared here, run by scripts/mutation_check.py (#1581).

The wrapper: the rules (one issue at a time; no duplicate for a branch or an issue). Split out of one guard that re-ran ALL four worktree fixture groups per mutant: this one runs only `guard_worktree`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_worktree",
    subject="plugins/rails-flow/hooks/scripts/guard-worktree.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree"),
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            'every command is taken for a worktree add, so a plain git status is judged and refused',
            '  if [[ $line =~ $re ]]; then hit=1; break; fi',
            '  if true; then hit=1; break; fi',
            'NOT a worktree add, left alone',
        ),
        Mutation(
            "the helper's refusal is swallowed and the command runs",
            '  2) printf \'%s\\n\' "$out" >&2; exit 2 ;;',
            '  2) exit 0 ;;',
            'a session that owns an UNMERGED worktree may not add another',
        ),
    ),
)
