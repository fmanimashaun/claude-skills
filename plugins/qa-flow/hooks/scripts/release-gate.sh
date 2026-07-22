#!/usr/bin/env bash
# PreToolUse[Bash] — block dev->main promotion unless QA certified the exact dev sha.
# Independent of rails-flow's guard; both can run. Exit 2 blocks with a reason.
set -uo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# Is this command promoting to main/master?
targets_main=0
printf '%s' "$cmd" | grep -qE 'git\s+push\b.*\b(origin\s+)?(HEAD:)?(main|master)\b' && targets_main=1
printf '%s' "$cmd" | grep -qE 'git\s+merge\b' && git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && targets_main=1
if printf '%s' "$cmd" | grep -qE 'gh\s+pr\s+merge\b'; then
  num="$(printf '%s' "$cmd" | grep -oE '[0-9]+' | head -1)"
  base="$(gh pr view "$num" --json baseRefName -q .baseRefName 2>/dev/null || true)"
  [ "$base" = "main" ] || [ "$base" = "master" ] && targets_main=1
fi
[ "$targets_main" -eq 1 ] || exit 0

deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }
[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override — promotion allowed without a fresh stamp (audited)." >&2; exit 0; }

stamp="qa/CERTIFICATION"
[ -f "$stamp" ] || deny "no certification found. Run /qa-flow:certify against staging first."

verdict="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("verdict",""))' 2>/dev/null || true)"
csha="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("sha",""))' 2>/dev/null || true)"
[ "$verdict" = "PASS" ] || deny "certification verdict is not PASS. Re-certify."

devsha="$(git rev-parse origin/dev 2>/dev/null || git rev-parse dev 2>/dev/null || true)"
if [ -n "$devsha" ] && [ -n "$csha" ]; then
  case "$devsha" in
    "$csha"*) : ;;
    *) deny "certification is for sha ${csha:0:12}, but dev is at ${devsha:0:12}. dev moved — re-certify before promoting." ;;
  esac
fi
echo "qa-flow: certification valid for ${csha:0:12} — promotion permitted." >&2
exit 0
