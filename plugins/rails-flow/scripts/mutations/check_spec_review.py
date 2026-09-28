"""Mutation guard: check_spec_review. Declared here, run by scripts/mutation_check.py (#1370).

Each mutation lets a spec review through that cites a criterion nobody wrote, flags a file it was
never given, or calls itself CLEAN over its own blocking findings.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_spec_review",
    subject="scripts/check_spec_review.py",
    selftest="scripts/check_spec_review.py",   # --selftest lives in the module itself
    needs=("scripts/check_criteria.py", "scripts/findings.py"),
    mutations=(
        Mutation(
            "an invented criterion is accepted",
            "            elif cited not in defined:",
            "            elif False:",
            "a finding citing an undefined criterion is refused",
        ),
        Mutation(
            "a criterion finding need not name its criterion",
            "            if cited is None:",
            "            if False:",
            "a criterion finding with no AC in its signature is refused",
        ),
        Mutation(
            "untracked files are invisible again, so a brand-new file reads as outside the diff",
            '    files |= set(git("ls-files", "--others", "--exclude-standard").split("\\n"))',
            "    pass",
            "an UNTRACKED new file is in the diff (#1341)",
        ),
        Mutation(
            "unasked-for behaviour may name any file",
            "        elif r.get(\"file\") not in changed:",
            "        elif False:",
            "unasked-for behaviour in a file the diff does not change is refused",
        ),
        Mutation(
            "CLEAN is believed over the review's own blocking findings",
            '    if verdict == "CLEAN":',
            "    if False:",
            "CLEAN beside a blocking spec finding is refused",
        ),
        # Its control: P3 is advisory. Treating it as blocking refuses every CLEAN review with a note.
        Mutation(
            "an advisory finding blocks a CLEAN verdict",
            'BLOCKING = ("P1", "P2")',
            'BLOCKING = ("P1", "P2", "P3")',
            "CONTROL: CLEAN beside an advisory (P3) finding passes",
        ),
        Mutation(
            "an unknown category is accepted",
            "        if category not in CATEGORIES:",
            "        if False:",
            "an unknown category is refused",
        ),
        Mutation(
            "a missing findings file reads as a clean review",
            "    if not findings_path.is_file():\n        raise Unusable(",
            "    if not findings_path.is_file():\n        return []\n        raise Unusable(",
            "a missing findings file is unusable, not clean",
        ),
        Mutation(
            "another pass's records are judged as spec findings",
            'r.get("pass") == PASS]',
            "True]",
            "CONTROL: another pass's records beside spec records are not judged here",
        ),
        # #1393 review: a file with only another pass's records read as a CLEAN spec review, so the
        # gate could not tell a spec pass that never ran from one that found nothing.
        Mutation(
            "a file holding only another pass's records reads as a clean spec review",
            "    if loaded and not records:",
            "    if False:",
            "a file holding only another pass's records is unusable, not a clean spec review",
        ),
    ),
)
