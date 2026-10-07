"""Mutation guard: hook_guard_bash. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #826. `-A` and `.` were anchored to the first argument of `git add`.
GUARD = Guard(
    name='hook_guard_bash',
    subject='plugins/rails-flow/hooks/scripts/guard-bash.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # Only the fixture groups that drive this subject (#1497): the whole harness per
    # mutant was ~70% of the mutation-coverage budget.
    selftest_args=("--only", "guard_bash"),
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=(
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # the harness drives release-gate.sh too (#906)
    mutations=(
        # #1570: grep -q quits at the first match, printf takes SIGPIPE once the text outgrows the pipe
        # buffer, and pipefail read that 141 as "no match". `git add -A` plus 10k lines was allowed.
        Mutation(
            "hit() runs under pipefail again, so a long command that matches is read as no match",
            '( set +o pipefail; printf \'%s\\n\' "$seg" | grep -qE "$re" )',
            'printf \'%s\\n\' "$seg" | grep -qE "$re"',
            "followed by 10k lines is still blocked",
        ),
        # #1489: `bash < file` names no create, so the trigger must fire on the redirect itself.
        Mutation(
            "the trigger ignores a shell reading a redirect, so bash < file never reaches the helper",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]([^;&|]|[<>]&|&>)*)?<([^<(]|$)' ) \\",
            "   || false \\",
            "a script with a create fed to bash by redirect is refused through the real hook",
        ),
        Mutation(
            "the trigger keeps `$`, so gh issue $'create' never reaches the helper (#1495)",
            "if ( set +o pipefail; printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\\$\" | tr '\\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' ) \\",
            "if ( set +o pipefail; printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\" | tr '\\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' ) \\",
            "`gh issue $'create'` reaches the helper",
        ),
        Mutation(
            "the redirect trigger stops at a redirect's &, so bash 2>&1 < f never reaches the helper (#1495)",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]([^;&|]|[<>]&|&>)*)?<([^<(]|$)' ) \\",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&][^;&|]*)?<([^<(]|$)' ) \\",
            "the & of a fd duplication is not a separator",
        ),
        Mutation(
            "the trigger ignores an escaped $'…', so gh issue $'\\x63reate' never reaches the helper (#1513)",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -q \"\\\\$'[^']*\\\\\\\\\" ); then",
            "   : || ( set +o pipefail; printf '%s' \"$cmd\" | false && grep -q \"\\\\$'[^']*\\\\\\\\\" ); then",
            "x63reate'` reaches the helper",
        ),
        Mutation(
            "the trigger needs a space after the shell, so bash&>log<f never reaches the helper (#1513)",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]([^;&|]|[<>]&|&>)*)?<([^<(]|$)' ) \\",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]]([^;&|]|[<>]&|&>)*)?<([^<(]|$)' ) \\",
            "the trigger sees a redirect glued to the shell",
        ),
        Mutation(
            "the redirect trigger is the first version's, so /bin/bash, --norc, sh<f and 0< never reach the helper",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]([^;&|]|[<>]&|&>)*)?<([^<(]|$)' ) \\",
            "   || ( set +o pipefail; printf '%s' \"$cmd\" | grep -qE '(^|[[:space:];&|(])(sh|bash|zsh|dash|ksh)([[:space:]]+-[a-zA-Z]+)*[[:space:]]*<[^<(]' ) \\",
            "guard-bash (#1489 review):",
        ),
        Mutation(
            "the trigger keeps quotes, so gh issue \"create\" never reaches the helper",
            "if ( set +o pipefail; printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\\$\" | tr '\\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' ) \\",
            "if ( set +o pipefail; printf '%s' \"$cmd\" | tr '\\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' ) \\",
            "guard-bash (#1462): `gh issue \"create\" -t X --body-` with no label is refused",
        ),
        # #1423: the label helper must run for a create that never starts a normalised segment.
        Mutation(
            "the label helper runs only for a create at a segment start, so sh -c and /usr/bin/gh escape",
            "if ( set +o pipefail; printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\\$\" | tr '\\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' ) \\",
            "if hit '^gh[[:space:]]+issue[[:space:]]+create\\b'; then",
            "a create inside `sh -c` is refused through the real hook",
        ),
        # #1342: each discarding form goes unblocked again, or its safe twin gets caught with it.
        Mutation(
            "git clean -f is allowed",
            "  deny \"git clean -f deletes untracked files",
            "  : \"git clean -f deletes untracked files",
            "`git clean -fd` is blocked",
        ),
        Mutation(
            "a dry-run clean is refused along with the real one",
            "   && ! exempt '^git[[:space:]]+clean\\b.*([[:space:]]-[a-zA-Z]*n|[[:space:]]--dry-run\\b)'; then",
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
            "   && ! exempt '^git[[:space:]]+restore\\b.*--staged\\b' ; then",
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
            '  seg="$(printf \'%s\' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; degraded=1; }',
            '  seg="$cmd"',
            "`FOO=1 git add -A` is blocked",
        ),
        Mutation(
            "the missing-lib fallback matches nothing instead of the raw text, so a lost file makes the guard fail OPEN",
            'else\n  seg="$cmd"; degraded=1\nfi',
            'else\n  seg=""; degraded=1\nfi',
            "falls back to the raw text and still blocks",
        ),
        Mutation(
            # #1526
            'the payload is decoded strictly again, so an invalid UTF-8 byte hides the command',
            'd=json.loads(sys.stdin.buffer.read().decode("utf-8","surrogateescape"))',
            'd=json.loads(sys.stdin.buffer.read().decode("utf-8"))',
            'an invalid byte beside a QUOTED mention still parses and passes',
        ),
        Mutation(
            # #1529 review
            'degraded mode keeps the `^` anchor, so a compound command with no awk passes',
            '  [ "$degraded" = 1 ] && re="${re#^}"',
            '',
            'with no awk, a COMPOUND `cd x && git add -A` is blocked',
        ),
        Mutation(
            # #1529 review
            'with no grep, hit() matches nothing, so every rule passes',
            '      [[ $line =~ $re ]] && return 0',
            '      false',
            'with no grep, `git add -A` is blocked',
        ),
        Mutation(
            # #1529 round 2
            'an empty normalised result is treated as a failure again, so a comment-only command is refused',
            ' || { seg="$cmd"; degraded=1; }',
            '\n  case "$cmd" in *[![:space:]]*) [ -n "$seg" ] || { seg="$cmd"; degraded=1; } ;; esac',
            '`# git add -A` only mentions the rule and passes',
        ),
        Mutation(
            # #1529 round 2
            "exemptions apply in degraded mode again, so another segment's `-n` exempts a real clean",
            '[ "$degraded" = 1 ] && return 1; hit "$1"; }',
            'hit "$1"; }',
            'is not exempted by another segment',
        ),
        Mutation(
            # #1529 round 2
            'stdin is read with `cat` again, so no cat means an empty command',
            'input=""; IFS= read -r -d \'\' input || true',
            'input="$(cat)"',
            'with no cat, `git add -A` is blocked',
        ),
        Mutation(
            # #1529 round 3
            'pipefail is dropped, so a failing EARLY stage (no sed) reads as a clean result',
            'set -uo pipefail\n',
            'set -u\n',
            'with no sed, `git add -A` is blocked',
        ),
        Mutation(
            # #1529 round 3
            'with no grep, `=~` matches the whole text at once, so `^` sees only the first segment',
            '    local rest="$seg"$\'\\n\' line\n    while [ -n "$rest" ]; do\n      line="${rest%%$\'\\n\'*}"; rest="${rest#*$\'\\n\'}"\n      [[ $line =~ $re ]] && return 0\n    done\n    return 1',
            '    [[ $seg =~ $re ]]',
            'with no grep, a LATER segment',
        ),
    ),
)
