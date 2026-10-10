"""Mutation guard: hook_fixture_git_binding. Declared here, run by scripts/mutation_check.py (#1588, #1660 review R3).

The harness's `_fixture_git` falls back to a plain git for an init dir or a linked worktree. `cwd` alone does not bind
git: an inherited GIT_DIR wins, which was the #1588 incident. The fallback strips the repo-locating environment.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_fixture_git_binding",
    subject="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "fixture_git_binding"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
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
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "the fallback keeps an inherited GIT_DIR, so a fixture commit lands in the repo it names",
            '    kw["env"] = fixture_git.hermetic(kw.get("env"))      # drops an inherited GIT_DIR & co: cwd alone does not bind (#1660 R3)\n',
            '',
            "binding: the fallback (no .git here) under an inherited GIT_DIR does not commit into the other repo",
        ),
        Mutation(
            "the calibration workload keeps an inherited GIT_DIR, so its commit lands in the repo it names",
            "                                env=fixture_git.hermetic())     # no inherited GIT_DIR: cwd alone does not bind (#1660 R3)",
            "                                )",
            "binding: the calibration workload under an inherited GIT_DIR does not commit into the other repo",
        ),
    ),
)
