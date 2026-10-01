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
            "        cmd = _ansi_c(strip_heredocs(cmd))\n    except ValueError:",
            "        cmd = _ansi_c(cmd)\n    except ValueError:",
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
            '        if cd is not None and repo is None and env_repo is None and not os.environ.get("GH_REPO"):',
            '        if cd is not None and env_repo is None and not os.environ.get("GH_REPO"):',
            "refused: a repo named with -R after the cd",
        ),
        Mutation(
            "a GH_REPO prefix on the create is ignored when following a cd",
            '        if cd is not None and repo is None and env_repo is None and not os.environ.get("GH_REPO"):',
            '        if cd is not None and repo is None and not os.environ.get("GH_REPO"):',
            "refused: GH_REPO on the create after the cd",
        ),
        Mutation(
            "GH_REPO in the hook's environment is ignored when following a cd",
            '        if cd is not None and repo is None and env_repo is None and not os.environ.get("GH_REPO"):',
            '        if cd is not None and repo is None and env_repo is None:',
            "GH_REPO in the environment keeps the session's rules",
        ),
        Mutation(
            "a target with no remote is followed, though gh's destination is unknown",
            "                if theirs and ours and ours.isdisjoint(theirs):",
            "                if ours and ours.isdisjoint(theirs):",
            "a target with no remote keeps the session's rules",
        ),
        Mutation(
            "a session with no remote follows every cd",
            "                if theirs and ours and ours.isdisjoint(theirs):",
            "                if theirs and ours.isdisjoint(theirs):",
            "a session with no remote keeps its own rules",
        ),
        Mutation(
            "only the session's origin is compared, so its upstream is missed",
            "                theirs, ours = remotes(found), remotes(root)",
            "                theirs, ours = remotes(found), {r for r in [own_repo(root)] if r}",
            "a session whose upstream is the target's repo keeps its own rules",
        ),
        Mutation(
            "a target sharing the session's repo takes its own rules",
            "                if theirs and ours and ours.isdisjoint(theirs):",
            "                if theirs and ours:",
            "a cd into a clone of the session's own repo keeps the session's rules",
        ),
        Mutation(
            "a URL normalises to everything after the host, so an ssh port reads as a foreign 22/me/skills",
            '    m = re.search(r"([^/:@\\s]+)/([^/:@\\s]+?)(?:\\.git)?/*$", s.strip().lower())',
            '    m = re.search(r"github\\.com[/:](.+?)/([^/]+?)(?:\\.git)?/*$", s.strip().lower())',
            "a clone whose origin uses an ssh port is the session's repo",
        ),
        Mutation(
            "repo names are compared without lowercasing",
            '    m = re.search(r"([^/:@\\s]+)/([^/:@\\s]+?)(?:\\.git)?/*$", s.strip().lower())',
            '    m = re.search(r"([^/:@\\s]+)/([^/:@\\s]+?)(?:\\.git)?/*$", s.strip())',
            "-R spelled `-R Me/Skills` is the session's repo",
        ),
        Mutation(
            "only origin is read, so an upstream pointing at the session's repo is missed",
            "    return {r for line in out.splitlines() if len(line.split()) >= 2\n            for r in [norm_repo(line.split()[1])] if r}",
            "    return {r for r in [own_repo(root)] if r}",
            "...and so does a fork origin with the session repo as upstream",
        ),
        Mutation(
            "a -R glued to its value is not read",
            "        elif a.startswith(\"-R\") and len(a) > 2:\n            repo = a[2:]",
            "        elif False:\n            repo = a[2:]",
            "CONTROL: a glued -R naming another repo needs one label, like the spaced form",
        ),
        Mutation(
            "a quoted <<X starts a heredoc and hides the create",
            "            if before.count(\"'\") % 2:\n                continue            # inside single quotes `<<X` is text",
            "            if False:\n                continue            # inside single quotes `<<X` is text",
            "a quoted <<X is text",
        ),
        Mutation(
            "a backslash-newline becomes a space, so `cre\\\\<nl>ate` is not a create",
            '    cmd = cmd.replace("\\\\\\n", "").replace("\\n", " ; ")',
            '    cmd = cmd.replace("\\\\\\n", " ").replace("\\n", " ; ")',
            "a backslash-newline joins",
        ),
        # ---- #1440: a quoted `&&` is not the separator ------------------------------------------
        Mutation(
            "the raw text is not checked, so a quoted '&&' makes the followed shape",
            "                    cd = _cd_in_force(items[:start]) if raw_cd_shape else None",
            "                    cd = _cd_in_force(items[:start])",
            "a quoted '&&' does not make the followed cd shape",
        ),
        # ---- #1423: a create the parser cannot check is refused (owner decision) ---------------
        Mutation(
            "a path to gh is not gh, so /usr/bin/gh issue create goes unchecked",
            '    if i >= len(words) or os.path.basename(words[i]) != "gh":',
            '    if i >= len(words) or words[i] != "gh":',
            "a path to gh is gh",
        ),
        Mutation(
            "a create in backticks is not refused",
            '    if any(_names_create(span) for span in ticks[1::2]):',
            "    if False:",
            "a create inside backticks is refused",
        ),
        Mutation(
            "backticks are not paired, so a create after a closed one reads as inside it",
            '    if any(_names_create(span) for span in ticks[1::2]):',
            '    if any(_names_create(span) for span in ticks[1:]):',
            "CONTROL: a backtick BEFORE the create is not a hidden create",
        ),
        Mutation(
            "a $( ) substitution runs to the end, so a create after it reads as inside it",
            '        if _names_create(text[m.end():j - (0 if depth else 1)]):',
            '        if _names_create(text[m.end():]):',
            "CONTROL: $( ) BEFORE the create is not a hidden create",
        ),
        Mutation(
            "a create in $( ) is not refused",
            '        if _names_create(text[m.end():j - (0 if depth else 1)]):',
            "        if False:",
            "a create inside a `$( … )` substitution is refused",
        ),
        Mutation(
            "sh -c strings are not refused",
            "            if head in SHELLS and runs_string and _names_create(rest):",
            "            if False:",
            "a create inside `sh -c` is refused",
        ),
        Mutation(
            "a bundled -c (bash -lc) is not recognised",
            '            runs_string = any(w.startswith("-") and not w.startswith("--") and "c" in w for w in words[1:])',
            '            runs_string = "-c" in words[1:]',
            "a create inside `bash -c` is refused",
        ),
        Mutation(
            "eval strings are not refused",
            "            if head == \"eval\" and _names_create(rest):",
            "            if False:",
            "a create inside `eval` is refused",
        ),
        Mutation(
            "a hidden create is never checked",
            "    shape = hidden_create(cmd)\n    if shape:",
            "    shape = None\n    if shape:",
            "a create inside `sh -c` is refused",
        ),
        # Final review of #1454: no false refusals of quoted text, and no wrapper escape.
        Mutation(
            "single-quoted text is scanned for substitutions, so a quoted commit message is refused",
            "    subst = \"\".join(literal)",
            "    subst = body",
            "CONTROL: single-quoted backticks is not a hidden create",
        ),
        Mutation(
            "a heredoc opened inside \"$( is read as text, so its body is scanned",
            "            if before.count('\"') % 2 and \"$(\" not in before[before.rfind('\"'):]:",
            "            if before.count('\"') % 2:",
            "CONTROL: a commit message heredoc inside $( ) is not a hidden create",
        ),
        Mutation(
            "wrappers are not peeled, so env sh -c escapes",
            "    while words and os.path.basename(words[0]) in WRAPPERS:\n        wrapper = os.path.basename(words.pop(0))",
            "    while False:\n        wrapper = os.path.basename(words.pop(0))",
            "a create behind `env` is refused",
        ),
        Mutation(
            "a wrapper's flags are not peeled, so sudo -E bash -c escapes",
            "        while words and words[0].startswith(\"-\"):\n            words.pop(0)\n        if wrapper in",
            "        while False:\n            words.pop(0)\n        if wrapper in",
            "a create behind `sudo` is refused",
        ),
        Mutation(
            "timeout's duration is not peeled, so timeout 5 bash -c escapes",
            '        if wrapper in ("timeout", "nice") and words and re.fullmatch(r"[\\d.]+[smhd]?", words[0]):',
            "        if False:",
            "a create behind `timeout` is refused",
        ),
        # ---- #1462 / #1467 / #1468 (group C2) ---------------------------------------------------
        Mutation(
            "gh issue new is not a create",
            '    if j + 1 < len(words) and words[j] == "issue" and words[j + 1] in ("create", "new"):',
            '    if j + 1 < len(words) and words[j] == "issue" and words[j + 1] == "create":',
            "gh issue new (an alias): its missing label is refused",
        ),
        Mutation(
            "gh's global flags are not skipped, so gh --repo o/r issue create is not seen",
            "    while j < len(words) and words[j].startswith(\"-\"):",
            "    while False:",
            "gh --repo o/r issue create (a global flag first): its missing label is refused",
        ),
        Mutation(
            "quotes are not removed before matching, so bash -c 'gh issue \"create\"' escapes",
            "    return bool(CREATE_TEXT.search(\" \" + text.replace(\"\\\\\\n\", \"\").replace('\"', \"\").replace(\"'\", \"\")))",
            "    return bool(CREATE_TEXT.search(\" \" + text))",
            "a create in `bash -c` is refused and named",
        ),
        Mutation(
            "a heredoc fed to a shell is not refused",
            '            if (feeder in SHELLS or feeder == "eval") and _names_create(text):',
            "            if False:",
            "a create in a heredoc fed to `bash` is refused and named",
        ),
        Mutation(
            "an unquoted heredoc's substitutions are not scanned",
            "        if not quoted:\n            # An escaped character",
            "        if False:\n            # An escaped character",
            "a $( ) create inside an unquoted heredoc is refused",
        ),
        Mutation(
            "a \\EOF delimiter reads as unquoted, so its literal body is scanned",
            "            quoted = bool(m.group(2) or m.group(3))",
            "            quoted = bool(m.group(3))",
            "CONTROL: a \\EOF delimiter is quoted, so its body is literal",
        ),
        Mutation(
            "a pipe into a shell is not refused",
            '                if prev_op in ("|", "|&") and _names_create(prev_text):',
            "                if False:",
            "a create in a pipe into `bash` is refused and named",
        ),
        Mutation(
            "a herestring fed to a shell is not refused",
            '                if here is not None and _names_create(" ".join([words[here][3:]] + words[here + 1:])):',
            "                if False:",
            "a create in a herestring fed to `bash` is refused and named",
        ),
        Mutation(
            "a backslash escape is not honoured, so an escaped backtick reads as a substitution",
            '        if ch == "\\\\":\n            i += 1                   # the escaped character is literal: never a substitution\n            continue\n',
            "",
            "CONTROL: an escaped backtick inside double quotes is text",
        ),
        # Final review of #1477.
        Mutation(
            "escapes are kept in an unquoted heredoc, so an escaped backtick reads as a substitution",
            '            found = _substituted_create(re.sub(r"\\\\.", "", text, flags=re.S))',
            "            found = _substituted_create(text)",
            "CONTROL: an escaped backtick in a PR body's unquoted heredoc is text",
        ),
        Mutation(
            "a heredoc piped into a shell is not seen",
            '        feeders = [_command_word(opener[:mark])] + ([_command_word(after)] if "|" in after else [])',
            "        feeders = [_command_word(opener[:mark])]",
            "refused as a heredoc fed to `bash`",
        ),
        Mutation(
            "a herestring glued to its word is not seen",
            '                here = next((k for k, w in enumerate(words) if w.startswith("<<<")), None)',
            '                here = next((k for k, w in enumerate(words) if w == "<<<"), None)',
            "refused as a herestring fed to `bash`",
        ),
        Mutation(
            "only the segment just before the shell is read, so a multi-stage pipe escapes",
            '            prev_text = (prev_text + " " + raw_seg) if prev_op in ("|", "|&") else raw_seg',
            "            prev_text = raw_seg",
            "refused as a pipe into `bash`",
        ),
        Mutation(
            "|& is not a pipe",
            '                if prev_op in ("|", "|&") and _names_create(prev_text):',
            '                if prev_op == "|" and _names_create(prev_text):',
            "refused as a pipe into `bash`",
        ),
        # #1489: a script fed to a shell by redirect.
        Mutation(
            "a redirected script is not read, so bash < file escapes",
            "                if script is not None and _names_create(script):",
            "                if False:",
            "a spaced redirect feeding a script with a create to a shell is refused",
        ),
        # #1489 review: each fix below has a fixture that must notice it going.
        Mutation(
            "stdin is read as the script even when a script operand is given",
            "        return has_s                 # an operand: the script is that file, unless -s",
            "        return True",
            "stdin is data for a script operand, allowed",
        ),
        Mutation(
            "`-s` is ignored, so bash -s arg1 < file escapes",
            "                has_s = True",
            "                pass",
            "'bash -s arg1 < ': stdin is the script",
        ),
        Mutation(
            "`0<` is not read as a redirect, so bash 0< file escapes",
            '        if w.startswith("0<"):',
            "        if False:",
            "bash 0< ",
        ),
        Mutation(
            "a glued `sh<f` stays one word, so its shell is never seen",
            "                if os.path.basename(pre) in SHELLS:",
            "                if False:",
            "'sh<': refused as a script fed by redirect",
        ),
        Mutation(
            "a literal cd no longer moves the directory, so a relative script is read from the session's",
            "                    here_dir = here_dir / os.path.expanduser(arg)",
            "                    pass",
            "a relative script is read from the cd target",
        ),
        Mutation(
            "a cd inside ( ) is followed past the ), so a script is read from a directory the shell never entered",
            "                    dir_stack.append(here_dir)",
            "                    pass",
            "the subshell's cd does not outlive it",
        ),
        Mutation(
            "a cd to a run-time path is followed as if literal, so the directory stays the last known one",
            '                if here_dir is None or head != "cd" or not arg or arg == "-" or "$" in arg or "`" in arg:',
            '                if here_dir is None or head != "cd" or not arg or arg == "-":',
            "after a cd it cannot resolve",
        ),
        # ---- #1495: the five #1489 edge cases --------------------------------------------------------
        Mutation(
            "a cd to a missing directory is followed, so the session's script is never read",
            "                elif (here_dir / os.path.expanduser(arg)).is_dir():",
            "                else:",
            "a cd to a missing directory fails and changes nothing",
        ),
        Mutation(
            "a bundled -o is a plain flag, so `-eo pipefail` reads pipefail as the script",
            '            if w in ("--rcfile", "--init-file") or re.fullmatch(r"[-+][A-Za-z]*[oO]", w):',
            '            if w in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):',
            "a bundled -o takes a value",
        ),
        Mutation(
            "a fd duplication is split at its &, so `bash 2>&1 < f` loses its redirect",
            '    text = re.sub(r"(\\d*[<>])&(\\d+|-)", r"\\1@\\2", text)',
            "    text = text",
            "the & of a fd duplication is not a separator",
        ),
        Mutation(
            "&> is read as a background &, so `bash &>log < f` loses its redirect",
            '    return re.sub(r"(?<![&|<>])&(>>?)", r"\\1", text)',
            "    return text",
            "&> is a redirect, not a background &",
        ),
        Mutation(
            "\\xHH is not decoded, so -l $'\\x66eature' reads as 66eature",
            "                return chr(int(text[j + 1:k], base)), k",
            "                return text[j + 1:k], k",
            "x66eature'` is the label `feature`",
        ),
        Mutation(
            "\\NNN octal is not decoded",
            "        return chr(int(text[j:k], 8) & 0xFF), k",
            "        return text[j:k], k",
            "146eature'` is the label `feature`",
        ),
        Mutation(
            "ANSI-C quoting is not decoded, so valid bash is refused as unparseable",
            "        cmd = _ansi_c(strip_heredocs(cmd))",
            "        cmd = strip_heredocs(cmd)",
            "before a harmless redirected script is allowed",
        ),
        Mutation(
            "every unparseable command is refused, even one naming no create",
            "    if _names_create(cmd) or SHELL_REDIRECT.search(cmd):",
            "    if True:",
            "an unparseable command naming no create and no redirect is allowed",
        ),
        Mutation(
            "`$HOME` is not expanded, so bash < $HOME/x.sh escapes",
            '        target = re.sub(r"^\\$(HOME|\\{HOME\\})(?=/|$)", lambda _: os.path.expanduser("~"), target)',
            "        pass",
            "$HOME expands and the script is read",
        ),
        Mutation(
            "a large script is skipped instead of read, so a create at its top escapes",
            "            return fh.read(1_000_000).decode(\"utf-8\", errors=\"replace\")",
            "            return None if path.stat().st_size > 1_000_000 else fh.read().decode(\"utf-8\", errors=\"replace\")",
            "a script over 1 MB with a create in its first 1 MB is refused",
        ),
        Mutation(
            "only a spaced `<` is read, so bash <file escapes",
            '        if w.startswith("<") and not w.startswith(("<<", "<(")) and len(w) > 1:',
            "        if False:",
            "a glued redirect feeding a script with a create to a shell is refused",
        ),
        # ---- #1400: the ALLOWLIST -- each way a cd the create may not have followed is trusted -----
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
            '    if len(prefix) != 3 or prefix[2] != "&&":',
            '    if len(prefix) < 3 or prefix[2] != "&&":',
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
