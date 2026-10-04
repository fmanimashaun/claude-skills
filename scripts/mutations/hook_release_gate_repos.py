"""Mutation guard: hook_release_gate_repos (#1592). Declared here, run by scripts/mutation_check.py.

The `release_gate_repos` fixture group proves the release gate acts on the repository a command ACTS on
(`gh -R`, GH_REPO, a `repos/<o>/<r>` path, a git remote) and, for another repository, judges its stamp and its
release-only layers (#1591). No other guard ran that group, so nothing proved its fixtures could fail.
Each mutation below breaks one piece of that code; the fixture named in `expects` must go red for it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_repos",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the group that drives this subject, as the two other release-gate guards do (#1497).
    selftest_args=("--only", "release_gate_repos"),
    # The harness resolves every hook from the selftest's own location and drives release-gate.sh beside
    # rails-flow's, so the hook trees and qa-flow's scripts are staged. DECLARED, not assumed: an undeclared
    # read kills the unmutated baseline and every mutation then reads as "caught" by that error.
    needs=("plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # judge_remote runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        # ---- which repository a command acts on (ctx_repo) -------------------------------------------------
        Mutation(
            "a repository that is not this checkout's is never marked foreign, so its command is judged here",
            '  _R="$r"; _foreign=1\n}',
            '  _R=""\n}',
            "acts on ANOTHER repository",
        ),
        Mutation(
            "this checkout's own repository is not recognised, so -R o/r is judged as another repository",
            '  [ "$r" = "$L" ] && return 0\n  _R="$r"; _foreign=1',
            '  _R="$r"; _foreign=1',
            "names this checkout's own repository",
        ),
        Mutation(
            "a repository is compared with its case kept, so -R O/R is another repository",
            """    *) r="$(printf '%s' "$f" | tr 'A-Z' 'a-z')" ;;""",
            """    *) r="$f" ;;""",
            "names this checkout's own repository",
        ),
        Mutation(
            "GH_REPO in the hook's environment is ignored",
            '    -) f="${GH_REPO:-}"',
            '    -) f=""',
            "GH_REPO in the hook's environment",
        ),
        Mutation(
            "a repository that is not owner/repo (a host-qualified one) is accepted",
            """  printf '%s\\n' "$r" | grep -qE '^[a-z0-9_.-]+/[a-z0-9_.-]+$' || { unresolved_pr=1; return 0; }""",
            "  :",
            "a host-qualified repository",
        ),
        Mutation(
            "a remote that does not exist is judged here, as if it were origin",
            '        [ "$n" = "origin" ] || unresolved_pr=1',
            "        :",
            "a remote that does not exist",
        ),
        # ---- the stamp of another repository (judge_remote, judge_in) ---------------------------------------
        Mutation(
            "every command is judged against THIS checkout's stamp, whatever repository it acts on",
            'judge_in() { if [ "$2" = "-" ]; then judge "$1" "$1" "$3"; else judge_remote "$1" "$2" "$3"; fi; }',
            'judge_in() { judge "$1" "$1" "$3"; }',
            "acts on ANOTHER repository",
        ),
        Mutation(
            "a release into another repository is judged against this checkout's stamp",
            'judge_remote "$_rsha" "$_R" "the release target"',
            'judge "$_rsha" "$_rsha" "the release target"',
            "a release into another repository",
        ),
        Mutation(
            "another repository's verdict is not checked, so a FAIL stamp permits",
            '    JWHY="${repo}: certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."; return 1',
            '    JWHY="${repo}: certification verdict is ${verdict}, not PASS. Fix the defects and re-certify."; return 0',
            "whose verdict is not PASS",
        ),
        Mutation(
            "a certified commit that is not an ancestor of the judged one is accepted",
            '      case "$status" in ahead|identical) : ;; *)',
            '      case "$status" in ahead|identical|diverged|behind) : ;; *)',
            "that is diverged",
        ),
        Mutation(
            "any change after another repository's stamp is accepted",
            '  if [ -n "$files" ]; then',
            '  if false; then',
            "a code change riding with that evidence is denied",
        ),
        # ---- the release-only layers of another repository (#1591) --------------------------------------------
        Mutation(
            "another repository's release-only layers are not enforced, so a HOLE still promotes",
            '--repo "$repo" --sha "$sha" --budget "$budget" 2>"$evtmp")"; then',
            '--repo "$repo" --sha "$sha" --budget "$budget" 2>"$evtmp")" || true; then',
            "committed HOLE in the sweep is denied",
        ),
        Mutation(
            "another repository's delta may carry only the stamp, so its own evidence is refused",
            "sed 1d | extra_files \"$evidence\" | head -3",
            "sed 1d | grep -vx 'qa/CERTIFICATION' | head -3",
            "whose commit carries its passing evidence, is permitted",
        ),
        # ---- the hook's own time (#1591): a hook that outlives its 15 s timeout does not deny -------------------------
        Mutation(
            "the evidence judge is given 600 s, so a stalled fetch outlives the hook's timeout and the command goes through",
            '--sha "$sha" --budget "$budget" 2>"$evtmp")"; then',
            '--sha "$sha" --budget 600 2>"$evtmp")"; then',
            "a fetch that stalls past the hook's own 15 s",
        ),
        Mutation(
            "the compare call is not bounded, so a stalled gh outlives the hook's timeout and the command goes through",
            'cmp="$(bounded 4 gh api "repos/${repo}/compare/',
            'cmp="$(gh api "repos/${repo}/compare/',
            "a gh that stalls is cut short",
        ),
        Mutation(
            "the stamp read is not bounded either",
            "if ! bounded 4 gh api -H 'Accept: application/vnd.github.raw+json'",
            "if ! gh api -H 'Accept: application/vnd.github.raw+json'",
            "a gh that stalls is cut short",
        ),
        Mutation(
            "a hook with no time left still starts the evidence judge",
            '  if [ "$budget" -lt 3 ]; then',
            '  if false; then',
            "a hook that has spent its time on the API",
        ),
        # ---- a name that becomes part of ANOTHER repository's API path (#1591, the class of #1600) ---------------------
        Mutation(
            "a ref that is not a plain name is put in another repository's commits path",
            '        ! plain_ref "$ref" || c="$(gh api "repos/${_R}/commits/${ref}" -q .sha 2>/dev/null || true)"',
            '        c="$(gh api "repos/${_R}/commits/${ref}" -q .sha 2>/dev/null || true)"',
            "REST merge's head that is not a plain name",
        ),
        Mutation(
            "a release target or tag that is not a plain name is put in another repository's API path",
            '    [ -z "$tgt" ] || plain_ref "$tgt" || return 1\n',
            '',
            "release's --target that is not a plain name",
        ),
        Mutation(
            "a release tag that is not a plain name is put in another repository's API path",
            '    [ -z "$tag" ] || plain_ref "$tag" || return 1\n',
            '',
            "release's tag that is not a plain name",
        ),
    ),
)
