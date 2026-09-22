"""Mutation guard: check_ci_runs_tests. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #334. Both mutations are ones I ACTUALLY MADE while writing it: a manifest command that cannot
# run, and an assertion that looked like it caught that but did not. The second is the reason
# this guard exists -- the vacuous version passed a re-introduced bug, and only mutation found it.
GUARD = Guard(
    # #779. The gate that stops a `bin/ci` being green on zero specs. Five mutations: it must
    # FAIL a --skip-test file, PASS once a suite step exists, key on the COMMAND not the label,
    # keep not-applicable as a third state, and distinguish "no steps at all" by its message.
    name="check_ci_runs_tests",
    subject="scripts/check_ci_runs_tests.py",
    selftest="scripts/check_ci_runs_tests.py",
    mutations=(
        Mutation(
            # WAS "every config/ci.rb passes, so the gate cannot fail", expecting the VERDICT
            # fixture. Since #1154 added a second way to return 1, this no longer flips the exit
            # code for a --skip-test file -- it flips the REASON, reporting a file with no suite
            # at all as one that merely forgot a reset. So the message fixture is the
            # discriminator now, and the verdict fixture is not; naming the old one would have
            # let it go quiet under a later change.
            "a file with no suite step is judged as though it had one",
            "    if running:",
            "    if True:",
            "...and the message names the zero-spec consequence",
        ),
        Mutation(
            # A step NAMED "Tests" that runs rubocop is the exact false confidence this refuses.
            "the step LABEL decides instead of the command",
            "if SUITE.search(cmd)]",
            "if SUITE.search(label)]",
            "...as a zero-spec file, not as one missing a reset",
        ),
        Mutation(
            "a repo with no config/ci.rb reads as a pass",
            'return 3, f"not applicable — no {CI_RB} in this repo (nothing to check, NOT a pass)"',
            'return 0, "ok"',
            "no config/ci.rb is not-applicable, not a pass",
        ),
        Mutation(
            # Both branches return 1, so a fixture checking only the verdict could not see this
            # one go -- it asserts the MESSAGE.
            "a ci.rb with no steps loses its own message",
            "    if not declared:",
            "    if False:",
            "...saying it declares NO step, not that 0 of them ran the suite",
        ),
        Mutation(
            # The line anchor is what excludes `# step ...`; there is no comment stripping,
            # because stripping truncated a real command containing a `#`.
            "STEP loses its line anchor, so a commented-out step counts",
            'r"""^\\s*step\\s+',
            'r"""\\s*step\\s+',
            "a commented-out suite step does not count",
        ),
        # ---- #1154: the reset rule. The database a suite reads is state the previous run wrote.
        Mutation(
            "the reset requirement is dropped, so a suite reading last run's rows passes",
            "        if not reset_precedes_suite(declared):",
            "        if False:",
            "a suite with no reset at all fails",
        ),
        Mutation(
            # THE ONE THAT MATTERS. `db:prepare` and `db:test:prepare` differ by four characters
            # and by whether anything is truncated; the reported project had the former and a
            # stage named "DB reset" over it. A PURGE pattern that accepts both is the defect.
            "PURGE accepts db:prepare, which truncates nothing",
            'PURGE = re.compile(r"\\bdb:(?:test:(?:prepare|purge|load_schema)|reset)\\b")',
            'PURGE = re.compile(r"\\bdb:(?:test:)?(?:prepare|purge|load_schema|reset)\\b")',
            "db:prepare before the suite is NOT a reset and still fails",
        ),
        Mutation(
            # Presence, not order -- and a purge the suite never reached is not a purge.
            "the reset may appear anywhere, so one running AFTER the suite counts",
            "    return any(PURGE.search(cmd) for _, cmd in declared[:first_suite])",
            "    return any(PURGE.search(cmd) for _, cmd in declared)",
            "a reset AFTER the suite does not count",
        ),
    ),
)
