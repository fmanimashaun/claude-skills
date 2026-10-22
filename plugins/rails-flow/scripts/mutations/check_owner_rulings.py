"""Mutation guard: check_owner_rulings (#2297). Declared here, run by scripts/mutation_check.py.

The check refuses a PR that closes an issue carrying an OWNER's ruling no D-NNN `Refs` line records, and refuses
(never passes) when gh is present but a read fails. Each mutation turns one refusal into a pass.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_owner_rulings",
    subject="scripts/check_owner_rulings.py",
    selftest="scripts/check_owner_rulings.py",
    selftest_args=("--selftest",),
    needs=(),
    mutations=(
        Mutation(
            'a closing keyword in the middle of a sentence closes an issue',
            'CLOSING = re.compile(r"^\\s*(?:fixes|closes|resolves)\\s+#(\\d+)\\s*$", re.I | re.M)',
            'CLOSING = re.compile(r"(?:fixes|closes|resolves)\\s+#(\\d+)", re.I | re.M)',
            "a closing keyword mid-sentence closes nothing (the repository's own convention)",
        ),
        Mutation(
            '`owner, <date>` stops marking a ruling',
            '|\\bowner,\\s*\\d{4}-\\d{2}-\\d{2}\\b", re.I)',
            '", re.I)',
            '`owner, <date>` in the body of an issue the OWNER wrote counts as a ruling',
        ),
        Mutation(
            'an owner ruling in the issue body is not read',
            '[(issue.get("createdAt", "")[:10], issue.get("body") or "")] if (issue.get("author") or {}).get("login") == owner else []',
            '[]',
            '`owner, <date>` in the body of an issue the OWNER wrote counts as a ruling',
        ),
        Mutation(
            "a body any reporter wrote counts as the owner's",
            'if (issue.get("author") or {}).get("login") == owner else []',
            'if True else []',
            '...but in the body of an issue a reporter wrote it is a quotation, not a ruling',
        ),
        Mutation(
            "a comment from anyone counts as the owner's",
            'for c in issue.get("comments", []) if c.get("authorAssociation") == "OWNER"]',
            'for c in issue.get("comments", [])]',
            "a reporter's comment quoting 'the owner decided' owes no record",
        ),
        Mutation(
            'every ruling counts as recorded',
            '    for b in blocks:\n        for m in REFS_LINE.finditer(FENCE.sub("", b)):',
            '    return True\n    for b in blocks:\n        for m in REFS_LINE.finditer(FENCE.sub("", b)):',
            'a closed issue with an owner ruling and no decision citing it is refused, naming the issue and the ruling',
        ),
        Mutation(
            '#50 is read as a mention of #5',
            'rf"#{issue}\\b"',
            'rf"#{issue}"',
            'a block that says Refs #50 does not record #5',
        ),
        Mutation(
            'a Refs line inside a code fence records the ruling',
            'REFS_LINE.finditer(FENCE.sub("", b))',
            'REFS_LINE.finditer(b)',
            'a `Refs #5` inside a code fence records nothing',
        ),
        Mutation(
            'a Refs in the middle of a line records the ruling',
            '^\\s*(?:[-*]\\s+)?\\**Refs',
            '(?:[-*]\\s+)?\\**Refs',
            'a `Refs #5` in the middle of a line is not a line of its own',
        ),
        Mutation(
            'a passing mention anywhere in the block records the ruling',
            '        for m in REFS_LINE.finditer(FENCE.sub("", b)):\n            if re.search(rf"#{issue}\\b", m.group(1)):',
            '        for m in [None]:\n            if re.search(rf"#{issue}\\b", b):',
            'a passing mention ("unlike #5") does not record it',
        ),
        Mutation(
            'an owner that cannot be told passes',
            '        if rc != 0 or not owner:\n            return 1,',
            '        if False:\n            return 1,',
            'with gh present, an owner that cannot be told REFUSES: a quotation cannot be told from a ruling',
        ),
        Mutation(
            'an issue that cannot be read passes',
            '        if rc != 0:\n            problems.append(f"could not read #{n}: {out[:200]}; its owner rulings cannot be checked, so the PR is refused")\n            continue',
            '        if rc != 0:\n            continue',
            'with gh present, an issue that cannot be read REFUSES the PR (exit 1), never passes',
        ),
        Mutation(
            'a PR that cannot be read passes',
            '        return 1, [f"could not read the pull request: {out[:200]}"]',
            '        return 0, [f"could not read the pull request: {out[:200]}"]',
            'with gh present, a PR that cannot be read refuses',
        ),
        Mutation(
            'no gh at all passes',
            '        return 3, ["gh is not installed',
            '        return 0, ["gh is not installed',
            'no gh at all is not applicable (exit 3) and says so',
        ),
    ),
)
