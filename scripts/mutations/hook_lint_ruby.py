"""Mutation guard: hook_lint_ruby. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #824. Parsed RuboCop's summary for a string it never prints after correcting anything, and
# used PATH's bundle so under mise it silently never ran.
GUARD = Guard(
    name='hook_lint_ruby',
    subject='plugins/rails-flow/hooks/scripts/lint-ruby.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            'corrected offenses are counted as remaining again',
            'remaining="$(printf \'%s\\n\' "$out" | grep -E \'^[RCWEF]: *[0-9]+: *[0-9]+:\' | grep -vc \'\\[Corrected\\]\' || true)"',
            'remaining="$(printf \'%s\\n\' "$out" | grep -E \'^[RCWEF]: *[0-9]+: *[0-9]+:\' | grep -c \'\' || true)"',
            'a file whose only offense was CORRECTED passes',
        ),
        Mutation(
            'the runner ignores mise, so a pinned-Ruby project is never linted',
            '  if command -v mise >/dev/null 2>&1 && mise current ruby >/dev/null 2>&1; then bundle_cmd="mise exec -- bundle"',
            '  if command -v mise >/dev/null 2>&1 && mise current ruby >/dev/null 2>&1; then bundle_cmd="bundle"',
            'under mise with a pinned Ruby the hook RUNS',
        ),
    ),
)
