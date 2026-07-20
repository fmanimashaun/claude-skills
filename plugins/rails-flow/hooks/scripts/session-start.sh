#!/usr/bin/env bash
# SessionStart — inject repo state as context (stdout becomes context).
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

branch="$(git branch --show-current 2>/dev/null)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
last="$(git log -1 --oneline 2>/dev/null)"
base="main"; git show-ref --verify --quiet refs/heads/dev && base="dev"

echo "## rails-flow session context"
echo "- branch: ${branch:-detached} (base: $base) | uncommitted files: $dirty"
echo "- last commit: $last"
[ -f CLAUDE.md ] || echo "- NOTE: no CLAUDE.md — run /rails-flow:setup-flow to scaffold project conventions."
[ -f GUARDRAILS.md ] || echo "- NOTE: no GUARDRAILS.md — run /rails-flow:setup-flow."
if [ -f docs/brain/MEMORY.md ]; then
  echo "- memory index (docs/brain/MEMORY.md):"
  head -12 docs/brain/MEMORY.md | sed 's/^/  /'
fi
exit 0
