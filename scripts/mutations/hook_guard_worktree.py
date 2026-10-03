"""Mutation guard: hook_guard_worktree. Declared here, run by scripts/mutation_check.py (#1581).

The wrapper decides what is a worktree add and makes every way the judgement can break a refusal (#1581).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_worktree",
    subject="plugins/rails-flow/hooks/scripts/guard-worktree.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_worktree"),
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            'every command is taken for a worktree add, so a plain git status is judged and refused',
            '  if [[ $line =~ $re ]]; then hit=1; break; fi',
            '  if true; then hit=1; break; fi',
            'NOT a worktree add, left alone',
        ),
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
        Mutation(
            "the helper's refusal is swallowed and the command runs",
            '  2) printf \'%s\\n\' "$out" >&2; exit 2 ;;',
            '  2) exit 0 ;;',
            'a session that owns an UNMERGED worktree may not add another',
        ),
    ),
)
