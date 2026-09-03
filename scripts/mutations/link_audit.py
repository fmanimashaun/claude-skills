"""Mutation guard: link_audit. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #108 item E. Five of these seven break a rule by making it fire MORE — the direction that gets
# a rule switched off. A link audit that reports every auth-gated page and every `mailto:` as a
# dead link is deleted within a day, taking every genuine 404 with it.
GUARD = Guard(
    name="link_audit",
    subject="plugins/qa-flow/scripts/link_audit.py",
    selftest="plugins/qa-flow/scripts/link_audit.py",
    needs=("plugins/qa-flow/scripts/crawl_collector.js",),
    mutations=(
        Mutation(
            "the broken-link boundary moves to 500, so every 404 goes quiet",
            "                elif isinstance(status, int) and status >= 400:",
            "                elif isinstance(status, int) and status >= 500:",
            "a 404 target is a broken link",
        ),
        Mutation(
            "the unauthenticated carve-out widens past 401/403 and swallows a dead link",
            "UNAUTHENTICATED_STATUSES = frozenset({401, 403})",
            "UNAUTHENTICATED_STATUSES = frozenset({401, 403, 410})",
            "a 410 is still a broken link",
        ),
        Mutation(
            "the scheme test becomes a substring match, exempting any href containing 'mailto:'",
            "    match = SCHEME.match(href.strip())",
            '    match = re.search(r"([a-zA-Z][a-zA-Z0-9+.\\-]*):", href.strip())',
            "an href CONTAINING 'mailto:' in a query is still judged",
        ),
        Mutation(
            "the rel test becomes a substring match, so a `noopenerfoo` typo passes as safe",
            '                if not tokens & {"noopener", "noreferrer"}:',
            '                if "noopener" not in str(link.get("rel") or "").lower():',
            "a lookalike rel token does not satisfy it",
        ),
        Mutation(
            # This one fires MORE, and on the single most common spelling of the fix.
            "`split()` goes, so the whole rel is one token and `noopener noreferrer` reports a leak",
            '                tokens = {tok for tok in str(link.get("rel") or "").lower().split() if tok}',
            '                tokens = {str(link.get("rel") or "").lower()}',
            "rel='noopener noreferrer' satisfies the rule",
        ),
        Mutation(
            "`noreferrer` stops counting, so a correctly-severed link reports a leak",
            '                if not tokens & {"noopener", "noreferrer"}:',
            '                if not tokens & {"noopener"}:',
            "rel='noreferrer' satisfies the rule",
        ),
        Mutation(
            "the opener rule moves out of reach, where a real leak can never be reported",
            '            if str(link.get("target") or "").lower() == "_blank":',
            "            if False:",
            "target=_blank with no rel is an opener leak",
        ),
        Mutation(
            "the top-of-document carve-out goes, so every `#` and `#top` reports dead",
            "            if fragment.lower() in TOP_FRAGMENTS:",
            "            if False:",
            "is the top of the document, not a dead fragment",
        ),
        Mutation(
            "an un-inventoried anchor list stops being distinguished from an empty one",
            "            if anchors is None:",
            "            if anchors is None or not anchors:",
            "a page with an EMPTY anchor list is still judged",
        ),
        Mutation(
            "the document carve-out widens to every response, so no missing asset is reported",
            '            if str(response.get("resourceType", "")) == DOCUMENT_RESOURCE:',
            "            if True:",
            "a 404 sub-resource is a missing asset",
        ),
        Mutation(
            "findings group by rule alone, collapsing unrelated defects into one",
            "        key = (rule, target)",
            '        key = (rule, "")',
            "two DIFFERENT broken targets are two findings",
        ),
        Mutation(
            "an inventory with no base origin is judged instead of refused",
            '    if not origin_of(str(data.get("base") or "")):',
            "    if False:",
            "no base origin, so internal cannot be told from external",
        ),
    ),
)
