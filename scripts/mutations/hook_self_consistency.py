"""Mutation guard: hook_self_consistency. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #825. `${CLAUDE_PLUGIN_ROOT}` bare under `set -u`.
GUARD = Guard(
    name='hook_self_consistency',
    subject='plugins/rails-flow/hooks/scripts/self-consistency.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            'the expansion loses its default and aborts the shell when the variable is unset',
            'script="${CLAUDE_PLUGIN_ROOT:-}/scripts/self_consistency.py"',
            'script="${CLAUDE_PLUGIN_ROOT}/scripts/self_consistency.py"',
            'with CLAUDE_PLUGIN_ROOT unset the hook exits 0',
        ),
    ),
)
