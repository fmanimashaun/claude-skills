"""Mutation guard: route_coverage. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="route_coverage",
    subject="scripts/route_coverage.py",
    selftest="scripts/route_coverage_selftest.py",
    # `qa_config` joins `needs` with #792: both loaders now delegate to the one reader,
    # so without it the staged tempdir fails at IMPORT and the harness reports the guard
    # INERT -- every mutation "caught" regardless. A guard's needs is everything its
    # subject imports, and that changed when the loader moved.
    needs=("scripts/qa_config.py",),
    # `validate_evidence` imports `evidence_app_tie` (#1133), so staging one without the other
    # leaves this guard dead on ModuleNotFoundError. Third time an added import has orphaned a
    # neighbouring guard (#1113, #1114); see the import-completeness invariant in the selftest.
    deps=("scripts/validate_evidence.py",
          "scripts/evidence_app_tie.py"),
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
        # #1039. The verb channel is the ONLY way a non-GET route is ever credited, so it needs
        # a mutation on each thing that could go wrong: the verb half, the pattern half, the
        # channel itself, the status filter, and the swallow that made the whole class invisible.
        Mutation(
            # Path-only crediting re-entering through the new door. This is #1037 all over again,
            # which is why the fixture that catches it is a GET and a DELETE on ONE pattern.
            "the verb half of the match is dropped, so any verb credits any other on that route",
            "            if verb == route.verb.upper() and pattern == route.pattern:",
            "            if pattern == route.pattern:",
            "GET /users/:id is NOT covered by a DELETE row on the same pattern",
        ),
        Mutation(
            # Exactness is what makes the verb channel safe. A substring match credits a route the
            # artifact never named -- inference, which is the thing this channel exists to avoid.
            "the pattern match loosens to a substring, so a pattern naming no route still credits",
            "            if verb == route.verb.upper() and pattern == route.pattern:",
            "            if verb == route.verb.upper() and pattern in route.pattern:",
            "a pattern naming no route credits nothing",
        ),
        Mutation(
            "the verb channel is disconnected, so no non-GET route can ever be covered",
            "        for (verb, pattern), sources in verb_seen.items():",
            "        for (verb, pattern), sources in {}.items():",
            "DELETE /users/:id IS covered by a row that drove it",
        ),
        Mutation(
            "an Out of Scope action row counts as driven",
            '                if row["Status"].lower() in {ve.OUT_OF_SCOPE_STATUS}:\n'
            "                    continue  # never driven, and not claimed to be",
            "                if False:\n"
            "                    continue",
            "an Out of Scope row drives nothing and credits nothing",
        ),
        Mutation(
            # The swallow itself. With this restored, the day a contract moves every artifact
            # stops parsing and coverage falls to near zero with no error anywhere -- which reads
            # as a regression rather than as the parse failure it is.
            "an unreadable evidence artifact is swallowed again instead of reported",
            "            except ve.Unusable as exc:\n"
            "                problems.append((str(path), str(exc)))",
            "            except ve.Unusable:\n"
            "                pass",
            "a CSV matching no contract is reported",
        ),
        # #1047. The report has to separate THREE states, and a mutation for each, because a
        # refusal that cannot tell them apart is worse than the missing provenance it replaces.
        Mutation(
            # The defect: a number that cannot say which tree it measured. Five denominators were
            # quoted to each other in one afternoon and none of them was wrong.
            "a stale inventory never refuses, so a percentage over another tree's routes prints",
            "    if not head or same_commit(head, recorded):\n        return None",
            "    if True:\n        return None",
            "an inventory from another commit must refuse",
        ),
        Mutation(
            # THE OPPOSITE FAILURE, and the one a reviewer specifically warned about: a refusal
            # that fires spuriously is worse than the warning it replaces, because the first thing
            # anyone does with a gate that blocks them wrongly is find the flag that turns it off.
            "the staleness check refuses ALWAYS, including on the tree it was enumerated from",
            "    if not head or same_commit(head, recorded):\n        return None",
            "    if False:\n        return None",
            "an inventory from THIS commit must not refuse",
        ),
        Mutation(
            # The migration half. An inventory written before #1047 has no provenance block, which
            # is what EVERY already-written file looks like; refusing it would make the upgrade
            # indistinguishable from a broken tool -- the #1039 lesson applied rather than relearned.
            "a pre-#1047 inventory is treated as stale, breaking every already-written file",
            '    if not prov:\n        return None\n    recorded = prov.get("commit")',
            '    if not prov:\n        return "no provenance"\n    recorded = prov.get("commit")',
            "a pre-#1047 inventory must be readable, not refused",
        ),
        Mutation(
            # ...but it must still SAY it cannot attribute the number, or the percentage is exactly
            # as unattributable as before and the change accomplished nothing.
            "a missing provenance block reports as fine instead of UNKNOWN",
            '        return ["  route inventory provenance: UNKNOWN \u2014 enumerated before provenance was "',
            '        return ["  route inventory provenance: fine \u2014 "',
            "a missing block must report UNKNOWN",
        ),
        Mutation(
            # RAILS_ENV alone produced 263 vs 275 on ONE tree. Asserting the field NAMES was not
            # enough -- this mutation survived that -- so the selftest sets the variable and looks.
            "RAILS_ENV stops being read, so the field ships permanently empty",
            '        "rails_env": os.environ.get("RAILS_ENV"),',
            '        "rails_env": None,',
            "RAILS_ENV is not read from the environment",
        ),
        # The v1.133.0 regression: `==` compares two RENDERINGS of a sha, not two commits. It
        # refused a downstream gate on an inventory enumerated seconds earlier from the same tree.
        Mutation(
            "the sha comparison returns to `==`, so an abbreviated sha refuses its own HEAD",
            "    if not head or same_commit(head, recorded):",
            "    if not head or head == recorded:",
            "an ABBREVIATED recorded sha must not refuse its own full-length HEAD",
        ),
        Mutation(
            # The over-correction. A prefix match is still a MATCH and not a licence: without a
            # floor, a 3-character "prefix" identifies nothing and the check stops being one.
            "the 7-character floor is dropped, so any prefix counts as the same commit",
            "    return len(short) >= 7 and long_.startswith(short)",
            "    return long_.startswith(short)",
            "a prefix shorter than 7 chars must not count as a match",
        ),
        Mutation(
            "every pair of shas counts as the same commit, so staleness can never be detected",
            "    if not a or not b:\n        return False",
            "    if True:\n        return True",
            "two DIFFERENT shas must still refuse when abbreviated",
        ),
        # #1062, the shipped defect. `[:9]` is for a SHA and was applied to the fallback too, so a
        # tree with no git rendered `route inventory: not a git` -- a truncated-looking
        # value on the one line a reader consults to decide whether a percentage can be
        # attributed to a tree. Same class as the abbreviated-SHA defect in `same_commit`:
        # a RENDERING treated as the value.
        Mutation(
            'the no-git fallback is truncated like a SHA again',
            '    commit = str(recorded)[:9] if recorded else "not a git tree"',
            '    commit = str(recorded or "not a git tree")[:9]',
            'the no-git fallback must print in full',
        ),
        # The over-correction, and it needs its own mutation because the fixture above cannot see
        # it: stop truncating at all and a 40-character hex string lands in a one-line
        # stamp. The fallback printing in full is not the same claim as nothing being
        # abbreviated.
        Mutation(
            'nothing is abbreviated, so a full SHA lands in the one-line stamp',
            '    commit = str(recorded)[:9] if recorded else "not a git tree"',
            '    commit = str(recorded) if recorded else "not a git tree"',
            'a real SHA must still be abbreviated',
        ),
    Mutation(
        # #1129: the narrowing. Without it every commit invalidates the inventory and the gate is
        # permanently ERROR on any working branch -- measured downstream at 11 commits, 0 verdicts.
        "any commit invalidates the inventory again, not just one that moved a route",
        "    if moved is False:",
        "    if False:",
        "stale_inventory: a commit that touched no route source must NOT refuse",
    ),
    Mutation(
        # THE CONTROL SIDE. The narrowing must not become "never refuse": a commit that really did
        # move a route source still has to stop the report.
        "a commit that moved a route source stops refusing",
        "    if moved is _LOOKUP_HEAD:",
        "    return None\n    if moved is _LOOKUP_HEAD:",
        "stale_inventory: a commit that moved a route source must still refuse",
    ),
    Mutation(
        # CANNOT TELL IS NOT CAN. Treating an undecidable diff as "fine" rebuilds the defect the
        # refusal exists to prevent, and does it silently.
        "an undecidable diff is treated as no change",
        "    if changed is None:\n        return None",
        "    if changed is None:\n        return False",
        "route_sources_changed: an undiffable pair must be None, not a verdict",
    ),
    Mutation(
        # #1129: nothing told anyone how to clear it. The message named two shas and no command.
        "the refusal stops naming the command that clears it",
        '            f"    python3 route_coverage.py enumerate --rails qa/reports/routes.txt")',
        '            f"")',
        "stale_inventory: the refusal must name the command that clears it",
    ),
    Mutation(
        # A prefix match that swallows a neighbour would make every `config/routes*` file a route
        # source, quietly widening the refusal back toward "any commit".
        "any path merely beginning with a route source counts",
        'ROUTE_SOURCE_PATHS = ("config/routes.rb", "config/routes/")',
        'ROUTE_SOURCE_PATHS = ("config/routes",)',
        "names_a_route_source: config/routes_helper.rb does not define routes",
    ),
    Mutation(
        # #1212 restored: the declaration keeps the `bin/rails routes` spelling and credits nothing.
        "the declared Route is no longer normalised",
        "                pattern = normalise(pattern)\n",
        "",
        "actions: a Route copied from bin/rails routes, with (.:format), IS credited",
    ),
    Mutation(
        # #1212: an under-claim nobody sees. The list must not quietly go empty.
        "a declaration naming no route is no longer reported",
        "    return sorted(k for k in verb_seen if k not in known)\n",
        "    return []\n",
        "actions: a declared route naming no inventory route is listed",
    ),
    ),
)
