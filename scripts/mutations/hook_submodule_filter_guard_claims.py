"""Mutation guard: hook_submodule_filter_guard_claims. Declared here, run by scripts/mutation_check.py (#1919)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1919. Without --ignore-submodules=dirty, git recurses into a submodule and runs a clean filter named in ITS config.
    name="hook_submodule_filter_guard_claims",
    subject="plugins/rails-flow/hooks/scripts/guard-claims.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "submodule_filter"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/scripts/wip_commit.py",  # wip-commit.sh runs it (#1915 x #1920)
           'plugins/qa-flow/scripts/remote_evidence.py',  # #1581 merge: run by release-gate.sh
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),
    mutations=(
        Mutation(
            "guard-claims.sh reads status through a submodule and runs its own clean filter",
            'diff --name-only --ignore-submodules=dirty HEAD 2>/dev/null;',
            'diff --name-only HEAD 2>/dev/null;',
            "submodule filter: guard-claims.sh never runs a submodule's own clean filter",
        ),
    ),
)
