"""Mutation guard: hook_session_start_stable. Declared here, run by scripts/mutation_check.py (#1886).

The hook's own text must not tick. scripts/check_hook_output_budget.py --selftest runs the REAL hook against a fixture whose review stamp is
old and scans what it prints for relative ages and clock times, so putting the age back turns that row red.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_session_start_stable",
    subject="plugins/rails-flow/hooks/scripts/session-start.sh",
    selftest="scripts/check_hook_output_budget.py",
    selftest_args=("--selftest",),   # the selftest is a different file from the subject, so the flag is passed here
    needs=("plugins/rails-flow/scripts/fixture_git.py", ".claude/settings.json", ".claude/hooks/scripts/maintainer-status.sh",
           "plugins/design-flow/hooks/hooks.json", "plugins/pipeline/hooks/hooks.json", "plugins/pipeline/hooks/scripts/pipeline-status.sh",
           "plugins/qa-flow/hooks/hooks.json", "plugins/qa-flow/hooks/scripts/qa-status.sh", "plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/rails-flow/scripts/fixture_git.py"),
    mutations=(
        Mutation(
            "the nudge states the age again, so its text changes every day",
            '        echo "- brain-review due since ${_due_date:-the cadence passed} (cadence ${_days}d) — run /rails-flow:brain-review"',
            '        echo "- brain-review due: last swept ${_age}d ago (cadence ${_days}d) — run /rails-flow:brain-review"',
            "every SessionStart hook's output, against the fixture, holds no ticking value",
        ),
        Mutation(
            "the nudge prints the time it was stamped, a clock value",
            '        echo "- brain-review due since ${_due_date:-the cadence passed} (cadence ${_days}d) — run /rails-flow:brain-review"',
            '        echo "- brain-review due since $(date -u -r "$_ts" +%FT%H:%M) (cadence ${_days}d) — run /rails-flow:brain-review"',
            "every SessionStart hook's output, against the fixture, holds no ticking value",
        ),
    ),
)
