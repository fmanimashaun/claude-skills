"""Mutation guard: check_arm_window. Declared here, run by scripts/mutation_check.py (#1170).

The two mutations that matter are the ones that make the check VACUOUS rather than wrong: keying on
the absence of `### Unreleased` alone (fires on every merge, so it gets switched off), and reading
the tag from the CHANGELOG instead of git (an already-promoted dev reads armed forever). Both leave a
check that runs, prints, and protects nothing.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_arm_window",
    subject="scripts/check_arm_window.py",
    selftest="scripts/check_arm_window.py",
    mutations=(
        Mutation(
            "the re-opened heading stops being a finding, so the window is unguarded",
            "    if not reopened:\n        return []",
            "    if True:\n        return []",
            "a merge that re-opens Unreleased on an ARMED dev is refused",
        ),
        # THE FIRES-CONSTANTLY MUTATION. Absence of `### Unreleased` alone is dev's ordinary state
        # right after a promotion, so this version reports on every merge and gets disabled.
        Mutation(
            "armed keys on the absence of Unreleased alone, ignoring the release block",
            "    pending = [v for v in RELEASE_BLOCK.findall(changelog) if v not in tags]\n"
            "    return sorted(pending)[-1] if pending else None",
            '    return "vX.Y.Z"',
            "zero release blocks is not armed",
        ),
        # THE NEVER-CLOSES MUTATION. Trusting the CHANGELOG's own text for tag existence means a
        # promoted dev stays armed forever and every later merge is refused.
        Mutation(
            "tag existence is taken from the CHANGELOG instead of git, so the window never closes",
            "    pending = [v for v in RELEASE_BLOCK.findall(changelog) if v not in tags]",
            "    pending = list(RELEASE_BLOCK.findall(changelog))",
            "an already-PROMOTED dev is not armed",
        ),
        Mutation(
            "an Unreleased heading no longer disqualifies arming, so a normal dev reads as armed",
            "    if UNRELEASED.search(changelog):\n        return None",
            "    if False:\n        return None",
            "an Unreleased heading anywhere means not armed",
        ),
        # The `Closes` half.
        Mutation(
            "a promotion missing a Closes for a shipped issue stops being refused",
            "    missing = sorted(shipped - set(CLOSES.findall(body)), key=int)",
            "    missing = []",
            "a promotion missing a Closes for a shipped issue is refused",
        ),
        # ITS CONTROL. Without this, the mutation above is satisfied by a check that refuses every
        # body -- including a correct one.
        Mutation(
            "every promotion body is refused, including a complete one",
            "    return [] if not missing else [",
            "    return [f'refused'] if True else [",
            "...and a complete promotion body passes",
        ),
        # The heading pattern. Anchoring `\)\s*$` matches NO real heading, because they carry a date
        # after the paren -- the check would then report every armed dev as unarmed, silently.
        Mutation(
            "the release-block pattern is anchored so no real heading matches",
            'RELEASE_BLOCK = re.compile(r"^### .*\\(release (v\\d+\\.\\d+\\.\\d+)\\)", re.M)',
            'RELEASE_BLOCK = re.compile(r"^### .*\\(release (v\\d+\\.\\d+\\.\\d+)\\)\\s*$", re.M)',
            "armed is detected when both halves hold",
        ),
    ),
)
