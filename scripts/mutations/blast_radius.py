"""Mutation guard: blast_radius. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="blast_radius",
    subject="plugins/qa-flow/scripts/blast_radius.py",
    selftest="plugins/qa-flow/scripts/blast_radius_selftest.py",
    # `qa_config` joins `needs` with #792: both loaders now delegate to the one reader,
    # so without it the staged tempdir fails at IMPORT and the harness reports the guard
    # INERT -- every mutation "caught" regardless. A guard's needs is everything its
    # subject imports, and that changed when the loader moved.
    needs=("plugins/qa-flow/scripts/qa_config.py",),
    mutations=(
        # -- the reverse walk itself -------------------------------------------------------
        Mutation(
            "the walk follows OUTGOING edges, reporting dependencies as dependents",
            '        target = edge.get("to")',
            '        target = edge.get("from")',
            "a dependent is included by an incoming references edge",
        ),
        Mutation(
            "the depth cap stops applying, so the radius silently becomes the whole app",
            "    for level in range(1, max(depth, 0) + 1):",
            "    for level in range(1, 99):",
            "the depth cutoff excludes",
        ),
        # Narrowing WITHOUT saying so is the failure this tool exists to prevent, so the
        # cutoff's report is a separate rule from the cutoff itself.
        Mutation(
            "the depth cutoff stops reporting what it dropped",
            "    for node in frontier:\n        for edge in incoming.get(node, []):",
            "    for node in []:\n        for edge in incoming.get(node, []):",
            "the depth cutoff is reported, not silent",
        ),
        Mutation(
            "an enrichment edge stops naming the tool that produced it",
            '                    + (f"  [via {tool}]" if tool else ""),',
            '                    + "",',
            "an enriched edge names the tool that produced it",
        ),
        Mutation(
            "--no-enrichment stops excluding machine-local edges",
            "    if use_enrichment and isinstance(block, dict):",
            "    if isinstance(block, dict):",
            "--no-enrichment reproduces a bare-runner walk",
        ),
        # -- the five non-negotiable risk axes ----------------------------------------------
        Mutation(
            "the migration axis stops firing",
            '    "migration": ("db/migrate/", "db/schema.rb", "db/structure.sql"),',
            "",
            "fires the migration axis",
        ),
        Mutation(
            "the shared-concern axis stops firing",
            '    "shared-concern": ("/concerns/", "app/views/layouts/", '
            '"app/helpers/application_helper.rb"),',
            "",
            "fires the shared-concern axis",
        ),
        Mutation(
            "the money name hints stop firing",
            '    "money": ("payment", "invoice", "billing", "charge", "subscription", '
            '"price", "pricing",\n              "order", "ledger", "refund", "wallet", '
            '"transaction", "checkout", "coupon",\n              "discount", "payout", '
            '"tax"),',
            "",
            "fires the money axis",
        ),
        # The whole point of "non-negotiable": a project's config may ADD to an axis and may
        # never empty one. Declaring `migration: []` must not switch the structural rule off.
        Mutation(
            "config becomes able to switch a structural axis off",
            "        for axis, markers in STRUCTURAL_RISK.items():",
            "        for axis, markers in {k: v for k, v in STRUCTURAL_RISK.items() "
            "if declared.get(k) != []}.items():",
            "config cannot switch a non-negotiable axis off",
        ),
        Mutation(
            "a declared high-risk path stops being printed as excluded",
            '            report.excluded.append(Exclusion(path, "declared in qa.config.yml '
            '`blast_radius.exclude`"))',
            "            pass",
            "a declared exclusion is printed with its reason",
        ),
        # -- the silence half: rules that are only useful if they stay quiet -----------------
        Mutation(
            "`authenticated` becomes an auth signal, so every controller change is wide",
            "TAG_RISK: dict[str, str] = {",
            'TAG_RISK: dict[str, str] = {\n    "authenticated": "auth",',
            "an authenticated controller is not on its own an auth hit",
        ),
        Mutation(
            "the risk classifier stops exempting test files, so every spec edit is wide",
            "    report.risk = classify_risk([p for p in considered "
            "if not p.startswith(TEST_ROOTS)],",
            "    report.risk = classify_risk(considered,",
            "a spec-only change is never wide",
        ),
        Mutation(
            "non-app files stop being excluded, so a docs edit reads as under-determined",
            "        if not (path.startswith(APP_ROOTS) or path in APP_FILES):",
            "        if False:",
            "a docs-only change is excluded with a reason, not unresolved",
        ),
        # -- accounting: an unexplained file must never read as "nothing is affected" --------
        Mutation(
            "an unaccounted-for app file stops forcing the wide selection",
            "        return bool(self.risk) or bool(self.unresolved)",
            "        return bool(self.risk)",
            "an unaccounted-for app file forces wide",
        ),
        Mutation(
            "a conventional spec path that does not exist is dropped instead of reported",
            '            present = (root / candidate).exists()\n'
            '            out[candidate] = TestTarget(candidate, f"{reason} ({why})", present)',
            '            present = (root / candidate).exists()\n'
            "            if present:\n"
            '                out[candidate] = TestTarget(candidate, f"{reason} ({why})", '
            "present)",
            "a missing spec is reported, not dropped",
        ),
        Mutation(
            "the test-framework narrowing stops reporting itself",
            "    if present_frameworks:\n"
            "        for framework in sorted(set(TEST_ROOTS) - present_frameworks):",
            "    if False:\n"
            "        for framework in sorted(set(TEST_ROOTS) - present_frameworks):",
            "and the drop is printed once, with its reason",
        ),
        Mutation(
            "the excluded section is hidden when it is empty",
            '    lines.append(f"excluded from the radius -> {len(report.excluded)}")',
            "    if report.excluded:\n"
            '        lines.append(f"excluded from the radius -> {len(report.excluded)}")',
            "the excluded section prints even when empty",
        ),
        # -- route selection reads the #119 table rather than asserting agreement -------------
        Mutation(
            "every route is claimed to be in the route table, so a disagreement is hidden",
            "                                              inclusion.unit in by_key)",
            "                                              True)",
            "a graph route absent from the route table is flagged",
        ),
        # -- exit codes: 2 is "could not run", never 0 ------------------------------------------
        Mutation(
            "an empty changed-file list becomes a clean run instead of UNUSABLE",
            '        raise Unusable("no changed files supplied -- pass --changed or '
            '--changed-from")',
            "        return []",
            "no changed files is UNUSABLE (2), not clean (0)",
        ),
        Mutation(
            "--require-graph falls back silently instead of failing",
            "    elif args.require_graph:",
            "    elif False:",
            "--require-graph with no graph is UNUSABLE (2), never a silent fallback",
        ),
    ),
)
