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
    # Each mutant runs only the fixture its `expects` names (#1599): the whole group cost 177 s of work on the CI runner for 22 mutants, over the 120 s limit for a new guard.
    narrow_with="--match",
    # Staged exactly as hook_guard_bash stages it, and in full even though `--only guard_bash_db_reset` drives one hook: the harness resolves every hook from
    # the selftest's own location, and `lint_self_consistency`'s harness-dependency-undeclared refuses a guard on this harness that lists fewer (a trimmed
    # list was tried and refused).
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # the harness drives release-gate.sh too (#906)
    mutations=(
        Mutation(
            'the declaration is not required, so an undeclared project may run the test-database reset',
            'if [ "$_seeded" = 1 ] && [ "$degraded" = 0 ] && {',
            'if [ "$degraded" = 0 ] && {',
            'still refused `RAILS_ENV=test bin/rails db:reset`',
        ),
        Mutation(
            'a declaration allows nothing, so a project that declares test-db-seeded is still refused its own reset',
            '    :   # declared, and exactly the test-database reset: allowed',
            '    deny "mutant: a declaration allows nothing"',
            'ALLOWS `RAILS_ENV=test bin/rails db:reset`',
        ),
        Mutation(
            'degraded mode is not checked, so an unreadable payload is read as a plain test reset',
            '[ "$degraded" = 0 ] && { [[ $cmd =~ $_env_first ]]',
            '{ [[ $cmd =~ $_env_first ]]',
            'a payload the hook cannot parse is refused even for a declared project',
        ),
        Mutation(
            'the end anchor of the env-first form is dropped, so a compound command that also resets the development database is allowed',
            'db:reset${_s}*\\$"\n  _env_last=',
            'db:reset"\n  _env_last=',
            "still refused `'RAILS_ENV=test bin/rails db:reset && bin/rails db:reset'`",
        ),
        Mutation(
            'the start anchor of the env-first form is dropped, so RAILS_ENV=development followed by RAILS_ENV=test is allowed',
            '_env_first="^${_s}*(env${_s}+)?RAILS_ENV=test',
            '_env_first="${_s}*(env${_s}+)?RAILS_ENV=test',
            "still refused `'RAILS_ENV=development RAILS_ENV=test bin/rails db:reset'`",
        ),
        Mutation(
            'the environment is not pinned to test, so a declared project may reset the development database',
            '(env${_s}+)?RAILS_ENV=test${_s}+${_runner}',
            '(env${_s}+)?RAILS_ENV=[a-z]+${_s}+${_runner}',
            "still refused `'RAILS_ENV=development bin/rails db:reset'`",
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
            '_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"\n  _tab=$\'\\t\'',
            '_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"\n  _tab=$\'\\t\'',
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
        Mutation(
            'the separator is [[:space:]] again, so a newline between the assignment and the command is one allowed command',
            '_s="[ ${_tab}]"',
            '_s="[[:space:]]"',
            "still refused `'RAILS_ENV=test\\nbin/rails db:reset'`",
        ),
        Mutation(
            'an HTML comment is not recognised, so the declaration inside a multi-line comment declares it',
            '      if [[ $_line == *\'<!--\'* ]]; then\n        _after_open="${_line#*<!--}"\n        [[ $_after_open == *\'-->\'* ]] || _commented=1\n        continue\n      fi\n',
            '',
            'an HTML comment spanning lines does not declare it',
        ),
        Mutation(
            'a comment never closes, so a declaration after a closed multi-line comment is not read',
            "        [[ $_line == *'-->'* ]] && _commented=0\n",
            '        :\n',
            'note\\n-->\\n- test-db-seeded: yes',
        ),
        Mutation(
            'a one-line comment opens a comment that never closes, so a declaration after it is not read',
            "        [[ $_after_open == *'-->'* ]] || _commented=1\n",
            '        _commented=1\n',
            '<!-- note -->\\n- test-db-seeded: yes',
        ),
        Mutation(
            'the db:reset rule ignores every runner prefix, so bundle exec rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers=''",
            'still refused `bundle exec rails db:reset`',
        ),
        Mutation(
            'the ruby, spring and bin/spring runners are dropped from the db:reset rule, so ruby bin/rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            'still refused `ruby bin/rails db:reset`',
        ),
        Mutation(
            'the app: namespace is dropped from the db:reset rule, so bin/rails app:db:reset is never refused',
            'if hit "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(app:)?db:reset\\\\b" \\',
            'if hit "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+db:reset\\\\b" \\',
            'still refused `bin/rails app:db:reset`',
        ),
        Mutation(
            'wrappers no longer chain, so bundle exec spring rails db:reset is never refused (shell-adversary review)',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)?'",
            'still refused `bundle exec spring rails db:reset`',
        ),
        Mutation(
            'bundle exec -- is not read, so bundle exec -- rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            'still refused `bundle exec -- rails db:reset`',
        ),
        Mutation(
            'ruby -S is not read, so ruby -S rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            'still refused `ruby -S rails db:reset`',
        ),
        Mutation(
            'a full-path env is not a wrapper, so /usr/bin/env bin/rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring)[[:space:]]+)*'",
            'still refused `/usr/bin/env bin/rails db:reset`',
        ),
        Mutation(
            'env assignments are not read, so /usr/bin/env FOO=1 bin/rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env))[[:space:]]+)*'",
            'still refused `/usr/bin/env FOO=1 bin/rails db:reset`',
        ),
        Mutation(
            'the runner must be a bare bin/ path, so ./bin/rails and /app/bin/rails are never refused',
            "_runner_cmd='(([^[:space:]]*/)?bin/(rails|rake)|rails|rake)'",
            "_runner_cmd='((bin/)?(rails|rake)|rails|rake)'",
            'still refused `/app/bin/rails db:reset`',
        ),
        Mutation(
            'spring at a path is not a wrapper, so ./bin/spring rails db:reset is never refused',
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|([^[:space:]]*/)?bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            "_wrappers='((bundle[[:space:]]+exec([[:space:]]+--)?|ruby([[:space:]]+-S)?|spring|bin/spring|([^[:space:]]*/)?env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)*)[[:space:]]+)*'",
            'still refused `./bin/spring rails db:reset`',
        ),
        Mutation(
            'a listing is not exempt, so rake -T db:reset is refused',
            '   && ! exempt "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(-T|--tasks|-D|--describe)([[:space:]=]|\\$)"; then',
            '   && ! false; then',
            'may run `rake -T db:reset`',
        ),
        Mutation(
            'every option is exempt, so db:reset with --trace is read as a listing',
            '   && ! exempt "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(-T|--tasks|-D|--describe)([[:space:]=]|\\$)"; then',
            '   && ! exempt "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(-[A-Za-z]|--[a-z]+)([[:space:]=]|\\$)"; then',
            'still refused `bin/rails db:reset --trace`',
        ),
        Mutation(
            'the listing exemption applies when the payload cannot be parsed, so a listing in an unreadable payload passes',
            '   && ! exempt "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(-T|--tasks|-D|--describe)([[:space:]=]|\\$)"; then',
            '   && ! hit "^${_wrappers}${_runner_cmd}([[:space:]]+[^[:space:]]+)*[[:space:]]+(-T|--tasks|-D|--describe)([[:space:]=]|\\$)"; then',
            'a listing in a payload the hook cannot parse is refused',
        ),
    ),
)
