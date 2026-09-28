"""Mutation guard: hook_issue_labels. Declared here, run by scripts/mutation_check.py (#1311, #1400).

The mutations that matter let an unlabelled or under-labelled issue through: no label accepted,
a `when` group ignored, a prefix never matching, a broken declaration read as "allow", a create the
parser never sees, or (#1400) a `cd` the create may not have followed being trusted anyway.
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
            "        cmd = strip_heredocs(cmd)\n    except ValueError:",
            "        cmd = cmd\n    except ValueError:",
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
            "            if False:\n                continue",
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
            "another repo's issue is held to this project's groups",
            "        foreign = repo is not None and norm_repo(repo) != mine",
            "        foreign = False",
            "another repo: one label is enough",
        ),
        # ---- #1400: the TARGET repository's declaration ------------------------------------------
        Mutation(
            "the cd target is used as-is, so a subdirectory has no declaration",
            '    return (Path(top) if top else path.resolve()), ""',
            '    return path.resolve(), ""',
            "a cd into a SUBDIRECTORY finds the repo's toplevel declaration",
        ),
        # ---- #1400: another repo's rules only when the create CERTAINLY files there --------------
        Mutation(
            "the followed cd's repo is never used, so the original bug returns",
            "                    target = found",
            "                    target = root",
            "cd into another repo: that repo's declaration applies, and passes",
        ),
        Mutation(
            "a repo named with -R on the create is ignored when following a cd",
            "        if cd is not None and repo is None and env_repo is None:",
            "        if cd is not None and env_repo is None:",
            "refused: a repo named with -R after the cd",
        ),
        Mutation(
            "a GH_REPO prefix on the create is ignored when following a cd",
            "        if cd is not None and repo is None and env_repo is None:",
            "        if cd is not None and repo is None:",
            "refused: GH_REPO on the create after the cd",
        ),
        Mutation(
            "a target with no remote is followed, though gh's destination is unknown",
            "                if theirs and (session_repo is None or session_repo not in theirs):",
            "                if (session_repo is None or session_repo not in theirs):",
            "a target with no remote keeps the session's rules",
        ),
        Mutation(
            "a target that files into the session's repo takes its own rules",
            "                if theirs and (session_repo is None or session_repo not in theirs):",
            "                if theirs:",
            "a cd into a clone of the session's own repo keeps the session's rules",
        ),
        Mutation(
            "only origin is read, so an upstream pointing at the session's repo is missed",
            "    return {r for line in out.splitlines() if len(line.split()) >= 2\n            for r in [norm_repo(line.split()[1])] if r}",
            "    return {r for r in [own_repo(root)] if r}",
            "...and so does a fork origin with the session repo as upstream",
        ),
        Mutation(
            "repo names are compared without lowercasing",
            "    s = s.strip().lower()",
            "    s = s.strip()",
            "-R spelled `-R Me/Skills` is the session's repo",
        ),
        Mutation(
            "a -R glued to its value is not read",
            "        elif a.startswith(\"-R\") and len(a) > 2:\n            repo = a[2:]",
            "        elif False:\n            repo = a[2:]",
            "CONTROL: a glued -R naming another repo needs one label, like the spaced form",
        ),
        Mutation(
            "a quoted <<X starts a heredoc and hides the create",
            "            if before.count(\"'\") % 2 or before.count('\"') % 2:\n                continue",
            "            if False:\n                continue",
            "a quoted <<X is text",
        ),
        Mutation(
            "a backslash-newline becomes a space, so `cre\\\\<nl>ate` is not a create",
            '    cmd = cmd.replace("\\\\\\n", "").replace("\\n", " ; ")',
            '    cmd = cmd.replace("\\\\\\n", " ").replace("\\n", " ; ")',
            "a backslash-newline joins",
        ),
        # ---- #1400: the ALLOWLIST -- each way a cd the create may not have followed is trusted -----
        Mutation(
            "a first word other than cd (pushd) is followed as a cd",
            '    if len(prefix) != 3 or prefix[0] != "cd" or prefix[2] != "&&":',
            '    if len(prefix) != 3 or prefix[2] != "&&":',
            "refused: pushd",
        ),
        Mutation(
            "an unterminated heredoc swallows the create after it",
            '                    raise ValueError(f"heredoc <<{tag} is never closed")',
            "                    pass",
            "an unterminated heredoc refuses rather than swallowing the create",
        ),
        Mutation(
            "every unterminated heredoc refuses, so a quoted <<EOF is a parse error again",
            '                if re.search(r"\\bgh\\s+issue\\s+create\\b", "\\n".join(lines[start_of_swallow:])):',
            "                if True:",
            "CONTROL: arithmetic << is not a parse error",
        ),
        Mutation(
            "a <<< herestring is read as a heredoc and swallows the create",
            """HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)""",
            """HEREDOC = re.compile(r"<<(-?)""",
            "a <<< herestring is not a heredoc",
        ),
        Mutation(
            "a command between the cd and the create is trusted",
            '    if len(prefix) != 3 or prefix[0] != "cd" or prefix[2] != "&&":',
            '    if len(prefix) < 3 or prefix[0] != "cd" or prefix[2] != "&&":',
            "refused: a command between the cd and the create",
        ),
        Mutation(
            "after a followed cd, a create behind env -C or command is trusted",
            '                    if cd is not None and (i != 0 or set(env) - {"GH_REPO"}):',
            '                    if cd is not None and (set(env) - {"GH_REPO"}):',
            "refused: env -C redirecting the create",
        ),
        Mutation(
            "after a followed cd, a GIT_DIR prefix on the create is trusted",
            '                    if cd is not None and (i != 0 or set(env) - {"GH_REPO"}):',
            "                    if cd is not None and (i != 0):",
            "refused: GIT_DIR on the create itself",
        ),
        Mutation(
            "a newline after && breaks the chain",
            '        if tok == ";" and items and items[-1] in ("&&", "||", "|"):\n            continue',
            "        if False:\n            continue",
            "a newline after && continues the chain",
        ),
    ),
)
