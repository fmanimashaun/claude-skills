#!/usr/bin/env python3
"""Judge a link inventory: which links point at nothing, and which assets never arrived.

Run:  python3 link_audit.py qa/manual-tests/links.json
      python3 link_audit.py qa/manual-tests/links.json --json
      python3 link_audit.py --schema      # what the collector must emit
      python3 link_audit.py --selftest

WHY (#108, epic item E — "broken link + missing asset audit: classic, cheap, currently absent").
#113 shipped the reporting half of this: a `links` evidence lane an agent fills in by hand and
`validate_evidence.py` checks the shape of. Nothing mechanical ever followed a link. The crawl added
in 1.17.0–1.18.0 visits a fixed list of routes and never looks at what those pages link TO, so a
footer link to `/pricng` is invisible: the typo is not in `qa/routes.json`, so it is never crawled,
never judged, and never reported.

THE CARVE-OUT THIS PAYS FOR. `interaction_report.py` excludes `a[href]` from `dead-control` because
"navigation IS its effect; a crawl that stays on the page cannot observe it" — correct, and it leaves
every link on the site judged by nothing at all. That exclusion is only safe once something else owns
link targets. This is that something.

TWO THINGS A STATUS-ONLY CHECK MISSES, and both are the normal case rather than the exotic one:

  * **A 404 subresource is not a failed request.** Playwright's `requestfailed` fires on network-level
    failures only — "HTTP error responses, such as 404 or 503, are still successful responses from
    HTTP standpoint, so request will complete with 'requestfinished' event"
    (https://playwright.dev/docs/api/class-request). `crawl_report.py` reads `failedRequests`, so a
    `<img src="/logo-old.png">` returning a perfectly well-formed 404 passes it. The collector
    therefore records RESPONSES with a 4xx/5xx status, which is a different mechanism, not a
    duplicate one.
  * **A fragment that matches nothing scrolls nowhere, silently.** `href="#pricing"` with no
    `id="pricing"` is a dead link that returns 200, because the fragment is never sent to the server.

BROWSER MEASURES, PYTHON JUDGES. The collector inventories hrefs, in-page anchor names, sub-resource
statuses, and the status of each distinct internal target it probed. Every threshold, exclusion and
verdict is here, which is what lets this be gated in CI with no browser.

ONE DEAD LINK IN A SHARED FOOTER IS ONE FINDING (#118). Findings are grouped by target, with a count
and up to three example routes. Reporting the same broken footer link once per page is how a report
of 773 "defects" turns out to be 18 — and a developer told 773 stops reading.

THE EXCLUSIONS ARE THE DESIGN, and each has a near-miss fixture proving it does not swallow the
finding it was carved from:

  * **Non-http(s) schemes** — `mailto:`, `tel:`, `javascript:`. Judged on the SCHEME, never on a
    substring: `/contact?to=mailto:x@y` is an ordinary internal link and is still judged.
  * **Another origin** — not probed, because a QA gate must not depend on the internet being up.
    Counted and reported. An absolute URL on the SAME origin is internal and still judged.
  * **`#` and `#top`** — the HTML Standard makes both the top of the document with no element
    required: "If decodedFragment is an ASCII case-insensitive match for the string `top` … scroll to
    the beginning of the document" (https://html.spec.whatwg.org/multipage/browsing-the-web.html).
    Matched case-insensitively and in full, so `#topic` still fires.
  * **401 / 403** — the crawl is unauthenticated, so an auth-gated target is UNKNOWN, not broken.
    Reported as unverified. Any other 4xx/5xx is still a finding.
  * **The document response** — a page's own 4xx is `crawl_report.py`'s `http-error`. A non-document
    response at that same URL is still a missing asset.

THREE STATES, AND THE THIRD IS THE POINT. A target the collector never probed, or that answered 401
or 403, is `unverified`: named on every run, never counted clean, and never a finding. A link audit
that quietly called an unprobed target fine would be the failure this whole toolchain keeps
re-learning.

WHAT IT DOES NOT DO. It does not crawl, and it does not fetch: it reads what a run recorded. It does
not judge the page a link lands on — `crawl_report.py` owns route status and error pages. It does not
decide coverage — `route_coverage.py` does — though an internal target that was never crawled is
exactly the gap that tool measures.

Exit codes:  0 clean · 1 findings · 2 the inventory is unusable

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

SCHEMA = "qa-flow/link-audit/1"

# The document a collector must produce. ONE definition, printed by `--schema` and cross-checked
# against the shipped collector by the selftest -- they are separate files in separate languages, so
# nothing else stops them drifting, and a collector that quietly stops emitting a field makes the
# rule reading it go silent rather than fail.
SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "base": "http://localhost:3000",
    "pages": [{
        "route": "/",
        # Every `id` on the page, plus every `a[name]` -- both are fragment targets per the HTML
        # Standard's "find a potential indicated element". Absent (null) means the collector did not
        # inventory them, which is unverified rather than "the page has none".
        "anchors": ["main", "pricing"],
        "links": [{"href": "/pricng", "resolved": "http://localhost:3000/pricng", "text": "Pricing"}],
        # Responses with a 4xx/5xx status. NOT the same thing as crawl.json's `failedRequests`,
        # which are network-level failures: a 404 is a successful response and never appears there.
        "responses": [{"url": "http://localhost:3000/logo-old.png", "status": 404,
                       "resourceType": "image"}],
    }],
    # Each distinct internal link target, defragmented, with the status the probe got.
    "targets": [{"url": "http://localhost:3000/pricng", "status": 404}],
}
COLLECTOR = "crawl_collector.js"

# A scheme that does not navigate to a document we could have probed. Matched at the START of the
# RAW href, never as a substring -- see the docstring's near-miss.
SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
NAVIGATIONAL_SCHEMES = frozenset({"http", "https"})

# Fragments the browser resolves without any matching element. Compared in full and
# case-insensitively, per the HTML Standard: `#topic` is not `#top`.
TOP_FRAGMENTS = frozenset({"", "top"})

# The crawl is unauthenticated, so these mean "we were not allowed to look", not "the link is dead".
# A rule that reported every auth-gated link as broken would be switched off the first day it ran,
# taking every genuine 404 with it.
UNAUTHENTICATED_STATUSES = frozenset({401, 403})

# A page's own error status belongs to crawl_report.py's `http-error`. Reporting it here too would be
# a second rule with a second owner for one defect.
DOCUMENT_RESOURCE = "document"

MAX_EXAMPLES = 3


class Unusable(RuntimeError):
    """The inventory cannot be judged -- reported, never treated as a clean audit."""


@dataclass
class Finding:
    rule: str
    target: str
    detail: str
    count: int          # DISTINCT routes affected -- see Grouper
    examples: list[str]


@dataclass
class Judged:
    findings: list[Finding] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    pages: int = 0
    judged: int = 0             # internal, navigational links actually judged
    external: int = 0
    non_navigational: int = 0


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Unusable(
            f"{path}: not a {SCHEMA} document. An inventory this file cannot read is NOT a clean "
            "audit — run `--schema` to see what the collector must emit.")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise Unusable(
            f"{path}: no pages. An empty inventory reporting zero broken links is indistinguishable "
            "from a site with none, which is the one outcome this must never produce.")
    if not origin_of(str(data.get("base") or "")):
        # Without the app's own origin nothing can tell an internal link from a third-party one, and
        # the failure is SILENT rather than loud: every external link degrades to "unverified" and
        # the report fills with noise about targets we were never going to probe.
        raise Unusable(
            f"{path}: no usable `base` origin. Which links are internal cannot be decided without "
            "it, so this is refused rather than judged.")
    if not any(page.get("links") for page in pages if isinstance(page, dict)):
        raise Unusable(
            f"{path}: not one link was inventoried across {len(pages)} page(s). A collector that "
            "recorded no hrefs reports zero broken links for the same reason a healthy site does — "
            "run the collector with `--links`.")
    return data


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme or parts.netloc else ""


def defrag(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def scheme_of(href: str) -> str | None:
    """The href's own scheme, or None when it is relative. Never a substring match."""
    match = SCHEME.match(href.strip())
    return match.group(1).lower() if match else None


class Grouper:
    """One finding per target, with a count and up to three example routes (#118).

    THE COUNT IS DISTINCT ROUTES, not occurrences, and that is not a detail. A real run showed the
    same missing image recorded eight times for one page — the interaction sweep navigates away and
    back, and each return re-requests it. "8×" for a one-page defect is the inflated arithmetic #118
    exists to stop, in miniature. `count` therefore answers "how many pages is this on".
    """

    def __init__(self) -> None:
        self._detail: dict[tuple[str, str], str] = {}
        self._routes: dict[tuple[str, str], dict[str, None]] = {}

    def add(self, rule: str, target: str, detail: str, route: str) -> None:
        key = (rule, target)
        self._detail.setdefault(key, detail)
        self._routes.setdefault(key, {})[route] = None

    def findings(self) -> list[Finding]:
        out = []
        for (rule, target), routes in sorted(self._routes.items()):
            out.append(Finding(rule, target, self._detail[(rule, target)],
                               len(routes), sorted(routes)[:MAX_EXAMPLES]))
        return out

    def lines(self) -> list[str]:
        """The same grouping rendered flat, for the states that are not findings.

        The RULE NAME leads, because these lines are all a reader gets for the third state and
        "unverified" alone does not say which kind of unknown it was.
        """
        return [f"{rule}: {target} — {self._detail[(rule, target)]} "
                f"(on {len(routes)} page(s), e.g. {', '.join(sorted(routes)[:MAX_EXAMPLES])})"
                for (rule, target), routes in sorted(self._routes.items())]


def judge(doc: dict) -> Judged:
    base_origin = origin_of(str(doc.get("base") or ""))
    pages = [p for p in doc.get("pages") or [] if isinstance(p, dict)]
    result = Judged(pages=len(pages))

    by_route = {str(p.get("route", "")): p for p in pages}
    targets = {str(t.get("url", "")): t.get("status")
               for t in doc.get("targets") or [] if isinstance(t, dict)}

    found = Grouper()
    unknown = Grouper()

    for page in pages:
        route = str(page.get("route", "<unknown>"))

        # ---- sub-resources ------------------------------------------------------------------
        for response in page.get("responses") or []:
            if not isinstance(response, dict):
                continue
            status = response.get("status")
            if not isinstance(status, int) or status < 400:
                continue
            if str(response.get("resourceType", "")) == DOCUMENT_RESOURCE:
                # crawl_report.py's `http-error` owns the page itself.
                continue
            url = str(response.get("url", "?"))
            found.add("missing-asset", url,
                      f"HTTP {status} for a sub-resource "
                      f"({response.get('resourceType') or 'unknown type'})", route)

        # ---- links --------------------------------------------------------------------------
        for link in page.get("links") or []:
            if not isinstance(link, dict):
                continue
            href = str(link.get("href") or "")
            resolved = str(link.get("resolved") or "")
            label = str(link.get("text") or "").strip()[:40] or "(no text)"

            scheme = scheme_of(href)
            if scheme is not None and scheme not in NAVIGATIONAL_SCHEMES:
                result.non_navigational += 1
                continue
            if not resolved:
                unknown.add("unresolved-href", href or "(empty href)",
                            "the collector recorded no resolved URL", route)
                continue
            if base_origin and origin_of(resolved) != base_origin:
                # Not probed: a QA gate that fails when the internet is down is a gate people
                # disable. Counted so the number is never mistaken for zero.
                result.external += 1
                continue

            result.judged += 1
            target = defrag(resolved)

            # -- the path half ----------------------------------------------------------------
            if target in targets:
                status = targets[target]
                if isinstance(status, int) and status in UNAUTHENTICATED_STATUSES:
                    unknown.add("auth-gated-target", target,
                                f"HTTP {status} — the crawl is unauthenticated, so this is unknown "
                                "rather than broken", route)
                elif isinstance(status, int) and status >= 400:
                    found.add("broken-link", target,
                              f"HTTP {status} — linked as {label!r}", route)
                elif not isinstance(status, int):
                    unknown.add("unprobed-target", target,
                                "the probe recorded no status", route)
            else:
                unknown.add("unprobed-target", target,
                            "no probe reached this target, so nothing about it was verified", route)

            # -- the fragment half ------------------------------------------------------------
            if "#" not in href:
                continue
            fragment = unquote(urlsplit(resolved).fragment)
            if fragment.lower() in TOP_FRAGMENTS:
                # The HTML Standard resolves both to the top of the document with no element.
                continue
            target_page = by_route.get(urlsplit(resolved).path)
            anchors = target_page.get("anchors") if isinstance(target_page, dict) else None
            if anchors is None:
                unknown.add("unverified-fragment", f"{urlsplit(resolved).path}#{fragment}",
                            "the target page's anchors were never inventoried", route)
            elif fragment not in {str(a) for a in anchors}:
                found.add("dead-fragment", f"{urlsplit(resolved).path}#{fragment}",
                          f"no element carries that id or name — linked as {label!r}", route)

    result.findings = found.findings()
    result.unverified = unknown.lines()
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge a link inventory.")
    ap.add_argument("inventory", nargs="?", type=Path, help="the collector's links.json")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--schema", action="store_true", help="print what the collector must emit")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if not args.inventory:
        ap.error("an inventory file is required (or --schema / --selftest)")

    try:
        result = judge(load(args.inventory))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"pages": result.pages, "judged": result.judged,
                          "external": result.external,
                          "nonNavigational": result.non_navigational,
                          "unverified": result.unverified,
                          "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        for f in result.findings:
            print(f"  [{f.rule}] {f.target}\n      {f.detail} (on {f.count} page(s), "
                  f"e.g. {', '.join(f.examples)})")
        for u in result.unverified:
            print(f"  [unverified] {u}")
        print(f"\n{result.pages} page(s), {result.judged} internal link(s) judged, "
              f"{len(result.findings)} finding(s), {len(result.unverified)} unverified, "
              f"{result.external} external and {result.non_navigational} non-navigational "
              f"link(s) not followed.")
        if result.unverified:
            # Said every time. See the module docstring's third state.
            print("A target nothing probed is NOT a working target.")
    return 1 if result.findings else 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    BASE = "http://localhost:3000"

    def link(href, resolved=None, text="Go"):
        return {"href": href,
                "resolved": resolved if resolved is not None else f"{BASE}{href}",
                "text": text}

    def doc(pages, targets=()):
        return {"schema": SCHEMA, "base": BASE, "pages": list(pages), "targets": list(targets)}

    def page(route="/", links=(), anchors=(), responses=()):
        return {"route": route, "links": list(links), "anchors": list(anchors),
                "responses": list(responses)}

    def rules(d) -> list[str]:
        return [f.rule for f in judge(d).findings]

    # ---- the baseline: a healthy page is SILENT ------------------------------------------------
    ok = doc([page(links=[link("/about")], anchors=["main"])],
             [{"url": f"{BASE}/about", "status": 200}])
    check("a 200 link is silent", rules(ok) == [], f"got {judge(ok)}")
    check("a 200 link is not unverified either", judge(ok).unverified == [], f"{judge(ok).unverified}")
    check("a 200 link is counted as judged", judge(ok).judged == 1, f"{judge(ok).judged}")

    # ---- broken-link ---------------------------------------------------------------------------
    d404 = doc([page(links=[link("/pricng")])], [{"url": f"{BASE}/pricng", "status": 404}])
    check("a 404 target is a broken link", rules(d404) == ["broken-link"], f"{rules(d404)}")
    d500 = doc([page(links=[link("/boom")])], [{"url": f"{BASE}/boom", "status": 500}])
    check("a 500 target is a broken link", rules(d500) == ["broken-link"], f"{rules(d500)}")
    d400 = doc([page(links=[link("/bad")])], [{"url": f"{BASE}/bad", "status": 400}])
    check("a 400 target is a broken link", rules(d400) == ["broken-link"],
          "the boundary is >= 400, not > 400")
    d301 = doc([page(links=[link("/moved")])], [{"url": f"{BASE}/moved", "status": 200}])
    check("a target the probe followed to a 200 is silent", rules(d301) == [], f"{rules(d301)}")

    # A query string is part of the target: /search?q=x and /search are different links.
    dq = doc([page(links=[link("/search?q=x")])],
             [{"url": f"{BASE}/search?q=x", "status": 404}, {"url": f"{BASE}/search", "status": 200}])
    check("the query string is part of the target", rules(dq) == ["broken-link"], f"{rules(dq)}")

    # ---- 401/403 ARE UNVERIFIED, NOT BROKEN, and the near-miss keeps 404 firing -----------------
    for status in (401, 403):
        d = doc([page(links=[link("/admin")])], [{"url": f"{BASE}/admin", "status": status}])
        check(f"an HTTP {status} target is unverified, not broken", rules(d) == [], f"{rules(d)}")
        check(f"an HTTP {status} target is named as unverified", len(judge(d).unverified) == 1,
              f"{judge(d).unverified}")
    d410 = doc([page(links=[link("/gone")])], [{"url": f"{BASE}/gone", "status": 410}])
    check("a 410 is still a broken link", rules(d410) == ["broken-link"],
          "the auth carve-out must be exactly {401, 403}; widening it swallows every dead link")

    # ---- THE THIRD STATE: a target nothing probed ----------------------------------------------
    # The target slug is deliberately BLAND. An earlier version linked `/never-probed` and asserted
    # the word "never" appeared, which the URL itself supplied -- the assertion passed without the
    # rule saying anything, which is the vacuous fixture this repo's mutation checker exists for.
    dun = doc([page(links=[link("/x")])], [])
    check("an unprobed target is not a finding", rules(dun) == [], f"{rules(dun)}")
    check("an unprobed target is named", len(judge(dun).unverified) == 1, f"{judge(dun).unverified}")
    check("an unprobed target is named as unprobed",
          bool(judge(dun).unverified) and judge(dun).unverified[0].startswith("unprobed-target:"),
          f"{judge(dun).unverified}")
    dnull = doc([page(links=[link("/x")])], [{"url": f"{BASE}/x", "status": None}])
    check("a probe with no status is unverified, not a pass",
          rules(dnull) == [] and len(judge(dnull).unverified) == 1, f"{judge(dnull)}")

    # ---- SCHEME EXCLUSIONS, and the near-miss that keeps them honest ---------------------------
    for href in ("mailto:a@b.com", "tel:+441234", "javascript:void(0)", "sms:+1",
                 "data:text/plain,hi"):
        d = doc([page(links=[link(href, resolved=href)])])
        check(f"{href.split(':')[0]}: is not judged as a link", rules(d) == [], f"{rules(d)}")
        check(f"{href.split(':')[0]}: is counted as non-navigational",
              judge(d).non_navigational == 1, f"{judge(d).non_navigational}")
    # NEAR MISS. The exclusion is on the SCHEME, never on a substring: this href merely CONTAINS
    # "mailto:" in a query value and is an ordinary internal link.
    dnm = doc([page(links=[link("/contact?to=mailto:a@b.com")])],
              [{"url": f"{BASE}/contact?to=mailto:a@b.com", "status": 404}])
    check("an href CONTAINING 'mailto:' in a query is still judged",
          rules(dnm) == ["broken-link"], f"{rules(dnm)}")
    check("a relative href with no scheme is judged",
          rules(doc([page(links=[link("/rel")])], [{"url": f"{BASE}/rel", "status": 404}]))
          == ["broken-link"])

    # A link the collector could not resolve is UNKNOWN, never silently dropped.
    dnores = doc([page(links=[{"href": "/x", "resolved": "", "text": "X"}])])
    check("a link with no resolved URL is not a finding", rules(dnores) == [], f"{rules(dnores)}")
    check("a link with no resolved URL is named",
          any(u.startswith("unresolved-href:") for u in judge(dnores).unverified),
          f"{judge(dnores).unverified}")
    check("a link with no resolved URL is not counted as judged",
          judge(dnores).judged == 0, f"{judge(dnores).judged}")

    # ---- ORIGIN EXCLUSION, and its near-miss ---------------------------------------------------
    dext = doc([page(links=[link("https://example.com/x", resolved="https://example.com/x")])])
    check("another origin is not probed or judged", rules(dext) == [], f"{rules(dext)}")
    check("another origin is counted", judge(dext).external == 1, f"{judge(dext).external}")
    dproto = doc([page(links=[link("//cdn.example.com/a.js", resolved="https://cdn.example.com/a.js")])])
    check("a protocol-relative URL to another host is external",
          judge(dproto).external == 1, f"{judge(dproto)}")
    # NEAR MISS: an ABSOLUTE url on the SAME origin is internal and must still be judged.
    dabs = doc([page(links=[link(f"{BASE}/dead", resolved=f"{BASE}/dead")])],
               [{"url": f"{BASE}/dead", "status": 404}])
    check("an absolute URL on the SAME origin is still judged",
          rules(dabs) == ["broken-link"], f"{rules(dabs)}")

    # ---- dead-fragment --------------------------------------------------------------------------
    dfrag = doc([page(links=[link("#pricing", resolved=f"{BASE}/#pricing")], anchors=["main"])],
                [{"url": f"{BASE}/", "status": 200}])
    check("a fragment matching no id fires", rules(dfrag) == ["dead-fragment"], f"{rules(dfrag)}")
    dok = doc([page(links=[link("#main", resolved=f"{BASE}/#main")], anchors=["main"])],
              [{"url": f"{BASE}/", "status": 200}])
    check("a fragment matching an id is silent", rules(dok) == [], f"{rules(dok)}")
    # An `a[name]` is a fragment target too, per the HTML Standard's potential-indicated-element.
    dname = doc([page(links=[link("#legacy", resolved=f"{BASE}/#legacy")], anchors=["legacy"])],
                [{"url": f"{BASE}/", "status": 200}])
    check("an a[name] anchor satisfies a fragment", rules(dname) == [], f"{rules(dname)}")
    # Percent-encoded fragments are decoded before comparison, per the spec.
    denc = doc([page(links=[link("#a%20b", resolved=f"{BASE}/#a%20b")], anchors=["a b"])],
               [{"url": f"{BASE}/", "status": 200}])
    check("a percent-encoded fragment is decoded before comparison", rules(denc) == [],
          f"{rules(denc)}")

    # NEAR MISSES on the top-of-document carve-out. `#` and `#top` need no element (HTML Standard);
    # `#topic` is a different fragment entirely and a carve-out that swallowed it would hide every
    # dead fragment beginning with those three letters.
    for href, resolved in (("#", f"{BASE}/#"), ("#top", f"{BASE}/#top"), ("#TOP", f"{BASE}/#TOP")):
        d = doc([page(links=[link(href, resolved=resolved)], anchors=[])],
                [{"url": f"{BASE}/", "status": 200}])
        check(f"{href!r} is the top of the document, not a dead fragment", rules(d) == [],
              f"{rules(d)}")
    dtopic = doc([page(links=[link("#topic", resolved=f"{BASE}/#topic")], anchors=[])],
                 [{"url": f"{BASE}/", "status": 200}])
    check("'#topic' is still judged", rules(dtopic) == ["dead-fragment"], f"{rules(dtopic)}")

    # A CROSS-PAGE fragment is judged against the page it points at, when we crawled it.
    dcross = doc([page(route="/", links=[link("/help#faq", resolved=f"{BASE}/help#faq")]),
                  page(route="/help", anchors=["intro"])],
                 [{"url": f"{BASE}/help", "status": 200}])
    check("a cross-page fragment matching nothing fires", rules(dcross) == ["dead-fragment"],
          f"{rules(dcross)}")
    dcross_ok = doc([page(route="/", links=[link("/help#faq", resolved=f"{BASE}/help#faq")]),
                     page(route="/help", anchors=["faq"])],
                    [{"url": f"{BASE}/help", "status": 200}])
    check("a cross-page fragment that matches is silent", rules(dcross_ok) == [], f"{rules(dcross_ok)}")
    # A page we never inventoried anchors for is UNVERIFIED, not clean -- and `anchors: []` (a page
    # with genuinely no ids) is a DIFFERENT thing that IS judged.
    dnoanch = doc([page(route="/", links=[link("/help#faq", resolved=f"{BASE}/help#faq")])],
                  [{"url": f"{BASE}/help", "status": 200}])
    unv = judge(dnoanch).unverified
    check("a fragment into a page whose anchors were never inventoried is unverified",
          rules(dnoanch) == [] and any(u.startswith("unverified-fragment:") for u in unv), f"{unv}")
    check("a page with an EMPTY anchor list is still judged",
          rules(doc([page(route="/", links=[link("/h#f", resolved=f"{BASE}/h#f")]),
                     page(route="/h", anchors=[])],
                    [{"url": f"{BASE}/h", "status": 200}])) == ["dead-fragment"],
          "anchors: [] means 'no ids', which is a finding; only null means 'not inventoried'")

    # A link WITHOUT a fragment never reaches the fragment rule, whatever the target page holds.
    dnofrag = doc([page(route="/", links=[link("/help", resolved=f"{BASE}/help")]),
                   page(route="/help", anchors=[])],
                  [{"url": f"{BASE}/help", "status": 200}])
    check("a link with no '#' is not judged for fragments", rules(dnofrag) == [], f"{rules(dnofrag)}")

    # ---- missing-asset, and the document carve-out's near-miss ----------------------------------
    dasset = doc([page(links=[link("/a")],
                       responses=[{"url": f"{BASE}/logo.png", "status": 404, "resourceType": "image"}])],
                 [{"url": f"{BASE}/a", "status": 200}])
    check("a 404 sub-resource is a missing asset", rules(dasset) == ["missing-asset"],
          f"{rules(dasset)}")
    check("a 200 sub-resource is silent",
          rules(doc([page(links=[link("/a")],
                          responses=[{"url": f"{BASE}/logo.png", "status": 200,
                                      "resourceType": "image"}])],
                    [{"url": f"{BASE}/a", "status": 200}])) == [])
    check("a 304 sub-resource is silent",
          rules(doc([page(links=[link("/a")],
                          responses=[{"url": f"{BASE}/logo.png", "status": 304,
                                      "resourceType": "image"}])],
                    [{"url": f"{BASE}/a", "status": 200}])) == [],
          "a cache revalidation is not a missing asset")
    ddoc = doc([page(links=[link("/a")],
                     responses=[{"url": f"{BASE}/", "status": 404, "resourceType": "document"}])],
               [{"url": f"{BASE}/a", "status": 200}])
    check("a 404 DOCUMENT response is left to crawl_report.py", rules(ddoc) == [], f"{rules(ddoc)}")
    # NEAR MISS: the same URL, fetched as data rather than as the document, IS a missing asset --
    # otherwise the carve-out silences a whole class by URL rather than by resource type.
    dxhr = doc([page(links=[link("/a")],
                     responses=[{"url": f"{BASE}/", "status": 404, "resourceType": "fetch"}])],
               [{"url": f"{BASE}/a", "status": 200}])
    check("the same URL fetched as data IS a missing asset", rules(dxhr) == ["missing-asset"],
          f"{rules(dxhr)}")

    # ---- ONE DEAD LINK IN A SHARED FOOTER IS ONE FINDING (#118) ---------------------------------
    shared = doc([page(route=f"/p{i}", links=[link("/pricng")]) for i in range(5)],
                 [{"url": f"{BASE}/pricng", "status": 404}])
    grouped = judge(shared).findings
    check("one broken target across five pages is ONE finding", len(grouped) == 1, f"{grouped}")
    check("and it carries the instance count",
          bool(grouped) and grouped[0].count == 5, f"{grouped}")
    check("and at most three example routes",
          bool(grouped) and len(grouped[0].examples) == MAX_EXAMPLES, f"{grouped}")
    two = doc([page(links=[link("/a"), link("/b")])],
              [{"url": f"{BASE}/a", "status": 404}, {"url": f"{BASE}/b", "status": 404}])
    check("two DIFFERENT broken targets are two findings", len(judge(two).findings) == 2,
          "grouping by rule alone would collapse unrelated defects into one")

    # THE COUNT IS PAGES, NOT OCCURRENCES. From a real run: the interaction sweep navigates away and
    # back, and each return re-requests the same missing image, so one page reported the asset eight
    # times. Counting occurrences turns a one-page defect into "8×" — #118's arithmetic in miniature.
    twice = doc([page(links=[link("/a"), link("/a", text="Again")])],
                [{"url": f"{BASE}/a", "status": 404}])
    counted = judge(twice).findings
    check("the same target twice on ONE page counts as one page",
          bool(counted) and counted[0].count == 1, f"{counted}")
    repeated = doc([page(responses=[{"url": f"{BASE}/i.png", "status": 404, "resourceType": "image"}
                                    for _ in range(8)], links=[link("/a")])],
                   [{"url": f"{BASE}/a", "status": 200}])
    assets = [f for f in judge(repeated).findings if f.rule == "missing-asset"]
    check("an asset requested eight times on one page counts as one page",
          bool(assets) and assets[0].count == 1, f"{assets}")

    # ---- AN UNUSABLE INVENTORY IS NOT A CLEAN ONE -----------------------------------------------
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "links.json"
        for label, body in (
            ("not json", "{["),
            ("wrong schema", '{"schema": "other/1", "pages": [{"links": [{}]}]}'),
            ("no pages", json.dumps({"schema": SCHEMA, "base": BASE, "pages": []})),
            ("pages but not one link inventoried",
             json.dumps({"schema": SCHEMA, "base": BASE, "pages": [{"route": "/", "links": []}]})),
            ("no base origin, so internal cannot be told from external",
             json.dumps({"schema": SCHEMA, "pages": [{"route": "/", "links": [{"href": "/a"}]}]})),
        ):
            p.write_text(body, encoding="utf-8")
            n += 1
            try:
                load(p)
                failures.append(f"{label}: expected UNUSABLE, got a parse")
            except Unusable:
                pass
        p.write_text(json.dumps(doc([page(links=[link("/a")])],
                                    [{"url": f"{BASE}/a", "status": 200}])), encoding="utf-8")
        n += 1
        try:
            load(p)
        except Unusable as exc:
            failures.append(f"a well-formed inventory must load: {exc}")

    # ---- THE COLLECTOR MUST EMIT EVERY FIELD THIS SCHEMA DECLARES -------------------------------
    # Separate files in separate languages drift, and a collector that quietly stops emitting a
    # field would make the rule reading it go SILENT rather than fail. Object shorthand counts:
    # `{ route }` is the same as `route: route`.
    collector = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", collector.is_file(), f"{collector} is missing")
    if collector.is_file():
        js = collector.read_text(encoding="utf-8")
        declared = (list(SCHEMA_EXAMPLE["pages"][0])
                    + list(SCHEMA_EXAMPLE["pages"][0]["links"][0])
                    + list(SCHEMA_EXAMPLE["pages"][0]["responses"][0])
                    + ["base", "targets"])
        missing = [f for f in declared
                   if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing,
              f"{COLLECTOR} never emits {missing} — the rule reading it would go quiet")
        check("the collector stamps the schema tag", SCHEMA in js, f"{SCHEMA} absent from {COLLECTOR}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"link_audit selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
