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
        Mutation('the line is written even when the plugin has no shim', '[ -x "${CLAUDE_PLUGIN_ROOT}/git-shim/git" ]; then\n', '[ -n "${CLAUDE_PLUGIN_ROOT}/git-shim/git" ]; then\n', 'a plugin with no shim'),
        Mutation('the path is not quoted, so a path with a space breaks', 'printf \'export PATH=%q:\' "${CLAUDE_PLUGIN_ROOT}', 'printf \'export PATH=%s:\' "${CLAUDE_PLUGIN_ROOT}', 'puts the shim first'),
        # #2110: exactly ONE shim on PATH, the running version's: the line strips every rails-flow git-shim entry, and an older version's line is dropped from the env file.
        Mutation('the line no longer strips the older shim directories from PATH', '''awk '$0 !~ "rails-flow(/[^/]+)?/git-shim/?$"' ''', 'cat ', 'leaves exactly one rails-flow git-shim on PATH'),
        Mutation('an older version\'s line is never dropped from the env file', '  if [ -n "$_shim_stale" ]; then', '  if false; then', "an env file carrying older versions' lines is rewritten"),
        Mutation('a failed strip empties PATH', '[ -n "$_p" ] || _p="$PATH"; ', '', 'when the strip cannot run or leaves nothing'),
        Mutation('the rewrite drops other hooks\' lines too', '''    _shim_keep="$(grep -vE -- "$_shim_old" "$CLAUDE_ENV_FILE" 2>/dev/null)"''', '    _shim_keep=""', "an env file carrying older versions' lines is rewritten"),
        Mutation('the rewrite truncates the env file in place instead of moving a temp file over it', '''printf '%s\\n' "$_shim_line"; } > "$_shim_tmp" 2>/dev/null''', '''printf '%s\\n' "$_shim_line"; } > "$CLAUDE_ENV_FILE" 2>/dev/null''', 'the env-file rewrite is atomic'),
        # #1982: the session's project toplevel, for the shim's fixture exemption.
        Mutation('the project toplevel is never recorded, so the exemption can never apply', '  if [ -n "$_top" ]; then', '  if false; then', "records the session's project toplevel"),
        Mutation('the toplevel line is written on every start', 'grep -qxF -- "$_top_line" "$CLAUDE_ENV_FILE" 2>/dev/null ||', 'false ||', "records the session's project toplevel"),
        Mutation('a subdirectory is recorded instead of the toplevel', '_top="$(git rev-parse --show-toplevel 2>/dev/null)"', '_top="$(pwd)"', "records the session's project toplevel"),
        Mutation('the session marker file is never written, so the shim cannot tell the project from a fixture by what is on disk',
                 '    [ -n "$_gcd" ] && [ -d "$_gcd" ] && : > "$_gcd/claude-session-project" 2>/dev/null || true', '    true', "records the session's project toplevel"),
        Mutation('a toplevel is recorded outside a repository', '  if [ -n "$_top" ]; then', '  if true; then', "records the session's project toplevel"),
    ),
)
