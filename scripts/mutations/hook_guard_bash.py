"""Mutation guard: hook_guard_bash. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #826. `-A` and `.` were anchored to the first argument of `git add`.
GUARD = Guard(
    name='hook_guard_bash',
    subject='plugins/rails-flow/hooks/scripts/guard-bash.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts',),
    mutations=(
        Mutation(
            'the `git add` pattern goes back to first-argument anchoring',
            'if printf \'%s\' "$cmd" | grep -qE \'git\\s+add(\\s+-[a-zA-Z]+)*\\s+(-[a-zA-Z]*A[a-zA-Z]*\\b|--all\\b|\\./?($|\\s)|:/($|\\s))\'; then',
            'if printf \'%s\' "$cmd" | grep -qE \'git\\s+add\\s+(-A\\b|--all\\b|\\.($|\\s))\'; then',
            '`git add -v -A` is blocked',
        ),
    ),
)
