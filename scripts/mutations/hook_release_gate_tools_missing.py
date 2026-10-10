"""Mutation guard: hook_release_gate_tools_missing. Declared here, run by scripts/mutation_check.py (#1664).

Each mutation lets a promotion through when sed, tr or awk are missing: the up-front missing-tools rule dropped or weakened.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_tools_missing",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the `tools_missing` group drives this subject here, and each mutant needs only the fixture its `expects` names, so
    # `--match` narrows it to that one after a control run of the unmutated code that must pass.
    selftest_args=("--only", "tools_missing"),
    narrow_with="--match",
    # The same staging as hook_command_cwd: the harness runs every hook from the whole directory.
    needs=(
           'plugins/rails-flow/scripts/fixture_git.py',  # check_hook_gates imports it (#1588)
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
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
            "the up-front missing-tools rule is dropped, so a promotion is judged with a normaliser that cannot run",
            'if [ -n "$_missing" ]; then',
            'if false; then',
            "tools-missing (no sed, tr or awk): release-gate.sh still refuses `git push origin main`",
        ),
        Mutation(
            "a missing tool is not on the list the rule looks for (sed, awk and tr are dropped from it)",
            'for _t in python3 git sed awk tr grep head; do',
            'for _t in python3 git grep head; do',
            "tools-missing (no sed, tr or awk): release-gate.sh still refuses `gh pr merge 1 --merge`",
        ),
    ),
)
