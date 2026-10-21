"""Mutation guard: gh_shim. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1839. The gh shim. Each mutation breaks ONE rule, and the selftest must notice it from the OUTSIDE: a real gh command through a real shell in a real repository, with a stub gh behind
# the shim that records whether it ran. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='gh_shim',
    subject='git-shim/gh',
    selftest="scripts/gh_shim_selftest.py",
    needs=("scripts/fixture_git.py", "git-shim/gh", "hooks/scripts/guard-pr-ready.sh", "hooks/scripts/lib",
           # #2258: the shim judges a claim-carrying body through guard-claims.sh, which reads extract_claims.py
           "hooks/scripts/guard-claims.sh", "scripts/extract_claims.py",
           "scripts/process_containment.py"),   # the selftest runs its cases under contained() (#1582)
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
        # #2258: the body of a claim-carrying command.
        Mutation('pr edit is not a claim-carrying verb', '"pr create"|"pr edit"|"issue comment")', '"pr create"|"issue comment")', 'claim bodies'),
        Mutation('an inline --body is not read', '      -b|--body) next=body ;; --body=*) body="${a#--body=}" ;;', '      -b|--body) ;; --body=*) ;;', 'claim bodies'),
        Mutation('a short flag joined to its value is not read', '      -F?*) file="${a#-F}"; file="${file#=}" ;;', '      -F?*) ;;', 'claim bodies'),
        Mutation('the hook is not run strict, so an unreadable body passes', 'RAILS_FLOW_CLAIMS_STRICT=1 /bin/bash -p "$hook"', '/bin/bash -p "$hook"', 'claim bodies'),
        Mutation('the hook refusing is ignored', '  [ "$rc" = 0 ] && return 0\n  echo "gh-shim (rails-flow): refused', '  return 0\n  echo "gh-shim (rails-flow): refused', 'claim bodies'),
        # #2268 review.
        Mutation('a body gh composes passes silently', '    echo "gh-shim (rails-flow): the body of \\`gh $verb\\` is composed by gh', '    return 0\n    echo "gh-shim (rails-flow): the body of \\`gh $verb\\` is composed by gh', 'claim bodies'),
        Mutation('a non-regular body file is read by the shim (a fifo hangs, a stream is starved)', '[ -n "$file" ] && [ -e "$file" ] && [ ! -f "$file" ]; }; then', '[ -n "$file" ] && false; }; then', 'claim bodies'),
        Mutation('GH_REPO is not read, so another repository is judged against this template', '  repo="${repo:-${GH_REPO:-}}"', '  :', 'claim bodies'),
        Mutation('gh is handed the original body, not the judged copy', '  "$real" "${out[@]}" --body-file "$JUDGED_TMP"', '  "$real" "$@"', 'claim bodies'),
        Mutation('a claim-carrying body is never judged', 'if verb="$(claims_verb "${ORIG[@]}")"; then\n  judge_body "$verb" "${ORIG[@]}" || exit 1', 'if false; then\n  judge_body "$verb" "${ORIG[@]}" || exit 1', 'claim bodies'),
        Mutation('a --body-file that cannot be read passes', '    cat -- "$file" > "$JUDGED_TMP" 2>/dev/null || { echo', '    cat -- "$file" > "$JUDGED_TMP" 2>/dev/null || { return 0; echo', 'claim bodies'),
        Mutation('a stdin body is refused instead of passed through loudly', '    echo "gh-shim (rails-flow): the body of \\`gh $verb\\` comes from stdin or a stream', '    return 1\n    echo "gh-shim (rails-flow): the body of \\`gh $verb\\` comes from stdin or a stream', 'claim bodies'),
        Mutation('an alias that expands to pr create skips the body check', '  if verb="$(claims_verb "${argv[@]}")"; then judge_body "$verb" "${argv[@]}" || exit 1; [ -n "$JUDGED_TMP" ] && run_judged "${argv[@]}"; fi', '  :', 'claim bodies'),
        Mutation('a signal removes the copy but the shim carries on, so gh gets a missing --body-file', "trap 'rf_body_cleanup; exit 143' TERM", "trap 'rf_body_cleanup' TERM", 'claim bodies'),
    ),
)
