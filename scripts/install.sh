#!/usr/bin/env bash
# Install skills into a project (.claude/skills) or personally (~/.claude/skills).
#
# Usage:
#   ./scripts/install.sh /path/to/project           # all skills -> project
#   ./scripts/install.sh /path/to/project rails-8   # one skill  -> project
#   ./scripts/install.sh --global                   # all skills -> ~/.claude/skills
#   ./scripts/install.sh --global hotwire           # one skill  -> personal
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills" && pwd)"
TARGET="${1:-.}"

if [ "$TARGET" = "--global" ] || [ "$TARGET" = "-g" ]; then
  DEST="$HOME/.claude/skills"
else
  DEST="$(cd "$TARGET" && pwd)/.claude/skills"
fi
shift || true
ONLY=("$@")

mkdir -p "$DEST"
installed=0
for skill in "$SRC"/*/; do
  name="$(basename "$skill")"
  if [ "${#ONLY[@]}" -gt 0 ]; then
    case " ${ONLY[*]} " in *" $name "*) ;; *) continue ;; esac
  fi
  rm -rf "${DEST:?}/$name"
  cp -R "$skill" "$DEST/$name"
  echo "installed: $name -> $DEST/$name"
  installed=$((installed + 1))
done

[ "$installed" -gt 0 ] || { echo "no matching skills found in $SRC" >&2; exit 1; }
echo
echo "Done. If this skills directory didn't exist when your Claude Code session"
echo "started, restart Claude Code so it can be watched; otherwise changes are"
echo "picked up live. Verify inside Claude Code by asking: what skills are available?"
