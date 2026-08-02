#!/usr/bin/env python3
"""Classify a boot failure from the log, instead of asking an agent to eyeball a table (#110).

`/qa-flow:smoke` step 4 says: *"classify it per the triage table below"*. That table is prose, and
until now nothing applied it. Its own paragraph explains why the category matters — *"a wall of
stack trace is not a diagnosis, and the categories below have genuinely different owners"* — which
is the argument for classifying, not for classifying **by hand**.

WHAT IT IS AND IS NOT. This is a lookup, not a diagnosis. Each category is a set of signatures the
runtime prints verbatim, so matching them is mechanical and the agent's judgement is not improved by
doing it manually. What stays judgement is the *next action*: the table's own last column is advice
for a human, and this script prints it rather than deciding it.

WHY THE ORDER IS FIXED AND NOT "MOST MATCHES WINS". A single boot log routinely carries several
signatures — a missing module often also prints a stack frame that mentions the runtime version.
Counting matches would let incidental noise outvote the specific cause, so the categories are tried
**most-specific first** and the first hit wins. That order is asserted by a fixture, because it is
the only thing separating this from a keyword soup.

APPLICATION ERROR IS THE FALLBACK, AND THAT IS DELIBERATE. Anything unrecognised is the app's own
defect -- which is the answer that files a bug rather than sending someone to fix their toolchain.
Guessing a more specific category on weak evidence is worse than the honest default, because the
specific ones all point at somebody else's problem.

Exit codes:  0 classified · 2 unusable (no log, unreadable)

Deliberately NOT 1-on-failure: every boot failure is a failure, so a non-zero exit here would carry
no information. The caller already knows the app did not boot; this says what kind.

Stdlib only, no network.

Usage:
    python3 classify_boot_failure.py qa/reports/smoke-boot.log
    python3 classify_boot_failure.py --json qa/reports/smoke-boot.log
    python3 classify_boot_failure.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Ordered most-specific first; the first category whose pattern appears wins. Every signature here
# is a string the runtime prints verbatim -- none is an inference about what the developer meant.
CATEGORIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "port-in-use",
        (r"EADDRINUSE", r"Address already in use", r"address already in use"),
        "re-run the step-2 probe — something already answers on that port; reuse it or pick another",
    ),
    (
        "dependency",
        (r"Module not found", r"Cannot find module", r"ERR_PACKAGE_PATH_NOT_EXPORTED",
         r"ERR_MODULE_NOT_FOUND", r"LoadError", r"Could not find gem"),
        "install it, or the package's `exports` map does not expose that subpath — a dependency "
        "problem, not an app defect",
    ),
    (
        "runtime-mismatch",
        (r"NODE_MODULE_VERSION", r"[Uu]nsupported engine", r"was compiled against a different",
         r"your Ruby version is", r"requires Ruby version"),
        "check the required runtime version against the installed one",
    ),
    (
        "config-policy",
        (r"blocked by .*policy", r"Blocked host", r"HostAuthorization", r"not allowed to load",
         r"ActionDispatch::HostAuthorization"),
        "consult the framework's docs for the policy — these rarely name the env var that fixes them",
    ),
)

FALLBACK = (
    "application-error",
    "the real defect — bad initializer, missing env var, failed migration. File it as "
    "`qa,from-qa,severity:s1`",
)


def classify(log: str) -> tuple[str, str, str | None]:
    """(category, next_action, matched_signature). Never raises; unrecognised is a real answer."""
    for name, patterns, action in CATEGORIES:
        for pattern in patterns:
            found = re.search(pattern, log)
            if found:
                return name, action, found.group(0)
    return FALLBACK[0], FALLBACK[1], None


def tail(log: str, lines: int = 20) -> str:
    return "\n".join(log.splitlines()[-lines:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify a boot failure from its log.")
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--tail", type=int, default=20)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.log:
        parser.error("a boot log is required (or --selftest)")
    try:
        text = args.log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"UNUSABLE: cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    category, action, signature = classify(text)
    if args.json:
        print(json.dumps({"category": category, "next_action": action,
                          "matched": signature, "tail": tail(text, args.tail)}, indent=2))
    else:
        print(f"  category : {category}")
        print(f"  matched  : {signature if signature else '(nothing recognised — the honest default)'}")
        print(f"  next     : {action}")
        print(f"\n  --- last {args.tail} line(s) of {args.log} ---")
        print(tail(text, args.tail))
    return 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def case(label: str, log: str, expect: str) -> None:
        nonlocal checks
        checks += 1
        got = classify(log)[0]
        if got != expect:
            failures.append(f"{label}: expected {expect}, got {got}")

    # Each category fires on a signature its runtime really prints.
    case("EADDRINUSE", "Error: listen EADDRINUSE: address already in use :::3000", "port-in-use")
    case("ruby address in use", "Errno::EADDRINUSE: Address already in use - bind(2)", "port-in-use")
    case("node missing module", "Error: Cannot find module 'playwright'", "dependency")
    case("exports map", "ERR_PACKAGE_PATH_NOT_EXPORTED ./internal", "dependency")
    case("ruby LoadError", "LoadError: cannot load such file -- pg", "dependency")
    case("native ABI", "was compiled against a different Node.js version", "runtime-mismatch")
    case("ruby version", "your Ruby version is 3.1.0, but your Gemfile specified 3.4.1",
         "runtime-mismatch")
    case("host policy", "Blocked host: example.test", "config-policy")

    # THE FALLBACK IS A REAL ANSWER, not a failure to classify. An app defect is the common case and
    # the one that files a bug rather than sending someone to fix their toolchain.
    case("unrecognised is an app error", "NoMethodError: undefined method `call' for nil",
         "application-error")
    case("an empty log still classifies", "", "application-error")

    # ORDER, which is the only thing separating this from keyword soup. A log carrying BOTH a
    # missing module and a runtime-version frame must classify as the dependency -- the specific
    # cause -- not as whichever pattern happens to appear more often or later.
    both = ("Error: Cannot find module 'sharp'\n"
            "    at ... was compiled against a different Node.js version\n"
            "    at ... was compiled against a different Node.js version\n")
    case("the specific cause wins over incidental noise", both, "dependency")
    # And the reverse: with no dependency signature, the runtime frame is the answer.
    case("runtime wins when it is the only signature",
         "Error: The module was compiled against a different Node.js version", "runtime-mismatch")

    # A category must never be reported without the action a reader is meant to take.
    checks += 1
    for name, _, action in CATEGORIES:
        if not action.strip():
            failures.append(f"{name}: no next action — naming a category without one is half a report")

    # Unusable input exits 2, never 0: a log we could not read is not "application-error".
    checks += 1
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.log"
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            code = main([str(missing)])
        if code != 2:
            failures.append(f"a missing log must exit 2, got {code}")

    if failures:
        print(f"SELFTEST FAILED — {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"classify_boot_failure selftest: {checks} checks passed across {len(CATEGORIES) + 1} categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
