"""Mutation guard: check_verdict_quotes. Declared here, run by scripts/mutation_check.py (#2233).

Each mutation lets a CONFIRMED verdict stand on a quote the page does not hold: a missing phrase read as present, a JavaScript shell read as a page,
a script's text counted as the reader's, case folded, a failed fetch read as a match, a refusal outranked by an inconclusive page, or a new audit
excused from carrying its quotes. The selftest's fabricated quote, shell, missing page and format fixtures must each turn red.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_verdict_quotes",
    subject="scripts/check_verdict_quotes.py",
    selftest="scripts/check_verdict_quotes.py",
    mutations=(
        Mutation(
            "a phrase that is not on the page is read as present",
            "    return MATCH if normalise(phrase) in page.text else ABSENT",
            "    return MATCH",
            "a FABRICATED quote is refused (exit 1)",
        ),
        Mutation(
            "a JavaScript shell is read as a page, so its verdict is not INCONCLUSIVE",
            "    return Page(text, is_html and len(text) < SHELL_MIN_CHARS)",
            "    return Page(text, False)",
            "a JavaScript shell is INCONCLUSIVE (exit 2), never CONFIRMED",
        ),
        Mutation(
            "text that only a <script> holds counts as the page's text",
            '_DROP = re.compile(r"<(script|style|noscript|template|svg)',
            '_DROP = re.compile(r"<(style|noscript|template|svg)',
            "text only a <script> holds is not on the page",
        ),
        Mutation(
            "case is folded, so a paraphrase in the wrong case is confirmed",
            "    return MATCH if normalise(phrase) in page.text else ABSENT",
            "    return MATCH if normalise(phrase).lower() in page.text.lower() else ABSENT",
            "case is not folded: the wrong case is refused",
        ),
        Mutation(
            "a page that could not be fetched is read as a match",
            "def judge(url: str, phrase: str, page: Page) -> str:\n    if page.error:\n        return UNFETCHABLE",
            "def judge(url: str, phrase: str, page: Page) -> str:\n    if page.error:\n        return MATCH",
            "a missing page is INCONCLUSIVE (exit 2)",
        ),
        Mutation(
            "an inconclusive page outranks an absent phrase, so a refusal is downgraded",
            "    code = 1 if absent else 2 if cannot else 0",
            "    code = 2 if cannot else 1 if absent else 0",
            "an absent phrase wins over an inconclusive page (exit 1), and both are reported",
        ),
        Mutation(
            "a page is fetched again for every phrase that cites it",
            "        if q.url not in pages:\n            pages[q.url] = fetcher(q.url)\n        page = pages[q.url]",
            "        pages[q.url] = fetcher(q.url)\n        page = pages[q.url]",
            "the page is fetched once however many phrases cite it",
        ),
        Mutation(
            "a new audit that says CONFIRMED is excused from carrying its quotes",
            "        if not quotes and not WAIVER.search(text):",
            "        if False:",
            "a new audit that says CONFIRMED with no quotes block is a finding",
        ),
        Mutation(
            "an inline tag becomes a space, so `<code>1</code>,` reads `1 ,` and a verbatim quote of the page is refused",
            '        raw = _TAG.sub("", _BLOCK.sub(" ", _DROP.sub(" ", raw)))',
            '        raw = _TAG.sub(" ", _BLOCK.sub(" ", _DROP.sub(" ", raw)))',
            "an inline tag leaves no space: `<code>x</code>,` reads as `x,`",
        ),
    ),
)
