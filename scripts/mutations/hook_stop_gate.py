"""Mutation guard: hook_stop_gate. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #822. The Stop gate handed a shell FUNCTION to the external `timeout` binary and read the
# resulting `not found` as a RED suite -- on every machine that HAS a timeout binary, which is
# every one except a stock Mac. The shell had no behavioural test; `bash -n` said it parsed.
GUARD = Guard(
    name='hook_stop_gate',
    subject='plugins/rails-flow/hooks/scripts/stop-gate.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            'the bundle runner goes back to being a function name that `timeout` cannot exec',
            '  if ! out="$(_rf_timeout 120 $bundle_cmd exec rspec $files --fail-fast --no-color 2>&1 | tail -15)"; then',
            '  if ! out="$(_rf_timeout 120 _rf_bundle_prefix exec rspec $files --fail-fast --no-color 2>&1 | tail -15)"; then',
            'a PASSING suite under a real `timeout` binary lets the stop proceed',
        ),
        Mutation(
            # Collapsing the positive signal makes every failure RED again, including the ones
            # where rspec never started -- the #724 misdiagnosis, back.
            'the RSpec summary line stops deciding RED, so an unrunnable suite is called red again',
            '      *" example, "*|*" examples, "*)',
            '      *)',
            'called an environment problem, not a red suite',
        ),
    ),
)
