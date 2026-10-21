"""Mutation guard: interface_audit. Declared here, run by scripts/mutation_check.py (#2221).

The judge decides A1, A2 and A4 from what the collector measured. Each mutation switches one
decision off, and a clean page must stay clean, so a mutant that always reports is caught too.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="interface_audit",
    subject="scripts/interface_audit.py",
    selftest="scripts/interface_audit.py",
    selftest_args=("--selftest",),
    needs=("scripts/audit_findings.py", "reference/architecture-rules.json"),
    mutations=(
        Mutation(
            "a second visible main stops being a finding",
            "    if mains > 1:",
            "    if mains > 99:",
            "two visible mains is an A1 finding with the count",
        ),
        Mutation(
            "a missing skip link stops being a finding",
            "    if not skip[\"present\"]:",
            "    if False:",
            "no skip link is an A2 finding",
        ),
        Mutation(
            "a skip link to nowhere stops being a finding",
            "    elif not skip[\"target_exists\"]:",
            "    elif False:",
            "a skip link to a missing target is an A2 finding",
        ),
        Mutation(
            "a missing live region stops being a finding",
            "    if snap[\"live_regions\"] < 1:",
            "    if False:",
            "no live region is an A2 finding",
        ),
        Mutation(
            "a nav link to this page without aria-current stops being a finding",
            "    if links and not any(l[\"current\"] for l in links):",
            "    if False:",
            "a nav link to this page without aria-current is an A4 finding",
        ),
        Mutation(
            "A4 fires on a page the nav does not link to",
            "    if links and not any(l[\"current\"] for l in links):",
            "    if not any(l[\"current\"] for l in snap[\"primary_nav\"][\"links\"]):",
            "a page the nav does not link to has no A4 finding",
        ),
        Mutation(
            "a non-2xx page is judged as if it rendered",
            "        if not isinstance(status, int) or not 200 <= status < 300:",
            "        if False:",
            "a non-2xx page is skipped and counted, not judged",
        ),
        Mutation(
            "an empty list stops being refused",
            "    if not isinstance(doc, list) or not doc:",
            "    if not isinstance(doc, list):",
            "an empty list is unusable",
        ),
        Mutation(
            "a run that judged nothing passes",
            "    if not judged:",
            "    if False:",
            "a list with no 2xx page is unusable",
        ),
    ),
)
