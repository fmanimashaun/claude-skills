"""Mutation guard: crawl_report. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="crawl_report",
    subject="scripts/crawl_report.py",
    selftest="scripts/crawl_report.py",
    # `plugins/qa-flow/scripts/crawl_collector.js`: its selftest asserts the collector ships beside the judge.
    needs=("scripts/crawl_collector.js",),
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
    Mutation(
        # #1130: Playwright's BUNDLED chromium and webkit render no PDF at all, so a judge
        # downstream of that navigation grades an empty document and reports a defect in a working
        # app -- a confident verdict over something that never happened.
        "a non-HTML response is graded as a page again",
        '        if not renders_as_a_page(content_type):',
        '        if False:',
        "a PDF route is classified, not graded",
    ),
    Mutation(
        # THE DIRECTION THAT MATTERS MORE, and the first cut of this fix got it wrong: treating an
        # UNRECORDED content type as "not a page" classifies away every route of every crawl
        # written before the collector emitted it -- zero findings for a 500 error page, the gate
        # switched off, shipping as a fix. The selftest passed until this fixture existed.
        "a crawl with no content type recorded stops being judged",
        "    return not kind or kind in PAGE_TYPES",
        "    return kind in PAGE_TYPES",
        "a crawl with no content type recorded is still judged",
    ),
    Mutation(
        # A `; charset=utf-8` parameter is on nearly every real HTML response.
        "the content type is matched with its parameters attached",
        '    kind = (content_type or "").split(";", 1)[0].strip().lower()',
        '    kind = (content_type or "").strip().lower()',
        "the type is matched without its parameters or case",
    ),
    ),
)
