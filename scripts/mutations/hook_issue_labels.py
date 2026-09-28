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
            "glued punctuation is left as one word, so the create after `);` vanishes",
            "        if tok and set(tok) <= set(\";&|()\"):\n            i = 0",
            "        if False:\n            i = 0",
            "refused: a cd inside a subshell",
        ),
        Mutation(
            "another repo's issue is held to this project's groups",
            "        foreign = repo is not None and repo != mine",
            "        foreign = False",
            "another repo: one label is enough",
        ),
        # ---- #1400: the TARGET repository's declaration ------------------------------------------
        Mutation(
            "the session's declaration is applied again, whatever repository the create runs in",
            "        target, why = target_root(cd, root)",
            '        target, why = root, ""',
            "cd into another repo: that repo's declaration applies, and passes",
        ),
        Mutation(
            "the cd target is used as-is, so a subdirectory has no declaration",
            '    return (Path(top) if top else path.resolve()), ""',
            '    return path.resolve(), ""',
            "a cd into a SUBDIRECTORY finds the repo's toplevel declaration",
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
        # ---- #1400: the ALLOWLIST -- each way a cd the create may not have followed is trusted -----
        Mutation(
            "a first word other than cd (pushd) is followed as a cd",
            '    if len(prefix) < 3 or prefix[0] != "cd" or prefix[2] != "&&":',
            "    if len(prefix) < 3:",
            "refused: pushd",
        ),
        Mutation(
            "a command whose first word is not cd reads as having no cd at all",
            "    if not any(_is_cd_word(t) for t in prefix):\n        return None",
            '    if prefix[:1] != ["cd"]:\n        return None',
            "refused: a cd that is not the first command",
        ),
        Mutation(
            "a cd glued into a backtick substitution is not seen",
            '    return any(piece in CD_WORDS for piece in re.split(r"[`=$(){};]+", tok))',
            "    return tok in CD_WORDS",
            "refused: a cd inside backticks",
        ),
        Mutation(
            "cd - or a $VAR operand is followed as a directory",
            '    if target in ("-", "--") or target.startswith("-") or "$" in target or "`" in target:',
            "    if False:",
            "refused: a cd to a variable",
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
            "CONTROL: a quoted <<EOF on the create's own line is not a parse error",
        ),
        Mutation(
            "a <<< herestring is read as a heredoc and swallows the create",
            """HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)""",
            """HEREDOC = re.compile(r"<<(-?)""",
            "a <<< herestring is not a heredoc",
        ),
        Mutation(
            "a command between the cd and the create is trusted",
            "    if len(prefix) != 3:\n        return UNKNOWN",
            "    if False:\n        return UNKNOWN",
            "refused: a command between the cd and the create",
        ),
        Mutation(
            "after a followed cd, a create behind env -C or command is trusted",
            '                    if cd not in (None, UNKNOWN) and (i != 0 or set(env) - {"GH_REPO"}):',
            '                    if cd not in (None, UNKNOWN) and (set(env) - {"GH_REPO"}):',
            "refused: env -C redirecting the create",
        ),
        Mutation(
            "after a followed cd, a GIT_DIR prefix on the create is trusted",
            '                    if cd not in (None, UNKNOWN) and (i != 0 or set(env) - {"GH_REPO"}):',
            "                    if cd not in (None, UNKNOWN) and (i != 0):",
            "refused: GIT_DIR on the create itself",
        ),
        Mutation(
            "a cd into a clone of the session's repo takes the clone's (missing) rules",
            "        elif cd is not None and session_repo is not None and own_repo(target) == session_repo:",
            "        elif False:",
            "a cd into a clone of the session's own repo keeps the session's rules",
        ),
        Mutation(
            "a newline after && breaks the chain",
            '        if tok == ";" and items and items[-1] in ("&&", "||", "|"):\n            continue',
            "        if False:\n            continue",
            "a newline after && continues the chain",
        ),
    ),
)
