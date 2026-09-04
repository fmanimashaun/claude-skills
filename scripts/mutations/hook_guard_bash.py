"""Mutation guard: hook_guard_bash. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #826. `-A` and `.` were anchored to the first argument of `git add`.
GUARD = Guard(
    name='hook_guard_bash',
    subject='plugins/rails-flow/hooks/scripts/guard-bash.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # the harness drives release-gate.sh too (#906)
    mutations=(
        Mutation(
            "the `git add` pattern goes back to first-argument anchoring",
            "if hit '^git[[:space:]]+add([[:space:]]+-[a-zA-Z]+)*[[:space:]]+(-[a-zA-Z]*A[a-zA-Z]*\\b|--all\\b|\\./?($|[[:space:]])|:/($|[[:space:]]))'; then",
            "if hit '^git[[:space:]]+add[[:space:]]+(-A\\b|--all\\b|\\.($|[[:space:]]))'; then",
            "`git add -v -A` is blocked",
        ),
        # #906. The normaliser is what separates "mentions the rule" from "stages everything".
        Mutation(
            "the normaliser is bypassed and the raw text is matched, so a prefixed `FOO=1 git add -A` fails OPEN",
            '  seg="$(printf \'%s\' "$cmd" | normalize_segments)"',
            '  seg="$cmd"',
            "`FOO=1 git add -A` is blocked",
        ),
        Mutation(
            "the missing-lib fallback matches nothing instead of the raw text, so a lost file makes the guard fail OPEN",
            'else\n  seg="$cmd"\nfi',
            'else\n  seg=""\nfi',
            "falls back to the raw text and still blocks",
        ),
    ),
)
