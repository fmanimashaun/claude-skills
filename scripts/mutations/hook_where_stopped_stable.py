"""Mutation guard: hook_where_stopped_stable. Declared here, run by scripts/mutation_check.py (#1886).

The where-stopped pointer names a file, never the time it was written (the file holds that). The budget selftest drives the real hook.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_where_stopped_stable",
    subject="plugins/rails-flow/hooks/scripts/lib/where_stopped.py",
    selftest="scripts/check_hook_output_budget.py",
    selftest_args=("--selftest",),   # the selftest is a different file from the subject, so the flag is passed here
    needs=("plugins/rails-flow/scripts/fixture_git.py", ".claude/settings.json", ".claude/hooks/scripts/maintainer-status.sh",
           "plugins/design-flow/hooks/hooks.json", "plugins/pipeline/hooks/hooks.json", "plugins/pipeline/hooks/scripts/pipeline-status.sh",
           "plugins/qa-flow/hooks/hooks.json", "plugins/qa-flow/hooks/scripts/qa-status.sh", "plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/rails-flow/scripts/fixture_git.py"),
    mutations=(
        Mutation(
            "the pointer prints the write time again, so the line differs at every turn",
            '        line = f"- where this worktree stopped (last turn): {path}"',
            '        line = f"- where this worktree stopped (last turn, {rec.get(\'written\', \'?\')}): {path}"',
            "every SessionStart hook's output, against the fixture, holds no ticking value",
        ),
    ),
)
