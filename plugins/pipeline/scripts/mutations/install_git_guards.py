"""Mutation guard: install_git_guards. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1789. The installer. Each mutation breaks ONE rule or ONE fail-closed branch, and the selftest must notice it from the
# OUTSIDE: a real push or a real commit, then a look at what moved. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='install_git_guards',
    subject='scripts/install-git-guards.sh',
    selftest="scripts/git_guard_selftest.py",
    needs=("scripts/fixture_git.py", "git-hooks/pre-push", "git-hooks/pre-commit", "scripts/install-git-guards.sh"),
    narrow_with="--match",
    mutations=(
        Mutation(
            'the hooks directory is derived from --git-dir, ignoring core.hooksPath',
            'hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null)"',
            'hooks_dir="$(git rev-parse --git-dir 2>/dev/null)/hooks"',
            'with core.hooksPath on a committed directory the guards fire',
        ),
        Mutation(
            'a tracked hook is overwritten',
            '  if [ -e "$dest" ] && git ls-files --error-unmatch -- "$dest" >/dev/null 2>&1; then',
            '  if false; then',
            'a tracked copy of our own guard is refused too',
        ),
        Mutation(
            'a foreign hook is overwritten',
            '  if [ -e "$dest" ] && ! grep -qF "$marker" "$dest" 2>/dev/null; then',
            '  if false; then',
            'a foreign hook that is not tracked is refused',
        ),
        Mutation(
            'an installed guard is left visible to git add',
            '  grep -qxF "/${abs#"$top"/}" "$excl" 2>/dev/null || printf \'/%s\\n\' "${abs#"$top"/}" >> "$excl"',
            '  :',
            'stay out of git status',
        ),
        Mutation(
            'a refused guard stops the other one from being installed',
            '    status=1; continue\n  fi\n  if [ -e "$dest" ] && ! grep',
            '    status=1; break\n  fi\n  if [ -e "$dest" ] && ! grep',
            'a tracked hook of the same name is refused',
        ),
        Mutation(
            'a refused install exits 0',
            'exit "$status"',
            'exit 0',
            'a tracked hook of the same name is refused',
        ),
        Mutation(
            'an installed guard is not made executable',
            '  chmod +x "$dest" || { echo "cannot make $dest executable"; status=1; continue; }',
            '  :',
            'both guards are installed where git runs hooks and fire',
        ),
    ),
)
