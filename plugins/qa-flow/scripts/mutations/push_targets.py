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
            '    for prefix in ("refs/", "heads/"):',
            '    for prefix in ("heads/",):',
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
            "'cd other\\ngit push': expected TARGETS main",
        ),
        Mutation(
            "an unbalanced quote is answered instead of refused",
            "        raise Unjudgeable(str(exc)) from exc",
            "        return []",
            "must be unjudgeable (the hook denies), not answered",
        ),
        Mutation(
            # #1470 review: a shell expansion in a refspec was read literally, so $(echo main) passed.
            "shell expansions in a refspec are read literally again",
            '        if EXPANDS & set(word) or word.startswith("~"):      # `~user` is tilde expansion',
            "        if False:",
            "'git push origin $(echo main)': expected TARGETS main",
        ),
        Mutation(
            "redirections stop being split off, so main>/dev/null is one refspec",
            'punctuation_chars=";&|()<>\\n")',
            'punctuation_chars=";&|()\\n")',
            "'git push origin main>/dev/null': expected TARGETS main",
        ),
        Mutation(
            "shlex's comment rule comes back, so a mid-word # hides the push",
            '    lex.commenters = ""               # removed above, by bash\'s rule',
            '    lex.commenters = "#"',
            "'echo done#1; git push origin main': expected TARGETS main",
        ),
        Mutation(
            "heads/ is no longer qualified, so HEAD:heads/main slips through",
            '    for prefix in ("refs/", "heads/"):',
            '    for prefix in ("refs/",):',
            "'git push origin HEAD:heads/main': expected TARGETS main",
        ),
        Mutation(
            "heredoc bodies are tokenised again, so an apostrophe denies a feature push",
            "            if m:\n                pending.append",
            "            if False:\n                pending.append",
            "it's done, push main later",
        ),
        Mutation(
            "a prior cd is ignored, so a bare push is resolved in the wrong clone",
            "            cwd = seg[1] if cwd is None",
            "            cwd = None if cwd is None",
            "'cd other && git push': expected TARGETS main",
        ),
        Mutation(
            "a crash exits like 'no' again",
            "TARGETS, NO, UNJUDGEABLE = 0, 10, 3",
            "TARGETS, NO, UNJUDGEABLE = 0, 1, 3",
            "must differ from 0, 1 (a crash)",
        ),
        Mutation(
            "a leading + is no longer stripped, so +HEAD:main reads as a push of '+HEAD'",
            '        spec = spec.lstrip("+")',
            "        pass",
            "'git push origin +main': expected TARGETS main",
        ),
        Mutation(
            "--repo no longer shifts the positionals, so --repo=origin main reads main as the remote",
            '        if a.startswith("--repo="):\n            repo_opt = True',
            '        if False:\n            repo_opt = True',
            "'git push --repo=origin main': expected TARGETS main",
        ),
        Mutation(
            "the bare `:` refspec no longer counts as the matching branches",
            '        if spec == ":":',
            '        if spec == "::":',
            "'git push origin :': expected TARGETS main",
        ),
    ),
)
