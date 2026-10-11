"""Mutation guard: hook_release_gate_deadline. The deadline block at the bottom of release-gate.sh. Run by scripts/mutation_check.py (#1575)."""
from mutation_types import Guard, Mutation  # noqa: F401

_BS, _BT = chr(92), chr(96)
_PW = "      _pw='(^|[[:space:];&|(])[\"'\"'\"'" + _BS * 2 + "]*push'"   # the leading boundary line in release-gate.sh (quotes and backslashes may precede the word)   # a backslash and a backtick, spelled so no escaping is read twice
_GX = '      _g_x="[' + _BS * 4 + '${_sq}' + _BS + _BT + ']"'   # the line in release-gate.sh

GUARD = Guard(
    name="hook_release_gate_deadline",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the deadline fixtures drive this subject; the whole harness per mutant is ~90 CPU-seconds.
    selftest_args=("--only", "deadline"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json",
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # release-gate.sh and guard-bash.sh run these; unstaged, the harness's other fixtures fail in the staged
           # tempdir and every mutation reads as caught for an environmental reason (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
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
            'deadline_seconds 13 13',
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
            'a repository dispatch stops being a promotion',
            '[[ $_in =~ ${_b}api${_e} ]] && [[ $_in =~ dispatches ]] && _looks_promotion=1',
            ':',
            'a bare `gh api` on a merge, ref, release or dispatch endpoint',
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
            'a bare `gh api` on a merge, ref, release or dispatch endpoint',
        ),
        # #1602 asked that the timeout path also refuse #1606's shapes; these are the two word rules that make it so.
        Mutation(
            'a write method (PUT, POST, PATCH, DELETE) on a `gh api` stops being a promotion',
            '      if [[ $_in =~ $_m_wr ]]; then',
            '      if false; then',
            '`gh api -X PUT repos/o/r/subscription`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'fields on a `gh api` (gh sends a POST) stop being a promotion',
            '      elif ! [[ $_in =~ $_m_get ]] && [[ $_in =~ $_m_fl ]]; then',
            '      elif false; then',
            '`gh api repos/o/r/issues/1/comments -f body=x`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a `$` after `push` (a variable or substitution as the destination) stops being a promotion',
            '      [[ $_in =~ ${_seg}[$] ]] && _looks_promotion=1',
            ':',
            '`git push origin HEAD:$B`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a glob `?` after `push` stops being a promotion',
            '      [[ $_in =~ ${_seg}${_g_q} ]] && _looks_promotion=1',
            ':',
            '`git push origin HEAD:refs/heads/mai?`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a brace expansion after `push` stops being a promotion',
            '      [[ $_in =~ ${_seg}${_g_b} ]] && _looks_promotion=1',
            ':',
            '`git push origin HEAD:ma{in,}`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a bracket glob after `push` stops being a promotion',
            '      [[ $_in =~ ${_seg}${_g_s} ]] && _looks_promotion=1',
            ':',
            '`git push origin HEAD:ma[i]n`',
        ),
        # #1607 (B1 of the PR review): ONE character class after `push` replaces a list of quote spellings; each member of the class has a mutant.
        Mutation(
            "a single quote after `push` stops being a promotion",
            _GX,
            '      _g_x="[' + _BS * 4 + _BS + _BT + ']"',
            "`git push origin HEAD:m'a'in`",
        ),
        Mutation(
            "a backslash after `push` stops being a promotion",
            _GX,
            '      _g_x="[${_sq}' + _BS + _BT + ']"',
            "`git push origin HEAD:m" + _BS + "ain`",
        ),
        Mutation(
            "a backtick after `push` stops being a promotion",
            _GX,
            '      _g_x="[' + _BS * 4 + '${_sq}]"',
            "`git push origin HEAD:ma`:`in`",
        ),
        Mutation(
            "the quote rule reads past the command into a later payload key",
            '      [[ $_in =~ ${_seg_cmd}${_g_x} ]] && _looks_promotion=1',
            '      [[ $_in =~ ${_seg}${_g_x} ]] && _looks_promotion=1',
            "an apostrophe in a later payload key is not read as part of the push destination",
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a git verb built by a variable (`git $V push`) stops being a promotion',
            '      [[ $_in =~ ${_b}git[[:space:]]+[$] ]] && _looks_promotion=1',
            ':',
            '`git $V push origin feature/x`',
        ),
        # #1607: the #1602 delta review's residuals S1-S4 (the coarse detector was an allow-by-default word list).
        Mutation(
            'a GraphQL body built by substitution stops being a promotion',
            "      case $_in in *'$('*|*'`'*|*'<('*) _looks_promotion=1 ;; esac",
            "      case $_in in *'<('*) _looks_promotion=1 ;; esac",
            'a GraphQL body built by substitution (S4)',
        ),
        # THE OTHER DIRECTION: a RULE over-blocks more than a word does, so each rule has a control that must be able to fail.
        Mutation(
            'a `-X GET` stops exempting a `gh api` read that carries fields (-f per_page=100)',
            '      elif ! [[ $_in =~ $_m_get ]] && [[ $_in =~ $_m_fl ]]; then',
            '      elif [[ $_in =~ $_m_fl ]]; then',
            'CONTROL (#1607): the coarse detector allows `gh api -X GET repos/o/r/pulls -f per_page=100`',
        ),
        # THE OTHER DIRECTION: a RULE over-blocks more than a word does, so each rule has a control that must be able to fail.
        Mutation(
            'the `$` rule looks anywhere in a command that says push, not only after it',
            '      [[ $_in =~ ${_seg}[$] ]] && _looks_promotion=1',
            '      [[ $_in =~ [$] ]] && _looks_promotion=1',
            'a `$` that does not follow `push` is not refused',
        ),
        # THE OTHER DIRECTION: a RULE over-blocks more than a word does, so each rule has a control that must be able to fail.
        Mutation(
            'a `?` followed by a letter (a URL query) counts as a glob',
            "      _g_q='[[:alnum:]_/.-][?][[:alnum:]_.%-]*([^[:alnum:]_.%=-]|$)'",
            "      _g_q='[[:alnum:]_/.-][?]'",
            '`git push https://x.test/r.git?z=1 feature/x`',
        ),
        # THE OTHER DIRECTION: a RULE over-blocks more than a word does, so each rule has a control that must be able to fail.
        Mutation(
            "the brace rule matches the JSON wrapper's own braces and commas",
            '      _g_b=\'[[:alnum:]_/.-][{][^{}"[:space:]]*,[^{}"[:space:]]*[}]\'',
            "      _g_b='[{][^{}]*,[^{}]*[}]'",
            'a payload with extra keys, an array and braces of its own is not refused',
        ),
        # #1617: the CLI verbs are a RULE (a short READ-ONLY list), a git alias hides push, a `?` is a glob unless it opens `?key=`, and `push` is a word.
        Mutation(
            "a `gh` verb that is not on the read-only list stops being refused",
            "          *) _looks_promotion=1 ;;",
            "          *) ;;",
            "`gh release delete v1`",
        ),
        Mutation(
            "`gh pr view` drops off the read-only list, so an ordinary read is refused",
            '"pr view"|"pr list"|',
            '"pr list"|',
            "allows `gh pr view 7`",
        ),
        Mutation(
            "a repo flag before the verb is read as the verb",
            "          -R|--repo|-C|-c|--hostname|--git-dir|--work-tree|--namespace) _j=$((_j + 2)); continue ;;",
            "          -C|-c|--hostname|--git-dir|--work-tree|--namespace) _j=$((_j + 2)); continue ;;",
            "allows `gh -R o/r pr view 7`",
        ),
        Mutation(
            "a git alias that names main stops being a promotion",
            '               *" main "*|*" master "*|',
            '               *" mainx "*|*" master "*|',
            "`git p origin main`",
        ),
        Mutation(
            "`checkout` drops off the git verb list, so `git checkout main` is refused",
            "status|log|diff|show|add|commit|checkout|switch|branch|fetch|pull|merge|rebase|stash|reset|restore|tag|remote|config|rev-parse|rev-list|\\",
            "status|log|diff|show|add|commit|switch|branch|fetch|pull|merge|rebase|stash|reset|restore|tag|remote|config|rev-parse|rev-list|\\",
            "allows `git checkout main`",
        ),
        Mutation(
            "a `?` followed by a letter is read as a URL query again, so `ma?n` is allowed",
            "      _g_q='[[:alnum:]_/.-][?][[:alnum:]_.%-]*([^[:alnum:]_.%=-]|$)'",
            "      _g_q='[[:alnum:]_/.-][?]([^[:alnum:]=&]|$)'",
            "`git push origin HEAD:ma?n`",
        ),
        Mutation(
            "a word that merely ENDS in push (`feature/push fix`) starts a push again: the leading boundary is gone",
            _PW,
            "      _pw='push'",
            'allows `git checkout -b "feature/push fix"`',
        ),
        Mutation(
            "a word that merely STARTS with push (`pushed`) starts a push again: the trailing boundary is gone",
            """      _seg_cmd="${_pw}"'([^[:alnum:]_./-][^;&|"]*)?'""",
            """      _seg_cmd="${_pw}"'[^;&|"]*'""",
            "allows `git push origin feature/x; git log --grep pushed \"x y\"`",
        ),
        Mutation(
            "a verb the full path allows (`gh run cancel`) drops off the coarse list, so the two lists drift apart",
            '"run watch"|"run download"|"run cancel"|"run delete"|',
            '"run watch"|"run download"|"run delete"|',
            "every `gh` verb the full path allows is allowed on a timeout",
        ),
        Mutation(
            "`gh api` drops off the exempt groups, so every API read is refused as an unlisted verb",
            "attestation|agent-task|licenses|preview|api) ;;",
            "attestation|agent-task|licenses|preview) ;;",
            "allows `gh api repos/o/r/pulls`",
        ),
        Mutation(
            "a QUOTED or ESCAPED push (`git \"push\" ...`) stops being a push, so the verb hides behind the quotes",
            _PW,
            "      _pw='(^|[[:space:];&|(])push'",
            'git "push" origin HEAD:ma?n',
        ),
    ),
)
