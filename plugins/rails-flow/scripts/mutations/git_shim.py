"""Mutation guard: git_shim. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1790. The git shim. Each mutation breaks ONE rule, and the selftest must notice it from the OUTSIDE: a real git command on a real repository, then a look
# at what moved. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='git_shim',
    subject='git-shim/git',
    selftest="scripts/git_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/git", "hooks/scripts/session-start.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation('add --all is not refused', 'if seen all; then RULE="git add --all', 'if false; then RULE="git add --all', 'add --all and every prefix'),
        Mutation('a long option is matched only in full, so --al and --ha pass', 'case "$c" in "$name"*) SEEN="$SEEN$c "; hit=1 ;; esac', 'case "$c" in "$name") SEEN="$SEEN$c "; hit=1 ;; esac', 'add --all and every prefix'),
        Mutation('a root pathspec is only the literal dot', '[ "$(norm "$PFX" "$p")" = "" ]', '[ "$p" = "." ]', 'add of the repository root is refused in every spelling'),
        Mutation(':/ is not read as the root', '    :/*) rest="${p#:/}"; p="$rest"; PFX="" ;;', '    :/*) return 1 ;;', 'add of the repository root is refused in every spelling'),
        Mutation('a bare glob is not the root', '    "*"|"**") p="" ;;', '    "*"|"**") p="$p" ;;', 'add of the repository root is refused in every spelling'),
        Mutation('the prefix is ignored, so `add .` in a subdirectory is refused', '[ "$(norm "$PFX" "$p")" = "" ]', '[ "$(norm "" "$p")" = "" ]', 'add near-misses run'),
        Mutation('add --dry-run is refused', '    add)\n      seen dry-run && return 0', '    add)\n      :', 'add near-misses run'),
        Mutation('add -u is refused', '      seen update && return 0; seen patch', '      seen patch', 'add near-misses run'),
        Mutation('reset --hard is not refused', 'if seen hard; then', 'if false; then', 'reset --hard and its prefixes'),
        Mutation('checkout --force is not refused', 'if seen force; then RULE="git checkout --force', 'if false; then RULE="git checkout --force', 'checkout and switch that discard work'),
        Mutation('checkout of the root is not refused', '      if any_root_pathspec; then RULE="git checkout of the repository root', '      if false; then RULE="git checkout of the repository root', 'checkout and switch that discard work'),
        Mutation('switch --force is not refused', 'if seen force || seen discard-changes; then', 'if false; then', 'checkout and switch that discard work'),
        Mutation('restore --staged . is refused', 'if { seen worktree || ! seen staged; } && any_root_pathspec; then', 'if any_root_pathspec; then', 'restore --staged passes'),
        Mutation('restore --staged --worktree . is allowed', 'if { seen worktree || ! seen staged; } && any_root_pathspec; then', 'if { ! seen staged; } && any_root_pathspec; then', 'restore of the working tree root is refused'),
        Mutation('clean --force is not refused', 'if seen force; then RULE="git clean --force', 'if false; then RULE="git clean --force', 'clean --force in every spelling'),
        Mutation('a clean dry run is refused', '    clean)\n      seen dry-run && return 0', '    clean)\n      :', 'clean dry runs pass'),
        Mutation('requireForce=false is not checked', 'if ! seen interactive && [ "$("$real" "${GLOBALS[@]}" config --type=bool --get clean.requireForce 2>/dev/null)" = "false" ]; then', 'if false; then', 'requireForce is off'),
        Mutation('--no-verify is not refused', 'if seen no-verify; then', 'if false; then', '--no-verify in every spelling'),
        Mutation('commit -n is not read as --no-verify', '    commit) echo "n=no-verify" ;;', '    commit) echo "" ;;', '--no-verify in every spelling'),
        Mutation('the value of commit -m is read as an option', '    commit) echo "mFCct" ;;', '    commit) echo "FCct" ;;', 'commit near-misses run'),
        Mutation('-- does not end the options', '      --) seen_dd=1 ;;', '      --) ;;', 'add near-misses run'),
        Mutation('-c core.hooksPath is not refused', 'case "$(lower "${ARGV[$i]}")" in core.hookspath*) RULE="-c core.hooksPath', 'case "$(lower "${ARGV[$i]}")" in core.hookspathXX*) RULE="-c core.hooksPath', 'core.hooksPath on the command line is refused'),
        Mutation('core.hooksPath is matched case-sensitively', 'case "$(lower "${ARGV[$i]}")" in core.hookspath*) RULE="-c core.hooksPath', 'case "${ARGV[$i]}" in core.hookspath*) RULE="-c core.hooksPath', 'core.hooksPath on the command line is refused'),
        Mutation('a git alias is not expanded', 'val="$("$real" "${GLOBALS[@]}" config --get "alias.$SUB" 2>/dev/null)" || val=""', 'val=""', 'a git alias is expanded'),
        Mutation('a shell alias verdict is ignored', 'case "${1##*/}" in git|git.exe) shift; evaluate "$@" || return 1 ;; esac', 'case "${1##*/}" in git|git.exe) shift; evaluate "$@" ;; esac', 'a git alias is expanded'),
        Mutation('the shim finds itself as the real git', '  [ "$dd" = "$self_dir" ] && continue', '  :', 'does not loop'),
        Mutation('the escape variable is not read', 'if [ "${RAILS_FLOW_GIT_OK:-}" = 1 ]; then', 'if [ "${RAILS_FLOW_GIT_OK:-}" = 2 ]; then', 'RAILS_FLOW_GIT_OK=1 runs the real git'),
        Mutation('-C is not forwarded when finding the root', '  TOP="$("$real" "${GLOBALS[@]}" rev-parse --show-toplevel 2>/dev/null)" || TOP=""', '  TOP="$("$real" rev-parse --show-toplevel 2>/dev/null)" || TOP=""', '-C is honoured'),
    ),
)
