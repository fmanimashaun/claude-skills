#!/usr/bin/env bash
# PreToolUse[Bash] — say what is wrong with the machine before a test suite's result is read as the code's (#1561, #1566).
#
# When the command runs a test suite (rspec, `rails test`, Playwright, `bin/e2e`, `bin/ci`), `test_preflight.py` checks Postgres
# (only when the project's database is detected), a held `bundler.lock`, the load average and the spec paths the command names,
# and says so. It runs no script or command line that a repository or the environment supplies, only `pg_isready`, `lsof` and `ps` (a PreToolUse hook runs before the
# user is asked about the command; #1821 keeps the removed project hook point and restart). Silent otherwise, and silent when everything is fine.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): a missing `python3`, `pg_isready` or `lsof`
# is silence, never a blocked command. Its text reaches the model as `additionalContext`, which Claude Code documents as added
# "alongside the tool result": it helps read a failure the environment caused, and it cannot stop the run. Plain stdout would NOT
# reach the model from a PreToolUse hook, which is why the script prints JSON. A missing interpreter or script is silent through the stderr
# redirect and the unconditional exit, so there is no `command -v python3` or `[ -f ]` guard; the interpreter lookup below is a different thing:
# it decides WHICH python3 may run at all, and each of its lines has a mutation.
set -uo pipefail

# THE INTERPRETER IS CHOSEN HERE, NOT BY THE SHELL'S OWN LOOKUP (review of #1826). `python3` found through PATH can be a `python3` the repository ships: an empty
# or `.` entry resolves into the checkout, and so does an absolute entry that points inside it. So it is taken only from an ABSOLUTE PATH entry that is not at or
# inside the repository, the repository being the OUTERMOST of the Gemfile and .git ancestors of the working directory (looked for by existence; git is never run),
# the same rule `trusted_which` applies to `pg_isready`, `lsof` and `ps`. And it runs ISOLATED (`-I`): PYTHONPATH and the other PYTHON* variables are ignored and
# neither the working directory nor the script's directory is put on the import path, so the script cannot be made to import a module from the checkout.
physical() { (cd -P "$1" 2>/dev/null && pwd -P); }

here="$(physical "$PWD")" || exit 0
root="$here"
probe="$here"
# Shell builtins only (no `dirname`: the hook must work on a PATH that holds nothing but a bash and a python3), and BOUNDED: no input can make this spin.
depth=0
while [ "$depth" -lt 64 ]; do
  if [ -e "$probe/Gemfile" ] || [ -e "$probe/.git" ]; then root="$probe"; fi
  [ "$probe" = "/" ] && break
  probe="${probe%/*}"
  [ -n "$probe" ] || probe="/"
  depth=$((depth + 1))
done

python=""
old_ifs="$IFS"
IFS=:
for dir in ${PATH:-}; do
  case "$dir" in /*) ;; *) continue ;; esac
  real="$(physical "$dir")" || continue
  case "$real/" in "$root"/*) continue ;; esac
  if [ -x "$real/python3" ]; then python="$real/python3"; break; fi
done
IFS="$old_ifs"

# `:-` because this runs under `set -u` and the variable is the harness's to set (#825).
[ -n "$python" ] && "$python" -I "${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py" 2>/dev/null
exit 0
