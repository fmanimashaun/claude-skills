"""Mutation guard: lint_markdown_shell. Declared here, run by scripts/mutation_check.py (#1231).

The shell linter had no selftest at all until #1231, so none of its pattern rules had ever been seen
to fail. Each mutation disables one rule; each must be caught by that rule's own fixture.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="lint_markdown_shell",
    subject="scripts/lint_markdown_shell.py",
    selftest="scripts/lint_markdown_shell.py",
    mutations=(
        Mutation(
            "a swallowed verdict is no longer reported",
            "            if SWALLOWED.search(line):",
            "            if False:",
            "swallowed-verdict: bad line",
        ),
        Mutation(
            "an unquoted test operand is no longer reported",
            "            if UNQUOTED_TEST.search(line):",
            "            if False:",
            "unquoted-test: bad line",
        ),
        Mutation(
            "git grep -E with a word boundary is no longer reported",
            "            if GIT_GREP_ERE_BOUNDARY.search(line):",
            "            if False:",
            "git-grep-ere-boundary: bad line",
        ),
        Mutation(
            # The segment bound: without it, a `\\b` in a LATER command of a pipeline would fire.
            "the rule reads across a pipe into the next command",
            "(?=[^\\n|;&]*\\\\b)",
            "(?=[^\\n]*\\\\b)",
            "git-grep-ere-boundary fired across a pipe",
        ),
    ),
)
