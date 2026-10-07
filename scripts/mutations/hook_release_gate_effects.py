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
    needs=(
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
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
            'if [ -n "$head" ]; then ctx_repo "${_PRR:--}"; add_ship "$head" "${_R:--}" "the PR head"; pin_head "$head"; else unresolved_pr=1; fi ;;\n    "")',
            'if [ -n "$head" ]; then needs_dev=1; pin_head "$head"; else unresolved_pr=1; fi ;;\n    "")',
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
            "          if grep -qE '^(main|master)$' <<<\"$(git rev-parse --abbrev-ref HEAD 2>/dev/null)\"; then\n            targets_main=1\n            _refs",
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
        # (#1571) a merge into main must PIN the head the gate judged
        Mutation(
            'an unpinned merge into main is no longer refused, so a head pushed after the check rides on the certification',
            '  [ -n "${pin_fail:-}" ] || pin_fail="this merges a pull request',
            '  : pin_fail="this merges a pull request',
            'release-gate (#1571): `gh pr merge` into main without a pin is blocked',
        ),
        Mutation(
            'a pin shorter than 7 digits is accepted as a prefix',
            '  if [ "$_PMG" = 1 ] && [ "${#m}" -ge 7 ]; then',
            '  if [ "$_PMG" = 1 ] && [ "${#m}" -ge 1 ]; then',
            'release-gate (#1571): a pin shorter than 7 digits does not pin the judged head, so it is blocked',
        ),
        Mutation(
            'a pin for a DIFFERENT commit is accepted',
            '*) case "$h" in "$m"*) return 0 ;; esac ;; esac',
            '*) case "$h" in *) return 0 ;; esac ;; esac',
            'release-gate (#1571): a pin for a DIFFERENT commit does not pin the judged head, so it is blocked',
        ),
        Mutation(
            'the pin is compared case-sensitively, so an uppercase copy of the head is refused',
            '  m="$(printf \'%s\' "$_PM" | tr \'A-F\' \'a-f\')"',
            '  m="$_PM"',
            'release-gate (#1571): CONTROL: an uppercase pin pins the judged head and is permitted',
        ),
        Mutation(
            'a pin that is not hexadecimal is accepted',
            '    case "$m" in *[!0-9a-f]*) ;; *) case',
            '    case "$m" in *[!0-9a-f]*) return 0 ;; *) case',
            'release-gate (#1571): a pin that is not hexadecimal does not pin the judged head, so it is blocked',
        ),
        Mutation(
            'the denial for gh pr merge prints a shortened head, not the exact command to run',
            '--match-head-commit ${h}   (keep your other flags).',
            '--match-head-commit ${h:0:7}   (keep your other flags).',
            'release-gate (#1571): `gh pr merge` without a pin: the denial prints the exact command, with the full head',
        ),
        Mutation(
            'the denial for a REST merge prints a shortened head',
            'fix="Add -f sha=${h} to the gh api call."',
            'fix="Add -f sha=${h:0:7} to the gh api call."',
            'release-gate (#1571): a REST merge without a pin: the denial prints the exact command, with the full head',
        ),
        Mutation(
            'the denial for a GraphQL merge prints a shortened head',
            'fix="Set expectedHeadOid: \\"${h}\\" in the mutation\'s input."',
            'fix="Set expectedHeadOid: \\"${h:0:7}\\" in the mutation\'s input."',
            'release-gate (#1571): a GraphQL merge without a pin: the denial prints the exact command, with the full head',
        ),
        Mutation(
            "the pin on a gh pr merge is not read from the classifier's line",
            'split_match "$_sel"; _sel="$_SPLIT_REST"; _PINKIND=cli;',
            '_PMG=0; _PM=""; _PINKIND=cli;',
            'release-gate (#1571): CONTROL: a full pin pins the judged head and is permitted',
        ),
        Mutation(
            "the pin on a REST merge is not read from the classifier's line",
            'split_match "$_n"; _n="$_SPLIT_REST"; _PINKIND=api;',
            '_PMG=0; _PM=""; _PINKIND=api;',
            'release-gate (#1571): CONTROL: a REST `sha=` pins the judged head and is permitted',
        ),
        Mutation(
            "the pin on a GraphQL merge is not read from the classifier's line",
            'split_match "$_id"; _id="$_SPLIT_REST"; _PINKIND=gql;',
            '_PMG=0; _PM=""; _PINKIND=gql;',
            'release-gate (#1571): CONTROL: a GraphQL expectedHeadOid pins the judged head and is permitted',
        ),
        # #1626: a lookup that errors is unresolved, not an answer. Real `gh` exits 1 and prints the raw error body to STDOUT.
        Mutation(
            "a lookup that exits non-zero is read for what it printed, so a failed lookup still resolves",
            '_o="$(gh "$@" 2>/dev/null)" || return 1;',
            '_o="$(gh "$@" 2>/dev/null)" || true;',
            "a GraphQL mergePullRequest whose lookup exits non-zero is blocked even though it printed an answer",
        ),
        Mutation(
            "a PR lookup whose base is not a ref name (the JSON error body) is read as a base",
            'sane_pr_lookup() { ref_name_returned "$base" &&',
            'sane_pr_lookup() { true &&',
            "a GraphQL mergePullRequest whose lookup prints something that is not a ref name (exit 0) is blocked",
        ),
        Mutation(
            "an updateRef lookup that prints something other than a ref name first is read as a ref",
            '          ref_name_returned "${_out%% *}" || _out=""   # #1626',
            '          true   # #1626',
            "a GraphQL updateRef whose lookup prints something that is not a ref name (exit 0) is blocked",
        ),
        # #1628: a looked-up name may come back qualified; the coarse detector reads `refs/heads/main` as main, so the full path strips ONE prefix.
        Mutation(
            "a PR lookup's base is not stripped of refs/heads/ or heads/, so refs/heads/main is judged not-main",
            'base="$(short_ref "$base")"',
            'base="$base"',
            "a `gh pr merge` whose base is looked up as `refs/heads/main` is judged as main and blocked",
        ),
        Mutation(
            "an updateRef lookup's name is not stripped, so refs/heads/main is judged not-main",
            'case "$(short_ref "${_out%% *}")" in',
            'case "${_out%% *}" in',
            "an updateRef whose ref is looked up as `refs/heads/main` is judged as main and blocked",
        ),
        Mutation(
            "short_ref strips only refs/heads/, so heads/main is judged not-main",
            'r="${r#refs/heads/}"; [ "$r" = "$1" ] && r="${r#heads/}";',
            'r="${r#refs/heads/}";',
            "a `gh pr merge` whose base is looked up as `heads/main` is judged as main and blocked",
        ),
    ),
)
