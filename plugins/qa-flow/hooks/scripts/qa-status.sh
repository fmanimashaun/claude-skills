#!/usr/bin/env bash
# SessionStart — surface certification status vs current dev so staleness is visible.
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
type -P python3 >/dev/null 2>&1 || exit 0   # no python3 → skip (non-blocking status only)
[ -f qa/CERTIFICATION ] || { [ -d qa ] && echo "- qa-flow: no certification yet — /qa-flow:certify before dev->main."; exit 0; }
# #721. Same one reader as release-gate.sh. This banner said "certification stale" forever on a
# non-conforming stamp, which is permanent false-negative noise -- and an advisory nobody can clear
# is an advisory people learn to ignore.
reader="${CLAUDE_PLUGIN_ROOT:-}/scripts/read_certification.py"
csha="$(python3 "$reader" --field sha 2>/dev/null || true)"
csha="${csha:0:12}"
verdict="$(python3 "$reader" --field verdict 2>/dev/null || true)"
if [ -z "$verdict" ]; then
  # Say what is actually wrong instead of implying the stamp is merely out of date.
  why="$(python3 "$reader" --field verdict --explain 2>/dev/null || true)"
  [ -n "$why" ] && echo "- qa-flow: $why"
  exit 0
fi
devsha="$(git rev-parse origin/dev 2>/dev/null | cut -c1-12 || true)"
if [ -n "$devsha" ] && [ "$csha" = "$devsha" ] && [ "$verdict" = "PASS" ]; then
  echo "- qa-flow: dev ($devsha) is CERTIFIED — cleared for main."
else
  echo "- qa-flow: certification stale (stamped ${csha:-none}, dev ${devsha:-?}) — re-run /qa-flow:certify before promoting."
fi
exit 0
