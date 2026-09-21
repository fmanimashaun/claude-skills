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
    subject="scripts/session_coordinator.py",
    selftest="scripts/session_coordinator.py",
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
            # #1018. The guard above was unreachable for as long as the join used a key `gh` has
            # never returned, so the arm above passed while the production path escalated at
            # everyone. Mutating the JOIN is the only way to see that.
            "the PR-to-session join goes back to a key `gh` never emits, so the idle guard is dead "
            "again and every green PR chases a working session",
            "        session = by_branch.get(branch_key(pr.get(\"headRefName\")))",
            "        session = by_branch.get(branch_key(pr.get(\"session\")))",
            "BUSY author's old green PR",
        ),
        Mutation(
            "a fatal git failure is folded back into 'matched nothing', so a malformed pattern "
            "reads as 'no numbers are claimed'",
            "        if failure.returncode != 1:     # 1 is \"no match\"; 128 is \"your pattern is malformed\"",
            "        if False:",
            "FATAL git failure was reported",
        ),
        Mutation(
            # #1023. The finding stays correct and becomes unreadable, which is the same as not
            # firing: the exit code and "nothing was checked" are at the end of 976 characters.
            "the failed-query detail prints every remote ref again, burying the exit code",
            "    if len(argv) <= keep:",
            "    if True:",
            "was printed in full",
        ),
        Mutation(
            "branch spellings stop being normalised, so `origin/fix/b` reads as unannounced and a "
            "BUSY session is chased",
            "        if name.startswith(prefix):",
            "        if False:",
            "was treated as not having announced it",
        ),
        Mutation(
            "two sessions claiming one branch stops being reported — the day's actual incident, "
            "which no path list predicted because neither had announced a path yet",
            "        if len(claiming) < 2:",
            "        if True:",
            "claiming one branch produced no collision",
        ),
        Mutation(
            # Last-wins made the verdict depend on ListAgents ordering. The fixture reverses the
            # list and compares, so only a deterministic answer passes.
            "an ambiguously-claimed branch resolves to whichever session came last in the list",
            "    by_branch = {b: s[0] for b, s in claimants.items() if len(s) == 1}",
            "    by_branch = {b: s[-1] for b, s in claimants.items()}",
            "named one of the claimants anyway",
        ),
        Mutation(
            "the collector stops asking for the fields the fixtures are built from",
            '                  ",".join(COLLECTED_FIELDS)], repo_root)',
            '                  "number,createdAt"], repo_root)',
            "does not ask for the fields",
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
            "    for pattern, command in generated:",
            "    for pattern, command in ():",
            "generated conflict was not named as regenerable",
        ),
        Mutation(
            # Silence reads as confirmation. An empty search and a wrong path are the same string.
            "an empty ledger search is reported as a clean result instead of as absent",
            '        return Finding("claims-absent", f"{ledger} matched nothing on any remote ref",',
            '        return Finding("claims", f"{ledger} matched nothing on any remote ref",',
            "empty search was reported as a clean result",
        ),
        Mutation(
            "a repository with no remote refs is reported as checked",
            '        return Finding("claims-absent", f"no remote refs to search for {ledger}",',
            '        return Finding("claims", f"no remote refs to search for {ledger}",',
            "no remote refs was reported as a clean result",
        ),
        Mutation(
            "claims come back lowest-first, so the query agrees with the stale ledger it replaces",
            "    return max(claimed) if claimed else None",
            "    return min(claimed) if claimed else None",
            "did not return the highest number",
        ),
        Mutation(
            "migration ordering stops being checked, and a migration below the schema version is "
            "marked applied and never runs",
            "        if stamp <= schema_version:",
            "        if False:",
            "numbered BELOW schema.rb produced no finding",
        ),
        Mutation(
            # The boundary, not the rule: equal IS already applied, so `<` is a real off-by-one
            # that no fixture below the version can see.
            "the ordering check becomes strictly-below, so a migration numbered exactly at the "
            "schema version passes",
            "        if stamp <= schema_version:",
            "        if stamp < schema_version:",
            "EXACTLY at the schema version",
        ),
        Mutation(
            "assignment crosses a repository boundary the session was never authorised into",
            "        if session.repo is not None and session.repo != repo:",
            "        if False:",
            "crossed a repository boundary",
        ),
    ),
)
