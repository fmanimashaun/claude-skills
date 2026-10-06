"""Mutation guard: hook_normalize_cmd. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #906. The lib both hooks source. Each mutation drops one peel or one strip, and the matrix in
# check_hook_gates must notice from the OUTSIDE (exit codes), not by reading the lib.
GUARD = Guard(
    name="hook_normalize_cmd",
    subject="plugins/rails-flow/hooks/scripts/lib/normalize_cmd.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the fixture groups that drive this subject (#1497): the whole harness per
    # mutant was ~70% of the mutation-coverage budget.
    selftest_args=("--only", "guard_bash,release_gate"),
    needs=(
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        Mutation(
            "git global options are no longer peeled, so `git -C repo add -A` presents as `git -C ...` and passes",
            "      while (j <= n && t[j] ~ /^-/) {",
            "      while (0) {",
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
            "    | tr ';|&()' '\\n' \\",
            '    | cat \\',
            "`git status && git add -A` is blocked",
        ),
        # ---- #1472: what the shell runs from inside a string, a wrapper or a group ------------------
        Mutation(
            "the strings a shell runs are never normalised, so `bash -c 'git add -A'` is invisible again",
            "    next=\"$(printf '%s' \"$level\" | _inner_strings \"$(( d > 0 ))\" | _join_strings)\"",
            "    next=\"\"",
            "`\"bash -c 'git add -A'\"` runs the command and is blocked",
        ),
        Mutation(
            "a shell's -c is not recognised, so its command string is never read",
            "            if (w ~ /^-[A-Za-z]*c/) seenc = 1",
            "            if (0) seenc = 1",
            "`\"bash -lc 'git reset --hard'\"` runs the command and is blocked",
        ),
        Mutation(
            "eval's arguments are not read as a command",
            '      if (b == "eval") {',
            "      if (0) {",
            "`'eval \"git add -A\"'` runs the command and is blocked",
        ),
        Mutation(
            "a $( ) inside double quotes is not read, so `echo \"$(git add -A)\"` passes",
            "emit(substr(s, i + 2, j - i - 2)); v = v substr",
            "v = v substr",
            "`'echo \"$(git add -A)\"'` runs the command and is blocked",
        ),
        Mutation(
            "one level of nesting only, so `bash -c \"eval '...'\"` hides the inner command",
            "  while [ \"$d\" -lt 3 ]; do",
            "  while [ \"$d\" -lt 1 ]; do",
            "eval \\'git add -A\\'\"'` runs the command and is blocked",
        ),
        Mutation(
            "heredoc bodies are lexed as commands, so a script WRITTEN by heredoc is refused",
            "        for (k = 1; k <= HDN; k++) {",
            "        for (k = 1; k <= 0; k++) {",
            "CONTROL: `\"cat <<'X' > s.sh\\nbash -c 'git add -A'\\nX\\ngit status\"` passes",
        ),
        Mutation(
            "a heredoc body inside $( ) is scanned, so a `)` in it ends the substitution early",
            '      if (c == "\\n" && hn) {',
            '      if (0) {',
            'e t --body "$(cat <<\\\'EOF\\\'\\n1) don\\\'t run `g\'',
        ),
        Mutation(
            "the pre-check reads the raw text, so a quoted `e'v'al` skips the lexer",
            "    p = S; gsub(/[\\047\"\\\\]/, \"\", p)",
            "    p = S",
            "`'e\\'v\\'al \"git add -A\"'` runs the command and is blocked",
        ),
        Mutation(
            "an unclosed heredoc in $( ) swallows the rest of the text",
            "        if (!found) i = start",
            "",
            "1) x\\n)\"\\nbash -c",
        ),
        # ---- #1504: one pipeline per depth, and a linear pre-check ----------------------------------
        Mutation(
            "a batch boundary does not reset heredoc state, so an unclosed heredoc in one string swallows the next (#1504)",
            "    $0 == \"\\002\" { inh=0; pending=\"\"; insub=0; inbt=0; next }",
            "    $0 == \"\\002\" { next }",
            "an unclosed heredoc in one string does not swallow the next",
        ),
        Mutation(
            "a batch is lexed as one text, so an unbalanced quote in one string hides the next (#1504)",
            "    if (batch) np = split(S, P, \"\\n\\002\\n\"); else { np = 1; P[1] = S }",
            "    np = 1; P[1] = S",
            "an unbalanced quote in one string does not stop the next being lexed",
        ),
        Mutation(
            "the bash `${var//[set]/}` pre-check is back, so a PR body costs seconds (#1504)",
            "    next=\"$(printf '%s' \"$level\" | _inner_strings \"$(( d > 0 ))\" | _join_strings)\"",
            "    _q=\"'\" _dq='\"' _bs='\\\\'; _p=\"${level//[$_q$_dq$_bs$_bs]/}\"; next=\"$(printf '%s' \"$level\" | _inner_strings \"$(( d > 0 ))\" | _join_strings)\"",
            "0 bash pattern substitutions over the command",
        ),
        Mutation(
            # #1504 takeover: the ratchet that COUNTS pipelines, so load cannot hide the regression
            "each depth's strings get a pipeline apiece again, so 30 `$(…)` cost 30 pipelines, not 1 (#1504)",
            "    printf '%s\\n' \"$next\" | _normalize_one || return 1",
            "    printf '%s\\n' \"$next\" | while IFS= read -r _s; do printf '%s\\n' \"$_s\" | _normalize_one; done || return 1",
            "30 `$(…)` strings at one depth cost 2",
        ),
        Mutation(
            "the raw command is split at a \\002 line too, so a control byte hides what follows (#1519 review)",
            "    if (batch) np = split(S, P, \"\\n\\002\\n\"); else { np = 1; P[1] = S }",
            "    np = split(S, P, \"\\n\\002\\n\")",
            "a raw \\002 line does not split the command",
        ),
        Mutation(
            "a string's own \\002 is kept, so it fakes a boundary in the next depth's batch (#1519 review)",
            "_join_strings() { awk 'NR > 1 { print \"\\002\" } { gsub(/\\002/, \"\"); gsub(/\\001/, \"\\n\"); print }'; }",
            "_join_strings() { awk 'NR > 1 { print \"\\002\" } { gsub(/\\001/, \"\\n\"); print }'; }",
            "a \\002 line inside a string does not split the batch",
        ),
        Mutation(
            "a wrapper such as `command` is not peeled",
            '    if (w == "command" || w == "builtin" || w == "nohup" || w == "time") { i = skipopts(t, n, i + 1, ""); continue }',
            "",
            "`'command git add -A'` runs the command and is blocked",
        ),
        Mutation(
            "sudo's valued options are flags, so `sudo -u deploy` presents `deploy` as the command",
            '    if (w == "sudo")    { i = skipopts(t, n, i + 1, "-u -g -h -p -C -U -r -t -D -R -T --user --group --host --prompt --other-user --role --type --chdir --chroot --close-from --command-timeout"); continue }',
            '    if (w == "sudo")    { i = skipopts(t, n, i + 1, ""); continue }',
            "`'sudo -u deploy git add -A'` runs the command and is blocked",
        ),
        Mutation(
            "grouping words are not peeled, so `{ git add -A; }` and `if …; then git add -A` pass",
            '    if (w == "{" || w == "!" || w == "if" || w == "then" || w == "elif" || w == "else" || w == "do" || w == "while" || w == "until") { i++; continue }',
            "",
            "`'{ git add -A; }'` runs the command and is blocked",
        ),
        Mutation(
            "git spelled by path or with .exe is not git",
            "  function isgit(w) { sub(/^\\\\/, \"\", w); return w ~ /^([^ \\t]*\\/)?git(\\.exe)?$/ }",
            "  function isgit(w) { sub(/^\\\\/, \"\", w); return w ~ /^git$/ }",
            "`'/usr/bin/git add -A'` runs the command and is blocked",
        ),
        Mutation(
            "an inline alias is not resolved, so `git -c alias.p=push p --force` passes",
            "      if (j <= n) { w = t[j]; if (tolower(w) in al) w = al[tolower(w)]; out = out \" \" w; j++ }",
            "      if (j <= n) { w = t[j]; out = out \" \" w; j++ }",
            "`'git -c alias.p=push p --force origin main'` runs the command and is blocked",
        ),
        Mutation(
            "the lexer does not end a command at an operator, so `echo x | xargs …` is one command",
            '      if (c == ";" || c == "&" || c == "|" || c == "(" || c == ")") { endcmd(); i++; continue }',
            "",
            "`\"echo x; bash -c 'git add -A'\"` runs the command and is blocked",
        ),
        Mutation(
            # #1526
            'a heredoc opened inside $( ) runs to the end again, hiding what follows the $( )',
            '      if (insub && $0 ~ /^[ \\t]*\\)/) { inh=0; pending=delim; pdash=dash; print; next }',
            '      if (0) { inh=0; pending=delim; pdash=dash; print; next }',
            'a heredoc left open inside $( ) does not hide',
        ),
        Mutation(
            # #1529 review
            'a heredoc left open inside backticks swallows the rest of the text',
            '      if (inbt && index($0, "`")) { inh=0; pending=delim; pdash=dash; print; next }',
            '',
            'BACKTICK',
        ),
        Mutation(
            # #1529 round 2
            'a pending delimiter no longer suppresses new heredocs, so a phantom heredoc hides the command',
            '    pending != "" {\n',
            '    0 {\n',
            'phantom',
        ),
        Mutation(
            # #1529 round 2
            "the normaliser's status is discarded again, so a failing awk reads as a clean result",
            # #1504 takeover: EVERY status in normalize_segments, since the batched loop returns its own
            # pipelines' status too, and with only the first discarded the loop still caught a failing awk.
            '  printf \'%s\' "$raw" | _normalize_one || return 1\n  level="$raw"\n  while [ "$d" -lt 3 ]; do\n'
            '    next="$(printf \'%s\' "$level" | _inner_strings "$(( d > 0 ))" | _join_strings)" || return 1\n'
            '    [ -n "$next" ] || return 0\n    printf \'%s\\n\' "$next" | _normalize_one || return 1\n',
            '  printf \'%s\' "$raw" | _normalize_one\n  level="$raw"\n  while [ "$d" -lt 3 ]; do\n'
            '    next="$(printf \'%s\' "$level" | _inner_strings "$(( d > 0 ))" | _join_strings)"\n'
            '    [ -n "$next" ] || return 0\n    printf \'%s\\n\' "$next" | _normalize_one\n',
            'with an awk that exits 2',
        ),
    ),
)
