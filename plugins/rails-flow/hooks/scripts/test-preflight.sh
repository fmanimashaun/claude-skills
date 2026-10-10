#!/usr/bin/env bash
# PreToolUse[Bash] — say what is wrong with the machine before a test suite's result is read as the code's (#1561, #1566).
#
# When the command runs a test suite (rspec, `rails test`, Playwright, `bin/e2e`, `bin/ci`), `test_preflight.py` checks Postgres
# (only when the project's database is detected), a held `bundler.lock`, the load average and the spec paths the command names,
# and says so. It EXECUTES NOTHING a repository or the environment supplies (a PreToolUse hook runs before the user is asked about the command; #1821 keeps the
# removed project hook point and restart). Silent otherwise, and silent when everything is fine.
#
# ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (docs/doctrine/harness-doctrine.md §5): a missing `python3`, `pg_isready` or `lsof`
# is silence, never a blocked command. Its text reaches the model as `additionalContext`, which Claude Code documents as added
# "alongside the tool result": it helps read a failure the environment caused, and it cannot stop the run. Plain stdout would NOT
# reach the model from a PreToolUse hook, which is why the script prints JSON. There is deliberately no `command -v python3` or
# `[ -f ]` guard: a missing interpreter or script is already silent through the stderr redirect and the unconditional exit, and a
# guard no fixture can distinguish from its absence is a line that proves nothing.
set -uo pipefail

# `:-` because this runs under `set -u` and the variable is the harness's to set (#825).
python3 "${CLAUDE_PLUGIN_ROOT:-}/scripts/test_preflight.py" 2>/dev/null
exit 0
