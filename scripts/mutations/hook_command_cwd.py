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
            "                    redirect = True\n",
            "                    redirect = False\n",
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
            '            if w[0] == "!":\n                raise Unresolved("a negated command before gh")\n',
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
            "    cmd = strip_heredoc_bodies(cmd)\n",
            "",
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
    ),
)
