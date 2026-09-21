#!/usr/bin/env bash
# PreToolUse[Bash] — a PR body that makes numeric claims must have had them checked (#1106).
#
# WHY A HOOK AND NOT DOCTRINE. `claim-verifier` exists, works, covers "any number: counts, ratios,
# versions, timings", and is named in /maintainer-work. It was skipped for an entire working day
# without anyone noticing, and two wrong numbers reached merged PR bodies -- "292 assertions, up
# from 285" (it was 292 before AND after) and "ten times in this release's own bullets" (2 here, 8
# in older published entries). The capability was never the gap. Remembering to use it was.
#
# The only things that changed behaviour that day were the ones that ran without being remembered:
# the duplicate-unreleased rule, the ci-verdict rule, and guard-bash.sh. So this is a wall, not a
# checklist item.
#
# SCOPED TO ONE THING: `gh pr create` / `gh pr edit` carrying a body. It cannot misfire on ordinary
# work, which is what keeps a fail-closed guard from being switched off.
#
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
input="$(cat)"

cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

# Not a PR body command -- nothing to say. This is the common case and it must be silent.
printf '%s' "$cmd" | grep -qE '\bgh[[:space:]]+pr[[:space:]]+(create|edit)\b' || exit 0
printf '%s' "$cmd" | grep -qE '(--body-file|--body)\b' || exit 0

# The audited escape. A fail-closed guard with no visible way past it gets disabled the first time
# it is wrong about something, and then it protects nothing.
if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "1" ]; then
  echo "rails-flow: RAILS_FLOW_CLAIMS_OK=1 — claim check skipped (audited)." >&2
  exit 0
fi

body=""
if printf '%s' "$cmd" | grep -qE '\-\-body-file\b'; then
  body="$(printf '%s' "$cmd" | sed -nE 's/.*--body-file[[:space:]]+"?([^"[:space:]]+)"?.*/\1/p' | head -1)"
fi
# No readable body file (inline --body, a heredoc, a path we cannot resolve): say so and allow.
# FAILING OPEN HERE IS DELIBERATE -- this guard's job is to make the check happen when it can, not
# to become an obstacle to opening a PR. It is loud about what it could not read.
if [ -z "$body" ] || [ ! -r "$body" ]; then
  echo "rails-flow: could not read a --body-file to check claims; verify any numbers by hand." >&2
  exit 0
fi

extract="${CLAUDE_PLUGIN_ROOT:-}/scripts/extract_claims.py"
if [ ! -f "$extract" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "rails-flow: extract_claims.py or python3 unavailable — claims NOT checked." >&2
  exit 0
fi

# ---------------------------------------------------------------------------------------------
# THE CHANGE-TYPE DECLARATION (doctrine-map's one tracked gap).
#
# CLAUDE.md: "State which kind of change you are making, in the PR, before editing. Silence is not
# exemption." The doctrine map carried this as a GAP with its reason spelled out -- "mechanisable
# in principle ... but it would live in CI against the PR body, WHICH NO GATE IN THIS REPO READS."
# This hook reads the PR body, so that blocker is gone.
#
# Scoped to a PR that touches `skills/**`, because that is where the rule bites: skills are doctrine
# other people's agents follow verbatim, and a framework claim carried through unverified is the
# defect the whole gate exists for.
if git diff --name-only HEAD 2>/dev/null | grep -q '^skills/' || \
   git diff --name-only --cached HEAD 2>/dev/null | grep -q '^skills/'; then
  if ! grep -qiE 'framework claim|architecture decision|change type|our own (design|doctrine|architecture)' "$body"; then
    echo "BLOCKED by rails-flow claim guard: this PR touches skills/** and names no CHANGE TYPE." >&2
    echo "" >&2
    echo "Say which it is, in the body, before editing doctrine:" >&2
    echo "  * a FRAMEWORK CLAIM      -> needs a doctrine-verifier verdict and a citation" >&2
    echo "  * an ARCHITECTURE DECISION -> needs the maintainer's decision recorded on the issue" >&2
    echo "Silence is not exemption, and a mixed change must be split (CLAUDE.md, The gate)." >&2
    echo "Deliberately shipping without one: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
    exit 2
  fi
fi

claims="$(python3 "$extract" "$body" 2>/dev/null)" || exit 0
n="$(printf '%s' "$claims" | sed -nE 's/^([0-9]+) load-bearing claim.*/\1/p' | head -1)"
[ -n "${n:-}" ] && [ "$n" -gt 0 ] 2>/dev/null || exit 0

# A body that already shows its working is what we are asking for, so recognise it and stand aside.
if grep -qiE 'verified against|re-verified|measured [a-z]*[[:space:]]*(on|against)|CONFIRMED' "$body"; then
  exit 0
fi

echo "BLOCKED by rails-flow claim guard: this PR body makes ${n} load-bearing claim(s) and shows no evidence any were checked." >&2
echo "" >&2
printf '%s\n' "$claims" >&2
echo "" >&2
echo "Run each one down, then say so in the body — 'verified against <tag>', 'measured 2026-..-..', or CONFIRMED." >&2
echo "Two wrong numbers reached merged PR bodies the day this guard was written; both would have been caught here (#1106)." >&2
echo "Deliberately shipping an unchecked body: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
exit 2
