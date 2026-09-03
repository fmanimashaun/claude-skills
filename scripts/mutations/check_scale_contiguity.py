"""Mutation guard: check_scale_contiguity. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #750. Two clauses -- a hole in a declared run, and a comment promising a step the file
    # never declares -- and both shipped simultaneously, so both need their own fixture.
    name="check_scale_contiguity",
    subject="plugins/design-flow/scripts/check_scale_contiguity.py",
    selftest="plugins/design-flow/scripts/check_scale_contiguity.py",
    # `doctrine_path.py` joins `needs` with #777: these now resolve the doctrine through the
    # shared resolver, so without it the staged tempdir fails at IMPORT and the harness
    # reports the guard INERT -- every mutation "caught" whether or not it breaks anything.
    # A guard's needs is everything its subject imports, and that changed when the subject did.
    needs=("skills", "plugins/design-flow/scripts/doctrine_path.py"),
    mutations=(
        Mutation(
            "a hole in the space run stops being reported",
            "        gaps = [SPACE_ORDER[i] for i in range(idx[0], idx[-1] + 1)",
            "        gaps = [SPACE_ORDER[i] for i in range(idx[0], idx[0])",
            "a hole in the space run is a finding",
        ),
        Mutation(
            "a skipped type step stops being reported, so 3 steps up to 5",
            "        holes = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]",
            "        holes = []",
            "a skipped type step is a finding",
        ),
        Mutation(
            # The half that caught the real defect: prose advertising a range the file omits.
            "a comment may promise a step the file never declares",
            "                if end not in present:",
            "                if False:",
            "a comment promising an undeclared end is a finding",
        ),
        Mutation(
            # The ladder IS the filter. Widening it would read `section` as a step and report a
            # hole between `l` and it -- a rule firing on correct work gets switched off.
            # Mutating the LADDER, not the filter: dropping the filter makes `.index()` raise,
            # and a crash is not a verdict -- the harness rejects a fixture that dies instead
            # of failing.
            "a named pair joins the ladder, so a one-off reads as a hole",
            'SPACE_ORDER = ["3xs", "2xs", "xs", "s", "m", "l", "xl", "2xl", "3xl"]',
            'SPACE_ORDER = ["3xs", "2xs", "xs", "s", "m", "l", "xl", "2xl", "3xl", "s-l"]',
            "a one-off pair is not read as a hole",
        ),
    ),
)
