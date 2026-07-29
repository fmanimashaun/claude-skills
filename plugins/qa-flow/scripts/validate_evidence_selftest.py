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

HEADER = ",".join(ve.COLUMNS)


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
        contains="more than the 10-column contract",
    )

    # ---- whitespace and Excel artefacts ---------------------------------------------
    expect_clean(
        "padded cells are normalised",
        "TC-100 , Create template , Templates , Pass , 200 , https://a/new , https://a/new , heading 'New' , , \n",
    )
    expect_clean("BOM header (Excel writes one) is still readable", f"{GOOD_PASS}\n", bom=True)
    expect_clean("blank lines between rows are skipped, not flagged", f"{GOOD_PASS}\n\n{GOOD_FAIL}\n")

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
    _tick()
    doctrine = Path(__file__).resolve().parents[1] / "agents" / "functional-tester.md"
    if not doctrine.is_file():
        FAILURES.append(f"cannot find {doctrine} to cross-check the column contract")
    elif HEADER not in doctrine.read_text(encoding="utf-8"):
        FAILURES.append(
            "functional-tester.md does not document the exact header this script enforces -- "
            f"the agent would write a CSV the checker rejects. Expected to find: {HEADER}"
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
