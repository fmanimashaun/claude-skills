"""Mutation guard: doctrine_map. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #655. The map's own failure mode is the one it exists to catch: a row that advertises
    # enforcement which no longer exists reads as coverage. Each mutation removes one validator
    # and names the fixture that must then fail.
    name="doctrine_map",
    subject="scripts/doctrine_map.py",
    selftest="scripts/doctrine_map.py",
    needs=(".claude-plugin", ".github", ".claude", "scripts", "plugins", "skills", "docs",
           "CLAUDE.md", "AGENTS.md"),
    mutations=(
        # #798. The map answered "which claim is enforced by what" for repo-process doctrine
        # only -- skills/rails-8, hotwire and design-system were not declared sources at all,
        # so the question was unanswerable for the doctrine users actually follow. Three claims
        # (#778/#797, #779, #792) were each found by a downstream project, one at a time.
        Mutation(
            # 49 unmapped files would fail the coverage gate on the first run -- red on day one,
            # which #800 spent a whole issue removing. So the mapped count RATCHETS.
            "the shipped-surface ratchet never fires, so coverage can silently regress",
            "    if len(mapped) < SHIPPED_FLOOR:",
            "    if False:",
            "one mapped file below a floor of 2 is a finding",
        ),
        Mutation(
            "every shipped file counts as mapped, so the floor is met by declaring them",
            "    mapped = sorted(s for s, n in shipped_counts.items() if n)",
            "    mapped = sorted(shipped_counts)",
            "two rows in ONE file does not meet a floor of 2 files",
        ),
        Mutation(
            "no shipped row is counted, so mapping a source changes nothing",
            "        if c.stated_in in shipped_counts:\n            shipped_counts[c.stated_in] += 1",
            "        if False:\n            shipped_counts[c.stated_in] += 1",
            "...and two mapped files meets it",
        ),
        Mutation(
            # Both surfaces are declared; rejecting the shipped one would make every new row an
            # `undeclared source` finding and the extension unusable.
            "shipped sources are rejected as undeclared",
            "        if c.stated_in not in sources and c.stated_in not in SHIPPED_SOURCES:",
            "        if c.stated_in not in sources:",
            "the real registry validates clean",
        ),
        Mutation(
            "a reworded or deleted claim keeps its row, so the map advertises doctrine we no "
            "longer state",
            "        elif c.anchor not in body:",
            "        elif False:",
            "anchor missing fires",
        ),
        Mutation(
            "a row may cite a gate, guard or rule that has been deleted",
            "            ok, why = resolver.resolve(ref)",
            '            ok, why = True, ""',
            "bad gate fires",
        ),
        Mutation(
            "a gap that got fixed stays listed as a gap -- the map going stale in the direction "
            "nobody looks",
            "            if resolved:",
            "            if False:",
            "resolved gap fires",
        ),
        Mutation(
            # A hook script on disk that nothing invokes is precisely the shape of defect this
            # map is for, so existence must not count as enforcement.
            "an existing but unwired hook counts as enforcement",
            '            return (name in self.hooks), f"hook script {name} exists but nothing wires it"',
            '            return True, ""',
            "an existing but unwired hook does not resolve",
        ),
    ),
)
