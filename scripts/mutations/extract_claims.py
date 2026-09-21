"""Mutation guard: extract_claims. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="extract_claims",
    subject="plugins/rails-flow/scripts/extract_claims.py",
    selftest="plugins/rails-flow/scripts/extract_claims.py",
    mutations=(
        # #1106. Digits were extracted; spelled-out numbers were not, and "ten times in this
        # release's own bullets" reached a commit message wrong -- 2 there, 8 in older entries.
        Mutation(
            "spelled-out counts stop being measurements again",
            'r"\\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"',
            '        r"\\b(?:zzzznope|"',
            "a spelled-out count is a measurement",
        ),
        Mutation(
            # THE MUST-PASS HALF. Unbinding the number word from a countable noun floods every
            # report with ordinary English -- "one of the reasons", "two halves" -- and a report
            # nobody triages is indistinguishable from a passing one.
            "a bare number word counts, so ordinary prose becomes a claim",
            'r"eighty|ninety|hundred)\\s+(?:checks?|fixtures?|mutations?|gates?|files?|rows?|sites?|"',
            '        r"eighty|ninety|hundred)\\s+(?:\\w+|"',
            "prose is not a measurement",
        ),
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
