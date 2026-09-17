"""Mutation guard: session_coordinator. Declared here, run by scripts/mutation_check.py (#866).

The subject is a coordinator, which is nothing but checks about other sessions' state — so it is
the most likely thing in the repository to ship green and verify nothing. Two of the five mutations
below are about the detector STAYING SILENT: a coordinator that fires on everything is not
over-eager, it is useless, and its characteristic failure (a false escalation at a session whose
work is proceeding normally) is invisible to any fixture that only checks that findings appear.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="session_coordinator",
    subject="plugins/rails-flow/scripts/session_coordinator.py",
    selftest="plugins/rails-flow/scripts/session_coordinator.py",
    mutations=(
        Mutation(
            # #1010's hardest acceptance line: "it cannot merge a PR or write to a repository --
            # enforced, not documented". A prefix rule reads as careful and admits `gh pr merge`.
            "the read-only boundary accepts anything, so the coordinator can act on the world",
            "    if _key(argv) not in READ_ONLY:",
            "    if False:",
            # The spy fires, not the "was NOT refused" branch: with the boundary gone the call
            # reaches the executor, which is the failure in its most literal form.
            "EXECUTED a write command",
        ),
        Mutation(
            "a naive clock is accepted again — the 60-minute error that produced two false "
            "escalations in five minutes",
            "    if now.tzinfo is None or now.utcoffset() is None:",
            "    if False:",
            "accepted a NAIVE clock",
        ),
        Mutation(
            # The negative arm. Deleting the floor makes the module MORE talkative, which is how
            # this class of defect survives review: it looks like sensitivity.
            "the stall floor is removed, so every young green PR is escalated",
            "        if age < STALL_MINUTES:",
            "        if False:",
            "that is the false escalation",
        ),
        Mutation(
            "a busy session is treated as parked, so the coordinator chases sessions mid-task",
            "        if session is not None and not session.idle:",
            "        if False:",
            "BUSY author's old green PR",
        ),
        Mutation(
            # Silence is a feature with a cost: a board every tick trains its readers to skip it.
            "it reports on single-session work, which is how an advisory gets switched off",
            "    if len(sessions) < 2:",
            "    if False:",
            "single session produced output",
        ),
        Mutation(
            "a generated conflict is handed to the author as a judgement call, which is how a "
            "hand-resolved graph nearly lost a subsystem",
            "    for pattern, command in GENERATED:",
            "    for pattern, command in ():",
            "generated conflict was not named as regenerable",
        ),
        Mutation(
            "assignment crosses a repository boundary the session was never authorised into",
            "        if session.repo is not None and session.repo != repo:",
            "        if False:",
            "crossed a repository boundary",
        ),
    ),
)
