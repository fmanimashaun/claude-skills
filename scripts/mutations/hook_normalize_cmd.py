"""Mutation guard: hook_normalize_cmd. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #906. The lib both hooks source. Each mutation drops one peel or one strip, and the matrix in
# check_hook_gates must notice from the OUTSIDE (exit codes), not by reading the lib.
GUARD = Guard(
    name="hook_normalize_cmd",
    subject="plugins/rails-flow/hooks/scripts/lib/normalize_cmd.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    needs=("plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts"),
    mutations=(
        Mutation(
            "git global options are no longer peeled, so `git -C repo add -A` presents as `git -C ...` and passes",
            "    | sed -E 's/^git[[:space:]]+((-C|-c|--git-dir|--work-tree|--namespace|--exec-path)([[:space:]]*=?[[:space:]]*[^[:space:]]+)?[[:space:]]+)+/git /'",
            "    | cat",
            "`git -C repo add -A` is blocked",
        ),
        Mutation(
            "quoted spans are kept, so a commit message carrying `; git add -A` splits inside the quote and is blocked",
            '_strip_quotes()   { sed -E "s/\'[^\']*\'//g; s/\\"[^\\"]*\\"//g"; }',
            "_strip_quotes()   { cat; }",
            "wip; git add -A comes later",
        ),
        Mutation(
            "segments are not split, so `git status && git add -A` has no segment starting with git add",
            "    | tr ';|&' '\\n' \\",
            '    | cat \\',
            "`git status && git add -A` is blocked",
        ),
    ),
)
