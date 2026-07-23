#!/usr/bin/env bash
# SessionStart — surface a pending-stage nudge left by a git hook, and the lifecycle
# position. Read-only; never spends tokens or invokes anything.
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
type -P python3 >/dev/null 2>&1 || exit 0   # no python3 → skip (non-blocking status only)
[ -f pipeline.yml ] || exit 0

# worktree-safe: read from the same git-dir the post-merge hook writes to.
pending="$(git rev-parse --git-dir 2>/dev/null)/pipeline-pending"
if [ -f "$pending" ]; then
  echo "- pipeline: $(head -c 200 "$pending" 2>/dev/null)"
  echo "  (/pipeline to advance · /pipeline:status for detail · /pipeline:ack to dismiss — e.g. a docs-only merge with nothing to verify)"
fi

branch="$(git branch --show-current 2>/dev/null)"
if [ -f qa/CERTIFICATION ]; then
  csha="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("sha","")[:12])' 2>/dev/null || true)"
  devsha="$(git rev-parse origin/dev 2>/dev/null | cut -c1-12 || true)"
  [ -n "$devsha" ] && [ "$csha" = "$devsha" ] && echo "- pipeline: dev ($devsha) certified — /pipeline:release to build the image."
fi
exit 0
