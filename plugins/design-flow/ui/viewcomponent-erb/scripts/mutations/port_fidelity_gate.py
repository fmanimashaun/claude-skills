"""Mutation guard: port_fidelity_gate. Declared here, run by scripts/mutation_check.py (#1873)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1873. The runner grades 3 as n/a, so "no manifest" must be 3 and a manifest without its port report must still fail.
    name="port_fidelity_gate",
    subject="ui/viewcomponent-erb/scripts/port_fidelity_gate.py",
    selftest="ui/viewcomponent-erb/scripts/port_fidelity_gate.py",   # --selftest lives in the module
    needs=(),                                    # the selftest's fixtures never reach canvas_manifest.py
    mutations=(
        Mutation(
            'no canvas manifest is a pass instead of n/a',
            '-- `canvas_manifest.py extract` writes one per canvas")\n        return 3',
            '-- `canvas_manifest.py extract` writes one per canvas")\n        return 0',
            'no canvas manifest is n/a (exit 3)',
        ),
        Mutation(
            'a manifest with no port report beside it is accounted for',
            '            bad += 1\n            continue',
            '            continue',
            'a manifest with no port report is a gap',
        ),
    ),
)
