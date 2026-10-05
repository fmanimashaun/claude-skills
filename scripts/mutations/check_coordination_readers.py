"""Mutation guard: check_coordination_readers. Declared here, run by scripts/mutation_check.py (#866).

#1585. The check keeps the status board's list of record field names in step with the ones coordination.py
writes. Each break below makes it pass over drift it exists to refuse: a write-side rename, a planned name
that now has a writer, a dead declaration, an empty list, a substring that passes for a key, and an exit
code that hides drift.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_coordination_readers",
    subject="scripts/check_coordination_readers.py",
    selftest="scripts/check_coordination_readers.py",
    selftest_args=("--selftest",),
    # The selftest also checks the REAL reader against the REAL writer.
    needs=("plugins/pipeline/scripts/status_board.py", "plugins/rails-flow/hooks/scripts/lib/coordination.py"),
    mutations=(
        Mutation(
            "a rename on the write side is no longer drift",
            "    for k in written:\n        if k not in written_by_writer:",
            "    for k in written:\n        if False:",
            "a rename on the write side is drift",
        ),
        Mutation(
            "a planned name that the writer now writes is no longer drift",
            "    for k in planned:\n        if k in written_by_writer:",
            "    for k in planned:\n        if False:",
            "a planned name that the writer now writes is drift",
        ),
        Mutation(
            "a listed name the reader never reads passes",
            "        if not quoted(body, k):",
            "        if False:",
            "a listed name the reader never reads",
        ),
        Mutation(
            "an empty WRITTEN list passes over nothing",
            "    if not written:",
            "    if False:",
            "an empty WRITTEN list is refused",
        ),
        Mutation(
            "a key name read anywhere in the writer counts as written (the write-site-only rename passes)",
            "    written_by_writer = write_keys(w_text)",
            "    written_by_writer = {k for k in (*written, *planned) if quoted(w_text, k)}",
            "a write-site-only rename passes a stale read",
        ),
        Mutation(
            "a subscript store no longer counts as a write",
            "        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):",
            "        elif False:",
            "a key assigned with a subscript store counts as written",
        ),
        Mutation(
            "a setdefault no longer counts as a write",
            "        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == \"setdefault\" and node.args:",
            "        elif False:",
            "a key written with setdefault counts as written",
        ),
        Mutation(
            "drift exits 0",
            "    return 1 if findings else 0\n\n\n",
            "    return 0\n\n\n",
            "main exits 1 on drift",
        ),
        Mutation(
            "a missing file exits 0",
            "            return 3\n    findings",
            "            return 0\n    findings",
            "a missing file exits 3",
        ),
    ),
)
