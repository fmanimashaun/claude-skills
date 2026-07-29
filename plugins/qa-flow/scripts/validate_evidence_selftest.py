#!/usr/bin/env python3
"""Prove every evidence-validation rule fires -- and, harder, that it stays silent.

Run:  python3 validate_evidence.py --selftest   (or execute this file directly)

The silent direction is the one that matters here, and #106 says why in its own words: the
naive version of this fix over-corrected and wrongly excluded four VALID cases -- real
404-page *designs*, which return HTTP 200 and legitimately contain "page not found". A
checker that flags those gets switched off after the third false positive and then catches
nothing. So the fixture set is adversarial in BOTH directions:

  * every rule has a fixture that must fire, and
  * every rule has a near-miss fixture that must NOT fire.

Fixtures are deliberately unrealistic where realism would share the implementation's blind
spot -- Excel BOM headers, quoted fields, short rows, over-long rows, emoji statuses,
boundary status codes. A realistic fixture proves the happy path and nothing else.

Costs nothing: no network, no browser, stdlib only.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_evidence as ve  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

HEADER = ve.FUNCTIONAL.header
A11Y_HEADER = ve.A11Y.header
RUNTIME_HEADER = ve.RUNTIME.header
PROFILE_NAMES = {p.name for p in ve.PROFILES}


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="qaflow-evidence-"))


def _write(body: str, *, header: str | None = None, bom: bool = False) -> Path:
    """Write a CSV fixture and return its path."""
    path = _tmpdir() / "2026-07-29-fixture-summary.csv"
    head = HEADER if header is None else header
    path.write_text(f"{head}\n{body}", encoding="utf-8-sig" if bom else "utf-8", newline="")
    return path


def expect_clean(label: str, body: str, **kw) -> None:
    """The rule must STAY SILENT on this input."""
    _tick()
    try:
        findings = ve.validate(_write(body, **kw))
    except ve.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)} finding(s): {findings}")


def expect_findings(label: str, body: str, *, contains: str, count: int | None = None, **kw) -> None:
    """The rule must FIRE on this input, and say the right thing."""
    _tick()
    try:
        findings = ve.validate(_write(body, **kw))
    except ve.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings do not mention {contains!r}: {blob}")
    if count is not None and len(findings) != count:
        FAILURES.append(f"{label}: expected {count} finding(s), got {len(findings)}: {blob}")


def expect_unusable(label: str, body: str, *, contains: str, **kw) -> None:
    """The input cannot be checked -- must raise Unusable, never report clean."""
    _tick()
    try:
        ve.validate(_write(body, **kw))
    except ve.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: Unusable message does not mention {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, but the report was accepted")


# --------------------------------------------------------------------------------------
# Rows. Column order: Test ID,Title,Menu,Status,HTTP,Requested URL,Final URL,Assertion,
#                     Screenshot,Notes
# --------------------------------------------------------------------------------------
GOOD_PASS = "TC-001,Create template,Templates,Pass,200,https://a/new,https://a/new,heading 'New template',,"
GOOD_FAIL = "TC-002,Empty required fields,Templates,Fail,200,https://a/new,https://a/new,heading 'New template',screenshots/fail-x.png,Validation msg absent"


def run() -> int:
    # ---- the silence proof: a conforming report ---------------------------------------
    expect_clean("conforming report", f"{GOOD_PASS}\n{GOOD_FAIL}\n")

    # ---- THE over-correction guard (issue #106's four wrongly-excluded cases) ---------
    # A real 404-page DESIGN: returns HTTP 200, contains "page not found", and IS the page
    # under test. This must PASS. If a future "improvement" text-sniffs for error strings,
    # this fixture is what catches it. Do not delete it to make a new rule pass.
    expect_clean(
        "intentional 404 design (HTTP 200, error text, legitimately Pass)",
        "TC-010,404 page design renders,Status pages,Pass,200,https://a/status/404-1,"
        "https://a/status/404-1,text 'Page not found',screenshots/pass-404-design.png,"
        "Intentional error-page design; the 404 copy IS the expectation\n",
    )
    expect_clean(
        "error-page design at /pages/404 with a 'not found' assertion",
        "TC-011,Not-found template,Pages,Pass,200,https://a/pages/404,https://a/pages/404,"
        "text 'not found',,\n",
    )

    # ---- the original defect: 12 of 66 captures were 404s ----------------------------
    expect_findings(
        "Pass on a 404 -- the shipped bug",
        "TC-020,Section index,Nav,Pass,404,https://a/section,https://a/section,heading 'Section',,\n",
        contains="HTTP 404",
    )
    expect_findings(
        "Pass on a 500",
        "TC-021,Dashboard,Home,Pass,500,https://a/,https://a/,heading 'Dashboard',,\n",
        contains="not the page under test",
    )
    expect_findings(
        "Fail on a 404 is equally untrustworthy -- Blocked, not Fail",
        "TC-022,Broken form,Forms,Fail,404,https://a/f,https://a/f,heading 'Form',screenshots/f.png,\n",
        contains="this is Blocked",
    )

    # ---- omission: the hole the prose rule never closed -------------------------------
    expect_findings(
        "Pass with no HTTP status recorded",
        "TC-030,Create template,Templates,Pass,,https://a/new,https://a/new,heading 'New',,\n",
        contains="without an HTTP status",
    )
    expect_findings(
        "Pass with HTTP 200 but NO expected-content assertion (the 200-error-page hole)",
        "TC-031,Create template,Templates,Pass,200,https://a/new,https://a/new,,,\n",
        contains="without an expected-content assertion",
        count=1,
    )
    expect_findings(
        "Pass with no Requested URL",
        "TC-032,Create template,Templates,Pass,200,,https://a/new,heading 'New',,\n",
        contains="without a Requested URL",
        count=1,
    )
    expect_findings(
        "Pass with no Final URL",
        "TC-033,Create template,Templates,Pass,200,https://a/new,,heading 'New',,\n",
        contains="without a Final URL",
        count=1,
    )
    expect_findings(
        "Fail without a screenshot -- pre-existing doctrine, now enforced",
        "TC-034,Empty fields,Templates,Fail,200,https://a/new,https://a/new,heading 'New',,Msg absent\n",
        contains="without a Screenshot",
        count=1,
    )

    # ---- redirects: a different page than intended was tested ------------------------
    expect_findings(
        "silent redirect on a Pass (login wall)",
        "TC-040,Profile,Account,Pass,200,https://a/profile,https://a/login,heading 'Sign in',,\n",
        contains="with no Notes",
        count=1,
    )
    expect_clean(
        "acknowledged redirect is fine -- Notes carries a QUOTED comma",
        'TC-041,Article,Blog,Pass,200,https://a/p/1,https://a/p/1-slug,heading \'Article\',,'
        '"Canonical slug redirect, expected"\n',
    )
    expect_clean(
        "acknowledged 3xx auth redirect",
        "TC-042,Login redirect,Auth,Pass,302,https://a/x,https://a/y,heading 'Sign in',,Expected auth redirect\n",
    )
    # Near-miss for the "Notes acknowledges it" carve-out: whitespace is not an explanation.
    expect_findings(
        "near miss: whitespace-only Notes does not acknowledge a redirect",
        "TC-043,Profile,Account,Pass,200,https://a/profile,https://a/login,heading 'Sign in',,   \n",
        contains="with no Notes",
        count=1,
    )

    # ---- the Fail path carries the same burden as Pass (coverage, not just Pass) -----
    expect_findings(
        "Fail with no expected-content assertion",
        "TC-044,Broken form,Forms,Fail,200,https://a/f,https://a/f,,screenshots/f.png,Submit did nothing\n",
        contains="without an expected-content assertion",
        count=1,
    )
    expect_findings(
        "Fail with a silent redirect",
        "TC-045,Broken form,Forms,Fail,200,https://a/f,https://a/login,button 'Save',screenshots/f.png,\n",
        contains="with no Notes",
        count=1,
    )
    expect_findings(
        "whitespace-only assertion is not an assertion",
        "TC-046,Create,Templates,Pass,200,https://a/n,https://a/n,   ,,\n",
        contains="without an expected-content assertion",
        count=1,
    )

    # ---- Blocked: honest, but must still record what it saw --------------------------
    expect_clean(
        "properly recorded Blocked",
        "TC-050,Section index,Nav,Blocked,404,https://a/section,https://a/section,,,"
        "No template for this section-index URL; not tested\n",
    )
    expect_clean(
        "Blocked with HTTP `none` -- navigation never returned",
        "TC-051,Timeout page,Nav,Blocked,none,https://a/slow,none,,,Navigation timed out after 30s\n",
    )
    expect_findings(
        "Blocked recording nothing at all -- must not become a free pass",
        "TC-052,Section index,Nav,Blocked,,,,,,\n",
        contains="without an HTTP status",
        count=3,  # HTTP, Final URL, Notes
    )
    expect_findings(
        "Blocked without Notes saying what was missing",
        "TC-053,Section index,Nav,Blocked,404,https://a/s,https://a/s,,,\n",
        contains="without Notes",
        count=1,
    )

    # ---- Out of Scope is exempt: not tested and not claimed to be --------------------
    # This is the widest carve-out in the checker, so it needs near-miss negatives: the
    # exemption must match the contract word EXACTLY, or "Out of Scope" becomes a way to
    # opt any row out of proof by spelling it creatively.
    #
    # Note which layer actually guards it: the VALID_STATUSES whitelist rejects an
    # unrecognised status before the exemption branch is ever consulted, so widening the
    # branch alone changes nothing. These two fixtures fire when the *vocabulary* is
    # widened -- verified by mutating both layers together. Keep them: adding a spelling
    # to VALID_STATUSES silently grants it the exemption too.
    expect_clean("Out of Scope carries no burden of proof", "TC-060,Billing,Billing,Out of Scope,,,,,,\n")
    expect_clean("Out of Scope is case-insensitive", "TC-061,Billing,Billing,OUT OF SCOPE,,,,,,\n")
    expect_findings(
        "near miss: hyphenated 'Out-of-Scope' is NOT the exemption",
        "TC-062,Billing,Billing,Out-of-Scope,,,,,,\n",
        contains="is not one of",
        count=1,
    )
    expect_findings(
        "near miss: 'Skipped' does not inherit the exemption",
        "TC-063,Billing,Billing,Skipped,,,,,,\n",
        contains="is not one of",
        count=1,
    )

    # ---- status vocabulary: the CSV takes plain words, not the Markdown's emoji ------
    expect_findings(
        "emoji status leaked from the Markdown template",
        "TC-070,Create template,Templates,✅ Pass,200,https://a/n,https://a/n,heading 'New',,\n",
        contains="is not one of",
        count=1,
    )
    expect_findings(
        "'Passed' is not a contract status",
        "TC-071,Create template,Templates,Passed,200,https://a/n,https://a/n,heading 'New',,\n",
        contains="is not one of",
        count=1,
    )
    expect_clean("lowercase 'pass' is accepted", GOOD_PASS.replace(",Pass,", ",pass,") + "\n")

    # ---- HTTP field is a status code, not prose -------------------------------------
    expect_findings(
        "non-integer HTTP",
        "TC-080,Create,Templates,Pass,200 OK,https://a/n,https://a/n,heading 'New',,\n",
        contains="HTTP 200 OK",
        count=1,
    )
    expect_clean("399 is the top of the accepted range", GOOD_PASS.replace(",200,", ",399,") + "\n")
    expect_findings("400 is out of range", GOOD_PASS.replace(",200,", ",400,") + "\n", contains="HTTP 400", count=1)
    expect_findings("199 is out of range", GOOD_PASS.replace(",200,", ",199,") + "\n", contains="HTTP 199", count=1)

    # ---- malformed rows must produce findings, never a crash ------------------------
    expect_findings(
        "short row (truncated by a writer) reports missing fields, does not crash",
        "TC-090,Create,Templates,Pass\n",
        contains="without an HTTP status",
    )
    expect_findings(
        "over-long row -- an unescaped comma shifted every field",
        "TC-091,Create, template,Templates,Pass,200,https://a/n,https://a/n,heading 'New',,,extra\n",
        contains="more than the 10-column functional contract",
    )

    # ---- whitespace and Excel artefacts ---------------------------------------------
    expect_clean(
        "padded cells are normalised",
        "TC-100 , Create template , Templates , Pass , 200 , https://a/new , https://a/new , heading 'New' , , \n",
    )
    expect_clean("BOM header (Excel writes one) is still readable", f"{GOOD_PASS}\n", bom=True)
    expect_clean("blank lines between rows are skipped, not flagged", f"{GOOD_PASS}\n\n{GOOD_FAIL}\n")

    # ======================================================================================
    # a11y profile -- the SAME rule, a different artifact. This exists because shipping the
    # rule as prose for a11y-auditor while machine-checking it for functional-tester left
    # qa-flow with one validated evidence path and one unvalidated one.
    # ======================================================================================
    A11Y_CLEAN = (
        "/dashboard,signed-in,Audited,200,https://a/dashboard,https://a/dashboard,"
        "heading 'Dashboard',0,Pass,qa/reports/axe-dashboard.json,"
    )
    a11y = {"header": A11Y_HEADER}

    expect_clean("a11y: conforming audited page", f"{A11Y_CLEAN}\n", **a11y)
    expect_clean(
        "a11y: violations by impact",
        "/settings,signed-in,Audited,200,https://a/s,https://a/s,heading 'Settings',"
        "critical:0 serious:2,Fail,qa/reports/axe-settings.json,Focus order wrong in tab panel\n",
        **a11y,
    )
    expect_clean(
        "a11y: 'Not run' is an honest keyboard verdict",
        "/reports,signed-in,Audited,200,https://a/r,https://a/r,heading 'Reports',0,Not run,"
        "qa/reports/axe-reports.json,Keyboard pass deferred to certify\n",
        **a11y,
    )
    # The over-correction guard again, on the a11y side: an intentional error-page design is
    # a legitimate audit target.
    expect_clean(
        "a11y: intentional 404 design is auditable, not disqualified",
        "/404,anon,Audited,200,https://a/404,https://a/404,text 'Page not found',0,Pass,"
        "qa/reports/axe-404.json,Intentional error-page design\n",
        **a11y,
    )
    expect_clean(
        "a11y: properly recorded Blocked",
        "/admin,anon,Blocked,302,https://a/admin,https://a/login,,,,,"
        "Redirected to login; not audited\n",
        **a11y,
    )
    expect_clean("a11y: Out of Scope is exempt", "/billing,anon,Out of Scope,,,,,,,,\n", **a11y)

    # ---- the defect this closes: axe violations from the wrong page -------------------
    expect_findings(
        "a11y: audited a 404 -- real violations, wrong page",
        "/section,anon,Audited,404,https://a/section,https://a/section,heading 'Section',3,Pass,"
        "qa/reports/axe-section.json,\n",
        contains="HTTP 404",
        count=1,
        **a11y,
    )
    expect_findings(
        "a11y: silent login redirect -- audited the login page, filed against /admin",
        "/admin,signed-in,Audited,200,https://a/admin,https://a/login,heading 'Sign in',2,Pass,"
        "qa/reports/axe-admin.json,\n",
        contains="with no Notes",
        count=1,
        **a11y,
    )
    expect_findings(
        "a11y: audited without an expected-content assertion",
        "/dashboard,signed-in,Audited,200,https://a/d,https://a/d,,0,Pass,qa/reports/axe.json,\n",
        contains="without an expected-content assertion",
        count=1,
        **a11y,
    )

    # ---- an audit must report an OUTCOME, not just that it was reached ---------------
    expect_findings(
        "a11y: audited with no Violations count",
        "/dashboard,signed-in,Audited,200,https://a/d,https://a/d,heading 'D',,Pass,"
        "qa/reports/axe.json,\n",
        contains="without a Violations count",
        count=1,
        **a11y,
    )
    for placeholder in ("TBD", "n/a", "-", "none", "pending"):
        expect_findings(
            f"a11y: Violations placeholder {placeholder!r} is not a result",
            f"/dashboard,signed-in,Audited,200,https://a/d,https://a/d,heading 'D',{placeholder},"
            "Pass,qa/reports/axe.json,\n",
            contains="records no number",
            count=1,
            **a11y,
        )
    expect_clean(
        "a11y: an explicit 0 IS a result (a clean page must stay expressible)",
        A11Y_CLEAN + "\n",
        **a11y,
    )
    expect_findings(
        "a11y: audited without a Keyboard verdict",
        "/dashboard,signed-in,Audited,200,https://a/d,https://a/d,heading 'D',0,,"
        "qa/reports/axe.json,\n",
        contains="without a Keyboard verdict",
        count=1,
        **a11y,
    )
    expect_findings(
        "a11y: invented Keyboard verdict",
        "/dashboard,signed-in,Audited,200,https://a/d,https://a/d,heading 'D',0,Mostly,"
        "qa/reports/axe.json,\n",
        contains="is not one of Pass / Fail / Not run",
        count=1,
        **a11y,
    )
    expect_findings(
        "a11y: audited with no Evidence path",
        "/dashboard,signed-in,Audited,200,https://a/d,https://a/d,heading 'D',0,Pass,,\n",
        contains="without an Evidence path",
        count=1,
        **a11y,
    )
    expect_findings(
        "a11y: Blocked recording nothing",
        "/admin,anon,Blocked,,,,,,,,\n",
        contains="without an HTTP status",
        count=3,
        **a11y,
    )

    # ---- the two profiles must not share a status vocabulary ------------------------
    expect_findings(
        "a11y: 'Pass' is a functional status, not an a11y one",
        "/dashboard,signed-in,Pass,200,https://a/d,https://a/d,heading 'D',0,Pass,"
        "qa/reports/axe.json,\n",
        contains="is not one of",
        count=1,
        **a11y,
    )
    expect_findings(
        "functional: 'Audited' is an a11y status, not a functional one",
        "TC-110,Create,Templates,Audited,200,https://a/n,https://a/n,heading 'New',,\n",
        contains="is not one of",
        count=1,
    )

    # ---- runtime capture: console + network per route (#109) ------------------------
    # The severity is RECOMPUTED from the counters, so these fixtures pin the mapping itself,
    # not just field presence. A row that grades its own uncaught exception as S2 is the
    # failure mode -- the whole point is that the grade cannot be talked down.
    rt = {"header": RUNTIME_HEADER}
    # Column order: Route,State,Status,HTTP,Requested URL,Final URL,Assertion,Console Errors,
    #               Console Warnings,Page Errors,Failed Critical,Failed Subresource,
    #               Severity,Ignored,Evidence,Notes
    RUNTIME_CLEAN = (
        "/,anon,Observed,200,https://a/,https://a/,heading 'Dashboard',0,0,0,0,0,none,0,,"
    )

    expect_clean("runtime: clean route", f"{RUNTIME_CLEAN}\n", **rt)
    # Warnings are informational by contract: a noisy-but-working page must not gate, or the
    # check goes red on every third-party library and gets switched off.
    expect_clean(
        "runtime: console warnings alone do not gate",
        "/help,anon,Observed,200,https://a/h,https://a/h,heading 'Help',0,3,0,0,0,none,0,,\n",
        **rt,
    )
    expect_clean(
        "runtime: uncaught exception graded S1",
        "/admin,signed-in,Observed,200,https://a/admin,https://a/admin,heading 'Admin',"
        "1,0,1,0,0,S1,0,qa/manual-tests/runtime/admin.log,"
        "TypeError: localStorage.getItem is not a function (vendor.js:42)\n",
        **rt,
    )
    expect_clean(
        "runtime: missing app bundle graded S1",
        "/dash,anon,Observed,200,https://a/d,https://a/d,heading 'Dash',"
        "0,0,0,1,0,S1,0,qa/manual-tests/runtime/dash.log,app bundle 404 -- /assets/app.js\n",
        **rt,
    )
    expect_clean(
        "runtime: failed subresource graded S2",
        "/gallery,anon,Observed,200,https://a/g,https://a/g,heading 'Gallery',"
        "0,0,0,0,2,S2,0,qa/manual-tests/runtime/gallery.log,hero images 404 -- /img/a.png\n",
        **rt,
    )
    # Suppression is visible rather than absent: a clean route that suppressed 4 known
    # third-party warnings still reports the 4.
    expect_clean(
        "runtime: ignored items counted on an otherwise clean route",
        "/,anon,Observed,200,https://a/,https://a/,heading 'Home',0,0,0,0,0,none,4,,\n",
        **rt,
    )

    # -- the severity mapping cannot be talked down --
    expect_findings(
        "runtime: uncaught exception downgraded to S2",
        "/a,anon,Observed,200,https://a/a,https://a/a,heading 'A',"
        "0,0,1,0,0,S2,0,qa/manual-tests/runtime/a.log,threw once\n",
        contains="is S1", **rt,
    )
    expect_findings(
        "runtime: failed script called clean",
        "/b,anon,Observed,200,https://a/b,https://a/b,heading 'B',0,0,0,2,0,none,0,,\n",
        contains="is S1", **rt,
    )
    expect_findings(
        "runtime: console errors called clean",
        "/c,anon,Observed,200,https://a/c,https://a/c,heading 'C',3,0,0,0,0,none,0,,\n",
        contains="is S2", **rt,
    )
    # The inverse: a severity with nothing behind it. Either a counter was not recorded or the
    # route is clean -- both are defects in the row, and an unexplained S1 trains people to
    # ignore S1.
    expect_findings(
        "runtime: severity with all gating counters at 0",
        "/d,anon,Observed,200,https://a/d,https://a/d,heading 'D',0,0,0,0,0,S1,0,x.log,nothing\n",
        contains="all 0", **rt,
    )

    # -- a capture that records nothing is not a clean capture --
    expect_findings(
        "runtime: missing a counter",
        "/e,anon,Observed,200,https://a/e,https://a/e,heading 'E',,0,0,0,0,none,0,,\n",
        contains="without a Console Errors count", **rt,
    )
    expect_findings(
        "runtime: placeholder text instead of a count",
        "/f,anon,Observed,200,https://a/f,https://a/f,heading 'F',none,0,0,0,0,none,0,,\n",
        contains="records no number", **rt,
    )
    expect_findings(
        "runtime: negative counter",
        "/g,anon,Observed,200,https://a/g,https://a/g,heading 'G',-1,0,0,0,0,none,0,,\n",
        contains="is negative", **rt,
    )
    expect_findings(
        "runtime: no Ignored count -- suppression must stay visible",
        "/h,anon,Observed,200,https://a/h,https://a/h,heading 'H',0,0,0,0,0,none,,,\n",
        contains="suppression must stay visible", **rt,
    )
    expect_findings(
        "runtime: S1 without evidence a human can re-read",
        "/i,anon,Observed,200,https://a/i,https://a/i,heading 'I',0,0,1,0,0,S1,0,,threw\n",
        contains="S1 without an Evidence path", **rt,
    )
    expect_findings(
        "runtime: graded but no message or resource URL recorded",
        "/j,anon,Observed,200,https://a/j,https://a/j,heading 'J',2,0,0,0,0,S2,0,j.log,\n",
        contains="without Notes", **rt,
    )
    expect_findings(
        "runtime: severity outside the vocabulary",
        "/k,anon,Observed,200,https://a/k,https://a/k,heading 'K',0,0,0,0,0,critical,0,,\n",
        contains="is not one of", **rt,
    )

    # -- the SHARED rules must apply to this profile too, not just its own extras --
    # A new profile that silently skipped the page-identity checks would reintroduce #106's
    # hole on the newest artifact.
    expect_findings(
        "runtime: observed on a 500 is not the page under test",
        "/l,anon,Observed,500,https://a/l,https://a/l,heading 'L',0,0,0,0,0,none,0,,\n",
        contains="was not the page under test", **rt,
    )
    expect_findings(
        "runtime: observed without an expected-content assertion",
        "/m,anon,Observed,200,https://a/m,https://a/m,,0,0,0,0,0,none,0,,\n",
        contains="expected-content assertion", **rt,
    )
    expect_findings(
        "runtime: silent redirect means another route was observed",
        "/n,anon,Observed,200,https://a/n,https://a/login,heading 'N',0,0,0,0,0,none,0,,\n",
        contains="redirected", **rt,
    )
    expect_clean(
        "runtime: Blocked route records what it saw",
        "/o,anon,Blocked,none,https://a/o,https://a/o,,,,,,,,,,listeners never attached "
        "-- navigation timed out\n",
        **rt,
    )

    # ---- profile detection is by header, and must never guess -----------------------
    _tick()
    detected = []
    for prof, body in ((ve.FUNCTIONAL, GOOD_PASS), (ve.A11Y, A11Y_CLEAN), (ve.RUNTIME, RUNTIME_CLEAN)):
        got, _ = ve.load_rows(_write(f"{body}\n", header=prof.header))
        detected.append(got.name)
        if got is not prof:
            FAILURES.append(f"profile detection: {prof.name} header resolved to {got.name}")
    if len(set(detected)) != len(PROFILE_NAMES):
        FAILURES.append(f"profile detection: expected distinct profiles, got {detected}")

    # An a11y-shaped header missing one column must not fall through to the functional
    # profile (or vice versa) -- ambiguity resolves to exit 2, never a guess.
    expect_unusable(
        "a11y header missing a column does not fall back to another profile",
        A11Y_CLEAN,
        header=",".join(c for c in ve.A11Y.columns if c != "Violations"),
        contains="missing ['Violations']",
    )

    # ---- unusable input: never report clean on something unread ---------------------
    expect_unusable("wrong header", GOOD_PASS, header="Test ID,Title,Status,Screenshot", contains="missing")
    expect_unusable(
        "columns out of order",
        GOOD_PASS,
        header=",".join([ve.COLUMNS[1], ve.COLUMNS[0]] + ve.COLUMNS[2:]),
        contains="out of order",
    )
    expect_unusable("extra unexpected column", GOOD_PASS, header=f"{HEADER},Vibe", contains="unexpected")
    expect_unusable("header but zero data rows", "", contains="zero data rows")
    expect_unusable("only blank lines below the header", "\n\n\n", contains="zero data rows")

    # A genuinely empty file (not even a newline) and a missing file: written directly,
    # since _write always emits a header line.
    _tick()
    empty = _tmpdir() / "empty-summary.csv"
    empty.write_text("", encoding="utf-8")
    try:
        ve.validate(empty)
        FAILURES.append("empty file: expected UNUSABLE, but it was accepted")
    except ve.Unusable as exc:
        if "no header row" not in str(exc):
            FAILURES.append(f"empty file: unexpected message: {exc}")

    _tick()
    try:
        ve.validate(_tmpdir() / "absent-summary.csv")
        FAILURES.append("missing file: expected UNUSABLE, but it was accepted")
    except ve.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- the doctrine and the code must agree on the column list -------------------
    # Without this, the agent could be told one header while the checker enforced another,
    # and every real report would be rejected as UNUSABLE. This is the claims-vs-enforcement
    # class the repo keeps getting bitten by, applied to my own change.
    agents = Path(__file__).resolve().parents[1] / "agents"
    for filename, profile in (
        ("functional-tester.md", ve.FUNCTIONAL),
        ("a11y-auditor.md", ve.A11Y),
        # The runtime capture is written by both browser-driven passes; functional-tester.md is
        # its canonical contract, and e2e-tester.md points at it rather than restating the
        # header (one copy to drift out of step is enough).
        ("functional-tester.md", ve.RUNTIME),
    ):
        _tick()
        doctrine = agents / filename
        if not doctrine.is_file():
            FAILURES.append(f"cannot find {doctrine} to cross-check the {profile.name} contract")
        elif profile.header not in doctrine.read_text(encoding="utf-8"):
            FAILURES.append(
                f"{filename} does not document the exact {profile.name} header this script "
                "enforces -- the agent would write a CSV the checker rejects. Expected to "
                f"find: {profile.header}"
            )

    # Every profile must be reachable from a documented agent, or it is a dead contract.
    _tick()
    documented = {
        p.name
        for p in ve.PROFILES
        for f in agents.glob("*.md")
        if p.header in f.read_text(encoding="utf-8")
    }
    if documented != PROFILE_NAMES:
        FAILURES.append(
            f"profiles with no agent documenting their header: {sorted(PROFILE_NAMES - documented)}"
        )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"validate_evidence selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
