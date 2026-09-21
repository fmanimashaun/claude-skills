"""Mutation guard: self_consistency. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="self_consistency",
    subject="scripts/self_consistency.py",
    selftest="scripts/self_consistency_selftest.py",
    mutations=(
        Mutation(
            # An example that runs code and asserts nothing is a test that cannot fail -- green
            # forever, and indistinguishable in a report from one that verifies something.
            "every example looks like it asserts, so assertion-free specs pass as coverage",
            "        if _PENDING.search(blob) or _ASSERTS.search(blob):",
            "        if True:",
            "assertion-free-spec / example runs code but asserts",
        ),
        Mutation(
            # A verification command whose failure cannot fail the build is a gate that cannot
            # fail -- the class this whole repo is organised around.
            "softened verdicts stop being reported, so `|| true` on a check passes review",
            "        match = _SOFTENED.search(line)",
            "        match = None",
            "swallowed-verdict / rspec verdict softened",
        ),
        Mutation(
            # An empty sample set must not read as "nothing to check" -- that is the vacuous
            # pass this repo keeps hitting, where a rule reports clean over nothing examined.
            "an empty sample set short-circuits, so documented-but-dead keys are never found",
            "    if not samples:",
            "    if True:",
            "dead-env-var / documented key nothing reads",
        ),
        # #1036, a matched pair. This rule has to sit between a too-narrow regex (the reported
        # false positive) and a too-wide one (a rule that cannot fail), so one mutation each way
        # is the only thing that proves it is still between them.
        Mutation(
            # TOO NARROW -- the reported bug restored. Bare `expect` cannot cross the `_`, so a
            # helper named `expect_a_way_back` read as an example that asserts nothing.
            "bare `expect` again, so a helper named expect_* reads as assertion-free",
            r'    r"\b(?:expect\w*|is_expected|',
            r'    r"\b(?:expect|is_expected|',
            "a helper named expect_* counts as asserting",
        ),
        Mutation(
            # TOO WIDE -- the over-correction. `\w*expect\w*` drops the leading word boundary, so
            # any identifier CONTAINING the substring counts and the rule stops being able to fail.
            "the suffix becomes a substring match, so any name containing `expect` asserts",
            r'    r"\b(?:expect\w*|is_expected|',
            r'    r"\b(?:\w*expect\w*|is_expected|',
            "a name merely CONTAINING expect is not an assertion",
        ),
        Mutation(
            "`rescue nil` stops being reported, so every failure it hides stays hidden",
            "        if _RESCUE_NIL.search(code):",
            "        if False:",
            "swallowed-exception / rescue nil",
        ),
    ),
)
