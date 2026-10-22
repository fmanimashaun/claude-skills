"""Mutation guard: doctrine_map. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #655. The map's own failure mode is the one it exists to catch: a row that advertises
    # enforcement which no longer exists reads as coverage. Each mutation removes one validator
    # and names the fixture that must then fail.
    name="doctrine_map",
    subject="scripts/doctrine_map.py",
    selftest="scripts/doctrine_map.py",
    needs=(".claude-plugin", ".github", ".claude", "scripts", "plugins", "docs",
           "CLAUDE.md", "AGENTS.md"),
    mutations=(
        # #798. The map answered "which claim is enforced by what" for repo-process doctrine
        # only -- plugins/rails-stack/skills/rails-8, hotwire and design-system were not declared sources at all,
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
        Mutation(
            # #2224: advice must stand on a verified source or a recorded decision.
            "unbased advice beyond the baseline is accepted",
            "            elif not c.basis and (c.stated_in, c.anchor) not in unbased:",
            "            elif False:",
            "unbased advice fires",
        ),
        Mutation(
            "the unbased baseline can keep a row that gained a basis, so the count never has to fall",
            "        if entry not in still_unbased:",
            "        if False:",
            "a baseline entry whose row gained a basis fires",
        ),
        Mutation(
            "a source with no version passes as a basis",
            'BASIS = re.compile(r"source: \\S.* @ \\S.*|decision: #(\\d+)")',
            'BASIS = re.compile(r"source: \\S.*|decision: #(\\d+)")',
            "a source with no version is malformed",
        ),
        Mutation(
            "a decision basis need not be cited in refs",
            "            elif m is not None and m.group(1) and int(m.group(1)) not in c.refs:",
            "            elif False:",
            "a decision the row does not cite in refs fires",
        ),
        Mutation(
            # #2254 review: the list agreeing with itself is no ratchet; the base's list is the authority.
            "an entry the base never allowed is accepted, so a new unbased row ships with its own grandfather entry",
            "            f\"refused, not grandfathered (#2224)\" for e in unbased if tuple(e) not in allowed and (_was(e[0]), e[1]) not in allowed]",
            "            f\"refused, not grandfathered (#2224)\" for e in unbased if False]",
            "a new row plus its own new entry is refused against the base's list",
        ),
        Mutation(
            "an unreadable base passes",
            "    if allowed is None:\n        return [f\"unbased-advice baseline unchecked",
            "    if allowed is None:\n        return []\n        return [f\"unbased-advice baseline unchecked",
            "an unreadable base is a finding, never a pass",
        ),
        Mutation(
            "--check stops comparing against the base",
            "    return validate() + ratchet_findings(ADVICE_UNBASED, *base_baseline((read or read_base)()))",
            "    return validate()",
            "--check compares the list against the base",
        ),
        Mutation(
            "a source basis need not cite what checked it",
            "            elif m is not None and not m.group(1) and not c.refs:",
            "            elif False:",
            "a source the row does not cite in refs fires",
        ),
        Mutation(
            "a base that is HEAD is compared with HEAD itself, so a list grown in HEAD's commit agrees with itself",
            "    if point == head:\n        point = run(\"rev-parse\", \"HEAD^1\")",
            "    if False:\n        point = run(\"rev-parse\", \"HEAD^1\")",
            "is measured from HEAD's parent, never HEAD",
        ),
        Mutation(
            "a base row whose kind is positional is not read, so its entry is falsely refused",
            '                kw = dict(zip(("claim", "stated_in", "anchor", "kind"), call.args))',
            "                kw = {}",
            "a base row whose kind is positional is read",
        ),
        Mutation(
            "a moved row is read under its new path only, so a skill that moved looks like a new advice row",
            "(_was(e[0]), e[1]) not in allowed]",
            "True]",
            "a row that moved with its skill is not a new row (#2186)",
        ),
        Mutation(
            "a path that did not move is read as the moved one, so any row is forgiven",
            "            return old + path[len(new):]\n    return path",
            '            return old + path[len(new):]\n    return "plugins/rails-stack/skills/s/SKILL.md"',
            "a row under a path that did not move is not forgiven by the move",
        ),
    ),
)
