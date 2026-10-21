"""Mutation guard: hook_wip_commit. Declared here, run by scripts/mutation_check.py (#1564).

The wrapper and its registration: an advisory Stop hook that does not exit 0, is not registered, is registered on PreToolUse, or runs a
python3 before the trusted-env lib has rebuilt PATH. The commit's own judgement is guarded by wip_commit.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_wip_commit",
    subject="plugins/rails-flow/hooks/scripts/wip-commit.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "wip_commit"),
    needs=("plugins/rails-flow/scripts/advisory_scope.py", "plugins/rails-flow/scripts/security_scope.py", "plugins/rails-flow/scripts/check_threat_model.py", "plugins/rails-flow/scripts/detect_stack.py",  # stop-gate.sh runs advisory_scope.py (#2262)
           "plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/wip_commit.py', 'plugins/rails-flow/scripts/check_memory_index.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "the advisory hook exits non-zero, so a failure inside it can stop the turn",
            'stop >/dev/null 2>&1\nexit 0',
            'stop >/dev/null 2>&1\nexit 3',
            "the real wrapper, exit 0, silent",
        ),
        Mutation(
            "the hook never calls the script, so nothing is ever committed",
            'python3 -I "${BASH_SOURCE[0]%/*}/../../scripts/wip_commit.py" 2>/dev/null',
            'true',
            "the real wrapper, exit 0, silent",
        ),
        Mutation(
            "the where-stopped record is not rewritten after the commit, so the next start calls it stale",
            '| python3 -I "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop >/dev/null 2>&1',
            '| true',
            "the where-stopped record is rewritten after the commit",
        ),
        Mutation(
            "the lib is not sourced, so a repository's python3 on a relative PATH, its PYTHONPATH and its GIT_CONFIG_* run",
            '. "${BASH_SOURCE[0]%/*}/lib/trusted-env.sh" 2>/dev/null',
            ':',
            "a repository-chosen python3 (relative PATH)",
        ),
    ),
)
