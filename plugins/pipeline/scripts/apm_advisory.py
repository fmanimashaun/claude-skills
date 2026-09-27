#!/usr/bin/env python3
"""Advise, at a production deploy, when the app carries no performance-monitoring gem (#1366).

Run:  python3 apm_advisory.py [path/to/Gemfile.lock]     # default ./Gemfile.lock
      python3 apm_advisory.py --selftest

ADVISORY, NEVER A GATE. Shipping without an APM is a legitimate choice, so this always exits 0: if a
model ignores the line, nothing breaks (`docs/doctrine/harness-doctrine.md`'s test). A deploy that
refused on it would be bypassed within a week, and then the reminder would be gone too.

ONE LINE OR NOTHING. It runs inside the deploy commands, whose output lands in the conversation, so
a present APM prints nothing and an absent one prints a single pointer. The install steps live in
`rails-8` `references/observability.md` §7 -- the one home for them; this names it and never repeats
them.

WHOLE GEM NAMES, NOT SUBSTRINGS. A lockfile is matched by the name token on each indented line, so
`skylight-extras` is not `skylight` and `sentry-ruby` is not `sentry-rails`. Any section counts --
GEM/GIT/PATH specs, a gem's own dependency lines, DEPENDENCIES (`name!` for a git source) -- because
a gem pulled in transitively is installed all the same.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# The tools `observability.md` §7 names, by the gem that installs each, plus Scout. Every name was
# checked against rubygems.org (HTTP 200) when this list was written.
APM_GEMS = frozenset({
    "rails_pulse",
    "skylight",
    "scout_apm",
    "newrelic_rpm",
    "appsignal",
    "datadog",
    "ddtrace",
    "sentry-rails",
    "honeybadger",
    "elastic-apm",
    "opentelemetry-instrumentation-rails",
    "solid_telemetry",
})

POINTER = "rails-8 skill, references/observability.md §7"
ADVICE = (f"apm advisory: no performance-monitoring gem in Gemfile.lock — production will have no "
          f"record of slow requests or queries. Optional; see {POINTER} (not blocking this deploy).")

# An indented lockfile line's leading name token: `    rails_pulse (0.4.1)`, `      skylight (>= 6)`,
# `  appsignal!`. Unindented lines are section headers (GEM, PLATFORMS, ...) and never gem names.
NAME = re.compile(r"^\s+([A-Za-z0-9][A-Za-z0-9._-]*)(?=[\s!(]|$)")


def gems_in(lockfile: str) -> set[str]:
    return {m.group(1) for line in lockfile.splitlines() if (m := NAME.match(line))}


def advise(lockfile: str) -> str | None:
    """The advisory line, or None when an APM gem is present."""
    return None if gems_in(lockfile) & APM_GEMS else ADVICE


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else "Gemfile.lock")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        # Not a skip dressed as a pass: say it did not run. Still 0 -- an advisory never blocks.
        print(f"apm advisory: skipped — no readable {path}")
        return 0
    line = advise(text)
    if line:
        print(line)
    return 0


# --------------------------------------------------------------------------- selftest
# Fixtures in the shape `bundle lock` writes, not a tidy one: platform-suffixed versions, a git
# source's `!`, a gem present only as another gem's dependency.

LOCK_HEAD = "GEM\n  remote: https://rubygems.org/\n  specs:\n"
LOCK_TAIL = "\nPLATFORMS\n  x86_64-linux\n\nDEPENDENCIES\n  rails (~> 8.1)\n\nBUNDLED WITH\n   2.6.2\n"
BARE = LOCK_HEAD + "    rails (8.1.3)\n      actionpack (= 8.1.3)\n    nokogiri (1.18.9-x86_64-linux-gnu)\n" + LOCK_TAIL


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool) -> None:
        if not ok:
            failures.append(label)

    # THE CASE IT EXISTS FOR.
    check_that("a lockfile with no APM gem gets the advisory", advise(BARE) == ADVICE)
    # ITS CONTROL. Without it, "advises when absent" is satisfied by a script that always advises.
    with_pulse = BARE.replace("    rails (8.1.3)\n", "    rails (8.1.3)\n    rails_pulse (0.4.1)\n      rails (>= 7.1.0)\n")
    check_that("a lockfile with rails_pulse is silent", advise(with_pulse) is None)
    check_that("a platform-suffixed APM version is still seen",
               advise(BARE.replace("    rails (8.1.3)\n", "    rails (8.1.3)\n    datadog (2.3.0-x86_64-linux)\n")) is None)
    check_that("a git-sourced APM in DEPENDENCIES is still seen",
               advise(BARE.replace("  rails (~> 8.1)\n", "  rails (~> 8.1)\n  skylight!\n")) is None)
    check_that("an APM present only as another gem's dependency is still seen",
               advise(BARE.replace("      actionpack (= 8.1.3)\n", "      actionpack (= 8.1.3)\n      newrelic_rpm (>= 9)\n")) is None)

    # WHOLE NAMES. Each of these would silence the advisory under a substring match.
    for near in ("skylight-extras (1.0)", "sentry-ruby (5.22.0)", "my_rails_pulse_fork (0.1)"):
        check_that(f"a near-miss name is not an APM: {near.split()[0]}",
                   advise(BARE.replace("    rails (8.1.3)\n", f"    rails (8.1.3)\n    {near}\n")) == ADVICE)
    # A section header or the BUNDLED WITH version is not a gem.
    check_that("unindented headers are never read as gem names", "GEM" not in gems_in(BARE) and "PLATFORMS" not in gems_in(BARE))

    # FAIL OPEN, and say so. A missing lockfile must not exit non-zero and must not print nothing.
    import contextlib, io, tempfile
    with tempfile.TemporaryDirectory() as d:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([str(Path(d) / "Gemfile.lock")])
        check_that("a missing lockfile exits 0", rc == 0)
        check_that("a missing lockfile says it skipped", "skipped" in out.getvalue())
        lock = Path(d) / "Gemfile.lock"
        lock.write_text(BARE, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([str(lock)])
        check_that("the advisory exits 0 — it never blocks a deploy", rc == 0)
        check_that("the entry point prints exactly one line", out.getvalue().count("\n") == 1)

    # THE SHIPPED CALL SITES. Proving the helper is not proving the caller: both deploy commands
    # must invoke this script, or the advisory exists and nothing runs it.
    here = Path(__file__).resolve().parents[1]
    for cmd in ("commands/deploy-cloud.md", "commands/release.md"):
        p = here / cmd
        check_that(f"{cmd} runs apm_advisory.py",
                   p.is_file() and "scripts/apm_advisory.py" in p.read_text(encoding="utf-8"))

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"apm_advisory selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
