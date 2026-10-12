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
            "    if not allowed(argv):",
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
        Mutation(
            "an option is accepted in a positional slot (`ls-remote --upload-pack=<cmd>`)",
            "else not w.startswith(\"-\")",
            "else True",
            "--upload-pack",
        ),
        Mutation(
            "the allowlist accepts nothing, and only refusals are tested",
            "    return any(len(argv) == len(shape)",
            "    return False and any(len(argv) == len(shape)",
            "accept: ",
        ),
        Mutation(
            "a glob branch is matched against every ref again (the #1833 bypass)",
            "        elif BAD_BRANCH.search(str(branch)):",
            "        elif False:",
            "verify: a glob branch is refused, never matched against every ref",
        ),
        Mutation(
            "remote_head takes line 1 of a broader answer instead of the exact ref",
            "        if len(parts) == 2 and parts[1] == ref:",
            "        if len(parts) == 2:",
            "remote_head: exact ref only",
        ),
        Mutation(
            "a head origin does not hold is accepted",
            "            elif on_origin != head:",
            "            elif False:",
            "verify: a head origin does not hold is a MISMATCH",
        ),
        Mutation(
            "a reply naming no branch passes",
            "        elif not branch:",
            "        elif False:",
            "verify: no branch named is a MISMATCH",
        ),
        Mutation(
            "a reply that says not ready passes when its head checks out",
            "        if r.get(\"ready\") is not True:",
            "        if False:",
            "verify: not ready is a MISMATCH even when the head checks out",
        ),
        Mutation(
            "a session still waiting on a heavy run counts as done, so `verify && compact` compacts early",
            "    return 0 if all(r[\"state\"] in (\"READY\", \"SELF\") for r in rows) else 1",
            "    return 0 if all(r[\"state\"] in (\"READY\", \"SKIP\", \"SELF\") for r in rows) else 1",
            "exit: a session still waiting on a heavy run (SKIP) is not done",
        ),
        Mutation(
            "a hung read escapes as a traceback instead of a failed read",
            "    except subprocess.TimeoutExpired:\n        raise ReadFailed(argv, 124, \"timed out after 60 s\")",
            "    except subprocess.TimeoutExpired:\n        raise",
            "timeout: ",
        ),
    ),
)
