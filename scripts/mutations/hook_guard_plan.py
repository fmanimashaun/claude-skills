"""Mutation guard: hook_guard_plan (#2262, plan-advisor A-1 on #2267). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name='hook_guard_plan',
    subject='plugins/rails-flow/hooks/scripts/guard-plan.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    selftest_args=("--only", "guard_plan"),
    # The same staging the stop-gate guard needs: the harness, the hooks directory, and advisory_scope.py with its siblings.
    needs=("plugins/rails-flow/scripts/rf_tmp.py",   # rf_tmp (#2306)
           'plugins/rails-flow/scripts/fixture_git.py',
           'plugins/rails-flow/scripts/assign_lanes.py',
           'plugins/rails-flow/scripts/brain_local_sync.py',
           'plugins/rails-flow/scripts/check_memory_index.py',
           'plugins/rails-flow/hooks/hooks.json',
           'plugins/rails-flow/hooks/scripts',
           'plugins/qa-flow/hooks/scripts',
           'plugins/qa-flow/scripts',
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/advisory_scope.py',
           'plugins/rails-flow/scripts/security_scope.py',
           'plugins/rails-flow/scripts/check_threat_model.py',
           'plugins/rails-flow/scripts/detect_stack.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py',
           'plugins/rails-flow/scripts/test_preflight.py',
           'plugins/rails-flow/scripts/wip_commit.py',
           'plugins/rails-flow/scripts/session_reaper.py',
           'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            "a required advisory no longer blocks a build edit",
            'if [ $? -eq 1 ]; then',
            'if false; then',
            "a build edit while the plan owes a plan-advisor pass is blocked",
        ),
        Mutation(
            "writing under docs/ is blocked too, so the record cannot be written",
            '  docs/*|../*) exit 0 ;;',
            '  ../*) exit 0 ;;',
            "writing under docs/ (the plan and its record) stays allowed",
        ),
        Mutation(
            "every branch is judged, not only the flow's",
            '  *) exit 0 ;;\nesac\nslug=',
            '  *) ;;\nesac\nslug=',
            "a branch outside the flow is not judged",
        ),
    ),
)
