"""Mutation guard: check_issue_mockup. Declared here, run by scripts/mutation_check.py (#1376).

Each mutation lets an issue that never decided whether it changes a screen read as ready, or
refuses one that did decide.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_issue_mockup",
    subject="scripts/check_issue_mockup.py",
    selftest="scripts/check_issue_mockup.py",   # --selftest lives in the module itself
    # It imports the approval rule from check_mockup_gate, which reads the diff through classify_door;
    # unstaged, the unmutated selftest failed and every mutation read as caught (INERT).
    needs=("scripts/check_mockup_gate.py", "scripts/classify_door.py"),
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
            'LINK = re.compile(r"https://[^/\\s]+\\.[^\\s]+"\n                  r"|(?:^|[\\s(`\\[])docs/product/mockups/(?:[^\\s/`\\]]+/)*[^\\s/`\\]]+\\.[A-Za-z0-9]+(?=[\\s),.;`\\]]|$)"\n                  r"|(?:^|[\\s(`\\[])[\\w./-]+\\.(?:html?|png|jpe?g|webp|pdf|svg)(?![\\w/-]|\\.\\w)", re.I)',
            'LINK = re.compile(r"https://[^/\\s]+\\.[^\\s]+", re.I)',
            "CONTROL: an agent-written section with a committed mock-up file is declared",
        ),
        # Pre-release review of #1387.
        Mutation(
            "any word ending in .md is a mock-up again",
            '                  r"|(?:^|[\\s(`\\[])[\\w./-]+\\.(?:html?|png|jpe?g|webp|pdf|svg)(?![\\w/-]|\\.\\w)", re.I)',
            '                  r"|(?:^|[\\s(`\\[])[\\w./-]+\\.(?:html?|png|jpe?g|webp|pdf|svg|md)(?![\\w/-]|\\.\\w)", re.I)',
            "\"TBD, see notes.md\" is not a declaration",
        ),
        Mutation(
            "triage accepts a linked mock-up with no approval",
            '    if APPROVAL.search(answer(body) or ""):',
            "    if True:",
            "a linked but unapproved mock-up is not ready",
        ),
        Mutation(
            # #1430
            'an approval link counts as the mock-up link again',
            '    return bool(LINK.search(APPROVAL.sub(" ", text))) or len({m.group(0).rsplit(\'#\', 1)[-1] for m in APPROVAL.finditer(text)}) >= 2',
            '    return bool(LINK.search(text))',
            'a section holding ONLY the approval link is not ready',
        ),
        Mutation(
            # #1430
            'a record path needs no extension, so docs/product/mockups/TBD links',
            '                  r"|(?:^|[\\s(`\\[])docs/product/mockups/(?:[^\\s/`\\]]+/)*[^\\s/`\\]]+\\.[A-Za-z0-9]+(?=[\\s),.;`\\]]|$)"',
            '                  r"|(?:^|[\\s(`\\[])docs/product/mockups/\\S+"',
            'docs/product/mockups/TBD is a placeholder',
        ),
        Mutation(
            # review of PR #1478
            'a mock-up posted as a comment is refused because its URL looks like an approval',
            '    return bool(LINK.search(APPROVAL.sub(" ", text))) or len({m.group(0).rsplit(\'#\', 1)[-1] for m in APPROVAL.finditer(text)}) >= 2',
            '    return bool(LINK.search(APPROVAL.sub(" ", text)))',
            'a mock-up posted as a comment, plus its approval, is ready',
        ),
        Mutation(
            # final review of PR #1478
            'one comment reached as issues/ and pull/ counts as two',
            "len({m.group(0).rsplit('#', 1)[-1] for m in APPROVAL.finditer(text)}) >= 2",
            'len({m.group(0) for m in APPROVAL.finditer(text)}) >= 2',
            'one comment reached two ways is not a mock-up plus approval',
        ),
        Mutation(
            # final review of PR #1478
            'a dotted folder satisfies the extension rule again',
            '                  r"|(?:^|[\\s(`\\[])docs/product/mockups/(?:[^\\s/`\\]]+/)*[^\\s/`\\]]+\\.[A-Za-z0-9]+(?=[\\s),.;`\\]]|$)"',
            '                  r"|(?:^|[\\s(`\\[])docs/product/mockups/\\S+\\.[A-Za-z0-9]+\\b"',
            'a dotted FOLDER does not make a placeholder a link',
        ),
        # #1479 (after #1478): the remainder #1478 did not cover.
        Mutation(
            'a path in backticks or a link target is not seen',
            'r"|(?:^|[\\s(`\\[])docs/product/mockups/',
            'r"|(?:^|\\s)docs/product/mockups/',
            'CONTROL: a path in backticks is linked',
        ),
        Mutation(
            'a mock-up extension need not end the name',
            'svg)(?![\\w/-]|\\.\\w)"',
            'svg)\\b"',
            'foo.pdf.TBD names no mock-up file',
        ),
    ),
)
