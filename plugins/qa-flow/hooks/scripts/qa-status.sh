#!/usr/bin/env bash
# SessionStart — surface certification status vs current dev so staleness is visible.
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -f qa/CERTIFICATION ] || { [ -d qa ] && echo "- qa-flow: no certification yet — /qa-flow:certify before dev->main."; exit 0; }
csha="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("sha","")[:12])' 2>/dev/null || true)"
verdict="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("verdict",""))' 2>/dev/null || true)"
devsha="$(git rev-parse origin/dev 2>/dev/null | cut -c1-12 || true)"
if [ -n "$devsha" ] && [ "$csha" = "$devsha" ] && [ "$verdict" = "PASS" ]; then
  echo "- qa-flow: dev ($devsha) is CERTIFIED — cleared for main."
else
  echo "- qa-flow: certification stale (stamped ${csha:-none}, dev ${devsha:-?}) — re-run /qa-flow:certify before promoting."
fi
exit 0
