"""Mutation guard: git_guard_pre_push. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1789. The pre-push guard. Each mutation breaks ONE rule or ONE fail-closed branch, and the selftest must notice it from the
# OUTSIDE: a real push or a real commit, then a look at what moved. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='git_guard_pre_push',
    subject='git-hooks/pre-push',
    selftest="scripts/git_guard_selftest.py",
    needs=("scripts/fixture_git.py", "git-hooks/pre-push", "git-hooks/pre-commit", "scripts/install-git-guards.sh"),
    narrow_with="--match",
    mutations=(
        Mutation(
            'a delete of a protected branch is not reported',
            'bad="${bad}  - $rref: a delete (protected branches are never deleted by a push)"$\'\\n\'',
            'bad="$bad"',
            'deleting a protected branch is refused',
        ),
        Mutation(
            'a non-fast-forward is not reported',
            '    1) bad="${bad}  - $rref: not a fast-forward ($rsha is not an ancestor of $lsha), so it would rewrite history"$\'\\n\' ;;',
            '    1) ;;',
            'a force push to main is refused',
        ),
        Mutation(
            'an ancestry check that cannot be answered is allowed',
            '    *) bad="${bad}  - $rref: cannot tell whether it is a fast-forward, because the remote tip $rsha is not in this clone (git fetch first)"$\'\\n\' ;;',
            '    *) ;;',
            'never seen is refused until it is fetched',
        ),
        Mutation(
            'main is not in the default protected list',
            'PROTECTED="main dev staging"',
            'PROTECTED="dev staging"',
            'a force push to main is refused',
        ),
        Mutation(
            'dev is not in the default protected list',
            'PROTECTED="main dev staging"',
            'PROTECTED="main staging"',
            'a force push to dev is refused',
        ),
        Mutation(
            'staging is not in the default protected list',
            'PROTECTED="main dev staging"',
            'PROTECTED="main dev"',
            'a force push to staging is refused',
        ),
        Mutation(
            'a declared protected-branches is not added',
            'PROTECTED="$PROTECTED $extra"',
            'PROTECTED="$PROTECTED"',
            'declared protected-branches adds a name and a glob',
        ),
        Mutation(
            'a fenced declaration is read',
            '    if [[ $line =~ $re_fence ]]; then fence=$((1 - fence)); continue; fi',
            '    :',
            'inside a code block, a comment or an indented block is not read',
        ),
        Mutation(
            'a commented declaration is read',
            '    case "$line" in *"<!--"*) case "$line" in *"-->"*) ;; *) comment=1 ;; esac; continue ;; esac',
            '    :',
            'inside a code block, a comment or an indented block is not read',
        ),
        Mutation(
            'an indented declaration is read',
            '    [[ $line =~ $re_indent ]] && continue',
            '    :',
            'inside a code block, a comment or an indented block is not read',
        ),
        Mutation(
            'creating a new protected branch is treated as an overwrite',
            '  if [[ $rsha =~ ^0+$ ]]; then continue; fi    # the branch does not exist on the remote yet: nothing to overwrite',
            '  :',
            'the first push of a new protected branch is allowed',
        ),
        Mutation(
            'every branch is protected',
            '  is_protected "$name" || continue',
            '  :',
            'a branch that is not protected is allowed',
        ),
        Mutation(
            'the escape variable is not read',
            'if [ "${RAILS_FLOW_PROTECTED_OK:-}" = 1 ]; then',
            'if [ "${RAILS_FLOW_PROTECTED_OK:-}" = 2 ]; then',
            'RAILS_FLOW_PROTECTED_OK=1 lets a rewrite through',
        ),
        Mutation(
            'a line that cannot be read is let through',
            '  if [ -z "${rsha:-}" ] || [ -n "${more:-}" ]; then',
            '  if false; then',
            'an unreadable line from git is refused',
        ),
        Mutation(
            'a local commit that cannot be resolved is not reported',
            '  if ! git rev-parse --verify -q "${lsha}^{commit}" >/dev/null 2>&1; then',
            '  if false; then',
            'a local commit it cannot resolve is refused',
        ),
    ),
)
