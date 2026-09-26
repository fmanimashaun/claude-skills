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
    needs=("plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        # #1337: the stamp's own commit invalidates it again, or any delta slips through.
        Mutation(
            "an ancestor stamp is never accepted, so committing the stamp denies its promotion",
            '        ""|"qa/CERTIFICATION") : ;;',
            '        "__never__") : ;;',
            "release-gate (#1337): the stamp committed on top of the tested sha still permits",
        ),
        Mutation(
            "any delta after an ancestor stamp is accepted",
            '        ""|"qa/CERTIFICATION") : ;;',
            '        *) : ;;',
            "release-gate (#1337): a code change after the tested sha is denied, naming the path",
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
