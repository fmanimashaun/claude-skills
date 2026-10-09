"""Mutation guard: hook_where_stopped. Declared here, run by scripts/mutation_check.py (#1639, #1643 R2).

The facts file a killed session leaves behind is only worth reading if it is the right worktree's, says when HEAD moved
since, and never calls a tree clean that git could not read. Those are the mutations that matter.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_where_stopped",
    subject="plugins/rails-flow/hooks/scripts/lib/where_stopped.py",
    selftest="plugins/rails-flow/hooks/scripts/lib/where_stopped.py",
    needs=("plugins/rails-flow/scripts/fixture_git.py",),   # #1588
    mutations=(
        Mutation(
            "a HEAD that moved since the last Stop is not flagged, so the file is read as the current state",
            '    drift = bool(rec.get("head") and f["head"] and rec["head"] != f["head"])',
            '    drift = False',
            "a HEAD that moved after the last Stop is flagged as drift",
        ),
        Mutation(
            "the once-per-change rule is gone, so the same warning repeats after every reply",
            '    if f["dirty"] is not None and before.get("unpushed", "0") == str(f["unpushed"] or 0) \\',
            '    if False and f["dirty"] is not None and before.get("unpushed", "0") == str(f["unpushed"] or 0) \\',
            "the same counts on the next turn are not repeated",
        ),
        Mutation(
            "every worktree shares one key, so a second worktree overwrites the first one's file",
            '    return f"{slug}-{hashlib.sha1(toplevel.encode()).hexdigest()[:8]}"',
            '    return "worktree"',
            "a second worktree writes its own file",
        ),
        Mutation(
            "a git status with no answer reads as an empty tree: the false all-clear",
            '    dirty = None if status is None else [line[3:] for line in status.splitlines()]',
            '    dirty = [line[3:] for line in (status or "").splitlines()]',
            "a git status with no answer is 'unknown'",
        ),
        Mutation(
            "the overall deadline is ignored, so a hung git costs 5 s per call",
            '    left = min(GIT_TIMEOUT, _deadline[0] - time.monotonic())',
            '    left = GIT_TIMEOUT',
            "past the overall deadline git is not called at all",
        ),
    ),
)
