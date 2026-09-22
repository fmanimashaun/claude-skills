#!/usr/bin/env python3
"""Refuse a `config/ci.rb` whose steps never invoke the test suite (#779).

WHY THIS EXISTS. `--skip-test` is mandated by `project-setup.md` so the project gets RSpec instead of
Minitest. Rails gates the test steps in its `config/ci.rb` template on that same flag, so the
generated file has **no `Tests:` step** -- and `bin/ci`, which this toolchain treats as the full
gate, then reports green having run **zero specs**. A gate that passes by not looking is worse than
no gate, because it is quoted as confidence.

#391 fixed the doctrine half: `testing.md` says to *add* the step and supplies it verbatim. It said
in its own text that the enforcement half was still open, and #779 is that half arriving from a
second greenfield app -- the recurrence being the report. The doctrine was correct and complete
throughout; it was simply performed by nothing and checked by nothing.

WHAT COUNTS AS RUNNING THE SUITE. A step whose command invokes rspec or `rails test`. Matched on the
COMMAND, never on the step's label: a step named "Tests:" that runs rubocop is the exact false
confidence this file exists to refuse, and a project is free to name its step anything.

THREE STATES, and the third is why this is not just `grep`. A repo with no `config/ci.rb` has nothing
to check and is reported **not applicable** -- never a pass. `project_gates.py` prints that state by
name, so an app that never adopted `bin/ci` cannot borrow this gate's green.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CI_RB = Path("config/ci.rb")

# Commands that actually run the suite. Anchored to a word boundary so `rspec-rails` in a comment or
# a `bin/rubocop` step cannot satisfy it.
SUITE = re.compile(
    r"\b(?:"
    r"bundle\s+exec\s+rspec"
    r"|bin/rspec"
    r"|\brspec\b"
    r"|bin/rails\s+(?:test|spec)"
    r"|rails\s+(?:test|spec)\b"
    r")"
)

# Commands that genuinely EMPTY the test database before the suite reads it (#1154).
#
# `db:prepare` IS DELIBERATELY ABSENT and must stay absent. Measured against activerecord-8.1.3.1:
# `db:prepare` (databases.rake:395) is `DatabaseTasks.prepare_all` -- create-if-absent then migrate,
# with no truncation on any path. `db:test:prepare` (:553) invokes `db:test:load_schema` (:537),
# which depends on `db:test:purge` (:546) and drops the database. Only the latter resets anything.
# A project whose reset stage is `db:prepare` is the reported defect, not an exemption from it, so
# the `db:test:` prefix here is load-bearing and a mutation removing it must fail a fixture.
PURGE = re.compile(r"\bdb:(?:test:(?:prepare|purge|load_schema)|reset)\b")

# `step "Label", "command"` -- the command is the second argument, and it is the only half that
# decides anything here.
STEP = re.compile(r"""^\s*step\s+(?P<q1>['"])(?P<label>.*?)(?P=q1)\s*,\s*(?P<q2>['"])(?P<cmd>.*?)(?P=q2)""",
                  re.M)


def steps(source: str) -> list[tuple[str, str]]:
    """(label, command) for each declared step.

    NO COMMENT STRIPPING, deliberately. The first draft stripped `#` to end-of-line first, and a
    mutation removing that survived every fixture -- because `STEP` is anchored with `^\\s*step`, so
    a commented-out `# step ...` never matched anyway. Worse than dead: it TRUNCATED a legitimate
    command containing a `#`, so `step "Tests", "bundle exec rspec --tag ~slow # skip"` lost its
    closing quote, matched nothing, and the gate reported a project that runs its suite as one that
    does not. A false positive is the failure mode that gets a gate switched off.
    """
    return [(m.group("label"), m.group("cmd")) for m in STEP.finditer(source)]


def suite_steps(source: str) -> list[tuple[str, str]]:
    return [(label, cmd) for label, cmd in steps(source) if SUITE.search(cmd)]


def reset_precedes_suite(declared: list[tuple[str, str]]) -> bool:
    """Does a step that PURGES the test database run before the first step that reads it?

    ORDER IS THE WHOLE CHECK, not presence. A purge after the suite protects the next run only if
    the run reaches it, so a crash mid-suite -- or any stage that writes rows afterwards -- leaves
    the database dirty for the next start. The head of the consuming stage is the only placement
    that holds under a run that dies halfway, which is the case the reporter actually hit.
    """
    first_suite = next((i for i, (_, cmd) in enumerate(declared) if SUITE.search(cmd)), None)
    if first_suite is None:
        return False
    return any(PURGE.search(cmd) for _, cmd in declared[:first_suite])


def run(root: Path = Path(".")) -> tuple[int, str]:
    """(exit, message). 0 pass, 1 fail, 3 not-applicable."""
    doc = root / CI_RB
    if not doc.is_file():
        return 3, f"not applicable — no {CI_RB} in this repo (nothing to check, NOT a pass)"
    source = doc.read_text(encoding="utf-8")
    declared = steps(source)
    if not declared:
        return 1, (f"{CI_RB} declares no `step` at all — bin/ci would run nothing. "
                   "Rails' own template declares Setup, Style and Security steps.")
    running = suite_steps(source)
    if running:
        names = ", ".join(f"{label!r}" for label, _ in running)
        if not reset_precedes_suite(declared):
            return 1, (
                f"{CI_RB} runs the suite ({names}) but NO step empties the test database first, so "
                "the suite reads whatever the previous run left behind.\n"
                "  `db:prepare` does not count and is not a reset: it creates-if-absent and "
                "migrates, and truncates nothing (activerecord-8.1.3 databases.rake:395).\n"
                "  `db:test:prepare` does — it invokes db:test:load_schema, which depends on "
                "db:test:purge and drops the database.\n"
                '  Add `step "Tests: DB reset", "bin/rails db:test:prepare"` BEFORE the suite step. '
                "The block is in skills/rails-8/references/testing.md.")
        return 0, f"{CI_RB} runs the suite — {len(running)} step(s): {names} — after a test-database reset"
    labels = ", ".join(f"{label!r}" for label, _ in declared)
    return 1, (
        f"{CI_RB} declares {len(declared)} step(s) — {labels} — and NONE runs the test suite, so "
        "`bin/ci` reports green having run zero specs.\n"
        "  This is the `--skip-test` consequence project-setup.md predicts: Rails gates its own test\n"
        "  steps on that flag, so the generated file has no `Tests:` step and one must be ADDED.\n"
        "  The block to add is in skills/rails-8/references/testing.md (`Tests:` and `Tests: Seeds`).")


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def verdict(body: str | None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            if body is not None:
                (root / "config").mkdir()
                (root / "config" / "ci.rb").write_text(body, encoding="utf-8")
            return run(root)

    # THE REPORTED SHAPE, verbatim from a real `--skip-test` scaffold (#779).
    SKIPPED = '''CI.run do
  step "Setup", "bin/setup --skip-server"
  step "Style: Ruby", "bin/rubocop"
  step "Security: Gem audit", "bin/bundler-audit"
  step "Security: Importmap vulnerability audit", "bin/importmap audit"
  step "Security: Brakeman code analysis", "bin/brakeman --quiet --no-pager --exit-on-warn"
end
'''
    # The reset stage every PASSING fixture below needs, so that the suite-recognition checks
    # witness suite recognition ONLY. Without this they fail for the #1154 reason and stop saying
    # anything about the thing they were written for.
    RESET = '  step "Tests: DB reset", "bin/rails db:test:prepare"\n'

    def ci(*step_lines: str) -> str:
        return SKIPPED.replace('end\n', "".join(step_lines) + 'end\n')

    code, msg = verdict(SKIPPED)
    check("a --skip-test config/ci.rb FAILS", code == 1, f"exit {code}: {msg}")
    check("...and the message names the zero-spec consequence", "zero specs" in msg, msg)

    # THE FIX passes -- without this the gate could be "always fail", which is equally useless.
    for label, cmd in (("bundle exec", 'bundle exec rspec'), ("binstub", "bin/rspec"),
                       ("minitest", "bin/rails test")):
        code, msg = verdict(ci(RESET, f'  step "Tests", "{cmd}"\n'))
        check(f"a suite step via {label} passes", code == 0, f"exit {code}: {msg}")

    # THE LABEL IS NOT THE SIGNAL. A step *named* Tests that runs rubocop is the exact false
    # confidence this refuses -- and keying on the label would have passed it.
    code, msg = verdict(SKIPPED.replace('end\n', '  step "Tests", "bin/rubocop"\nend\n'))
    check("a step NAMED Tests that runs rubocop still fails", code == 1, f"exit {code}: {msg}")

    # ...and this is the case that actually WITNESSES command-vs-label. The one above cannot: it
    # keys on "Tests", which is not a suite word, so a label-matching implementation fails it for
    # the same reason a command-matching one does. Here the LABEL is a suite word and the command
    # is not, so only a command-matching implementation refuses it. The mutation harness rejected
    # the weaker fixture as a coincidental catch, which is exactly what it is for.
    code, msg = verdict(SKIPPED.replace('end\n', '  step "rspec", "bin/rubocop"\nend\n'))
    check("a step LABELLED rspec that runs rubocop still fails", code == 1, f"exit {code}: {msg}")
    # ...AND FOR THE RIGHT REASON. Since #1154 both branches return 1, so `code == 1` no longer
    # says which defect was found: a label-matching implementation ALSO returns 1 here, via the
    # missing-reset branch, and this fixture went quiet under its own mutation until it asserted
    # the message. The verdict stopped discriminating the moment a second way to fail existed.
    check("...as a zero-spec file, not as one missing a reset", "zero specs" in msg, msg[:160])

    # ...and conversely the label may be anything, because a project names its own steps.
    code, _ = verdict(ci(RESET, '  step "Suite", "bundle exec rspec"\n'))
    check("a suite step under any label passes", code == 0)

    # NOT APPLICABLE is the third state and never a pass.
    code, msg = verdict(None)
    check("no config/ci.rb is not-applicable, not a pass", code == 3, f"exit {code}")
    check("...and says so rather than reporting clean", "NOT a pass" in msg, msg)

    # A file with no steps at all is a failure, not a vacuous pass -- and the MESSAGE is asserted,
    # not just the exit code. Both branches return 1, so a mutation deleting this one survived a
    # fixture that checked only the verdict: the fallthrough would have said "declares 0 step(s) —
    # — and NONE runs", which is true, ugly, and points the reader nowhere.
    code, msg = verdict("CI.run do\nend\n")
    check("a ci.rb with no steps fails", code == 1)
    check("...saying it declares NO step, not that 0 of them ran the suite",
          "declares no `step` at all" in msg, msg[:110])

    # COMMENTS DO NOT COUNT -- held by `STEP`'s line anchor, not by stripping.
    code, msg = verdict(SKIPPED.replace('end\n', '  # step "Tests", "bundle exec rspec"\nend\n'))
    check("a commented-out suite step does not count", code == 1 and "zero specs" in msg,
          f"exit {code}: {msg[:160]}")

    # ...AND A REAL COMMAND MAY CONTAIN A `#`. This is the fixture the first draft lacked: stripping
    # comments truncated the command past its closing quote, so a project that DOES run its suite was
    # reported as one that does not. Measured before the stripping came out.
    code, msg = verdict(ci(RESET, '  step "Tests", "bundle exec rspec --tag ~slow # skip the slow ones"\n'))
    check("a suite command containing # is still found", code == 0, f"exit {code}: {msg}")

    # ------------------------------------------------------------------ #1154: the reset must
    # PRECEDE the suite, and `db:prepare` is not a reset.
    SUITE_STEP = '  step "Tests", "bundle exec rspec"\n'

    code, msg = verdict(ci(SUITE_STEP))
    check("a suite with no reset at all fails", code == 1, f"exit {code}: {msg}")
    check("...naming the previous run as the source, not the project's specs",
          "previous run left behind" in msg, msg[:140])

    # THE DISCRIMINATOR. This is the shipped defect: a project that believes it resets, because the
    # stage is named for it and the task is spelled `prepare`. A pattern matching `db:.*prepare`
    # passes this and is useless; only one requiring `db:test:` refuses it.
    code, msg = verdict(ci('  step "Tests: DB reset", "bin/rails db:prepare"\n', SUITE_STEP))
    check("db:prepare before the suite is NOT a reset and still fails", code == 1, f"exit {code}: {msg}")
    check("...and the message says db:prepare truncates nothing",
          "does not count and is not a reset" in msg, msg[:140])

    # ORDER IS THE CHECK, not presence -- a purge after the suite is a purge the suite never saw,
    # and a run that dies mid-suite never reaches it at all. A presence-only implementation passes
    # this fixture; that is what it is here to catch.
    code, msg = verdict(ci(SUITE_STEP, '  step "Tests: DB reset", "bin/rails db:test:prepare"\n'))
    check("a reset AFTER the suite does not count", code == 1, f"exit {code}: {msg}")

    # ...and each spelling that genuinely purges is accepted, since a project picks its own.
    for task in ("db:test:prepare", "db:test:purge", "db:reset"):
        code, msg = verdict(ci(f'  step "Reset", "bin/rails {task}"\n', SUITE_STEP))
        check(f"{task} before the suite passes", code == 0, f"exit {code}: {msg}")
    check("...and the passing message says the reset was seen",
          "after a test-database reset" in msg, msg)

    # A ci.rb with a reset and NO suite still fails for the original reason -- the two rules must not
    # mask one another.
    code, msg = verdict(ci(RESET))
    check("a reset without a suite still fails as zero-spec", code == 1 and "zero specs" in msg,
          f"exit {code}: {msg[:120]}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} ci-runs-tests assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, msg = run()
    print(msg, file=sys.stderr if code == 1 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
