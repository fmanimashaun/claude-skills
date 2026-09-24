#!/usr/bin/env python3
"""Judge a crawl against the launch profile: a baseline for every app, plus a marketing set for an indexable one (#1289).

THE AXIS IS REACHABILITY, NOT AUDIENCE. An "internal" app is still on the public internet. So every
app gets the BASELINE: a <title> and a favicon on every page, and a reachable robots.txt that says
what the project decided about search engines. Only the marketing set is situational: a meta
description, a social preview (og:image) and a sitemap matter only for pages meant to be found. The
project DECLARES which it is, as `config.x.indexable`, and `/rails-flow:setup-flow` asks and records it.

  indexable = false  robots.txt must disallow indexing: `Disallow: /` for `User-agent: *`.
                     A reachable app with no such line is one a search engine can list, sign-in included.
  indexable = true   robots.txt must NOT disallow everything, and every page needs a description and
                     an og:image, and /sitemap.xml must be reachable.

Exit: 0 clean · 1 findings · 2 unusable (the crawl cannot be read, or predates the head/site probes,
      so it says nothing) · 3 undeclared (nobody decided; the baseline is still reported, never clean)

FACTS COME FROM THE COLLECTOR. `crawl_collector.js` records each page's `head` and a `site` block
(robots.txt status and body, sitemap.xml status, fetched signed out). This file only decides, and it
reads the crawl through `crawl_report.load`, so there is one reader.

Not judged here: the privacy policy, terms and cookie consent, which `/rails-flow:setup-flow` drafts
from the app's data inventory and country of operation; and spam protection, which is a request-spec
concern (`rails-8` `auth-security.md` → Unauthenticated endpoints).

Run:  launch_readiness.py qa/manual-tests/crawl.json [--root DIR]
      launch_readiness.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_report import Unusable, load  # noqa: E402  -- one crawl reader, not two
from qa_config import load_section  # noqa: E402  -- one qa.config.yml reader, not two

DECL = re.compile(r"\bconfig\.x\.indexable\s*=\s*(true|false)\b")
BASELINE = (
    ("launch-title-missing", lambda h, p: bool((p.get("title") or "").strip()), "the page has no <title>"),
    ("launch-favicon-missing", lambda h, p: bool(h.get("favicon")), 'no <link rel="icon">'),
)
MARKETING = (
    ("launch-description-missing", lambda h, p: bool(h.get("description")), 'no <meta name="description">'),
    ("launch-og-image-missing", lambda h, p: bool(h.get("ogImage")), 'no <meta property="og:image"> (social preview)'),
)
NOTE = ("NOTE: not judged here -- the privacy policy, terms and cookie consent (setup-flow drafts them from "
        "this app's data inventory and country of operation, for legal review) and spam protection on "
        "unauthenticated endpoints (request specs).")


def declared(root: Path) -> bool | None:
    """`True`/`False` as the project declared it, or `None` when it never did."""
    for f in [root / "config" / "application.rb", *sorted((root / "config" / "initializers").glob("*.rb"))]:
        if f.is_file():
            m = DECL.search(f.read_text(encoding="utf-8"))
            if m:
                return m.group(1) == "true"
    return None


def disallows_all(robots: str) -> bool:
    """Whether the `User-agent: *` group carries `Disallow: /` -- the whole site, not a path."""
    agent, groups = None, {}
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            agent = value
            groups.setdefault(agent, [])
        elif field == "disallow" and agent is not None:
            groups[agent].append(value)
    return "/" in groups.get("*", [])


def health_path(root: Path) -> str | None:
    """The declared health endpoint (`app: health:` in qa/qa.config.yml), or None (#1297).

    Rails serves `/up` as a bare HTML status page with no <head>, so judged as a page it "lacks" a
    title and a favicon. It is not a page: `smoke` and `crawl` already read this same key.
    """
    value = load_section(root / "qa" / "qa.config.yml", "app").get("health")
    return value.strip() if isinstance(value, str) and value.strip() else None


def judge(data: dict, pages: list[dict], indexable: bool | None,
          health: str | None = None) -> list[tuple[str, str, str]]:
    """`(rule, where, detail)` findings. Raises Unusable when the crawl carries no launch facts."""
    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200 and p.get("route") != health
            and "html" in (p.get("contentType") or "text/html")]
    if not html:
        raise Unusable("no 200 HTML page was crawled, so nothing about a launch can be judged")
    if any("head" not in p for p in html) or not isinstance(data.get("site"), dict):
        raise Unusable("this crawl has no head/site facts -- it predates #1289. Re-run the crawl with "
                       "the current crawl_collector.js; an old crawl is not a clean launch")
    site = data.get("site") or {}
    rules = BASELINE + (MARKETING if indexable else ())
    findings = []
    for p in html:
        for rule, ok, detail in rules:
            if not ok(p.get("head") or {}, p):
                findings.append((rule, p["route"], detail))
    robots = site.get("robots")
    if robots != 200:
        findings.append(("launch-robots-unreachable", "/robots.txt",
                         f"returned {robots}" if robots is not None else "could not be fetched"))
    elif indexable is False and not disallows_all(site.get("robotsBody") or ""):
        findings.append(("launch-robots-allows-indexing", "/robots.txt",
                         "the app is declared not indexable, but `User-agent: *` has no `Disallow: /`, "
                         "so a search engine may list it"))
    elif indexable is True and disallows_all(site.get("robotsBody") or ""):
        findings.append(("launch-robots-blocks-indexing", "/robots.txt",
                         "the app is declared indexable, but `User-agent: *` disallows `/`"))
    if indexable:
        sitemap = site.get("sitemap")
        if sitemap != 200:
            findings.append(("launch-sitemap-unreachable", "/sitemap.xml",
                             f"returned {sitemap}" if sitemap is not None else "could not be fetched"))
    return findings


def run(crawl: Path, root: Path) -> tuple[int, list[str]]:
    indexable = declared(root)
    try:
        pages = load(crawl)
        data = json.loads(crawl.read_text(encoding="utf-8"))
        findings = judge(data, pages, indexable, health_path(root))
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    lines = [f"  [{rule}] {where} -- {detail}" for rule, where, detail in findings]
    if indexable is None:
        return 3, ["UNDECLARED: this project never said whether search engines should index it. Run "
                   "/rails-flow:setup-flow, which records `config.x.indexable = true|false`. Baseline findings "
                   "(robots.txt content is not judged until it is declared):", *lines, NOTE]
    lines.append(NOTE)
    if findings:
        return 1, [f"{len(findings)} launch finding(s):", *lines]
    scope = "baseline and marketing set" if indexable else "baseline, and robots.txt disallows indexing"
    return 0, [f"launch profile clean ({scope})", NOTE]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="launch_readiness.py", description=__doc__.splitlines()[0])
    ap.add_argument("crawl", nargs="?", type=Path)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.crawl:
        ap.error("a crawl.json is required (or --selftest)")
    code, lines = run(a.crawl, a.root.resolve())
    print("\n".join(lines))
    return code


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    fails: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    full = {"description": "Plans", "ogImage": "/og.png", "favicon": True}
    closed = "User-agent: *\nDisallow: /\n"
    open_ = "User-agent: *\nDisallow: /admin\n"

    def page(route="/", **over):
        p = {"route": route, "status": 200, "contentType": "text/html", "title": "Home",
             "h1": "Home", "head": dict(full), "skipped": None}
        p.update(over)
        return p

    def crawl_file(tmp: Path, pages: list[dict], site=None) -> Path:
        doc = {"schema": "qa-flow/route-crawl/1", "pages": pages}
        if site is not False:
            doc["site"] = site if site is not None else {"robots": 200, "robotsBody": closed, "sitemap": 200}
        f = tmp / "crawl.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        return f

    def project(tmp: Path, value: str | None) -> Path:
        (tmp / "config" / "initializers").mkdir(parents=True, exist_ok=True)
        if value is not None:
            (tmp / "config" / "initializers" / "launch.rb").write_text(
                f"Rails.application.configure do\n  config.x.indexable = {value}\nend\n", encoding="utf-8")
        return tmp

    check("robots: `Disallow: /` under `*` disallows all", disallows_all(closed))
    check("robots: a path-only Disallow does not", not disallows_all(open_))
    check("robots: `Disallow: /` under another agent does not",
          not disallows_all("User-agent: Googlebot\nDisallow: /\n\nUser-agent: *\nDisallow:\n"))
    check("robots: comments and case are ignored", disallows_all("user-agent: * # all\nDISALLOW: / # none\n"))

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        internal = project(t / "internal", "false")
        public = project(t / "public", "true")
        undeclared = project(t / "undeclared", None)

        # --- NOT INDEXABLE: the baseline only, and robots must close the site.
        bare = {"description": "", "ogImage": "", "favicon": True}
        c = crawl_file(t, [page(head=bare), page("/tasks", head=bare)])
        code, out = run(c, internal)
        check("CONTROL: a non-indexable app needs no description or og:image, and is clean", code == 0, f"{code} {out}")
        c = crawl_file(t, [page()], site={"robots": 200, "robotsBody": open_, "sitemap": 404})
        code, out = run(c, internal)
        check("non-indexable, robots allows indexing: a finding",
              code == 1 and any("launch-robots-allows-indexing" in l for l in out), f"{out}")
        check("...and no sitemap is demanded of it", not any("sitemap" in l for l in out), f"{out}")
        c = crawl_file(t, [page(head={**full, "favicon": False}), page("/x", title="")])
        code, out = run(c, internal)
        check("the baseline (title, favicon) applies to a non-indexable app too",
              any("launch-favicon-missing] /" in l for l in out) and any("launch-title-missing] /x" in l for l in out), f"{out}")

        # --- INDEXABLE: the marketing set joins the baseline.
        c = crawl_file(t, [page(), page("/pricing")], site={"robots": 200, "robotsBody": open_, "sitemap": 200})
        code, out = run(c, public)
        check("CONTROL: a complete indexable crawl is clean", code == 0, f"{code} {out}")
        c = crawl_file(t, [page(), page("/pricing", head={**full, "ogImage": ""})],
                       site={"robots": 200, "robotsBody": open_, "sitemap": 200})
        code, out = run(c, public)
        check("indexable, a page with no og:image: a finding naming the route",
              code == 1 and any("launch-og-image-missing] /pricing" in l for l in out), f"{out}")
        c = crawl_file(t, [page(head={**full, "description": ""})], site={"robots": 200, "robotsBody": open_, "sitemap": 200})
        check("indexable, no description: a finding", any("launch-description-missing" in l for l in run(c, public)[1]))
        c = crawl_file(t, [page()], site={"robots": 200, "robotsBody": closed, "sitemap": None})
        code, out = run(c, public)
        check("indexable, robots closes the site and the sitemap is unfetchable: both findings",
              any("launch-robots-blocks-indexing" in l for l in out)
              and any("launch-sitemap-unreachable] /sitemap.xml -- could not be fetched" in l for l in out), f"{out}")

        # --- robots missing, for either declaration.
        c = crawl_file(t, [page()], site={"robots": 404, "sitemap": 200})
        check("robots.txt 404 is a finding even for a non-indexable app",
              any("launch-robots-unreachable] /robots.txt -- returned 404" in l for l in run(c, internal)[1]))

        # --- Not judged: error and skipped pages.
        c = crawl_file(t, [page(), page("/boom", status=500, head={}), page("/gone", skipped="timeout")])
        check("a 500 or skipped page is not judged for head tags", run(c, internal)[0] == 0, str(run(c, internal)))

        # --- UNUSABLE, never clean.
        old = page()
        del old["head"]
        c = crawl_file(t, [old], site=False)
        check("a crawl that predates the probes is UNUSABLE (exit 2), not clean", run(c, internal)[0] == 2)
        c = crawl_file(t, [page(status=500)])
        check("a crawl with no 200 HTML page is UNUSABLE", run(c, internal)[0] == 2)

        # --- UNDECLARED: exit 3 even when the baseline is clean, and the baseline is still reported.
        c = crawl_file(t, [page()])
        code, out = run(c, undeclared)
        check("undeclared: exit 3, never 0, even on a clean baseline", code == 3 and "UNDECLARED" in out[0], f"{code} {out}")
        c = crawl_file(t, [page(title="")])
        code, out = run(c, undeclared)
        check("undeclared: the baseline findings are still listed", any("launch-title-missing" in l for l in out), f"{out}")

        # --- #1297: the declared health endpoint is not a page. Same bare page, two routes.
        bodiless = {"description": "", "ogImage": "", "favicon": False}
        c = crawl_file(t, [page(), page("/up", title="", head=bodiless)])
        declared_up = project(t / "declared-up", "false")
        (declared_up / "qa").mkdir()
        (declared_up / "qa" / "qa.config.yml").write_text(
            "app:\n  start: bin/dev\n  health:       /up        # 200-when-ready\n", encoding="utf-8")
        code, out = run(c, declared_up)
        check("a declared health path is not judged as a page", code == 0, f"{code} {out}")
        check("CONTROL: the same bare page on an undeclared project is a finding",
              any("launch-title-missing] /up" in l for l in run(c, internal)[1]), str(run(c, internal)))
        c = crawl_file(t, [page(), page("/status", title="", head=bodiless)])
        check("...and a bare page on another route still fails when /up is declared",
              any("launch-title-missing] /status" in l for l in run(c, declared_up)[1]), str(run(c, declared_up)))

        # --- THE ENTRY POINT: main returns run's code.
        c = crawl_file(t, [page()], site={"robots": 200, "robotsBody": open_, "sitemap": 200})
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main([str(c), "--root", str(internal)])
        check("main returns the judgement's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"launch_readiness selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
