"""Mutation guard: hook_session_end. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1582 slice C. A three-line advisory wrapper; each line is load-bearing, as in hook_ci_verdict_hint.
GUARD = Guard(
    name="hook_session_end",
    subject="plugins/rails-flow/hooks/scripts/session-end.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "session_end"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/qa-flow/scripts/remote_evidence.py",
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py",
           "plugins/rails-flow/scripts/session_reaper.py",
           "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            "the hook calls a script that does not exist, so nothing is ever reaped",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/session_reaper.py"',
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/session_reaper_missing.py"',
            "this session's stopped orphan is reaped and the hook exits 0",
        ),
        Mutation(
            "the expansion loses its default and aborts the shell when the variable is unset",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/session_reaper.py"',
            '"${CLAUDE_PLUGIN_ROOT}/scripts/session_reaper.py"',
            "CLAUDE_PLUGIN_ROOT unset exits 0 silently",
        ),
        Mutation(
            "the advisory exits non-zero and becomes a gate nobody asked for",
            "\nexit 0\n",
            "\nexit 2\n",
            "this session's stopped orphan is reaped and the hook exits 0",
        ),
    ),
)
