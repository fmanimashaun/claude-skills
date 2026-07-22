#!/usr/bin/env bash
# PreToolUse[Bash] — block dev->main promotion unless QA certified the exact dev sha.
# Independent of rails-flow's guard; both can run. Exit 2 blocks with a reason.
set -uo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# Detect promotion to main/master.
targets_main=0
printf '%s' "$cmd" | grep -qE 'git\s+push\b.*\b(origin\s+)?(HEAD:)?(main|master)\b' && targets_main=1
printf '%s' "$cmd" | grep -qE 'git\s+merge\b' && git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$' && targets_main=1
# gh pr merge: base is the PR's target. #3: handle explicit number AND bare (current branch).
if printf '%s' "$cmd" | grep -qE 'gh\s+pr\s+merge\b'; then
  # a bare integer arg that isn't a flag value = PR number; else current branch's PR
  num="$(printf '%s' "$cmd" | grep -oE '(^|[[:space:]])[0-9]+([[:space:]]|$)' | tr -d ' ' | head -1)"
  if [ -n "$num" ]; then
    base="$(gh pr view "$num" --json baseRefName -q .baseRefName 2>/dev/null || true)"
  else
    base="$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || true)"
  fi
  case "$base" in main|master) targets_main=1 ;; esac
  # If we couldn't resolve the base at all on a merge command, fail safe: treat as promotion.
  [ -z "$base" ] && targets_main=1
fi
[ "$targets_main" -eq 1 ] || exit 0

deny() { echo "BLOCKED by qa-flow release gate: $1" >&2; exit 2; }
[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override — promotion allowed without a fresh stamp (audited)." >&2; exit 0; }

stamp="qa/CERTIFICATION"
[ -f "$stamp" ] || deny "no certification found. Run /qa-flow:certify against staging first."

verdict="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("verdict",""))' 2>/dev/null || true)"
csha="$(python3 -c 'import json;print(json.load(open("qa/CERTIFICATION")).get("sha",""))' 2>/dev/null || true)"
[ "$verdict" = "PASS" ] || deny "certification verdict is not PASS. Re-certify."
# #2: the sha binding IS the gate — empty/garbled sha must fail closed, not pass on PASS alone.
[ -n "$csha" ] || deny "certification has no sha — the stamp is invalid. Re-run /qa-flow:certify."

devsha="$(git rev-parse origin/dev 2>/dev/null || git rev-parse dev 2>/dev/null || true)"
if [ -n "$devsha" ]; then
  case "$devsha" in
    "$csha"*) : ;;
    *) deny "certification is for sha ${csha:0:12}, but dev is at ${devsha:0:12}. dev moved — re-certify before promoting." ;;
  esac
else
  deny "cannot resolve dev sha to compare against the certification. Fetch dev and retry."
fi
echo "qa-flow: certification valid for ${csha:0:12} — promotion permitted." >&2
exit 0
