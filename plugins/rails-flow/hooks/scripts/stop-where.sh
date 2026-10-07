#!/usr/bin/env bash
# Stop — where this worktree stopped (#1639). Rewrites `<git-common-dir>/handoff/<worktree-key>.md` with the facts of
# the last completed turn (branch, HEAD, commits not on any remote, uncommitted files), so a session killed without
# warning still leaves them on disk; and says ONCE, when the counts change, that there is unpushed or uncommitted
# work. The judgement lives in lib/where_stopped.py.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): if a model ignores the line
# the cost is work a later kill could lose, never a stopped turn. A missing interpreter or script is silent through
# the stderr redirect and the unconditional exit.
set -uo pipefail
python3 "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop 2>/dev/null
exit 0
