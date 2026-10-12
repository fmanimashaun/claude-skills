#!/usr/bin/env bash
# Stop — commit a lane's TRACKED changes as WIP when a turn ends, so a cut-off session loses at most one turn (#1564).
# The judgement lives in scripts/wip_commit.py: lane branches only (feature/* and fix/*), tracked files only, git found outside the
# repository and run in a scrubbed environment, never a push. See that file for what it refuses and why.
#
# A STOP HOOK ON PURPOSE, never PreToolUse: a PreToolUse hook runs before the user is asked, under an environment a project's own settings
# can set (#1843), so it must not execute anything the repository or the environment chose. The WIP commit on `git push`, `gh pr merge`
# and `gh pr ready` that #1564 first proposed is deliberately not built.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): if a model ignores it, the cost is work a later
# kill could lose, never a stopped turn. A missing interpreter or script is silent through the stderr redirect and the unconditional exit.
set -uo pipefail
. "${BASH_SOURCE[0]%/*}/lib/trusted-env.sh" 2>/dev/null   # #1850: scrub PYTHON*/GIT_*/BASH_ENV and rebuild PATH from outside the repository, before any python3, git or gh
IFS= read -r -d '' payload || :   # a builtin: with no PATH, an external `cat` or `head` would print an error
printf '%s' "$payload" | python3 -I "${BASH_SOURCE[0]%/*}/../../scripts/wip_commit.py" 2>/dev/null
# The WIP commit moves HEAD after stop-where.sh recorded it, and the next SessionStart would call that record stale (review of 8725ef4d).
# Rewrite it from the state the commit left. Stop hooks in one list may run in parallel, so this runs after OUR commit whatever order they take.
printf '%s' "$payload" | python3 -I "${BASH_SOURCE[0]%/*}/lib/where_stopped.py" stop >/dev/null 2>&1
exit 0
