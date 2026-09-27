"""Mutation guard: check_issue_mockup. Declared here, run by scripts/mutation_check.py (#1376).

Each mutation lets an issue that never decided whether it changes a screen read as ready, or
refuses one that did decide.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_issue_mockup",
    subject="scripts/check_issue_mockup.py",
    selftest="scripts/check_issue_mockup.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "an issue with no section reads as declared",
            '        return False, "no Mock-up section: add one',
            '        return True, "no Mock-up section: add one',
            "an issue with no Mock-up section is missing",
        ),
        Mutation(
            "a blank form answer reads as declared",
            '    if not text or text == "_No response_":',
            "    if not text:",
            "a form left blank (_No response_) is missing",
        ),
        Mutation(
            "any answer at all reads as declared",
            "    return False, f\"the Mock-up section neither links",
            "    return True, f\"the Mock-up section neither links",
            "\"TBD\" is not a declaration",
        ),
        Mutation(
            "the section runs to the end of the issue, so a later link satisfies it",
            "        return (rest[: nxt.start()] if nxt else rest).strip()",
            "        return rest.strip()",
            "a link under a LATER heading does not satisfy the Mock-up section",
        ),
        Mutation(
            "a heading-less mention counts as the section",
            r'HEADING = re.compile(r"^\s{0,3}#{1,6}\s*mock-?up\b[^\n]*$", re.I | re.M)',
            r'HEADING = re.compile(r"mock-?up\b[^\n]*$", re.I | re.M)',
            "prose that mentions a mock-up is not a section",
        ),
        # The controls: each declared form must stay declared.
        Mutation(
            "\"no visible change\" is not accepted",
            '        return True, "declared: no visible change"',
            '        return False, "declared: no visible change"',
            "CONTROL: a form answer saying no visible change is declared",
        ),
        Mutation(
            "an agent-written `Mock-up:` line is not read",
            "    m = INLINE.search(body)\n    return m.group(1).strip() if m else None",
            "    return None",
            "CONTROL: a `Mock-up:` line with a link is declared",
        ),
        Mutation(
            "a committed mock-up file is not a link",
            r'LINK = re.compile(r"https://\S+|(?:^|\s)[\w./-]+\.(?:html?|png|jpe?g|webp|pdf|md)\b", re.I)',
            r'LINK = re.compile(r"https://\S+", re.I)',
            "CONTROL: an agent-written section with a committed mock-up file is declared",
        ),
    ),
)
