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
        Mutation('a gh alias is not looked up', 'if has_pr_ready "${ORIG[@]}" || alias_hides_pr_ready "${ORIG[@]}"; then judge=1; fi', 'if has_pr_ready "${ORIG[@]}"; then judge=1; fi', 'alias'),
        Mutation('the judge verdict is ignored', 'if "$py" "$lib" --shim "${argv[@]}"; then', 'if true; then', 'no record'),
        Mutation('a missing python3 lets a `pr ready` through', 'is missing, so the sweep record for HEAD cannot be checked (RAILS_FLOW_GH_OK=1 to override, audited)." >&2\n  exit 1', 'is missing, so the sweep record for HEAD cannot be checked (RAILS_FLOW_GH_OK=1 to override, audited)." >&2\n  exec "$real" "${ORIG[@]}"', 'no python3'),
    ),
)
