"""Mutation guard: check_upstream_docs. Declared here, run by scripts/mutation_check.py (#1328).

Each mutation makes a changed Claude Code doc, or a citation nothing re-reads, look fine: the two
things this checker exists to report.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_upstream_docs",
    subject="scripts/check_upstream_docs.py",
    selftest="scripts/check_upstream_docs.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a quote the page no longer says passes",
            '        if normalise(row["quote"]) not in pages[url]:',
            "        if False:",
            "a quote the page no longer says is a finding naming what is built on it",
        ),
        Mutation(
            "the page is fetched as rendered HTML, not markdown",
            '                pages[url] = normalise(fetch(url + ".md"))',
            "                pages[url] = normalise(fetch(url))",
            "the page is fetched as markdown",
        ),
        Mutation(
            "a fetch failure reads as a clean page",
            "                raise Unusable(f\"could not fetch {url}.md: {exc}\") from exc",
            '                pages[url] = ""\n                continue',
            "a fetch failure is UNUSABLE, never clean",
        ),
        Mutation(
            "markdown emphasis is left in, so a bold word breaks every quote",
            '    text = re.sub(r"[*`]", "", text)',
            '    text = re.sub(r"[`]", "", text)',
            "CONTROL: a quote across lines, emphasis and a link is found",
        ),
        Mutation(
            "versions compare as text, so 2.1.100 reads as older than 2.1.99",
            "        if version and _version(version) > _version(cursor)",
            "        if version and version > cursor",
            "versions compare numerically, not as text",
        ),
        Mutation(
            "an entry naming our surfaces is dropped",
            'and line.startswith("- ") and SURFACES.search(line):',
            'and line.startswith("- ") and False:',
            "entries after the cursor that name our surfaces are listed",
        ),
        Mutation(
            "a cited page with no registry row goes unreported",
            "    for url in sorted(set(cited) - rows_by_url):",
            "    for url in []:",
            "a cited page with no row is a finding naming the citer",
        ),
        Mutation(
            "a used_by path that vanished is not reported",
            "            if not (root / path).exists():",
            "            if False:",
            "a used_by path that does not exist is a finding",
        ),
    ),
)
