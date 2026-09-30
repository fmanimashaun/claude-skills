"""Mutation guard: measure_subagent_context. Declared here, run by scripts/mutation_check.py (#866).

#1505. The script backs the subagent-context figure in `plugins/rails-flow/reference/model-tiers.md`, so
a break that under-counts (the last request instead of the peak, input without cache) would shrink the
number the advisor policy is argued from, and still print a plausible table.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="measure_subagent_context",
    subject="scripts/measure_subagent_context.py",
    selftest="scripts/measure_subagent_context.py",
    # shipped_agents() reads the real agent files to name what we ship.
    needs=("plugins/",),
    mutations=(
        Mutation(
            "the last request's context is taken instead of the peak",
            '            peak = max(peak, sum(int(usage.get(k) or 0) for k in',
            '            peak = (sum(int(usage.get(k) or 0) for k in',
            'peak context summed per request and maximised per run',
        ),
        Mutation(
            'cache tokens are left out of the context',
            '                                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))',
            '                                 ("input_tokens",)))',
            'peak context summed per request and maximised per run',
        ),
        Mutation(
            'a run with no usage counts as a zero measurement',
            '        if transcript.is_file() and (peak := peak_context(transcript)):',
            '        if transcript.is_file() and ((peak := peak_context(transcript)) or True):',
            'a run with no usage is not a measurement',
        ),
    ),
)
