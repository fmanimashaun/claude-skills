"""Mutation guard: check_published_blocks. Run by scripts/mutation_check.py (#1096)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_published_blocks",
    subject="scripts/check_published_blocks.py",
    selftest="scripts/check_published_blocks.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # The destructive direction. A published note a reader relied on vanishing is the
            # defect this was written for -- it happened to a real v1.133.0 bullet.
            "a bullet lost from a published block stops being a finding",
            "        if [b for b in then if b not in now]:",
            "        if False:",
            "a LOST bullet is reported, and named as destroyed history",
        ),
        Mutation(
            # The misattribution direction: unshipped work filed under a shipped release.
            "a bullet added after the tag stops being a finding",
            "        if [b for b in now if b not in then]:",
            "        if False:",
            "a GAINED bullet is reported",
        ),
        Mutation(
            # THE RATCHET MUST NOT EXCUSE DESTRUCTION. Baselining a loss would let the one
            # irreversible case be waved through by a file anyone can edit.
            "the baseline starts excusing losses, not just additions",
            "    for tag in losses:",
            "    for tag in [t for t in losses if t not in baseline]:",
            "a LOSS is reported even for a baselined tag",
        ),
        Mutation(
            # USABILITY, and the reason this check survives. Keying on the whole first line read
            # four path corrections -- `docs/coverage.html` to `docs/evidence/coverage.html` and
            # friends -- as destroyed notes across v1.44.0, v1.92.0 and v1.112.0. A gate red on
            # correct maintenance is one somebody removes.
            "a path correction inside a note counts as a different note",
            '                title = re.sub(r"`[^`]*`", "", m.group(1))',
            "                title = m.group(1)",
            "a note whose cited path was corrected is the SAME note",
        ),
    ),
)
