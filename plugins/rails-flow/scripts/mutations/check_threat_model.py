"""Mutation guard: check_threat_model (#2117). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_threat_model",
    subject="scripts/check_threat_model.py",
    selftest="scripts/check_threat_model.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "a missing section stops being reported",
            "        if s.lower() not in heads:",
            "        if False:",
            "a missing section is found",
        ),
        Mutation(
            "a decision outside the four stops being reported",
            "                if decision.lower() not in DECISIONS:",
            "                if False:",
            "a row without a decision is found",
        ),
        Mutation(
            "an accept with no reason stops being reported",
            '                elif decision.lower() == "accept" and (not reason or _is_filler(reason)):',
            '                elif decision.lower() == "accept" and False:',
            "an accept without a reason is found",
        ),
        Mutation(
            "a STRIDE letter outside S T R I D E stops being reported",
            "                if not stride or stride[0].upper() not in STRIDE:",
            "                if False:",
            "a bad STRIDE letter is found",
        ),
        Mutation(
            "a file with no threat rows stops being unusable (exit 2) and reads as clean",
            "        if rows == 0:\n            print(f\"UNUSABLE",
            "        if False:\n            print(f\"UNUSABLE",
            "a file with no threat rows is exit 2",
        ),
        Mutation(
            "a placeholder left from the template stops being reported, so the unedited template passes",
            "    for ph in sorted({m_.group(0) for m_ in PLACEHOLDER.finditer(prose)}):",
            "    for ph in []:",
            "the unedited shipped template is refused",
        ),
        Mutation(
            "an empty section stops being reported",
            "        if s != \"Threats\" and not [ln for ln in lines if not _is_filler(ln.lstrip(\"-* \"))]:",
            "        if False:",
            "an empty section is found",
        ),
        Mutation(
            "a section with no bullet stops being reported",
            "            if not [b for b in bullets if not _is_filler(b)]:",
            "            if False:",
            "a boundaries section with no bullet is found",
        ),
        Mutation(
            "a filler word stops counting as filler",
            "    return all(w in _FILLER_WORDS for w in re.sub(r\"[^\\w\\s]\", \" \", cell).lower().split())",
            "    return False",
            "a filler threat is found",
        ),
        Mutation(
            # #2117 adversary: `TODO: fill in` and `none yet` passed as content.
            "a stop word beside a filler hides it again",
            '    "fill", "in", "yet", "wip",',
            '    "zz1",',
            "a stop-word filler is found",
        ),
        Mutation(
            "one letter stops counting as filler",
            "    if len(re.findall(r\"[^\\W\\d_]\", cell)) < 2:",
            "    if len(re.findall(r\"[^\\W\\d_]\", cell)) < 1:",
            "one letter is filler",
        ),
        Mutation(
            "a cell with no letter stops counting as filler",
            "    if len(re.findall(r\"[^\\W\\d_]\", cell)) < 2:",
            "    if False:",
            "a reason with no letter is found",
        ),
        Mutation(
            "a placeholder wrapped in backticks inside a threat cell passes again",
            "for p_ in CELL_PLACEHOLDER.finditer(c.replace(\"`\", \"\"))}):",
            "for p_ in CELL_PLACEHOLDER.finditer(re.sub(r\"`[^`]*`\", \"\", c))}):",
            "a backticked placeholder in a threat cell is found",
        ),
        Mutation(
            "a placeholder with punctuation in it passes again, so the template's own reason cell is content",
            'CELL_PLACEHOLDER = re.compile(r"<(?!%)[^<>`\\n]{1,120}>")',
            'CELL_PLACEHOLDER = re.compile(r"<(?!%)[\\w /-]{1,120}>")',
            "the template's own placeholder in a cell is found",
        ),
        Mutation(
            "a placeholder exemption widens past `<%`, so text starting with a letter hides a placeholder",
            'CELL_PLACEHOLDER = re.compile(r"<(?!%)[^<>`\\n]{1,120}>")',
            'CELL_PLACEHOLDER = re.compile(r"<(?!%)(?![a-z])[^<>`\\n]{1,120}>")',
            "a backticked placeholder in a threat cell is found",
        ),
        Mutation(
            "an unclosed comment stops hiding the rest of the file",
            '    return re.sub(r"<!--.*?(?:-->|\\Z)", "", text, flags=re.S)',
            '    return re.sub(r"<!--.*?-->", "", text, flags=re.S)',
            "an unclosed comment hides the rest",
        ),
        Mutation(
            # #2131: the rows read comment-stripped text but the headings did not, so a heading hidden in a comment counted.
            "headings are read from the raw text again",
            '    heads = {m.group(1).strip().lower() for m in re.finditer(r"^##\\s+(.+?)\\s*$", _uncommented(text), re.M)}',
            '    heads = {m.group(1).strip().lower() for m in re.finditer(r"^##\\s+(.+?)\\s*$", text, re.M)}',
            "a heading inside a comment is missing",
        ),
        Mutation(
            "a row with no TM-n ID stops being reported",
            "                if not ID_RE.fullmatch(rid):",
            "                if False:",
            "a row without an ID is found",
        ),
        Mutation(
            "a repeated ID stops being reported",
            "                elif _tm_number(rid) in ids:  # TM-1 and TM-01 are one number, so one citation would cover both (#2213 adversary)",
            "                elif False:",
            "a repeated ID is found",
        ),
        Mutation(
            "the row number is its position again, so deleting a row shifts every citation",
            "            out.append((int(cells[0][3:]), cells[1], cells[4].lower()))",
            "            out.append((len(out) + 1, cells[1], cells[4].lower()))",
            "threat_rows reads each row's own ID, not its position",
        ),
        Mutation(
            "TM-1 and TM-01 count as two IDs again",
            "                    ids.add(_tm_number(rid))",
            "                    ids.add(rid.upper())",
            "TM-1 and TM-01 are the same ID",
        ),
        Mutation(
            "a second Threats section passes again",
            '    if len(re.findall(r"^##\\s+Threats\\s*$", _uncommented(text), re.M)) > 1:',
            '    if False:',
            "a second Threats section is found",
        ),
    ),
)
