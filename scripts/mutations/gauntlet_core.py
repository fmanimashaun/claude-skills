"""Mutation guard: gauntlet_core. Declared here, run by scripts/mutation_check.py (#1563, B2 and B3 of the #1578 review)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="gauntlet_core",
    subject="scripts/gauntlet_core.py",
    selftest="scripts/gauntlet_core.py",   # --selftest lives in the module
    needs=(
        # The selftest runs the battery against the real hook, and reads the real agent files and the real registry.
        "plugins/rails-flow/hooks", "plugins/qa-flow/hooks", ".claude/agents", "scripts", "plugins",
    ),
    mutations=(
        Mutation(
            # B2 of the #1578 review: a guard is found by the script it declares, not by its name. Dropping the subject
            # entry makes every script look unguarded.
            "a guard is no longer found by its declared subject",
            "        by_path.setdefault(subject, name)\n",
            "        pass\n",
            "B2: a hook script found by its declared subject",
        ),
        Mutation(
            "a changed script with no guard is CLEAN",
            "    lines = [f\"{'BLOCKED' if missing else 'CLEAN'}  {len(missing)} finding(s), {len(run)} guard(s) to run\"]",
            "    lines = [f\"CLEAN  {len(missing)} finding(s), {len(run)} guard(s) to run\"]",
            "a changed script with no guard BLOCKS",
        ),
        Mutation(
            "an unguarded script exits 0",
            "    return (1 if missing else 0), lines",
            "    return 0, lines",
            "a changed script with no guard BLOCKS",
        ),
        Mutation(
            "a diff with nothing to attack reads as CLEAN",
            "        return 2, [\"NOTHING TO ATTACK",
            "        return 0, [\"NOTHING TO ATTACK",
            "nothing to attack is exit 2, never CLEAN",
        ),
        Mutation(
            "a guard file is itself a script that needs a guard",
            "NOT_A_SUBJECT = (\"*/mutations/*\", \"*/__pycache__/*\")",
            "NOT_A_SUBJECT = (\"*/__pycache__/*\",)",
            "a guard file is not itself a script that needs a guard",
        ),
        Mutation(
            "the battery never compares the hook's exit with what was wanted",
            "        if (got == 2) != must_refuse:",
            "        if False:",
            "a hook that checks raw text before dequoting BLOCKS",
        ),
        Mutation(
            # A hook that refuses everything must not pass: the legitimate rows are the positive control.
            "the battery checks only the refusals, so refuse-everything passes",
            "        if (got == 2) != must_refuse:",
            "        if must_refuse and got != 2:",
            "a hook that refuses everything BLOCKS on the legitimate rows",
        ),
        Mutation(
            "a hook that is not there is CLEAN",
            "        return 2, [f\"COULD NOT RUN  {hook} does not exist\"]",
            "        return 0, [f\"COULD NOT RUN  {hook} does not exist\"]",
            "a hook that is not there is exit 2, not CLEAN",
        ),
        Mutation(
            # The reverted-prompt check must be able to fail: it is the only thing tying an agent to its command.
            "an agent's instructions are never checked for their command",
            "    return AGENT_COMMANDS[agent] in text",
            "    return True",
            "instructions, reverted to the prose step, no longer do",
        ),
    ),
)
