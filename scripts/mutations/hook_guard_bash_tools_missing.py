"""Mutation guard: hook_guard_bash_tools_missing. Declared here, run by scripts/mutation_check.py (#1664).

Each mutation lets a refusal become an allow when sed, tr and awk are missing: a failed normaliser read as an empty, clean command.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_bash_tools_missing",
    subject="plugins/rails-flow/hooks/scripts/guard-bash.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the `tools_missing` group drives this subject here, and each mutant needs only the fixture its `expects` names, so
    # `--match` narrows it to that one after a control run of the unmutated code that must pass.
    selftest_args=("--only", "tools_missing"),
    narrow_with="--match",
    # The same staging as hook_command_cwd: the harness runs every hook from the whole directory.
    needs=(
           'plugins/rails-flow/scripts/fixture_git.py',  # check_hook_gates imports it (#1588)
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            "a failed normaliser reads as an empty clean command, so nothing matches and the command is allowed",
            '|| { seg="$cmd"; degraded=1; }',
            '|| { seg=""; }',
            "tools-missing (no sed, tr or awk): guard-bash.sh still refuses `git add -A`",
        ),
        Mutation(
            "degraded mode stays anchored, so a compound command's second segment is never seen",
            '  [ "$degraded" = 1 ] && re="${re#^}"',
            '  :',
            "tools-missing (no sed, tr or awk): guard-bash.sh still refuses `cd /tmp && git add -A`",
        ),
    ),
)
