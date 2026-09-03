"""Mutation guard: issue_graph. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="issue_graph",
    subject="scripts/issue_graph.py",
    selftest="scripts/issue_graph.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a dependency cycle stops being a filing error",
            "    cycle = _cycle_in(dependency)",
            "    cycle = None",
            "dependency cycle",
        ),
        Mutation(
            "a full page of gh results is accepted as the whole tracker (#211)",
            "    if len(payload) >= limit:",
            "    if False:",
            "truncation guard",
        ),
        Mutation(
            "declarations under the wrong fence tag go silent again",
            "        if lines and all(_STRICT.match(line) for line in lines):",
            "        if False:",
            "declarations under an untagged fence",
        ),
        # The near-miss half of the same carve-out. Widening `all` to `any` makes the check
        # fire on any fence that merely CONTAINS a declaration — the false positive that
        # would get it switched off. Proves the silence fixtures are load-bearing.
        Mutation(
            "the mistag check widens to any fence containing a declaration",
            "        if lines and all(_STRICT.match(line) for line in lines):",
            "        if lines and any(_STRICT.match(line) for line in lines):",
            "a fence mixing prose with a declaration is a sample",
        ),
        Mutation(
            "a declaration loose in prose stops being reported",
            "        if _STRICT.match(line):",
            "        if False:",
            "a declaration outside any fence",
        ),
        Mutation(
            "a typo'd key silently declares nothing",
            "            if key not in KEYS:",
            "            if False:",
            "typo'd key",
        ),
        Mutation(
            "an edge to an issue that does not exist stops being reported",
            "            if target not in graph.issues:",
            "            if False:",
            "edge to an issue not in the tracker",
        ),
        Mutation(
            "a self-referencing declaration is no longer named as such",
            "                if target == number:",
            "                if False:",
            "self reference",
        ),
        Mutation(
            "the critical-path tiebreak stops preferring the higher priority",
            "    return (lengths.get(number, 1), -PRIORITIES.index(priority) "
            "if priority else -len(PRIORITIES), -number)",
            "    return (lengths.get(number, 1), 0, -number)",
            "critical-path tiebreak",
        ),
        # The doctor runs this selftest as a gate, and a diagnostic that writes into the
        # working tree is a defect however tidy its cleanup looks. Reverting to a repo-local
        # fixture must be caught, not merely tolerated because the file is unlinked after.
        # Anchored on the ONE temp-dir helper every end-to-end fixture goes through, so a
        # second `main()` call cannot quietly acquire its own unguarded write path.
        Mutation(
            "the selftest writes its fixture into the repo again",
            '        with tempfile.TemporaryDirectory(prefix="issue-graph-selftest-") as workdir:',
            "        for workdir in [str(Path(__file__).resolve().parent)]:",
            "left files in scripts/",
        ),
        # The property that makes this a gate rather than a report: a graph known to be
        # broken must print NO queue, because a wrong ordering reads exactly like a right one.
        Mutation(
            "a queue is printed for a graph already known to be invalid",
            '    if graph.problems:\n        print(f"ISSUE GRAPH INVALID',
            '    if False:\n        print(f"ISSUE GRAPH INVALID',
            "cyclic",
        ),
        # --- the gate at the point of use (`--ready`) --------------------------------
        # Both directions, because each alone leaves the other half unguarded: a gate that
        # stops refusing is useless, and a gate that refuses the doctrine's preferred branch
        # shape gets switched off, after which nothing checks the order at all.
        Mutation(
            "--ready stops noticing a blocker outside the requested set",
            "        outside = [p for p in waiting if p not in inside]",
            "        outside = []",
            "an issue waiting on open work is not ready",
        ),
        Mutation(
            "--ready treats a group's own internal dependency as a blocker",
            "    inside = set(wanted)",
            "    inside = set()",
            "a group takes its own internal dependency with it",
        ),
        Mutation(
            "--ready clears an issue that is not in the tracker at all",
            "            problems.append(\n"
            '                f"#{number} is not in the tracker, so nothing is known about what'
            ' it waits on"\n            )',
            "            notes.append(\n"
            '                f"#{number} is not in the tracker, so nothing is known about what'
            ' it waits on"\n            )',
            "an issue absent from the tracker",
        ),
        Mutation(
            "--ready clears an issue that is already closed",
            "        if not issue.is_open:",
            "        if False:",
            "an already-closed issue is not work to start",
        ),
        # The honesty half. Without the caveat a READY on an issue that declared nothing
        # reads as "nothing blocks it" rather than "the tracker names no blocker" — the
        # unverified-negative class, and with the backfill incomplete it is the common case.
        Mutation(
            "a READY verdict stops saying the issue declared no edges",
            "        if number not in graph.declared:",
            "        if False:",
            "coverage caveat",
        ),
        # The other direction: a caveat on EVERY verdict is a caveat nobody reads, which
        # destroys the signal exactly as thoroughly as having none.
        Mutation(
            "the coverage caveat fires on issues that did declare edges",
            "        if number not in graph.declared:",
            "        if True:",
            "declares edges",
        ),
    ),
)
