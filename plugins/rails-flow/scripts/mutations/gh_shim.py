"""Mutation guard: gh_shim. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1839. The gh shim. Each mutation breaks ONE rule, and the selftest must notice it from the OUTSIDE: a real gh command through a real shell in a real repository, with a stub gh behind
# the shim that records whether it ran. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='gh_shim',
    subject='git-shim/gh',
    selftest="scripts/gh_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/gh", "hooks/scripts/guard-pr-ready.sh", "hooks/scripts/lib"),
    narrow_with="--match",
    mutations=(
        Mutation('RAILS_FLOW_GH_OK is ignored', 'if [ "${RAILS_FLOW_GH_OK:-}" = 1 ]; then', 'if false; then', 'escape'),
        Mutation('a `pr ready` is never recognised', '      [ "$a" = ready ] && return 0', '      [ "$a" = ready ] && return 1', 'no record'),
        Mutation('the value of -R between pr and ready is read as the verb', '      case "$a" in -R|--repo) skip=1; continue ;; -*) continue ;; esac', '      case "$a" in -*) continue ;; esac', 'explicit target'),
        Mutation('a gh alias is not looked up', 'elif name="$(alias_word "${ORIG[@]}")" && exp="$(alias_expansion "$name")" && [ -n "$exp" ]; then', 'elif false; then', 'alias flags'),
        Mutation('the judge verdict is ignored', 'if "$py" -I "$lib" --shim "${argv[@]}"; then', 'if true; then', 'no record'),
        Mutation('a missing python3 lets a `pr ready` through', 'is missing, so the sweep record for HEAD cannot be checked (RAILS_FLOW_GH_OK=1 to override, audited)." >&2\n  exit 1', 'is missing, so the sweep record for HEAD cannot be checked (RAILS_FLOW_GH_OK=1 to override, audited)." >&2\n  exec "$real" "${ORIG[@]}"', 'no python3'),
        Mutation('the value of -R before an alias is read as the alias name', '    case "$a" in -R|--repo) skip=1; continue ;; -*) continue ;; esac\n    printf', '    case "$a" in -*) continue ;; esac\n    printf', 'alias flags'),
        Mutation('an alias expansion after a TAB or several spaces is not read', '      "$name":*) found=1; value=', '      "$name"": "*) found=1; value=', 'alias flags'),
        Mutation('a gh api that marks a PR ready is not judged', 'if has_pr_ready "${ORIG[@]}" || has_api_ready "${ORIG[@]}"; then', 'if has_pr_ready "${ORIG[@]}"; then', 'gh api'),
        Mutation('an alias placeholder is not substituted', 'expanded+=("${rest[$((n - 1))]:-}")', 'expanded+=("$w")', 'alias placeholder'),
        Mutation('a second copy of the shim is taken for the real gh', '  is_shim "$d/gh" && continue', '  :', 'two shims'),
        Mutation('an alias expansion that is not plain words is read, not refused', '    *[!A-Za-z0-9\\ \\\t_./:@=,+%\\$-]*)', '    *NEVER_MATCHES*)', 'alias flags'),
        Mutation('a quoted placeholder is not normalised, so a documented alias is refused', '  for n in 1 2 3 4 5 6 7 8 9; do', '  for n in; do', 'alias placeholder'),
        Mutation('a relative or empty PATH entry can be the real gh', '  case "$d" in /*) ;; *) continue ;; esac\n', '  [ -n "$d" ] || d="."\n', 'real gh path'),
        Mutation('a gh inside the checkout can be the real gh', '  if [ -n "$repo_top" ]; then case "$dd/" in "$repo_top"/*) continue ;; esac; fi\n', '', 'real gh path'),
        Mutation('an indented continuation line of a multi-line alias is ignored', '      case "$line" in " "*|"\t"*) value="$value |" ;; *) break ;; esac\n', '      break\n', 'alias flags'),
        Mutation('the judge is the first python3 on PATH, not the lib\'s', 'py="$(trusted_python)"\nif [ -z "$py" ]', 'py="$(command -v python3)"\nif [ -z "$py" ]', 'interpreter'),
    ),
)
