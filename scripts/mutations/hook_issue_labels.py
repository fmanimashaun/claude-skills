"""Mutation guard: hook_issue_labels. Declared here, run by scripts/mutation_check.py (#1311).

The mutations that matter let an unlabelled or under-labelled issue through: no label accepted,
a `when` group ignored, a prefix never matching, a broken declaration read as "allow", or a
compound command whose create is never seen.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_issue_labels",
    subject="plugins/rails-flow/hooks/scripts/lib/issue_labels.py",
    selftest="plugins/rails-flow/hooks/scripts/lib/issue_labels.py",
    mutations=(
        # #1336: a heredoc body is tokenised again, so prose apostrophes refuse a labelled create.
        Mutation(
            "heredoc bodies are no longer stripped before tokenising",
            "    cmd = strip_heredocs(cmd).replace(",
            "    cmd = (cmd).replace(",
            "a heredoc body with apostrophes does not break a labelled create",
        ),
        Mutation(
            "a <<- heredoc keeps its tab-indented closing tag unrecognised",
            '            while i < len(lines) and (lines[i].lstrip("\\t") if dash else lines[i]) != tag:',
            "            while i < len(lines) and lines[i] != tag:",
            "a <<- heredoc (tab-indented close) is stripped too",
        ),
        Mutation(
            "a create with no label is allowed",
            "        if not labels:\n            where =",
            "        if False:\n            where =",
            "no label: refused",
        ),
        Mutation(
            "a `when` group applies to every issue, so a feature is asked for a severity",
            '            if g.get("when") and not any(matches(l, g["when"]) for l in labels):\n                continue',
            '            if False:\n                continue',
            "CONTROL: a feature is allowed",
        ),
        Mutation(
            "a `when` group is never applied, so a bug needs no severity",
            '            if g.get("when") and not any(matches(l, g["when"]) for l in labels):\n                continue',
            '            if g.get("when"):\n                continue',
            "a bug without a severity: refused, saying why",
        ),
        Mutation(
            "a prefix pattern never matches",
            '    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern',
            "    return label == pattern",
            "prefix groups: comp/type/prio all present is allowed",
        ),
        Mutation(
            "an unreadable declaration allows the command",
            '        return None, f"{where} is unreadable ({exc}); fix it so labels can be checked"',
            '        return None, ""',
            "an unreadable declaration refuses rather than allowing",
        ),
        Mutation(
            "only the first segment of a compound command is read",
            "    for k, (kind, val) in enumerate(items):",
            "    for k, (kind, val) in enumerate(items[:1]):",
            "a create later in a compound command is checked",
        ),
        # #1400: the declaration is the TARGET repository's, not the session's.
        Mutation(
            "the session's declaration is applied again, whatever repository the create runs in",
            "        target, why = target_root(cd, root)",
            '        target, why = root, ""',
            "cd into another repo: that repo's declaration applies, and passes",
        ),
        Mutation(
            "a cd is no longer tracked, so the create is judged where the session stands",
            "        if seg and seg[0] in (\"cd\", \"pushd\", \"popd\"):",
            "        if False:",
            "cd into another repo: that repo's declaration applies, and passes",
        ),
        Mutation(
            "the cd target is used as-is, so a subdirectory has no declaration",
            "    return (Path(top) if top else path.resolve()), \"\"",
            "    return path.resolve(), \"\"",
            "a cd into a SUBDIRECTORY finds the repo's toplevel declaration",
        ),
        Mutation(
            "an unresolvable cd is guessed instead of refused",
            '                    or "$" in target or "`" in target or cd == UNKNOWN:',
            "                    or cd == UNKNOWN:",
            "a cd to a variable is refused, not guessed",
        ),
        # #1400 review: each way an uncertain cd would be GUESSED instead of refused.
        Mutation(
            "glued punctuation is left as one word, so the create after `);` vanishes",
            "        if tok and set(tok) <= set(\";&|()\"):\n            i = 0",
            "        if False:\n            i = 0",
            "refused: a glued `)&&` still splits",
        ),
        Mutation(
            "a subshell's cd outlives its closing parenthesis",
            "            elif stack:\n                cd, conditional = stack.pop()",
            "            elif stack:\n                stack.pop()",
            "refused: a subshell cd ends at its )",
        ),
        Mutation(
            "a cd in a pipeline is followed",
            '            if before in ("|", "&") or after in ("|", "&") or seg[0] == "popd" or target == "-" \\',
            '            if seg[0] == "popd" or target == "-" \\',
            "refused: a cd in a pipeline",
        ),
        Mutation(
            "cd - is read as a directory",
            '            if before in ("|", "&") or after in ("|", "&") or seg[0] == "popd" or target == "-" \\',
            '            if before in ("|", "&") or after in ("|", "&") or seg[0] == "popd" \\',
            "refused: cd - names no visible directory",
        ),
        Mutation(
            "a conditional cd is trusted past a ;",
            "            if val == \";\" and conditional:\n                cd, conditional = UNKNOWN, False",
            "            if False:\n                cd, conditional = UNKNOWN, False",
            "refused: a cd that may never have run",
        ),
        Mutation(
            "a create after `cd x ||` is judged in x",
            '            if after == "||":\n                cd = UNKNOWN',
            '            if False:\n                cd = UNKNOWN',
            "refused: a create that runs only if the cd failed",
        ),
        Mutation(
            "-R naming the session's own repo takes the cd's rules again",
            "        if repo is not None and session_repo is not None and repo == session_repo:",
            "        if False:",
            "refused: -R naming the session's own repo keeps its rules",
        ),
        Mutation(
            "a GH_REPO prefix is ignored",
            "        repo = repo or env_repo",
            "        repo = repo",
            "refused: GH_REPO naming the session's own repo keeps its rules",
        ),
        Mutation(
            "newlines stop separating commands",
            '    cmd = strip_heredocs(cmd).replace("\\\\\\n", " ").replace("\\n", " ; ")',
            "    cmd = strip_heredocs(cmd)",
            "a newline separates commands",
        ),
        Mutation(
            "a newline after && breaks the chain",
            '            if val == ";" and op_at(k - 1) in ("&&", "||", "|"):\n                continue',
            '            if False:\n                continue',
            "a newline after && continues the chain",
        ),
        Mutation(
            "builtin cd is not recognised as cd",
            '        while seg and seg[0] in ("builtin", "command"):\n            seg.pop(0)',
            '        while False:\n            seg.pop(0)',
            "builtin cd is cd",
        ),
        Mutation(
            "another repo's issue is held to this project's groups",
            "        foreign = repo is not None and repo != mine",
            "        foreign = False",
            "another repo: one label is enough",
        ),
    ),
)
