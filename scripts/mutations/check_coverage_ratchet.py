"""Mutation guard: check_coverage_ratchet. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #800. The doctrine shipped `minimum_coverage 90` COMMENTED with "enable once realistic",
    # and nothing ever made it realistic -- coverage unenforced from the first commit to the
    # last. A drop is a measured regression, not judgement, so it can gate.
    name="check_coverage_ratchet",
    subject="plugins/rails-flow/scripts/check_coverage_ratchet.py",
    selftest="plugins/rails-flow/scripts/check_coverage_ratchet.py",
    mutations=(
        Mutation(
            # The defect being replaced was a line shipped COMMENTED; a whole-file search would
            # match it and report the exact problem as solved.
            "the config is searched whole-file, so a commented ratchet counts",
            'if not line.lstrip().startswith("#"))',
            "if True)",
            "a COMMENTED ratchet still fails",
        ),
        Mutation(
            "the ratchet clause is off, so a coverage drop passes",
            "    if not uncommented(spec_text, RATCHET):",
            "    if False:",
            "a SimpleCov config with no ratchet FAILS",
        ),
        Mutation(
            "a fixed minimum_coverage stops being refused",
            "    if uncommented(spec_text, FIXED_THRESHOLD):",
            "    if False:",
            "a fixed minimum_coverage FAILS even with the ratchet",
        ),
        Mutation(
            # `minimum_coverage_by_file line: 0` is PRESCRIBED. Dropping the digit requirement
            # would fail a project following the doctrine -- the false positive that gets a
            # gate switched off.
            "the threshold pattern loses its digit, so the prescribed per-file floor is flagged",
            'FIXED_THRESHOLD = re.compile(r"\\bminimum_coverage\\s+\\d")',
            'FIXED_THRESHOLD = re.compile(r"\\bminimum_coverage")',
            "minimum_coverage_by_file is not the forbidden form",
        ),
        Mutation(
            # Ignoring coverage/ without the exception means the ratchet compares against
            # nothing in CI -- present, configured, and remembering no baseline.
            "the gitignore clause is off, so the ratchet silently loses its memory",
            "        if any(IGNORES_COVERAGE.match(l) for l in lines) and not any(",
            "        if False and not any(",
            "ignoring coverage/ with no exception FAILS",
        ),
        Mutation(
            "a project without simplecov reads as a pass",
            '        return 3, ("not applicable — `simplecov` is not declared in this project "',
            '        return 0, ("ok "',
            "no simplecov is not-applicable, not a pass",
        ),
    ),
)
