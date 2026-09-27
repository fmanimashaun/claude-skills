#!/usr/bin/env bash
# PreToolUse[Bash] guardrails — mechanical enforcement of GUARDRAILS.md.
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
input="$(cat)"

cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

deny() { echo "BLOCKED by rails-flow guardrails: $1" >&2; exit 2; }

# MATCH THE INVOKED COMMAND, NOT ANY SUBSTRING (#906). The raw text blocked `grep -c "git add -A"
# GUARDRAILS.md`, `echo "never git add -A"` and a commit message quoting the rule, while
# `git -C repo add -A` slipped through. `seg` is one invoked segment per line, verb first, with
# quotes, comments and heredoc bodies stripped and env/sudo/git-global-option prefixes peeled.
# FAIL CLOSED: if the lib cannot be sourced, match the raw text as before — a guard that goes
# quiet because a file is missing is the one failure this hook must not have.
_lib="$(dirname "${BASH_SOURCE[0]}")/lib/normalize_cmd.sh"
if [ -f "$_lib" ] && . "$_lib" 2>/dev/null && type normalize_segments >/dev/null 2>&1; then
  seg="$(printf '%s' "$cmd" | normalize_segments)"
else
  seg="$cmd"
fi
hit() { printf '%s\n' "$seg" | grep -qE "$1"; }

# A rails/rake task segment that names db:reset (not the word inside a quoted string or a grep).
if hit '^(bin/)?(rails|rake)([[:space:]]+[^[:space:]]+)*[[:space:]]+db:reset\b'; then
  deny "db:reset is prohibited (seeds break test isolation). Use: db:drop db:create db:schema:load."
fi

if hit '^git[[:space:]]+push\b.*(--force\b|[[:space:]]-f\b)' && ! hit '^git[[:space:]]+push\b.*--force-with-lease'; then
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
   && ! hit '^git[[:space:]]+clean\b.*([[:space:]]-[a-zA-Z]*n|[[:space:]]--dry-run\b)'; then
  deny "git clean -f deletes untracked files with no undo. Run 'git clean -n' first and show the user what it would remove; delete named paths with approval."
fi
if hit '^git[[:space:]]+checkout\b.*[[:space:]]--([[:space:]]|$)' \
   || hit '^git[[:space:]]+checkout([[:space:]]+-[a-zA-Z-]+)*[[:space:]]+(\./?|:/)($|[[:space:]])'; then
  deny "git checkout -- <path> / git checkout . overwrites uncommitted edits with no undo. To keep them: git stash push -m <why> -- <path>. To discard ONE file you own: git restore -- <that path>."
fi
if hit '^git[[:space:]]+restore\b.*[[:space:]](\./?|:/|\*)($|[[:space:]])' \
   && ! hit '^git[[:space:]]+restore\b.*--staged\b' ; then
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
if hit '^gh[[:space:]]+issue[[:space:]]+create\b'; then
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
