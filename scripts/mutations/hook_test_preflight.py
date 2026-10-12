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
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs both (#1581: the harness drives it)
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
            # Without the redirect, python's own "can't open file" (the script is missing, or the plugin root is unset) prints into the transcript. A missing python3 no longer reaches
            # the redirect at all: the hook does not call an interpreter it did not find.
            "a script python cannot open leaks its error into the conversation",
            "test_preflight.py\" 2>/dev/null\n",
            "test_preflight.py\"\n",
            "with CLAUDE_PLUGIN_ROOT unset it exits 0 silently",
        ),
        # THE INTERPRETER LOOKUP IS THE LIB'S (#1850, #1893). This hook used to carry its own copy of it (skip the repository, the outermost Gemfile or .git, a link into the
        # repository, `set -f`, absolute entries only), and once `lib/trusted-env.sh` rebuilds PATH first those directory rules could never fire: four of their mutants
        # survived because they were EQUIVALENT, not because a fixture was missing. The lookup is now `rf_trusted_python`, whose rules are proven by the `hook_trusted_env`
        # guard and the hostile-environment group; the fixtures here still run the real hook against each shape. What the hook adds on top is `-I`.
        Mutation(
            "python3 is not run isolated, so the working directory and the script's directory are on its import path",
            '"$RF_PYTHON" -I "${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py"',
            '"$RF_PYTHON" "${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py"',
            "the interpreter is run ISOLATED",
        ),
        Mutation(
            "the interpreter is the shell's own lookup, not the lib's, so a python3 the repository ships can be run",
            "rf_trusted_python\n",
            "RF_PYTHON=\"$(type -P python3)\"\n",
            "a python3 that is a symlink into the repository is NOT run",
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
