"""Mutation guard: resume_lanes (#1564). Declared here, run by scripts/mutation_check.py.

Each mutation makes the lane lister hide an unfinished lane, show a finished one, misplace its branch or worktree, or write something.
The named fixture in `resume_lanes.py --selftest` must go red for each.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="resume_lanes",
    subject="scripts/resume_lanes.py",
    selftest="scripts/resume_lanes.py",   # --selftest lives in the module itself
    needs=("scripts/fixture_git.py", "scripts/check_handoff.py"),   # its git goes through fixture_git (#1588); it parses orders with check_handoff
    mutations=(
        Mutation(
            "a DONE order is listed as unfinished",
            '    if status == "done":\n        return None',
            "    if False:\n        return None",
            "a DONE order is not listed",
        ),
        Mutation(
            "an order with no Progress section reads as done, so a lane nothing recorded is never resumed",
            'else "no-progress-recorded"',
            'else "done"',
            "an order with no Progress section is listed",
        ),
        Mutation(
            "a remote-only branch is not found, so it reads as missing",
            'f"refs/remotes/origin/{branch}"',
            'f"refs/remotes/origin/NEVER-{branch}"',
            "a remote-only branch says how to recover it",
        ),
        Mutation(
            "the worktree that has the branch is not named",
            'return "local", trees.get(branch, "no worktree has it checked out")',
            'return "local", "no worktree has it checked out"',
            "the worktree that has the branch is named",
        ),
        Mutation(
            "a file that does not parse is reported as done, so an unreadable order hides a lane",
            '"status": "unreadable"',
            '"status": "done"',
            "listed as unreadable",
        ),
        Mutation(
            "a Last green that is not a commit goes unreported",
            '        if not any(_git(root, "rev-parse", "--verify", "-q", f"{s}^{{commit}}")[0] == 0 for s in shas):',
            "        if False:",
            "a Last green that is not a commit",
        ),
        Mutation(
            "the pre-layout docs/handoff/ is not read",
            'HANDOFF_DIRS = ("docs/product/handoff", "docs/handoff")',
            'HANDOFF_DIRS = ("docs/product/handoff",)',
            "the pre-layout docs/handoff/ is read too",
        ),
        Mutation(
            "unfinished lanes exit 0, so a script waiting on the exit status sees a clean tree",
            '    print("\\n".join(brief(i) for i in items))\n    return 1',
            '    print("\\n".join(brief(i) for i in items))\n    return 0',
            "unfinished lanes exit 1",
        ),
    ),
)
