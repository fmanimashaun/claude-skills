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
    needs=("scripts/check_threat_model.py",),   # #2118: the threat-model rows are read through it
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
            '    r"\\b(?i:raise[sd]?)\\s+(?:(?i:an?)\\s+)?[`*_]*(?:[A-Z][\\w:]*|(?i:error|exception)\\b)"',
            '    r"\\b(?i:raise[sd]?)\\b"',
            "the DOMAIN verb 'raises a request' is not an error path",
        ),
        # #1209: markdown delimiters between the verb and the class.
        Mutation(
            "a quoted class after the verb is not recognised",
            '    r"\\b(?i:raise[sd]?)\\s+(?:(?i:an?)\\s+)?[`*_]*(?:[A-Z][\\w:]*|(?i:error|exception)\\b)"',
            '    r"\\b(?i:raise[sd]?)\\s+(?:(?i:an?)\\s+)?(?:[A-Z][\\w:]*|(?i:error|exception)\\b)"',
            "an article before a quoted class counts",
        ),
        Mutation(
            "the passive voice is not recognised",
            '    r"|\\b[A-Z][\\w:]*[`*_]*\\s+(?:is|are|gets?|be|being)\\s+raised\\b"\n',
            '',
            "the passive `X is raised` counts",
        ),
        Mutation(
            "a class ending in Error is not recognised on its own",
            '    r"|\\b[A-Z][\\w:]*(?:Error|Exception)\\b"\n',
            '',
            "a class ending in Error counts without the verb",
        ),
        Mutation(
            "the passive counts a lowercase subject, so domain prose passes",
            '    r"|\\b[A-Z][\\w:]*[`*_]*\\s+(?:is|are|gets?|be|being)\\s+raised\\b"\n',
            '    r"|\\b\\w+\\s+(?:is|are|gets?|be|being)\\s+raised\\b"\n',
            "a lowercase \'a request is raised\' is not an error path",
        ),
        # #2118. A mitigate row nobody turned into a [security] criterion is the gap this exists for.
        Mutation(
            "a mitigate row no [security] criterion cites stops being a finding",
            "        if n not in cited:",
            "        if False:",
            "a mitigate row no [security] criterion cites is a finding",
        ),
        Mutation(
            "a [security] criterion that cites no row stops being a finding",
            "        if not refs:",
            "        if False:",
            "a [security] criterion citing no row is a finding",
        ),
        Mutation(
            "citing an accept row stops being a finding",
            "            elif n not in mitigate:",
            "            elif False:",
            "a [security] criterion citing an accept row is a finding",
        ),
        Mutation(
            "html comments and code spans stop being hidden, so a tag or citation inside one counts",
            "    return HIDDEN_RE.sub(\" \", text)",
            "    return text",
            "a tag inside a code span is not a tag",
        ),
        Mutation(
            "a citation counts anywhere in the sentence, not only at its end",
            r'\s*[.;]?\s*$", re.I)',
            '", re.I)',
            "a citation followed by more words is not in the slot",
        ),
        Mutation(
            "a model with no readable table stops being exit 2",
            "        if not rows:\n            print(f\"UNUSABLE: {model} exists",
            "        if False:\n            print(f\"UNUSABLE: {model} exists",
            "a model with no table is exit 2",
        ),
        Mutation(
            # #2213 review: the default model sat three parents up, so a criteria file anywhere else skipped the security check.
            "the default threat model is three parents up again",
            "            return d / \"docs\" / \"security\" / \"threat-models\" / criteria_path.name, \"\"",
            "            return criteria_path.resolve().parent.parent.parent / \"security\" / \"threat-models\" / criteria_path.name, \"\"",
            "a criteria file deeper than docs/product/acceptance still finds its model at the repo root",
        ),
        Mutation(
            "a skipped security check is silent again",
            "        print(f\"security check skipped: {why or f'no threat model at {model}'}{hint}; pass --threat-model FILE if the unit has one\", file=sys.stderr)",
            "        pass",
            "no model found says the security check was skipped",
        ),
        Mutation(
            # #2213 adversary: threat_rows skipped a malformed row, so `**TM-3**` or `Mitigated` dropped its requirement.
            "a model row the reader cannot parse is dropped silently again",
            "        if rows and table_findings:",
            "        if False:",
            "a model row with a bolded ID is refused, not dropped",
        ),
        Mutation(
            "a multi-line comment hides nothing from the parser again",
            '    text = re.sub(r"<!--.*?(?:-->|\\Z)", lambda m: "\\n" * m.group(0).count("\\n"), text, flags=re.S)',
            '    pass',
            "a criterion inside a multi-line comment does not cite",
        ),
        Mutation(
            "a fenced block hides nothing from the parser again",
            "        elif mark:\n            fence = mark.group(1)",
            "        elif False:\n            fence = mark.group(1)",
            "a criterion inside a backtick fence does not cite",
        ),
        Mutation(
            "a fence never closes, so everything after it is hidden",
            "                fence = \"\"\n",
            "                pass\n",
            "a criterion after a closed fence still cites",
        ),
        Mutation(
            "the skip note stops naming the other models in the directory",
            '        hint = f" ({len(others)} other model(s) there: {\', \'.join(others[:5])}; is one this unit\'s?)" if others else ""',
            '        hint = ""',
            "a skip names the other models in the directory",
        ),
    ),
)
