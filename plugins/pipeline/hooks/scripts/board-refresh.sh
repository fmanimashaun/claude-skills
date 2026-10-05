#!/usr/bin/env bash
# Stop — refresh the status board (#1585). ADVISORY: it fails OPEN and never blocks a stop.
#
# OPT-IN. It runs only in a repository that asked for a board: `.claude/board.config.json` or an earlier
# `.claude/state/board.json` exists. A project that never ran `/pipeline:board` gets no files from a hook.
#
# THROTTLED. A board newer than BOARD_HOOK_FRESH_MIN minutes (default 2) is left alone, so a session that stops
# every few seconds does not re-measure `gh` every time.
#
# TIME-BOXED. The collector stops starting calls after BOARD_HOOK_BUDGET seconds (default 8), under the hook's
# own 15 s timeout (hooks.json). It READS only; nothing here writes the coordination record, and nothing takes
# its lock. Silent: the collector's one-line summary is discarded, because a Stop hook's output is not for the model.
set -uo pipefail
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
type -P python3 >/dev/null 2>&1 || exit 0
[ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/status_board.py" ] || exit 0
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$root" ] || exit 0
board="$root/.claude/state/board.json"
[ -f "$root/.claude/board.config.json" ] || [ -f "$board" ] || exit 0
fresh="${BOARD_HOOK_FRESH_MIN:-2}"
case "$fresh" in ''|*[!0-9]*) fresh=2 ;; esac
if [ -f "$board" ] && [ -n "$(find "$board" -mmin "-$fresh" 2>/dev/null)" ]; then
  exit 0
fi
budget="${BOARD_HOOK_BUDGET:-8}"
case "$budget" in ''|*[!0-9.]*) budget=8 ;; esac
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status_board.py" collect --root "$root" --budget-seconds "$budget" >/dev/null 2>&1 || true
exit 0
