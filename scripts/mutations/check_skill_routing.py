"""Mutation guard: check_skill_routing. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #158. The routing regex is the mutation that matters here. Its whole job is telling a real
# dispatch entry apart from prose that happens to name the file, and getting that wrong in the
# LOOSE direction is silent: every reference looks routed and the gate reports clean forever.
# That is precisely how `design-system/references/coverage.md` hid at depth 2 while two other
# reference files name it in passing.
GUARD = Guard(
    name="check_skill_routing",
    subject="scripts/check_skill_routing.py",
    selftest="scripts/check_skill_routing.py",
    mutations=(
        Mutation(
            "the `references/` anchor becomes optional, so prose naming a file counts as routing",
            'REF_PATH_RE = re.compile(r"(?:\\./)?references/([A-Za-z0-9._-]+\\.md)")',
            'REF_PATH_RE = re.compile(r"(?:\\./)?(?:references/)?([A-Za-z0-9._-]+\\.md)")',
            "a bare prose mention is NOT routing",
        ),
        Mutation(
            "the unrouted rule stops reporting, so an orphaned reference is clean",
            "    for missing in sorted(present - routed):",
            "    for missing in []:",
            "an unrouted reference is a finding",
        ),
        Mutation(
            "the dead-link rule stops reporting, so a router pointing at nothing is clean",
            "    for dead in sorted(routed - present):",
            "    for dead in []:",
            "a dead reference link is a finding",
        ),
        Mutation(
            "the Level-2 budget goes off-by-one and fires on a compliant 500-line body",
            "    if line_count > MAX_SKILL_LINES:",
            "    if line_count >= MAX_SKILL_LINES:",
            "a body exactly AT the budget is silent",
        ),
        Mutation(
            "a skill directory with no SKILL.md becomes a silent skip instead of an error",
            '        raise Unreadable(f"{name}/: no SKILL.md")',
            "        return [], 0",
            "skipped instead of raising",
        ),
    ),
)
