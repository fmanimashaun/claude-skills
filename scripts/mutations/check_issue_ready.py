"""Mutation guard: check_issue_ready. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #849. The shipped readiness gate for a project's own tracker (the marketplace has issue_graph.py).
GUARD = Guard(
    name="check_issue_ready",
    subject="plugins/rails-flow/scripts/check_issue_ready.py",
    selftest="plugins/rails-flow/scripts/check_issue_ready.py",
    mutations=(
        # #849 part 1: the computed queue. Each of these is a way the order stops being computed.
        Mutation(
            "priority stops ordering the queue",
            "        return (PRIORITY_RANK.get(prio, 9), 0 if labels & BUG_LABELS else 1, issue.get(\"createdAt\", \"\"), issue[\"number\"])",
            "        return (0, 0 if labels & BUG_LABELS else 1, issue.get(\"createdAt\", \"\"), issue[\"number\"])",
            "READY is ordered P1 before P2",
        ),
        Mutation(
            "a blocked issue is ranked as ready",
            "        (blocked if open_waits else ready).append((issue, open_waits))",
            "        ready.append((issue, open_waits))",
            "a P1 that is BLOCKED is not ranked as ready",
        ),
        Mutation(
            "needs-info issues are queued as work",
            "        if labels & SKIP_LABELS:\n            skipped.append(issue)\n            continue",
            "        if False:\n            skipped.append(issue)\n            continue",
            "needs-info is skipped",
        ),
        Mutation(
            "a cycle is no longer a graph error, so the queue is printed from a wrong graph",
            '                errors.append("cycle: " + " -> ".join(f"#{x}" for x in cycle))',
            "                pass",
            "a cycle is a graph error",
        ),
        Mutation(
            "the coverage line stops counting",
            "        if e[\"depends-on\"] or e[\"blocks\"]:\n            declared += 1",
            "        if False:\n            declared += 1",
            "the coverage line counts issues that declare edges",
        ),

        Mutation(
            "an issue whose dependency is still open is no longer refused",
            "        open_waits = sorted(w for w in waits if w in open_numbers)",
            "        open_waits = []",
            "an issue whose depends-on is OPEN is refused",
        ),
        Mutation(
            "a closed issue is started again",
            '        if record.get("state", "").upper() != "OPEN":',
            "        if False:",
            "a closed issue is refused",
        ),
        Mutation(
            "other fences stop being stripped, so a Ruby `depends_on:` in a code sample reads as an edge",
            '        text = _ANY_FENCE.sub("", body)  # strip every other fence -- `depends_on: :account` lives there',
            "        text = body",
            "a fenced SAMPLE of the syntax is not an edge",
        ),
        Mutation(
            "`blocks:` on another issue is no longer read as a dependency",
            '        for target in parse_edges(issue.get("body", "")).get("blocks", set()):',
            "        for target in ():",
            "declared on ANOTHER open issue is read as a dependency",
        ),
        Mutation(
            "edges inside the named set stop being satisfied by the branch, so grouping is refused",
            "        waits -= named_set  # edges inside the named set are satisfied by the branch",
            "        pass",
            "edges between the named issues are satisfied by the branch",
        ),
        Mutation(
            "naming no issue becomes a vacuous READY",
            '    if not named:\n        return [], ["no issue named"]',
            "    if False:\n        return [], []",
            "naming no issue is a refusal",
        ),
    ),
)
