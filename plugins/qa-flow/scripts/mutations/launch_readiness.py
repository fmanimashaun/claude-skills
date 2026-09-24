"""Mutation guard: launch_readiness. Declared here, run by scripts/mutation_check.py (#1289).

The mutations that matter make the profile VACUOUS: treating "nobody decided" as "internal", or an
old crawl with no probe data as a clean launch.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="launch_readiness",
    subject="scripts/launch_readiness.py",
    selftest="scripts/launch_readiness.py",
    deps=("scripts/crawl_report.py",),   # the one crawl reader
    mutations=(
        Mutation(
            "an undeclared project is treated as internal, so nobody is ever asked",
            "        return 3, [\"UNDECLARED:",
            "        return 0, [\"UNDECLARED:",
            "undeclared: exit 3, never 0",
        ),
        Mutation(
            "a crawl without the head/site probes reads as a clean launch",
            '    if any("head" not in p for p in html) or not isinstance(data.get("site"), dict):',
            "    if False:",
            "a crawl that predates the probes is UNUSABLE (exit 2), not clean",
        ),
        Mutation(
            "og:image is no longer required",
            '    ("launch-og-image-missing", lambda h, p: bool(h.get("ogImage")),',
            '    ("launch-og-image-missing", lambda h, p: True,',
            "a page with no og:image is a finding naming the route",
        ),
        Mutation(
            "the site files are no longer probed",
            "        if status != 200:",
            "        if False:",
            "robots 404 and an unfetchable sitemap are both findings",
        ),
        Mutation(
            "error pages are judged for head tags, so every 500 is a false launch finding",
            '    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200',
            '    html = [p for p in pages if not p.get("skipped")',
            "a 500 or skipped page is not judged for head tags",
        ),
        Mutation(
            "a declared-internal project is judged anyway",
            "    if public is False:",
            "    if public is None and False:",
            "declared internal: not applicable, exit 0",
        ),
    ),
)
