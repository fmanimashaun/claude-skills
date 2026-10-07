"""Mutation guard: hook_stop_where. Declared here, run by scripts/mutation_check.py (#1639, #1643 R2).

The wrapper and its registration: an advisory Stop hook that does not exit 0, or is not registered, is a hook that either
stops turns or never runs. The lib's own judgement is guarded by hook_where_stopped.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_stop_where",
    subject="plugins/rails-flow/hooks/scripts/stop-where.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "where_stopped"),
    needs=(
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "the advisory hook exits non-zero, so a failure inside it can stop the turn",
            'python3 "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop 2>/dev/null\nexit 0',
            'python3 "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop 2>/dev/null\nexit 3',
            "clean and pushed, the Stop hook exits 0 and says nothing",
        ),
        Mutation(
            "the hook never calls the lib, so no facts file is written",
            'python3 "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop 2>/dev/null',
            'true',
            "the facts file is written under <git-common-dir>/handoff",
        ),
    ),
)
