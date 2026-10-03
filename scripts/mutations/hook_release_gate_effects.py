"""Mutation guard: hook_release_gate_effects (#1569). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_effects",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the fixture groups that drive this subject (#1497): the whole harness per
    # mutant was ~70% of the mutation-coverage budget.
    selftest_args=("--only", "release_gate_effects"),
    # The harness resolves every hook from the selftest's own location, and drives release-gate.sh
    # alongside rails-flow's (#906), so the whole hook tree plus qa-flow's scripts must be staged.
    # DECLARED, not assumed: an undeclared read makes the unmutated baseline die in the tempdir and
    # every mutation then reads as "caught" by an error that has nothing to do with the mutation.
    needs=("plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        # #1569: classify by EFFECT, judge a PR by the HEAD it merges, gate publishing. Each mutation
        # removes one of those, and the fixtures must go red.
        Mutation(
            "a REST PUT .../pulls/N/merge is no longer a promotion",
            '"API_PR_MERGE "*)',
            '"API_PR_MERGE_OFF "*)',
            "REST PUT, placeholders merging an uncertified PR head into main is blocked",
        ),
        Mutation(
            "a PR into main is judged at dev's tip again, so a hotfix rides dev's certification",
            'if [ -n "$head" ]; then ctx_repo "${_PRR:--}"; add_ship "$head" "${_R:--}" "the PR head"; else unresolved_pr=1; fi ;;\n    "")',
            'if [ -n "$head" ]; then needs_dev=1; else unresolved_pr=1; fi ;;\n    "")',
            "a hotfix head is judged by ITS stamp, not dev's",
        ),
        Mutation(
            "an unresolved PR is judged at dev instead of denied",
            '[ -z "$unresolved_pr" ] || deny "cannot tell',
            '[ -z "$unresolved_pr" ] || echo "cannot tell',
            "an unresolvable PR could not be judged, so it is blocked",
        ),
        Mutation(
            "a gh api the classifier cannot read is judged at dev instead of denied",
            "    unresolved_pr=1\n  fi\nelif [ \"$_mentions\" = 1 ]; then",
            "    :\n  fi\nelif [ \"$_mentions\" = 1 ]; then",
            "a missing --input file could not be judged, so it is blocked",
        ),
        Mutation(
            "an API write to main (POST merges, ref PATCH) is no longer a promotion",
            'targets_main=1; _v="${_line#* }"',
            '_v="${_line#* }"',
            "POST merges, base main writes main and is blocked",
        ),
        Mutation(
            "a release is collected but never judged: the hook exits before the release loop",
            '[ "$targets_main" -eq 1 ] || [ -n "$releases" ] || exit 0',
            '[ "$targets_main" -eq 1 ] || exit 0',
            "gh release create --target main publishing an uncertified commit is blocked",
        ),
        Mutation(
            "the release line is never recorded",
            '"RELEASE "*) ctx_repo',
            '"RELEASE_OFF "*) ctx_repo',
            "gh api POST releases publishing an uncertified commit is blocked",
        ),
        Mutation(
            "a release is judged at dev's tip instead of the commit it publishes",
            'pass --target <sha>."\n  if [ -n "$_R" ]; then',
            'pass --target <sha>."\n  _rsha="$(git rev-parse --verify -q dev)"\n  if [ -n "$_R" ]; then',
            "gh release create --target main publishing an uncertified commit is blocked",
        ),
        Mutation(
            "git merge on main is judged at dev's tip again, so an uncertified hotfix merges on dev's stamp",
            'targets_main=1; add_commit "${_line#PUSH_REF }" "$_crepo" local "the commit being merged or pushed" ;;',
            'targets_main=1; needs_dev=1 ;;',
            "push of a branch to main is blocked",
        ),
        Mutation(
            "a merge ref that does not resolve is allowed instead of denied",
            'if [ -n "$c" ]; then add_ship "$c" "${_R:--}" "$4"; else unresolved_pr=1; fi',
            'if [ -n "$c" ]; then add_ship "$c" "${_R:--}" "$4"; fi',
            "a ref that does not resolve is blocked",
        ),
        Mutation(
            "the commits queued by a push or merge are never judged",
            '  judge_in "$_c" "$_crp" "$_lab" || deny "$JWHY"',
            '  :',
            "`git merge` on main of an uncertified hotfix branch is blocked",
        ),
        Mutation(
            "git merge on main is no longer a promotion",
            "          if git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qE '^(main|master)$'; then\n            targets_main=1\n            _refs",
            "          if false; then\n            targets_main=1\n            _refs",
            "`git merge` on main of an uncertified hotfix branch is blocked",
        ),
        Mutation(
            "a bare merge is judged at nothing, so it passes",
            "            [ -n \"$_refs\" ] || _refs='@{upstream}'",
            "            :",
            "a bare merge with no upstream is blocked",
        ),
        Mutation(
            "a gh release edit is no longer collected",
            '        "RELEASE_EDIT "*)\n',
            '        "RELEASE_EDIT_OFF "*)\n',
            "gh release edit --draft=false, a draft targeting main publishes an uncertified commit",
        ),
        Mutation(
            "a draft whose target GitHub cannot name is allowed",
            "            if [ -z \"$_tgt\" ]; then unresolved_pr=1; targets_main=1; _tgt=\"-\"; fi",
            "            if [ -z \"$_tgt\" ]; then _tgt=\"dev\"; fi",
            "gh release edit with GitHub unable to name the target",
        ),
        Mutation(
            "an API release PATCH is no longer resolved to its target",
            '        "RELEASE_ID "*)\n',
            '        "RELEASE_ID_OFF "*)\n',
            "gh api PATCH releases/<id> draft=false publishes an uncertified commit",
        ),
        Mutation(
            "a release id GitHub cannot name is allowed",
            '            "") unresolved_pr=1; targets_main=1 ;;',
            '            "") : ;;',
            "gh api PATCH releases/<id> GitHub cannot name",
        ),
        # (#1571) the two lines the classifier emits when a command puts itself on main
        Mutation(
            'GIT_MERGE_MAIN is no longer a promotion, so `switch main && merge` reaches main uncertified',
            '        GIT_MERGE_MAIN*)\n',
            '        GIT_MERGE_MAIN_OFF*)\n',
            'release-gate (#1571): a switch to main, then a merge is blocked',
        ),
        Mutation(
            'a merge the command puts on main has its refs dropped instead of judged',
            '          [ -n "$_refs" ] || _refs=\'@{upstream}\'\n          for _r in $_refs; do add_commit "$_r" "-" local "the commit being merged or pushed"; done ;;\n        GIT_MERGE*)',
            '          [ -n "$_refs" ] || _refs=\'@{upstream}\'\n          for _r in $_refs; do : add_commit "$_r" "-" local "the commit being merged or pushed"; done ;;\n        GIT_MERGE*)',
            'release-gate (#1571): a switch to main, then a merge is blocked',
        ),
        Mutation(
            'GIT_PULL_MAIN is no longer a promotion, so `switch main && pull` reaches main unjudged',
            '        GIT_PULL_MAIN)\n',
            '        GIT_PULL_MAIN_OFF)\n',
            'release-gate (#1571): a switch to main, then a pull is blocked',
        ),
        Mutation(
            "QA_ALLOW_MAIN typed into the command text authorises it, so any command can approve itself",
            '[ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: QA_ALLOW_MAIN=1 override',
            '{ [ "${QA_ALLOW_MAIN:-0}" = "1" ] || printf \'%s\' "$cmd" | grep -q \'QA_ALLOW_MAIN=1\'; } && { echo "qa-flow: QA_ALLOW_MAIN=1 override',
            "release-gate (#1571): QA_ALLOW_MAIN typed into the command as an inline assignment does not authorise it",
        ),
    ),
)
