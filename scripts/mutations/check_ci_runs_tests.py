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
    subject="plugins/rails-flow/scripts/check_ci_runs_tests.py",
    selftest="plugins/rails-flow/scripts/check_ci_runs_tests.py",
    mutations=(
        Mutation(
            "every config/ci.rb passes, so the gate cannot fail",
            "    if running:",
            "    if True:",
            "a --skip-test config/ci.rb FAILS",
        ),
        Mutation(
            # A step NAMED "Tests" that runs rubocop is the exact false confidence this refuses.
            "the step LABEL decides instead of the command",
            "if SUITE.search(cmd)]",
            "if SUITE.search(label)]",
            "a step LABELLED rspec that runs rubocop still fails",
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
    ),
)
