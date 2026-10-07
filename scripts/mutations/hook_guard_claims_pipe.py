"""Mutation guard: hook_guard_claims_pipe. Declared here, run by scripts/mutation_check.py (#1579).

guard-claims.sh is a fail-closed gate, and under `pipefail` a `printf | grep -q` reads SIGPIPE as "no match", so a long
command with the `gh pr create` first was allowed unchecked. Its own guard, so the mutant runs only this fixture group.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_claims_pipe",
    subject="plugins/rails-flow/hooks/scripts/guard-claims.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_claims_pipe"),
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
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "pipefail is back on inside has(), so SIGPIPE from a long tail reads as no match and the guard checks nothing",
            """has() { ( set +o pipefail; printf '%s' "$1" | grep -qE "$2" ); }""",
            """has() { ( printf '%s' "$1" | grep -qE "$2" ); }""",
            "an unchecked claim is blocked when a 10,000-line tail FOLLOWS the gh pr create",
        ),
    ),
)
