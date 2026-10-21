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
            'a phrase that is not on the page is read as present',
            '    return MATCH if normalise(phrase) in page.text else ABSENT',
            '    return MATCH',
            'a FABRICATED quote is refused (exit 1)',
        ),
        Mutation(
            'a JavaScript shell is read as a page, so its verdict is not INCONCLUSIVE',
            '    return Page(text, is_html and len(text) < SHELL_MIN_CHARS)',
            '    return Page(text, False)',
            'a JavaScript shell is INCONCLUSIVE (exit 2), never CONFIRMED',
        ),
        Mutation(
            "text that only a <script> holds counts as the page's text",
            '"head script style noscript template svg title".split()',
            '"head style noscript template svg title".split()',
            'text only a <script> in the body holds is not on the page',
        ),
        Mutation(
            "the <head>, and its <title>, count as the page's text",
            '"head script style noscript template svg title".split()',
            '"script style noscript template svg".split()',
            'hidden text is not on the page: the title only the head holds',
        ),
        Mutation(
            'an element with the `hidden` attribute counts as visible',
            'hides = (tag in _NEVER_VISIBLE or "hidden" in a or',
            'hides = (tag in _NEVER_VISIBLE or False or',
            'hidden text is not on the page: text inside a hidden attribute',
        ),
        Mutation(
            'an element with aria-hidden="true" counts as visible',
            'or a.get("aria-hidden", "").lower() == "true" or',
            'or False or',
            'hidden text is not on the page: text inside aria hidden',
        ),
        Mutation(
            'an inline display:none counts as visible',
            'bool(_HIDDEN_STYLE.search(a.get("style", "")))',
            'False',
            'hidden text is not on the page: text inside an inline display none',
        ),
        Mutation(
            'case is folded, so a paraphrase in the wrong case is confirmed',
            '    return MATCH if normalise(phrase) in page.text else ABSENT',
            '    return MATCH if normalise(phrase).lower() in page.text.lower() else ABSENT',
            'case is not folded: the wrong case is refused',
        ),
        Mutation(
            'a page that could not be fetched is read as a match',
            'def judge(url: str, phrase: str, page: Page) -> str:\n    if page.error:\n        return UNFETCHABLE',
            'def judge(url: str, phrase: str, page: Page) -> str:\n    if page.error:\n        return MATCH',
            'a missing page is INCONCLUSIVE (exit 2)',
        ),
        Mutation(
            'a redirect is followed silently, so the page read is not the page cited',
            '            if r.geturl() != url:',
            '            if False:',
            'a redirect is INCONCLUSIVE (exit 2): the page read is not the page cited',
        ),
        Mutation(
            'an inconclusive page outranks an absent phrase, so a refusal is downgraded',
            '    code = 1 if absent else 2 if cannot else 0',
            '    code = 2 if cannot else 1 if absent else 0',
            'an absent phrase wins over an inconclusive page (exit 1), and both are reported',
        ),
        Mutation(
            'a page is fetched again for every phrase that cites it',
            '        if q.url not in pages:\n            pages[q.url] = fetcher(q.url)\n        page = pages[q.url]',
            '        pages[q.url] = fetcher(q.url)\n        page = pages[q.url]',
            'the page is fetched once however many phrases cite it',
        ),
        Mutation(
            'every closing tag becomes a space, so `<code>1</code>,` reads `1 ,` and a verbatim quote of the page is refused',
            '                break\n        if tag in _BLOCK_TAGS and not self._hidden():',
            '                break\n        if not self._hidden():',
            'an inline tag leaves no space: `<code>x</code>,` reads as `x,`',
        ),
        Mutation(
            'an audit with a back-dated file name is treated as old',
            '        if rel in LEGACY_AUDITS:\n            continue',
            '        if rel in LEGACY_AUDITS or rel < "2026-10-22":\n            continue',
            'a BACK-DATED name does not make an audit old',
        ),
        Mutation(
            'the Verdict: line is matched in capitals only, so `verdict: confirmed` is no verdict',
            'VERDICT_LINE = re.compile(r"^\\s*[-*>]*\\s*\\**\\s*verdict\\s*\\**\\s*:\\s*\\**\\s*confirmed\\b", re.I)',
            'VERDICT_LINE = re.compile(r"^\\s*[-*>]*\\s*\\**\\s*Verdict\\s*\\**\\s*:\\s*\\**\\s*CONFIRMED\\b")',
            "`Verdict: Confirmed` and `verdict: confirmed` are verdicts in any case",
        ),
        Mutation(
            "a table cell that is CONFIRMED is no verdict",
            '        if VERDICT_LINE.search(line) or "confirmed" in cells:',
            "        if VERDICT_LINE.search(line):",
            "a table cell that is exactly CONFIRMED is a verdict, in any case",
        ),
        Mutation(
            "any line that uses the word confirmed is a verdict, so prose forces waivers",
            '        if VERDICT_LINE.search(line) or "confirmed" in cells:',
            '        if VERDICT_LINE.search(line) or "confirmed" in line.casefold():',
            "PROSE that says confirmed is not a verdict",
        ),
        Mutation(
            'one quotes block clears every verdict in the file',
            '            if ev and ev.group(1) in have:\n                continue',
            '            if have:\n                continue',
            'ONE block does not cover a second verdict',
        ),
        Mutation(
            'a waiver with any reason, of any length, clears a verdict',
            'len(waived.group(1).strip()) >= MIN_REASON',
            'len(waived.group(1).strip()) >= 0',
            'a waiver reason of `x` is a finding',
        ),
        Mutation(
            'an empty version or date field is accepted',
            'or not parts[1] or not parts[2]:',
            'or not parts[2]:',
            'an empty version or date field is refused',
        ),
    ),
)
