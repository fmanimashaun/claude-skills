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

# THE PROJECT'S RUBY, NOT PATH'S (#824). The same resolution stop-gate.sh gained for #683, copied
# rather than shared because a hook must stand alone. Under mise the PATH `bundle` is a shim for
# whichever Ruby is global, so `bundle exec rubocop --version` failed on a project whose Ruby is
# pinned in `.ruby-version`, and this advisory exited 0 on every edit -- silently never running.
bundle_cmd="bundle"
if [ -f .tool-versions ] || [ -f .ruby-version ]; then
  if command -v mise >/dev/null 2>&1 && mise current ruby >/dev/null 2>&1; then bundle_cmd="mise exec -- bundle"
  elif command -v rbenv >/dev/null 2>&1; then bundle_cmd="rbenv exec bundle"
  elif command -v asdf >/dev/null 2>&1; then bundle_cmd="asdf exec bundle"; fi
fi
# shellcheck disable=SC2086  # word-split by design; no element can contain a space
$bundle_cmd exec rubocop --version >/dev/null 2>&1 || exit 0

out="$($bundle_cmd exec rubocop -a --no-color --format simple "$file" 2>/dev/null)"
# COUNT WHAT REMAINS; DO NOT PARSE THE SUMMARY (#824). `--format simple` prints one line per offense
# -- `C:  3:  1: Cop/Name: message` -- and tags the ones `-a` fixed with `[Corrected]`. The summary
# line counts DETECTED offenses, corrected ones included, so ` 0 offenses` never appears after a
# fix and the old test reported "still reports offenses" over a file that was now clean.
remaining="$(printf '%s\n' "$out" | grep -E '^[RCWEF]: *[0-9]+: *[0-9]+:' | grep -vc '\[Corrected\]' || true)"
if [ "${remaining:-0}" -gt 0 ]; then
  echo "rubocop still reports $remaining offense(s) in $file after auto-correct:" >&2
  printf '%s\n' "$out" | grep -E '^[RCWEF]: *[0-9]+: *[0-9]+:' | grep -v '\[Corrected\]' | head -30 >&2
  exit 2
fi
exit 0
