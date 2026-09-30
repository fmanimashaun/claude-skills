"""Mutation guard: hook_normalize_cmd. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #906. The lib both hooks source. Each mutation drops one peel or one strip, and the matrix in
# check_hook_gates must notice from the OUTSIDE (exit codes), not by reading the lib.
GUARD = Guard(
    name="hook_normalize_cmd",
    subject="plugins/rails-flow/hooks/scripts/lib/normalize_cmd.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    needs=("plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
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
            "  printf '%s' \"$raw\" | _inner_strings | {",
            "  : | {",
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
            '  [ "${_NC_DEPTH:-0}" -ge 3 ] && return 0',
            '  [ "${_NC_DEPTH:-0}" -ge 1 ] && return 0',
            "eval \\'git add -A\\'\"'` runs the command and is blocked",
        ),
        Mutation(
            "heredoc bodies are lexed as commands, so a script WRITTEN by heredoc is refused",
            "        for (k = 1; k <= HDN; k++) {",
            "        for (k = 1; k <= 0; k++) {",
            "CONTROL: `\"cat <<'X' > s.sh\\nbash -c 'git add -A'\\nX\\ngit status\"` passes",
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
    ),
)
