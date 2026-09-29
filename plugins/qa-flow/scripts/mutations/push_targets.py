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
            "'git push origin {main,dev}': expected TARGETS main",
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
            # git help push: `--repo` equals the <repository> argument, and a positional wins.
            "the first positional stops being the repository, so --repo=origin main reads main as a refspec",
            "    refspecs = positional[1:]",
            "    refspecs = positional",
            "'git push --repo=origin main': expected does not target main",
        ),
        Mutation(
            # #1470 round 2: `-v$(true)` hid the refspecs from the first parser.
            "a substitution in an option word is read as a plain option again",
            "        if SUBST in word:",
            "        if False:",
            '"git push origin -v$(echo \' main\')": expected TARGETS main',
        ),
        Mutation(
            "unquoted $( is no longer one word, so shlex splits at ( and the refspecs vanish",
            "            out.append(_placeholder(cmd[i + 2:end - 1]) if c == \"$\" else SUBST)\n            i = end\n            continue",
            "            out.append(c)\n            i += 1\n            continue",
            "'git -C $(pwd) push origin main': expected TARGETS main",
        ),
        Mutation(
            "the current-branch idiom is refused like any substitution",
            '    return "HEAD" if " ".join(body.split()) in CURRENT_BRANCH_IDIOMS else SUBST',
            "    return SUBST",
            "git branch --show-current)\"': expected does not target main",
        ),
        Mutation(
            "the bare `:` refspec no longer counts as the matching branches",
            '        if spec == ":":',
            '        if spec == "::":',
            "'git push origin :': expected TARGETS main",
        ),
        Mutation(
            # 41's delta review of #1470: every one of these hid a push the hook never saw.
            "git is matched by exact name again, so /usr/bin/git and git.exe hide the push",
            '    return base in names or (base.endswith(".exe") and base[:-4] in names)',
            "    return word in names",
            "'/usr/bin/git push origin main': expected TARGETS main",
        ),
        Mutation(
            "sh -c strings are no longer parsed, so bash -c 'git push origin main' passes",
            "                        yield from all_segments(seg[i + 1], depth + 1)",
            "                        pass",
            "\"bash -c 'git push origin main'\": expected TARGETS main",
        ),
        Mutation(
            "eval is no longer parsed",
            "                yield from all_segments(\" \".join(seg[k + 1:]), depth + 1)",
            "                pass",
            "'eval \"git push origin main\"': expected TARGETS main",
        ),
        Mutation(
            "a backslash-newline is kept, so the refspec after it is a new command",
            '            if cmd[i + 1] != "\\n":\n                out.append(c + cmd[i + 1])',
            '            if True:\n                out.append(c + cmd[i + 1])',
            "'git push origin \\\\\\nmain': expected TARGETS main",
        ),
        Mutation(
            "an inline alias is followed as its literal verb, so -c alias.p=push hides the push",
            '                    raise Unjudgeable("a git alias defined inline can be any verb, push included")',
            "                    pass",
            "'git -c alias.p=push p origin main': expected TARGETS main",
        ),
        Mutation(
            "xargs is read as if its stdin were empty",
            '                raise Unjudgeable("xargs appends its stdin to the push, so its refspecs are unknown")',
            "                pass",
            "'echo main | xargs git push origin': expected TARGETS main",
        ),
        Mutation(
            "gh pr merge ignores the PR it names and falls back to the current branch's",
            "                sel = a\n                break",
            "                break",
            "classify 'gh pr merge 12'",
        ),
        Mutation(
            "git merge is no longer reported when a wrapper precedes it",
            '    if any(git_verb(seg, "merge") is not None for seg in all_segments(cmd)):',
            "    if False:",
            "classify 'git merge dev'",
        ),
        Mutation(
            "shell options that take a value are no longer stepped over, so -o pipefail hides -c",
            "                    if seg[i] in SHELL_OPTS_WITH_VALUE:\n                        i += 2",
            "                    if False:\n                        i += 2",
            "\"bash -o pipefail -c 'git push origin main'\": expected TARGETS main",
        ),
    ),
)
