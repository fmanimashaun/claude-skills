#!/usr/bin/env bash
# PreToolUse[Bash] — refuse a `git worktree add` that would orphan work already started. #1581
#
# The owner's rules for parallel sessions (issue #1581): one issue at a time, and resume in place. A
# prose rule stopped neither failure: sessions kept creating a second worktree mid-issue, and a restart
# created a duplicate of the worktree it had just left. This hook DENIES the command, and says where to
# resume. `lib/worktree_guard.py` makes the judgement; this wrapper only decides whether the command is
# one it judges, and makes every way the judgement can break a refusal.
#
# SCOPED TO `git worktree add`, AND SILENT OTHERWISE. A single-session project, a command that merely
# mentions the words, `git worktree list` and `git worktree remove` are exit 0 without a word. A guard
# that fired on ordinary work would be switched off, and then the rule has nothing behind it.
#
# FAILS CLOSED, SCOPED. Exit 2 blocks; any other non-zero is a NON-blocking error that lets the command
# run, so a crashing helper must be mapped to 2 here. With no python3, or no helper, a `git worktree add`
# is refused with the reason; the rest of the shell is untouched. Match the invoked command, not any
# substring: the normaliser (the one guard-bash.sh uses) presents `cd x && git -C repo worktree add`
# as `git worktree add`. When it cannot run, the match is unanchored, which also refuses a quoted
# mention: the right side to err on when the command could not be read.
#
# WHAT IT DOES NOT CATCH, STATED. It protects against ACCIDENT, not impersonation: a session's identity is
# the `session_id` it sends, and the lane record is written by the coordinator (coordination.py), so
# a session nobody recorded passes the "one issue" rule (the duplicate rule still holds, and needs no
# record). `git -C <another repo> worktree add` is judged against the repository of the payload's cwd.
# A worktree made by a script or by hand outside the agent is out of reach, and so is one reached through a shell
# variable, function or alias the normaliser cannot expand (`G=git; $G worktree add ...`). A `$VAR` or `$(...)` in the BRANCH
# cannot be judged without running it, so the duplicate check does not see it. Also out of reach: a pipe to `sh`, `find -exec`,
# an alias and a heredoc. A command the normaliser surfaces but the helper cannot parse is refused, not allowed: the two
# parsers can disagree, and the disagreement must fail closed. `cd <repo> && git worktree add` from a cwd outside any
# repository is refused for the same reason (which repository it targets cannot be judged); from a cwd INSIDE one it is
# judged against that cwd's repository, like `git -C`.
set -uo pipefail
input=""; IFS= read -r -d '' input || true

parsed=1
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
d=json.loads(sys.stdin.buffer.read().decode("utf-8","surrogateescape"))
sys.stdout.buffer.write(str(d.get("tool_input",{}).get("command","")).encode("utf-8","replace"))' 2>/dev/null)" || { parsed=0; cmd="$input"; }

_dir="${BASH_SOURCE[0]%/*}"
_lib="$_dir/lib/normalize_cmd.sh"
_py="$_dir/lib/worktree_guard.py"

degraded=0
if [ "$parsed" = 1 ] && [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; degraded=1; }
else
  seg="$cmd"; degraded=1
fi

re='^git[[:space:]]+worktree[[:space:]]+add([[:space:]]|$)'
[ "$degraded" = 1 ] && re='git[[:space:]]+worktree[[:space:]]+add([[:space:]]|$)'
# Line by line, in memory, with bash's own `=~`: no grep is needed to decide the scope.
hit=0
rest="$seg"$'\n'
while [ -n "$rest" ]; do
  line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
  if [[ $line =~ $re ]]; then hit=1; break; fi
done
# QUOTED WORDS (ae's review of #1596). The normaliser strips quoted spans, so `'git' worktree add`, `git 'worktree' add` and
# `git worktree "add"` normalise to something else and never matched. Test the raw text with its quotes and backslashes dropped
# too: a match there that the normaliser did not make goes to the helper as RAW, which reads the real tokens and lets a plain
# mention (`echo "git worktree add"`) through.
raw=0
if [ "$hit" = 0 ] && [ "$parsed" = 1 ]; then
  plain="${cmd//[\'\"\\]/}"
  if [[ $plain =~ (^|[^[:alnum:]_])git[[:space:]]([^\;\&\|]*[[:space:]])?worktree[[:space:]]+add([[:space:]]|$) ]]; then hit=1; raw=1; fi
fi
[ "$hit" = 1 ] || exit 0

deny() { echo "BLOCKED by rails-flow worktree guard: $1" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 \
  || deny "python3 is not available, so this \`git worktree add\` cannot be judged. Install python3, or create the worktree yourself outside the agent."
[ -f "$_py" ] || deny "the guard's helper is missing ($_py), so this \`git worktree add\` cannot be judged. Reinstall the rails-flow plugin."

flag=""; [ "$raw" = 1 ] && flag="--raw"
out="$(printf '%s' "$input" | python3 "$_py" check $flag 2>&1)"; rc=$?
case "$rc" in
  0) exit 0 ;;
  2) printf '%s\n' "$out" >&2; exit 2 ;;
  *) deny "the guard's helper failed (exit $rc), so this \`git worktree add\` cannot be judged: ${out:0:200}" ;;
esac
