"""Mutation guard: check_brief. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# rails-flow #130. FIVE of these eleven break a fixture whose job is to stay SILENT, because the
# centrepiece is a SIMILARITY rule and similarity rules are false-positive machines: a brief and
# the PRD it indexes describe the same product in the same words to the same reader. A
# blockquote is quotation, a fenced block is quoted code, a coverage-map cell quotes the
# source's own heading BY DESIGN, and shared product nouns are not a copy. Two more guard the
# carve-outs that keep the prose rules usable at all.
GUARD = Guard(
    name="check_brief",
    subject="plugins/rails-flow/scripts/check_brief.py",
    selftest="plugins/rails-flow/scripts/check_brief_selftest.py",
    # The self-containment rules are IMPORTED from check_handoff rather than copied -- "what
    # counts as a reference to the conversation" is one decision, and two copies of it would be
    # the second-source-of-truth failure this checker exists to police. check_criteria comes
    # along because check_handoff imports it.
    deps=(
        "plugins/rails-flow/scripts/check_handoff.py",
        "plugins/rails-flow/scripts/check_criteria.py",
    ),
    # Read, not imported. The selftest's last checks run the REAL command against this
    # checker's section contract and FAIL rather than skip when absent.
    needs=("plugins/rails-flow/commands/brief.md",),
    mutations=(
        Mutation(
            "the duplication threshold collapses and shared vocabulary reads as a copy",
            "DUP_WINDOW = 12",
            "DUP_WINDOW = 4",
            "eleven shared words is shared vocabulary",
        ),
        Mutation(
            "blockquotes stop being exempt, so quoting the user is duplication",
            '                and not stripped.startswith(">")',
            "                and True",
            "a blockquote of the same words is attributed quotation",
        ),
        Mutation(
            "table rows stop being exempt, so the citation mechanism flags itself",
            '                and not stripped.startswith("|")',
            "                and True",
            "a table row quoting the source's own heading",
        ),
        Mutation(
            "fenced blocks stop being exempt from the duplication rule",
            "                not fenced and bool(stripped)",
            "                bool(stripped)",
            "a fenced block of the same words is quoted code",
        ),
        Mutation(
            "the heading disqualifier loses its plural (the real bug a fixture found)",
            'rf"\\b{re.escape(d)}s?\\b"',
            'rf"\\b{re.escape(d)}\\b"',
            "is not the scope section",
        ),
        Mutation(
            "the mode cross-check widens back to the whole line and can never fire",
            'clause = re.split(r"[.|]", line[found.end():], maxsplit=1)[0][:60]',
            "clause = line",
            "the mode letter and the mode word disagree",
        ),
        Mutation(
            "a locator stops being resolved, so a citation only has to name a real file",
            "                if _collapse(locator) not in _collapse(body):",
            "                if False:",
            "a reference whose locator is not in the file",
        ),
        Mutation(
            "an `answered` row stops needing a source",
            '        if row.state == "answered" and not SOURCE_REF_RE.search(row.source):',
            "        if False:",
            "an `answered` row citing no source",
        ),
        Mutation(
            "an open question stops needing an owner",
            "        if not OWNER_RE.search(_strip_code(text)):",
            "        if False:",
            "an open question with no owner",
        ),
        Mutation(
            "TBD stops being carved out of Open questions (the false-positive direction)",
            "            if section is open_questions:",
            "            if False:",
            "TBD inside the open questions is that section's job",
        ),
        Mutation(
            "the `- None.` carve-out stops covering an explicitly empty open-questions section",
            "    if body and all(NONE_ONLY_RE.match(line) for line in body.splitlines()):",
            "    if False:",
            "an explicitly empty open-questions section is a real answer",
        ),
        Mutation(
            "a coverage gap stops needing to be recorded anywhere",
            "    if open_questions.bullets():",
            "    if True:",
            "a gap in the map and no open question recorded",
        ),
        Mutation(
            "a cited `D-nnn` stops being resolved against the decisions file",
            "        if num not in defined:",
            "        if False:",
            "a cited `D-nnn` the decisions file does not define",
        ),
        Mutation(
            "the non-goals hedge list stops applying, so `- None.` is a non-goal",
            '            if _collapse(_strip_code(text)).strip(".") not in HEDGES '
            "and len(_tokens(text)) >= 3]",
            "            if True]",
            "non-goals that say nothing",
        ),
    ),
)
