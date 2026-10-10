"""Mutation guard: architecture_graph. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #836. The second-largest script in the repo had no test. `--check` rebuilt with the default cap
# whatever the committed graph was built with, and the truncation note sits inside the digest.
GUARD = Guard(
    name="architecture_graph",
    subject="scripts/architecture_graph.py",
    selftest="scripts/architecture_graph.py",
    needs=("scripts/fixture_git.py",),   # #1588
    deps=("scripts/generated_docs.py",),   # #1230: imported for the opt-in branch policy
    mutations=(
        # The quoted-path class narrowed again, so hyphens, `:segments` and dots cut the path short.
        Mutation(
            "a quoted route path is cut at the first hyphen again",
            '            first = re.match(r"^[\'\\"]([^\'\\"]+)[\'\\"]", rest) or re.match(r"^:([a-z0-9_]+)", rest)',
            '            first = re.match(r"^[:\'\\"]([a-z0-9_/]+)[\'\\"]?", rest)',
            "a hyphenated literal path is kept whole",
        ),
        # #1292: loc back in the digest, so a line-count edit is drift again.
        Mutation(
            "loc is hashed again, so a component growing by four lines turns dev red",
            '    nodes = [{k: v for k, v in n.items() if k not in NON_STRUCTURAL_NODE_FIELDS} for n in core["nodes"]]',
            '    nodes = core["nodes"]',
            "a model that only grew in lines is not drift (--check exits 0)",
        ),
        # #850. The page drew nothing; these keep it drawing the right thing.
        Mutation(
            "the diagram ignores layers, so every node lands in one column",
            "        col = LAYER_ORDER.index(layer)",
            "        col = 0",
            "columns follow LAYER_ORDER",
        ),
        Mutation(
            "edges are no longer drawn",
            '    for e in graph["edges"]:  # every edge, drawn once',
            "    for e in []:  # every edge, drawn once",
            "edges whose both endpoints are placed are drawn",
        ),
        Mutation(
            "an edge to a node outside the graph crashes the render",
            "        if not a or not b:\n            continue",
            "        if False:\n            continue",
            "render_svg survives an edge to a node outside the graph",
        ),
        Mutation(
            "node labels stop being escaped, so an id with `<` breaks the SVG",
            '{html.escape(_label(node["id"]))}</text></g>',
            '{_label(node["id"])}</text></g>',
            "the SVG parses as XML",
        ),
        Mutation(
            "the page stops embedding the diagram",
            '        .replace("__SVG__", render_svg(graph))',
            '        .replace("__SVG__", "")',
            "the page embeds the diagram",
        ),

        Mutation(
            "the committed cap is ignored, so --check rebuilds at the default again",
            '    if committed is not None and isinstance(committed.get("max_flows"), int):',
            "    if False:",
            "--check rebuilds with the COMMITTED cap",
        ),
        Mutation(
            "the cap is no longer recorded in the graph",
            '        "max_flows": max_flows,',
            '        "max_flows": None,',
            "the graph RECORDS the cap",
        ),
        Mutation(
            "an explicit --max-flows stops winning",
            "    if requested is not None:\n        return requested",
            "    if False:\n        return requested",
            "an explicit --max-flows wins",
        ),
    Mutation(
        # #1158: the title came from the directory basename, and the lane skill puts every session
        # in a worktree named for its task. Measured downstream: 37 of 113 commits to the generated
        # page carried a wrong title, in 28 distinct spellings, every one a worktree directory --
        # each produced by following the pre-push guard's own printed instruction.
        "the title comes from this checkout's directory again",
        "    common = git(\"rev-parse\", \"--git-common-dir\")",
        "    common = None",
        "a worktree resolves back to the primary checkout, not its own directory",
    ),
    Mutation(
        # The remote is preferred because it is identical from every checkout and survives the
        # directory being renamed. Losing it falls back to a path-derived name again.
        "the origin remote is no longer consulted",
        '    url = git("remote", "get-url", "origin")',
        "    url = None",
        "the origin remote's repository name wins",
    ),
        Mutation(
            # #1230: the policy is consulted but its verdict ignored -- drift fails on every branch again.
            "a stale graph fails a feature branch that the policy makes advisory",
            "        advisory = drift_is_advisory(root)\n        if advisory:\n",
            "        advisory = drift_is_advisory(root)\n        if False:\n",
            "with a policy: a stale graph is a NOTE and passes on a feature branch",
        ),
        Mutation(
            # #1230: the fires-everywhere direction -- drift passes on EVERY branch, dev included.
            "a stale graph passes even on an enforcing branch",
            "    return None if ok else why\n",
            "    return why\n",
            "...and still FAILS on an enforcing branch",
        ),
        # #1698: which schema files the graph's table nodes come from (the vendored-alone copy of the rule in build_project_wiki.py).
        Mutation(
            "only db/schema.rb is scanned, so a second database's tables are missing",
            '        for path in app_schema_files(self.root):',
            '        for path in [os.path.join(self.root, SCHEMA_RB)]:',
            "#1698 a second database's table is a node too, with the schema file it is in",
        ),
        Mutation(
            'the Solid trio is read as well',
            '        if os.path.basename(path) in FRAMEWORK_SCHEMAS and all(t.startswith("solid_") for t in tables):',
            '        if False:',
            "#1698 the Solid trio, holding only solid_* tables, is the framework's: no table node comes from it",
        ),
        Mutation(
            'a trio-named file is skipped by its name alone',
            '        if os.path.basename(path) in FRAMEWORK_SCHEMAS and all(t.startswith("solid_") for t in tables):',
            '        if os.path.basename(path) in FRAMEWORK_SCHEMAS:',
            "#1698 a cache_schema.rb holding a table of the PROJECT's own is the project's",
        ),
        Mutation(
            'a table in two schema files is drawn silently',
            '                if name in self.table_names:',
            '                if False:',
            '#1698 a table in two schema files is drawn once (the first), and a note says so',
        ),
    ),
)
