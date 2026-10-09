"""Mutation guard: hook_guard_bash_db_reset. Declared here, run by scripts/mutation_check.py (#866, #1734).

`guard-bash.sh` refuses `db:reset` unless the project declares `test-db-seeded: yes` in GUARDRAILS.md, and then allows exactly one command:
`RAILS_ENV=test ... db:reset`, run alone. Each break below weakens one of the things that makes that allow narrow, or one of the things that
keeps an undeclared project refused. They run the small `guard_bash_db_reset` fixture group (a few seconds), not the whole `guard_bash` one.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name='hook_guard_bash_db_reset',
    subject='plugins/rails-flow/hooks/scripts/guard-bash.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    selftest_args=("--only", "guard_bash_db_reset"),
    # Staged exactly as hook_guard_bash stages it: the harness resolves every hook from the selftest's own location.
    # Only what `--only guard_bash_db_reset` touches: the hook, its libs, and what the harness imports or reads at start-up.
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/hooks/hooks.json", "plugins/rails-flow/hooks/scripts"),
    mutations=(
        Mutation(
            'the declaration is not required, so an undeclared project may run the test-database reset',
            'if [ "$_seeded" = 1 ] && [ "$degraded" = 0 ] && {',
            'if [ "$degraded" = 0 ] && {',
            'an UNDECLARED project is still refused',
        ),
        Mutation(
            'a declaration allows nothing, so a project that declares test-db-seeded is still refused its own reset',
            '    :   # declared, and exactly the test-database reset: allowed',
            '    deny "mutant: a declaration allows nothing"',
            'a project declaring test-db-seeded ALLOWS',
        ),
        Mutation(
            'degraded mode is not checked, so an unreadable payload is read as a plain test reset',
            '[ "$degraded" = 0 ] && { [[ $cmd =~ $_env_first ]]',
            '{ [[ $cmd =~ $_env_first ]]',
            'a payload the hook cannot parse is refused even for a declared project',
        ),
        Mutation(
            'the end anchor of the env-first form is dropped, so a compound command that also resets the development database is allowed',
            'db:reset[[:space:]]*$"\n  _env_last=',
            'db:reset"\n  _env_last=',
            'even a declared project is still refused',
        ),
        Mutation(
            'the start anchor of the env-first form is dropped, so RAILS_ENV=development followed by RAILS_ENV=test is allowed',
            '_env_first="^[[:space:]]*(env[[:space:]]+)?RAILS_ENV=test',
            '_env_first="[[:space:]]*(env[[:space:]]+)?RAILS_ENV=test',
            'even a declared project is still refused',
        ),
        Mutation(
            'the environment is not pinned to test, so a declared project may reset the development database',
            '(env[[:space:]]+)?RAILS_ENV=test[[:space:]]+${_runner}',
            '(env[[:space:]]+)?RAILS_ENV=[a-z]+[[:space:]]+${_runner}',
            'even a declared project is still refused',
        ),
        Mutation(
            'the CI hint is dropped, so an undeclared project with bin/ci is not pointed at it',
            '_ci_hint=" If this project\'s suite needs a SEEDED test database, run bin/ci, which does its own reset."',
            '_ci_hint=""',
            'an undeclared project WITH bin/ci is told to run bin/ci',
        ),
        Mutation(
            'the declaration must not continue past its value is dropped, so `yes but only on Tuesdays` declares it',
            "`?[[:space:]]*$'",
            "`?'",
            'a longer value does not declare it',
        ),
        Mutation(
            'the declaration need not start its line, so a sentence that mentions it declares it',
            "'^[[:space:]]*([-*+][[:space:]]*)?`?test-db-seeded",
            "'`?test-db-seeded",
            'a sentence that ENDS with it does not declare it',
        ),
        Mutation(
            'the project root ignores CLAUDE_PROJECT_DIR, so the declaration is read from wherever the shell is',
            '_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"\n  _seeded=0',
            '_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"\n  _seeded=0',
            "the declaration is read from the project directory, not the shell's cwd",
        ),
        Mutation(
            'the declared-project refusal branch is dropped, so it falls through to the undeclared message',
            '  elif [ "$_seeded" = 1 ]; then',
            '  elif false; then',
            "the declared project's refusal says what IS allowed",
        ),
        Mutation(
            'lines inside a fenced block are read, so an example of the declaration in a code fence declares it',
            '      [ "$_fenced" = 1 ] && continue\n',
            '',
            'a fenced example does not declare it',
        ),
        Mutation(
            'indented code is read, so an example of the declaration indented four spaces declares it',
            '      [[ $_line =~ $_re_indented ]] && continue\n',
            '',
            'an indented code example does not declare it',
        ),
        Mutation(
            'only a backtick fence is recognised, so a tilde-fenced example declares it',
            "_re_fence='^[[:space:]]{0,3}(```|~~~)'",
            "_re_fence='^[[:space:]]{0,3}(```)'",
            'a tilde-fenced example does not declare it',
        ),
        Mutation(
            'a tab does not make code, so a tab-indented example declares it',
            '"^([[:space:]]{4,}|${_tab})"',
            '"^([[:space:]]{4,})"',
            'a tab-indented example does not declare it',
        ),
    ),
)
