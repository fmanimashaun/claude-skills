"""Mutation guard: hook_ci_verdict_hint. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1173. The wrapper is three lines and each one is load-bearing; the guards a sibling hook carries
# (`command -v python3`, `[ -f ]`) were removed because no fixture could tell them from their absence.
GUARD = Guard(
    name="hook_ci_verdict_hint",
    subject="plugins/rails-flow/hooks/scripts/ci-verdict-hint.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # check_hook_gates drives every hook in both plugins from its own location, so the whole set is
    # staged, plus each script a hook shells out to -- one missing and every mutation reads as caught.
    needs=("plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py"),
    mutations=(
        Mutation(
            # PROVES THE POSITIVE FIXTURE IS LIVE. Point at a script that is not there and the hook is
            # silent -- which only a fixture expecting it to SPEAK can notice.
            "the hook calls a script that does not exist, and is silent everywhere",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/ci_verdict_hint.py"',
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/ci_verdict_hint_missing.py"',
            "a failing `gh pr checks` (PostToolUseFailure) emits additionalContext",
        ),
        Mutation(
            "the expansion loses its default and aborts the shell when the variable is unset",
            '"${CLAUDE_PLUGIN_ROOT:-}/scripts/ci_verdict_hint.py"',
            '"${CLAUDE_PLUGIN_ROOT}/scripts/ci_verdict_hint.py"',
            "with CLAUDE_PLUGIN_ROOT unset it exits 0 silently",
        ),
        Mutation(
            # Without the redirect, a missing python3 prints `command not found` into the transcript.
            "a missing python3 leaks `command not found` into the conversation",
            "ci_verdict_hint.py\" 2>/dev/null\n",
            "ci_verdict_hint.py\"\n",
            "with no python3 on PATH it exits 0 and says nothing",
        ),
        Mutation(
            # AN ADVISORY MUST NEVER BLOCK. Exit 2 on PostToolUse reaches the model as an error.
            "the advisory exits non-zero and becomes a gate nobody asked for",
            "\nexit 0\n",
            "\nexit 2\n",
            "an all-passing `gh pr checks` is silent and exits 0",
        ),
    ),
)
