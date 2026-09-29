"""Mutation guard: push_targets. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1410. Each way the parser can go wrong in the two directions: refusing a branch that merely
    # CONTAINS main, and allowing a push that really writes it.
    name="push_targets",
    subject="scripts/push_targets.py",
    selftest="scripts/push_targets.py",
    mutations=(
        Mutation(
            "the substring match comes back, so fix/1010-one-main is a promotion again",
            "            if dst in PROTECTED or",
            "            if any(p in dst for p in PROTECTED) or",
            "'git push -u origin fix/1010-one-main': expected does not target main",
        ),
        Mutation(
            "a refspec's destination is ignored, so dev:main reads as a push of dev",
            "        target = dst if sep and dst else src",
            "        target = src",
            "'git push origin dev:main': expected TARGETS main",
        ),
        Mutation(
            "refs/heads/ is no longer stripped, so refs/heads/main slips through",
            '    return dst[len("refs/heads/"):] if dst.startswith("refs/heads/") else dst',
            "    return dst",
            "'git push origin refs/heads/main': expected TARGETS main",
        ),
        Mutation(
            "--all no longer counts as every branch",
            'EVERY_BRANCH = {"--all", "--branches", "--mirror"}',
            'EVERY_BRANCH = {"--mirror"}',
            "'git push --all origin': expected TARGETS main",
        ),
        Mutation(
            "a bare push ignores @{push}, so a branch tracking origin/main pushes there unseen",
            "        dst = current(True) or current(False)",
            "        dst = current(False)",
            "'git push': expected TARGETS main",
        ),
        Mutation(
            "a newline stops separating commands, so a second-line push is read as arguments",
            'lex.whitespace = " \\t\\r"',
            'lex.whitespace = " \\t\\r\\n"',
            "'git status\\ngit push origin main': expected TARGETS main",
        ),
        Mutation(
            "an unbalanced quote is answered instead of refused",
            "        raise Unjudgeable(str(exc)) from exc",
            "        return []",
            "must be unjudgeable (the hook denies), not answered",
        ),
    ),
)
