"""Mutation guard: git_shim_selftest_skip. Declared here, run by scripts/mutation_check.py (#1971)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1971 (9f's review of #1972). Where zsh is absent, `zsh_row` must SAY its row did not run: the line is the only thing that tells a reader the
# count is one short, and without a guard dropping it leaves every guard green. The subject is the selftest itself, so the harness passes it
# `--selftest`, which the selftest ignores; `narrow_with` runs the mutant on the zsh-absent case alone.
GUARD = Guard(
    name="git_shim_selftest_skip",
    subject="scripts/git_shim_selftest.py",
    selftest="scripts/git_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/git", "hooks/scripts/session-start.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation(
            "the zsh row is dropped silently again where zsh is absent",
            '        print(f"  skip: zsh is not on PATH, so \\"{label}\\" did NOT run under zsh -- not a pass.", file=sys.stderr)',
            "        pass",
            "zsh absent: the zsh row says it did NOT run",
        ),
        Mutation(
            "the skipped zsh row counts a check of its own, so a skip reads as a pass in the tally",
            '        print(f"  skip: zsh is not on PATH, so \\"{label}\\" did NOT run under zsh -- not a pass.", file=sys.stderr)',
            '        print(f"  skip: zsh is not on PATH, so \\"{label}\\" did NOT run under zsh -- not a pass.", file=sys.stderr)\n        check(label, True)',
            "zsh absent: the zsh row says it did NOT run",
        ),
    ),
)
