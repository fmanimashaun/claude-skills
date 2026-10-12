"""Mutation guard: git_guard_pre_commit. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1789. The pre-commit guard. Each mutation breaks ONE rule or ONE fail-closed branch, and the selftest must notice it from the
# OUTSIDE: a real push or a real commit, then a look at what moved. `narrow_with` runs each mutant on only the case its `expects` names.
GUARD = Guard(
    name='git_guard_pre_commit',
    subject='git-hooks/pre-commit',
    selftest="scripts/git_guard_selftest.py",
    needs=("scripts/fixture_git.py", "git-hooks/pre-push", "git-hooks/pre-commit", "scripts/install-git-guards.sh"),
    narrow_with="--match",
    mutations=(
        Mutation(
            'env files are not a never-commit class',
            '    .env|.env.*) case',
            '    .envX|.envX.*) case',
            'a new env file is refused',
        ),
        Mutation(
            'the .example/.sample/.template twins are refused',
            '*.example|*.sample|*.template) return 1 ;; esac; return 0 ;;',
            '*.example|*.sample) return 1 ;; esac; return 0 ;;',
            'look-alikes are allowed',
        ),
        Mutation(
            'a .keep placeholder is refused',
            '    .keep|.gitkeep|id_rsa.pub) return 1 ;;\n',
            '',
            'look-alikes are allowed',
        ),
        Mutation(
            'certificates are not a never-commit class',
            '    *.pem|*.key|*.p12|id_rsa|id_rsa.*|*.sqlite3|*.log|.ds_store) return 0 ;;',
            '    *.key|*.p12|id_rsa|id_rsa.*|*.sqlite3|*.log|.ds_store) return 0 ;;',
            'a key or certificate is refused',
        ),
        Mutation(
            'databases, logs and .DS_Store are not a never-commit class',
            '    *.pem|*.key|*.p12|id_rsa|id_rsa.*|*.sqlite3|*.log|.ds_store) return 0 ;;',
            '    *.pem|*.key|*.p12|id_rsa|id_rsa.*) return 0 ;;',
            'a database, a log or an OS file is refused',
        ),
        Mutation(
            'dependency and temp directories are not a never-commit class',
            '    */node_modules/*|*/.bundle/*) return 0 ;;     # at any depth: a dependency tree is never source',
            '    */.bundle/*) return 0 ;;     # at any depth: a dependency tree is never source',
            'a dependency or temp directory is refused',
        ),
        Mutation(
            'a file of exactly the limit is refused',
            '  if [ "$size" -gt "$max_bytes" ]; then',
            '  if [ "$size" -ge "$max_bytes" ]; then',
            'the size limit boundary is 5 MiB',
        ),
        Mutation(
            'a count of exactly the limit is refused',
            '  if [ "$new_files" -gt "$max_new" ]; then',
            '  if [ "$new_files" -ge "$max_new" ]; then',
            'the new-file count boundary is 100',
        ),
        Mutation(
            'the first commit of a repository is counted',
            'if [ "$first_commit" = 0 ]; then',
            'if true; then',
            'the first commit of a repository may add any number of files',
        ),
        Mutation(
            'modified files are counted as new files',
            '  staged A\n',
            '  staged ACMR\n',
            'modified files are not counted as new files',
        ),
        Mutation(
            'a rename into a never-commit path is not checked',
            'staged ACR\nwhile',
            'staged AC\nwhile',
            'a rename into a never-commit path is refused',
        ),
        Mutation(
            'a modified tracked env file is refused',
            'staged ACR\nwhile',
            'staged ACMR\nwhile',
            'a tracked env file that is only modified or deleted is allowed',
        ),
        Mutation(
            'a declared size limit is not read',
            'if [ -n "$v" ]; then [[ $v =~ ^[0-9]+$ ]] || fail "max-staged-file-mb in GUARDRAILS.md is \'$v\', not a whole number"; max_mb="$v"; fi',
            'if false; then :; fi',
            'a size limit declared in GUARDRAILS.md is read',
        ),
        Mutation(
            'a malformed size limit is guessed at',
            '[[ $v =~ ^[0-9]+$ ]] || fail "max-new-files-per-commit in GUARDRAILS.md is \'$v\', not a whole number"; max_new="$v"',
            'max_new="$v"',
            'a malformed declared limit is refused, not guessed',
        ),
        Mutation(
            'a fenced declaration is read',
            '    if [[ $line =~ $re_fence ]]; then fence=$((1 - fence)); continue; fi',
            '    :',
            'a code block is not',
        ),
        Mutation(
            'an indented declaration is read',
            '    [[ $line =~ $re_indent ]] && continue',
            '    :',
            'a code block is not',
        ),
        Mutation(
            'the escape variable is not read',
            'if [ "${RAILS_FLOW_STAGING_OK:-}" = 1 ]; then',
            'if [ "${RAILS_FLOW_STAGING_OK:-}" = 2 ]; then',
            'RAILS_FLOW_STAGING_OK=1 lets a commit through',
        ),
        Mutation(
            'a temp file that cannot be created is ignored',
            'tmp="$(mktemp "${TMPDIR:-/tmp}/git-guard.XXXXXX")" || fail "cannot create a temp file, so the staged content cannot be read"',
            'tmp="$(mktemp "${TMPDIR:-/tmp}/git-guard.XXXXXX")" || tmp=/dev/null',
            'when it cannot create its temp file it refuses',
        ),
        Mutation(
            'an unreadable index is read as nothing staged',
            '> "$tmp" 2>/dev/null || fail "cannot read the index (git diff --cached failed)"',
            '> "$tmp" 2>/dev/null || :',
            'a corrupt index refuses',
        ),
        Mutation(
            'paths are matched case-sensitively, so .ENV, KEY.PEM and Foo.LOG commit freely',
            'lc="$(printf \'%s\' "$1" | LC_ALL=C tr \'A-Z\' \'a-z\')"',
            'lc="$1"',
            'a new env file is refused',
        ),
        Mutation(
            'tmp/, log/ and coverage/ match at any depth, so app/services/log/x.rb is refused',
            '    /tmp/*|/log/*|/coverage/*) return 0 ;;       # at the repository ROOT only: app/services/log/x.rb and docs/coverage/z.md are source',
            '    */tmp/*|*/log/*|*/coverage/*) return 0 ;;',
            'look-alikes are allowed',
        ),
        Mutation(
            'tmp/, log/ and coverage/ at the root are not a never-commit class',
            '    /tmp/*|/log/*|/coverage/*) return 0 ;;       # at the repository ROOT only: app/services/log/x.rb and docs/coverage/z.md are source',
            '    /nothing/*) return 0 ;;',
            'a dependency or temp directory is refused',
        ),
        Mutation(
            'id_rsa.pub is refused with the private key',
            '    .keep|.gitkeep|id_rsa.pub) return 1 ;;',
            '    .keep|.gitkeep) return 1 ;;',
            'look-alikes are allowed',
        ),
    ),
)
