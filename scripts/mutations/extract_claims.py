"""Mutation guard: extract_claims. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="extract_claims",
    subject="plugins/rails-flow/scripts/extract_claims.py",
    selftest="plugins/rails-flow/scripts/extract_claims.py",
    mutations=(
        Mutation(
            # Hedged prose is not a claim. Without the filter, "arguably this prevents X" is
            # extracted as an assertion someone must then verify.
            "hedges stop disqualifying a sentence, so speculation is extracted as a claim",
            "    if any(re.search(h, sentence, re.I) for h in HEDGES):",
            "    if False:",
            "silent on 'Arguably this prevents confusion.'",
        ),
    ),
)
