"""Mutation guard: check_blocked_catalogue. Run by scripts/mutation_check.py (#1563)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_blocked_catalogue",
    subject="scripts/check_blocked_catalogue.py",
    selftest="scripts/check_blocked_catalogue.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # THE RULE ITSELF. A fixture the catalogue points at that no longer contains its
            # literal is how a defence quietly disappears in a refactor. Dropping the read makes
            # every pointer pass whatever the file says.
            "a fixture that has lost its literal still resolves",
            '    if literal not in target.read_text(encoding="utf-8", errors="replace"):',
            "    if False:",
            "a missing literal is reported",
        ),
        Mutation(
            # A row can claim a fixture on dev while its PR is still open. Only `merged` rows may
            # stand in the fixture table, because an open PR's fixture is not on dev.
            "an open PR's row is accepted in the fixture table",
            '        if state != "merged":',
            "        if False:",
            "an open row in the fixture table is reported",
        ),
        Mutation(
            # A fix on an open PR with nobody named is a class that has no owner, which is how it
            # stops being worked.
            "an open row with no owner passes",
            "        if not owner:",
            "        if False:",
            "an open row with no owner is reported",
        ),
        Mutation(
            # An advisory row with no reason is a class that was dropped, not a class that was
            # judged.
            "an advisory row with no reason passes",
            "        if not reason:",
            "        if False:",
            "an advisory row with no reason is reported",
        ),
        Mutation(
            # The vacuous pass: a missing or empty catalogue must be 2 (nothing examined), never
            # 0. A check that reports clean on input it never read is worse than none.
            "a catalogue that was never read passes",
            "    if examined == 0:",
            "    if False:",
            "a missing catalogue must exit 2",
        ),
        Mutation(
            # B1 of the #1578 review: renaming one heading dropped 8 of 15 rows and the check still exited 0.
            "a renamed section heading shrinks the check silently",
            "    return [name for name, key in SECTIONS if not section(found, key)]",
            "    return []",
            "a renamed heading must name its section",
        ),
        Mutation(
            # The run must REFUSE on a missing section, not only report it from `examine`.
            "a missing section is found but the run still passes",
            "    if missing:\n        print(f\"blocked catalogue: section(s)",
            "    if False:\n        print(f\"blocked catalogue: section(s)",
            "a catalogue with a section missing must exit 2",
        ),
    ),
)
