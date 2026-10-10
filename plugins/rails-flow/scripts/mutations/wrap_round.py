"""Mutation guard: wrap_round. Declared here, run by scripts/mutation_check.py (#866).

The round's value is that it does not take a reply on trust, so every mutation below makes it believe
something it should check: a write it should refuse, a short SHA, silence, a worktree still present,
a branch that was never pushed, or a heavy run it should wait out.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="wrap_round",
    subject="scripts/wrap_round.py",
    selftest="scripts/wrap_round.py",
    mutations=(
        Mutation(
            "the read-only boundary accepts anything, so the round can remove a worktree itself",
            "    if not any(tuple(argv[:len(p)]) == p for p in READ_ONLY):",
            "    if False:",
            "EXECUTED a command that is not a read",
        ),
        Mutation(
            "a short or placeholder SHA is accepted as a claim",
            "        if not SHA.fullmatch(head):",
            "        if not head:",
            "verify: a short SHA is refused, not prefix-matched",
        ),
        Mutation(
            "a session holding a heavy run is sent the round mid-run",
            "        elif s.get(\"heavy_run\"):",
            "        elif False:",
            "plan: a session holding a heavy run is skipped, not interrupted",
        ),
        Mutation(
            "no reply is read as READY",
            "            row[\"state\"], row[\"findings\"] = \"MISSING\", [\"no reply: silence is not READY\"]",
            "            row[\"state\"], row[\"findings\"] = \"READY\", []",
            "verify: no reply is MISSING, never READY",
        ),
        Mutation(
            "a worktree still in `git worktree list` is taken as removed",
            "            if str(path).rstrip(\"/\") in present:",
            "            if False:",
            "verify: a worktree claimed removed but still listed is a MISMATCH",
        ),
        Mutation(
            "a branch that is neither pushed nor merged passes",
            "                if code != 0:",
            "                if False:",
            "verify: an unpushed, unmerged branch is a MISMATCH",
        ),
    ),
)
