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
# it decides WHICH python3 may run at all, and it is the lib's (`rf_trusted_python`), below. A stray `~/.git` or `~/Gemfile` makes the home directory the repository, which
# silences the hook for a tool installed under it (a Postgres in `~/.local/bin`): quiet, never wrong.
set -uo pipefail
. "${BASH_SOURCE[0]%/*}/lib/trusted-env.sh" 2>/dev/null   # #1850: scrub PYTHON*/GIT_*/BASH_ENV and rebuild PATH from outside the repository, before any python3, git or gh

# THE INTERPRETER IS CHOSEN BY THE LIB, NOT BY THE SHELL'S OWN LOOKUP (review of #1826, #1850). `python3` found through PATH can be a `python3` the repository ships: an empty or
# `.` entry resolves into the checkout, and so does an absolute entry or a link that points inside it. `rf_trusted_python` (lib/trusted-env.sh) takes it only from an ABSOLUTE
# PATH entry that is not at or inside the repository (the OUTERMOST Gemfile or .git ancestor of the working directory), whose own link target is outside it too, with a `*` in
# an entry kept literal. This hook used to carry its own copy of that lookup, and once the lib rebuilds PATH first, the copy's directory rules could never fire, so its
# mutants were equivalent and survived (#1893): the rules are the lib's, proven by its guard (`hook_trusted_env`) and the hostile-environment group. What stays HERE is what the
# lib does not do: it runs ISOLATED (`-I`: the working directory and the script's directory are not put on the import path, and PYTHON* is ignored even if something set it
# after the lib ran), and an absent interpreter is silence.
rf_trusted_python

# `:-` because this runs under `set -u` and the variable is the harness's to set (#825).
[ -n "${RF_PYTHON:-}" ] && "$RF_PYTHON" -I "${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py" 2>/dev/null
exit 0
