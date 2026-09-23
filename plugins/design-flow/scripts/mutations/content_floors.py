"""Mutation guard: content_floors. Declared here, run by scripts/mutation_check.py (#1187).

The mutation that matters most is the one that makes the ratchet a LICENCE: if a missing floor file
stops meaning zero tolerance, every greenfield project silently loses the gate, and nothing in the
output says so. The rest guard the two directions and the per-rule split.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="content_floors",
    subject="scripts/content_floors.py",
    selftest="scripts/content_floors.py",
    mutations=(
        # #1214. The version a floor was cut with.
        Mutation(
            "a version mismatch stops warning, so a floor counted by a different detector looks agreed",
            "    elif cut_with != now_with:",
            "    elif False:",
            "a version mismatch WARNS",
        ),
        # THE CONTROL'S MUTATION. Without it, "warns on mismatch" is satisfied by warning always --
        # and a warning on every run is one nobody reads.
        Mutation(
            "every run warns, whether or not the versions differ",
            "    elif cut_with != now_with:",
            "    elif True:",
            "the SAME version prints no warning",
        ),
        # The mismatch must stay a WARNING. Failing would turn every toolchain bump red.
        Mutation(
            "a version mismatch fails the gate instead of warning",
            "    cut_with = floor_version(root, gate)",
            "    cut_with = floor_version(root, gate)\n    failed = failed or floor_version(root, gate) != toolchain_version()",
            "a mismatch does NOT fail the gate",
        ),
        Mutation(
            "the version is no longer recorded, so every later floor reads as pre-#1214",
            "        versions[gate] = toolchain_version()",
            "        versions.pop(gate, None)",
            "set_floor records the version it counted with",
        ),
        Mutation(
            "the version is hardcoded instead of read from plugin.json",
            '        return str(json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version") or "unknown")',
            '        return "1.43.0"',
            "the version is read from plugin.json at runtime",
        ),
        Mutation(
            "a floor with no recorded version is silently treated as agreeing",
            "    if cut_with is None:",
            "    if False:",
            "a floor with no version says UNKNOWN",
        ),
        # THE DANGEROUS ONE. No floor file must keep meaning "no debt is sanctioned".
        Mutation(
            "a missing floor file becomes a pass, so every greenfield project loses the gate",
            "    if floors is None:\n        return (1 if findings else 0), []",
            "    if floors is None:\n        return 0, []",
            "no floor file: findings still fail",
        ),
        Mutation(
            "growth above the floor stops failing — sanctioned debt becomes a budget",
            "        elif now > floor:",
            "        elif False:",
            "above the floor: fails",
        ),
        Mutation(
            "a stale floor stops failing, so a rule may silently drift back to an old number",
            "        elif now < floor:",
            "        elif False:",
            "below the floor: fails as STALE",
        ),
        # THE PER-RULE SPLIT, which is the whole reason the floors are a dict and not an int.
        Mutation(
            "every finding is tallied under one key, so a swap between rules reads as no change",
            "        out[rule_of(f)] = out.get(rule_of(f), 0) + 1",
            '        out["*"] = out.get("*", 0) + 1',
            "a swap that keeps the total is still caught",
        ),
        # An unsanctioned rule must not inherit its gate's permission.
        Mutation(
            "a rule with no recorded floor is skipped instead of refused",
            "        if floor is None:\n            failed = True",
            "        if floor is None:\n            continue",
            "an unsanctioned rule fails even when the others are at their floor",
        ),
        # Iterating only what is found would hide a floor for a rule that has gone to zero.
        Mutation(
            "only the rules still found are checked, so a fully-fixed rule's stale floor is invisible",
            "    for rule in sorted(set(counts) | set(floors)):",
            "    for rule in sorted(counts):",
            "a rule fixed to ZERO still reports its stale floor",
        ),
        Mutation(
            "an emptied gate keeps its row, so strictness is never restored",
            '        floors.pop(gate, None)           # nothing left to sanction: remove the row, restore strict',
            "        pass",
            "set-floor with nothing left removes the row, restoring strict",
        ),
    ),
)
