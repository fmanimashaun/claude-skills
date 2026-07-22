#!/usr/bin/env bash
# SessionStart — surface the open-issue signal for a skills marketplace repo so the
# maintenance queue is visible. Read-only, non-blocking; fails OPEN (exit 0) whenever a
# dependency or precondition is missing — a status hook must never block a session.
set -uo pipefail

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
# Only speak in a skills/plugins marketplace repo.
[ -f .claude-plugin/marketplace.json ] || exit 0
# gh is optional here; without it, stay silent rather than erroring.
type -P gh >/dev/null 2>&1 || exit 0
gh auth status >/dev/null 2>&1 || exit 0

# gh has a built-in jq (-q), so no external jq/python3 needed for counts.
open="$(gh issue list --state open --limit 200 --json number -q 'length' 2>/dev/null || echo "")"
[ -n "$open" ] || exit 0
[ "$open" = "0" ] && { echo "- skill-maintainer: no open issues — tracker clear."; exit 0; }

p1="$(gh issue list --state open --label prio:P1 --limit 200 --json number -q 'length' 2>/dev/null || echo 0)"
doctrine="$(gh issue list --state open --label type:incorrect-doctrine --limit 200 --json number -q 'length' 2>/dev/null || echo 0)"

msg="- skill-maintainer: $open open issue(s)"
[ "${p1:-0}" != "0" ] && msg="$msg — ${p1} P1"
[ "${doctrine:-0}" != "0" ] && msg="$msg, ${doctrine} incorrect-doctrine"
echo "$msg. Run /skill-maintainer:triage to queue, /skill-maintainer:work to ship."
exit 0
