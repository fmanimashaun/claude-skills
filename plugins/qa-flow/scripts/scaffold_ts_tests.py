#!/usr/bin/env python3
"""Run the node:test files beside the QA robot's scaffolded TypeScript helpers (#1835).

    scaffold_ts_tests.py [--selftest]

The helpers in `plugins/qa-flow/scaffold/qa/e2e/support/` are copied into a project by /qa-flow:setup-qa, so a defect in
them ships to every project that takes the release-image robot. This runs their tests with Node's own runner and type
stripping (`node --experimental-strip-types --test`, Node 22.6 or later), with no npm install and no Playwright.

A pass needs all three: Node new enough, at least one test, and zero failures. A run that found no tests is not a pass —
it is the shape of a glob that matched nothing. Exit: 0 pass, 1 a test failed or none ran, 3 Node missing or too old on a
maintainer's machine (INCOMPLETE, a skip). **Under CI (`CI` set) a missing or too-old Node is exit 1**: CI only asserts that
`node` is on PATH, not its version, so a 3 there would be a skip nobody reads (review of #1844).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORT = Path(__file__).resolve().parents[1] / "scaffold" / "qa" / "e2e" / "support"
MIN_NODE = (22, 6)


def node_version(node: str) -> tuple[int, int] | None:
    out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    m = re.fullmatch(r"v(\d+)\.(\d+)\.\d+.*", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def summary(output: str) -> tuple[int | None, int | None]:
    """(tests, fail) from node:test's spec-reporter footer; None when a line is absent (the run did not finish)."""
    def count(name: str) -> int | None:
        m = re.search(rf"^\S* ?{name} (\d+)$", output, re.M)
        return int(m.group(1)) if m else None
    return count("tests"), count("fail")


def unrunnable(why: str, env: dict[str, str]) -> int:
    """Nothing could run. A skip on a maintainer's machine (3); a FAILURE under CI (1), where a skip would hide it."""
    ci = bool(env.get("CI", "").strip())
    print(f"scaffold_ts_tests: {why} -- nothing ran ({'FAILED: under CI this cannot be a skip' if ci else 'INCOMPLETE'})", file=sys.stderr)
    return 1 if ci else 3


def selftest() -> int:
    """The fail-closed rule, without needing an old Node installed."""
    bad = []
    if unrunnable("x", {"CI": "true"}) != 1: bad.append("under CI, a missing or old Node is not exit 1")
    if unrunnable("x", {}) != 3: bad.append("off CI, a missing or old Node is not exit 3")
    if unrunnable("x", {"CI": " "}) != 3: bad.append("a blank CI value is treated as CI")
    for b in bad:
        print(f"FAIL {b}")
    return 1 if bad else 0


def main() -> int:
    if "--selftest" in sys.argv[1:] and selftest():
        return 1
    node = shutil.which("node")
    if not node:
        return unrunnable("node is not on PATH", dict(os.environ))
    have = node_version(node)
    if have is None or have < MIN_NODE:
        return unrunnable(f"node {have} is older than {MIN_NODE[0]}.{MIN_NODE[1]}, which type stripping needs", dict(os.environ))
    files = sorted(str(p) for p in SUPPORT.glob("*.test.ts"))
    if not files:
        print(f"scaffold_ts_tests: no *.test.ts under {SUPPORT} -- a run with no tests is not a pass")
        return 1
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", "--test", "--test-reporter=spec", *files],
                       capture_output=True, text=True, timeout=300)
    tests, fail = summary(r.stdout)
    if r.returncode != 0 or tests is None or fail is None or tests == 0 or fail != 0:
        # Every failing test BY NAME first: a tail of the output alone cut the first file's failures off.
        failed = sorted({l.strip() for l in r.stdout.splitlines() if l.lstrip().startswith("✖") and "failing tests" not in l})
        print("failing tests:\n  " + "\n  ".join(failed) if failed else "failing tests: none named")
        print(r.stdout[-4000:])
        print(r.stderr[-2000:], file=sys.stderr)
        print(f"scaffold_ts_tests: FAILED (exit {r.returncode}, tests {tests}, fail {fail})")
        return 1
    print(f"scaffold_ts_tests: {tests} tests passed across {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
