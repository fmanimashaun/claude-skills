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
    selftest_args=("--only", "release_gate_repos", "--strict-timing"),   # its stall mutants are STARVED-shaped by design (#1664)
    # Each mutant runs only the fixture its `expects` names (#1599), after a control run of the unmutated hook with the same
    # flag: seventeen mutants of a 150-check group would otherwise cost seventeen whole groups.
    narrow_with="--match",
    # The harness resolves every hook from the selftest's own location and drives release-gate.sh beside
    # rails-flow's, so the hook trees and qa-flow's scripts are staged. DECLARED, not assumed: an undeclared
    # read kills the unmutated baseline and every mutation then reads as "caught" by that error.
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/hooks/hooks.json",
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # #1581 merge: run by session-start.sh / release-gate.sh
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
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
            "GH_REPO ALONE sends a release",
        ),
        Mutation(
            "a repository that is not owner/repo (a host-qualified one) is accepted",
            """  grep -qE '^[a-z0-9_.-]+/[a-z0-9_.-]+$' <<<"$r" || { unresolved_pr=1; return 0; }""",
            "  :",
            "a host-qualified GH_REPO is refused as unresolved",
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
            '--check-verdict --tree "$tree" 2>"$evtmp")"; then',
            '--check-verdict --tree "$tree" 2>"$evtmp")" || true; then',
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
            "a refused verdict does not stop the gate, so a promotion with no usable verdict goes through",
            'Judge them first, which takes a while and is not done inside this hook: ${rec}"; return 1',
            'Judge them first, which takes a while and is not done inside this hook: ${rec}"; true',
            "no verdict at all denies",
        ),
        Mutation(
            "the compare call is not bounded, so a stalled gh outlives the hook's timeout and the command goes through",
            'cmp="$(bounded 4 gh api "repos/${repo}/compare/',
            'cmp="$(gh api "repos/${repo}/compare/',
            "a compare call that stalls on its own is cut short",
        ),
        Mutation(
            "the stamp read is not bounded either",
            "if ! bounded 4 gh api -H 'Accept: application/vnd.github.raw+json'",
            "if ! gh api -H 'Accept: application/vnd.github.raw+json'",
            "a gh that stalls is cut short",
        ),
    ),
)
