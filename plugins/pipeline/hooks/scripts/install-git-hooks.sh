#!/usr/bin/env bash
# Invoked by /pipeline:install-hooks. Writes LOCAL git hooks that NUDGE, never spend.
# Coexists with other tools' hooks: appends to an existing post-merge (idempotent
# marker guard) or backs up a non-managed one — never silently clobbers.
set -uo pipefail

command -v git >/dev/null 2>&1 || { echo "git not found"; exit 1; }
gitdir="$(git rev-parse --git-dir 2>/dev/null)" || { echo "not a git repo"; exit 1; }

# #4: don't let a missing pipeline.yml abort under pipefail before the fallback.
dev_branch="dev"
if [ -f pipeline.yml ]; then
  v="$(grep -E '^dev_branch:' pipeline.yml 2>/dev/null | awk '{print $2}' || true)"
  [ -n "${v:-}" ] && dev_branch="$v"
fi

hook="$gitdir/hooks/post-merge"
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

if [ ! -f "$hook" ]; then
  { echo "#!/usr/bin/env bash"; echo; printf '%s\n' "$block"; } > "$hook"
  chmod +x "$hook"
  echo "installed: $hook (new, nudge-only)"
elif grep -qF "$marker" "$hook"; then
  # idempotent: replace our managed block in place, leave the rest untouched
  tmp="$(mktemp "${TMPDIR:-/tmp}/pl-hook.XXXXXX")"
  awk -v m="$marker" -v e="$end_marker" '
    $0==m {skip=1} skip && $0==e {skip=0; next} !skip {print}
  ' "$hook" > "$tmp"
  { cat "$tmp"; printf '%s\n' "$block"; } > "$hook"
  rm -f "$tmp"; chmod +x "$hook"
  echo "updated: $hook (refreshed pipeline-nudge block, other content preserved)"
else
  # existing NON-managed hook: back it up, then append our block (don't clobber)
  cp "$hook" "$hook.pre-pipeline.bak"
  printf '\n%s\n' "$block" >> "$hook"
  chmod +x "$hook"
  echo "appended to existing $hook (backup at $hook.pre-pipeline.bak)"
fi
