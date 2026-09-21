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
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
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
