#!/usr/bin/env bash
# PostToolUse[Bash] + PostToolUseFailure[Bash] — a red CI result is not yet a test failure (#1173).
#
# When a command that reads CI conclusions (`gh pr checks`, `gh run list|view`, ...) shows a
# failing one, add a single line of context naming `ci_verdict.py`, which can tell a suite that ran
# and failed from a runner that never started. `gh` prints the same word for both. Silent otherwise.
#
# Both events, because a Bash call that exits non-zero fires PostToolUseFailure instead of
# PostToolUse, and plain `gh pr checks` exits 1 exactly when a check has failed.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): if a model
# ignores the line the cost is a wrong diagnosis, not a broken repository. There is deliberately no
# `command -v python3` or `[ -f ]` guard: a missing interpreter or script is already silent through
# the stderr redirect and the unconditional exit, and a guard no fixture can distinguish from its
# absence is a line that proves nothing. Each line left is one a mutation breaks.
set -uo pipefail

# `:-` because this runs under `set -u` and the variable is the harness's to set (#825).
python3 "${CLAUDE_PLUGIN_ROOT:-}/scripts/ci_verdict_hint.py" 2>/dev/null
exit 0
