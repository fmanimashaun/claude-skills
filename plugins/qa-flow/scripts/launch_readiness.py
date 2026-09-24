#!/usr/bin/env python3
"""Judge a crawl against the "public launch" profile, for a project that declared itself public-facing (#1289).

WHY IT IS SITUATIONAL. A public website needs a title, a description and a social preview on every
page, a favicon, and a reachable robots.txt and sitemap. An internal platform needs none of them,
and demanding them everywhere is the false positive that gets a check switched off. So the project
DECLARES which it is, in `config.x.public_launch`, and `/rails-flow:setup-flow` asks and records it.
That gives the four honest states a situational rule needs (see `check_i18n_setup.py`, #799):

  exit 0  clean, or not applicable because the project declared `config.x.public_launch = false`
  exit 1  public-facing, and at least one page or site file is missing what a launch needs
  exit 2  unusable: the crawl cannot be read, or it predates the head/site probes, so it says nothing
  exit 3  undeclared: nobody has decided, which is different from "internal" and never reported clean

FACTS COME FROM THE COLLECTOR. `crawl_collector.js` records each page's `head` (description,
og:image, favicon) and a `site` block (robots.txt, sitemap.xml status from a signed-out context).
This file only decides. It reads the crawl through `crawl_report.load`, so there is one reader.

Privacy policy, terms and cookie consent are NOT judged here. Their content is legal and
jurisdiction-specific; the profile flags them for legal review and never generates them.

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

DECL = re.compile(r"\bconfig\.x\.public_launch\s*=\s*(true|false)\b")
PAGE_RULES = (
    ("launch-title-missing", lambda h, p: bool((p.get("title") or "").strip()), "the page has no <title>"),
    ("launch-description-missing", lambda h, p: bool(h.get("description")), 'no <meta name="description">'),
    ("launch-og-image-missing", lambda h, p: bool(h.get("ogImage")), 'no <meta property="og:image"> (social preview)'),
    ("launch-favicon-missing", lambda h, p: bool(h.get("favicon")), 'no <link rel="icon">'),
)
SITE_FILES = (("robots", "/robots.txt"), ("sitemap", "/sitemap.xml"))
NOTE = ("NOTE: privacy policy, terms and cookie consent are not checked here -- their content is legal "
        "and jurisdiction-specific. Have them reviewed before launch.")


def declared(root: Path) -> bool | None:
    """`True`/`False` as the project declared it, or `None` when it never did."""
    for f in [root / "config" / "application.rb", *sorted((root / "config" / "initializers").glob("*.rb"))]:
        if f.is_file():
            m = DECL.search(f.read_text(encoding="utf-8"))
            if m:
                return m.group(1) == "true"
    return None


def judge(data: dict, pages: list[dict]) -> list[tuple[str, str, str]]:
    """`(rule, where, detail)` findings. Raises Unusable when the crawl carries no launch facts."""
    html = [p for p in pages if not p.get("skipped") and p.get("status") == 200
            and "html" in (p.get("contentType") or "text/html")]
    if not html:
        raise Unusable("no 200 HTML page was crawled, so nothing about a launch can be judged")
    if any("head" not in p for p in html) or not isinstance(data.get("site"), dict):
        raise Unusable("this crawl has no head/site facts -- it predates #1289. Re-run the crawl with "
                       "the current crawl_collector.js; an old crawl is not a clean launch")
    findings = []
    for p in html:
        for rule, ok, detail in PAGE_RULES:
            if not ok(p.get("head") or {}, p):
                findings.append((rule, p["route"], detail))
    for key, path in SITE_FILES:
        status = (data.get("site") or {}).get(key)
        if status != 200:
            findings.append((f"launch-{key}-unreachable", path,
                             f"returned {status}" if status is not None else "could not be fetched"))
    return findings


def run(crawl: Path, root: Path) -> tuple[int, list[str]]:
    public = declared(root)
    if public is None:
        return 3, ["UNDECLARED: this project never said whether it is public-facing. Run "
                   "/rails-flow:setup-flow, which records `config.x.public_launch = true|false`."]
    if public is False:
        return 0, ["not applicable: the project declared `config.x.public_launch = false` (internal)"]
    try:
        pages = load(crawl)
        data = json.loads(crawl.read_text(encoding="utf-8"))
        findings = judge(data, pages)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    lines = [f"  [{rule}] {where} -- {detail}" for rule, where, detail in findings]
    lines.append(NOTE)
    if findings:
        return 1, [f"{len(findings)} launch finding(s):", *lines]
    return 0, ["every crawled page has a title, description, og:image and favicon; robots.txt and "
               "sitemap.xml are reachable", NOTE]


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
    import tempfile

    fails: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    good_head = {"description": "Plans", "ogImage": "/og.png", "favicon": True}

    def page(route="/", **over):
        p = {"route": route, "status": 200, "contentType": "text/html", "title": "Home",
             "h1": "Home", "head": dict(good_head), "skipped": None}
        p.update(over)
        return p

    def crawl_file(tmp: Path, pages: list[dict], site=None) -> Path:
        doc = {"schema": "qa-flow/route-crawl/1", "pages": pages}
        if site is not False:
            doc["site"] = site if site is not None else {"robots": 200, "sitemap": 200}
        f = tmp / "crawl.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        return f

    def project(tmp: Path, value: str | None) -> Path:
        (tmp / "config" / "initializers").mkdir(parents=True, exist_ok=True)
        if value is not None:
            (tmp / "config" / "initializers" / "launch.rb").write_text(
                f"Rails.application.configure do\n  config.x.public_launch = {value}\nend\n", encoding="utf-8")
        return tmp

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        root = project(t / "app", "true")
        c = crawl_file(t, [page(), page("/pricing")])
        code, out = run(c, root)
        check("CONTROL: a complete public crawl is clean", code == 0, f"{code} {out}")

        c = crawl_file(t, [page(), page("/pricing", head={**good_head, "ogImage": ""})])
        code, out = run(c, root)
        check("a page with no og:image is a finding naming the route",
              code == 1 and any("launch-og-image-missing] /pricing" in l for l in out), f"{out}")
        c = crawl_file(t, [page(head={**good_head, "description": ""}), page("/x", title="")])
        code, out = run(c, root)
        check("a missing description and a missing title are both reported",
              any("launch-description-missing] /" in l for l in out) and any("launch-title-missing] /x" in l for l in out),
              f"{out}")
        c = crawl_file(t, [page(head={**good_head, "favicon": False})])
        check("no favicon is a finding", any("launch-favicon-missing" in l for l in run(c, root)[1]))
        c = crawl_file(t, [page()], site={"robots": 404, "sitemap": None})
        code, out = run(c, root)
        check("robots 404 and an unfetchable sitemap are both findings",
              code == 1 and any("launch-robots-unreachable] /robots.txt -- returned 404" in l for l in out)
              and any("launch-sitemap-unreachable] /sitemap.xml -- could not be fetched" in l for l in out),
              f"{out}")
        # A skipped or non-200 page is not judged: an error page has no head to demand.
        c = crawl_file(t, [page(), page("/boom", status=500, head={}), page("/gone", skipped="timeout")])
        check("a 500 or skipped page is not judged for head tags", run(c, root)[0] == 0, str(run(c, root)))

        # UNUSABLE, never clean: an old crawl without the probes.
        old = page()
        del old["head"]
        c = crawl_file(t, [old], site=False)
        code, out = run(c, root)
        check("a crawl that predates the probes is UNUSABLE (exit 2), not clean", code == 2, f"{code} {out}")
        c = crawl_file(t, [page(status=500)])
        check("a crawl with no 200 HTML page is UNUSABLE", run(c, root)[0] == 2)

        # THE FOUR STATES, on the same failing crawl, so only the declaration differs.
        bad = crawl_file(t, [page(head={**good_head, "ogImage": ""})])
        check("declared public: the failing crawl exits 1", run(bad, root)[0] == 1)
        internal = project(t / "internal", "false")
        code, out = run(bad, internal)
        check("declared internal: not applicable, exit 0", code == 0 and "not applicable" in out[0], f"{out}")
        undeclared = project(t / "undeclared", None)
        code, out = run(bad, undeclared)
        check("undeclared: exit 3, never 0", code == 3 and "UNDECLARED" in out[0], f"{code} {out}")

        # THE ENTRY POINT: main returns run's code.
        rc = main([str(bad), "--root", str(root)])
        check("main returns the judgement's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"launch_readiness selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
