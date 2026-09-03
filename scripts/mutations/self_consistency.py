"""Mutation guard: self_consistency. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="self_consistency",
    subject="plugins/rails-flow/scripts/self_consistency.py",
    selftest="plugins/rails-flow/scripts/self_consistency_selftest.py",
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
        Mutation(
            "`rescue nil` stops being reported, so every failure it hides stays hidden",
            "        if _RESCUE_NIL.search(code):",
            "        if False:",
            "swallowed-exception / rescue nil",
        ),
    ),
)
