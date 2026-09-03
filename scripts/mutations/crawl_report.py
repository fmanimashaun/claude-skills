"""Mutation guard: crawl_report. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="crawl_report",
    subject="plugins/qa-flow/scripts/crawl_report.py",
    selftest="plugins/qa-flow/scripts/crawl_report.py",
    # `plugins/qa-flow/scripts/crawl_collector.js`: its selftest asserts the collector ships beside the judge.
    needs=("plugins/qa-flow/scripts/crawl_collector.js",),
    mutations=(
        Mutation(
            # The dangerous direction for a de-duplicator: merging defects that are not the
            # same one. Grouping on the rule alone would hide every distinct error behind
            # whichever fired first.
            "grouping drops `detail`, so two different errors merge under one rule name",
            "        routes = out.setdefault((f.rule, f.detail), [])",
            "        routes = out.setdefault((f.rule, f.rule), [])",
            "same rule, different detail stays two groups",
        ),
        Mutation(
            "a route repeating within a group is counted twice, inflating the spread claim",
            "        if f.route not in routes:",
            "        if True:",
            "one route counted once per group",
        ),
        Mutation(
            "uncaught exceptions stop being reported, so an S1 category goes unobserved again",
            '    for error in page.get("pageErrors", []) or []:',
            "    for error in []:",
            "an uncaught exception is reported",
        ),
        Mutation(
            "the 200-but-error rule stops firing",
            '    for pattern in ERROR_PAGE_MARKERS:',
            '    for pattern in []:',
            "200 rendering 'Internal Server Error' fires",
        ),
        Mutation(
            "an unreachable route is judged instead of named",
            '            result.skipped.append(f"{page.get(\'route\', \'?\')}: {page.get(\'skipped\')}")',
            '            pass',
            "a skipped route is named",
        ),
        Mutation(
            "console warnings become findings, so the rule fires on every real app",
            'CONSOLE_FATAL = ("error",)',
            'CONSOLE_FATAL = ("error", "warning")',
            "a console WARNING stays silent",
        ),
    ),
)
