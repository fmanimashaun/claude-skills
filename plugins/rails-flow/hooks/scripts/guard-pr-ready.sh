#!/usr/bin/env bash
# PreToolUse[Bash] — refuse `gh pr ready` unless a GREEN sweep with zero skips is recorded for HEAD. #1565
#
# WHY. "Mark a PR ready only after a green sweep" was prose: measured on #1565, every PreToolUse hook let
# `gh pr ready` through after a red sweep, after a skipped one, and with no sweep at all. This hook decides
# on a RECORDED EFFECT, not on command text (the coordinator's decision on #1565, epic #1793):
# `scripts/project_gates.py` writes `<git dir>/rails-flow/sweep/<HEAD sha>.json` after a run from a clean
# worktree, and `lib/pr_ready_guard.py` lets `gh pr ready` through only when that record exists for the
# current HEAD with verdict green and skips 0. A missing, red, stale (other-HEAD) or skipped record refuses,
# and the message names the sweep command to run.
#
# THE TWO-COMMAND RULE. Chains are NOT parsed. `<sweep> && gh pr ready` in ONE command is judged before the
# sweep in it has run, so it is refused unless a green record already exists. Run the sweep, then
# `gh pr ready`, as two separate commands.
#
# SCOPE. Silent (exit 0) for every command that does not invoke `gh pr ready`, and for `gh pr ready --undo`
# (the safe direction). NOT APPLICABLE, and passes, where the target repository does not run project_gates:
# in force only when a `.github/workflows/*.yml` names `project_gates.py`, `CLAUDE.md` carries the
# `<!-- rails-flow:begin` managed marker, or a `rails-flow/sweep` directory exists under the git dir.
# Outside a git repository: exit 0.
#
# FAILS CLOSED, SCOPED. Exit 2 blocks. When it is in force and the record is unreadable or malformed, or
# when python3 or the helper is missing for a `gh pr ready`, the command is refused with the reason. The
# match uses the shared normaliser (lib/normalize_cmd.sh), so `cd x && gh pr ready` is seen and
# `echo "gh pr ready"` is not; when the normaliser cannot run, the match is unanchored.
#
# WHAT IT DOES NOT CATCH, STATED. No network: `gh pr ready <n>` is judged by the HEAD of the checkout the
# command runs in (lib/command_cwd.py follows its own `cd`s), so a PR whose head is not checked out there
# is refused unless that HEAD was swept, and a PR whose head differs from a swept local HEAD is not told
# apart. When the command's directory cannot be told, it is refused only if the session's repository is in
# force. A remote-targeted `gh pr ready` (-R/--repo/GH_REPO/a PR URL) is refused when the command's or the session's repo is
# in force, and passes from a session and directory where neither repo is in force. A record can be hand-written; the guard protects against accident, not forgery. `gh api` calls
# that mark a PR ready, and a `gh` reached through a variable, alias or function, are out of reach.
set -uo pipefail
input=""; IFS= read -r -d '' input || true

parsed=1
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
d=json.loads(sys.stdin.buffer.read().decode("utf-8","surrogateescape"))
sys.stdout.buffer.write(str(d.get("tool_input",{}).get("command","")).encode("utf-8","replace"))' 2>/dev/null)" || { parsed=0; cmd="$input"; }

_dir="${BASH_SOURCE[0]%/*}"
_lib="$_dir/lib/normalize_cmd.sh"
_py="$_dir/lib/pr_ready_guard.py"

degraded=0
if [ "$parsed" = 1 ] && [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; degraded=1; }
else
  seg="$cmd"; degraded=1
fi

# gh by name or by path, then any global flags (`-R o/r`, `--repo o/r`, `--repo=o/r`), `pr`, any flags again, `ready`. The anchored
# `^gh pr ready` missed `gh -R o/r pr ready` and `/usr/local/bin/gh pr ready` (security review of #1565).
_f='([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*'
re="^([^[:space:]]*/)?gh${_f}[[:space:]]+pr${_f}[[:space:]]+ready([[:space:]]|\$)"
[ "$degraded" = 1 ] && re="(^|[[:space:]])([^[:space:]]*/)?gh${_f}[[:space:]]+pr${_f}[[:space:]]+ready([[:space:]]|\$)"
hit=0; args=""; segment=""
rest="$seg"$'\n'
while [ -n "$rest" ]; do
  line="${rest%%$'\n'*}"; rest="${rest#*$'\n'}"
  if [[ $line =~ $re ]]; then
    m="${BASH_REMATCH[0]}"; a="${line#*"$m"}"; a=" ${a}"
    [[ " $a " =~ [[:space:]]--undo[[:space:]] ]] && continue
    hit=1; args="$a"; segment="$line"; break
  fi
done
[ "$hit" = 1 ] || exit 0

deny() { echo "BLOCKED by rails-flow pr-ready guard: $1" >&2; echo "Then run, as two commands: python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/project_gates.py\"  and  gh pr ready$args" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 \
  || deny "python3 is not available, so the sweep record for HEAD cannot be read."
[ -f "$_py" ] || deny "the guard's helper is missing ($_py). Reinstall the rails-flow plugin."

out="$(printf '%s' "$input" | python3 "$_py" "$args" "$segment" 2>&1)"; rc=$?
case "$rc" in
  0) exit 0 ;;
  2) printf '%s\n' "$out" >&2; exit 2 ;;
  *) deny "the guard's helper failed (exit $rc): ${out:0:200}" ;;
esac
