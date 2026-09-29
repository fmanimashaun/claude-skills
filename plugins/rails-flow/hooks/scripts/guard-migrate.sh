#!/usr/bin/env bash
# PreToolUse[Write] — refuse CREATING a new file under db/migrate/ directly, in a Rails project.
#
# #1362. Maintainer decision (2026-09-27):
# https://github.com/fmanimashaun/claude-skills/issues/1362#issuecomment-5857527899
#
# Nothing made "use the generator" true. An agent free-forming a Write straight into db/migrate/
# produces a migration with none of the things `bin/rails generate migration` gets right for
# free -- the timestamp that orders it after every existing one, and a class name that matches the
# file. This hook is `Write` ONLY: `Edit`/`MultiEdit` cannot create a file, so they carry no
# creation moment to refuse.
#
# SCOPED THREE WAYS, so nothing legitimate is caught in it:
#   - not a Rails project (no bin/rails at the project root) -- silent, always.
#   - not db/migrate/, or not a `.rb` file -- every other write stays exactly as free as it was.
#   - the file already EXISTS -- overwriting a migration via Write stays allowed; only creating
#     one from scratch is blocked.
#
# THE KNOWN LIMIT (verified 2026-09-27): a project that overrides `migrations_paths` in
# `database.yml` (Rails' multi-database support) writes migrations somewhere other than
# `db/migrate/`, and this guard does not read `database.yml` to find that path -- judged out of
# scope. It only ever refuses the literal `db/migrate/` directory.
#
# FAILS CLOSED, SCOPED. Without python3, or when the JSON cannot be parsed at all, judge the raw
# payload text the way guard-bash.sh does: block only if it contains a db/migrate/*.rb path AND
# this project has bin/rails; otherwise allow. That is coarser than the parsed path (it cannot
# check whether the file already exists), which is the accepted cost of failing closed rather
# than open in a degraded environment.
set -uo pipefail

DENY_MSG='Creating files under db/migrate/ directly is blocked in this project. Use the Rails generator instead:

  bin/rails generate migration AddPartNumberToProducts part_number:string

It picks the timestamped filename and matching class name. Once the file exists you can edit it freely — only creating it from scratch is blocked. Run `bin/rails generate migration --help` for the column syntax it accepts.'

input="$(cat)"

# `CLAUDE_PROJECT_DIR`, else this hook's own cwd (the session's cwd) -- used by every fallback
# below, and by the parsed path when the payload names no `cwd` of its own.
root_dir="${CLAUDE_PROJECT_DIR:-$PWD}"

# bash's own `=~`, not grep: this path exists for a degraded environment, and a missing grep there
# would otherwise make the fail-closed fallback allow (grep "not found" is a non-match).
_raw_migrate_path='db/migrate/[^/"]*\.rb'
_raw_fallback() {
  if [ -f "$root_dir/bin/rails" ] && [[ $input =~ $_raw_migrate_path ]]; then
    echo "BLOCKED by rails-flow migration guard: $DENY_MSG" >&2
    exit 2
  fi
  exit 0
}

type -P python3 >/dev/null 2>&1 || _raw_fallback

verdict="$(printf '%s' "$input" | CLAUDE_PROJECT_DIR="$root_dir" python3 -c '
import json, os, sys

# THE ONE PLACE the target directory is named -- `db/migrate/` only. A project with a custom
# `migrations_paths` in database.yml is NOT covered (see the header comment); widening this to
# read that config is a decision for later, and this is the one function that would change.
def is_migrate_dir(parent):
    parent = parent.replace(os.sep, "/")
    return parent == "db/migrate" or parent.endswith("/db/migrate")

try:
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or os.getcwd()
    root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        print("ALLOW"); sys.exit(0)
    if not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)
    file_path = os.path.normpath(file_path)

    if not os.path.isfile(os.path.join(root, "bin", "rails")):
        print("ALLOW"); sys.exit(0)
    if not file_path.endswith(".rb"):
        print("ALLOW"); sys.exit(0)
    if not is_migrate_dir(os.path.dirname(file_path)):
        print("ALLOW"); sys.exit(0)
    if os.path.exists(file_path):
        print("ALLOW"); sys.exit(0)
    print("DENY")
except Exception:
    # Parsed as JSON but something in the shape was not what we expected -- fail closed the same
    # way an unparsable payload does, not open.
    print("PARSE_ERROR")
' 2>/dev/null)"

case "$verdict" in
  DENY)
    echo "BLOCKED by rails-flow migration guard: $DENY_MSG" >&2
    exit 2
    ;;
  ALLOW)
    exit 0
    ;;
  *)
    # Empty output (python3 crashed before printing anything) or the explicit PARSE_ERROR token --
    # both mean the payload could not be judged the normal way. Fail closed, scoped, on raw text.
    _raw_fallback
    ;;
esac
