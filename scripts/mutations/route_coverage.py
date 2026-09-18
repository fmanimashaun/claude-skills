"""Mutation guard: route_coverage. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="route_coverage",
    subject="plugins/qa-flow/scripts/route_coverage.py",
    selftest="plugins/qa-flow/scripts/route_coverage_selftest.py",
    # `qa_config` joins `needs` with #792: both loaders now delegate to the one reader,
    # so without it the staged tempdir fails at IMPORT and the harness reports the guard
    # INERT -- every mutation "caught" regardless. A guard's needs is everything its
    # subject imports, and that changed when the loader moved.
    needs=("plugins/qa-flow/scripts/qa_config.py",),
    deps=("plugins/qa-flow/scripts/validate_evidence.py",),
    mutations=(
        Mutation(
            # The whole reason the third state exists: folding a crawl visit into `covered`
            # would inflate the one number this tool keeps honest, on exactly the routes
            # nobody wrote a test for.
            "a crawl visit is folded into `covered`, inflating the coverage percentage",
            "    seen = visited_paths(evidence)",
            "    seen = {**visited_paths(evidence), **visit_only_paths(evidence)}",
            "a crawl visit changed the coverage arithmetic",
        ),
        # #1037. This carve-out USED to live at the crawl call site, and only there -- so the
        # `covered` axis, the one number anybody quotes, credited a GET visit to the non-GET route
        # sharing its path. Measured against Retask: 78 of 201 "covered" routes were non-GET,
        # reporting 76% coverage where the honest figure was 47%. The rule now lives in
        # `attribute`, so ONE mutation trips both axes -- the covered-axis fixture named in
        # `expects`, and the older crawl fixture ("a destructive route was claimed as crawled")
        # which fails alongside it.
        Mutation(
            "the verb stops deciding, so a GET visit credits the non-GET route sharing its path",
            "        if not route.destructive:\n"
            "            for path, sources in seen.items():\n"
            "                if rx.match(path):\n"
            "                    artifacts |= sources",
            "        for path, sources in seen.items():\n"
            "            if rx.match(path):\n"
            "                artifacts |= sources",
            "is NOT covered by that same visit",
        ),
        Mutation(
            "the third-state line is suppressed when zero, so nobody can tell it ran",
            '    print(f"  of those, {len(crawled)} visited by a crawl but never asserted, "',
            '    print("") if False else print(f"  of those, {max(len(crawled), 1)} visited by a crawl but never asserted, "',
            "the third-state line must print even when the count is zero",
        ),
        Mutation(
            ":id matches greedily, over-crediting coverage",
            'out.append(r"[^/]+")',
            'out.append(r".+")',
            "swallow a deeper path",
        ),
        Mutation(
            "a findings rollup is credited as real visits",
            "columns = ROUTE_SOURCES.get(profile.name)",
            'columns = ROUTE_SOURCES.get(profile.name) or ("Example Routes",)',
            "contributes no coverage",
        ),
        # Classifying a new pass and actually READING it are two claims. The
        # "every profile classified" check proves only the first.
        Mutation(
            "the keyboard walk stops earning route coverage (#114)",
            '    "keyboard": ("Route", "Requested URL", "Final URL"),',
            "",
            "keyboard walk was not credited",
        ),
        Mutation(
            "the forms pass stops earning route coverage (#115)",
            '    "forms": ("Route", "Requested URL", "Final URL"),',
            "",
            "forms pass was not credited",
        ),

        # ---- AXIS TWO: measured at a small viewport (#953) ---------------------------------
        # The axis exists because a suite reported 49/49 routes covered while every table was
        # 71-83% hidden at a phone width. Its failure modes are all "a desktop measurement, or no
        # measurement, quietly counts as a small one".
        Mutation(
            "a desktop measurement counts as a small one, so the axis reads 100% on day one",
            "                if width is None or width > max_width:\n                    continue",
            "                if False:\n                    continue",
            "a 1280px measurement must not count as small",
        ),
        Mutation(
            "a probe that threw counts as a measurement — SKIP-is-not-a-PASS on axis two",
            '                if entry.get("elements") is None:\n                    continue',
            "                if False:\n                    continue",
            "a null probe must not count as measured",
        ),
        Mutation(
            # Measured downstream: the interaction sweep clicked sign-out and five admin routes
            # were recorded under the routes asked for while showing the landing page.
            "a route measured somewhere else counts, so a signed-out crawl reads as covered",
            '                if isinstance(landed, str) and landed.strip() and normalise(landed) != candidate:\n                    continue',
            "                if False:\n                    continue",
            "a route that landed elsewhere must not count as measured",
        ),
        Mutation(
            "any layout.json grants coverage, schema or not",
            '            if not isinstance(doc, dict) or doc.get("schema") != SMALL_VIEWPORT_SCHEMA:',
            "            if not isinstance(doc, dict):",
            "a foreign schema must not grant responsive coverage",
        ),
        Mutation(
            # Placed where it would actually matter — BEFORE attribution. The first draft mutated
            # a line after `covered` was already computed, so it changed no number and survived.
            "the two axes are averaged: small evidence starts moving `covered`",
            "    seen = visited_paths(evidence)",
            "    seen = visited_paths(evidence)\n"
            "    seen.update(small_viewport_paths(evidence, _small_max(config)))",
            "axis one moved when small evidence arrived",
        ),
        Mutation(
            "non-GET routes come back into the denominator, making the axis unreachable",
            "        [r for r in kept if not r.destructive], responsive_exclusions)",
            "        kept, responsive_exclusions)",
            "a non-GET route must not be counted as unmeasured",
        ),
        Mutation(
            # #1029. The plugin hardcoded `--fail-on-untested` for every adopter, so a project with
            # a backlog got a permanently red gate it could not opt out of — and the red step then
            # aborted the job before the project's own ratchet ran.
            "the project's `coverage.fail_on` is ignored and the axes are armed from the CLI alone",
            "    untested, unmeasured_axis = fail_axes(args, config)",
            "    untested, unmeasured_axis = args.fail_on_untested, args.fail_on_unmeasured",
            "coverage.fail_on: untested in the project config must exit 1",
        ),
        Mutation(
            "an unknown `fail_on` value is accepted, silently disarming the gate",
            '        raise SystemExit(f"coverage.fail_on is {raw!r}, not one of "',
            '        return FAIL_ON["none"]  # noqa  (mutant: silently disarm)\n        raise SystemExit(f"coverage.fail_on is {raw!r}, not one of "',
            "silently disarmed the gate",
        ),
        Mutation(
            "`--fail-on-unmeasured` stops gating, so the axis can never hold a line",
            "    failed = (untested and gaps) or (unmeasured_axis and unmeasured)",
            "    failed = untested and gaps",
            "--fail-on-unmeasured must fail when a route was never measured small",
        ),
        # ---- the denominator itself (#953) -------------------------------------------------
        # 64 of 143 rows on a real app, dropped in silence, and route coverage reported 100% over
        # what was left. Both halves are mutated: the parse, and the refusal to be quiet about a
        # row it cannot parse.
        Mutation(
            "the defaults hash breaks parsing again, dropping 45% of a real route table",
            '    r"(?:\\s+\\{.*\\})?\\s*$"',
            '    r"\\s*$"',
            "a row with a defaults hash is parsed",
        ),
        Mutation(
            "an unparseable row stops being reported, so the next format change is silent too",
            "    return [line.rstrip() for line in text.splitlines()\n"
            "            if _VERB_BEARING.search(line) and not _RAILS_ROW.match(line)]",
            "    return []",
            "an unparseable verb row must be reported",
        ),
        Mutation(
            "a partial enumeration is written and exits 0, producing a confident wrong percentage",
            "        return 2\n    return 0",
            "        pass\n    return 0",
            "enumerate refuses a partial parse",
        ),

        Mutation(
            "the responsive line goes quiet when there is no evidence, reading as clean",
            "        print(f\"  no {SMALL_VIEWPORT_ARTIFACT} evidence found — run \"",
            "        print(f\"  \" + \"\" or f\"  no {SMALL_VIEWPORT_ARTIFACT} evidence \"",
            "no small evidence at all must say so",
        ),
    ),
)
