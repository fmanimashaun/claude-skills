"""Mutation guard: derive_mandated_gems. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #797. The list is DERIVED from the rails-8 doctrine and committed beside the checker,
    # because a runtime read would cross a plugin boundary -- #617's class, already recurred
    # twice. This guard covers the derivation; the drift gate covers the artifact.
    name="derive_mandated_gems",
    subject="scripts/derive_mandated_gems.py",
    selftest="scripts/derive_mandated_gems.py",
    needs=("skills/rails-8/references/testing.md",),
    mutations=(
        Mutation(
            # `re.match` anchors at position 0, which is what excludes `# gem "x"`. An explicit
            # comment-skip AND a `^` in the pattern both did the same job, so a mutation
            # removing any ONE survived. Two guards for one behaviour means neither is testable.
            "match becomes search, so a commented gem is derived as required",
            "(GEM.match(l) for l in block.splitlines())",
            "(GEM.search(l) for l in block.splitlines())",
            "a COMMENTED gem is not derived",
        ),
        Mutation(
            "an empty derivation is accepted, making the gate unable to fail",
            "    if not gems:",
            "    if False:",
            "an all-commented fence refuses",
        ),
        Mutation(
            # "the first ruby fence" would follow any edit that inserted an earlier one, and the
            # failure would be a silently shorter list.
            "the first fence is taken instead of the anchored one",
            "    hits = [b for b in blocks if anchor in b]",
            "    hits = blocks[:1]",
            "an earlier unrelated fence is not chosen",
        ),
    ),
)
