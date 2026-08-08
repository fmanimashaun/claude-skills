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
KEYBOARD_HEADER = ve.KEYBOARD.header
FORMS_HEADER = ve.FORMS.header
EMULATION_HEADER = ve.EMULATION.header
PERF_HEADER = ve.PERF.header
FINDINGS_HEADER = ve.FINDINGS.header
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

    # ======================================================================================
    # keyboard profile -- exhaustive focus/tab-order walk (#114)
    #
    # The defect being designed against is SAMPLING, which no per-row field can reveal on its
    # own: the real probe checked one button per page and produced focus evidence for 25 of 72
    # pages while reporting nothing missing. So the fixtures attack the DENOMINATOR arithmetic
    # hardest -- a row that looked at 3 of 40 elements must be indistinguishable from nothing,
    # never from a clean page.
    # ======================================================================================
    kb = {"header": KEYBOARD_HEADER}
    # Column order: Route,State,Status,HTTP,Requested URL,Final URL,Assertion,Engine,Interactive,
    #               Tab Stops,Unreachable,No Focus Indicator,Positive Tabindex,Backward Jumps,
    #               Overlays,Trap Failures,Escape Failures,Restore Failures,Skip Link,Severity,
    #               Evidence,Notes
    KEYBOARD_CLEAN = (
        "/,anon,Walked,200,https://a/,https://a/,heading 'Home',chromium,12,12,0,0,0,0,0,0,0,0,"
        "Present,none,,"
    )

    expect_clean("keyboard: clean exhaustive walk", f"{KEYBOARD_CLEAN}\n", **kb)

    # -- THE sampling guard: the 25-of-72 defect, made arithmetic --
    expect_findings(
        "keyboard: sampled 3 of 40 interactive elements (the 25-of-72 defect)",
        "/dash,anon,Walked,200,https://a/d,https://a/d,heading 'D',chromium,40,3,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="samples where the contract is exhaustive", count=1, **kb,
    )
    # Near miss: fully accounted for -- reached + unreachable == inventory. Must stay silent, or
    # a genuinely exhaustive page with unreachable elements reads as a sampling defect.
    expect_clean(
        "keyboard: 37 reached + 3 unreachable accounts for all 40",
        "/dash,anon,Walked,200,https://a/d,https://a/d,heading 'D',chromium,40,37,3,0,0,0,0,0,0,0,"
        "Present,S1,qa/reports/kb/dash.json,3 icon buttons never focusable\n",
        **kb,
    )
    # Near miss the other way: MORE tab stops than inventory is legitimate -- the skip link, an
    # iframe and the document are tab stops that are not interactive-inventory elements.
    expect_clean(
        "keyboard: more tab stops than inventory elements is not a defect",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,10,13,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        **kb,
    )

    # -- you cannot report on what you never focused / never opened --
    expect_findings(
        "keyboard: more missing indicators than elements focused",
        "/x,anon,Walked,200,https://a/x,https://a/x,heading 'X',chromium,5,5,0,9,0,0,0,0,0,0,"
        "Present,S1,e.json,nine unstyled by resting-vs-focused diff\n",
        contains="actually focused", count=1, **kb,
    )

    # -- a blocking S1 must show its work --
    # The defect this came from: a conformant app flagged S1 on every page because the pass looked
    # up `outline` while the ring lived in `box-shadow`, so nothing ever consulted the real
    # indicator. The fixture above now records a method too, or it would stop isolating its own rule.
    expect_findings(
        "keyboard: missing-indicator count with no method recorded",
        "/y,anon,Walked,200,https://a/y,https://a/y,heading 'Y',chromium,9,9,0,2,0,0,0,0,0,0,"
        "Present,S1,e.json,two unstyled\n",
        contains="resting-vs-focused diff", count=1, **kb,
    )
    expect_clean(
        "keyboard: ...and none when the diff is recorded",
        "/z,anon,Walked,200,https://a/z,https://a/z,heading 'Z',chromium,9,9,0,2,0,0,0,0,0,0,"
        "Present,S1,e.json,two unstyled — confirmed by resting-vs-focused diff\n",
        **kb,
    )
    # A count of ZERO needs no method -- demanding one would make every clean page a finding.
    expect_clean(
        "keyboard: a zero count needs no method",
        "/w,anon,Walked,200,https://a/w,https://a/w,heading 'W',chromium,9,9,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        **kb,
    )
    expect_findings(
        "keyboard: 3 focus-restore failures across 1 overlay",
        "/m,anon,Walked,200,https://a/m,https://a/m,heading 'M',chromium,8,8,0,0,0,0,1,0,0,3,"
        "Present,S1,e.json,restore broken\n",
        contains="cannot fail one assertion more than once", count=1, **kb,
    )
    expect_clean(
        "keyboard: 3 restore failures across 3 overlays is arithmetic, not a defect",
        "/m,anon,Walked,200,https://a/m,https://a/m,heading 'M',chromium,8,8,0,0,0,0,3,0,0,3,"
        "Present,S1,e.json,all three modals drop focus to body on close\n",
        **kb,
    )

    # -- the grade cannot be talked down --
    expect_findings(
        "keyboard: unreachable elements downgraded to S2",
        "/y,anon,Walked,200,https://a/y,https://a/y,heading 'Y',chromium,10,8,2,0,0,0,0,0,0,0,"
        "Present,S2,e.json,two buttons\n",
        contains="is S1", count=1, **kb,
    )
    expect_findings(
        "keyboard: a focus-restore failure called clean",
        "/z,anon,Walked,200,https://a/z,https://a/z,heading 'Z',chromium,6,6,0,0,0,0,2,0,0,1,"
        "Present,none,,\n",
        contains="is S1", count=1, **kb,
    )
    expect_findings(
        "keyboard: positive tabindex called clean",
        "/t,anon,Walked,200,https://a/t,https://a/t,heading 'T',chromium,6,6,0,0,3,0,0,0,0,0,"
        "Present,none,,\n",
        contains="is S2", count=1, **kb,
    )
    expect_clean(
        "keyboard: positive tabindex correctly graded S2",
        "/t,anon,Walked,200,https://a/t,https://a/t,heading 'T',chromium,6,6,0,0,3,0,0,0,0,0,"
        "Present,S2,,three tabindex=1 in the nav\n",
        **kb,
    )
    expect_findings(
        "keyboard: severity with every gating counter at 0",
        "/q,anon,Walked,200,https://a/q,https://a/q,heading 'Q',chromium,4,4,0,0,0,0,0,0,0,0,"
        "Present,S1,e.json,nothing actually wrong\n",
        contains="all 0", count=1, **kb,
    )

    # -- the VERIFIED WebKit caveat: Tab reaches text fields and lists only unless Full Keyboard
    #    Access is on, so an unreachable count from webkit is a platform default until the row
    #    says otherwise. Without this, a webkit run files every link as a false S1.
    expect_findings(
        "keyboard: unreachable on webkit without confirming Full Keyboard Access",
        "/w,anon,Walked,200,https://a/w,https://a/w,heading 'W',webkit,20,15,5,0,0,0,0,0,0,0,"
        "Present,S1,e.json,five links never focused\n",
        contains="Full Keyboard Access", count=1, **kb,
    )
    expect_clean(
        "keyboard: webkit unreachable IS a finding once Full Keyboard Access is confirmed",
        "/w,anon,Walked,200,https://a/w,https://a/w,heading 'W',webkit,20,15,5,0,0,0,0,0,0,0,"
        "Present,S1,e.json,Full Keyboard Access enabled; five links genuinely unreachable\n",
        **kb,
    )
    # Near miss: the carve-out is about UNREACHABLE counts, not about webkit. A webkit row with
    # nothing unreachable must not be asked to justify itself.
    expect_clean(
        "keyboard: webkit with 0 unreachable needs no Full Keyboard Access note",
        "/w,anon,Walked,200,https://a/w,https://a/w,heading 'W',webkit,20,20,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        **kb,
    )
    # ...and the reverse near miss: chromium is not granted the webkit exemption's inverse --
    # an unreachable count there is a finding on its own merits, no note required.
    expect_clean(
        "keyboard: chromium unreachable needs no platform note",
        "/w,anon,Walked,200,https://a/w,https://a/w,heading 'W',chromium,20,15,5,0,0,0,0,0,0,0,"
        "Present,S1,e.json,five icon buttons are div-based\n",
        **kb,
    )

    expect_findings(
        "keyboard: no Engine recorded -- reachability is engine-dependent",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',,12,12,0,0,0,0,0,0,0,0,Present,"
        "none,,\n",
        contains="no Engine", count=1, **kb,
    )
    expect_findings(
        "keyboard: Engine outside the vocabulary",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',safari,12,12,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="is not one of", count=1, **kb,
    )
    expect_findings(
        "keyboard: no Skip Link state",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,12,12,0,0,0,0,0,0,0,0,,"
        "none,,\n",
        contains="no Skip Link state", count=1, **kb,
    )
    expect_findings(
        "keyboard: invented Skip Link state",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,12,12,0,0,0,0,0,0,0,0,"
        "Maybe,none,,\n",
        contains="is not one of", count=1, **kb,
    )
    # `Absent` is a real, reportable state and must not gate: SC 2.4.7 does not mandate a skip
    # link, and axe's `bypass` rule is satisfied by landmarks or headings too.
    expect_clean(
        "keyboard: an absent skip link is reportable, not a failure",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,12,12,0,0,0,0,0,0,0,0,"
        "Absent,none,,\n",
        **kb,
    )

    # -- a walk that records nothing is not a clean walk --
    expect_findings(
        "keyboard: missing the Interactive denominator",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,,12,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="no Interactive count", count=1, **kb,
    )
    expect_findings(
        "keyboard: placeholder instead of a count",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,none,12,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="records no number", count=1, **kb,
    )
    expect_findings(
        "keyboard: negative counter",
        "/,anon,Walked,200,https://a/,https://a/,heading 'H',chromium,12,-1,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="is negative", **kb,
    )
    expect_findings(
        "keyboard: S1 without evidence a human can re-walk",
        "/y,anon,Walked,200,https://a/y,https://a/y,heading 'Y',chromium,10,8,2,0,0,0,0,0,0,0,"
        "Present,S1,,two buttons\n",
        contains="S1 without an Evidence path", count=1, **kb,
    )
    expect_findings(
        "keyboard: graded but no element named",
        "/y,anon,Walked,200,https://a/y,https://a/y,heading 'Y',chromium,10,8,2,0,0,0,0,0,0,0,"
        "Present,S1,e.json,\n",
        contains="without Notes naming the element", count=1, **kb,
    )

    # -- the SHARED page-identity rules must reach this profile too (#106 on the newest artifact)
    expect_findings(
        "keyboard: walked a 404 -- a real focus path on the wrong page",
        "/gone,anon,Walked,404,https://a/gone,https://a/gone,heading 'G',chromium,12,12,0,0,0,0,"
        "0,0,0,0,Present,none,,\n",
        contains="not the page under test", count=1, **kb,
    )
    expect_findings(
        "keyboard: walked without an expected-content assertion",
        "/,anon,Walked,200,https://a/,https://a/,,chromium,12,12,0,0,0,0,0,0,0,0,Present,none,,\n",
        contains="expected-content assertion", count=1, **kb,
    )
    expect_findings(
        "keyboard: silent login redirect -- walked the login page, filed against /admin",
        "/admin,signed-in,Walked,200,https://a/admin,https://a/login,heading 'Sign in',chromium,"
        "12,12,0,0,0,0,0,0,0,0,Present,none,,\n",
        contains="redirected", count=1, **kb,
    )
    expect_clean(
        "keyboard: Blocked walk records what it saw",
        "/admin,anon,Blocked,302,https://a/admin,https://a/login,,,,,,,,,,,,,,,,"
        "Redirected to login; tab order not walked\n",
        **kb,
    )
    expect_clean("keyboard: Out of Scope is exempt", "/billing,anon,Out of Scope,,,,,,,,,,,,,,,,,,,\n", **kb)
    expect_findings(
        "keyboard: 'Audited' is an a11y status, not a keyboard one",
        "/,anon,Audited,200,https://a/,https://a/,heading 'H',chromium,12,12,0,0,0,0,0,0,0,0,"
        "Present,none,,\n",
        contains="is not one of", count=1, **kb,
    )

    # ======================================================================================
    # forms profile -- validation state testing (#115)
    #
    # The hole here is not "no checks" but VERDICTS ON STATES NOBODY TRIGGERED: a row can claim
    # the aria-invalid contract held on a form it never submitted, and that reads exactly like a
    # real result. So Submit Mode and the error-contract columns are checked against each other
    # in BOTH directions.
    # ======================================================================================
    fm = {"header": FORMS_HEADER}
    # Column order: Form,Route,Surface,Status,HTTP,Requested URL,Final URL,Assertion,Controls,Unlabelled,
    #               Submit Mode,Invalid Marked,Message Linked,Announced,Values Retained,
    #               Colour Only,Severity,Evidence,Notes
    FORMS_CLEAN = (
        "signup,/signup,page,Exercised,200,https://a/signup,https://a/signup,heading 'Sign up',6,0,0,"
        "dry-run,Not run,Not run,Not run,Not run,Not run,none,,"
    )

    expect_clean("forms: clean dry-run inspection", f"{FORMS_CLEAN}\n", **fm)
    expect_clean(
        "forms: an empty submit whose error contract fully holds",
        "login,/login,page,Exercised,200,https://a/login,https://a/login,heading 'Sign in',3,0,0,empty,"
        "Pass,Pass,Pass,Pass,Pass,none,qa/reports/forms/login.png,\n",
        **fm,
    )

    # -- THE headline rule, in both directions --
    expect_findings(
        "forms: verdicts on an error state a dry-run never triggered",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,dry-run,"
        "Pass,Pass,Pass,Pass,Pass,none,,\n",
        contains="never submitted an invalid form", count=5, **fm,
    )
    expect_findings(
        "forms: submitted an invalid form but recorded no verdict",
        "login,/login,page,Exercised,200,https://a/l,https://a/l,heading 'L',3,0,0,empty,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="the error contract is the reason for submitting", count=5, **fm,
    )
    # Near miss: a VALID submit triggers no error state, so `Not run` is the honest answer there
    # and must not be flagged. Without this the rule would force fabricated verdicts.
    expect_clean(
        "forms: 'valid' mode legitimately reports Not run for the error contract",
        "search,/search,page,Exercised,200,https://a/s,https://a/s,heading 'S',2,0,0,valid,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        **fm,
    )

    # -- the destructive carve-out leaves a trace --
    expect_findings(
        "forms: destructive form skipped with no trace",
        "delete-account,/settings,page,Exercised,200,https://a/set,https://a/set,heading 'Set',4,0,0,"
        "skipped-destructive,Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="naming the pattern that matched", count=1, **fm,
    )
    expect_clean(
        "forms: destructive skip that names what matched",
        "delete-account,/settings,page,Exercised,200,https://a/set,https://a/set,heading 'Set',4,0,0,"
        "skipped-destructive,Not run,Not run,Not run,Not run,Not run,none,,"
        "matched destructive pattern /delete/\n",
        **fm,
    )

    # -- #115 criterion 6, made mechanical by #424: the modal-CRUD 422 re-render ------------
    # It shipped as a POINTER at `functional-tester`, which never specified it, so the criterion
    # was asserted nowhere for three releases. These fixtures are what make it real.
    expect_findings(
        "forms: modal CRUD that navigated instead of re-rendering",
        "edit,/invoices,modal,Exercised,422,https://a/invoices,https://a/invoices/1/edit,"
        "heading 'Edit',4,0,0,invalid,Fail,Pass,Pass,Pass,Pass,S1,e.png,navigated away\n",
        contains="navigated", count=1, **fm,
    )
    expect_findings(
        "forms: modal CRUD on a status Turbo will not reframe",
        "edit,/invoices,modal,Exercised,200,https://a/invoices,https://a/invoices,"
        "heading 'Edit',4,0,0,invalid,Fail,Pass,Pass,Pass,Pass,S1,e.png,200 not 422\n",
        contains="not 422", count=1, **fm,
    )
    expect_findings(
        "forms: a row that does not say which surface it exercised",
        # 200 rather than 422 on purpose: a 422 row with no Surface ALSO trips the status rule,
        # because the modal carve-out correctly refuses to apply to a row that never said it
        # was a modal. Isolating the surface finding is what makes this fixture about one thing.
        "edit,/invoices,,Exercised,200,https://a/invoices,https://a/invoices,"
        "heading 'Edit',4,0,0,invalid,Fail,Pass,Pass,Pass,Pass,S1,e.png,no surface\n",
        contains="no Surface", count=1, **fm,
    )
    # The SILENT half, which is what keeps the rule usable.
    expect_clean(
        "forms: modal CRUD that re-rendered into the frame on 422",
        "edit,/invoices,modal,Exercised,422,https://a/invoices,https://a/invoices,"
        "heading 'Edit',4,0,0,invalid,Fail,Pass,Pass,Pass,Pass,S1,e.png,re-rendered in frame\n",
        **fm,
    )
    # NEAR MISS: a PAGE form legitimately navigates and legitimately is not 422. Firing here would
    # flag every ordinary full-page CRUD failure in the corpus.
    expect_clean(
        "forms: a page form may navigate and need not be 422",
        "signup,/signup,page,Exercised,200,https://a/signup,https://a/signup/errors,"
        "heading 'Sign up',4,0,0,invalid,Fail,Pass,Pass,Pass,Pass,S1,e.png,full page re-render\n",
        **fm,
    )
    # NEAR MISS: a modal row that never submitted an invalid form has no 422 to assert.
    expect_clean(
        "forms: an unexercised modal row asserts nothing about 422",
        "edit,/invoices,modal,Exercised,200,https://a/invoices,https://a/invoices,"
        "heading 'Edit',4,0,0,dry-run,Not run,Not run,Not run,Not run,Not run,none,,not submitted\n",
        **fm,
    )

    # -- label arithmetic --
    expect_findings(
        "forms: more unlabelled controls than the form has",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',3,5,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S1,e.png,five unlabelled\n",
        contains="more controls lack a label", count=1, **fm,
    )
    expect_findings(
        "forms: a form with zero controls is not a form under test",
        "ghost,/g,page,Exercised,200,https://a/g,https://a/g,heading 'G',0,0,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="not a form under test", count=1, **fm,
    )
    expect_findings(
        "forms: more required-unexposed controls than the form has",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',3,0,7,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S2,e.png,seven required\n",
        contains="more controls are required", count=1, **fm,
    )
    # An OVER-grade is deliberately tolerated, and this fixture pins that asymmetry so it stays a
    # decision rather than an oversight. The gate exists to stop a verdict being talked DOWN;
    # escalating S2 to S1 is conservative, and the `runtime` profile -- which shares this
    # recompute -- has always behaved the same way. Flagging it here and not there would mean two
    # severity semantics behind one helper, which a reader could not predict.
    # A severity with NOTHING behind it is still caught: see "gating counters at 0" below.
    expect_clean(
        "forms: required-unexposed escalated to S1 is conservative, not a defect",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,2,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S1,e.png,two required inputs\n",
        **fm,
    )
    expect_findings(
        "forms: severity with every gating counter at 0",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S1,e.png,nothing actually wrong\n",
        contains="all 0", count=1, **fm,
    )
    expect_clean(
        "forms: required-unexposed correctly graded S2",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,2,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S2,e.png,email and password lack aria-required\n",
        **fm,
    )
    # An unlabelled control outranks an unexposed-required one, so a row carrying both is S1.
    expect_clean(
        "forms: unlabelled outranks required-unexposed when both are present",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,1,2,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S1,e.png,one unlabelled and two unexposed\n",
        **fm,
    )

    # -- a forms row that records no counts is not a clean form. `_read_counters` is shared with
    #    the keyboard profile, so without these its omission path was exercised on one of its two
    #    callers only.
    expect_findings(
        "forms: missing the Controls denominator",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',,0,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="no Controls count", count=1, **fm,
    )
    expect_findings(
        "forms: placeholder instead of an Unlabelled count",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,n/a,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="records no number", count=1, **fm,
    )
    expect_findings(
        "forms: negative counter",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,-2,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="is negative", count=1, **fm,
    )

    expect_clean(
        "forms: unlabelled controls correctly graded S1 (3.3.2 / 4.1.2 are Level A)",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,2,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,S1,e.png,date and tel inputs have no label\n",
        **fm,
    )

    # -- the grade cannot be talked down --
    expect_findings(
        "forms: aria-invalid failure called clean",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        "Fail,Pass,Pass,Pass,Pass,none,,\n",
        contains="is S1", count=1, **fm,
    )
    expect_findings(
        "forms: colour-only error state downgraded to S2 (1.4.1 is Level A)",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        "Pass,Pass,Pass,Pass,Fail,S2,e.png,error shown in red only\n",
        contains="is S1", count=1, **fm,
    )
    expect_findings(
        "forms: lost input values called clean",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,invalid,"
        "Pass,Pass,Pass,Fail,Pass,none,,\n",
        contains="is S2", count=1, **fm,
    )
    expect_clean(
        "forms: value loss correctly graded S2",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,invalid,"
        "Pass,Pass,Pass,Fail,Pass,S2,e.png,email cleared on re-render\n",
        **fm,
    )

    # -- vocabulary and omission --
    expect_findings(
        "forms: no Submit Mode -- nothing decides which verdicts are permitted",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="no Submit Mode", count=1, **fm,
    )
    expect_findings(
        "forms: invented Submit Mode",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,poked,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="is not one of", count=1, **fm,
    )
    expect_findings(
        "forms: missing a contract verdict",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        ",Pass,Pass,Pass,Pass,none,,\n",
        contains="no Invalid Marked verdict", count=1, **fm,
    )
    expect_findings(
        "forms: invented contract verdict",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        "Mostly,Pass,Pass,Pass,Pass,none,,\n",
        contains="is not one of Pass / Fail / Not run", count=1, **fm,
    )
    expect_findings(
        "forms: S1 without evidence of the error state",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        "Fail,Pass,Pass,Pass,Pass,S1,,aria-invalid never set\n",
        contains="S1 without an Evidence path", count=1, **fm,
    )
    expect_findings(
        "forms: graded but no control named",
        "signup,/signup,page,Exercised,200,https://a/s,https://a/s,heading 'S',6,0,0,empty,"
        "Fail,Pass,Pass,Pass,Pass,S1,e.png,\n",
        contains="without Notes naming the control", count=1, **fm,
    )

    # -- shared page-identity rules reach this profile too --
    expect_findings(
        "forms: exercised a form on a 500",
        "signup,/signup,page,Exercised,500,https://a/s,https://a/s,heading 'S',6,0,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="not the page under test", count=1, **fm,
    )
    expect_clean(
        "forms: Blocked form records what it saw",
        "signup,/signup,page,Blocked,404,https://a/s,https://a/s,,,,,,,,,,,,,"
        "Form absent on this build; not exercised\n",
        **fm,
    )
    expect_findings(
        "forms: 'Walked' is a keyboard status, not a forms one",
        "signup,/signup,Walked,200,https://a/s,https://a/s,heading 'S',6,0,0,dry-run,"
        "Not run,Not run,Not run,Not run,Not run,none,,\n",
        contains="is not one of", count=1, **fm,
    )

    # ---- findings rollup: dedupe by signature (#118) ---------------------------------
    # The measured case this exists for: 773 "disclosure trigger without aria-expanded" was
    # ~18 distinct defects, one navbar bug across 72 pages. Same arithmetic decides whether
    # qa-reporter files 18 issues or 773.
    fd = {"header": FINDINGS_HEADER}
    # Column order: Signature,Source,Status,Severity,Title,Instances,Routes,Example Routes,
    #               Evidence,Notes
    NAVBAR = ("navbar/disclosure-no-aria-expanded,a11y,Confirmed,S1,Disclosure trigger without "
              "aria-expanded,773,72,/ /about /pricing,qa/reports/findings.json,"
              "one navbar defect across every page")
    COSMETIC = ("card/icon-no-name,a11y,Confirmed,S2,Icon-only control without accessible name,"
                "6,3,/ /pricing,qa/reports/findings.json,three templates")

    expect_clean("findings: the real 773 -> 18 case", f"{NAVBAR}\n{COSMETIC}\n", **fd)
    # page_identity=False: this profile has no HTTP / Final URL / Assertion columns at all, and
    # a clean rollup proves the shared per-page rules are not demanded of a cross-route finding.
    expect_clean(
        "findings: a single distinct defect on one route",
        "footer/dead-link,links,Confirmed,S3,Footer link 404s,1,1,/,"
        "qa/reports/findings.json,dead target /old\n",
        **fd,
    )

    # -- dedupe itself: the guarantee that only exists across rows --
    expect_findings(
        "findings: a repeated signature means it did not roll up",
        f"{NAVBAR}\n{NAVBAR}\n",
        contains="already appeared", **fd,
    )
    # -- the arithmetic that catches an occurrence count pasted into a distinct column --
    expect_findings(
        "findings: fewer instances than routes is impossible",
        "x/y,a11y,Confirmed,S1,Thing,3,72,/ /a,qa/reports/f.json,note\n",
        contains="impossible", **fd,
    )
    expect_findings(
        "findings: zero instances is not a defect",
        "x/y,a11y,Confirmed,S1,Thing,0,1,/,qa/reports/f.json,note\n",
        contains="occurs at least once", **fd,
    )
    expect_findings(
        "findings: more example routes than affected routes",
        "x/y,a11y,Confirmed,S1,Thing,9,2,/ /a /b /c,qa/reports/f.json,note\n",
        contains="cannot outnumber", **fd,
    )
    # -- collapsing 773 rows into 1 must not destroy the 773 --
    expect_findings(
        "findings: no Evidence means the instance list is gone",
        "x/y,a11y,Confirmed,S1,Thing,9,2,/ /a,,note\n",
        contains="instance list must stay retrievable", **fd,
    )
    expect_findings(
        "findings: no example routes to locate it by",
        "x/y,a11y,Confirmed,S1,Thing,9,2,,qa/reports/f.json,note\n",
        contains="not actionable", **fd,
    )
    expect_findings(
        "findings: no signature to dedupe on",
        ",a11y,Confirmed,S1,Thing,9,2,/ /a,qa/reports/f.json,note\n",
        contains="no Signature", **fd,
    )
    expect_findings(
        "findings: severity outside the vocabulary",
        "x/y,a11y,Confirmed,critical,Thing,9,2,/ /a,qa/reports/f.json,note\n",
        contains="is not one of", **fd,
    )
    # Dedupe applies to EVERY source, so the source is checked against the full list rather
    # than left free-text -- #118 is explicit that this is not an a11y-only rule.
    expect_findings(
        "findings: unknown source",
        "x/y,vibes,Confirmed,S1,Thing,9,2,/ /a,qa/reports/f.json,note\n",
        contains="is not one of", **fd,
    )

    # -- ordering, so "ranked by severity x reach" is true of the file, not claimed of it --
    expect_findings(
        "findings: S2 ordered above S1 buries the important one",
        f"{COSMETIC}\n{NAVBAR}\n",
        contains="outranks", **fd,
    )
    expect_findings(
        "findings: within one severity, wider reach must come first",
        "a/b,a11y,Confirmed,S1,Narrow,3,3,/ /a /b,qa/reports/f.json,n\n"
        "c/d,a11y,Confirmed,S1,Wide,72,72,/ /a /b,qa/reports/f.json,n\n",
        contains="outranks", **fd,
    )

    # -- page_identity=False is NOT a blanket exemption --
    expect_findings(
        "findings: an unknown status still fails",
        "x/y,a11y,Audited,S1,Thing,9,2,/ /a,qa/reports/f.json,note\n",
        contains="is not one of", **fd,
    )
    expect_clean(
        "findings: a Blocked source still says why",
        "perf/not-run,perf,Blocked,,,,,,,k6 unavailable on this runner\n",
        **fd,
    )
    expect_findings(
        "findings: Blocked without Notes records nothing",
        "perf/not-run,perf,Blocked,,,,,,,\n",
        contains="Blocked without Notes", **fd,
    )

    # ---- emulated media conditions (#116) -------------------------------------------
    # Column order: Route,Mode,Status,HTTP,Requested URL,Final URL,Assertion,Engine,Animations,
    #   Motion Not Suppressed,Autoplay No Control,End State Committed,Elements Checked,
    #   Text Invisible,Focus Indicator Lost,Colour Only,Ink Burning,Print Overflow,Severity,
    #   Evidence,Notes
    em = {"header": EMULATION_HEADER}
    _id = "200,https://a/d,https://a/d,heading 'D',chromium"
    EMULATION_CLEAN = f"/d,reduced-motion,Emulated,{_id},4,0,0,Pass,,,,,,,none,,"

    expect_clean("emulation: a clean reduced-motion route", f"{EMULATION_CLEAN}\n", **em)
    expect_clean(
        "emulation: a route that simply does not animate (0 is a real result)",
        f"/static,reduced-motion,Emulated,{_id},0,0,0,Not run,,,,,,,none,,\n",
        **em,
    )
    expect_clean(
        "emulation: a clean forced-colors route",
        f"/d,forced-colors,Emulated,{_id},,,,,120,0,0,0,,,none,,\n",
        **em,
    )
    expect_clean(
        "emulation: a clean print route",
        f"/d,print,Emulated,{_id},,,,,90,,,,0,0,none,,\n",
        **em,
    )

    # -- THE ADVISORY BOUNDARY, both directions. SC 2.3.3 is Level AAA, so motion that ignores the
    # preference is counted and reported but must NOT be graded a defect. This pair is why the
    # profile has the shape it has; deleting either half reopens the hole.
    expect_clean(
        "emulation: unsuppressed motion recorded as advisory (SC 2.3.3 is AAA)",
        f"/d,reduced-motion,Emulated,{_id},6,3,0,Pass,,,,,,,none,,"
        "spinner and skeleton shimmer ignore the preference\n",
        **em,
    )
    expect_findings(
        "emulation: an AAA advisory inflated into an S1 defect",
        f"/d,reduced-motion,Emulated,{_id},6,3,0,Pass,,,,,,,S1,e.png,shimmer animates\n",
        contains="Level AAA", count=1, **em,
    )
    expect_findings(
        "emulation: a print nit inflated into a defect (no WCAG upstream at all)",
        f"/d,print,Emulated,{_id},,,,,90,,,,4,2,S1,e.png,dark hero burns ink\n",
        contains="no WCAG success criterion covers print output", count=1, **em,
    )
    expect_findings(
        "emulation: an advisory count with no Notes is unactionable",
        f"/d,reduced-motion,Emulated,{_id},6,3,0,Pass,,,,,,,none,,\n",
        contains="an advisory finding is still a finding", count=1, **em,
    )

    # -- what DOES gate --
    expect_findings(
        "emulation: >5s autoplay with no control called clean (SC 2.2.2 is Level A)",
        f"/d,reduced-motion,Emulated,{_id},6,0,2,Pass,,,,,,,none,,carousel\n",
        contains="is S1", count=1, **em,
    )
    expect_clean(
        "emulation: >5s autoplay correctly graded S1",
        f"/d,reduced-motion,Emulated,{_id},6,0,2,Pass,,,,,,,S1,e.png,"
        "hero carousel loops with no pause control\n",
        **em,
    )
    expect_findings(
        "emulation: a state change that never commits called clean",
        f"/d,reduced-motion,Emulated,{_id},2,0,0,Fail,,,,,,,none,,\n",
        contains="is S1", count=1, **em,
    )
    expect_findings(
        "emulation: a box-shadow-only focus ring lost under forced colors, called clean",
        f"/d,forced-colors,Emulated,{_id},,,,,120,0,7,0,,,none,,\n",
        contains="is S1", count=1, **em,
    )
    expect_clean(
        "emulation: focus rings lost under forced colors, correctly graded",
        f"/d,forced-colors,Emulated,{_id},,,,,120,0,7,0,,,S1,e.png,"
        "all buttons ring via box-shadow with no outline\n",
        **em,
    )
    expect_findings(
        "emulation: colour-only meaning called clean (SC 1.4.1 is Level A)",
        f"/d,forced-colors,Emulated,{_id},,,,,40,0,0,5,,,none,,\n",
        contains="is S1", count=1, **em,
    )
    expect_findings(
        "emulation: unreadable text under forced colors called clean",
        f"/d,forced-colors,Emulated,{_id},,,,,40,9,0,0,,,none,,\n",
        contains="is S1", count=1, **em,
    )

    # -- THE MODE CONTRACT: a count from a condition the row never emulated --
    expect_findings(
        "emulation: a print row carrying a forced-colors count",
        f"/d,print,Emulated,{_id},,,,,90,,,3,0,0,none,,x\n",
        contains="never emulated the condition", count=1, **em,
    )
    expect_findings(
        "emulation: a forced-colors row carrying an animation count",
        f"/d,forced-colors,Emulated,{_id},5,,,,120,0,0,0,,,none,,\n",
        contains="never emulated the condition", count=1, **em,
    )
    expect_findings(
        "emulation: a print row carrying a reduced-motion verdict",
        f"/d,print,Emulated,{_id},,,,Pass,90,,,,0,0,none,,\n",
        contains="never emulated the condition", count=1, **em,
    )
    expect_findings(
        "emulation: a reduced-motion row that recorded no verdict at all",
        f"/d,reduced-motion,Emulated,{_id},4,0,0,,,,,,,,none,,\n",
        contains="no End State Committed verdict", count=1, **em,
    )

    # -- THE WEBKIT CEILING, and its near-miss. WebKit answers the forced-colors media query but
    # applies none of the forcing, so a result there reports clean on a broken app. Reduced motion
    # is purely author-side, so the SAME engine is perfectly valid for that mode -- which is what
    # makes this a real carve-out rather than "webkit is unsupported".
    expect_findings(
        "emulation: forced-colors result on webkit is a platform ceiling",
        "/d,forced-colors,Emulated,200,https://a/d,https://a/d,heading 'D',webkit,,,,,"
        "120,0,0,0,,,none,,\n",
        contains="platform ceiling", count=1, **em,
    )
    expect_clean(
        "emulation: forced-colors on webkit recorded Blocked instead",
        "/d,forced-colors,Blocked,200,https://a/d,https://a/d,heading 'D',webkit,,,,,"
        ",,,,,,none,,webkit implements no forced-color-adjust; ran chromium instead\n",
        **em,
    )
    expect_clean(
        "emulation: reduced-motion on webkit is fine (author-side only)",
        "/d,reduced-motion,Emulated,200,https://a/d,https://a/d,heading 'D',webkit,"
        "3,0,0,Pass,,,,,,,none,,\n",
        **em,
    )

    # -- denominators: sampling stays impossible to hide --
    expect_findings(
        "emulation: more unsuppressed animations than animations running",
        f"/d,reduced-motion,Emulated,{_id},2,5,0,Pass,,,,,,,none,,five\n",
        contains="cannot exceed the inventory", count=1, **em,
    )
    expect_findings(
        "emulation: more lost focus rings than elements inspected",
        f"/d,forced-colors,Emulated,{_id},,,,,10,0,25,0,,,S1,e.png,twenty-five\n",
        contains="cannot exceed the inventory", count=1, **em,
    )
    expect_findings(
        "emulation: forced-colors row that inspected nothing",
        f"/d,forced-colors,Emulated,{_id},,,,,0,0,0,0,,,none,,\n",
        contains="inspected nothing", count=1, **em,
    )
    # The print mode shares `Elements Checked` as its denominator, so it needs its own bound
    # fixture -- the forced-colors one above exercises a different pair of columns.
    expect_findings(
        "emulation: more print overflows than elements inspected",
        f"/d,print,Emulated,{_id},,,,,12,,,,0,30,none,,thirty\n",
        contains="cannot exceed the inventory", count=1, **em,
    )
    expect_findings(
        "emulation: an end-state verdict outside the vocabulary",
        f"/d,reduced-motion,Emulated,{_id},4,0,0,Committed,,,,,,,none,,\n",
        contains="is not one of Pass / Fail / Not run", count=1, **em,
    )
    expect_findings(
        "emulation: a counter filled with placeholder text",
        f"/d,forced-colors,Emulated,{_id},,,,,120,n/a,0,0,,,none,,\n",
        contains="records no number", count=1, **em,
    )

    # -- vocabulary --
    expect_findings(
        "emulation: an unknown Mode",
        f"/d,dark-mode,Emulated,{_id},,,,,,,,,,,none,,\n",
        contains="is not one of", count=1, **em,
    )
    expect_findings(
        "emulation: no Mode at all",
        f"/d,,Emulated,{_id},4,0,0,Pass,,,,,,,none,,\n",
        contains="no Mode", count=1, **em,
    )
    expect_findings(
        "emulation: no Engine recorded",
        "/d,forced-colors,Emulated,200,https://a/d,https://a/d,heading 'D',,,,,,"
        "120,0,0,0,,,none,,\n",
        contains="no Engine", count=1, **em,
    )
    expect_clean(
        "emulation: a Blocked row still says what it saw",
        "/d,print,Blocked,none,https://a/d,https://a/d,,chromium,,,,,,,,,,,none,,"
        "navigation timed out\n",
        **em,
    )

    # ---- client-side performance capture (#117) --------------------------------------
    # Column order: Route,State,Status,HTTP,Requested URL,Final URL,Assertion,Engine,Samples,
    #   TTFB ms,LCP ms,LCP Element,CLS,CLS Budget,Requests,Transfer KB,Opaque Requests,
    #   Largest Resource KB,Oversized Requests,Fonts No Swap,Render Blocking,Interaction Probe,
    #   Severity,Evidence,Notes
    pf = {"header": PERF_HEADER}
    _pnav = "Measured,200,https://a/d,https://a/d,heading 'D'"
    _pev = "qa/reports/run-1/results.jsonl"
    PERF_CLEAN = (
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},"
    )

    expect_clean("perf: a clean chromium route", f"{PERF_CLEAN}\n", **pf)

    # -- THE ENGINE CAPABILITY CONTRACT, and the carve-out that proves it is not "webkit is
    # unsupported". LCP shipped in Firefox 122 and Safari 26.2, so it is REQUIRED on every engine;
    # layout-shift and renderBlockingStatus are Chromium-only, so those columns must be blank
    # off chromium. Both halves matter: without the first this becomes an engine ban, and without
    # the second a `CLS 0` from an observer that never existed reads as a perfectly stable page.
    expect_clean(
        "perf: firefox row measures LCP and leaves the Chromium-only columns blank",
        f"/d,default,{_pnav},firefox,3,180,1420,img.hero,,,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        **pf,
    )
    expect_clean(
        "perf: webkit measures LCP too (Safari 26.2 shipped it) -- not an unsupported engine",
        f"/d,default,{_pnav},webkit,3,210,1650,h1.title,,,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        **pf,
    )
    expect_findings(
        "perf: CLS 0 on firefox, from an observer firefox does not implement",
        f"/d,default,{_pnav},firefox,3,180,1420,img.hero,0,0.1,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        contains="an API that does not exist", count=2, **pf,
    )
    expect_findings(
        "perf: renderBlockingStatus counted on webkit, where it does not exist",
        f"/d,default,{_pnav},webkit,3,180,1420,img.hero,,,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="Render Blocking records", count=1, **pf,
    )
    expect_findings(
        "perf: chromium row that recorded no CLS at all",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="finite, non-negative decimal", count=1, **pf,
    )
    expect_findings(
        "perf: chromium row that recorded no render-blocking count",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        contains="no Render Blocking count", count=1, **pf,
    )

    # -- THE CEILING. This profile's distinctive direction: #114/#115 stop a row grading a defect
    # DOWN, #116 stops it grading an advisory UP, and here nothing may be graded S1 at all. No
    # standard mandates a performance budget, and a localhost timing cannot establish one.
    expect_findings(
        "perf: a client-side timing graded S1",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.34,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,S1,{_pev},hero image shifts the headline\n",
        contains="ceiling here is S2", count=1, **pf,
    )

    # -- TIMINGS ARE TRENDED, NEVER GRADED. The pair is the whole "advisory" claim: a 9.4s LCP is
    # recorded and left alone, and grading it a defect is rejected.
    expect_clean(
        "perf: a slow LCP recorded and not graded",
        f"/d,default,{_pnav},chromium,3,180,9400,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        **pf,
    )
    expect_findings(
        "perf: a slow LCP graded S2 on a row whose gating counters are all 0",
        f"/d,default,{_pnav},chromium,3,180,9400,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,S2,{_pev},LCP is slow on this route\n",
        contains="environment-sensitive", count=1, **pf,
    )

    # -- WHAT DOES GATE: a shift the page really performs, against the budget the row carries.
    expect_findings(
        "perf: CLS over the row's own budget, called clean",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.34,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="is S2", count=1, **pf,
    )
    expect_clean(
        "perf: CLS over budget, correctly graded",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.34,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,S2,{_pev},webfont swap reflows the article body\n",
        **pf,
    )
    expect_clean(
        "perf: a relaxed budget is visible in the row rather than hidden in config",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.34,0.5,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        **pf,
    )
    expect_findings(
        "perf: a request over the byte budget, called clean",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,1900,0,1200,3,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="is S2", count=1, **pf,
    )

    # -- THE FALSE-CLEAN BYTE VERDICT. transferSize is 0 for a cross-origin asset with no
    # Timing-Allow-Origin and 0 for a cache hit, so "nothing over budget" can mean "nothing
    # MEASURABLE over budget". Only the clean direction is rejected: an incomplete positive
    # finding is still a real one, and that near-miss is what keeps the rule from being a ban.
    expect_findings(
        "perf: no oversized requests, among the ones that reported a size at all",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,9,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="bytes nobody measured", count=1, **pf,
    )
    expect_clean(
        "perf: opaque requests alongside a real oversized finding is incomplete, not false",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,9,180,2,0,0,"
        f"separate-visit,S2,{_pev},vendor.js and the hero jpeg are both over budget\n",
        **pf,
    )

    # -- denominators --
    expect_findings(
        "perf: more opaque requests than requests",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,40,180,2,0,0,"
        f"separate-visit,S2,{_pev},two over budget\n",
        contains="cannot exceed the inventory", count=1, **pf,
    )
    expect_findings(
        "perf: one resource larger than the whole page transfer (encoded/decoded mix-up)",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,300,0,900,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="cannot exceed the inventory", count=1, **pf,
    )
    expect_findings(
        "perf: a route that was never sampled",
        f"/d,default,{_pnav},chromium,0,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="Out of Scope", count=1, **pf,
    )
    expect_findings(
        "perf: a route whose own document request was never counted",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,0,0,0,0,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="Out of Scope", count=1, **pf,
    )

    # -- a number with no attributable cause is the complaint #117 exists to answer --
    expect_findings(
        "perf: an LCP time with nothing to attribute it to",
        f"/d,default,{_pnav},chromium,3,180,1420,,0.02,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="a number, not a finding", count=1, **pf,
    )

    # -- THE PROBE ORDERING HAZARD. Playwright's click is trusted, so it terminates LCP observation
    # and marks shifts within 500 ms hadRecentInput. A same-visit probe truncates the LCP printed
    # two columns to its left.
    expect_findings(
        "perf: the interaction probe ran on the same visit as the metric read",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"same-visit,none,{_pev},\n",
        contains="truncated", count=1, **pf,
    )
    expect_clean(
        "perf: no probe was run at all -- honest, and leaves the metrics intact",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"not run,none,{_pev},\n",
        **pf,
    )
    expect_findings(
        "perf: no Interaction Probe recorded",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f",none,{_pev},\n",
        contains="no Interaction Probe", count=1, **pf,
    )
    expect_findings(
        "perf: an Interaction Probe outside the vocabulary",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        f"inp,none,{_pev},\n",
        contains="is not one of", count=1, **pf,
    )

    # -- advisory causes: counted, never graded, and never a bare number --
    expect_clean(
        "perf: fonts without font-display recorded as advisory",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,4,0,"
        f"separate-visit,none,{_pev},Inter and Lora declare no font-display\n",
        **pf,
    )
    expect_findings(
        "perf: an advisory count with no Notes is unactionable",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,4,0,"
        f"separate-visit,none,{_pev},\n",
        contains="an advisory finding is still a finding", count=1, **pf,
    )
    # The rule covers BOTH advisory columns, so both get a fixture -- exercising one and claiming
    # the rule is tested is the coverage gap this repo's own review skill names.
    expect_findings(
        "perf: a render-blocking count with no Notes is unactionable",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,6,"
        f"separate-visit,none,{_pev},\n",
        contains="Render Blocking above 0", count=1, **pf,
    )
    expect_clean(
        "perf: render-blocking stylesheets recorded as advisory, never graded",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,6,"
        f"separate-visit,none,{_pev},six blocking stylesheets in the document head\n",
        **pf,
    )

    # -- persistence is acceptance criterion 3, so it is enforced rather than described --
    expect_findings(
        "perf: measured with nothing persisted to compare the next run against",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,412,0,180,0,0,0,"
        "separate-visit,none,,\n",
        contains="not a trend", count=1, **pf,
    )

    # -- vocabulary and placeholders --
    expect_findings(
        "perf: no Engine recorded",
        f"/d,default,{_pnav},,3,180,1420,img.hero,,,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        contains="no Engine", count=1, **pf,
    )
    expect_findings(
        "perf: an unknown Engine",
        f"/d,default,{_pnav},brave,3,180,1420,img.hero,,,34,412,0,180,0,0,,"
        f"separate-visit,none,{_pev},\n",
        contains="is not one of", count=1, **pf,
    )
    expect_findings(
        "perf: a counter filled with placeholder text",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,0.02,0.1,34,n/a,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="records no number", count=1, **pf,
    )
    # `float()` accepts both of these and they would sail through a `>` comparison as measurements.
    expect_findings(
        "perf: CLS recorded as nan",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,nan,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="finite, non-negative decimal", count=1, **pf,
    )
    expect_findings(
        "perf: a negative CLS",
        f"/d,default,{_pnav},chromium,3,180,1420,img.hero,-0.4,0.1,34,412,0,180,0,0,0,"
        f"separate-visit,none,{_pev},\n",
        contains="finite, non-negative decimal", count=1, **pf,
    )
    expect_clean(
        "perf: a Blocked row still says what it saw",
        "/d,default,Blocked,none,https://a/d,https://a/d,,firefox,,,,,,,,,,,,,,,,,"
        "the dev server never answered\n",
        **pf,
    )

    # ---- the Source vocabulary and the doctrine that names it must agree -------------
    # A pre-existing drift found while adding `emulation`: `keyboard` and `forms` were accepted by
    # the checker for a whole release while qa-reporter.md's own list of sources denied they
    # existed. Prose is what the agent reads, so a source missing from it is a pass whose findings
    # never reach the rollup -- claims-vs-enforcement, in the direction that silently drops data.
    _tick()
    reporter = Path(__file__).resolve().parents[1] / "agents" / "qa-reporter.md"
    if not reporter.is_file():
        FAILURES.append(f"cannot find {reporter} to cross-check the Source vocabulary")
    else:
        lines = reporter.read_text(encoding="utf-8").splitlines()
        start = next((i for i, ln in enumerate(lines) if "every finding source" in ln), None)
        if start is None:
            FAILURES.append(
                "qa-reporter.md no longer states which finding sources the rule applies to -- "
                "that sentence IS the agent's copy of FINDING_SOURCES"
            )
        else:
            # The bullet WRAPS, so read its continuation lines too. Reading one line found six
            # sources "missing" that were simply on the next line -- a checker that mis-parses its
            # input is indistinguishable from one reporting a real defect.
            bullet = [lines[start]]
            for line in lines[start + 1:]:
                if not line.startswith("  ") or line.strip().startswith("- "):
                    break
                bullet.append(line.strip())
            # After the FIRST em-dash (later prose contains more), up to the end of that sentence.
            listing = " ".join(bullet).split("—", 1)[-1].split(".", 1)[0]
            named = {word.strip(" *_`") for word in listing.split(",")}
            unlisted = ve.FINDING_SOURCES - named
            if unlisted:
                FAILURES.append(
                    f"qa-reporter.md's finding-source list omits {sorted(unlisted)}, which "
                    "validate_evidence.py accepts as a Source -- those passes' findings would "
                    "never be rolled up"
                )

    # ---- profile detection is by header, and must never guess -----------------------
    _tick()
    detected = []
    for prof, body in ((ve.FUNCTIONAL, GOOD_PASS), (ve.A11Y, A11Y_CLEAN),
                      (ve.RUNTIME, RUNTIME_CLEAN), (ve.KEYBOARD, KEYBOARD_CLEAN),
                      (ve.FORMS, FORMS_CLEAN), (ve.EMULATION, EMULATION_CLEAN),
                      (ve.PERF, PERF_CLEAN), (ve.FINDINGS, NAVBAR)):
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
        # Both new passes are a11y-auditor's: the keyboard walk and the forms error contract are
        # accessibility contracts, and the modal-CRUD 422 expectation is referenced to
        # functional-tester rather than restated, so there stays one copy of it.
        ("a11y-auditor.md", ve.KEYBOARD),
        ("a11y-auditor.md", ve.FORMS),
        # The emulated-media pass is a11y-auditor's too: reduced motion and colour-only meaning are
        # accessibility contracts, and the print mode rides along because it is the same
        # emulate-then-assert mechanism, not because it is an a11y concern.
        ("a11y-auditor.md", ve.EMULATION),
        # The client-side capture is perf-tester's, and lives beside the k6 load profile on
        # purpose: the two are the easiest pair in this plugin to confuse, and #117's fourth
        # acceptance criterion is that they are documented as distinct.
        ("perf-tester.md", ve.PERF),
        ("qa-reporter.md", ve.FINDINGS),
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
