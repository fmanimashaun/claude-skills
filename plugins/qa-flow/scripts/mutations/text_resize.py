"""Mutation guard: text_resize. Declared here, run by scripts/mutation_check.py (#1367)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The two dangerous directions are opposite, as for layout_fit: a rule that stops firing reports a
# clean page that cuts a paragraph in half at 200%, and an unverified case that turns clean reports a
# pass over text that never grew. Both are mutated, plus the collector's verified values.
GUARD = Guard(
    name="text_resize",
    subject="scripts/text_resize.py",
    selftest="scripts/text_resize.py",
    # Imports layout_fit (which imports qa_config) and cross-checks the collector.
    needs=(
        "scripts/layout_fit.py",
        "scripts/qa_config.py",
        "scripts/crawl_collector.js",
    ),
    mutations=(
        Mutation(
            "a clip at 200% stops being reported",
            '                    kind = "clipped" if overflow in CLIPS else "overlap"',
            '                    kind = "clipped" if overflow in CLIPS else "overlap"\n'
            '                    if kind == "clipped":\n                        continue',
            "a fixed-height box that clips at 200% text is resize-clipped",
        ),
        Mutation(
            "only the horizontal axis is judged, so a box that clips vertically passes",
            '    for axis, client, scroll in (("x", "clientWidth", "scrollWidth"), ("y", "clientHeight", "scrollHeight")):',
            '    for axis, client, scroll in (("x", "clientWidth", "scrollWidth"),):',
            "a fixed-height box that clips at 200% text is resize-clipped",
        ),
        Mutation(
            "the as-served comparison is dropped, so layout_fit's defects are reported twice",
            "                    if (ref, axis) in served:",
            "                    if False:",
            "a clip already present as served is not reported again",
        ),
        Mutation(
            "pre-existing loss is matched by ref alone, so a clip on the other axis excuses a new one",
            "                    served.add((str(row.get(\"ref\")), axis))",
            "                    served.update((str(row.get(\"ref\")), a) for a in (\"x\", \"y\"))",
            "a clip on the other axis as served does not excuse a new one",
        ),
        Mutation(
            "text that never grew is judged anyway, so a px-sized page reads as clean",
            "                if grew / texts < MIN_GREW_SHARE:",
            "                if False:",
            "text that did not grow leaves the 200% check unverified",
        ),
        Mutation(
            "a probe that threw is skipped silently instead of reported",
            '                out.unverified.append(f"{route} ({CRITERION[name]}): the probe did not run")\n',
            "",
            "a probe that threw is unverified",
        ),
        # #1395 review: the cap applies to every mode, so each mode's truncation must be read.
        Mutation(
            "a truncated scaled list is trusted",
            '            if mode.get("truncated"):\n                out.unverified.append(f"{route} ({CRITERION[name]}): the list',
            '            if mode.get("truncated") and name != "scaled":\n                out.unverified.append(f"{route} ({CRITERION[name]}): the list',
            "a truncated scaled list is unverified, never a pass",
        ),
        Mutation(
            "a truncated spacing list is trusted",
            '            if mode.get("truncated"):\n                out.unverified.append(f"{route} ({CRITERION[name]}): the list',
            '            if mode.get("truncated") and name != "spacing":\n                out.unverified.append(f"{route} ({CRITERION[name]}): the list',
            "a truncated spacing list is unverified, never a pass",
        ),
        Mutation(
            "a truncated scaled list stops the loop, so spacing is never judged",
            "                                      \"collector's cap, so a clip may have been cut from it\")\n                continue",
            "                                      \"collector's cap, so a clip may have been cut from it\")\n                break",
            "CONTROL: a truncated scaled list leaves the spacing check judged",
        ),
        Mutation(
            "a mode with no truncated flag is read as complete",
            '    if not isinstance(mode.get("truncated"), bool):',
            "    if False:",
            "a mode with no truncated flag is unusable, not complete",
        ),
        Mutation(
            "the route comparison stops normalising, so a query string reads as a redirect",
            "        if isinstance(landed, str) and landed.strip() and route_path(landed) != route_path(route):",
            "        if isinstance(landed, str) and landed.strip() and landed != route:",
            "a route with a query string is the page it lands on",
        ),
        Mutation(
            "the untested share of px-sized text is no longer reported",
            "                if grew < texts:",
            "                if False:",
            "text that partly did not grow is reported with its untested share",
        ),
        Mutation(
            "a truncated as-served list is trusted",
            '        if base.get("truncated"):',
            "        if False:",
            "a truncated as-served list is unverified",
        ),
        Mutation(
            "scrollable content is treated as loss",
            "                    if overflow in SCROLLS:",
            "                    if False:",
            "content reachable by scrolling is not loss",
        ),
        Mutation(
            "an unverified run exits 0",
            "    return 1 if (result.findings or result.unverified) else 0",
            "    return 1 if result.findings else 0",
            "an unverified run exits 1",
        ),
    ),
)
