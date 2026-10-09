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
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
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
            "the trigger ignores a shell word, so a shell reading a redirect or a script operand never reaches the helper",
            ' || rawhit "$cmd" "$_re_shell_word" \\\n   || rawhit',
            ' \\\n   || rawhit',
            "a script with a create fed to bash by redirect is refused through the real hook",
        ),
        Mutation(
            "the trigger keeps `$`, so gh issue $'create' never reaches the helper (#1495)",
            "  _flat=\"$(printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\\$\" | tr '\\n' ' ')\"",
            "  _flat=\"$(printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\" | tr '\\n' ' ')\"",
            "`gh issue $'create'` reaches the helper",
        ),
        Mutation(
            "the shell word needs a space after it, so sh<f, bash>/dev/null<f and bash&>log<f never reach the helper (#1489, #1495, #1513)",
            "_re_shell_word='(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]<>&]|$)'",
            "_re_shell_word='(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]]|$)'",
            "guard-bash (#1489 review): `sh<`",
        ),
        Mutation(
            "the trigger ignores an escaped $'…', so gh issue $'\\x63reate' never reaches the helper (#1513)",
            ' || rawhit "$cmd" "$_re_ansi"; then',
            '; then',
            "x63reate'` reaches the helper",
        ),
        Mutation(
            "the trigger keeps quotes, so gh issue \"create\" never reaches the helper",
            "  _flat=\"$(printf '%s' \"$cmd\" | tr -d \"\\\"'\\\\\\\\\\$\" | tr '\\n' ' ')\"",
            "  _flat=\"$(printf '%s' \"$cmd\" | tr '\\n' ' ')\"",
            "guard-bash (#1462): `gh issue \"create\" -t X --body-` with no label is refused",
        ),
        # #1423: the label helper must run for a create that never starts a normalised segment.
        Mutation(
            "the label helper runs only for a create at a normalised segment start, so a spelling the normaliser does not resolve escapes",
            'if [ "$_fire" = 1 ] || rawhit "$_flat" "$_re_verb" || rawhit "$cmd" "$_re_shell_word" \\\n   || rawhit "$cmd" "$_re_source" || rawhit "$cmd" "$_re_runs_text" || rawhit "$_flat" "$_re_api" || rawhit "$cmd" "$_re_ansi"; then',
            "if hit '^gh[[:space:]]+issue[[:space:]]+create\\b'; then",
            "guard-bash (#1495): `gh issue $'create'` reaches the helper",
        ),
        # #1545: the label trigger had grep and tr called directly, so with either missing it was skipped.
        Mutation(
            "the raw-text matcher calls grep even when there is none, so the trigger fails closed's opposite: skipped",
            'local text="$1" re="$2"\n  if [ "$have_grep" = 1 ]; then',
            'local text="$1" re="$2"\n  if true; then',
            "guard-bash (#1545): with no grep on PATH, an unlabelled",
        ),
        Mutation(
            "with no tr the trigger no longer fires unconditionally, so the label check is skipped there",
            '_flat="$cmd"; _fire=1',
            '_flat="$cmd"; _fire=0',
            "guard-bash (#1545): with no tr on PATH, a QUOTED verb",
        ),
        # #1515: the trigger must reach the helper for a script, a source, an indirect create and a `gh api` POST.
        Mutation(
            "`source` and the dot no longer trigger the helper",
            ' || rawhit "$cmd" "$_re_source"',
            '',
            "guard-bash (#1515): `source bad.sh` is refused",
        ),
        Mutation(
            "`eval`, `xargs`, `alias` and a function definition no longer trigger the helper (#1645 R2)",
            ' || rawhit "$cmd" "$_re_runs_text"',
            '',
            "guard-bash (#1645 R2): `alias g='gh issue'; g create -t X` is refused",
        ),
        Mutation(
            "`gh api` naming issues no longer triggers the helper",
            ' || rawhit "$_flat" "$_re_api"',
            '',
            "guard-bash (#1515): `gh api -X POST repos/o/r/issues",
        ),
        Mutation(
            "the verb trigger needs a gh word again, so a gh word built at run time never reaches the helper",
            "_re_verb='issue[[:space:]]+(create|new)'",
            "_re_verb='gh[[:space:]].*issue[[:space:]]+(create|new)'",
            "guard-bash (#1515): `$(echo gh) issue create",
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
            '    local rest="$seg"$\'\\n\' line\n    while [ -n "$rest" ]; do\n      line="${rest%%$\'\\n\'*}"; rest="${rest#*$\'\\n\'}"\n      [[ $line =~ $re ]] && return 0',
            '    local rest="$seg"$\'\\n\' line\n    while [ -n "$rest" ]; do\n      line="${rest%%$\'\\n\'*}"; rest="${rest#*$\'\\n\'}"\n      false',
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
