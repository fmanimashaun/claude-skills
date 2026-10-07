#!/usr/bin/env bash
# SessionEnd — reap this session's own STOPPED ORPHANS (#1582 slice C).
#
# A process the session stopped and left behind is re-parented to pid 1 and stays stopped for good; enough of
# them exhaust the user's process limit and every fork on the machine fails. `session_reaper.py` finds the
# session's own by the id in their ENVIRONMENT (never by command name) and signals only stopped orphans.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): SessionEnd cannot block,
# and a cleanup that fails costs a leaked process, not a broken repository. The stdin payload goes straight to
# the script. Deliberately no `command -v python3` guard, as in ci-verdict-hint.sh: a missing interpreter is
# already silent through the redirect and the unconditional exit.
set -uo pipefail

python3 "${CLAUDE_PLUGIN_ROOT:-}/scripts/session_reaper.py" 2>/dev/null
exit 0
