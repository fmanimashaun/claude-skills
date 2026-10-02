"""Mutation guard: hook_command_cwd. Declared here, run by scripts/mutation_check.py (#1509).

`lib/command_cwd.py` decides which repository's PR template guard-claims judges a body against. Each
mutation makes it name the wrong directory again: a subshell's cd leaks out, a cd that may not have run
counts, a heredoc body is lexed as shell, or an unresolvable target is guessed instead of refused.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_command_cwd",
    subject="plugins/rails-flow/hooks/scripts/lib/command_cwd.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # The same staging as hook_guard_claims: the harness runs every hook from the whole directory.
    needs=("plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           "plugins/rails-flow/scripts/ci_verdict_hint.py"),
    mutations=(
        Mutation(
            "a cd in a while/until condition is not followed (R1516-1)",
            'KEYWORDS = {"{", "}", "!", "if", "then", "elif", "else", "fi", "do", "done", "while", "until", "time"}',
            'KEYWORDS = {"{", "}", "!", "if", "then", "elif", "else", "fi", "do", "done", "time"}',
            "a cd in a while condition is followed",
        ),
        Mutation(
            "builtin/command before cd is read as the command (R1516-1)",
            'WRAPPERS = {"builtin", "command"}',
            'WRAPPERS: set = set()',
            "builtin cd is followed",
        ),
        Mutation(
            "the walk stops at an earlier command that merely mentions gh pr create (R1516-2)",
            "        if _is_gh(w):",
            '        if w[0] == "echo" or _is_gh(w):',
            "a quoted `gh pr create` earlier in the chain is followed",
        ),
        Mutation(
            "a redirection's target counts as a cd argument (R1516-5)",
            '                    redirect = True         # prepare()',
            '                    redirect = False         # prepare()',
            "a cd with its stderr redirected is followed",
        ),
        Mutation(
            "a case pattern's ) is read as a subshell's close (R1516-5)",
            '                elif cases and cases[-1][2] == "pattern" and op == ")":',
            "                elif False:",
            "a cd and gh in the same case branch is followed",
        ),
        Mutation(
            "after esac, a branch's cd is forgotten and the session template judged",
            "            after_case_unknown = True       # which branch ran is unknown after esac",
            "            pass",
            "a gh after a case whose branch moved the directory is NOT checked",
        ),
        Mutation(
            "the resolver ignores the payload's cwd and starts in its own (R1516-7)",
            "    start = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else os.getcwd()",
            "    start = os.getcwd()",
            "the command starts in the payload's cwd",
        ),
        Mutation(
            "a brace group's cd is not followed (`{` read as the command)",
            'KEYWORDS = {"{", "}", "!", "if", "then", "elif", "else", "fi", "do", "done", "while", "until", "time"}',
            'KEYWORDS = {"!", "if", "then", "elif", "else", "fi", "do", "done", "while", "until", "time"}',
            "a cd inside a brace group runs in this shell",
        ),
        Mutation(
            "a negated cd is followed as if it ran",
            '                if w[0] == "!":\n                    raise Unresolved("a negated command before gh")\n',
            '',
            "(a negated cd)",
        ),
        Mutation(
            "a cd inside a subshell outlives it",
            "                here = stack.pop() if stack else here",
            "                stack.pop() if stack else None",
            "a cd inside a subshell does not outlive it",
        ),
        Mutation(
            "a cd joined by || counts as having run",
            'APPLIES = {"&&", ";", ";;", ";&", ";;&"}',
            'APPLIES = {"&&", ";", ";;", ";&", ";;&", "||"}',
            "(a cd joined by ||)",
        ),
        Mutation(
            "heredoc bodies are lexed as shell, so an apostrophe in one hides the cd",
            '                pending.append((word, dash))',
            '                pass',
            "a heredoc body before the cd does not stop it being followed",
        ),
        Mutation(
            "a cd to a missing directory is followed anyway",
            "    if not os.path.isdir(path):",
            "    if False:",
            "(a cd to a missing directory)",
        ),
        Mutation(
            "a cd to a variable is taken literally",
            '    if a == "-" or "$" in a or "`" in a:',
            '    if a == "-":',
            "(a cd to a variable)",
        ),
        Mutation(
            "the cd is ignored: the hook's own directory is always returned",
            "            raise Found(here)\n",
            "            raise Found(start)\n",
            "a `cd <other repo>` is judged against that repo's template",
        ),
        Mutation(
            # Re-review blocker 1: a regression from e16c6b5.
            'a gh behind env/exec/nohup/nice/timeout is not found, so the cd before it is lost (R2-1)',
            '            elif w[0] in EXTERNAL:',
            '            elif False:',
            '`env gh` is followed',
        ),
        Mutation(
            'a gh named by its path is not found (R2-1)',
            'os.path.basename(w[0]) == "gh"',
            'w[0] == "gh"',
            'an absolute path to gh is followed',
        ),
        Mutation(
            '`command -p` is not peeled (R2-1)',
            '                    while w and w[0] in ("-p", "--"):',
            '                    while w and w[0] in ("--",):',
            '`command -p gh` is followed',
        ),
        Mutation(
            "timeout's duration is read as the command (R2-1)",
            '                    w.pop(0)                # the duration',
            '                    pass',
            '`timeout 60 gh` is followed',
        ),
        Mutation(
            'no gh command word after a cd falls back to the starting directory (R2-1)',
            '    if CD_ANYWHERE.search(cmd):\n        raise Unresolved("no gh',
            '    if False:\n        raise Unresolved("no gh',
            'gh behind `sudo` after a cd is NOT checked',
        ),
        Mutation(
            'a cd behind a program wrapper counts as the builtin (R2-1)',
            '            if external:\n                raise Unresolved("a cd run as a program, behind a wrapper")\n',
            '',
            'a cd run as a program (`env cd`) is NOT checked',
        ),
        Mutation(
            # Re-review blocker 2.
            'a comment is not dropped, so an apostrophe in it is lexed as a quote (R2-2)',
            '        elif c == "#" and word_start:',
            '        elif False:',
            'a leading comment with an apostrophe is followed',
        ),
        Mutation(
            "shlex's own comment handling is left on, so a `#` ends the whole command (R2-2)",
            '    lex.commenters = ""                     # prepare() has dropped the real comments\n',
            '',
            '`issue#12`, which is one word, not a comment is followed',
        ),
        Mutation(
            'a `#` mid-word starts a comment (R2-2)',
            '        word_start = i == 0 or cmd[i - 1] in META',
            '        word_start = True',
            '`issue#12`, which is one word, not a comment is followed',
        ),
        Mutation(
            # Re-review blocker 3.
            'a `<<` inside quotes opens a heredoc (R2-3)',
            '        if q:                               # inside quotes',
            '        if q and not cmd.startswith("<<", i):  # inside quotes',
            'a `<<END` inside a quoted string is followed',
        ),
        Mutation(
            "an fd number apart from its `>` is taken as the redirection's (R2-suggestion)",
            '        elif c.isdigit() and word_start and re.match(r"\\d+[<>]", cmd[i:]):',
            '        elif c.isdigit() and word_start and re.match(r"\\d+\\s*[<>]", cmd[i:]):',
            '`cd 5 >/dev/null` (5 is the directory, not an fd) is followed',
        ),
        Mutation(
            "a function definition's body is followed as though it ran (R2-suggestion)",
            '                    if words and not words[-1].endswith(("$", "=")):',
            '                    if False:',
            "a function body's cd is NOT checked",
        ),
        Mutation(
            "a `function` keyword definition's body is followed as though it ran (R2-suggestion)",
            '        if w[0] == "function":\n            raise Unresolved("a function definition before gh")\n',
            '',
            "a `function` keyword body's cd is NOT checked",
        ),
    ),
)
