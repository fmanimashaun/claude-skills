"""Mutation guard: launch_readiness. Declared here, run by scripts/mutation_check.py (#1289).

The mutations that matter make the profile VACUOUS or point it at the wrong apps: an undeclared
project read as clean, an old crawl read as clean, the marketing set demanded of an app that must not
be found, or a non-indexable app left open to search engines.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="launch_readiness",
    subject="scripts/launch_readiness.py",
    selftest="scripts/launch_readiness.py",
    deps=("scripts/crawl_report.py", "scripts/qa_config.py"),   # the one crawl reader; the one config reader
    mutations=(
        # #1297: the declared health endpoint judged as a page again.
        Mutation(
            "the declared health path is judged as a page",
            '    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200 and p.get("route") != health',
            '    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200',
            "a declared health path is not judged as a page",
        ),
        Mutation(
            "an undeclared project is reported clean when its baseline is",
            "    if indexable is None:\n        return 3,",
            "    if indexable is None and False:\n        return 3,",
            "undeclared: exit 3, never 0, even on a clean baseline",
        ),
        Mutation(
            "a crawl without the head/site probes reads as a clean launch",
            '    if any("head" not in p for p in html) or not isinstance(data.get("site"), dict):',
            "    if False:",
            "a crawl that predates the probes is UNUSABLE (exit 2), not clean",
        ),
        Mutation(
            "the marketing set is demanded of every app, including one that must not be found",
            "    rules = BASELINE + (MARKETING if indexable else ())",
            "    rules = BASELINE + MARKETING",
            "CONTROL: a non-indexable app needs no description or og:image, and is clean",
        ),
        Mutation(
            "the marketing set is never demanded, even of an indexable app",
            "    rules = BASELINE + (MARKETING if indexable else ())",
            "    rules = BASELINE",
            "indexable, a page with no og:image: a finding naming the route",
        ),
        Mutation(
            "a non-indexable app with an open robots.txt passes",
            "    elif indexable is False and not disallows_all(site.get(\"robotsBody\") or \"\"):",
            "    elif False:",
            "non-indexable, robots allows indexing: a finding",
        ),
        Mutation(
            "a Disallow under any user agent counts as closing the site",
            '    return "/" in groups.get("*", [])',
            '    return any("/" in v for v in groups.values())',
            "robots: `Disallow: /` under another agent does not",
        ),
        Mutation(
            "a missing robots.txt is no longer a finding",
            "    if robots != 200:",
            "    if False:",
            "robots.txt 404 is a finding even for a non-indexable app",
        ),
        Mutation(
            "error pages are judged for head tags, so every 500 is a false launch finding",
            '    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200',
            '    html = [p for p in pages if not p.get("skipped")',
            "a 500 or skipped page is not judged for head tags",
        ),
    ),
)
