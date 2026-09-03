"""Mutation guard: architecture_graph. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #836. The second-largest script in the repo had no test. `--check` rebuilt with the default cap
# whatever the committed graph was built with, and the truncation note sits inside the digest.
GUARD = Guard(
    name="architecture_graph",
    subject="plugins/rails-flow/scripts/architecture_graph.py",
    selftest="plugins/rails-flow/scripts/architecture_graph.py",
    mutations=(
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
    ),
)
