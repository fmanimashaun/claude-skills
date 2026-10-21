#!/usr/bin/env bash
# PreToolUse[Edit|Write|MultiEdit] — refuse a BUILD edit while the unit's plan owes a `plan-advisor` pass (#2262, plan-advisor A-1 on #2267).
#
# The stop gate proves the advisory was recorded before the TURN ended, not before the BUILD: a whole build can happen inside one turn.
# This is the tripwire at the build's first step, shaped like guard-migrate: on a flow branch (feature/*, feat/*, fix/*), a Write or
# Edit OUTSIDE `docs/` is refused while `advisory_scope.py --slug <slug>` exits 1. Writing the plan, the threat model and the record
# itself stays free: they all live under `docs/`.
#
# A TRIPWIRE, NOT THE GUARANTEE. The guarantee is the stop gate and the `plan-advisory` sweep check that `gh pr ready` needs. So this
# hook FAILS OPEN when it cannot judge (no python3, no plugin root, an unparseable payload, a branch or slug it cannot read, the check
# itself unable to classify): an advisory that blocks work on a missing dependency gets disabled. A shell write (`cat >`, `cp`) goes
# through Bash, which this hook never sees.
set -uo pipefail
. "${BASH_SOURCE[0]%/*}/lib/trusted-env.sh" 2>/dev/null   # #1850: scrub PYTHON*/GIT_*/BASH_ENV and rebuild PATH from outside the repository

input="$(cat)"
root_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
checker="${CLAUDE_PLUGIN_ROOT:-}/scripts/advisory_scope.py"
type -P python3 >/dev/null 2>&1 || exit 0
[ -f "$checker" ] || exit 0

branch="$(git -C "$root_dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
case "$branch" in
  feature/*|feat/*|fix/*) ;;
  *) exit 0 ;;
esac
slug="${branch#*/}"
slug="${slug//\//-}"

target="$(printf '%s' "$input" | ROOT="$root_dir" python3 -c '
import json, os, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
path = ((data.get("tool_input") or {}).get("file_path") or "")
if not path:
    sys.exit(0)
root = os.path.realpath(os.environ["ROOT"])
full = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
rel = os.path.relpath(full, root)
print(rel.replace(os.sep, "/"))
' 2>/dev/null)"
[ -n "$target" ] || exit 0
case "$target" in
  docs/*|../*) exit 0 ;;      # the plan, the threat model and the record; or outside the project, which is not this unit's build
esac

aout="$(python3 "$checker" --slug "$slug" --root "$root_dir" 2>&1)"
if [ $? -eq 1 ]; then
  {
    echo "BLOCKED by rails-flow plan guard: the plan for \`$slug\` owes a plan-advisor pass before the build starts (#2262)."
    printf '%s\n' "$aout"
    echo "Writing under docs/ (the plan, the threat model, the record) stays allowed."
  } >&2
  exit 2
fi
exit 0
