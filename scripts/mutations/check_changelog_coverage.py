"""Mutation guard: check_changelog_coverage. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #105. The first mutation is the whole point of the file: a 200 that renders an error is the
# page every status check calls healthy, so the rule that catches it must be proven to fire.
GUARD = Guard(
    # #728. Three clauses, three mutations. It has to fire on a real omission AND stay silent on
    # the common case -- it exists because a real omission slipped through every existing gate.
    name="check_changelog_coverage",
    subject="scripts/check_changelog_coverage.py",
    selftest="scripts/check_changelog_coverage.py",
    needs=(".claude-plugin", "scripts"),
    mutations=(
        Mutation(
            "a component with pre-existing bullets never needs a new one",
            "        added = now.get(comp, set()) - was.get(comp, set())",
            "        added = now.get(comp, set())",
            "a changed skill with no new bullet is a finding",
        ),
        Mutation(
            # Requiring a note for every script edit would fire on correct work.
            "maintainer-only changes start demanding a component note",
            '    touched.discard("repository")',
            "    pass",
            "a repository-only change is silent",
        ),
        Mutation(
            "any line counts as a bullet, so renaming a heading looks like writing a note",
            "        elif owner and BULLET.match(line):",
            "        elif owner:",
            "converting a heading is not a note",
        ),
    ),
)
