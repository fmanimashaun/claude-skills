"""Mutation guard: check_criteria. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The four that pre-dated the pillars and were flagged rather than fixed. Each target and each
# `expects` was found EMPIRICALLY -- the mutation applied, the selftest run, the failure line
# read -- because three earlier guesses in this repo named the pass message instead of the
# failure message, and one named a line the selftest never exercised.
GUARD = Guard(
    name="check_criteria",
    subject="scripts/check_criteria.py",
    selftest="scripts/check_criteria_selftest.py",
    mutations=(
        # #707. `ID_RE` matches an `AC-n` anywhere, so an explanatory NOTE was parsed as a
        # malformed criterion and the whole file rejected -- from the Stop gate, every turn.
        Mutation(
            "prose mentioning criteria is parsed as a criterion definition again",
            "        lead = DEF_RE.match(raw)",
            "        lead = ID_RE.search(raw)",
            "a `## Notes` bullet naming two AC ids is prose, not a criterion",
        ),
        Mutation(
            "bolded ids stop being the definition marker, so a criterion may not reference "
            "another",
            "        if bold:",
            "        if False:",
            "a criterion referencing another criterion in its text",
        ),
        Mutation(
            # The dangerous direction: silently dropping a real criterion is worse than the
            # false positive being fixed.
            "a Given/When/Then line whose id does not lead is silently dropped",
            "            if (ID_RE.search(raw) and GIVEN_RE.search(raw)",
            "            if (False and ID_RE.search(raw) and GIVEN_RE.search(raw)",
            "a Given/When/Then line whose id does not lead is reported, not dropped",
        ),
        Mutation(
            "empty criteria stop being unusable, so a brief with nothing in it is accepted",
            "    if not out:",
            "    if False:",
            "no criteria at all: expected UNUSABLE",
        ),
        # #1189: Ruby expresses an error path by raising.
        Mutation(
            "Ruby's failure vocabulary is ignored, so a raised exception is not an error path",
            '    return any(h in low for h in ERROR_HINTS) or bool(RUBY_FAILURE.search(text))',
            '    return any(h in low for h in ERROR_HINTS)',
            "an untagged `raises SomeError` criterion counts as the error path",
        ),
        Mutation(
            # THE DOMAIN-VERB GUARD: a bare raise makes 'a requester raises a request' an error path.
            "the verb counts without what is raised, so a domain 'raise' passes",
            '    r"\\b(?i:raise[sd]?)\\s+(?:(?i:an?)\\s+)?(?:[A-Z][\\w:]*|(?i:error|exception)\\b)"',
            '    r"\\b(?i:raise[sd]?)\\b"',
            "the DOMAIN verb 'raises a request' is not an error path",
        ),
    ),
)
