"""Mutation guard: hook_command_cwd. Declared here, run by scripts/mutation_check.py (#1509).

`lib/command_cwd.py` decides which repository's PR template guard-claims judges a body against. It is an
allowlist (#1516, round 3): each mutation widens the grammar it follows, so a shape outside it is judged
against a guessed directory again, or narrows it, so a shape inside it stops being followed.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_command_cwd",
    subject="plugins/rails-flow/hooks/scripts/lib/command_cwd.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only guard-claims drives this subject (#1599): with no `--only`, every one of the 53 mutants re-ran all twelve
    # fixture groups (8559 s of CPU in one run). And each mutant needs only the fixture its `expects` names, so
    # `--match` narrows it to that one, after a control run of the unmutated code that must pass.
    selftest_args=("--only", "guard_claims"),
    narrow_with="--match",
    # The same staging as hook_guard_claims: the harness runs every hook from the whole directory.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            'the explicit refusal of a marked cd path is dropped: normpath then collapses it (#1605 review)',
            '    if GLOB_MARK in a:',
            '    if False:',
            'an unquoted `[b]` glob followed by `/..` (#1605: normpath would collapse it back to the start) is NOT checked',
        ),
        Mutation(
            'every glob character, not only `[` and `]`, may be a lone word (#1605 review)',
            '            lone = c in "[]" and word_start',
            '            lone = word_start',
            'a bare unquoted `?` as a cd path (#1605) is NOT checked',
        ),
        Mutation(
            'prepare() no longer marks an unquoted glob or brace character (#1605)',
            '            out.append(GLOB_MARK if c in GLOB_CHARS and not lone else c)',
            '            out.append(c)',
            'an unquoted `{b1,b2}` brace list in a cd path (#1605) is NOT checked',
        ),
        Mutation(
            'a lone `[` (the test command) is marked as a glob too (#1605)',
            '            out.append(GLOB_MARK if c in GLOB_CHARS and not lone else c)',
            '            out.append(GLOB_MARK if c in GLOB_CHARS else c)',
            'a `[ ... ]` test before gh: a lone `[` is not a glob (#1605) is judged in the starting repo',
        ),
        Mutation(
            'a quoted or escaped glob character is refused too (#1605)',
            '    if GLOB_MARK in a:',
            '    if GLOB_MARK in a or any(g in a for g in GLOB_CHARS):',
            'a double-quoted glob path, which the shell takes literally (#1605) is followed',
        ),
        Mutation(
            'a cd joined by || counts as having run',
            'SEPS = {"&&", ";"}',
            'SEPS = {"&&", ";", "||"}',
            'a cd joined by || is NOT checked, with the notice',
        ),
        Mutation(
            'any command before the gh is skipped, as if it could not move the directory (N4)',
            '        if seg[0] != "cd":\n            raise Unresolved(',
            '        if seg[0] != "cd":\n            continue\n            raise Unresolved(',
            'N4 `false && cd B; gh` is NOT checked, with the notice',
        ),
        Mutation(
            'every cd is ignored: the starting directory is always returned',
            '    if all(_safe(seg) and not writes for seg, _, _, writes in done):',
            '    if True:',
            "`cd B;` is followed to the cd target's template",
        ),
        Mutation(
            'a blank segment (a comment line) is read as a command',
            '        if not seg:\n            continue',
            '        if False:\n            continue',
            "a leading comment line is followed to the cd target's template",
        ),
        Mutation(
            'an input redirect on a cd is allowed',
            '        if sep not in SEPS or not clean:',
            '        if sep not in SEPS:',
            'a cd with an input redirect is NOT checked, with the notice',
        ),
        Mutation(
            'no redirect on a cd is allowed',
            'CD_REDIRECTS = {">", ">>", ">&"}',
            'CD_REDIRECTS: set = set()',
            "a cd with its stdout redirected is followed to the cd target's template",
        ),
        Mutation(
            "a redirection's target counts as a cd argument",
            '            if redirect:                    # the redirection\'s target, not an argument\n                redirect = False\n                writes = writes or not (t == "/dev/null" or t.isdigit() or t == "-")\n                continue\n',
            '',
            "a cd with its stdout redirected is followed to the cd target's template",
        ),
        Mutation(
            'comments are not dropped',
            '        elif c == "#" and word_start:',
            '        elif False:',
            "a leading comment with an apostrophe is followed to the cd target's template",
        ),
        Mutation(
            "shlex's own comment handling is left on",
            '    lex.commenters = ""                     # prepare() has dropped the real comments\n',
            '',
            "a `#` inside a word is followed to the cd target's template",
        ),
        Mutation(
            'a `#` mid-word starts a comment',
            '        word_start = i == 0 or (cmd[i - 1] in META and not escaped)',
            '        word_start = True',
            "a `#` inside a word is followed to the cd target's template",
        ),
        Mutation(
            'an escaped space ends a word (S-b)',
            '        word_start = i == 0 or (cmd[i - 1] in META and not escaped)',
            '        word_start = i == 0 or cmd[i - 1] in META',
            "an escaped space before `#` (S-b) is followed to the cd target's template",
        ),
        Mutation(
            'quotes are not tracked, so a quoted `#` is a comment',
            '        elif c in "\'\\"":\n            q = c\n',
            '        elif c in "\'\\"":\n            q = ""\n',
            "a `#` inside a quoted path is followed to the cd target's template",
        ),
        Mutation(
            "an fd number apart from its `>` is the redirection's",
            '        elif c.isdigit() and word_start and re.match(r"\\d+[<>]", cmd[i:]):',
            '        elif c.isdigit() and word_start and re.match(r"\\d+\\s*[<>]", cmd[i:]):',
            "`cd 5 >/dev/null` (5 is the directory, not an fd) is followed to the cd target's template",
        ),
        Mutation(
            'an fd number touching its `>` is a cd argument',
            '        elif c.isdigit() and word_start and re.match(r"\\d+[<>]", cmd[i:]):',
            '        elif False:',
            "a cd with its stderr redirected is followed to the cd target's template",
        ),
        Mutation(
            'an unbalanced quote before gh falls back to the start',
            '        raise Unresolved(f"the command could not be lexed: {e}") from e',
            '        return start',
            'an unbalanced quote before the cd is NOT checked, with the notice',
        ),
        Mutation(
            'no gh command word falls back to the start',
            '    raise Unresolved("no gh pr create|edit / issue comment command word was found")',
            '    return start',
            'gh behind `sudo` with no cd is NOT checked, with the notice',
        ),
        Mutation(
            'a cd to a variable is taken literally',
            '    if a.startswith("-") or "$" in a or "`" in a:',
            '    if a.startswith("-"):',
            'a cd to a variable is NOT checked, with the notice',
        ),
        Mutation(
            'a cd to a missing directory is followed anyway',
            '    if not os.path.isdir(path):',
            '    if False:',
            'a cd to a missing directory is NOT checked, with the notice',
        ),
        Mutation(
            'CDPATH is ignored',
            '    if os.environ.get("CDPATH") and',
            '    if False and',
            'a relative cd with CDPATH set',
        ),
        Mutation(
            'a cd with two arguments takes the first',
            '    if len(args) != 1:',
            '    if len(args) < 1:',
            'a cd with two arguments is NOT checked, with the notice',
        ),
        Mutation(
            '`~/` is not expanded',
            '    if a == "~" or a.startswith("~/"):\n        a = home + a[1:]\n    elif a.startswith("~"):',
            '    if a.startswith("~"):',
            "a `~/` path is followed to the cd target's template",
        ),
        Mutation(
            '`~user` is taken literally',
            '    elif a.startswith("~"):\n        raise Unresolved(f"cd {a}")\n',
            '',
            'a cd to ~user is NOT checked, with the notice',
        ),
        Mutation(
            "env's options are peeled, so `env -C dir gh` is found (N1)",
            '            while w and ASSIGN.match(w[0]):\n                w.pop(0)\n        elif h == "command":',
            '            while w and (ASSIGN.match(w[0]) or w[0].startswith("-")):\n                w.pop(0)\n        elif h == "command":',
            'N1 `env -C/dir` is NOT checked, with the notice',
        ),
        Mutation(
            'env is not peeled',
            '        if h == "env":',
            '        if False:',
            "`env gh` is followed to the cd target's template",
        ),
        Mutation(
            'an assignment before gh is not peeled',
            '    w = list(words)\n    while w and ASSIGN.match(w[0]):\n        w.pop(0)\n',
            '    w = list(words)\n',
            "`VAR=1 gh` is followed to the cd target's template",
        ),
        Mutation(
            '`command -p` is not peeled',
            '            if w and w[0] == "-p":\n                w.pop(0)\n        elif h in ("exec"',
            '            pass\n        elif h in ("exec"',
            "`command -p gh` is followed to the cd target's template",
        ),
        Mutation(
            'nohup is not peeled',
            '        elif h in ("exec", "nohup"):',
            '        elif h in ("exec",):',
            "`nohup gh` is followed to the cd target's template",
        ),
        Mutation(
            '`nice -n N` keeps its N',
            '                del w[:2]\n',
            '                pass\n',
            "`nice -n 5 gh` is followed to the cd target's template",
        ),
        Mutation(
            "timeout's duration is read as the command",
            '            w = w[1:]                       # the duration',
            '            pass',
            "`timeout 60 gh` is followed to the cd target's template",
        ),
        Mutation(
            "timeout's option arguments are read as the duration",
            '                del w[:2 if w[0] in ("-s", "-k", "--signal", "--kill-after") else 1]',
            '                del w[:1]',
            "`timeout -k 5 60 gh` is followed to the cd target's template",
        ),
        Mutation(
            '`time -p` is not peeled',
            '        elif h == "time":',
            '        elif False:',
            "`time -p gh` is followed to the cd target's template",
        ),
        Mutation(
            'a gh named by its path is not found',
            'os.path.basename(w[0]) == "gh" and (',
            'w[0] == "gh" and (',
            "an absolute path to gh is followed to the cd target's template",
        ),
        Mutation(
            # Round 4: the shortcut is an allowlist.
            'the no-cd shortcut takes any command word (round 4, B2)',
            '    return w[0] in SAFE',
            '    return True',
            'B2 zsh `chdir` is NOT checked, with the notice',
        ),
        Mutation(
            'an assignment before a SAFE command defeats the shortcut',
            '    w = list(seg)\n    while w and ASSIGN.match(w[0]):\n        w.pop(0)\n    if not w:',
            '    w = list(seg)\n    if not w:',
            'known-safe commands and an assignment before gh is judged in the starting repo',
        ),
        Mutation(
            # Round 4.
            '`cd -P` is peeled and resolved logically again (round 4, B1)',
            'def _target(args: list[str], here: str, home: str) -> str:\n    if len(args) != 1:',
            'def _target(args: list[str], here: str, home: str) -> str:\n    if args and args[0] in ("-P", "-L"):\n        args = args[1:]\n    if len(args) != 1:',
            'B1 `cd -P link/..` is NOT checked, with the notice',
        ),
        Mutation(
            # Round 5: GIT_DIR / GIT_WORK_TREE.
            'GIT_DIR on the gh command is ignored (round 5)',
            '    if found and any(REPO_ENV.match(x) for x in words[:len(words) - len(w)]):',
            '    if False:',
            'R5 `GIT_DIR=B/.git gh` is NOT checked, with the notice',
        ),
        Mutation(
            'GIT_WORK_TREE is not a repository-picking variable (round 5)',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'REPO_ENV = re.compile(r"\\A(GIT_DIR|HOME|XDG_CONFIG_HOME)=")',
            'R5 `GIT_WORK_TREE=B gh` is NOT checked, with the notice',
        ),
        Mutation(
            'a persisting GIT_DIR assignment before gh is safe (round 5)',
            '        return not any(REPO_ENV.match(x) for x in seg)',
            '        return True',
            'R5 `GIT_DIR=…;` before gh is NOT checked, with the notice',
        ),
        Mutation(
            'an inherited GIT_DIR is ignored (round 5)',
            '    if any(k.startswith(("GIT_", "GH_")) and k not in INHERITED_EXEMPT for k in os.environ):',
            '    if False:',
            'GIT_DIR inherited by the hook is NOT checked',
        ),
        Mutation(
            # Round 6: the GIT_* / GH_* class.
            'the prefix test narrows to GIT_ only (round 6)',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'REPO_ENV = re.compile(r"\\A((GIT)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'R6 `GH_HOST` (the class) is NOT checked, with the notice',
        ),
        Mutation(
            'the prefix test narrows back to a list (round 6)',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'REPO_ENV = re.compile(r"\\A(GIT_DIR|GIT_WORK_TREE|GH_REPO|GH_HOST|HOME|XDG_CONFIG_HOME)=")',
            'R6 an arbitrary `GIT_FOO=1` (the class) is NOT checked, with the notice',
        ),
        Mutation(
            'the inherited test narrows to GIT_ only (round 6)',
            '    if any(k.startswith(("GIT_", "GH_")) and k not in INHERITED_EXEMPT for k in os.environ):',
            '    if any(k.startswith(("GIT_",)) and k not in INHERITED_EXEMPT for k in os.environ):',
            'GH_HOST inherited by the hook is NOT checked',
        ),
        Mutation(
            "the harness's GIT_EDITOR is not exempt (round 6)",
            ' and k not in INHERITED_EXEMPT for k in os.environ):',
            ' for k in os.environ):',
            'an inherited GIT_EDITOR (the harness sets it) is still judged',
        ),
        Mutation(
            # Round 7: the config-redirecting family.
            'HOME set by the command is not refused (round 7)',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|XDG_CONFIG_HOME)=")',
            'R7 `HOME=… gh` is NOT checked, with the notice',
        ),
        Mutation(
            'XDG_CONFIG_HOME set by the command is not refused (round 7)',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")',
            'REPO_ENV = re.compile(r"\\A((GIT|GH)_[A-Za-z0-9_]*|HOME)=")',
            'R7 `XDG_CONFIG_HOME=… gh` is NOT checked, with the notice',
        ),
        Mutation(
            'any git subcommand is SAFE (round 7)',
            '        return bool(a) and a[0] in GIT_SAFE_SUB',
            '        return True',
            'R7 `git config --global …insteadOf` before gh is NOT checked, with the notice',
        ),
        Mutation(
            'an unknown git option is skipped (round 7)',
            '            else:\n                return False\n        return bool(a)',
            '            else:\n                a.pop(0)\n        return bool(a)',
            'R7 an unknown git option before gh is NOT checked, with the notice',
        ),
        Mutation(
            '`git -c` takes no value (round 7)',
            '                del a[:GIT_OPTS[a[0]]]',
            '                a.pop(0)',
            '`git -c url…insteadOf=… status` before gh is judged in the starting repo',
        ),
        Mutation(
            '`--config-env=` is not a git option (round 7)',
            '            elif a[0].startswith(("--config-env=", "--git-dir=", "--work-tree=")):',
            '            elif a[0].startswith(("--git-dir=", "--work-tree=")):',
            '`git --config-env=…` before gh is judged in the starting repo',
        ),
        Mutation(
            'any gh subcommand is SAFE (round 7)',
            '        return len(w) > 1 and w[1] in GH_SAFE_SUB',
            '        return True',
            'R7 `gh repo set-default` before gh is NOT checked, with the notice',
        ),
        Mutation(
            'a segment writing a file is SAFE (round 7)',
            '    if all(_safe(seg) and not writes for seg, _, _, writes in done):',
            '    if all(_safe(seg) for seg, _, _, writes in done):',
            'R7 a write into .git/config before gh is NOT checked, with the notice',
        ),
        Mutation(
            'a redirect to /dev/null or an fd counts as a write (round 7)',
            '                writes = writes or not (t == "/dev/null" or t.isdigit() or t == "-")',
            '                writes = True',
            'a redirect to /dev/null and an fd before gh is judged in the starting repo',
        ),
        Mutation(
            'sed is SAFE again, so `sed -i` can rewrite .git/config (round 7)',
            '"mkdir", "touch", "jq"}',
            '"mkdir", "touch", "jq", "sed"}',
            'R7 `sed -i` on .git/config before gh is NOT checked, with the notice',
        ),
    ),
)
