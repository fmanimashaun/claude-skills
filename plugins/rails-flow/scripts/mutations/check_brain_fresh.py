"""Mutation guard: check_brain_fresh (#2297). Declared here, run by scripts/mutation_check.py.

The check refuses an arm or promotion while STATUS.md predates the last release, and refuses when it cannot
tell. Each mutation turns one of those refusals into a pass and names the fixture that must notice.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_brain_fresh",
    subject="scripts/check_brain_fresh.py",
    selftest="scripts/check_brain_fresh.py",
    selftest_args=("--selftest",),
    needs=("scripts/fixture_git.py",),
    mutations=(
        Mutation(
            "a STATUS older than the last promotion passes",
            "    if sha_ts < tag_ts:",
            "    if False:",
            "a STATUS older than the last promotion is refused, and says so",
        ),
        Mutation(
            "a sha this clone does not have passes as fresh",
            '    if sha_at is None:\n        return 1,',
            '    if False:\n        return 1,',
            "a sha this clone does not have is refused, not passed",
        ),
        Mutation(
            "a STATUS with no readable _Updated line passes",
            "    if not m:\n        return 1,",
            "    if False:\n        return 1,",
            "a STATUS with no readable _Updated line is refused",
        ),
        Mutation(
            "a missing STATUS passes",
            "    if not status.is_file():\n        return 1,",
            "    if False:\n        return 1,",
            "a missing STATUS is refused",
        ),
        Mutation(
            "a shallow clone, whose tags are not all there, passes",
            '    if rc == 0 and shallow == "true":',
            "    if False:",
            "a shallow clone cannot tell and is refused, not passed",
        ),
        Mutation(
            "a project with a tag and no promotion yet is treated as having none",
            "    if not tags:\n        return 0,",
            "    if True:\n        return 0,",
            "a STATUS older than the last promotion is refused, and says so",
        ),
        Mutation(
            "--when arm judges on every branch, so it is no longer a release check",
            "    if ARM_BRANCH.match(branch):\n        return True",
            "    if True:\n        return True",
            "--when arm on a branch that is not an arm is not applicable (exit 3), whatever STATUS says",
        ),
        Mutation(
            "an arm is never recognised, so --when arm never judges",
            "    if ARM_BRANCH.match(branch):\n        return True",
            "    if False:\n        return True",
            "--when arm on an arm branch judges, and refuses a stale STATUS",
        ),
        Mutation(
            "a release heading in the diff no longer marks an arm",
            "    return rc == 0 and any(RELEASE_HEADING.match(line) for line in diff.splitlines())",
            "    return False",
            "--when arm also fires on a diff that adds a `(release vX)` heading, whatever the branch is called",
        ),
        Mutation(
            "the instants are compared as ISO text, so a UTC offset decides the order",
            "    if sha_ts < tag_ts:",
            "    if sha_date < tag_date:",
            "a STATUS at 10:00+05:00 (05:00Z) is OLDER than a tag at 08:00Z, though its text sorts later",
        ),
        Mutation(
            "the instants are compared as ISO text, so a later STATUS in a western offset reads as stale",
            "    if sha_ts < tag_ts:",
            "    if sha_date < tag_date:",
            "a STATUS at 08:00Z is NEWER than a tag at 10:00+05:00 (05:00Z), though its text sorts earlier",
        ),
    ),
)
