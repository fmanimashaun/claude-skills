"""Mutation guard: hook_release_gate_deadline. The deadline block at the bottom of release-gate.sh. Run by scripts/mutation_check.py (#1575)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_deadline",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the deadline fixtures drive this subject; the whole harness per mutant is ~90 CPU-seconds.
    selftest_args=("--only", "deadline"),
    needs=("plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # release-gate.sh and guard-bash.sh run these; unstaged, the harness's other fixtures fail in the staged
           # tempdir and every mutation reads as caught for an environmental reason (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py"),
    mutations=(
        # A blocking gate: a promotion it cannot read must be refused.
        Mutation(
            'a timeout never denies, so a promotion that cannot be read in time is allowed',
            '    if [ "$_looks_promotion" = "1" ]; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            '    if false; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'refuses `git push origin main` when it cannot finish reading it',
        ),
        # Blocking every slow command would be the failure; the coarse detector decides.
        Mutation(
            'a timeout always denies, so every slow command is blocked, not only a promotion',
            '    if [ "$_looks_promotion" = "1" ]; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            '    if true; then\n      [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'ALLOWS a command that does not look like a promotion',
        ),
        # The audited override works in the missing-tool path and must work here.
        Mutation(
            'QA_ALLOW_MAIN=1 stops being honoured on a timeout',
            '[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: the gate hit',
            'false && { echo "qa-flow: the gate hit',
            'QA_ALLOW_MAIN=1 is honoured and audited on a timeout',
        ),
        # Past hooks.json's 15 s Claude Code stops waiting.
        Mutation(
            "the default and ceiling move above the hook's own timeout",
            'deadline_seconds 10 13',
            'deadline_seconds 20 30',
            "default and ceiling sit below the hook's configured timeout",
        ),
        # #1602 review F1: a LIST of mutation names let three promotions through on a timeout.
        Mutation(
            'a timeout stops denying `gh api graphql` mutations by the word, so a promotion with a new name gets through',
            '[[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ ${_b}graphql${_e} ]] && [[ $_in =~ mutation ]] && _looks_promotion=1',
            ':',
            'refuses `gh api graphql -f` enablePullRequestAutoMerge when it cannot finish reading it',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'the `heads/` shorthand stops being main, so `HEAD:heads/main` is allowed on a timeout',
            '(^|[^[:alnum:]_/.-]|refs/heads/|[^[:alnum:]_/.-]heads/)(main|master)${_e}',
            '(^|[^[:alnum:]_/.-]|refs/heads/)(main|master)${_e}',
            'refuses the `heads/` shorthand for refs/heads/main',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            '--all and --mirror stop being promotions',
            '[[ $_in =~ (^|[^[:alnum:]_-])--(all|mirror)${_e} ]] && _looks_promotion=1',
            ':',
            'refuses a push of every branch (--all, --mirror)',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'a wildcard refspec stops being a promotion',
            '[[ $_in =~ [*] ]] && _looks_promotion=1',
            ':',
            'refuses a wildcard refspec, which pushes every branch',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'update-branch stops being a promotion',
            '[[ $_in =~ update-branch ]] && _looks_promotion=1',
            ':',
            'refuses update-branch',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'a workflow run stops being a promotion',
            '[[ $_in =~ ${_b}workflow${_e} ]] && [[ $_in =~ ${_b}run${_e} ]] && _looks_promotion=1',
            ':',
            'refuses a workflow run',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'a repository dispatch stops being a promotion',
            '[[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ dispatches ]] && _looks_promotion=1',
            ':',
            'refuses a repository dispatch',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'a GraphQL --input body stops being a promotion',
            '[[ $_in =~ (^|[^[:alnum:]_-])--input${_e} ]] && _looks_promotion=1',
            ':',
            '`gh api graphql --input q.json`',
        ),
        # #1602 review of the timeout path: shapes the FULL path denies and the coarse detector allowed (a 486-command differential).
        Mutation(
            'a GraphQL -F query=@file body stops being a promotion',
            '[[ $_in =~ (^|[^[:alnum:]_-])(-F|--field)[[:space:]=]*[^[:space:]=]+=@ ]] && _looks_promotion=1',
            ':',
            '`gh api graphql -F query=@q.graphql`',
        ),
        # THE OTHER DIRECTION: refusing too much would pass every refusal example above, so a control must be able to fail.
        Mutation(
            'a lower-case -f query=@x, a LITERAL string in gh, is counted as a file read',
            '[[ $_in =~ (^|[^[:alnum:]_-])(-F|--field)[[:space:]=]*[^[:space:]=]+=@ ]] && _looks_promotion=1',
            '[[ $_in =~ (^|[^[:alnum:]_-])(-f|-F|--field|--raw-field)[[:space:]=]*[^[:space:]=]+=@ ]] && _looks_promotion=1',
            'CONTROL: the coarse detector allows `gh api graphql -f query=@q.graphql`',
        ),
        # THE OTHER DIRECTION: refusing too much would pass every refusal example above, so a control must be able to fail.
        Mutation(
            '--tags is counted as a push of every branch',
            '[[ $_in =~ (^|[^[:alnum:]_-])--(all|mirror)${_e} ]] && _looks_promotion=1',
            '[[ $_in =~ (^|[^[:alnum:]_-])--(all|mirror|tags)${_e} ]] && _looks_promotion=1',
            'CONTROL: the coarse detector allows `git push --tags origin`',
        ),
        # #1602 asked that the timeout path also refuse #1606's shapes; these are the two word rules that make it so.
        Mutation(
            'a `gh api` REST merge or ref write stops being a promotion on a timeout',
            '[[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ (merge|merges|refs|releases|mergePullRequest|updateRef|createRef) ]] && _looks_promotion=1',
            ':',
            'refuses a REST merge or ref write whose head or sha is not a plain name (#1606)',
        ),
        # #1602 asked that the timeout path also refuse #1606's shapes; these are the two word rules that make it so.
        Mutation(
            'a `gh release create|edit` stops being a promotion on a timeout',
            '[[ $_in =~ ${_b}release${_e} ]] && [[ $_in =~ ${_b}(create|edit)${_e} ]] && _looks_promotion=1',
            ':',
            'refuses a release publish whose tag or target is not a plain name (#1606)',
        ),
    ),
)
