"""Mutation guard: check_spec_support. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #803. Rails ships the spec/support auto-loader COMMENTED. Left as generated, every file
    # under spec/support/ is dead with no error and no output -- a support directory that loads
    # nothing looks exactly like one that works.
    name="check_spec_support",
    subject="plugins/rails-flow/scripts/check_spec_support.py",
    selftest="plugins/rails-flow/scripts/check_spec_support.py",
    mutations=(
        Mutation(
            # The whole point: a whole-file search matches the COMMENTED line and reports the
            # exact defect as clean. `uncommented` goes line by line for this reason.
            "the loader is searched whole-file, so a commented-out one counts",
            'if not line.lstrip().startswith("#"))',
            "if True)",
            "a COMMENTED auto-loader still fails",
        ),
        Mutation(
            "the auto-loader clause is switched off, so a dead support dir passes",
            "    if support_files and not uncommented(helper_text, AUTOLOAD):",
            "    if False:",
            "support files with no auto-loader FAIL",
        ),
        Mutation(
            # The inert-GEM clause, mirroring the inert-CONFIG rule mandated-gems refuses.
            "capybara no longer needs a driver, so the gem drives nothing and passes",
            "        if not DRIVEN_BY.search(spec_text):",
            "        if False:",
            "capybara with no driven_by FAILS",
        ),
        Mutation(
            "a repo with no spec/ reads as a pass",
            'return 3, f"not applicable — no {SPEC}/ in this repo (nothing to check, NOT a pass)"',
            'return 0, "ok"',
            "no spec/ is not-applicable, not a pass",
        ),
        Mutation(
            # Rails generates `Dir[Rails.root.join(...)]`; testing.md shows `Rails.root.glob`.
            # Accepting one spelling fails a project that used the other -- a false positive on
            # conforming work, which is what gets a gate switched off.
            "only one loader spelling is accepted, failing conforming projects",
            "(?:Rails\\.root\\.glob|Dir\\[?\\s*Rails\\.root\\.join)",
            "(?:Rails\\.root\\.glob)",
            "the Dir[Rails.root.join] spelling also counts",
        ),
    ),
)
