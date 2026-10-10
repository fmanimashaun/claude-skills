"""Mutation guard: hook_test_preflight. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1561, #1566. The wrapper is three lines and each one is load-bearing; it is ADVISORY (harness-doctrine section 5), so it must fail open and
# exit 0 whatever the script does. The same guards a sibling hook dropped (`command -v python3`, `[ -f ]`) are absent here for the same reason:
# no fixture could tell them from their absence.
GUARD = Guard(
    name="hook_test_preflight",
    subject="plugins/rails-flow/hooks/scripts/test-preflight.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the fixture groups that drive this subject (#1497): the whole harness per mutant was ~70% of the budget.
    selftest_args=("--only", "test_preflight"),
    # check_hook_gates drives every hook in both plugins from its own location, so the whole set is
    # staged, plus each script a hook shells out to -- one missing and every mutation reads as caught.
    # test-preflight.sh runs test_preflight.py (#1561): unstaged, its fixtures fail and every mutation reads as caught.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",  # release-gate.sh runs it (#1410)
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            # PROVES THE POSITIVE FIXTURE IS LIVE. Point at a script that is not there and the hook is silent -- which only a fixture
            # expecting it to SPEAK can notice.
            "the hook calls a script that does not exist, and is silent everywhere",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py"',
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight_missing.py"',
            "a Postgres outage before an rspec run is named, and the hook still exits 0",
        ),
        Mutation(
            "the expansion loses its default and aborts the shell when the variable is unset",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py"',
            '"${CLAUDE_PLUGIN_ROOT}/scripts/test_preflight.py"',
            "with CLAUDE_PLUGIN_ROOT unset it exits 0 silently",
        ),
        Mutation(
            # Without the redirect, a missing python3 prints `command not found` into the transcript.
            "a missing python3 leaks `command not found` into the conversation",
            "test_preflight.py\" 2>/dev/null\n",
            "test_preflight.py\"\n",
            "with no python3 on PATH it exits 0 and says nothing",
        ),
        Mutation(
            # AN ADVISORY MUST NEVER BLOCK. Exit 2 on PreToolUse blocks the command it was only meant to comment on.
            "the advisory exits non-zero and becomes a gate nobody asked for",
            "\nexit 0\n",
            "\nexit 2\n",
            "Postgres up, everything fine: silent and exits 0",
        ),
    ),
)
