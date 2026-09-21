"""Mutation guard: structure_ratchet. Run by scripts/mutation_check.py (#1072)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="structure_ratchet",
    subject="scripts/structure_ratchet.py",
    selftest="scripts/structure_ratchet.py",   # --selftest lives in the module
    needs=("scripts/check_layer_structure.py",),   # discover_layers is imported, not duplicated
    mutations=(
        Mutation(
            # The RISE arm: the whole point. Without it the floors file is decoration.
            "a root count above its floor stops being a finding",
            "        if now > floor:",
            "        if False:",
            "a file added at the root of a layer at its floor is a finding",
        ),
        Mutation(
            # The STALE arm. A floor left high after real grouping work silently permits the next
            # slice to undo it -- a ratchet that has stopped ratcheting and still reports green.
            "a floor left above the real count stops being a finding",
            "        elif now < floor:",
            "        elif False:",
            "a floor left above the real count fails as STALE",
        ),
        Mutation(
            # Day one must be GREEN. At-the-floor is the state every project is in the moment it
            # runs --set-floor; failing it turns adoption into a red build and the gate comes out.
            "a project sitting exactly at its floor is failed",
            "        if now > floor:",
            "        if now >= floor:",
            "...and the recorded baseline produces no findings",
        ),
        Mutation(
            # A layer with no floor is growth, not regression. Judging it against an implicit 0
            # fails every project the day it adds a directory -- the false positive that gets a
            # gate switched off.
            "a layer with no recorded floor is judged against an implicit zero",
            "        floor = floors.get(layer)",
            "        floor = floors.get(layer, 0)",
            "...but a layer with no floor is not a finding",
        ),
    ),
)
