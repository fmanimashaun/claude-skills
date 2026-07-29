#!/usr/bin/env python3
"""Reject a QA evidence artifact whose pages were never validated as the pages under test.

Run:  python3 validate_evidence.py qa/manual-tests/<date>-<slug>-summary.csv
      python3 validate_evidence.py qa/reports/a11y-<slug>-pages.csv
      python3 validate_evidence.py qa/manual-tests/<date>-<slug>-runtime.csv
      python3 validate_evidence.py --selftest

The artifact kind is detected from the header, so callers never pass a --kind flag that
could disagree with the file. Unknown header => exit 2, never a silent pass.

The bug this exists for (qa-flow #106): `functional-tester` was told "every finding needs a
screenshot" and nothing more. A screenshot of a 404, an error page, a redirect target, or a
still-loading skeleton sits in the evidence folder looking exactly as legitimate as the real
thing -- so it manufactures a false PASS, which is worse than no evidence because the report
looks complete and green. A real audit shipped 12 such captures out of 66 and a human caught
it by eye.

`a11y-auditor` had the same hole for the same reason: an axe run against a 404 or a login
redirect returns REAL violations attributed to the wrong page, and then files them as
defects. Its rule shipped as prose first; this module is what makes it enforced, so qa-flow
does not have one validated evidence path and one unvalidated one.

The runtime profile (#109) closes the inverse hole: a page that IS the page under test, and
returns 200, while throwing uncaught exceptions or 404-ing its own script bundle. Validating
page identity says nothing about whether the page then worked.

WHAT THIS GUARANTEES
    No row asserting a page was tested/audited can OMIT its HTTP status, requested/final
    URL, or expected-content assertion; none can claim a result on a non-2xx/3xx status or
    on a silent redirect; a Blocked row must still record what it saw; and per-profile
    outcome fields (a screenshot on a Fail, the violation count and keyboard verdict on an
    audited page, the console/network counters on an observed route) cannot be left blank or
    filled with placeholder text. For a runtime row the SEVERITY IS RECOMPUTED from those
    counters, so the mapping is enforced rather than trusted: an uncaught exception or a
    failed document/script/stylesheet is S1 however the row grades itself.

WHAT IT DOES NOT
    It cannot tell whether a recorded status is TRUTHFUL -- an agent that writes `200` for
    a page it never loaded defeats it -- and it never opens the screenshots or the axe
    JSON, so "not still loading" stays agent-side judgement. It closes the omission hole,
    which is the one that produced the false PASS. It is not a substitute for looking, and
    the agent doctrine says so in the same words.

DELIBERATELY NOT DONE: sniffing a row for "404" / "not found" to disqualify it. The naive
version of this fix did exactly that and wrongly excluded four VALID cases -- real 404-page
*designs*, which return HTTP 200 and legitimately contain that text. Status alone is
insufficient (error pages return 200); text alone is insufficient (error-page designs
contain error text). The expected-content assertion is the reliable signal because it comes
from the case's own expectation, not from a keyword list. Fixtures pin this
(`selftest: intentional 404 design`); do not "improve" them away.

Exit codes:  0 clean · 1 findings · 2 unusable input (unknown header / no data rows / no file)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------------------
# Shared vocabulary. A "result" status asserts the page WAS exercised, so it carries the
# burden of proof. Blocked asserts it was not -- honest, but it must still record what it
# saw, or "Blocked" becomes a way to record nothing and still satisfy the checker.
# ---------------------------------------------------------------------------------------
BLOCKED_STATUS = "blocked"
SKIPPED_STATUS = "out of scope"


class Unusable(Exception):
    """The input cannot be checked at all -- never report clean for it."""


@dataclass(frozen=True)
class Profile:
    """One evidence artifact's contract. Adding a browser pass = adding a Profile."""

    name: str
    written_by: str
    columns: tuple[str, ...]
    result_statuses: frozenset[str]
    ident_columns: tuple[str, ...]
    # Extra, profile-specific checks for a row that claims a result. The shared
    # status/URL/assertion rules are applied to every profile before this runs.
    extra: Callable[[dict[str, str], str, str], list[str]] = field(default=lambda r, w, s: [])

    @property
    def valid_statuses(self) -> frozenset[str]:
        return self.result_statuses | {BLOCKED_STATUS, SKIPPED_STATUS}

    @property
    def header(self) -> str:
        return ",".join(self.columns)


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _has_digit(value: str) -> bool:
    return any(ch.isdigit() for ch in value)


# ---------------------------------------------------------------------------------------
# Profile: functional-tester's report summary
# ---------------------------------------------------------------------------------------
def _functional_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    if status == "fail" and not row["Screenshot"]:
        return [f"{where}: Fail without a Screenshot -- a failure without evidence is not a valid finding"]
    return []


FUNCTIONAL = Profile(
    name="functional",
    written_by="functional-tester",
    columns=(
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
    ),
    result_statuses=frozenset({"pass", "fail"}),
    ident_columns=("Test ID", "Title"),
    extra=_functional_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: a11y-auditor's per-page audit log
# ---------------------------------------------------------------------------------------
KEYBOARD_VERDICTS = {"pass", "fail", "not run"}


def _a11y_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """An audited page must report its outcome, not just that it was reached."""
    findings: list[str] = []

    violations = row["Violations"]
    if not violations:
        findings.append(
            f"{where}: audited without a Violations count -- an audit that records no "
            "outcome is indistinguishable from one that never ran"
        )
    elif not _has_digit(violations):
        # Rejects "TBD", "n/a", "-", "none" -- placeholder text that reads as a result.
        # A clean page is `0` (or `critical:0 serious:0`), which is a real, checkable claim.
        findings.append(
            f"{where}: Violations {violations!r} records no number -- use 0 for a clean "
            "page, or counts by impact"
        )

    keyboard = row["Keyboard"].lower()
    if not keyboard:
        findings.append(f"{where}: audited without a Keyboard verdict (Pass / Fail / Not run)")
    elif keyboard not in KEYBOARD_VERDICTS:
        findings.append(
            f"{where}: Keyboard {row['Keyboard']!r} is not one of Pass / Fail / Not run"
        )

    if not row["Evidence"]:
        findings.append(
            f"{where}: audited without an Evidence path (the axe results/screenshot that "
            "makes this row checkable by a human)"
        )

    return findings


A11Y = Profile(
    name="a11y",
    written_by="a11y-auditor",
    columns=(
        "Page",
        "State",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Violations",
        "Keyboard",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"audited"}),
    ident_columns=("Page", "State"),
    extra=_a11y_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: browser runtime capture -- console + network per route (#109)
#
# A page can return 200, render, and pass a scripted scenario while throwing uncaught
# exceptions, 404-ing its own script bundle, or violating CSP on every load. The Flowbite
# audit demonstrated it twice over: `Module not found: svgmap/dist/svgMap.min.css` and a
# repeating `TypeError: localStorage.getItem is not a function`, both on a route serving
# HTTP 200. A status-only check calls that page healthy.
#
# The counters are split by SEVERITY CONSEQUENCE rather than by event name, so the severity
# mapping in the issue is mechanically checkable from the row itself instead of trusted:
#
#   Page Errors        uncaught exception              -> S1 (broken even though it rendered)
#   Failed Critical    document / script / stylesheet  -> S1 (the page is missing its own code)
#   Console Errors     console.error                   -> S2
#   Failed Subresource image / font / media / other    -> S2
#   Console Warnings   console.warn                    -> informational, never gates
#
# A single "Failed Requests" column could not support that: losing the resource type loses
# the difference between a missing analytics pixel and a missing application bundle.
# ---------------------------------------------------------------------------------------
S1, S2, NO_SEVERITY = "s1", "s2", "none"
RUNTIME_SEVERITIES = {S1, S2, NO_SEVERITY}

# Counters that force a severity, mapped to the floor they force.
GATING_COUNTERS: tuple[tuple[str, str], ...] = (
    ("Page Errors", S1),
    ("Failed Critical", S1),
    ("Console Errors", S2),
    ("Failed Subresource", S2),
)
RUNTIME_COUNTERS = tuple(name for name, _ in GATING_COUNTERS) + ("Console Warnings",)


def _count(value: str) -> int | None:
    """A counter's integer value, or None when it records no number at all."""
    try:
        return int(value)
    except ValueError:
        return None


def _runtime_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """An observed route must report what the browser actually said, and grade it correctly."""
    findings: list[str] = []

    counts: dict[str, int] = {}
    for column in RUNTIME_COUNTERS:
        raw = row[column]
        if not raw:
            findings.append(
                f"{where}: observed without a {column} count -- a capture that records no "
                "counts is indistinguishable from one where the listeners never attached"
            )
            continue
        value = _count(raw)
        if value is None:
            # Rejects "none", "n/a", "-", "TBD": placeholder text that reads as a clean result.
            findings.append(
                f"{where}: {column} {raw!r} records no number -- use 0 for a clean route"
            )
            continue
        if value < 0:
            findings.append(f"{where}: {column} {raw!r} is negative")
            continue
        counts[column] = value

    # Suppression must be visible. An ignore list that silently drops findings turns a red
    # check green with no trace, so the count of suppressed items is part of the contract
    # even when it is 0.
    ignored = row["Ignored"]
    if not ignored:
        findings.append(
            f"{where}: no Ignored count -- suppression must stay visible, so record 0 when "
            "the ignore list matched nothing"
        )
    elif _count(ignored) is None:
        findings.append(f"{where}: Ignored {ignored!r} records no number -- use 0 for none")

    severity = row["Severity"].lower()
    if not severity:
        findings.append(
            f"{where}: observed without a Severity ({'/'.join(sorted(RUNTIME_SEVERITIES))})"
        )
        return findings
    if severity not in RUNTIME_SEVERITIES:
        findings.append(
            f"{where}: Severity {row['Severity']!r} is not one of "
            f"{'/'.join(sorted(RUNTIME_SEVERITIES))}"
        )
        return findings

    # Only grade what parsed. A missing counter is already reported above; inferring a
    # severity from it would turn one defect into two and blame the wrong field.
    required = NO_SEVERITY
    drivers: list[str] = []
    for column, floor in GATING_COUNTERS:
        if counts.get(column, 0) > 0:
            drivers.append(f"{column}={counts[column]}")
            if floor == S1:
                required = S1
            elif required != S1:
                required = S2

    if required == NO_SEVERITY and severity != NO_SEVERITY:
        if len(counts) == len(RUNTIME_COUNTERS):
            findings.append(
                f"{where}: Severity {row['Severity']} on a route whose gating counters are all "
                "0 -- either a counter is wrong or this route is clean (Severity none)"
            )
    elif required == S1 and severity != S1:
        findings.append(
            f"{where}: {', '.join(drivers)} is S1 (the page is missing its own code, or threw "
            f"before it finished) but Severity says {row['Severity']}"
        )
    elif required == S2 and severity == NO_SEVERITY:
        findings.append(
            f"{where}: {', '.join(drivers)} is S2 but Severity says none -- a route with "
            "runtime errors is not clean"
        )

    # S1 is the gating verdict, so a human must be able to re-read the raw evidence.
    if severity == S1 and not row["Evidence"]:
        findings.append(
            f"{where}: S1 without an Evidence path -- the console/network log that makes this "
            "verdict checkable by a human"
        )
    if severity != NO_SEVERITY and not row["Notes"]:
        findings.append(
            f"{where}: {row['Severity']} without Notes -- record the message and the resource "
            "URL, or the finding is not actionable"
        )
    return findings


RUNTIME = Profile(
    name="runtime",
    written_by="functional-tester / e2e-tester (browser runtime capture)",
    columns=(
        "Route",
        "State",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Console Errors",
        "Console Warnings",
        "Page Errors",
        "Failed Critical",
        "Failed Subresource",
        "Severity",
        "Ignored",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"observed"}),
    ident_columns=("Route", "State"),
    extra=_runtime_extra,
)


PROFILES: tuple[Profile, ...] = (FUNCTIONAL, A11Y, RUNTIME)

# Kept as a module-level alias: the functional contract is the one mirrored in
# functional-tester.md, and external callers/selftests refer to it by this name.
COLUMNS = list(FUNCTIONAL.columns)


def detect_profile(header: list[str], path: Path) -> Profile:
    """Pick the profile whose contract this header matches exactly, or raise Unusable."""
    for profile in PROFILES:
        if header == list(profile.columns):
            return profile

    # Name the closest contract by overlap so the message is actionable rather than a
    # wall of every known schema.
    best = max(PROFILES, key=lambda p: len(set(header) & set(p.columns)))
    missing = [c for c in best.columns if c not in header]
    extra = [c for c in header if c not in best.columns]
    detail = []
    if missing:
        detail.append(f"missing {missing}")
    if extra:
        detail.append(f"unexpected {extra}")
    if not detail:
        detail.append("columns are out of order")
    raise Unusable(
        f"{path} header matches no known evidence contract. Closest is "
        f"{best.name} (written by {best.written_by}): {'; '.join(detail)}. "
        f"Expected exactly: {best.header}"
    )


def load_rows(path: Path) -> tuple[Profile, list[dict[str, str]]]:
    """Parse an evidence CSV, or raise Unusable.

    Refusing an unreadable artifact is the point: a checker that reports clean on input it
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

        profile = detect_profile([_norm(cell) for cell in header], path)
        width = len(profile.columns)

        rows = []
        for raw in reader:
            cells = [_norm(c) for c in raw]
            if not any(cells):
                continue  # blank line -- not a result, and not an error either
            # Pad short rows rather than letting zip() drop keys: a truncated row must
            # surface as "field missing" findings, never as a KeyError crash (a checker
            # that dies on malformed input has not checked it).
            if len(cells) < width:
                cells += [""] * (width - len(cells))
            row = dict(zip(profile.columns, cells))
            # An over-long row means the writer's columns have drifted from the contract,
            # or an unescaped comma split a field. Either way its cells are not where we
            # think they are, so record it instead of silently truncating.
            row["__overflow__"] = str(len(cells) - width) if len(cells) > width else ""
            rows.append(row)

    if not rows:
        raise Unusable(
            f"{path} has a valid {profile.name} header but zero data rows -- refusing to "
            "bless an artifact with no results in it"
        )
    return profile, rows


def _http_ok(value: str) -> bool:
    """True only for an integer status in the 2xx/3xx range."""
    try:
        code = int(value)
    except ValueError:
        return False
    return 200 <= code <= 399


def check_row(row: dict[str, str], line: int, profile: Profile) -> list[str]:
    """Findings for one row. Empty list = this row is honest."""
    findings: list[str] = []
    ident = " / ".join(row[c] for c in profile.ident_columns if row[c]) or "<unnamed>"
    where = f"row {line} ({ident})"
    status = row["Status"].lower()

    if row.get("__overflow__"):
        findings.append(
            f"{where}: has {row['__overflow__']} cell(s) more than the "
            f"{len(profile.columns)}-column {profile.name} contract -- an unescaped comma "
            "or a drifted template means these fields are not the fields they appear to be"
        )

    if status not in profile.valid_statuses:
        # Return here (an unrecognised status makes the per-status rules meaningless) but
        # keep anything already found -- discarding it would hide a second defect.
        expected = " / ".join(sorted(s.title() for s in profile.valid_statuses))
        findings.append(f"{where}: Status {row['Status']!r} is not one of {expected}")
        return findings

    if status == SKIPPED_STATUS:
        # Not exercised and not claimed to be -- nothing to prove.
        return findings

    if status == BLOCKED_STATUS:
        # Blocked must still say what it saw.
        if not row["HTTP"]:
            findings.append(
                f"{where}: Blocked without an HTTP status (use the code, or `none` if "
                "navigation never returned)"
            )
        if not row["Final URL"]:
            findings.append(f"{where}: Blocked without a Final URL")
        if not row["Notes"]:
            findings.append(f"{where}: Blocked without Notes saying what was missing")
        return findings

    # ---- a result status: this row asserts the page was actually exercised -------------
    label = row["Status"]
    if not row["HTTP"]:
        findings.append(
            f"{where}: {label} without an HTTP status recorded from the navigation response"
        )
    elif not _http_ok(row["HTTP"]):
        findings.append(
            f"{where}: {label} on HTTP {row['HTTP']} -- a non-2xx/3xx page was not the page "
            f"under test; this is Blocked, not {label}"
        )

    if not row["Requested URL"]:
        findings.append(f"{where}: {label} without a Requested URL")
    if not row["Final URL"]:
        findings.append(f"{where}: {label} without a Final URL")

    if not row["Assertion"]:
        findings.append(
            f"{where}: {label} without an expected-content assertion -- the only signal "
            "that distinguishes the page under test from an error page that also returns 200"
        )

    # A silent redirect means a different page was exercised than intended. Acknowledged
    # redirects are fine and common (canonical slugs, trailing slashes, post-login).
    req, fin = row["Requested URL"], row["Final URL"]
    if req and fin and req != fin and not row["Notes"]:
        findings.append(
            f"{where}: redirected {req} -> {fin} with no Notes -- a different page was "
            "exercised than requested; explain why that is expected or mark it Blocked"
        )

    findings.extend(profile.extra(row, where, status))
    return findings


def validate(path: Path) -> list[str]:
    profile, rows = load_rows(path)
    findings: list[str] = []
    for offset, row in enumerate(rows):
        findings.extend(check_row(row, line=offset + 2, profile=profile))  # +2: past the header
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a QA evidence CSV carries validated page identity."
    )
    parser.add_argument(
        "csv_path", nargs="?",
        help="path to a functional summary, a11y pages, or runtime capture CSV "
             "(the kind is detected from the header)",
    )
    parser.add_argument("--selftest", action="store_true", help="prove the rules fire AND stay silent")
    parser.add_argument(
        "--contracts", action="store_true", help="print the known evidence contracts and exit"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import validate_evidence_selftest as st

        return st.run()

    if args.contracts:
        for profile in PROFILES:
            print(f"{profile.name} (written by {profile.written_by}):\n  {profile.header}")
        return 0

    if not args.csv_path:
        parser.error("csv_path is required (or pass --selftest / --contracts)")

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
            "\nFix the artifact, not this checker. A row that cannot carry a validated "
            "status/URL/assertion is a Blocked row.",
            file=sys.stderr,
        )
        return 1

    print(f"evidence validated: {args.csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
