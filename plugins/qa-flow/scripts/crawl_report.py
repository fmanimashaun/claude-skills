#!/usr/bin/env python3
"""Judge a route crawl: which pages are broken, and which only look fine.

Run:  python3 crawl_report.py qa/manual-tests/crawl.json
      python3 crawl_report.py qa/manual-tests/crawl.json --json
      python3 crawl_report.py --schema      # what the collector must emit
      python3 crawl_report.py --selftest

WHY (#105, criterion 1). qa-flow could enumerate routes (#119) and capture console errors per page
(#109), and design-flow could judge a *rendered* page against the design system (#107). Nothing
judged the crawl itself: **which routes are broken.**

THE CASE THIS EXISTS FOR IS THE 200. A non-2xx is caught by anything, including a curl loop. A Rails
app that rescues an exception and renders its 500 template **with a 200 status** is the failure that
survives every status-code check ever written, and it is the normal shape of a production error page
behind a `rescue_from`. So status is necessary and not sufficient: a page is also a finding when it
*renders* like an error, and when it logs one.

BROWSER MEASURES, PYTHON JUDGES. Every threshold, marker and verdict is here; the collector records
status, title, console errors and failed requests and decides nothing. That split is what lets this
be gated in CI with no browser — this file has a selftest, the collector cannot.

WHAT IT DOES NOT DO. It does not crawl. It reads a crawl result, so the browser half stays where the
agent drives it and this half stays runnable anywhere. It does not judge appearance, layout or
tokens — `rendered_conformance.py` owns that, and duplicating it here would be a second rule with a
second owner. It does not decide route coverage — that is `route_coverage.py`.

Exit codes:  0 clean · 1 findings · 2 the crawl file is unusable

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "qa-flow/route-crawl/1"

# The document a collector must produce. ONE definition, printed by `--schema` and cross-checked
# against the shipped collector by the selftest -- they are separate files in separate languages, so
# nothing else stops them drifting, and a collector that quietly stops emitting a field makes the
# rule reading it go silent rather than fail.
SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "pages": [{
        "route": "/dashboard", "status": 200, "title": "Dashboard", "h1": "Your work",
        "console": [{"level": "error", "text": "Uncaught TypeError: x is not a function"}],
        "failedRequests": [{"method": "GET", "url": "/assets/missing.js",
                            "failure": "net::ERR_ABORTED"}],
        "skipped": None,
    }],
}
COLLECTOR = "crawl_collector.js"

# Text that means "this page IS an error", in the <title> or the first heading. Deliberately
# anchored to the shapes frameworks actually render, not to the word "error" anywhere on the page --
# a documentation page about error handling is not an error page, and a rule that cannot tell the
# difference gets switched off. Matched case-insensitively against the TITLE and H1 only.
ERROR_PAGE_MARKERS = (
    r"\b(?:internal server error|server error|application error)\b",
    r"\b(?:page|route|record)\s+not\s+found\b",
    r"\bthe change you wanted was rejected\b",          # Rails 422
    r"\bwe're sorry, but something went wrong\b",        # Rails 500
    r"\bexception\s+caught\b",
    r"\baction\s?controller::",                          # a leaked Rails exception class
    r"\bactive\s?record::",
)

# A console message the app itself caused. `warning` is NOT included: warnings are noise in every
# real app, and a rule that fires on all of them is a rule nobody reads.
CONSOLE_FATAL = ("error",)


MAX_EXAMPLES = 3


def _grouped(findings):
    """[( (rule, detail), [route, ...] ), ...] in first-seen order, routes de-duplicated.

    First-seen order, not sorted: the judge already emits in route order, and re-sorting by
    rule name would put an S1 uncaught exception below a cosmetic S3 purely alphabetically.
    """
    out: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        routes = out.setdefault((f.rule, f.detail), [])
        if f.route not in routes:
            routes.append(f.route)
    return list(out.items())


@dataclass
class Finding:
    route: str
    rule: str
    detail: str


@dataclass
class Judged:
    findings: list[Finding] = field(default_factory=list)
    routes: int = 0
    skipped: list[str] = field(default_factory=list)


class Unusable(RuntimeError):
    """The crawl file cannot be judged -- reported, never treated as a clean run."""


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Unusable(
            f"{path}: not a {SCHEMA} document. A crawl this file cannot read is NOT a clean crawl — "
            "run `--schema` to see what the collector must emit.")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise Unusable(
            f"{path}: no pages. An empty crawl reporting zero findings is indistinguishable from a "
            "healthy app, which is the one outcome this must never produce.")
    return pages


def judge_page(page: dict) -> list[Finding]:
    route = str(page.get("route", "<unknown>"))
    out: list[Finding] = []

    status = page.get("status")
    if not isinstance(status, int):
        out.append(Finding(route, "no-status", "the collector recorded no HTTP status"))
    elif status >= 400:
        out.append(Finding(route, "http-error", f"HTTP {status}"))
    elif 300 <= status < 400:
        out.append(Finding(route, "unresolved-redirect",
                           f"HTTP {status} — the crawl did not follow it, so the target is untested"))

    # THE 200-BUT-ERROR CASE. Checked whatever the status, because a `rescue_from` that renders the
    # 500 template with a 200 is exactly the page a status check calls healthy.
    haystack = " ".join(str(page.get(k, "")) for k in ("title", "h1"))
    for pattern in ERROR_PAGE_MARKERS:
        if re.search(pattern, haystack, re.I):
            out.append(Finding(route, "renders-as-error",
                               f"HTTP {status} but the page reads as an error: {haystack.strip()[:90]!r}"))
            break

    for message in page.get("console", []) or []:
        if str(message.get("level", "")).lower() in CONSOLE_FATAL:
            out.append(Finding(route, "console-error",
                               str(message.get("text", ""))[:120] or "(no text)"))

    # An uncaught exception is S1 in `functional-tester.md:105` — "the page is broken even though it
    # rendered" — and until the collector gained a `pageerror` listener nothing could observe the
    # highest severity in our own taxonomy. Kept distinct from `console-error`: a page can render a
    # correct-looking DOM while throwing, which is exactly the case a console scan misses.
    for error in page.get("pageErrors", []) or []:
        out.append(Finding(route, "uncaught-exception",
                           f"{error.get('name', 'Error')}: {str(error.get('message', ''))[:100]}"))

    for failed in page.get("failedRequests", []) or []:
        out.append(Finding(route, "failed-request",
                           f"{failed.get('method', '?')} {str(failed.get('url', '?'))[:80]} "
                           f"— {failed.get('failure', 'failed')}"))
    return out


def judge(pages: list[dict]) -> Judged:
    result = Judged(routes=len(pages))
    for page in pages:
        if page.get("skipped"):
            # A route the crawl could not reach did NOT pass. Named, and never counted as clean.
            result.skipped.append(f"{page.get('route', '?')}: {page.get('skipped')}")
            continue
        result.findings.extend(judge_page(page))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge a route crawl.")
    ap.add_argument("crawl", nargs="?", type=Path, help="the collector's JSON output")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--schema", action="store_true", help="print what the collector must emit")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if not args.crawl:
        ap.error("a crawl file is required (or --schema / --selftest)")

    try:
        pages = load(args.crawl)
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    result = judge(pages)

    if args.json:
        print(json.dumps({"routes": result.routes, "skipped": result.skipped,
                          "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        # #108 item J: one line per (rule, route) is how a 72-page crawl reports 773 "defects"
        # that are 18 repeated by a shared layout. Identical (rule, detail) IS the same defect,
        # so grouping on the exact pair never merges two different ones — and the `--json` path
        # above still carries every occurrence, so nothing machine-readable is lost.
        for (rule, detail), routes in _grouped(result.findings):
            if len(routes) == 1:
                print(f"  [{rule}] {routes[0]} — {detail}")
            else:
                print(f"  [{rule}] {detail} (on {len(routes)} page(s), "
                      f"e.g. {', '.join(routes[:MAX_EXAMPLES])})")
        for s in result.skipped:
            print(f"  [skipped] {s}")
        judged = result.routes - len(result.skipped)
        distinct = len(_grouped(result.findings))
        # BOTH numbers, always. The occurrence count is what tells you a defect is systemic
        # rather than local, and printing only the distinct count would hide exactly that.
        print(f"\n{judged} route(s) judged, {distinct} distinct finding(s) across "
              f"{len(result.findings)} occurrence(s), {len(result.skipped)} not reached.")
        if result.skipped:
            # Said every time. A route the crawl never reached verified nothing, and a summary that
            # lets it read as clean is the defect this whole toolchain keeps re-learning.
            print("A route the crawl did not reach is NOT a passing route.")
    return 1 if result.findings else 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def rules(page: dict) -> set[str]:
        return {f.rule for f in judge_page(page)}

    ok_page = {"route": "/", "status": 200, "title": "Dashboard", "h1": "Your work"}
    check("a healthy page is silent", rules(ok_page) == set(), f"got {rules(ok_page)}")

    check("a 500 fires", "http-error" in rules({**ok_page, "status": 500}))
    check("a 404 fires", "http-error" in rules({**ok_page, "status": 404}))
    check("a 302 is reported as unresolved",
          "unresolved-redirect" in rules({**ok_page, "status": 302}))
    check("a missing status fires", "no-status" in rules({"route": "/", "title": "x"}))

    # THE CASE THIS FILE EXISTS FOR: status 200, and the page is an error.
    for title in ("Internal Server Error", "We're sorry, but something went wrong",
                  "The change you wanted was rejected", "ActionController::RoutingError",
                  "Page not found"):
        check(f"200 rendering {title!r} fires",
              "renders-as-error" in rules({**ok_page, "title": title}),
              f"got {rules({**ok_page, 'title': title})}")
    check("an error marker in the H1 fires too",
          "renders-as-error" in rules({**ok_page, "h1": "Server Error"}))

    # NEAR MISSES. These decide whether the rule survives contact with a real app: a page ABOUT
    # errors is not an error page, and a rule that cannot tell gets switched off within a day.
    for title in ("Error handling guide", "How we handle exceptions",
                  "Error budget report", "Not Found — a history of lost things"):
        check(f"{title!r} stays silent", "renders-as-error" not in rules({**ok_page, "title": title}),
              f"fired on {title!r}")

    check("a console error fires",
          "console-error" in rules({**ok_page, "console": [{"level": "error", "text": "boom"}]}))
    check("an uncaught exception is reported",
          "uncaught-exception" in rules({**ok_page,
              "pageErrors": [{"name": "TypeError", "message": "null.f is not a function"}]}))
    # THE POINT of the rule: the page renders correctly and still throws. A DOM-only or
    # console-only check calls this clean.
    check("a page that renders fine but throws is not clean",
          rules({**ok_page, "pageErrors": [{"name": "TypeError", "message": "x"}]}) != [])
    check("no pageErrors key is silent, not an error",
          "uncaught-exception" not in rules(ok_page))
    check("an empty pageErrors list is silent",
          "uncaught-exception" not in rules({**ok_page, "pageErrors": []}))
    check("a console WARNING stays silent",
          "console-error" not in rules({**ok_page, "console": [{"level": "warning", "text": "meh"}]}),
          "warnings are noise in every real app; firing on them makes the rule unread")
    check("a failed request fires",
          "failed-request" in rules({**ok_page, "failedRequests": [{"url": "/a.js"}]}))

    # A SKIPPED ROUTE IS NOT A PASSING ROUTE.
    r = judge([{"route": "/admin", "skipped": "auth required"}])
    check("a skipped route is not judged clean", r.skipped and not r.findings, f"{r}")
    check("a skipped route is named", "auth required" in r.skipped[0], f"{r.skipped}")

    # ---- #108 item J: grouping repeats WITHOUT merging distinct defects ------------------
    F = Finding
    same = [F("/a", "console-error", "TypeError: x"), F("/b", "console-error", "TypeError: x"),
            F("/c", "console-error", "TypeError: x")]
    g = _grouped(same)
    check("three pages sharing one defect collapse to one group", len(g) == 1, f"{g}")
    check("the group keeps every route", g[0][1] == ["/a", "/b", "/c"], f"{g}")
    # THE FAILURE THAT WOULD MATTER: merging two defects that only share a rule name.
    diff = [F("/a", "console-error", "TypeError: x"), F("/b", "console-error", "RangeError: y")]
    check("same rule, different detail stays two groups", len(_grouped(diff)) == 2,
          f"{_grouped(diff)}")
    same_detail = [F("/a", "console-error", "boom"), F("/a", "uncaught-exception", "boom")]
    check("same detail, different rule stays two groups", len(_grouped(same_detail)) == 2,
          f"{_grouped(same_detail)}")
    # A route repeated within one rule (two console errors of the same text on one page) is one
    # page, not two -- otherwise "on 2 page(s)" would be a false claim about spread.
    dup = [F("/a", "console-error", "boom"), F("/a", "console-error", "boom")]
    check("one route counted once per group", _grouped(dup)[0][1] == ["/a"], f"{_grouped(dup)}")
    check("first-seen order is preserved, not sorted",
          [k[1] for k, _ in _grouped(diff)] == ["TypeError: x", "RangeError: y"], f"{_grouped(diff)}")
    check("no findings groups to nothing", _grouped([]) == [], f"{_grouped([])}")

    # AN UNUSABLE CRAWL IS NOT A CLEAN CRAWL -- three ways in.
    # THE COLLECTOR MUST EMIT EVERY FIELD THIS SCHEMA DECLARES. Object shorthand counts:
    # `{ route, status }` is the same as `route: route`.
    collector = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", collector.is_file(), f"{collector} is missing")
    if collector.is_file():
        js = collector.read_text(encoding="utf-8")
        missing = [f for f in SCHEMA_EXAMPLE["pages"][0]
                   if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing,
              f"{COLLECTOR} never emits {missing} — the rule reading it would go quiet")
        check("the collector stamps the schema tag", SCHEMA in js, f"{SCHEMA} absent")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for label, body in (("not json", "{["),
                            ("wrong schema", '{"schema": "other/1", "pages": [{}]}'),
                            ("no pages", f'{{"schema": "{SCHEMA}", "pages": []}}')):
            p = Path(tmp) / "c.json"
            p.write_text(body, encoding="utf-8")
            n += 1
            try:
                load(p)
                failures.append(f"{label}: expected UNUSABLE, got a parse")
            except Unusable:
                pass

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"crawl_report selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
