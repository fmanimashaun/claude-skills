#!/usr/bin/env bash
# Invoked by /pipeline:install-hooks. Installs the two git GUARDS (#1789): pre-push (a protected branch is only fast-forwarded) and
# pre-commit (the staged content is checked). Unlike the nudge, these REFUSE: a non-zero exit from the hook stops the push or the commit.
#
# A guard is installed as a WHOLE file, carrying a marker on its first comment line, so a re-run refreshes it. It is never merged into
# another tool's hook: a pre-push hook's stdin can be read once, and a block appended after someone else's code may never run. A hook of
# that name that is tracked by git, or that exists without our marker, is REFUSED (exit 1, with where it is) and left as it was.
set -uo pipefail

command -v git >/dev/null 2>&1 || { echo "git not found"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo"; exit 1; }

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src_dir="$here/../git-hooks"
[ -d "$src_dir" ] || { echo "cannot find the guard scripts at $src_dir"; exit 1; }

# Where git runs hooks from: honours core.hooksPath, and a linked worktree resolves to the common directory (see install-git-hooks.sh).
hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null)" || { echo "cannot resolve the hooks directory"; exit 1; }
mkdir -p "$hooks_dir" || { echo "cannot create $hooks_dir"; exit 1; }

# An untracked hook inside the working tree (core.hooksPath naming a committed directory) must stay out of `git status`.
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

status=0
for name in pre-push pre-commit; do
  src="$src_dir/$name"
  dest="$hooks_dir/$name"
  marker="# rails-flow-git-guard: $name"
  if ! grep -qF "$marker" "$src" 2>/dev/null; then
    echo "not installed: $src is missing or has no '$marker' line"
    status=1; continue
  fi
  if [ -e "$dest" ] && git ls-files --error-unmatch -- "$dest" >/dev/null 2>&1; then
    echo "not installed: $dest is tracked by git, so it is shared and not this installer's to edit."
    echo "  To opt in, add the guard to it yourself and commit it: $src"
    status=1; continue
  fi
  if [ -e "$dest" ] && ! grep -qF "$marker" "$dest" 2>/dev/null; then
    echo "not installed: $dest already exists and is not a rails-flow guard; a second hook cannot be chained safely."
    echo "  To opt in, call the guard from it yourself: $src"
    status=1; continue
  fi
  if [ -e "$dest" ] && cmp -s "$src" "$dest"; then
    verb="unchanged"
  elif [ -e "$dest" ]; then
    verb="updated"
  else
    verb="installed"
  fi
  cp "$src" "$dest" || { echo "cannot write $dest"; status=1; continue; }
  chmod +x "$dest" || { echo "cannot make $dest executable"; status=1; continue; }
  keep_local "$dest"
  echo "$verb: $dest"
done
exit "$status"
