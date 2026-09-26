"""Mutation guard: hook_guard_bash. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #826. `-A` and `.` were anchored to the first argument of `git add`.
GUARD = Guard(
    name='hook_guard_bash',
    subject='plugins/rails-flow/hooks/scripts/guard-bash.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),   # the harness drives release-gate.sh too (#906)
    mutations=(
        # #1342: each discarding form goes unblocked again, or its safe twin gets caught with it.
        Mutation(
            "git clean -f is allowed",
            "  deny \"git clean -f deletes untracked files",
            "  : \"git clean -f deletes untracked files",
            "`git clean -fd` is blocked",
        ),
        Mutation(
            "a dry-run clean is refused along with the real one",
            "   && ! hit '^git[[:space:]]+clean\\b.*([[:space:]]-[a-zA-Z]*n|[[:space:]]--dry-run\\b)'; then",
            "   ; then",
            "safe twin `git clean -fdn` stays allowed",
        ),
        Mutation(
            "git checkout -- <path> is allowed",
            "  deny \"git checkout -- <path> / git checkout . overwrites",
            "  : \"git checkout -- <path> / git checkout . overwrites",
            "`git checkout -- app/x.rb` is blocked",
        ),
        Mutation(
            "git restore . is allowed",
            "  deny \"git restore . discards every uncommitted edit",
            "  : \"git restore . discards every uncommitted edit",
            "`git restore .` is blocked",
        ),
        Mutation(
            "restore --staged (unstage only) is refused with the discarding form",
            "   && ! hit '^git[[:space:]]+restore\\b.*--staged\\b' ; then",
            "   ; then",
            "safe twin `git restore --staged .` stays allowed",
        ),
        Mutation(
            "git branch -D is allowed",
            "  deny \"git branch -D deletes an unmerged branch.",
            "  : \"git branch -D deletes an unmerged branch.",
            "`git branch -D feature/x` is blocked",
        ),
        Mutation(
            "git stash drop is allowed",
            "  deny \"git stash drop/clear is refused",
            "  : \"git stash drop/clear is refused",
            "`git stash drop` is blocked",
        ),
        Mutation(
            "the `git add` pattern goes back to first-argument anchoring",
            "if hit '^git[[:space:]]+add([[:space:]]+-[a-zA-Z]+)*[[:space:]]+(-[a-zA-Z]*A[a-zA-Z]*\\b|--all\\b|\\./?($|[[:space:]])|:/($|[[:space:]]))'; then",
            "if hit '^git[[:space:]]+add[[:space:]]+(-A\\b|--all\\b|\\.($|[[:space:]]))'; then",
            "`git add -v -A` is blocked",
        ),
        # #906. The normaliser is what separates "mentions the rule" from "stages everything".
        Mutation(
            "the normaliser is bypassed and the raw text is matched, so a prefixed `FOO=1 git add -A` fails OPEN",
            '  seg="$(printf \'%s\' "$cmd" | normalize_segments)"',
            '  seg="$cmd"',
            "`FOO=1 git add -A` is blocked",
        ),
        Mutation(
            "the missing-lib fallback matches nothing instead of the raw text, so a lost file makes the guard fail OPEN",
            'else\n  seg="$cmd"\nfi',
            'else\n  seg=""\nfi',
            "falls back to the raw text and still blocks",
        ),
    ),
)
