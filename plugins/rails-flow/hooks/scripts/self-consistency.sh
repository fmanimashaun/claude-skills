#!/usr/bin/env bash
# PostToolUse[Edit|Write|MultiEdit] — does the edited file do what it claims?
#
# Ordinary linting asks "is this code correct?". This asks the question authors are
# blind to: does the file honour its own comments, config and project rules? See
# the `code-review` skill (bundled in rails-stack) for the full class list.
#
# Exit 2 on findings, deliberately. A check that can only advise is itself a
# `gate-that-cannot-fail` — one of the classes this enforces — so it has to be
# able to fail. Fails OPEN on a missing dependency (no python3): a guard decides
# whether to RUN a check, it must never soften the verdict.
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"

# Only the file types the per-file rules actually cover. Anything else exits 0
# rather than pretending to have checked it.
case "$file" in
  *.rb|*.erb|*.rake|*.sh|*.bash|*.yml|*.yaml) : ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

script="${CLAUDE_PLUGIN_ROOT}/scripts/self_consistency.py"
[ -f "$script" ] || exit 0

out="$(python3 "$script" --file "$file" 2>&1)"
status=$?

if [ "$status" -eq 1 ]; then
  echo "self-consistency findings in $file — the code does not do what it claims:" >&2
  printf '%s\n' "$out" >&2
  echo "" >&2
  echo "Fix the code, or fix the claim — decide which is wrong. See the code-review skill." >&2
  exit 2
fi

exit 0
