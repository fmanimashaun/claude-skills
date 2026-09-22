"""Mutation guard: hook_guard_lane. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #823. A fail-closed guard with a one-segment hole: `..` was normalised by nothing.
GUARD = Guard(
    name='hook_guard_lane',
    subject='plugins/rails-flow/hooks/scripts/guard-lane.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            'the `..` refusal is removed, so a lane escape passes the prefix match again',
            '  */../*)\n    {\n      echo "BLOCKED by rails-flow lane guard: a path containing \'..\' is refused while a lane is"',
            '  */.../*)\n    {\n      echo "BLOCKED by rails-flow lane guard: a path containing \'..\' is refused while a lane is"',
            'a `..` escape is blocked',
        ),
    ),
)
