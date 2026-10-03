#!/usr/bin/env python3
"""Run the unit tests of the mods rails-flow ships, under Node (#1547).

A mod (`hooks/*.mjs`) is JavaScript that Claude Code loads, and `claude plugin test` is the only thing that
exercises one inside the real engine -- which needs the `claude` CLI, and the gate runners do not have it.
Each `tests/<name>.unit.mjs` drives a mod's hooks with a hand-built host under plain Node instead, so the
mod's own logic is able to FAIL in CI. This wrapper is the one entry point the doctor's gate and every mod's
mutation guard (`scripts/mutations/<mod>.py`) run.

    python3 plugins/rails-flow/scripts/check_mods.py            # every tests/*.unit.mjs
    python3 plugins/rails-flow/scripts/check_mods.py context-nudge register   # just those

To add a mod's tests: write `tests/<name>.unit.mjs` that exits non-zero on failure, and a mutation guard
whose `selftest` is this script and whose `selftest_args` is `("<name>",)`.

What it does not cover: that the engine calls these hooks, with these event shapes. That stays with
`claude plugin validate` and `claude plugin test`, run locally.

No `node`, a named test that does not exist, or no test at all is an error, exit 3, never a pass: a check
that skips for want of its interpreter is indistinguishable from one that passed (`lint_markdown_code.py`
makes the same choice).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
TESTS = PLUGIN / "tests"


def main(argv: list[str]) -> int:
    node = shutil.which("node")
    if node is None:
        print("mod unit tests: `node` is not on PATH, so nothing was checked (exit 3)", file=sys.stderr)
        return 3
    names = argv[1:]
    files = [TESTS / f"{n}.unit.mjs" for n in names] if names else sorted(TESTS.glob("*.unit.mjs"))
    missing = [f.name for f in files if not f.is_file()]
    if missing or not files:
        print(f"mod unit tests: nothing to run ({missing or 'no tests/*.unit.mjs'}), so nothing was checked (exit 3)",
              file=sys.stderr)
        return 3
    worst = 0
    for test in files:
        result = subprocess.run([node, str(test)], cwd=PLUGIN, capture_output=True, text=True, errors="replace")
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        worst = max(worst, result.returncode)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
