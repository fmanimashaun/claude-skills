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
        Mutation(
            "the GET-only carve-out goes, so a DELETE route is claimed as crawl-visited",
            "                  if c.covered and not c.route.destructive}",
            "                  if c.covered}",
            "a destructive route was claimed as crawled",
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
    ),
)
