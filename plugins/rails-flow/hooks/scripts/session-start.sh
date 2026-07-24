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
if [ -f docs/brain/STATUS.md ]; then
  echo "- brain STATUS (docs/brain/STATUS.md, top):"
  head -8 docs/brain/STATUS.md | sed 's/^/  /'
fi
if [ -f docs/brain/MEMORY.md ]; then
  echo "- memory index (docs/brain/MEMORY.md):"
  head -12 docs/brain/MEMORY.md | sed 's/^/  /'
fi

# brain-review cadence nudge (local, offline). /rails-flow:brain-review stamps an epoch into
# docs/brain/.last-review; if the last sweep is older than the cadence (default 7d, override
# RAILS_FLOW_BRAIN_REVIEW_DAYS), remind. Reminder only — never auto-runs. Fails open.
if [ -f docs/brain/STATUS.md ]; then
  _days="${RAILS_FLOW_BRAIN_REVIEW_DAYS:-7}"
  if [ -f docs/brain/.last-review ]; then
    _ts="$(tr -dc 0-9 < docs/brain/.last-review 2>/dev/null)"
    if [ -n "$_ts" ]; then
      _age=$(( ( $(date +%s) - _ts ) / 86400 ))
      [ "$_age" -ge "$_days" ] && echo "- brain-review due: last swept ${_age}d ago (cadence ${_days}d) — run /rails-flow:brain-review"
    fi
  else
    echo "- brain-review: no sweep on record — run /rails-flow:brain-review to start the maintenance cadence"
  fi
fi

if [ -f .claude/skills/.manifest.tsv ]; then
  stale=0
  while IFS="$(printf '\t')" read -r src hash; do
    [ -n "$src" ] && [ -f "$src" ] || continue
    cur="$(sha256sum "$src" 2>/dev/null | cut -c1-12)"
    [ -n "$cur" ] && [ "$cur" != "$hash" ] && stale=$((stale+1))
  done < .claude/skills/.manifest.tsv
  [ "$stale" -gt 0 ] && echo "- $stale curated doc(s) drifted from their project skills — run /rails-flow:curate"
fi

exit 0
