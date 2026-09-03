#!/usr/bin/env bash
# PostToolUse[Edit|Write|MultiEdit] — flag LLM design tells in the file just written (#157).
#
# ADVISORY, therefore FAIL OPEN. Applying the guarantee-vs-advice test in docs/doctrine/harness-doctrine.md
# ("if a model ignores this, what happens?"): the answer is a view carries `text-gray-500` until
# `/design-flow:audit` or a reviewer catches it. That is drift, not a broken guarantee, and an
# advisory that blocks work when python3 is absent is an advisory people switch off. Every early
# exit below is therefore `exit 0`.
#
# Findings go to stderr with exit 2, which surfaces them to the model without failing the edit —
# the same shape as lint-ruby.sh.
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' \
  2>/dev/null || true)"

# View and component surfaces only. A model edits plenty of Ruby that has no markup in it, and
# running there would be noise rather than signal.
case "$file" in
  *.erb|*.html|*.css|*.slim|*.haml|*.jsx|*.tsx|*.vue) : ;;
  *_component.rb|*/components/*.rb) : ;;
  *) exit 0 ;;
esac

[ -f "$file" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

detector="${CLAUDE_PLUGIN_ROOT:-}/scripts/llm_tell_detector.py"
[ -f "$detector" ] || exit 0

out="$(python3 "$detector" --quiet "$file" 2>/dev/null)"
status=$?

# 2 is the detector's "unusable" — a bad path or a broken import. That is our problem, not the
# user's edit, so it stays silent here rather than interrupting them with our stack trace.
if [ "$status" -eq 1 ] && [ -n "$out" ]; then
  echo "design-flow: LLM design tells in $file — each cites the doctrine it enforces." >&2
  printf '%s\n' "$out" >&2
  echo "Disable one with a reason: <!-- design-flow-disable <rule>: why -->" >&2
  exit 2
fi
exit 0
