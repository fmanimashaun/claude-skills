"""Mutation guard: git_shim_real_git. Declared here, run by scripts/mutation_check.py (#2091)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #2091. The selftest's REAL_GIT came from the ambient PATH, where the SessionStart hook puts the INSTALLED shim first, so fixture setup ran
# through an older shim and 14 checks failed for the wrong reason. `real_git_on` skips a `git-shim` directory; the subject is the selftest itself.
GUARD = Guard(
    name="git_shim_real_git",
    subject="scripts/git_shim_selftest.py",
    selftest="scripts/git_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/git", "hooks/scripts/session-start.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation(
            "a git-shim directory on PATH is no longer skipped, so REAL_GIT can be the installed shim again",
            '        if not q or Path(q).name == "git-shim":',
            "        if not q:",
            "REAL_GIT skips a git-shim directory",
        ),
        Mutation(
            "with no real git on PATH the resolver does not fall back to /usr/bin/git",
            '    return "/usr/bin/git"\n\n\nREAL_GIT',
            '    return "git"\n\n\nREAL_GIT',
            "REAL_GIT skips a git-shim directory",
        ),
    ),
)
