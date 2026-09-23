#!/usr/bin/env bash
# Invoked by /pipeline:install-hooks. Writes LOCAL git hooks that NUDGE, never spend.
# Coexists with other tools' hooks: appends to an existing post-merge (idempotent
# marker guard) or backs up a non-managed one — never silently clobbers.
set -uo pipefail

command -v git >/dev/null 2>&1 || { echo "git not found"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo"; exit 1; }

# WHERE GIT RUNS HOOKS FROM, which is not always `.git/hooks`. `--git-path hooks` honours
# `core.hooksPath` — a repo that sets it runs hooks from that directory and never reads
# `.git/hooks` — and from a linked worktree it resolves to the common directory, not
# `.git/worktrees/<name>/hooks`, which git never reads either. `$(git rev-parse --git-dir)/hooks`
# was wrong in both cases and wrong silently: the hook installed, reported success, and never ran.
hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null)" || { echo "cannot resolve the hooks directory"; exit 1; }
mkdir -p "$hooks_dir" || { echo "cannot create $hooks_dir"; exit 1; }
hook="$hooks_dir/post-merge"

# #4: don't let a missing pipeline.yml abort under pipefail before the fallback.
dev_branch="dev"
if [ -f pipeline.yml ]; then
  v="$(grep -E '^dev_branch:' pipeline.yml 2>/dev/null | awk '{print $2}' || true)"
  [ -n "${v:-}" ] && dev_branch="$v"
fi

marker="# >>> pipeline-nudge >>>"
end_marker="# <<< pipeline-nudge <<<"

block="$(cat << HOOK
$marker
# pipeline nudge: a merge landed. If on the dev branch, QA verify is pending.
# Nudge-only — never invokes Claude, never spends tokens.
_pl_branch="\$(git branch --show-current 2>/dev/null)"
if [ "\$_pl_branch" = "$dev_branch" ]; then
  echo "QA verify pending on $dev_branch (\$(git rev-parse --short HEAD)) — run /qa-flow:verify or /pipeline" > "\$(git rev-parse --git-dir)/pipeline-pending"
  echo "[pipeline] $dev_branch updated — QA verify pending. Open Claude Code and run /pipeline."
fi
$end_marker
HOOK
)"

# A TRACKED hook belongs to the team, not to this nudge. `core.hooksPath` usually names a committed
# directory, and appending a local nudge to a committed hook dirties a shared file on every machine
# that runs this. Refuse, and print the block so a person can choose to add and commit it.
if [ -f "$hook" ] && git ls-files --error-unmatch -- "$hook" >/dev/null 2>&1; then
  echo "not installed: $hook is tracked by git, so it is shared and not this installer's to edit."
  echo "To opt in, add this block to it yourself and commit it:"
  printf '%s\n' "$block"
  exit 1
fi

# An untracked hook inside the working tree — `core.hooksPath` pointing at a committed directory —
# must stay out of `git status`, or a routine `git add` commits one machine's local nudge.
keep_local() {
  local path="$1" top abs excl
  top="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
  top="$(cd "$top" && pwd -P)"
  abs="$(cd "$(dirname "$path")" && pwd -P)/$(basename "$path")"
  case "$abs" in "$top"/*) ;; *) return 0 ;; esac
  excl="$(git rev-parse --git-path info/exclude)"
  mkdir -p "$(dirname "$excl")"
  grep -qxF "/${abs#"$top"/}" "$excl" 2>/dev/null || printf '/%s\n' "${abs#"$top"/}" >> "$excl"
}

if [ ! -f "$hook" ]; then
  { echo "#!/usr/bin/env bash"; echo; printf '%s\n' "$block"; } > "$hook"
  chmod +x "$hook"
  keep_local "$hook"
  echo "installed: $hook (new, nudge-only)"
elif grep -qF "$marker" "$hook"; then
  # idempotent: replace our managed block in place, leave the rest untouched
  tmp="$(mktemp "${TMPDIR:-/tmp}/pl-hook.XXXXXX")"
  awk -v m="$marker" -v e="$end_marker" '
    $0==m {skip=1} skip && $0==e {skip=0; next} !skip {print}
  ' "$hook" > "$tmp"
  { cat "$tmp"; printf '%s\n' "$block"; } > "$hook"
  rm -f "$tmp"; chmod +x "$hook"
  keep_local "$hook"
  echo "updated: $hook (refreshed pipeline-nudge block, other content preserved)"
else
  # existing NON-managed hook: back it up, then append our block (don't clobber)
  cp "$hook" "$hook.pre-pipeline.bak"
  printf '\n%s\n' "$block" >> "$hook"
  chmod +x "$hook"
  keep_local "$hook"; keep_local "$hook.pre-pipeline.bak"
  echo "appended to existing $hook (backup at $hook.pre-pipeline.bak)"
fi
