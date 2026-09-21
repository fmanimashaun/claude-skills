"""Mutation guard: check_layer_structure. Run by scripts/mutation_check.py (#1072)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_layer_structure",
    subject="scripts/check_layer_structure.py",
    selftest="scripts/check_layer_structure.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # The one thing this gate fails on: the file path and the routing table disagreeing
            # about the same class. Everything else it merely reports.
            "a controller under an undeclared module stops being a finding",
            "        if directory in declared:",
            "        if True:",
            "a controller under an undeclared module is reported",
        ),
        Mutation(
            # THE MUST-PASS HALF, and the reason this gate is usable. A flat controllers root is an
            # ABSENCE, not a violation -- nobody told the project what shape to aim for. Failing it
            # would fail nearly every Rails app on day one, and the gate would be removed.
            "a flat controller becomes a finding",
            "        if len(rel.parts) < 2:",
            "        if False:",
            "a flat controller is not a finding",
        ),
        Mutation(
            # `namespace` sets the module too. Reading only `scope module:` would report every
            # namespaced controller in the app as contradicting its route.
            "only `scope module:` counts, so `namespace` no longer declares a module",
            "    return set(SCOPE_MODULE.findall(body)) | set(NAMESPACE.findall(body))",
            "    return set(SCOPE_MODULE.findall(body))",
            "`namespace` also declares a module",
        ),
        Mutation(
            # With nothing declared anywhere there is nothing to contradict; reporting then would
            # flag every grouped controller in a project that has not adopted the doctrine yet.
            "a project declaring no module at all is judged against an empty set",
            "    if not declared:",
            "    if False:",
            "with no module declared anywhere, nothing is a contradiction",
        ),
    ),
)
