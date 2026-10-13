#!/usr/bin/env python3
"""Run the node:test files beside the QA robot's scaffolded TypeScript helpers (#1835).

    scaffold_ts_tests.py [--selftest | --selftest-only]

`--selftest-only` runs the decision rules' own rows and stops: no Node needed, which is what the mutation guard runs (#1979).

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


def too_old(have: tuple[int, int] | None) -> bool:
    """Node is unusable: its version could not be read, or it is below the floor type stripping needs."""
    return have is None or have < MIN_NODE


def no_tests(files: list[str]) -> bool:
    """A run that found no test files is not a pass: it is the shape of a glob that matched nothing."""
    return not files


def run_passed(returncode: int, tests: int | None, fail: int | None) -> bool:
    """A pass needs the runner to exit 0, BOTH footer counts to be present, at least one test, and zero failures."""
    return returncode == 0 and tests is not None and fail is not None and tests > 0 and fail == 0


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
    # The decisions main() takes, without needing Node: each is a pure function, and each rule is a row that can fail (#1979).
    footer = "ℹ tests 30\nℹ suites 0\nℹ pass 30\nℹ fail 0\nℹ cancelled 0\n"
    if summary(footer) != (30, 0): bad.append("summary does not read tests and fail from node:test's footer")
    if summary(footer.replace("fail 0", "fail 2")) != (30, 2): bad.append("summary does not read a non-zero failure count")
    if summary("") != (None, None): bad.append("summary invents counts for a run that printed no footer")
    if not run_passed(0, 30, 0): bad.append("a run with tests, no failures and exit 0 is not a pass")
    if run_passed(0, 0, 0): bad.append("a run that executed no tests is a pass")
    if run_passed(0, 30, 2): bad.append("a run with failing tests is a pass")
    if run_passed(1, 30, 0): bad.append("a non-zero exit from the runner is a pass")
    if run_passed(0, None, 0): bad.append("a run with no tests count is a pass")
    if run_passed(0, 30, None): bad.append("a run with no failure count is a pass")
    if not too_old(None): bad.append("a Node whose version could not be read is usable")
    if not too_old((22, 5)): bad.append("Node 22.5, below the type-stripping floor, is usable")
    if too_old((22, 6)): bad.append("Node 22.6, the floor itself, is too old")
    if too_old((24, 0)): bad.append("a newer Node is too old")
    if not too_old((21, 99)): bad.append("Node 21.99 is usable")
    if not no_tests([]): bad.append("an empty list of test files is not 'no tests'")
    if no_tests(["a.test.ts"]): bad.append("a list with a test file is 'no tests'")
    for b in bad:
        print(f"FAIL {b}")
    return 1 if bad else 0


def main() -> int:
    if "--selftest-only" in sys.argv[1:]:
        return selftest()
    if "--selftest" in sys.argv[1:] and selftest():
        return 1
    node = shutil.which("node")
    if not node:
        return unrunnable("node is not on PATH", dict(os.environ))
    have = node_version(node)
    if too_old(have):
        return unrunnable(f"node {have} is older than {MIN_NODE[0]}.{MIN_NODE[1]}, which type stripping needs", dict(os.environ))
    files = sorted(str(p) for p in SUPPORT.glob("*.test.ts"))
    if no_tests(files):
        print(f"scaffold_ts_tests: no *.test.ts under {SUPPORT} -- a run with no tests is not a pass")
        return 1
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", "--test", "--test-reporter=spec", *files],
                       capture_output=True, text=True, timeout=300)
    tests, fail = summary(r.stdout)
    if not run_passed(r.returncode, tests, fail):
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
