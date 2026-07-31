#!/usr/bin/env python3
"""Prove route enumeration and coverage attribution are right -- in both directions.

Run:  python3 route_coverage.py --selftest   (or execute this file directly)

A coverage number is believed without being checked, which makes over-crediting the dangerous
failure: a tool that reports 100% while nothing visited `/users/:id/edit` is worse than no tool,
because it retires the question. So the fixtures attack the OVER-credit direction hardest --
segment counts, trailing slashes, format suffixes, and the deliberate refusal to count a
deduplicated finding's example routes as visits.

Stdlib + the sibling modules only; no network, no browser.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import route_coverage as rc  # noqa: E402
import validate_evidence as ve  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def check(label: str, got, want) -> None:
    _tick()
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


def matches(pattern: str, path: str) -> bool:
    return bool(rc.compile_pattern(pattern).match(path))


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="qaflow-routes-"))


RAILS = """                                   Prefix Verb   URI Pattern                     Controller#Action
                                     root GET    /                               home#index
                                    users GET    /users(.:format)                users#index
                                          POST   /users(.:format)                users#create
                                 edit_user GET    /users/:id/edit(.:format)      users#edit
                                     user GET    /users/:id(.:format)            users#show
                                          DELETE /users/:id(.:format)            users#destroy
                            admin_reports GET    /admin/reports(.:format)        admin/reports#index
                               rails_health GET  /up(.:format)                   rails/health#show
"""


def run() -> int:
    # ---- enumeration: Rails ------------------------------------------------------------
    routes = rc.from_rails(RAILS)
    check("rails: route count", len(routes), 8)
    check("rails: no (.:format) survives anywhere",
          [r.pattern for r in routes if "format" in r.pattern], [])
    check("rails: patterns", "/users/:id/edit" in {r.pattern for r in routes}, True)
    check("rails: verbs captured", sorted({r.verb for r in routes}), ["DELETE", "GET", "POST"])
    check("rails: namespace becomes the area",
          next(r.area for r in routes if r.controller == "admin/reports#index"), "admin")
    check("rails: non-GET is destructive",
          sorted({r.verb for r in routes if r.destructive}), ["DELETE", "POST"])
    # The header line must not become a route -- it matches the shape of one loosely.
    _tick()
    if any("Pattern" in r.pattern for r in routes):
        FAILURES.append("rails: the header row was parsed as a route")

    # ---- enumeration: sitemap ----------------------------------------------------------
    sitemap = ("<urlset><url><loc>https://x.test/</loc></url>"
               "<url><loc>https://x.test/about/</loc></url>"
               "<url><loc>https://x.test/docs/intro</loc></url></urlset>")
    sm = rc.from_sitemap(sitemap)
    check("sitemap: host stripped, trailing slash normalised",
          sorted(r.pattern for r in sm), ["/", "/about", "/docs/intro"])
    check("sitemap: everything is GET", {r.verb for r in sm}, {"GET"})

    # ---- enumeration: filesystem -------------------------------------------------------
    fs = _tmp()
    (fs / "docs").mkdir(parents=True)
    (fs / "index.html").write_text("x", encoding="utf-8")
    (fs / "about.html").write_text("x", encoding="utf-8")
    (fs / "docs" / "[slug].html").write_text("x", encoding="utf-8")
    (fs / "docs" / "[...rest].html").write_text("x", encoding="utf-8")
    (fs / "ignore.txt").write_text("x", encoding="utf-8")
    got = sorted(r.pattern for r in rc.from_fs(fs))
    check("fs: index -> /, [slug] -> :slug, [...rest] -> *glob, non-page ignored",
          got, ["/", "/about", "/docs/*glob", "/docs/:slug"])

    # ---- normalisation: one spelling per route ----------------------------------------
    check("normalise: trailing slash", rc.normalise("/about/"), "/about")
    check("normalise: root keeps its slash", rc.normalise("/"), "/")
    check("normalise: format suffix", rc.normalise("/users(.:format)"), "/users")
    check("normalise: query dropped", rc.normalise("/search?q=x"), "/search")
    check("normalise: fragment dropped", rc.normalise("/docs#intro"), "/docs")

    # ---- matching: THE over-credit guard ---------------------------------------------
    # `:id` is ONE segment. If it matched greedily, /users/:id would claim coverage for
    # /users/42/edit -- a different action, and the report would say tested when it is not.
    check("match: :id matches one segment", matches("/users/:id", "/users/42"), True)
    check("match: :id does NOT swallow a deeper path",
          matches("/users/:id", "/users/42/edit"), False)
    check("match: nested dynamic route", matches("/users/:id/edit", "/users/42/edit"), True)
    check("match: *glob does swallow the rest", matches("/docs/*glob", "/docs/a/b/c"), True)
    check("match: static is exact", matches("/about", "/aboutus"), False)
    check("match: root matches only root", matches("/", "/"), True)
    check("match: root does not match everything", matches("/", "/about"), False)
    check("match: trailing slash tolerated on the visit",
          matches("/about", "/about/"), True)

    # ---- attribution from validated evidence ------------------------------------------
    ev = _tmp()
    (ev / "2026-07-30-x-summary.csv").write_text(
        ve.FUNCTIONAL.header + "\n"
        "TC-1,Home,Nav,Pass,200,https://x.test/,https://x.test/,heading 'Home',,\n",
        encoding="utf-8",
    )
    (ev / "2026-07-30-x-runtime.csv").write_text(
        ve.RUNTIME.header + "\n"
        "/users/42/edit,anon,Observed,200,https://x.test/users/42/edit,"
        "https://x.test/users/42/edit,heading 'Edit',0,0,0,0,0,none,0,,\n",
        encoding="utf-8",
    )
    # The keyboard (#114) and forms (#115) passes visit real routes, so they must earn coverage
    # like any other pass. Wiring them into ROUTE_SOURCES is otherwise an untested claim: the
    # "every profile is classified" check below proves they were not FORGOTTEN, not that
    # attribution actually reads them.
    (ev / "2026-07-30-x-keyboard.csv").write_text(
        ve.KEYBOARD.header + "\n"
        "/admin/reports,signed-in,Walked,200,https://x.test/admin/reports,"
        "https://x.test/admin/reports,heading 'Reports',chromium,9,9,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        encoding="utf-8",
    )
    (ev / "2026-07-30-x-forms.csv").write_text(
        ve.FORMS.header + "\n"
        "new-user,/users,Exercised,200,https://x.test/users,https://x.test/users,"
        "heading 'Users',4,0,0,dry-run,Not run,Not run,Not run,Not run,Not run,none,,\n",
        encoding="utf-8",
    )
    seen = rc.visited_paths([ev])
    check("attribution: paths collected from every per-page artifact",
          sorted(seen), ["/", "/admin/reports", "/users", "/users/42/edit"])
    # `.get` rather than `[]` deliberately: when a profile is dropped from ROUTE_SOURCES the path
    # is absent from `seen` entirely, and indexing would raise KeyError -- reporting a crash
    # instead of the defect, and letting an unrelated assertion take the credit for catching it.
    _tick()
    if not any("keyboard:" in s for s in seen.get("/admin/reports", ())):
        FAILURES.append("attribution: the keyboard walk was not credited")
    _tick()
    if not any("forms:" in s for s in seen.get("/users", ())):
        FAILURES.append("attribution: the forms pass was not credited")
    _tick()
    if not any("functional:" in s for s in seen["/"]):
        FAILURES.append("attribution: the functional artifact was not credited")

    cov = {c.route.key: c for c in rc.attribute(rc.from_rails(RAILS), seen)}
    check("attribution: root covered", cov["GET /"].covered, True)
    check("attribution: /users/:id/edit covered", cov["GET /users/:id/edit"].covered, True)
    # The same visit must NOT credit the sibling show route -- this is the over-credit case
    # again, now end to end rather than at the regex.
    check("attribution: /users/:id NOT covered by a visit to /users/42/edit",
          cov["GET /users/:id"].covered, False)
    check("attribution: never-visited route uncovered", cov["DELETE /users/:id"].covered, False)
    check("attribution: names which artifact covered it",
          any("runtime:" in a for a in cov["GET /users/:id/edit"].by), True)

    # ---- a findings rollup must never be counted as visits ---------------------------
    # Its Example Routes are up to three examples of a deduped defect. Counting them would
    # credit coverage for routes nobody opened -- inflating the exact number this makes honest.
    ev2 = _tmp()
    (ev2 / "findings.csv").write_text(
        ve.FINDINGS.header + "\n"
        "nav/x,a11y,Confirmed,S1,Thing,9,3,/ /about /docs/intro,qa/reports/f.json,note\n",
        encoding="utf-8",
    )
    check("findings rollup contributes no coverage", rc.visited_paths([ev2]), {})
    # ...and that exclusion is deliberate, not an oversight: every profile must be classified.
    _tick()
    classified = set(rc.ROUTE_SOURCES) | set(rc.ROUTE_LESS)
    unclassified = {p.name for p in ve.PROFILES} - classified
    if unclassified:
        FAILURES.append(
            f"evidence profiles neither credited nor explicitly route-less: {sorted(unclassified)}"
            " -- a new pass would silently contribute no coverage and understate the gap"
        )
    _tick()
    overlap = set(rc.ROUTE_SOURCES) & set(rc.ROUTE_LESS)
    if overlap:
        FAILURES.append(f"profiles both credited and route-less: {sorted(overlap)}")
    # Every column named as a URL source must exist on that profile, or attribution silently
    # reads nothing and every route looks untested.
    for name, columns in rc.ROUTE_SOURCES.items():
        _tick()
        profile = next((p for p in ve.PROFILES if p.name == name), None)
        if profile is None:
            FAILURES.append(f"ROUTE_SOURCES names unknown profile {name!r}")
            continue
        missing = [c for c in columns if c not in profile.columns]
        if missing:
            FAILURES.append(f"{name}: ROUTE_SOURCES names columns it does not have: {missing}")

    # ---- 'Out of Scope' rows are not visits -----------------------------------------
    ev3 = _tmp()
    (ev3 / "s-summary.csv").write_text(
        ve.FUNCTIONAL.header + "\n"
        "TC-9,Skipped,Nav,Out of Scope,,https://x.test/secret,,,,not in scope\n",
        encoding="utf-8",
    )
    check("out-of-scope row credits no coverage", rc.visited_paths([ev3]), {})

    # ---- exclusions: applied, and always visible ------------------------------------
    all_routes = rc.from_rails(RAILS)
    kept, dropped = rc.excluded(all_routes, ["/up"])
    check("exclusions: health endpoint dropped", [r.pattern for r in dropped], ["/up"])
    check("exclusions: the rest kept", len(kept), len(all_routes) - 1)
    check("exclusions: none declared drops nothing", rc.excluded(all_routes, [])[1], [])
    # NEAR MISS: an exclusion is a substring match, so it must be narrow enough to be stated
    # deliberately -- `/users` must not silently take `/users/:id/edit` unless asked.
    _tick()
    _, wide = rc.excluded(all_routes, ["/admin"])
    if {r.pattern for r in wide} != {"/admin/reports"}:
        FAILURES.append(f"exclusions: '/admin' dropped {sorted(r.pattern for r in wide)}")

    # ---- gap ordering: destructive, then authenticated, then the rest ----------------
    gaps = sorted(
        (c for c in rc.attribute(all_routes, {}) if not c.covered),
        key=lambda c: rc.priority(c, ["/admin"]),
    )
    check("gap order: a non-GET route comes first", gaps[0].route.destructive, True)
    _tick()
    verbs = [c.route.destructive for c in gaps]
    if verbs != sorted(verbs, reverse=True):
        FAILURES.append("gap order: destructive routes are not all ahead of GET routes")
    _tick()
    first_get = next(c for c in gaps if not c.route.destructive)
    if not first_get.route.pattern.startswith("/admin"):
        FAILURES.append(
            "gap order: among GET routes the authenticated one must rank first, got "
            f"{first_get.route.key}"
        )

    # ---- config parsing: the coverage block only ------------------------------------
    cfg = _tmp() / "qa.config.yml"
    cfg.write_text(
        "base_url: env:QA_BASE_URL\n"
        "coverage:\n"
        "  exclude:\n"
        "    - /up            # health endpoint\n"
        "    - rails/active_storage\n"
        "  authenticated_prefixes:\n"
        "    - /admin\n"
        "web_e2e: playwright\n",
        encoding="utf-8",
    )
    parsed = rc.load_config(cfg)
    check("config: exclusions read, comments stripped",
          parsed.get("exclude"), ["/up", "rails/active_storage"])
    check("config: auth prefixes read", parsed.get("authenticated_prefixes"), ["/admin"])
    _tick()
    if "web_e2e" in parsed:
        FAILURES.append("config: keys outside the coverage block leaked in")
    check("config: absent file yields no config", rc.load_config(_tmp() / "nope.yml"), {})
    empty = _tmp() / "empty.yml"
    empty.write_text("coverage:\n  exclude: []\n  authenticated_prefixes: []\n", encoding="utf-8")
    check("config: `exclude: []` parses as declared-and-empty, not missing",
          rc.load_config(empty), {"exclude": [], "authenticated_prefixes": []})

    # ---- end to end: enumerate -> report, with the trend appended -------------------
    work = _tmp()
    routes_json = work / "routes.json"
    routes_json.write_text(json.dumps({"routes": [
        {"verb": "GET", "pattern": "/", "controller": "home#index", "area": "home"},
        {"verb": "DELETE", "pattern": "/users/:id", "controller": "users#destroy", "area": "users"},
    ]}) + "\n", encoding="utf-8")
    trend = work / "trend.jsonl"
    import argparse as _a

    args = _a.Namespace(routes=str(routes_json), evidence=[str(ev)], config=str(cfg),
                        trend=str(trend), json=False, fail_on_untested=False)
    import contextlib, io

    _tick()
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        rc_exit = rc.cmd_report(args)
    if rc_exit != 0:
        FAILURES.append("report: a gap is the deliverable, not a failure -- exit must be 0")
    shown = captured.getvalue()
    # The gap report must NAME the untested route and say why it ranks first, or it is a number
    # nobody can act on -- and the excluded count must print even when it is zero.
    for expected in ("DELETE /users/:id", "non-GET", "excluded by config: 0"):
        _tick()
        if expected not in shown:
            FAILURES.append(f"report: output omits {expected!r}\n{shown}")
    args.fail_on_untested = True
    _tick()
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args) != 1:
            FAILURES.append("report: --fail-on-untested must exit 1 while a gap remains")
    _tick()
    lines = [json.loads(x) for x in trend.read_text(encoding="utf-8").splitlines()]
    if len(lines) != 2:
        FAILURES.append(f"trend: expected 2 appended runs, got {len(lines)}")
    elif lines[0] != {"routes": 2, "covered": 1, "untested": 1, "excluded": 0, "percent": 50}:
        FAILURES.append(f"trend: wrong arithmetic recorded: {lines[0]}")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"route_coverage selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
