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
            "    declared = set(SCOPE_MODULE.findall(body)) | set(NAMESPACE.findall(body))",
            "    declared = set(SCOPE_MODULE.findall(body))",
            "`namespace` also declares a module",
        ),
        Mutation(
            # The false positive that shipped: real routes name a module inline with
            # `to: "sessions/omniauth#create"`, and not reading it reported correctly-organised
            # controllers as drift -- in the half of this check that FAILS a build (#1124).
            "an explicit `to:` stops declaring its module",
            "    for target in EXPLICIT_TO.findall(body):",
            "    for target in []:",
            "an explicit `to:` declares its module",
        ),
        Mutation(
            # The opposite error, and the reason the slice is `[:-1]`: `to: "home#index"` must not
            # declare a module called `home`, or any flat route silences a directory of that name.
            "the controller segment is counted as a module too",
            '        segments = target.split("/")[:-1]',
            '        segments = target.split("/")',
            "...but the last segment is the controller, not a module",
        ),
        Mutation(
            # A fixed list is what hid `app/javascript/controllers` from the first version. The
            # fixture builds `app/queries`, a layer named nowhere in the script.
            "layers are enumerated again instead of discovered",
            "    for entry in sorted(app.iterdir()):",
            '    for entry in [app / "models", app / "controllers"]:',
            "a layer nobody enumerated is discovered, not skipped",
        ),
        Mutation(
            # Without the container rule, `app/javascript` becomes a layer and its `controllers/`
            # child reads as one of its NAMESPACE directories -- the inverse of the truth.
            "`app/javascript` is treated as a layer rather than a container",
            "        if entry.name in CONTAINERS:",
            "        if False:",
            "...and `javascript` is NOT a layer, so its child is not read as a namespace",
        ),
        Mutation(
            # Stimulus controllers are `.js`. Counting only Ruby made the largest flat layer in the
            # motivating app invisible even once it was discovered.
            "only Ruby and ERB are counted, so Stimulus disappears",
            'CODE_SUFFIXES = (".rb", ".erb", ".js")',
            'CODE_SUFFIXES = (".rb", ".erb")',
            "Stimulus is its own layer",
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
