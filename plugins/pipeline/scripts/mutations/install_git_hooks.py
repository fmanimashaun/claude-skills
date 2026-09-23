"""Mutation guard: install-git-hooks. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The installer's defect was that it reported success and installed a hook git never runs. Each
# mutation below restores one way of doing that again, and each is caught by a REAL merge rather
# than by looking for the file -- "the file exists where we expected" is the assertion that passed
# over the original defect for days.
GUARD = Guard(
    name="install_git_hooks",
    subject="hooks/scripts/install-git-hooks.sh",
    selftest="scripts/install_git_hooks_selftest.py",
    mutations=(
        Mutation(
            "the hooks directory is derived from --git-dir again, ignoring core.hooksPath",
            'hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null)"',
            'hooks_dir="$(git rev-parse --git-dir 2>/dev/null)/hooks"',
            "core.hooksPath: a real merge fires the nudge",
        ),
        Mutation(
            "a tracked, team-owned hook is edited instead of refused",
            'if [ -f "$hook" ] && git ls-files --error-unmatch -- "$hook" >/dev/null 2>&1; then',
            "if false; then",
            "a tracked hook is never modified",
        ),
        Mutation(
            "a hook installed inside the working tree is left visible to `git add`",
            """grep -qxF "/${abs#"$top"/}" "$excl" 2>/dev/null || printf '/%s\\n' "${abs#"$top"/}" >> "$excl\"""",
            ":",
            "the installed hook stays out of git status",
        ),
    ),
)
