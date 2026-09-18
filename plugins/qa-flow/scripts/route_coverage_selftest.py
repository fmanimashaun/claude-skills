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
import os
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
                                 requests GET    /requests(.:format)             placeholders#show {screen: "All requests", feature: "F-06"}
"""


def _stale(prov, head, label):
    """`stale_inventory`, with an exception recorded as a FAILURE instead of killing the run.

    A mutation that bypasses the guard clause leaves `head` None on a path that then slices it, so
    the selftest died with a TypeError before printing anything -- and the mutation harness then
    reported the break as "caught, but not by the expected fixture", because the fixture that
    SHOULD have named it never got to print. A crash is not a verdict; it has to fail as a value.
    """
    try:
        return rc.stale_inventory(prov, head=head)
    except Exception as exc:                                   # noqa: BLE001 -- any break, reported
        FAILURES.append(f"stale_inventory raised on {label}: {type(exc).__name__}: {exc}")
        return None


def _json_payload(text: str) -> dict:
    """The `--json` object a captured cmd_report printed, or {} when it printed none.

    Every call site used `text[text.index("{"):]` directly, which raises ValueError when
    cmd_report REFUSED and printed nothing -- so a mutation that makes it refuse killed the
    selftest with a traceback instead of failing an assertion. A crash is not a verdict, and the
    mutation harness rejects a fixture that dies rather than failing. Three separate sites hit
    this in turn while #1047 was being written, which is why it is a helper and not a third
    inline guard.
    """
    return json.loads(text[text.index("{"):]) if "{" in text else {}


def run() -> int:
    # ---- enumeration: Rails ------------------------------------------------------------
    routes = rc.from_rails(RAILS)
    check("rails: route count", len(routes), 9)
    # THE 45% SILENT DROP (#953). Rails prints a route's `defaults:` AFTER the controller, and the
    # parser required the controller to be the last token — so on a real app 64 of 143 verb-bearing
    # rows vanished and route coverage reported "49/49 (100%)" over a denominator that contained
    # none of the pages the defects were found on.
    check("rails: a row with a defaults hash is parsed",
          "/requests" in {r.pattern for r in routes}, True)
    check("rails: the defaults hash does not leak into the controller",
          next((r.controller for r in routes if r.pattern == "/requests"), "(route missing)"),
          "placeholders#show")
    # AND THE SILENCE IS THE DEFECT, not the regex. A verb-bearing row nobody can parse must be
    # reported, or the next format change is another 45% drop with a confident percentage on top.
    check("rails: nothing in the fixture is left unparsed", rc.unparsed_rails_rows(RAILS), [])
    _tick()
    # A trailing column the parser does not know — the shape a future Rails format change takes,
    # and the shape that dropped 64 rows last time. NOT a bad controller token: `\S+` would happily
    # accept that and call the row parsed, which is the near miss this fixture had on its first
    # draft.
    broken = RAILS + ("                                 weird GET    /weird(.:format)"
                      "   placeholders#show trailing column\n")
    if len(rc.unparsed_rails_rows(broken)) != 1:
        FAILURES.append(f"an unparseable verb row must be reported: "
                        f"{rc.unparsed_rails_rows(broken)}")
    _tick()
    if rc.unparsed_rails_rows(broken) and "weird" not in rc.unparsed_rails_rows(broken)[0]:
        FAILURES.append("the unparsed row must be quoted, so the format change is visible")
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

    # ---- THE VERB DECIDES, NOT JUST THE PATH (#1037) -----------------------------------
    # The check directly above passes VACUOUSLY: no evidence path matches `/users/:id` at all,
    # so `DELETE /users/:id` is uncovered because it was never reached, not because its verb was
    # weighed. It passed identically before and after the fix -- a carve-out with no negative
    # test, in the very assertion that looked like one.
    #
    # This block supplies the missing discrimination: ONE evidence row at `/users/42`, and a pair
    # of routes that share that path and differ ONLY in verb. `GET` must be covered and `DELETE`
    # must not, from the same row. The GET half is the control -- it proves the path really does
    # match, so the DELETE half can only be False because of the verb. Without it, a matcher that
    # had simply stopped matching anything would pass too.
    #
    # A SEPARATE evidence dir, so the arithmetic pinned above is not perturbed.
    verb_ev = _tmp()
    (verb_ev / "2026-09-18-x-summary.csv").write_text(
        ve.FUNCTIONAL.header + "\n"
        "TC-9,User,Users,Pass,200,https://x.test/users/42,https://x.test/users/42,"
        "heading 'User',,\n",
        encoding="utf-8",
    )
    verb_seen = rc.visited_paths([verb_ev])
    check("verb: the fixture row was read at all", sorted(verb_seen), ["/users/42"])
    vcov = {c.route.key: c for c in rc.attribute(rc.from_rails(RAILS), verb_seen)}
    check("verb: GET /users/:id IS covered by a visit to /users/42 (the control -- the path "
          "matches, so a False below is the verb and nothing else)",
          vcov["GET /users/:id"].covered, True)
    check("verb: DELETE /users/:id is NOT covered by that same visit -- a navigation is a GET, "
          "and crediting it would be a false claim about the riskiest route on the list",
          vcov["DELETE /users/:id"].covered, False)
    check("verb: POST /users is NOT covered by a visit to /users",
          {c.route.key: c for c in rc.attribute(rc.from_rails(RAILS),
                                                {"/users": {"functional:x.csv"}})}
          ["POST /users"].covered, False)
    check("attribution: names which artifact covered it",
          any("runtime:" in a for a in cov["GET /users/:id/edit"].by), True)

    # PLACED EARLY, BEFORE ANYTHING DRIVES cmd_report. These are pure-function checks that
    # need no fixtures, and run late they were unreachable: a mutation making cmd_report
    # refuse killed the selftest on a missing trend file first, so the break read as a
    # crash rather than as these assertions failing. A crash is not a verdict.
    # ---- the report says which tree it measured (#1047) -----------------------------------
    # Five different denominators were quoted to each other across one afternoon -- 263, 275, 227,
    # 226, 223 -- and none was wrong. Each correctly measured a different object, and nothing in
    # the output said which. These pin the THREE states apart, because a refusal that cannot tell
    # them apart is worse than the missing provenance it replaces.
    #
    # HEAD IS INJECTED, never read from the ambient tree. These ran in a tempdir that is not a git
    # repository, where a HEAD-reading version answered None and every one of them passed
    # vacuously -- exactly the shape #1040 exists to find, in the checks for #1047.
    HEAD_A, HEAD_B = "a" * 40, "b" * 40
    _tick()
    # STATE 1: a recorded commit that is not HEAD -> REFUSE.
    why = _stale({"commit": HEAD_A}, HEAD_B, "a foreign commit")
    if not why or HEAD_A[:9] not in why:
        FAILURES.append(f"stale_inventory: an inventory from another commit must refuse, got {why!r}")
    _tick()
    # THE CONTROL that stops this being a refusal which always fires: the SAME shape at the SAME
    # commit must proceed. Without it, "refuses on a foreign commit" also passes for a function
    # that refuses everything.
    if _stale({"commit": HEAD_A}, HEAD_A, "the same commit") is not None:
        FAILURES.append("stale_inventory: an inventory from THIS commit must not refuse")
    _tick()
    # THE SHIPPED REGRESSION. v1.133.0 compared the recorded commit to HEAD with `==`, which
    # compares two RENDERINGS rather than two commits, and refused a downstream `doctrine` job on
    # the first run after the bump: "enumerated from 978814d but the working tree is at
    # 978814d29" -- the SAME commit, written at two lengths, with the enumerate and the report
    # running seconds apart in one CI job. The gate refused the one state it must always accept.
    #
    # Every fixture here used two 40-character strings, so the whole class was invisible: nothing
    # asserted that a real sha and its abbreviation are one commit. These are the missing cases,
    # in the exact shape that failed.
    if _stale({"commit": "978814d"}, "978814d29", "an abbreviated sha") is not None:
        FAILURES.append("stale_inventory: an ABBREVIATED recorded sha must not refuse its own "
                        "full-length HEAD -- this is the v1.133.0 regression")
    _tick()
    FULL = "978814d2912f7c8a4b5e6d0f1a2b3c4d5e6f7a8b"
    if _stale({"commit": FULL[:7]}, FULL, "short vs full") is not None:
        FAILURES.append("stale_inventory: a 7-char prefix of HEAD must not refuse")
    _tick()
    # ...and the other direction, because which side is abbreviated is not fixed: the recorded
    # value is whatever `enumerate` wrote and HEAD is whatever the caller resolved.
    if _stale({"commit": FULL}, FULL[:8], "full vs short") is not None:
        FAILURES.append("stale_inventory: a full recorded sha must not refuse an abbreviated HEAD")
    _tick()
    # THE CONTROL, and the reason this widening is a fix and not a deletion: a prefix match is
    # still a MATCH, not a licence. Two shas that genuinely differ must still refuse at any length.
    if _stale({"commit": "978814d"}, "978815a29", "a different commit, abbreviated") is None:
        FAILURES.append("stale_inventory: two DIFFERENT shas must still refuse when abbreviated")
    _tick()
    # And a prefix too short to identify anything is not a match. Seven is git's own floor; below
    # it, accepting a "prefix" would rebuild the defect this check exists to catch.
    if _stale({"commit": "978"}, FULL, "a 3-char prefix") is None:
        FAILURES.append("stale_inventory: a prefix shorter than 7 chars must not count as a match")
    _tick()
    # Case must not decide it either -- git renders lower-case, but a hand-edited artifact may not.
    if _stale({"commit": FULL.upper()}, FULL, "upper-case") is not None:
        FAILURES.append("stale_inventory: sha comparison must be case-insensitive")

    _tick()
    # STATE 2: no provenance at all -- what every file written before #1047 looks like. Refusing it
    # would make the upgrade indistinguishable from a broken tool (#1039's lesson, applied).
    if _stale(None, HEAD_A, "no provenance") is not None:
        FAILURES.append("stale_inventory: a pre-#1047 inventory must be readable, not refused")
    _tick()
    if _stale({"commit": None}, HEAD_A, "a null commit") is not None:
        FAILURES.append("stale_inventory: an inventory taken outside a git tree must not refuse")
    _tick()
    # ...and the mirror: with no HEAD to compare against, staleness is UNDECIDABLE, so it must not
    # refuse. Proving a mismatch is the only thing that licenses a refusal.
    if _stale({"commit": HEAD_A}, None, "no HEAD") is not None:
        FAILURES.append("stale_inventory: with no HEAD to compare, it must not claim staleness")
    _tick()
    # ...but a missing block must still SAY the number is unattributable, or nothing changed.
    unknown = " ".join(rc.provenance_lines(None))
    if "UNKNOWN" not in unknown:
        FAILURES.append(f"provenance_lines: a missing block must report UNKNOWN, got {unknown!r}")
    _tick()
    # STATE 3: a dirty tree is ANNOTATED, never refused. Enumerating mid-change is ordinary, and
    # `git status --porcelain` says nothing about whether the change touched routes.rb. A refusal
    # here blocks a legitimate workflow, and a gate that blocks people wrongly gets turned off.
    dirty_line = " ".join(rc.provenance_lines(
        {"commit": "abc123def456", "dirty": True, "rails_env": "test",
         "enumerated_at": "2026-09-18T12:00:00Z"}))
    if "+dirty" not in dirty_line or "RAILS_ENV=test" not in dirty_line:
        FAILURES.append(f"provenance_lines: a dirty tree and its env must be visible, got {dirty_line!r}")
    _tick()
    if _stale({"commit": HEAD_A, "dirty": True}, HEAD_A, "a dirty tree") is not None:
        FAILURES.append("stale_inventory: a dirty tree at the right commit must annotate, not refuse")
    _tick()
    # RAILS_ENV alone produced 263 vs 275 on ONE tree, so an unset one must READ as unset rather
    # than vanish -- a blank is indistinguishable from `production`.
    unset_line = " ".join(rc.provenance_lines(
        {"commit": "abc123def456", "dirty": False, "rails_env": None,
         "enumerated_at": "2026-09-18T12:00:00Z"}))
    if "RAILS_ENV=unset" not in unset_line:
        FAILURES.append(f"provenance_lines: an unset RAILS_ENV must say so, got {unset_line!r}")
    _tick()
    # The recorder must populate what the reporter reads. Two halves written apart is how a field
    # goes quietly empty.
    made = rc.enumeration_provenance()
    if set(made) != {"commit", "dirty", "rails_env", "enumerated_at"}:
        FAILURES.append(f"enumeration_provenance: wrong fields: {sorted(made)}")
    _tick()
    # ...and the env var must actually be READ, not merely present as a key. Asserting field names
    # alone passed a mutation that hardcoded `rails_env: None`, which would have shipped a
    # permanently empty field -- the exact hole #1047 is about. Set it and look.
    _env_before = os.environ.get("RAILS_ENV")
    os.environ["RAILS_ENV"] = "selftest-env"
    try:
        if rc.enumeration_provenance().get("rails_env") != "selftest-env":
            FAILURES.append("enumeration_provenance: RAILS_ENV is not read from the environment")
    finally:
        if _env_before is None:
            os.environ.pop("RAILS_ENV", None)
        else:
            os.environ["RAILS_ENV"] = _env_before

    # ---- the ONLY channel that can cover a non-GET route (#1039) --------------------------
    # #1037 stopped a GET crediting a DELETE. That was correct and it left every state-changing
    # route permanently uncoverable -- a gap nobody can close, which is the pressure that ends in
    # someone excluding the state-changing routes. The `actions` profile is the channel; these are
    # the checks that it opens ONLY as far as it claims to.
    act_ev = _tmp()
    (act_ev / "2026-09-18-x-actions.csv").write_text(
        ve.ACTIONS.header + "\n"
        "DELETE,/users/:id,admin,exercised,302,https://x.test/users/42,https://x.test/users,"
        "flash 'Deleted',shot.png,\n",
        encoding="utf-8",
    )
    av = rc.verb_paths([act_ev])
    check("actions: the row is read as (verb, pattern)", sorted(av), [("DELETE", "/users/:id")])
    acov = {c.route.key: c
            for c in rc.attribute(rc.from_rails(RAILS), {}, av)}
    # THE POINT OF THE WHOLE ISSUE: a non-GET route can now be covered, and only this way.
    check("actions: DELETE /users/:id IS covered by a row that drove it",
          acov["DELETE /users/:id"].covered, True)
    # THE DISCRIMINATING CONTROL, on the SAME evidence. `GET /users/:id` shares the pattern and
    # differs only in verb, so if this were True the match would be path-only again -- the exact
    # defect #1037 removed, re-entering through the new door.
    check("actions: GET /users/:id is NOT covered by a DELETE row on the same pattern",
          acov["GET /users/:id"].covered, False)
    check("actions: POST /users is NOT covered by a DELETE row on a different pattern",
          acov["POST /users"].covered, False)
    check("actions: the artifact is named as the source",
          acov["DELETE /users/:id"].by, ["actions:2026-09-18-x-actions.csv"])

    # A PATTERN THAT NAMES NO ROUTE CREDITS NOTHING rather than guessing. Exact matching on both
    # halves is what makes the verb channel safe: a wrong pattern under-claims, and under-claiming
    # is the direction this file takes everywhere else.
    #
    # `/users` is deliberately a strict SUBSTRING of the real `/users/:id`, and that is the whole
    # value of this fixture. An earlier version used `/user/:id`, which is not a substring of
    # anything -- so loosening `==` to `in` passed it, and the check proved nothing about the one
    # loosening anybody would actually write. There is no `DELETE /users` route, so the honest
    # answer is that `DELETE /users/:id` stays uncovered; a substring or prefix match credits it.
    typo_ev = _tmp()
    (typo_ev / "typo-actions.csv").write_text(
        ve.ACTIONS.header + "\n"
        "DELETE,/users,admin,exercised,302,https://x.test/users,https://x.test/users,"
        "flash 'Deleted',shot.png,\n",
        encoding="utf-8",
    )
    tcov = {c.route.key: c
            for c in rc.attribute(rc.from_rails(RAILS), {}, rc.verb_paths([typo_ev]))}
    check("actions: a pattern naming no route credits nothing -- a wrong pattern under-claims",
          tcov["DELETE /users/:id"].covered, False)

    # A SKIPPED row is not evidence. Same file, same route, one word different.
    skip_ev = _tmp()
    (skip_ev / "skip-actions.csv").write_text(
        ve.ACTIONS.header + "\n"
        "DELETE,/users/:id,admin,Out of Scope,none,,,,,not in this release\n",
        encoding="utf-8",
    )
    check("actions: an Out of Scope row drives nothing and credits nothing",
          rc.verb_paths([skip_ev]), {})

    # ---- an unreadable artifact is REPORTED, not silently skipped (#1039) -----------------
    # `visited_paths` still skips what it cannot parse -- guessing at a malformed artifact is
    # worse than ignoring it -- but the skip is now visible. Without this the day a contract
    # moves, every written artifact stops parsing and coverage falls to near zero with no error,
    # which reads as a regression rather than as the parse failure it is.
    bad_ev = _tmp()
    (bad_ev / "broken.csv").write_text("Not,A,Known,Header\n1,2,3,4\n", encoding="utf-8")
    bad = rc.unusable_artifacts([bad_ev])
    check("unusable: a CSV matching no contract is reported", len(bad), 1)
    # Indexed defensively. Under the mutation that restores the silent swallow this list is EMPTY,
    # and `bad[0]` would raise IndexError -- a crash, which is not a verdict. The harness rejects a
    # fixture that dies instead of failing, so it has to report a wrong value rather than blow up.
    check("unusable: it says which file",
          bool(bad) and bad[0][0].endswith("broken.csv"), True)
    # THE CONTROL. A directory of well-formed evidence must report NOTHING -- otherwise "1 could
    # not be read" would be printed on every healthy run and would mean nothing at all.
    check("unusable: well-formed evidence reports nothing", rc.unusable_artifacts([act_ev]), [])


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
    classified = set(rc.ROUTE_SOURCES) | set(rc.VERB_SOURCES) | set(rc.ROUTE_LESS)
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
                        trend=str(trend), json=False, fail_on_untested=False, fail_on_unmeasured=False)
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
    # THE PROJECT DECIDES WHICH AXES FAIL (#1029). `checks.json` armed `--fail-on-untested` for
    # every adopter, so a project with a backlog got a permanently red gate it could not opt out of
    # — one downstream project had written the opposite decision into its own CI and the plugin
    # overrode it, then aborted the job before that project's own ratchet could run.
    _tick()
    if rc.fail_axes(args, {}) != (False, False):
        FAILURES.append("fail_axes: the DEFAULT must be none — a partial-coverage project is normal")
    _tick()
    if rc.fail_axes(args, {"fail_on": "untested"}) != (True, False):
        FAILURES.append("fail_axes: coverage.fail_on: untested must arm exactly that axis")
    _tick()
    if rc.fail_axes(args, {"fail_on": "both"}) != (True, True):
        FAILURES.append("fail_axes: coverage.fail_on: both must arm both axes")
    # A TYPO MUST BE REFUSED, not read as `none`: silently disarming a gate is indistinguishable
    # from the gate passing, which is the failure this whole file exists to make impossible.
    _tick()
    try:
        rc.fail_axes(args, {"fail_on": "untetsed"})
        FAILURES.append("fail_axes: a misspelt fail_on was accepted and silently disarmed the gate")
    except SystemExit:
        pass
    # AND THE WHOLE COMMAND HONOURS IT, not just the helper: proving the helper is not proving the
    # caller, and this repo has paid for that distinction more than once.
    _saved_trend, args.trend = args.trend, None
    _tick()
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args) != 0:
            FAILURES.append("report: with fail_on unset, a gap must still exit 0")
    _base_cfg = cfg.read_text(encoding="utf-8")
    cfg.write_text(_base_cfg.replace("coverage:\n", "coverage:\n  fail_on: untested\n", 1),
                   encoding="utf-8")
    _tick()
    if rc.load_config(cfg).get("fail_on") != "untested":
        FAILURES.append("report: the fixture did not land inside the coverage block, so the "
                        "assertion below would pass for the wrong reason")
    _tick()
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args) != 1:
            FAILURES.append("report: coverage.fail_on: untested in the project config must exit 1")
    cfg.write_text(_base_cfg, encoding="utf-8")
    args.trend = _saved_trend

    args.fail_on_untested = True
    _tick()
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args) != 1:
            FAILURES.append("report: --fail-on-untested must exit 1 while a gap remains")
    # An explicit CLI flag still WINS over the config, so a project that reached full coverage can
    # arm one axis in its own CI without editing config — and nobody passing the flag on purpose
    # was broken by #1029.
    _tick()
    if rc.fail_axes(args, {"fail_on": "none"}) != (True, False):
        FAILURES.append("fail_axes: an explicit --fail-on-untested must beat coverage.fail_on: none")
    _tick()
    # Read defensively. Under a mutation that makes cmd_report REFUSE -- e.g. one that treats a
    # pre-#1047 inventory as stale -- no trend file is written at all, and reading it unguarded
    # raised FileNotFoundError: the selftest died instead of reporting, and a crash is not a
    # verdict. The harness rejects a fixture that dies rather than failing.
    lines = ([json.loads(x) for x in trend.read_text(encoding="utf-8").splitlines()]
             if trend.exists() else [])
    if not trend.exists():
        FAILURES.append("trend: no trend file was written — cmd_report did not complete a run")
    if len(lines) != 2:
        FAILURES.append(f"trend: expected 2 appended runs, got {len(lines)}")
    elif lines[0] != {# #1047. The ratchet reads this file, so the provenance has to survive into
                      # the record and not only onto the screen. None here because this fixture's
                      # routes.json predates the block -- which is exactly what an inventory
                      # written by an older version looks like, and it must still be readable.
                      "provenance": None,
                      "routes": 2, "covered": 1, "untested": 1, "crawled_unasserted": 0,
                      "excluded": 0, "percent": 50,
                      # AXIS TWO in the same line, because a trend file that records one axis is a
                      # trend nobody can read the other from later (#953).
                      # 1, not 2: `DELETE /users/:id` is not in the responsive denominator —
                      # a layout probe navigates with a GET.
                      "measured_small": 0, "unmeasured_small": 1, "small_percent": 0,
                      "small_viewport_max": 480}:
        FAILURES.append(f"trend: wrong arithmetic recorded: {lines[0]}")

    # ---- #108 residual: crawl visits are a THIRD state, never folded into `covered` ---------
    crawl_dir = work / "crawled"
    crawl_dir.mkdir()
    (crawl_dir / "crawl.json").write_text(json.dumps({"pages": [
        {"route": "/users"}, {"route": "http://localhost:3000/users/7"},
        {"route": "/reports"}]}) + "\n",
        encoding="utf-8")
    _tick()
    vo = rc.visit_only_paths([crawl_dir])
    if set(vo) != {"/users", "/users/7", "/reports"}:
        FAILURES.append(f"visit_only_paths: expected both routes, got {sorted(vo)}")
    _tick()
    if vo and next(iter(vo.values())) != {"crawl.json"}:
        FAILURES.append(f"visit_only_paths: must attribute the artifact, got {vo}")

    # THE WHOLE POINT: the percentage must not move. A crawl visit is not an assertion, and a
    # coverage number that counts one is the SKIP-is-not-a-PASS defect wearing a percentage.
    # A SEPARATE routes file, so the arithmetic pinned above is not perturbed. `GET /users` is
    # the crawlable gap; `DELETE /users/:id` is the destructive one that must NOT be claimed.
    routes2 = work / "routes2.json"
    routes2.write_text(json.dumps({"routes": [
        {"verb": "GET", "pattern": "/", "controller": "home#index", "area": "home"},
        {"verb": "GET", "pattern": "/reports", "controller": "reports#index",
         "area": "reports"},
        {"verb": "DELETE", "pattern": "/users/:id", "controller": "users#destroy",
         "area": "users"},
    ]}) + "\n", encoding="utf-8")
    _tick()
    args2 = _a.Namespace(routes=str(routes2), evidence=[str(ev), str(crawl_dir)],
                         config=str(cfg), trend=None, json=True, fail_on_untested=False, fail_on_unmeasured=False)
    with contextlib.redirect_stdout(io.StringIO()) as cap2:
        rc.cmd_report(args2)
    body = cap2.getvalue()
    # Parsed defensively, for the same reason the trend read above is: under a mutation that makes
    # cmd_report REFUSE, it prints nothing to stdout and `body.index("{")` raised ValueError --
    # the selftest died instead of reporting a wrong value. An empty payload makes the assertions
    # below fail honestly rather than crash.
    payload = _json_payload(body)
    if not payload:
        FAILURES.append("--json printed no payload — cmd_report did not complete a run")
    if payload.get("covered") != 1 or payload.get("untested") != 2 or payload.get("percent") != 33:
        FAILURES.append(f"a crawl visit changed the coverage arithmetic: {payload}")
    _tick()
    if payload.get("crawled_unasserted") != ["GET /reports"]:
        FAILURES.append(f"the crawled gap, and ONLY it, must be named: "
                        f"{payload.get('crawled_unasserted')}")
    _tick()
    flags = {g["route"]: g.get("crawled") for g in payload.get("gaps", [])}
    if flags.get("GET /reports") is not True:
        FAILURES.append(f"the crawled gap must be FLAGGED, not silently reclassified: {flags}")
    # A GET crawl of /users/7 must NOT be claimed as a visit to `DELETE /users/:id`. The crawler
    # navigates with page.goto, which is a GET; claiming otherwise is a false statement about
    # the riskiest routes on the list.
    _tick()
    if flags.get("DELETE /users/:id") is not False:
        FAILURES.append(f"a destructive route was claimed as crawled: {flags}")
    _tick()
    if "crawled, unasserted" not in body:
        FAILURES.append("the human listing must flag the crawled gap too, not only --json")
    # A run with no crawl artifact at all must still print the line -- a number that appears only
    # when non-zero cannot be told from a number nobody computed.
    _tick()
    args3 = _a.Namespace(routes=str(routes_json), evidence=[str(ev)], config=str(cfg),
                         trend=None, json=False, fail_on_untested=False, fail_on_unmeasured=False)
    with contextlib.redirect_stdout(io.StringIO()) as cap3:
        rc.cmd_report(args3)
    if "0 visited by a crawl but never asserted" not in cap3.getvalue():
        FAILURES.append("the third-state line must print even when the count is zero")
    # An unreadable or non-crawl JSON is skipped, never guessed at.
    _tick()
    (crawl_dir / "links.json").write_text("not json at all", encoding="utf-8")
    if set(rc.visit_only_paths([crawl_dir])) != {"/users", "/users/7", "/reports"}:
        FAILURES.append("an unreadable artifact must be skipped, not crash the run")

    # ---- AXIS TWO: measured at a small viewport (#953) --------------------------------------
    # A route asserted at 1280px and never seen at 390px is fully covered on axis one and absent
    # from this one. That is not a hypothetical: it is the state that shipped 71-83% of a table
    # hidden while the suite reported 49/49 routes covered.
    small_dir = work / "layout"
    small_dir.mkdir()

    def _layout(*entries, viewport="390x844") -> None:
        (small_dir / "layout.json").write_text(json.dumps({
            "schema": "qa-flow/layout-fit/1", "viewport": viewport,
            "routes": list(entries)}) + "\n", encoding="utf-8")

    def _entry(route, *, viewport="390x844", elements=(), landed=None) -> dict:
        out = {"route": route, "viewport": viewport, "elements": list(elements)}
        if landed is not None:
            out["landedOn"] = landed
        return out

    _tick()
    _layout(_entry("/users"), _entry("/reports"))
    got = rc.small_viewport_paths([small_dir], 480)
    if set(got) != {"/users", "/reports"}:
        FAILURES.append(f"small_viewport_paths: expected both routes, got {sorted(got)}")
    _tick()
    if got and next(iter(got.values())) != {"layout.json@390px"}:
        FAILURES.append(f"small_viewport_paths must attribute the width, got {got}")

    # A DESKTOP MEASUREMENT IS NOT A SMALL ONE. This is the whole axis: the flow's only browser
    # sweep was pinned to 1280x900, so every route was "measured" and none was measured small.
    _tick()
    _layout(_entry("/users", viewport="1280x900"))
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("a 1280px measurement must not count as small")
    _tick()
    _layout(_entry("/users", viewport="480x900"))
    if set(rc.small_viewport_paths([small_dir], 480)) != {"/users"}:
        FAILURES.append("the boundary width itself must count as small")
    _tick()
    _layout(_entry("/users", viewport="481x900"))
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("one pixel past the boundary must not count")

    # A PROBE THAT THREW MEASURED NOTHING, and a route recorded with `elements: null` claiming
    # coverage would be the SKIP-is-not-a-PASS defect on axis two.
    _tick()
    _layout({"route": "/users", "viewport": "390x844", "elements": None})
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("a null probe must not count as measured")
    # An empty element list IS a measurement -- "nothing hidden" is an answer.
    _tick()
    _layout(_entry("/users"))
    if set(rc.small_viewport_paths([small_dir], 480)) != {"/users"}:
        FAILURES.append("an empty element list is still a measurement")

    # A ROUTE MEASURED SOMEWHERE ELSE WAS NOT MEASURED. Downstream, the interaction sweep clicked
    # sign-out and five admin routes were recorded under the routes asked for while showing the
    # landing page.
    _tick()
    _layout(_entry("/users", landed="/"))
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("a route that landed elsewhere must not count as measured")
    _tick()
    _layout(_entry("/users", landed="/users"))
    if set(rc.small_viewport_paths([small_dir], 480)) != {"/users"}:
        FAILURES.append("landing where you asked must still count")

    # A viewport that cannot be parsed is not a measurement, and neither is a missing one.
    for label, entry in (("absent", {"route": "/users", "elements": []}),
                         ("nonsense", _entry("/users", viewport="wide"))):
        _tick()
        (small_dir / "layout.json").write_text(json.dumps({
            "schema": "qa-flow/layout-fit/1", "routes": [entry]}) + "\n", encoding="utf-8")
        if rc.small_viewport_paths([small_dir], 480) != {}:
            FAILURES.append(f"a {label} viewport must not count as a small measurement")

    # THE WRONG SCHEMA IS NOT LAYOUT EVIDENCE. Reading any `layout.json` would let an unrelated
    # file grant coverage on the axis this tool exists to keep honest.
    _tick()
    (small_dir / "layout.json").write_text(json.dumps({
        "schema": "something/else/1", "viewport": "390x844",
        "routes": [_entry("/users")]}) + "\n", encoding="utf-8")
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("a foreign schema must not grant responsive coverage")
    _tick()
    (small_dir / "layout.json").write_text("not json at all", encoding="utf-8")
    if rc.small_viewport_paths([small_dir], 480) != {}:
        FAILURES.append("an unreadable layout artifact must be skipped, not crash the run")

    # THE AXES MUST NOT BE AVERAGED. `covered` may not move when small evidence arrives, and the
    # responsive line must print even with no evidence at all.
    #
    # ITS OWN ROUTES FILE, and the reason is a mutation that SURVIVED the first draft: with the
    # two-route fixture, the only route measured small was already covered on axis one, so merging
    # the axes changed no number and the fixture proved nothing. `/reports` is measured small and
    # asserted by nothing, which is exactly the state that has to stay visible on both axes.
    routes3 = work / "routes3.json"
    routes3.write_text(json.dumps({"routes": [
        {"verb": "GET", "pattern": "/", "controller": "home#index", "area": "home"},
        {"verb": "GET", "pattern": "/reports", "controller": "reports#index", "area": "reports"},
        {"verb": "GET", "pattern": "/deep/page", "controller": "deep#show", "area": "deep"},
        # A non-GET route belongs in THIS file, or the assertion below that it stays out of the
        # responsive denominator is vacuous — which is how it went quiet once already.
        {"verb": "DELETE", "pattern": "/users/:id", "controller": "users#destroy", "area": "users"},
    ]}) + "\n", encoding="utf-8")
    _tick()
    _layout(_entry("/"), _entry("/reports"))
    args4 = _a.Namespace(routes=str(routes3), evidence=[str(ev), str(small_dir)],
                         config=str(cfg), trend=None, json=True,
                         fail_on_untested=False, fail_on_unmeasured=False)
    with contextlib.redirect_stdout(io.StringIO()) as cap4:
        rc.cmd_report(args4)
    axis = _json_payload(cap4.getvalue())
    if not axis:
        FAILURES.append("axis two: --json printed no payload")
    # 1 of 3 asserted. `/reports` is measured small and asserted by nothing: if the axes merged it
    # would be credited as covered and this number would move to 66%.
    if axis.get("percent") != 25 or axis.get("covered") != 1:
        FAILURES.append(f"axis one moved when small evidence arrived: "
                        f"{axis.get('percent')}% covered={axis.get('covered')}")
    _tick()
    # 2 measured small of 3 GET routes; `/deep/page` is the one nothing measured.
    if axis.get("measured_small") != 2 or axis.get("unmeasured_small") != ["GET /deep/page"]:
        FAILURES.append(f"axis two wrong: {axis.get('measured_small')} / "
                        f"{axis.get('unmeasured_small')}")
    # A NON-GET ROUTE IS NOT IN THE DENOMINATOR. A layout probe navigates with `page.goto`, so
    # `DELETE /users/:id` cannot be measured at any width — this fixture reported it missing until
    # the denominator was corrected, which would have made the axis permanently unreachable.
    _tick()
    if "DELETE /users/:id" in (axis.get("unmeasured_small") or []):
        FAILURES.append("a non-GET route must not be counted as unmeasured on the responsive axis")

    _tick()
    if "responsive coverage:" not in cap3.getvalue():
        FAILURES.append("the responsive line must print even with no layout evidence")
    _tick()
    if "no layout.json evidence found" not in cap3.getvalue():
        FAILURES.append("no small evidence at all must say so, not read as 0%")

    # `--fail-on-unmeasured` gates axis two ALONE, so reaching one axis is not held hostage to the
    # other. Same routes, no small evidence: untested must not fail it, unmeasured must.
    _tick()
    args5 = _a.Namespace(routes=str(routes_json), evidence=[str(ev)], config=str(cfg),
                         trend=None, json=False, fail_on_untested=False, fail_on_unmeasured=True)
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args5) != 1:
            FAILURES.append("--fail-on-unmeasured must fail when a route was never measured small")
    _tick()
    _layout(_entry("/"), _entry("/reports"), _entry("/deep/page"))
    args6 = _a.Namespace(routes=str(routes3), evidence=[str(ev), str(small_dir)],
                         config=str(cfg), trend=None, json=False,
                         fail_on_untested=False, fail_on_unmeasured=True)
    with contextlib.redirect_stdout(io.StringIO()):
        if rc.cmd_report(args6) != 0:
            FAILURES.append("--fail-on-unmeasured must pass once every route is measured small")

    # The boundary is declared, and a nonsense one is refused rather than silently defaulted.
    _tick()
    if rc._small_max({}) != rc.DEFAULT_SMALL_VIEWPORT_MAX:
        FAILURES.append("an absent small_viewport_max must fall back to the default")
    _tick()
    if rc._small_max({"small_viewport_max": "414"}) != 414:
        FAILURES.append("a declared small_viewport_max must be honoured")
    # AND THROUGH THE PARSER, not only through a hand-built dict (#1029). Every fixture here fed
    # `_small_max` a dict directly, so the reader that drops or carries the key was never exercised
    # — and it dropped every scalar, silently, for as long as the key has existed. Proving the
    # helper is not proving the caller.
    _e2e = _tmp() / "viewport.yml"
    _e2e.write_text("coverage:\n  small_viewport_max: 414   # a real phone\n", encoding="utf-8")
    _tick()
    if rc._small_max(rc.load_config(_e2e)) != 414:
        FAILURES.append("a small_viewport_max written in qa.config.yml never reaches _small_max")
    for bad in ("wide", "12"):
        _tick()
        try:
            rc._small_max({"small_viewport_max": bad})
            FAILURES.append(f"small_viewport_max={bad!r} must be refused")
        except SystemExit:
            pass

    # ---- enumerate REFUSES a partial parse (#953) -------------------------------------------
    # Writing a route file that is missing rows and exiting 0 is how a confident percentage gets
    # computed over an application that does not exist.
    enum_dir = work / "enum"
    enum_dir.mkdir()
    rails_ok = enum_dir / "routes-ok.txt"
    rails_ok.write_text(RAILS, encoding="utf-8")
    rails_bad = enum_dir / "routes-bad.txt"
    rails_bad.write_text(RAILS + ("                                 weird GET    /weird(.:format)"
                                  "   placeholders#show trailing column\n"), encoding="utf-8")
    _tick()
    good = _a.Namespace(rails=str(rails_ok), sitemap=None, fs=None,
                        out=str(enum_dir / "ok.json"), func=None)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        if rc.cmd_enumerate(good) != 0:
            FAILURES.append("a fully parsed route table must enumerate cleanly")
    _tick()
    bad = _a.Namespace(rails=str(rails_bad), sitemap=None, fs=None,
                       out=str(enum_dir / "bad.json"), func=None)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        if rc.cmd_enumerate(bad) != 2:
            FAILURES.append("enumerate refuses a partial parse — an unparsed row must exit 2")
    _tick()
    if "did not parse" not in err.getvalue():
        FAILURES.append("the refusal must say what it could not parse, not just fail")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"route_coverage selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
