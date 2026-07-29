#!/usr/bin/env python3
"""Reject a functional-test report whose evidence was never validated.

Run:  python3 validate_evidence.py qa/manual-tests/<date>-<slug>-summary.csv
      python3 validate_evidence.py --selftest

The bug this exists for (qa-flow #106): `functional-tester` was told "every finding
needs a screenshot" and nothing more. A screenshot of a 404, an error page, a redirect
target, or a still-loading skeleton sits in the evidence folder looking exactly as
legitimate as the real thing -- so it manufactures a false PASS, which is worse than no
evidence because the report looks complete and green. A real audit shipped 12 such
captures out of 66 and a human caught it by eye.

WHAT THIS GUARANTEES
    No Pass/Fail row can OMIT its HTTP status, requested/final URL, or expected-content
    assertion; no row can claim Pass on a non-2xx/3xx status or on a silent redirect;
    a Blocked row must still record what it saw.

WHAT IT DOES NOT
    It cannot tell whether a recorded status is TRUTHFUL -- an agent that writes
    `200` for a page it never loaded defeats it -- and it never sees the screenshots,
    so "not still loading" stays agent-side judgement. It closes the omission hole,
    which is the one that produced the false PASS. It is not a substitute for looking,
    and the agent doctrine says so in the same words.

DELIBERATELY NOT DONE: sniffing the row for "404" / "not found" to disqualify it. The
naive version of this fix did exactly that and wrongly excluded four VALID cases -- real
404-page *designs*, which return HTTP 200 and legitimately contain that text. Status
alone is insufficient (error pages return 200); text alone is insufficient (error-page
designs contain error text). The expected-content assertion is the reliable signal
because it comes from the case's own expectation, not from a keyword list. There is a
fixture pinning this (`selftest: intentional 404 design`); do not "improve" it away.

Exit codes:  0 clean · 1 findings · 2 unusable input (bad header / no data rows / no file)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# The fixed contract, mirrored in functional-tester.md. Order matters: the header must
# match exactly, so a template drift is a loud failure (exit 2) rather than a checker
# that quietly matches nothing and reports clean.
COLUMNS = [
    "Test ID",
    "Title",
    "Menu",
    "Status",
    "HTTP",
    "Requested URL",
    "Final URL",
    "Assertion",
    "Screenshot",
    "Notes",
]

# Statuses that assert a case was actually executed -- these carry the burden of proof.
RESULT_STATUSES = {"pass", "fail"}
# Statuses that assert it was not -- honest, but must still record what was seen.
BLOCKED_STATUS = "blocked"
SKIPPED_STATUS = "out of scope"
VALID_STATUSES = RESULT_STATUSES | {BLOCKED_STATUS, SKIPPED_STATUS}


class Unusable(Exception):
    """The input cannot be checked at all -- never report clean for it."""


def _norm(value: str | None) -> str:
    return (value or "").strip()


def load_rows(path: Path) -> list[dict[str, str]]:
    """Parse the summary CSV, or raise Unusable.

    Refusing an unreadable report is the point: a checker that reports clean on input it
    never read is worse than no checker (the lesson from lint_markdown_shell's coverage
    audit, which silently skipped 11 blocks in 7 files).
    """
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise Unusable(f"{path} is empty -- no header row") from None

        actual = [_norm(cell) for cell in header]
        if actual != COLUMNS:
            missing = [c for c in COLUMNS if c not in actual]
            extra = [c for c in actual if c not in COLUMNS]
            detail = []
            if missing:
                detail.append(f"missing {missing}")
            if extra:
                detail.append(f"unexpected {extra}")
            if not detail:
                detail.append("columns are out of order")
            raise Unusable(
                f"{path} header does not match the contract ({'; '.join(detail)}). "
                f"Expected exactly: {','.join(COLUMNS)}"
            )

        rows = []
        for raw in reader:
            cells = [_norm(c) for c in raw]
            if not any(cells):
                continue  # blank line -- not a result, and not an error either
            # Pad short rows rather than letting zip() drop keys: a truncated row must
            # surface as "field missing" findings, never as a KeyError crash (a checker
            # that dies on malformed input has not checked it).
            if len(cells) < len(COLUMNS):
                cells += [""] * (len(COLUMNS) - len(cells))
            row = dict(zip(COLUMNS, cells))
            # An over-long row means the writer's columns have drifted from the contract,
            # or an unescaped comma split a field. Either way its cells are not where we
            # think they are, so record it instead of silently truncating.
            row["__overflow__"] = str(len(cells) - len(COLUMNS)) if len(cells) > len(COLUMNS) else ""
            rows.append(row)

    if not rows:
        raise Unusable(
            f"{path} has a valid header but zero data rows -- refusing to bless a report "
            "with no results in it"
        )
    return rows


def _http_ok(value: str) -> bool:
    """True only for an integer status in the 2xx/3xx range."""
    try:
        code = int(value)
    except ValueError:
        return False
    return 200 <= code <= 399


def check_row(row: dict[str, str], line: int) -> list[str]:
    """Findings for one row. Empty list = this row is honest."""
    findings: list[str] = []
    ident = row["Test ID"] or row["Title"] or "<unnamed>"
    where = f"row {line} ({ident})"
    status = row["Status"].lower()

    if row.get("__overflow__"):
        findings.append(
            f"{where}: has {row['__overflow__']} cell(s) more than the {len(COLUMNS)}-column "
            "contract -- an unescaped comma or a drifted template means these fields are not "
            "the fields they appear to be"
        )

    if status not in VALID_STATUSES:
        # Return here (an unrecognised status makes the per-status rules meaningless) but
        # keep anything already found -- discarding it would hide a second defect.
        findings.append(
            f"{where}: Status {row['Status']!r} is not one of "
            "Pass / Fail / Blocked / Out of Scope"
        )
        return findings

    if status == SKIPPED_STATUS:
        # Not tested and not claimed to be -- nothing to prove.
        return findings

    if status == BLOCKED_STATUS:
        # A blocked case must still say what it saw, or "Blocked" becomes a way to
        # record nothing at all and still satisfy the checker.
        if not row["HTTP"]:
            findings.append(f"{where}: Blocked without an HTTP status (use the code, or `none` if navigation never returned)")
        if not row["Final URL"]:
            findings.append(f"{where}: Blocked without a Final URL")
        if not row["Notes"]:
            findings.append(f"{where}: Blocked without Notes saying what was missing")
        return findings

    # Pass / Fail -- the rows that assert the page was actually tested.
    if not row["HTTP"]:
        findings.append(f"{where}: {row['Status']} without an HTTP status recorded from the navigation response")
    elif not _http_ok(row["HTTP"]):
        findings.append(
            f"{where}: {row['Status']} on HTTP {row['HTTP']} -- a non-2xx/3xx page was not "
            f"the page under test; this is Blocked, not {row['Status']}"
        )

    if not row["Requested URL"]:
        findings.append(f"{where}: {row['Status']} without a Requested URL")
    if not row["Final URL"]:
        findings.append(f"{where}: {row['Status']} without a Final URL")

    if not row["Assertion"]:
        findings.append(
            f"{where}: {row['Status']} without an expected-content assertion -- the only "
            "signal that distinguishes the page under test from an error page that also "
            "returns 200"
        )

    # A silent redirect means a different page was tested than intended. Acknowledged
    # redirects are fine and common (canonical slugs, trailing slashes, post-login).
    req, fin = row["Requested URL"], row["Final URL"]
    if req and fin and req != fin and not row["Notes"]:
        findings.append(
            f"{where}: redirected {req} -> {fin} with no Notes -- a different page was "
            "tested than requested; explain why that is expected or mark it Blocked"
        )

    if status == "fail" and not row["Screenshot"]:
        findings.append(f"{where}: Fail without a Screenshot -- a failure without evidence is not a valid finding")

    return findings


def validate(path: Path) -> list[str]:
    rows = load_rows(path)
    findings: list[str] = []
    for offset, row in enumerate(rows):
        findings.extend(check_row(row, line=offset + 2))  # +2: 1-indexed, past the header
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a functional-test summary CSV carries validated evidence."
    )
    parser.add_argument("csv_path", nargs="?", help="path to <date>-<slug>-summary.csv")
    parser.add_argument("--selftest", action="store_true", help="prove the rules fire AND stay silent")
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import validate_evidence_selftest as st

        return st.run()

    if not args.csv_path:
        parser.error("csv_path is required (or pass --selftest)")

    try:
        findings = validate(Path(args.csv_path))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    if findings:
        print(
            f"{len(findings)} evidence-validation finding(s) in {args.csv_path} -- "
            "results are not trustworthy as written:",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nFix the report, not this checker. A row that cannot carry a validated "
            "status/URL/assertion is a Blocked row.",
            file=sys.stderr,
        )
        return 1

    print(f"evidence validated: {args.csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
