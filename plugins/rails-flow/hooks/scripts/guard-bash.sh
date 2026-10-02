#!/usr/bin/env bash
# PreToolUse[Bash] guardrails — mechanical enforcement of GUARDRAILS.md.
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
# The `read` BUILTIN, never `cat`: with no `cat` on PATH, `$(cat)` read nothing and every rule passed
# (#1529 review). Stops at a NUL, which JSON cannot contain.
input=""; IFS= read -r -d '' input || true

# #1526: decoded with `surrogateescape`, so an invalid UTF-8 byte cannot make the parse fail. A failed
# parse left the raw JSON as `cmd`, where the command sits inside double quotes the normaliser strips:
# `git add -A \xff` was allowed.
parsed=1
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
d=json.loads(sys.stdin.buffer.read().decode("utf-8","surrogateescape"))
sys.stdout.buffer.write(str(d.get("tool_input",{}).get("command","")).encode("utf-8","replace"))' 2>/dev/null)" || { parsed=0; cmd="$input"; }

deny() { echo "BLOCKED by rails-flow guardrails: $1" >&2; exit 2; }

# MATCH THE INVOKED COMMAND, NOT ANY SUBSTRING (#906). The raw text blocked `grep -c "git add -A"
# GUARDRAILS.md`, `echo "never git add -A"` and a commit message quoting the rule, while
# `git -C repo add -A` slipped through. `seg` is one invoked segment per line, verb first, with
# quotes, comments and heredoc bodies stripped and env/sudo/git-global-option prefixes peeled.
# FAIL CLOSED: if the lib cannot be sourced, match the raw text as before — a guard that goes
# quiet because a file is missing is the one failure this hook must not have.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib/normalize_cmd.sh"
#
# #1526: the lib needs awk, sed, tr and grep. Without awk it printed NOTHING, so every rule passed. An
# unparsed payload, a missing lib, or a normaliser that EXITED NON-ZERO puts the hook in DEGRADED mode.
# The exit status, not an empty result, decides: a comment-only command normalises to nothing and is a
# mention (#906). A missing tool needs no check of its own -- the shell's 127 fails the pipeline under
# `pipefail` and the lib returns it (#1529 review) -- and a `command -v` per tool changed no outcome,
# which the mutation guard measured. `LC_ALL=C`: macOS awk aborts on an invalid byte in a UTF-8 locale.
degraded=0
if [ "$parsed" = 1 ] && [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | LC_ALL=C normalize_segments)" || { seg="$cmd"; degraded=1; }
else
  seg="$cmd"; degraded=1
fi
# DEGRADED MEANS UNANCHORED (#1529 review). Every rule is anchored `^git`, and the raw text is the
# JSON payload or a compound command (`cd x && git add -A`), so an anchored rule never matched it and
# "fall back to the raw text" passed everything. In degraded mode a rule matches ANYWHERE: that refuses
# a quoted mention too, which is the right side to err on when the command could not be read. With no
# grep at all, bash's own `=~` matches (`\b` dropped, which only widens the match).
have_grep=0; command -v grep >/dev/null 2>&1 && have_grep=1
hit() {
  local re="$1"
  [ "$degraded" = 1 ] && re="${re#^}"
  if [ "$have_grep" = 1 ]; then
    printf '%s\n' "$seg" | grep -qE "$re"
  else
    re="${re//\\b/}"
    [[ $seg =~ $re ]]
  fi
}
# An EXEMPTION (`--force-with-lease`, clean's `-n`, restore's `--staged`) never applies in degraded
# mode: unanchored, its `.*` reaches another segment, so `git clean -fd && echo -n` was exempt (#1529
# review). Refusing a real dry run there is the price of a command that could not be read.
exempt() { [ "$degraded" = 1 ] && return 1; hit "$1"; }

# A rails/rake task segment that names db:reset (not the word inside a quoted string or a grep).
if hit '^(bin/)?(rails|rake)([[:space:]]+[^[:space:]]+)*[[:space:]]+db:reset\b'; then
  deny "db:reset is prohibited (seeds break test isolation). Use: db:drop db:create db:schema:load."
fi

if hit '^git[[:space:]]+push\b.*(--force\b|[[:space:]]-f\b)' && ! exempt '^git[[:space:]]+push\b.*--force-with-lease'; then
  deny "force-push is prohibited. Use --force-with-lease on your own feature branch only, never on main/dev/staging."
fi
if hit '^git[[:space:]]+push\b.*--force-with-lease' && hit '^git[[:space:]]+push\b.*\b(main|master|dev|staging)\b'; then
  deny "force-pushing a protected branch (main/dev/staging) requires explicit user approval."
fi

# Leading short flags are allowed through (`-v -A`), `-A` may sit inside a bundle (`-vA`), and the
# repo-root spellings `./` and `:/` count as `.` (#826). Verb at the START of a segment (#906).
if hit '^git[[:space:]]+add([[:space:]]+-[a-zA-Z]+)*[[:space:]]+(-[a-zA-Z]*A[a-zA-Z]*\b|--all\b|\./?($|[[:space:]])|:/($|[[:space:]]))'; then
  deny "stage specific files, never 'git add -A' / 'git add .' (GUARDRAILS: no accidental secrets or stray files)."
fi

# `--no-verify` as a flag of a git commit/push/merge segment — not the words in an echo or a doc edit.
if hit '^git[[:space:]]+(commit|push|merge|rebase|cherry-pick)\b.*[[:space:]]--no-verify\b'; then
  deny "--no-verify skips pre-commit checks and is prohibited."
fi

if hit '^git[[:space:]]+reset[[:space:]]+--hard\b'; then
  deny "git reset --hard requires explicit user approval (uncommitted work loss)."
fi

# #1342. The other ways git throws away work with no undo. Each keeps a safe twin allowed:
# `clean -n` (dry run), `branch -d` (refuses an unmerged branch), `checkout <branch>`,
# `restore --staged` (unstage only) and `restore -- <explicit path>` (one named file, on purpose).
if hit '^git[[:space:]]+clean\b.*([[:space:]]-[a-zA-Z]*f|[[:space:]]--force\b)' \
   && ! exempt '^git[[:space:]]+clean\b.*([[:space:]]-[a-zA-Z]*n|[[:space:]]--dry-run\b)'; then
  deny "git clean -f deletes untracked files with no undo. Run 'git clean -n' first and show the user what it would remove; delete named paths with approval."
fi
if hit '^git[[:space:]]+checkout\b.*[[:space:]]--([[:space:]]|$)' \
   || hit '^git[[:space:]]+checkout([[:space:]]+-[a-zA-Z-]+)*[[:space:]]+(\./?|:/)($|[[:space:]])'; then
  deny "git checkout -- <path> / git checkout . overwrites uncommitted edits with no undo. To keep them: git stash push -m <why> -- <path>. To discard ONE file you own: git restore -- <that path>."
fi
if hit '^git[[:space:]]+restore\b.*[[:space:]](\./?|:/|\*)($|[[:space:]])' \
   && ! exempt '^git[[:space:]]+restore\b.*--staged\b' ; then
  deny "git restore . discards every uncommitted edit in the tree. Name the one file you mean: git restore -- <path>."
fi
if hit '^git[[:space:]]+branch\b.*[[:space:]](-[a-zA-Z]*D\b|--delete[[:space:]]+--force\b|--force[[:space:]]+--delete\b)'; then
  deny "git branch -D deletes an unmerged branch. Use 'git branch -d' (refuses unmerged work), or ask the user."
fi
if hit '^git[[:space:]]+stash[[:space:]]+(drop|clear)\b'; then
  deny "git stash drop/clear is refused: the stash stack is shared by every session in this repository, so the top entry may not be yours. Ask the user."
fi

# An issue filed from the shell skips the templates that apply labels, so it is labelled HERE or
# never (#1311). The raw command goes to the helper, because a label value is usually quoted and the
# normalised `seg` strips quotes. FAIL CLOSED: a helper that cannot run blocks the command.
# Called whenever the text names a create ANYWHERE (#1423): a create in `sh -c`, `eval`, backticks
# or behind `/usr/bin/gh` never starts a normalised segment, so a segment match alone never saw it.
# The helper tells a command from a mention (`echo "gh issue create"` stays allowed).
# Quotes, backslashes and newlines are dropped for this TRIGGER only (#1462): `gh issue "create"`,
# `gh issue \<newline>create` and `gh --repo o/r issue create` must reach the helper, which parses
# the raw command properly and tells a create from a mention.
# A shell reading a script by redirect (`bash < file`, #1489) names no create in its text at all, so it
# triggers the helper too; the helper reads the file and decides. Coarse on purpose -- `/bin/bash < f`,
# `bash --norc < f`, `bash -o errexit < f`, `sh<f`, `bash 0< f` -- because over-triggering costs one
# parse, and under-triggering skips the check.
if printf '%s' "$cmd" | tr -d "\"'\\\\" | tr '\n' ' ' | grep -qE 'gh[[:space:]].*issue[[:space:]]+(create|new)' \
   || printf '%s' "$cmd" | grep -qE '(^|[[:space:];&|(/])(sh|bash|zsh|dash|ksh)([[:space:]][^;&|]*)?<([^<(]|$)'; then
  _root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  _why="$(printf '%s' "$cmd" | python3 "$(dirname "${BASH_SOURCE[0]}")/lib/issue_labels.py" --root "$_root" 2>&1)"
  _rc=$?
  if [ "$_rc" -eq 1 ]; then
    deny "$_why"
  elif [ "$_rc" -ne 0 ]; then
    deny "the issue-label check could not run (exit $_rc), so this gh issue create is refused rather than let through unlabelled."
  fi
fi

if hit '^kamal[[:space:]]+deploy\b' && [ "${RAILS_FLOW_ALLOW_DEPLOY:-0}" != "1" ]; then
  deny "production deploys require explicit user approval. Ask the user; on approval rerun with RAILS_FLOW_ALLOW_DEPLOY=1 kamal deploy ..."
fi

exit 0
