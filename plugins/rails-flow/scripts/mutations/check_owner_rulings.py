"""Mutation guard: check_owner_rulings (#2297). Declared here, run by scripts/mutation_check.py.

The check refuses a PR that closes an issue carrying an owner ruling no D-NNN record mentions, and refuses
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
            '`owner, <date>` in the issue body counts as a ruling',
        ),
        Mutation(
            'an owner ruling in the issue body is not read',
            '[(issue.get("createdAt", "")[:10], issue.get("body") or "")]',
            '[("", "")]',
            '`owner, <date>` in the issue body counts as a ruling',
        ),
        Mutation(
            'every ruling counts as recorded',
            '    return any(re.search(rf"#{issue}\\b", b) for b in blocks)',
            '    return True',
            'a closed issue with an owner ruling and no decision citing it is refused, naming the issue and the ruling',
        ),
        Mutation(
            '#50 is read as a mention of #5',
            'rf"#{issue}\\b"',
            'rf"#{issue}"',
            'a block that mentions #50 does not record #5',
        ),
        Mutation(
            'a mention outside DECISIONS.md records the ruling',
            '    blocks = decision_blocks(decisions)\n',
            '    blocks = decision_blocks(decisions) + ([(root / "docs/brain/STATUS.md").read_text()] if (root / "docs/brain/STATUS.md").exists() else [])\n',
            'a mention outside DECISIONS.md does not record it',
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
