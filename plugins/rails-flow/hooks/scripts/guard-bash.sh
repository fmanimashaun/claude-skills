#!/usr/bin/env bash
# PreToolUse[Bash] guardrails — mechanical enforcement of GUARDRAILS.md.
# Exit 2 blocks the command; stderr is shown to Claude with the reason.
set -uo pipefail
input="$(cat)"

cmd="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || printf '%s' "$input")"

deny() { echo "BLOCKED by rails-flow guardrails: $1" >&2; exit 2; }

case "$cmd" in
  *db:reset*)
    deny "db:reset is prohibited (seeds break test isolation). Use: db:drop db:create db:schema:load." ;;
esac

if printf '%s' "$cmd" | grep -qE 'git\s+push\b.*(--force|\s-f\b)' && \
   ! printf '%s' "$cmd" | grep -q -- '--force-with-lease'; then
  deny "force-push is prohibited. Use --force-with-lease on your own feature branch only, never on main/dev/staging."
fi
if printf '%s' "$cmd" | grep -qE -- '--force-with-lease' && \
   printf '%s' "$cmd" | grep -qE '\b(main|master|dev|staging)\b'; then
  deny "force-pushing a protected branch (main/dev/staging) requires explicit user approval."
fi

if printf '%s' "$cmd" | grep -qE 'git\s+add\s+(-A\b|--all\b|\.($|\s))'; then
  deny "stage specific files, never 'git add -A' / 'git add .' (GUARDRAILS: no accidental secrets or stray files)."
fi

case "$cmd" in
  *--no-verify*)
    deny "--no-verify skips pre-commit checks and is prohibited." ;;
esac

if printf '%s' "$cmd" | grep -qE 'git\s+reset\s+--hard'; then
  deny "git reset --hard requires explicit user approval (uncommitted work loss)."
fi

if printf '%s' "$cmd" | grep -qE '\bkamal\s+deploy\b' && [ "${RAILS_FLOW_ALLOW_DEPLOY:-0}" != "1" ]; then
  deny "production deploys require explicit user approval. Ask the user; on approval rerun with RAILS_FLOW_ALLOW_DEPLOY=1 kamal deploy ..."
fi

exit 0
