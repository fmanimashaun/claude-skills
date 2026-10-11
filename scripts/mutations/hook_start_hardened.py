"""Mutation guard: hook_start_hardened. How every rails-flow hook command starts (#1850). Run by scripts/mutation_check.py.

The other three plugins' commands are driven by the same group; one guard per hooks.json keeps a mutant to one subject file."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_start_hardened",
    subject="plugins/rails-flow/hooks/hooks.json",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "hostile_env"),
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/qa-flow/hooks/hooks.json", "plugins/pipeline/hooks/hooks.json", "plugins/design-flow/hooks/hooks.json",
           "plugins/rails-flow/scripts/assign_lanes.py", "plugins/rails-flow/scripts/brain_local_sync.py",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/pipeline/hooks/scripts", "plugins/design-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # The hostile-environment group RUNS every hook, and a hook whose script is missing exits quietly: unstaged, a mutant could survive because nothing ran (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py", "plugins/pipeline/scripts/status_board.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py", "plugins/qa-flow/scripts/remote_evidence.py",
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/wip_commit.py",
           "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            'one rails-flow hook command starts with a bare `bash`, which the harness resolves through PATH',
            '/bin/bash -p \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard-bash.sh\\"',
            'bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard-bash.sh\\"',
            'hostile environment: rails-flow/guard-bash.sh (PreToolUse) starts no program the repository chose',
        ),
        Mutation(
            'one rails-flow hook command starts `/bin/bash` without -p, so BASH_ENV is sourced',
            '/bin/bash -p \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/stop-gate.sh\\"',
            '/bin/bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/stop-gate.sh\\"',
            'hostile environment: rails-flow/stop-gate.sh (Stop) starts no program the repository chose',
        ),
    ),
)
