"""Mutation guard: git_shim_hook. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1790. The SessionStart export that puts the shim first. Each mutation breaks ONE rule, and the selftest must notice it from the OUTSIDE: a real git command on a real repository, then a look
# at what moved. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='git_shim_hook',
    subject='hooks/scripts/session-start.sh',
    selftest="scripts/git_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/git", "hooks/scripts/session-start.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation('the PATH line is added on every start', 'grep -qxF -- "$_shim_line" "$CLAUDE_ENV_FILE" 2>/dev/null ||', 'false ||', 'does not repeat the line'),
        Mutation('the line is written even when the plugin has no shim', '[ -x "${CLAUDE_PLUGIN_ROOT}/git-shim/git" ]; then\n  _shim_line', '[ -n "${CLAUDE_PLUGIN_ROOT}/git-shim/git" ]; then\n  _shim_line', 'a plugin with no shim'),
        Mutation('the path is not quoted, so a path with a space breaks', 'printf \'export PATH=%q:"$PATH"\'', 'printf \'export PATH=%s:"$PATH"\'', 'puts the shim first'),
        # #1982: the session's project toplevel, for the shim's fixture exemption.
        Mutation('the project toplevel is never recorded, so the exemption can never apply', '  if [ -n "$_top" ]; then', '  if false; then', "records the session's project toplevel"),
        Mutation('the toplevel line is written on every start', 'grep -qxF -- "$_top_line" "$CLAUDE_ENV_FILE" 2>/dev/null ||', 'false ||', "records the session's project toplevel"),
        Mutation('a subdirectory is recorded instead of the toplevel', '_top="$(git rev-parse --show-toplevel 2>/dev/null)"', '_top="$(pwd)"', "records the session's project toplevel"),
        Mutation('a toplevel is recorded outside a repository', '  if [ -n "$_top" ]; then', '  if true; then', "records the session's project toplevel"),
    ),
)
