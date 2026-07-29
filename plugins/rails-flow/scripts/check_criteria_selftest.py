#!/usr/bin/env python3
"""Prove every acceptance-criteria rule fires -- and, harder, that it stays silent.

Run:  python3 check_criteria.py --selftest   (or execute this file directly)

The silent direction decides whether this survives. A criteria checker that flags well-written
criteria gets switched off after the third false positive, and then the flow is back to
post-hoc goals. So the rubber-stamp list has near-miss fixtures: "properly" must not fire
inside "property", and a criterion whose observable legitimately contains "not found" (a 404
page IS the observable) must pass.

Fixtures are adversarial rather than realistic -- a realistic criteria file exercises only the
happy path, which is the same blind spot the rule itself is about.

Costs nothing: no network, no Rails, no bundler.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_criteria as cc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

GOOD = (
    "## Sign-in\n"
    "- **AC-1** Given a registered user, when they submit the sign-in form with a correct "
    "password, then the browser lands on /dashboard and the header shows their name\n"
    "- **AC-2** Given a wrong password, when the user submits the sign-in form, then the page "
    "shows 'wrong email or password' and does NOT redirect to the dashboard [error]\n"
)


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _write(body: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-criteria-"))
    p = root / "acceptance.md"
    p.write_text(body, encoding="utf-8")
    return p


def expect_clean(label: str, body: str, *, specs: Path | None = None) -> None:
    _tick()
    try:
        findings = cc.check(cc.parse(_write(body)), specs)
    except cc.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_findings(label: str, body: str, *, contains: str, count: int | None = None,
                    specs: Path | None = None) -> None:
    _tick()
    try:
        findings = cc.check(cc.parse(_write(body)), specs)
    except cc.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings omit {contains!r}: {blob}")
    if count is not None and len(findings) != count:
        FAILURES.append(f"{label}: expected {count}, got {len(findings)}: {blob}")


def expect_unusable(label: str, body: str, *, contains: str) -> None:
    _tick()
    try:
        cc.parse(_write(body))
    except cc.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message omits {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, input was accepted")


def run() -> int:
    # ---- the silence proof --------------------------------------------------------------
    expect_clean("well-written criteria", GOOD)

    # ---- the shape ---------------------------------------------------------------------
    expect_findings(
        "no Given/when/then at all -- the issue's 'login works'",
        "## Sign-in\n- **AC-1** login works [error]\n",
        contains="missing Given, when, then",
    )
    expect_findings(
        "missing only the then clause",
        "## Sign-in\n- **AC-1** Given a user, when they submit the form, the page updates [error]\n",
        contains="missing then",
    )
    expect_findings(
        "trivial when clause",
        "## Sign-in\n- **AC-1** Given a user, when submitted, then the page shows an error "
        "message [error]\n",
        contains="names no real action",
    )
    expect_findings(
        "trivial then clause",
        "## Sign-in\n- **AC-1** Given a bad password, when the user submits the form, then it "
        "fails\n",
        contains="names no real observable",
    )

    # ---- rubber-stamp phrasings: the issue's own 'bad' list -----------------------------
    for phrase in ("works correctly", "handles errors", "gracefully", "as expected",
                   "no errors", "is correct"):
        expect_findings(
            f"rubber-stamp observable {phrase!r}",
            f"## Unit\n- **AC-1** Given an invalid invoice, when POST /invoices runs, then it "
            f"{phrase} and nothing breaks [error]\n",
            contains="rubber-stamp phrasing",
        )

    # ---- near misses: the rule must NOT fire on legitimate criteria --------------------
    # "property" contains "properly"? No -- but "properly" as a substring of another word is
    # exactly the kind of match that turns a useful rule into a disabled one. Pin it.
    expect_clean(
        "the word 'property' does not trip the 'properly' rule",
        "## Listings\n- **AC-1** Given a listing with no photos, when the agent opens the "
        "property page, then the gallery region shows the 'no photos yet' empty state [error]\n",
    )
    expect_clean(
        "'not found' is a legitimate observable (the 404 page IS the expected result)",
        "## Routing\n- **AC-1** Given an unknown slug, when GET /articles/nope runs, then the "
        "response is 404 and the page renders the 'not found' design [error]\n",
    )
    expect_clean(
        "'workspace' does not trip the 'works' rule",
        "## Workspaces\n- **AC-1** Given a member of two workspaces, when they switch "
        "workspace, then the sidebar lists only the new workspace's projects\n"
        "- **AC-2** Given a non-member, when they request another workspace, then the response "
        "is 403 and no project names appear [error]\n",
    )

    # ---- every unit needs an error path ------------------------------------------------
    expect_findings(
        "happy-path-only unit",
        "## Sign-in\n- **AC-1** Given a registered user, when they submit valid credentials, "
        "then the browser lands on /dashboard\n",
        contains="no error-path criterion",
        count=1,
    )
    expect_clean(
        "an explicit [error] tag satisfies it",
        "## Sign-in\n- **AC-1** Given a registered user, when they submit valid credentials, "
        "then the browser lands on /dashboard\n"
        "- **AC-2** Given a locked account, when they submit valid credentials, then the page "
        "shows 'account locked' and stays on /sign-in [error]\n",
    )
    expect_clean(
        "an untagged failure case still counts (keyword fallback)",
        "## Invoices\n- **AC-1** Given an invoice with line items, when POST /invoices runs, "
        "then the response is 201 and the invoice appears in the index\n"
        "- **AC-2** Given an invoice with no line items, when POST /invoices runs, then the "
        "response is 422 and the modal re-renders with 'must have at least one line item'\n",
    )
    expect_findings(
        "a second unit without an error path is caught even when the first has one",
        GOOD + "## Invoices\n- **AC-3** Given a draft invoice, when the user clicks Send, then "
        "the status column reads 'sent'\n",
        contains="'Invoices'",
        count=1,
    )

    # ---- duplicate ids would make the spec mapping ambiguous --------------------------
    expect_findings(
        "duplicate criterion id",
        "## Sign-in\n- **AC-1** Given a user, when they submit the form, then the dashboard "
        "loads\n- **AC-1** Given a bad password, when they submit the form, then an error "
        "message appears [error]\n",
        contains="reuses an id",
    )

    # ---- unusable input: never report clean over something unparsed ------------------
    expect_unusable("no criteria at all", "## Sign-in\nSome prose, no ids.\n", contains="no `AC-n` criteria")
    expect_unusable("empty file", "", contains="no `AC-n` criteria")
    expect_unusable(
        "two ids on one line makes the mapping ambiguous",
        "## Sign-in\n- **AC-1** and **AC-2** Given a user, when they submit, then it loads\n",
        contains="one criterion per line",
    )
    _tick()
    try:
        cc.parse(Path(tempfile.mkdtemp(prefix="railsflow-criteria-")) / "absent.md")
        FAILURES.append("missing file: expected UNUSABLE")
    except cc.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- the 1:1 mapping check --------------------------------------------------------
    spec_root = Path(tempfile.mkdtemp(prefix="railsflow-spec-")) / "spec" / "requests"
    spec_root.mkdir(parents=True)
    (spec_root / "sign_in_spec.rb").write_text(
        'RSpec.describe "sign in" do\n'
        '  it "AC-1 lands on the dashboard" do\n  end\n'
        '  it "AC-2 rejects a wrong password" do\n  end\nend\n',
        encoding="utf-8",
    )
    specs = spec_root.parent.parent
    expect_clean("every criterion cited by a spec", GOOD, specs=specs)
    expect_findings(
        "a criterion no spec cites",
        GOOD + "## Invoices\n- **AC-3** Given no line items, when POST /invoices runs, then the "
        "response is 422 and an error message appears [error]\n",
        contains="no spec under",
        specs=specs,
    )
    expect_findings(
        "a missing spec root must fail closed, not pass silently",
        GOOD,
        contains="does not exist",
        specs=Path(tempfile.mkdtemp(prefix="railsflow-nospec-")) / "absent",
    )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_criteria selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
