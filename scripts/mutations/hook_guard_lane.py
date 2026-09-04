"""Mutation guard: hook_guard_lane. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #823. A fail-closed guard with a one-segment hole: `..` was normalised by nothing.
GUARD = Guard(
    name='hook_guard_lane',
    subject='plugins/rails-flow/hooks/scripts/guard-lane.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            'the `..` refusal is removed, so a lane escape passes the prefix match again',
            '  */../*)\n    {\n      echo "BLOCKED by rails-flow lane guard: a path containing \'..\' is refused while a lane is"',
            '  */.../*)\n    {\n      echo "BLOCKED by rails-flow lane guard: a path containing \'..\' is refused while a lane is"',
            'a `..` escape is blocked',
        ),
    ),
)
