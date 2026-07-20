#!/usr/bin/env bash
# PostToolUse[Edit|Write] — auto-correct the edited Ruby file; surface leftovers.
set -uo pipefail
input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"

case "$file" in
  *.rb) : ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0
command -v bundle >/dev/null 2>&1 || exit 0
bundle exec rubocop --version >/dev/null 2>&1 || exit 0

out="$(bundle exec rubocop -a --no-color --format simple "$file" 2>/dev/null | tail -20)"
if printf '%s' "$out" | grep -qE '[1-9][0-9]* offenses? (detected|remaining)' && \
   ! printf '%s' "$out" | grep -q 'no offenses'; then
  if printf '%s' "$out" | grep -qE 'offenses? detected.*corrected' && printf '%s' "$out" | grep -q ' 0 offenses'; then
    exit 0
  fi
  echo "rubocop still reports offenses in $file after auto-correct:" >&2
  printf '%s\n' "$out" >&2
  exit 2
fi
exit 0
