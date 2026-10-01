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
            "a cd inside a subshell outlives it",
            "                here = stack.pop() if stack else here",
            "                stack.pop() if stack else None",
            "a cd inside a subshell does not outlive it",
        ),
        Mutation(
            "a cd joined by || counts as having run",
            'APPLIES = {"&&", ";"}',
            'APPLIES = {"&&", ";", "||"}',
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
            "    return here\n",
            "    return start\n",
            "a `cd <other repo>` is judged against that repo's template",
        ),
    ),
)
