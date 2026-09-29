"""Mutation guard: hook_release_gate. Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
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
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        # #1337: the stamp's own commit invalidates it again, or any delta slips through.
        Mutation(
            "an ancestor stamp is never accepted, so committing the stamp denies its promotion",
            '        [ "$f" = "qa/CERTIFICATION" ] && continue',
            '        [ "$f" = "__never__" ] && continue',
            "release-gate (#1337): the stamp committed on top of the tested sha still permits",
        ),
        Mutation(
            "any delta after an ancestor stamp is accepted",
            '      if [ -n "$extra" ]; then',
            '      if false; then',
            "release-gate (#1337): a code change after the tested sha is denied, naming the path",
        ),
        # #1428. The evidence check is skipped: a PASS stamp alone unlocks main again.
        Mutation(
            "the release-only layers are not checked, so a HOLE still promotes",
            'if evidence="$(python3 "$ev" stamp --rev "$devsha" 2>"$evtmp")"; then',
            'if evidence="$(python3 "$ev" stamp --rev "$devsha" 2>"$evtmp")" || true; then',
            "release-gate (#1428): a HOLE in the sweep denies",
        ),
        # The allowance matches ANY path under the evidence's parent, so code rides along unchecked.
        Mutation(
            "every changed file counts as evidence",
            '            (*/) case "$f" in ("$p"*) ok=1 ;; esac ;;',
            '            (*/) ok=1 ;;',
            "release-gate (#1428): a code change riding with the evidence is still denied",
        ),
        # The trailing slash is what stops first-boot-v1-other matching first-boot-v1.
        Mutation(
            "the evidence directory is matched without its trailing slash",
            '            (*/) case "$f" in ("$p"*) ok=1 ;; esac ;;',
            '            (*/) case "$f" in ("${p%/}"*) ok=1 ;; esac ;;',
            "release-gate (#1428): a look-alike of the evidence path is not evidence",
        ),
        # #1437 review: a contains-match survived every fixture. The allowance is a PREFIX.
        Mutation(
            "the evidence allowance matches the path anywhere, not as a prefix",
            '            (*/) case "$f" in ("$p"*) ok=1 ;; esac ;;',
            '            (*/) case "$f" in (*"$p"*) ok=1 ;; esac ;;',
            "release-gate (#1428): a path merely containing the evidence path is not evidence",
        ),
        # #1437 review round 2: the sweep FILE matched as a prefix, so sweep.csv.rb rode along.
        Mutation(
            "the sweep file matches as a prefix",
            '            (*) [ "$f" = "$p" ] && ok=1 ;;',
            '            (*) case "$f" in ("$p"*) ok=1 ;; esac ;;',
            "release-gate (#1428): a file that only starts with the sweep's name is not evidence",
        ),
        Mutation(
            "rename detection is back, so code moved into the evidence folder is never judged",
            '      if ! delta="$(git -c core.quotePath=false diff --no-renames --name-only "$full" "$devsha" 2>/dev/null)"; then',
            '      if ! delta="$(git -c core.quotePath=false diff -M --name-only "$full" "$devsha" 2>/dev/null)"; then',
            "release-gate (#1428): code renamed into the evidence folder is denied",
        ),
        Mutation(
            "the evidence is judged in the working tree, not as committed at dev",
            'if evidence="$(python3 "$ev" stamp --rev "$devsha" 2>"$evtmp")"; then',
            'if evidence="$(python3 "$ev" stamp 2>"$evtmp")"; then',
            "release-gate (#1428): a committed HOLE denies though the fix is only staged",
        ),
        Mutation(
            "git quotes non-ASCII names again, so a legitimate evidence commit is denied",
            '      if ! delta="$(git -c core.quotePath=false diff --no-renames --name-only "$full" "$devsha" 2>/dev/null)"; then',
            '      if ! delta="$(git diff --no-renames --name-only "$full" "$devsha" 2>/dev/null)"; then',
            "release-gate (#1428): a non-ASCII evidence file name is recognised as evidence",
        ),
        # The paths come from stdout; losing them denies the stamp's own evidence commit.
        Mutation(
            "the evidence paths are discarded, so the stamp's evidence commit is denied",
            '$evidence\nEVIDENCE',
            '\nEVIDENCE',
            "release-gate (#1428): a schema-2 stamp whose commit carries its passing evidence permits",
        ),
        Mutation(
            "the ancestry check is skipped, so a stamp from another branch is accepted",
            '      if [ -z "$full" ] || ! git merge-base --is-ancestor "$full" "$devsha" 2>/dev/null; then',
            '      if [ -z "$full" ]; then',
            "release-gate (#1337): a stamp for a sha that is not an ancestor of dev is denied",
        ),
        Mutation(
            "the dev sha is read with plain rev-parse again, so a missing origin/dev poisons it",
            'devsha="$(git rev-parse --verify -q origin/dev 2>/dev/null || git rev-parse --verify -q dev 2>/dev/null || true)"',
            'devsha="$(git rev-parse origin/dev 2>/dev/null || git rev-parse dev 2>/dev/null || true)"',
            "release-gate (#1337): CONTROL: an uncommitted stamp for dev's tip permits",
        ),
        Mutation(
            # WITHOUT the carve-out the gate denies every promotion of its own source repo. That is
            # a gate wrong about correct code: the maintainer overrides it every release or turns
            # it off, and then it protects nobody. It blocked v1.134.0 before this landed.
            "the marketplace carve-out is removed, so the gate blocks its own repo",
            'if [ -f ".claude-plugin/marketplace.json" ]; then',
            "if false; then",
            "the marketplace's OWN repo is not a consumer",
        ),
        Mutation(
            # THE OTHER HALF, and the one that decides whether this is a carve-out or a hole. Fire
            # it unconditionally and the gate stops gating -- every project promotes uncertified.
            # Keyed on marketplace.json rather than "has no qa/ directory" precisely because the
            # latter is the ordinary state of an app that never ran /qa-flow:setup-qa.
            "the carve-out fires for every repo, so nothing is ever gated",
            'if [ -f ".claude-plugin/marketplace.json" ]; then',
            "if true; then",
            "an ordinary repo with no certification is STILL blocked",
        ),
    ),
)
