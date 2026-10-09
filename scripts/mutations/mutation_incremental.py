"""Mutation guard: mutation_incremental (#1738, #1739). Run by scripts/mutation_check.py.

The module decides what the mutation harness SKIPS and which shard OWNS a guard. A rule that goes quiet here makes the full sweep
claim a proof it did not run, so each rule is broken once and the case that names it must trip.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="mutation_incremental",
    subject="scripts/mutation_incremental.py",
    selftest="scripts/mutation_incremental_selftest.py",
    mutations=(
        # ---- what a guard's hash covers ----
        Mutation(
            "the hash ignores a guard's needs files, so a changed fixture is skipped as unchanged",
            "    staged = [guard.subject, guard.selftest, *guard.deps, *guard.needs]",
            "    staged = [guard.subject, guard.selftest, *guard.deps]",
            "a change to a needs file changes the hash",
        ),
        Mutation(
            "the hash ignores a guard's deps",
            "    staged = [guard.subject, guard.selftest, *guard.deps, *guard.needs]",
            "    staged = [guard.subject, guard.selftest, *guard.needs]",
            "a change to a dep changes the hash",
        ),
        Mutation(
            "the hash ignores the guard's own mutation list, so a new mutation is never run",
            "    return [module] + [f\"{base}{p}\" for p in staged]",
            "    return [f\"{base}{p}\" for p in staged]",
            "a change to the guard's own mutation module changes the hash",
        ),
        Mutation(
            "the hash ignores the guard's base, so a plugin guard hashes the wrong files",
            '    base = "" if guard.base in (".", "") else guard.base.rstrip("/") + "/"',
            '    base = ""',
            "a plugin-based guard hashes the files under its base",
        ),
        Mutation(
            "a needs directory is hashed one level deep, so a nested fixture is skipped as unchanged",
            '        for child in sorted(p for p in path.rglob("*") if',
            '        for child in sorted(p for p in path.glob("*") if',
            "a file NESTED under a needs directory is part of the hash",
        ),
        Mutation(
            "a missing file hashes like an empty one",
            '        h.update(b"MISSING\\0")',
            '        h.update(hashlib.sha256(b"").digest())',
            "a needs file that appears changes the hash (missing is not empty)",
        ),
        Mutation(
            "line endings are not normalised, so a CRLF checkout re-runs everything",
            '        data = data.replace(b"\\r\\n", b"\\n")',
            "        data = data",
            "a CRLF checkout of the same text is not a change",
        ),
        Mutation(
            "line endings are normalised in binary files too",
            '    if b"\\0" not in data[:8000]:',
            "    if True:",
            "a binary file is hashed byte for byte",
        ),
        Mutation(
            "the harness hash leaves out a helper the runner leans on",
            '    "plugins/rails-flow/scripts/process_containment.py",\n)',
            ")",
            "editing a helper the runner leans on changes the harness hash",
        ),
        # ---- when a guard is skipped ----
        Mutation(
            "a harness change does not force a full run",
            '    if not entry or entry["harness"] != harness:',
            "    if not entry:",
            "a harness change forces a full run",
        ),
        Mutation(
            "a guard whose hash changed is skipped anyway",
            '    return {name: entry["commit"] for name, digest in hashes.items() if entry["guards"].get(name) == digest}',
            '    return {name: entry["commit"] for name, digest in hashes.items() if entry["guards"].get(name) is not None}',
            "a guard whose hash changed is NOT skipped",
        ),
        Mutation(
            "a guard that never passed is skipped, so nothing ever proves it",
            '    return {name: entry["commit"] for name, digest in hashes.items() if entry["guards"].get(name) == digest}',
            '    return {name: entry["commit"] for name, digest in hashes.items() if entry["guards"].get(name, digest) == digest}',
            "a guard with no recorded hash runs",
        ),
        Mutation(
            "the record of one OS vouches for another",
            '    entry = (proof or {}).get("systems", {}).get(system)',
            '    entry = (proof or {}).get("systems", {}).get("linux")',
            "a record for another OS skips nothing",
        ),
        Mutation(
            "--full still skips unchanged guards",
            "    if not full and not named:",
            "    if not named:",
            "--full skips nothing",
        ),
        Mutation(
            "a guard named with --guard is skipped",
            "    if not full and not named:",
            "    if not full:",
            "a guard named with --guard is run, not skipped",
        ),
        # ---- the record file ----
        Mutation(
            "writing one OS erases the others",
            '    current = load_proof(path) or {"systems": {}}',
            '    current = {"systems": {}}',
            "writing one OS keeps another OS's entry",
        ),
        Mutation(
            "a malformed record is read as valid",
            "    if not isinstance(systems, dict) or not all(",
            "    if False and not all(",
            "a malformed record",
        ),
        # ---- shards ----
        Mutation(
            "a shard index outside 1..N is accepted",
            "    if not 1 <= index <= count:",
            "    if False:",
            "shard: '0/4' is refused",
        ),
        Mutation(
            "the split is by count: a guard weighs one whatever it costs",
            "        load[lightest] += weights.get(name, default)",
            "        load[lightest] += 1.0",
            "the split follows cost, not count",
        ),
        Mutation(
            "the lightest shard is not chosen: guards deal out in turn, so the heaviest ones can share a shard",
            "        lightest = min(range(count), key=lambda i: (load[i], i))",
            "        lightest = sum(len(s) for s in shards) % count",
            "one heavy guard against nine light ones is exactly even",
        ),
        Mutation(
            "the heaviest guard is not placed first, so the split is order-dependent",
            "    for name in sorted(names, key=lambda n: (-weights.get(n, default), n)):",
            "    for name in names:",
            "the assignment is stable",
        ),
        # ---- the summary ----
        Mutation(
            "a missing shard is not reported",
            "        if index not in seen:",
            "        if False:",
            "a MISSING shard is a problem, not a pass",
        ),
        Mutation(
            "the same shard reported twice replaces the first",
            "        elif index in seen:",
            "        elif False:",
            "the same shard twice is a problem",
        ),
        Mutation(
            "shards for different commits are merged",
            '    for key in ("os", "commit", "harness"):',
            '    for key in ("os", "harness"):',
            "shards for different commits are refused",
        ),
        Mutation(
            "shards for different harnesses are merged",
            '    for key in ("os", "commit", "harness"):',
            '    for key in ("os", "commit"):',
            "shards for different harnesses are refused",
        ),
        Mutation(
            "a guard no shard ran is not reported",
            "    for name in sorted(names - set(covered)):",
            "    for name in []:",
            "a guard no shard ran is a problem",
        ),
        Mutation(
            "a guard two shards ran is not reported",
            "    for name in sorted(n for n, c in covered.items() if c > 1):",
            "    for name in sorted(n for n, c in covered.items() if c > 99):",
            "a guard two shards ran is a problem",
        ),
        Mutation(
            "a guard that no longer exists is not reported",
            "    for name in sorted(set(covered) - names):",
            "    for name in []:",
            "a guard that no longer exists is a problem",
        ),
        Mutation(
            "a shard run as one of a different N is accepted",
            '        if result.get("of") != expect:',
            "        if False:",
            "a shard run as one of a different N is a problem",
        ),
        Mutation(
            "a guard a shard skipped is not counted as covered",
            '        for name in list(result.get("guards", {})) + list(result.get("skipped", {})):',
            '        for name in list(result.get("guards", {})):',
            "a skipped guard counts as covered",
        ),
        Mutation(
            "a set with skipped guards is called a full run, so a proof is written for guards that did not run",
            '"full": all(r.get("full") for r in seen.values()),',
            '"full": True,',
            "and the set is then NOT full",
        ),
        Mutation(
            "any shard result is accepted by the summary",
            '    if result == "success":',
            "    if True:",
            "result 'failure' in full mode is refused",
        ),
        Mutation(
            "a skipped (never-run) shard passes the summary in full mode",
            '    if fast and result in ("skipped", ""):',
            '    if result in ("skipped", ""):',
            "result 'skipped' in full mode is refused",
        ),
        Mutation(
            "a failed shard passes the summary in fast mode",
            '    if fast and result in ("skipped", ""):',
            "    if fast:",
            "result 'failure' in fast mode is refused",
        ),
        # ---- where a cost record may come from ----
        Mutation(
            "--rebaseline is accepted from any machine",
            '    if env.get("GITHUB_ACTIONS") == "true":',
            "    if True:",
            "refused outside CI without --host",
        ),
        Mutation(
            "an explicit --host is ignored",
            "    if host:\n        return host, None",
            "    if False:\n        return host, None",
            "an explicit --host is accepted",
        ),
        # ---- the summary job's command line ----
        Mutation(
            "the verdict command always exits 0, so a failed shard passes the summary job",
            "    return 0 if ok else 1",
            "    return 0",
            "verdict CLI: a failed shard exits 1",
        ),
        Mutation(
            "the verdict command reads the mode backwards",
            '    ok, message = summary_verdict(args[1], args[2] == "fast")',
            '    ok, message = summary_verdict(args[1], args[2] != "fast")',
            "verdict CLI: a shard that never ran exits 1 in full mode",
        ),
        Mutation(
            "the verdict command accepts any mode",
            '    if len(args) != 3 or args[0] != "verdict" or args[2] not in ("fast", "full"):',
            '    if len(args) != 3 or args[0] != "verdict":',
            "verdict CLI: an unknown mode is misuse (2)",
        ),
    ),
)
