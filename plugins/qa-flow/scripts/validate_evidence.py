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

The keyboard (#114) and forms (#115) profiles close a third, different hole: a pass that
reports a verdict on surface it never exercised. Both are per-page passes whose evidence looks
identical whether the pass was exhaustive or sampled one element and stopped, so both carry a
DENOMINATOR and the arithmetic is enforced -- an interactive element is either reached by Tab
or reported unreachable, and an error-contract verdict is only permitted on a form that was
actually submitted. An unexercised check must be indistinguishable from nothing, never from a
pass.

The perf profile (#117) closes the version of that hole where the unexercised check does not leave
a blank -- it returns a plausible NUMBER. `CLS 0` from Firefox, whose engine implements no
layout-shift observer at all, and a transfer total summed from an API that reports 0 bytes for
every cross-origin asset, both read exactly like clean measurements. So this profile's columns are
tied to what the ENGINE can actually implement, and its severity is capped rather than floored: a
slow number may never be escalated into an S1, and the timings are never graded at all.

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
import math
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
    # Does one row describe ONE page visit? True for every per-page artifact, and the reason
    # the shared HTTP/requested-URL/final-URL/assertion rules exist -- they prove the row is
    # about the page it claims to be about.
    #
    # False for a ROLLUP, where one row is a distinct defect spanning many routes (#118): there
    # is no single status or final URL to record, and demanding one would force the writer to
    # pick an arbitrary route and call it the finding's location. Such a profile is NOT exempt
    # from scrutiny -- it still gets the overflow check, the status vocabulary, and its own
    # `extra` rules, which for a rollup are the stronger ones (a duplicate signature is a
    # finding, and the instance/route arithmetic must hold).
    page_identity: bool = True
    # Checks that need EVERY row at once. Deduplication is the example that forced this: whether
    # a signature repeats is unknowable from a single row, and "no signature repeats" IS the
    # dedupe guarantee rather than a proxy for it.
    cross: Callable[[list[dict[str, str]]], list[str]] = field(default=lambda rows: [])

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
# Pass / Fail / Not run. Shared by the a11y `Keyboard` column and every forms error-contract
# column, so "Not run" means the same honest thing in all of them rather than three vocabularies
# drifting apart.
VERDICTS = frozenset({"pass", "fail", "not run"})
KEYBOARD_VERDICTS = VERDICTS  # the a11y profile's Keyboard column, under its original name


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


def _grade(counts: dict[str, int], gating: tuple[tuple[str, str], ...]) -> tuple[str, list[str]]:
    """The severity these counters FORCE, and the counters that forced it.

    Shared by every profile that recomputes its own verdict. The point of recomputing is that a
    row cannot talk its own grade down: whether a page is S1 is a function of what the browser
    counted, not of what the writer typed in the Severity column.

    Only counters that PARSED are graded -- a missing counter is already its own finding, and
    inferring a severity from it would turn one defect into two and blame the wrong field.
    """
    required = NO_SEVERITY
    drivers: list[str] = []
    for column, floor in gating:
        if counts.get(column, 0) > 0:
            drivers.append(f"{column}={counts[column]}")
            if floor == S1:
                required = S1
            elif required != S1:
                required = S2
    return required, drivers


def _read_counters(
    row: dict[str, str], where: str, columns: tuple[str, ...], blind: str
) -> tuple[dict[str, int], list[str]]:
    """Parse a profile's integer counters, reporting every one that records no honest number.

    `blind` completes the sentence "a pass that records no counts is indistinguishable from
    one where ..." -- each profile names its own way of silently doing nothing, because that is
    the failure the counter exists to make visible.
    """
    counts: dict[str, int] = {}
    findings: list[str] = []
    for column in columns:
        raw = row[column]
        if not raw:
            findings.append(
                f"{where}: no {column} count -- a pass that records no counts is "
                f"indistinguishable from one where {blind}"
            )
            continue
        value = _count(raw)
        if value is None:
            # Rejects "none", "n/a", "-", "TBD": placeholder text that reads as a clean result.
            findings.append(f"{where}: {column} {raw!r} records no number -- use 0 for none")
            continue
        if value < 0:
            findings.append(f"{where}: {column} {raw!r} is negative")
            continue
        counts[column] = value
    return counts, findings


def _check_bounds(
    counts: dict[str, int], where: str, bounds: tuple[tuple[str, str], ...]
) -> list[str]:
    """Every defect counter is bounded by the inventory it was drawn from.

    This is the rule that makes sampling impossible to hide, exactly as in the keyboard profile:
    you cannot find more unsuppressed animations than animations that were running, and one
    resource cannot be larger than the page's whole transfer.

    Shared rather than copied, and that is load-bearing beyond taste. `mutation_check.py` anchors a
    mutation on this comparison, and a second textual copy would make that anchor match twice --
    which that checker treats as a hard error, deliberately, because an ambiguous anchor cannot be
    verified applied. The third profile to want this rule is what turned the copy into a helper.
    """
    findings: list[str] = []
    for column, denominator in bounds:
        if {column, denominator} <= counts.keys() and counts[column] > counts[denominator]:
            findings.append(
                f"{where}: {counts[column]} in {column} but only {counts[denominator]} "
                f"{denominator} -- a count cannot exceed the inventory it was drawn from"
            )
    return findings


def _check_severity(
    row: dict[str, str], where: str, counts: dict[str, int],
    gating: tuple[tuple[str, str], ...], every: tuple[str, ...],
    *, s1_because: str, inflated_because: str,
) -> list[str]:
    """Compare the stated Severity against the one the counters force.

    `every` is the counter list this call grades against: an unexplained severity is only
    reported when all of them parsed, or a single missing counter would be reported twice over.
    The invariant is that `counts` and `every` describe the SAME set of columns -- callers may
    include their denominators (keyboard) or exclude them (forms), but not disagree, because the
    all-parsed test is a length comparison between the two.

    The two rationale strings are required rather than defaulted because this helper serves
    profiles whose defects have nothing to do with each other. It used to hardcode the keyboard
    reason, so a FORMS colour-only finding explained itself as "an element a keyboard user cannot
    reach" -- a caller's finding described in another caller's vocabulary. A default would let the
    next profile inherit the same wrong sentence silently.

    `inflated_because` covers the opposite direction from `s1_because`, and it is the one an
    AA-targeted audit needs: a row may not grade a finding ABOVE what its counters force. That is
    what keeps a Level AAA criterion (or a check with no upstream at all) advisory in fact rather
    than only in prose.
    """
    findings: list[str] = []
    severity = row["Severity"].lower()
    if not severity:
        findings.append(f"{where}: no Severity ({'/'.join(sorted(RUNTIME_SEVERITIES))})")
        return findings
    if severity not in RUNTIME_SEVERITIES:
        findings.append(
            f"{where}: Severity {row['Severity']!r} is not one of "
            f"{'/'.join(sorted(RUNTIME_SEVERITIES))}"
        )
        return findings

    # Structured as a match on the FORCED grade rather than as `elif required == S1 and
    # severity != S1`, deliberately: `_runtime_extra` spells that comparison out with its own
    # prose, and mutation_check.py anchors a mutation on that exact line. Two textual copies
    # would make the anchor ambiguous, and an anchor that matches twice is a hard error.
    required, drivers = _grade(counts, gating)
    if severity == required:
        return findings
    if required == NO_SEVERITY:
        if len(counts) == len(every):
            findings.append(
                f"{where}: Severity {row['Severity']} on a row whose gating counters are all "
                f"0 -- {inflated_because}"
            )
    elif required == S1:
        findings.append(
            f"{where}: {', '.join(drivers)} is S1 but Severity says {row['Severity']} -- "
            f"{s1_because}"
        )
    elif severity == NO_SEVERITY:
        findings.append(
            f"{where}: {', '.join(drivers)} is S2 but Severity says none -- not clean"
        )
    return findings


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
    required, drivers = _grade(counts, GATING_COUNTERS)

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


# ---------------------------------------------------------------------------------------
# Profile: keyboard-only navigation and focus-order audit (#114)
#
# Doctrine says every interactive element is keyboard-operable with a visible focus ring, and
# that overlays trap focus and restore it to the trigger on close. Nothing verified any of it,
# and axe cannot: under the WCAG tag filter `a11y-auditor` targets, axe runs NO focus rule at
# all. Its `tabindex` (positive tabindex) and `skip-link` rules are tagged **best-practice**,
# and `focus-order-semantics` is best-practice/experimental and only asks whether a focusable
# element's ROLE is interactive -- never whether the visual order matches, whether an indicator
# is visible, or whether focus returns to the trigger. Best-practice rules are not included by
# wcag2a/wcag2aa/wcag21a/wcag21aa/wcag22aa, so none of the three runs today.
#
# THE DEFECT THIS PROFILE IS SHAPED BY. The real probe sampled ONE button per page and produced
# focus evidence for 25 of 72 pages -- while reporting nothing missing. Sampling is invisible in
# a per-page log unless the log carries a DENOMINATOR, so the guarantee here is arithmetic:
# every interactive element is either reached by Tab or reported unreachable, and
# `Tab Stops + Unreachable < Interactive` means the remainder were never focused. That one rule
# is what makes "exhaustive, not sampled" checkable rather than promised.
#
# WHY THE ENGINE IS PART OF THE CONTRACT. Playwright's WebKit inherits the macOS default where
# Tab moves focus to text fields and lists only -- not to links and buttons -- unless Full
# Keyboard Access is on (the same setting behind Safari's "Press Tab to highlight each item on a
# webpage"). A keyboard pass run in WebKit therefore reports every link as unreachable: a page
# full of false S1s. So an Unreachable count from WebKit must say in Notes that Full Keyboard
# Access was enabled, or it is a platform setting rather than a finding about the app.
#
# WHAT IS DELIBERATELY NOT GATED. Focus-indicator thickness and contrast (2 CSS px, 3:1) come
# from WCAG 2.2 SC 2.4.13 Focus Appearance, which is **Level AAA**. a11y-auditor targets AA, so
# those stay advisory and must not be counted in `No Focus Indicator`. What IS gated is SC 2.4.7
# Focus Visible (**Level AA**): that an indicator exists at all.
# ---------------------------------------------------------------------------------------
ENGINES = frozenset({"chromium", "firefox", "webkit"})
SKIP_LINK_STATES = frozenset({"present", "absent", "n/a"})
# Phrases that make a WebKit Unreachable count a claim about the app rather than about macOS.
FKA_TOKENS = ("full keyboard access", "fka", "tab to highlight")

KEYBOARD_GATING: tuple[tuple[str, str], ...] = (
    ("Unreachable", S1),
    ("No Focus Indicator", S1),
    ("Trap Failures", S1),
    ("Escape Failures", S1),
    ("Restore Failures", S1),
    ("Positive Tabindex", S2),
    ("Backward Jumps", S2),
)
# Interactive / Tab Stops / Overlays are DENOMINATORS, not defects: they never force a severity,
# and they are what the gating counters are checked against.
KEYBOARD_COUNTERS = ("Interactive", "Tab Stops", "Overlays") + tuple(
    name for name, _ in KEYBOARD_GATING
)


def _keyboard_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """A keyboard pass must prove it looked at everything, and cannot grade itself down."""
    counts, findings = _read_counters(
        row, where, KEYBOARD_COUNTERS,
        "the Tab loop never ran and document.activeElement never moved",
    )

    engine = row["Engine"].lower()
    if not engine:
        findings.append(
            f"{where}: no Engine -- Tab reachability is engine-dependent, so a focus result that "
            f"does not say where it ran cannot be read ({'/'.join(sorted(ENGINES))})"
        )
    elif engine not in ENGINES:
        findings.append(
            f"{where}: Engine {row['Engine']!r} is not one of {'/'.join(sorted(ENGINES))}"
        )

    # THE SAMPLING GUARD. Every interactive element is either reached or reported unreachable;
    # anything left over was never examined, which is precisely the 25-of-72 defect.
    if {"Interactive", "Tab Stops", "Unreachable"} <= counts.keys():
        accounted = counts["Tab Stops"] + counts["Unreachable"]
        if accounted < counts["Interactive"]:
            findings.append(
                f"{where}: {counts['Interactive']} interactive element(s) but only {accounted} "
                f"accounted for ({counts['Tab Stops']} reached + {counts['Unreachable']} "
                "unreachable) -- the remainder were never focused, so this row samples where the "
                "contract is exhaustive"
            )

    # You cannot read the focus indicator of an element you never focused.
    if {"No Focus Indicator", "Tab Stops"} <= counts.keys() and (
        counts["No Focus Indicator"] > counts["Tab Stops"]
    ):
        findings.append(
            f"{where}: {counts['No Focus Indicator']} element(s) with no focus indicator but "
            f"only {counts['Tab Stops']} tab stop(s) -- the indicator can only be read from an "
            "element that was actually focused"
        )

    # ...nor assert trap / Escape / restore on an overlay you never opened.
    if "Overlays" in counts:
        for column in ("Trap Failures", "Escape Failures", "Restore Failures"):
            if counts.get(column, 0) > counts["Overlays"]:
                findings.append(
                    f"{where}: {counts[column]} {column} across {counts['Overlays']} overlay(s) "
                    "-- an overlay cannot fail one assertion more than once"
                )

    skip = row["Skip Link"].lower()
    if not skip:
        findings.append(
            f"{where}: no Skip Link state ({'/'.join(sorted(SKIP_LINK_STATES))}) -- whether a "
            "skip-to-content affordance is the first tab stop is part of the pass"
        )
    elif skip not in SKIP_LINK_STATES:
        findings.append(
            f"{where}: Skip Link {row['Skip Link']!r} is not one of "
            f"{'/'.join(sorted(SKIP_LINK_STATES))}"
        )

    findings.extend(_check_severity(
        row, where, counts, KEYBOARD_GATING, KEYBOARD_COUNTERS,
        s1_because=(
            "an element a keyboard user cannot reach or see focus on is not a lesser defect"
        ),
        inflated_because="either a counter is wrong or this row is clean (Severity none)",
    ))

    # The verified WebKit caveat, applied where it does damage: as an app defect.
    if engine == "webkit" and counts.get("Unreachable", 0) > 0:
        note = row["Notes"].lower()
        if not any(token in note for token in FKA_TOKENS):
            findings.append(
                f"{where}: {counts['Unreachable']} unreachable element(s) on webkit without "
                "Notes confirming Full Keyboard Access was enabled -- WebKit's default moves Tab "
                "to text fields and lists only, so this is a platform setting until proven "
                "otherwise, not a finding about the app"
            )

    severity = row["Severity"].lower()
    if severity == S1 and not row["Evidence"]:
        findings.append(
            f"{where}: S1 without an Evidence path -- the focus path that lets a human re-walk "
            "the tab order"
        )
    if severity in {S1, S2} and not row["Notes"]:
        findings.append(
            f"{where}: {row['Severity']} without Notes naming the element(s) -- a focus defect "
            "nobody can locate is not actionable"
        )
    return findings


KEYBOARD = Profile(
    name="keyboard",
    written_by="a11y-auditor (keyboard-only navigation pass)",
    columns=(
        "Route",
        "State",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Engine",
        "Interactive",
        "Tab Stops",
        "Unreachable",
        "No Focus Indicator",
        "Positive Tabindex",
        "Backward Jumps",
        "Overlays",
        "Trap Failures",
        "Escape Failures",
        "Restore Failures",
        "Skip Link",
        "Severity",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"walked"}),
    ident_columns=("Route", "State"),
    extra=_keyboard_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: form validation state testing (#115)
#
# The audited corpus carried 200+ form controls and qa-flow had no systematic way to test
# validation behaviour. Forms doctrine requires a real label association, `aria-invalid` on
# error, the message referenced from the control, an announced error summary, and values that
# survive a failed round-trip. The WCAG floor under those is low and mostly **Level A**:
# 3.3.2 Labels or Instructions (A), 4.1.2 Name Role Value (A), 3.3.1 Error Identification (A),
# 1.4.1 Use of Color (A), with 3.3.3 Error Suggestion at AA -- which is why an unlabelled
# control and a colour-only error state are S1 here rather than stylistic notes.
#
# THE HOLE THIS CLOSES IS NOT "no checks" -- IT IS "verdicts on states nobody triggered". A
# forms row can claim `aria-invalid` was correct on a form it never submitted, and that reads
# exactly like a real result. So the error-contract columns are tied to `Submit Mode`: they MUST
# be `Not run` unless the row actually submitted something invalid, and they must NOT be
# `Not run` when it did. Same shape as the keyboard profile's denominator rule, and the same
# reason -- an unexercised check must be indistinguishable from nothing, never from a pass.
#
# `aria-invalid` NEEDS THE VALUE, NOT THE ATTRIBUTE. Its default is `false`, and an absent
# attribute, `aria-invalid=""` and `aria-invalid="false"` are all equivalent to not-invalid. So
# "the attribute is present" is not the check; `aria-invalid="true"` on the offending control
# is. The agent doctrine says this in the same words, because a pass that greps for the
# attribute name would report a clean contract on a form that marks nothing.
#
# The message link is accepted as EITHER `aria-describedby` or `aria-errormessage`: both are in
# use, and the ARIA spec text on whether `aria-errormessage` is exposed independently of
# `aria-invalid="true"` was not something this change verified, so it is not asserted either way.
# ---------------------------------------------------------------------------------------
FORM_MODES = frozenset({"dry-run", "empty", "invalid", "valid", "skipped-destructive"})
# The modes that actually submit something invalid, and therefore DO observe the error contract.
ERROR_EXERCISING_MODES = frozenset({"empty", "invalid"})
# The error-contract columns, and the severity a Fail in each forces.
FORM_CONTRACT: tuple[tuple[str, str], ...] = (
    ("Invalid Marked", S1),
    ("Message Linked", S1),
    ("Announced", S1),
    ("Colour Only", S1),
    ("Values Retained", S2),
)
# `Required Unexposed` is S2 rather than S1: a required control with a label is still
# operable and announced, it just does not tell an assistive technology that it is mandatory --
# worse than fine, not as bad as a control with no accessible name at all.
FORMS_GATING: tuple[tuple[str, str], ...] = (
    ("Unlabelled", S1),
    ("Required Unexposed", S2),
) + FORM_CONTRACT
FORMS_COUNTERS = ("Controls", "Unlabelled", "Required Unexposed")
# What can force a severity: the two structural gaps plus each contract Fail. `Controls` is the
# denominator and never a defect.
FORMS_GRADED = ("Unlabelled", "Required Unexposed") + tuple(c for c, _ in FORM_CONTRACT)


def _forms_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """A forms row may only carry verdicts on states it actually triggered."""
    counts, findings = _read_counters(
        row, where, FORMS_COUNTERS, "the form was never located in the DOM",
    )

    if counts.get("Controls") == 0:
        findings.append(
            f"{where}: 0 Controls -- a form with no controls is not a form under test; if there "
            "was nothing to exercise, this row is Out of Scope"
        )
    # Both structural counters are bounded by the same denominator: a form cannot have more
    # unlabelled -- or more required-but-unexposed -- controls than it has controls.
    for column, what in (("Unlabelled", "lack a label"), ("Required Unexposed", "are required")):
        if {"Controls", column} <= counts.keys() and counts[column] > counts["Controls"]:
            findings.append(
                f"{where}: {counts[column]} of {counts['Controls']} control(s) in {column} -- "
                f"more controls {what} than the form has"
            )

    mode = row["Submit Mode"].lower()
    if not mode:
        findings.append(
            f"{where}: no Submit Mode ({'/'.join(sorted(FORM_MODES))}) -- what was submitted is "
            "what decides which error-contract columns may carry a verdict at all"
        )
    elif mode not in FORM_MODES:
        findings.append(
            f"{where}: Submit Mode {row['Submit Mode']!r} is not one of "
            f"{'/'.join(sorted(FORM_MODES))}"
        )

    # The destructive-form carve-out is the widest exemption here, so its suppression stays
    # visible -- the same doctrine as the runtime profile's Ignored count.
    if mode == "skipped-destructive" and not row["Notes"]:
        findings.append(
            f"{where}: skipped-destructive without Notes naming the pattern that matched -- a "
            "form skipped without a trace is indistinguishable from one that passed"
        )

    exercised = mode in ERROR_EXERCISING_MODES
    verdicts: dict[str, int] = {}
    for column, _ in FORM_CONTRACT:
        raw = row[column].lower()
        if not raw:
            findings.append(f"{where}: no {column} verdict (Pass / Fail / Not run)")
            continue
        if raw not in VERDICTS:
            findings.append(
                f"{where}: {column} {row[column]!r} is not one of Pass / Fail / Not run"
            )
            continue
        if exercised and raw == "not run":
            findings.append(
                f"{where}: Submit Mode {row['Submit Mode']} submitted an invalid form but "
                f"{column} is Not run -- the error contract is the reason for submitting"
            )
        elif not exercised and raw != "not run" and mode in FORM_MODES:
            findings.append(
                f"{where}: {column} claims {row[column]} but Submit Mode {row['Submit Mode']} "
                "never submitted an invalid form -- that is a verdict on an error state nobody "
                "triggered"
            )
        verdicts[column] = 1 if raw == "fail" else 0

    graded = {column: value for column, value in counts.items() if column != "Controls"}
    graded.update(verdicts)
    findings.extend(_check_severity(
        row, where, graded, FORMS_GATING, FORMS_GRADED,
        s1_because=(
            "an unnamed control, or an error state conveyed by colour alone, fails a Level A "
            "criterion -- it is not a lesser defect"
        ),
        inflated_because="either a counter is wrong or this form is clean (Severity none)",
    ))

    severity = row["Severity"].lower()
    if severity == S1 and not row["Evidence"]:
        findings.append(
            f"{where}: S1 without an Evidence path -- the capture of the error state that lets a "
            "human re-check it"
        )
    if severity in {S1, S2} and not row["Notes"]:
        findings.append(
            f"{where}: {row['Severity']} without Notes naming the control(s) -- a validation "
            "defect nobody can locate is not actionable"
        )
    return findings


FORMS = Profile(
    name="forms",
    written_by="a11y-auditor (form validation state pass)",
    columns=(
        "Form",
        "Route",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Controls",
        "Unlabelled",
        "Required Unexposed",
        "Submit Mode",
        "Invalid Marked",
        "Message Linked",
        "Announced",
        "Values Retained",
        "Colour Only",
        "Severity",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"exercised"}),
    ident_columns=("Form", "Route"),
    extra=_forms_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: emulated media conditions -- reduced motion, forced colors, print (#116)
#
# Doctrine requires motion to be gated on `prefers-reduced-motion` and requires meaning never to
# rest on colour alone. Playwright can emulate all three conditions offline and for free, so this
# was unverified doctrine with a trivial verification path. What the path is NOT is a fourth
# copy of the axe/keyboard severity model, and the reason is the whole shape of this profile.
#
# THE HOLE THIS CLOSES IS THE OPPOSITE OF THE OTHER PROFILES'. Keyboard (#114) and forms (#115)
# stop a row from grading a real defect DOWN. Here the risk runs the other way: the reduced-motion
# and print checks have little or no WCAG force behind them, so a row that grades them S1 inflates
# an advisory nit into a release-blocking defect, and an audit whose findings are mostly
# unactionable gets switched off -- the same way the #106 over-correction would have been. So
# `_check_severity` is called with an explicit `inflated_because`, and the AAA / no-upstream
# boundary is arithmetic rather than prose.
#
# WHAT GATES, AND ON WHOSE AUTHORITY. Verified against the specifications, not the issue body:
#
#   SC 2.3.3 Animation from Interactions   Level AAA  -> ADVISORY. This is the criterion whose
#       sufficient techniques (C39, SCR40) literally ARE `prefers-reduced-motion`. So "this
#       animation ignores the preference" is a Level AAA finding, and `a11y-auditor` targets AA.
#       Identical treatment to SC 2.4.13 Focus Appearance in the keyboard profile above.
#   SC 2.2.2 Pause, Stop, Hide             Level A    -> GATES, but only for the narrow subset it
#       actually covers: motion that starts automatically, runs MORE THAN FIVE SECONDS, and is
#       presented in parallel with other content, with no mechanism to pause/stop/hide it. That
#       is `Autoplay No Control` -- deliberately not named after the media query, because the
#       failure is the missing control, not the missing `@media` block.
#   SC 1.4.1 Use of Color                  Level A    -> GATES. `Colour Only`, the same criterion
#       and the same citation the forms profile already uses for its own colour-only column.
#   forced-colors support                  NO SC      -> our decision, recorded as one.
#   print output                           NO SC      -> our decision, and it gates NOTHING.
#
# There is no WCAG success criterion requiring forced-colors / Windows High Contrast support at
# all, and none covering print output. Both were searched for and not found rather than assumed
# absent. `Text Invisible` and `Focus Indicator Lost` therefore gate on a MAINTAINER DECISION
# (recorded on #116): content that cannot be read, and a focus ring that vanishes, are the same
# defects the keyboard profile already rates S1, so a user agent revealing them does not make
# them lesser. Print gates nothing, because its own technique cannot support a gate (below).
#
# WHY `Focus Indicator Lost` IS A REAL CLASS AND NOT A THEORY. In forced colors mode `box-shadow`
# and `text-shadow` COMPUTE TO `none` (W3C CSS Color Adjustment Module Level 1, "Properties
# Affected by Forced Colors Mode"). The keyboard pass reads focus indicators from
# `outline-width`/`outline-style`/`box-shadow`, so a ring implemented with box-shadow and no
# outline genuinely disappears for a forced-colors user while passing the keyboard pass. That is
# the highest-value finding here and it is why the two profiles are worth having separately.
#
# WHY THE ENGINE IS PART OF THE CONTRACT -- AND WHY IT FAILS OPEN THE OTHER WAY THAN #114'S.
# Playwright can make the `forced-colors` media query report `active` in all three engines (its
# own conformance test carries no per-engine skip). WebKit, however, never implements the forcing
# itself: its media-query commit says outright that there is no concept of forced colors in
# Cocoa, and `forced-color-adjust` is unimplemented in Safari to this day. So WebKit strips no
# box-shadow and forces no system colour, and a forced-colors run there reports CLEAN on an app
# that breaks for real Windows high-contrast users. #114's WebKit caveat manufactures false
# defects; this one manufactures false confidence, which is worse, so it is not a Notes
# requirement -- a forced-colors row on webkit cannot be a result row at all.
#
# WHAT IS DELIBERATELY NOT CLAIMED. `emulateMedia({ media: 'print' })` switches the CSS media type
# for real -- computed styles and screenshots follow it -- but a screenshot is one viewport-shaped
# render with NO PAGINATION. Page-boundary clipping exists only in genuinely paginated output, and
# `page.pdf()` is Headless-Chromium-only (the server throws "PDF generation is only supported for
# Headless Chromium" elsewhere). So this profile records print-stylesheet sanity -- ink-burning
# backgrounds, content overflowing the print width -- and must not be read as proving nothing is
# clipped at a page break. #116 conflated the two; the counters are named for what they measure.
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EmulationMode:
    """One emulated media condition: what its row must record, and what may gate."""

    numeric: tuple[str, ...]          # counters this mode must record, denominator first
    verdicts: tuple[str, ...]         # Pass/Fail/Not run columns this mode must carry
    gating: tuple[tuple[str, str], ...]      # (column, forced severity floor)
    bounds: tuple[tuple[str, str], ...]      # (counter, the denominator bounding it)
    advisory: tuple[str, ...]         # counted, reported, and NEVER a severity
    require_nonzero: tuple[str, ...]  # denominators for which 0 means "nothing was inspected"
    blind: str                        # completes "...indistinguishable from one where {blind}"
    s1_because: str
    inflated_because: str


EMULATION_BY_MODE: dict[str, EmulationMode] = {
    "reduced-motion": EmulationMode(
        numeric=("Animations", "Motion Not Suppressed", "Autoplay No Control"),
        verdicts=("End State Committed",),
        # SC 2.2.2 is Level A; the committed-end-state invariant is ours (motion.md: "the trip is
        # skipped, the information still arrives") and a broken one means content never arrives.
        gating=(("Autoplay No Control", S1), ("End State Committed", S1)),
        bounds=(("Motion Not Suppressed", "Animations"),
                ("Autoplay No Control", "Animations")),
        advisory=("Motion Not Suppressed",),
        # 0 animations is a legitimate, checkable result: a route may simply not animate.
        require_nonzero=(),
        blind="document.getAnimations() was never called and nothing was ever sampled",
        s1_because=(
            "an animation that autostarts, runs over five seconds alongside other content and "
            "offers no way to stop it fails SC 2.2.2 at Level A, and a state change that never "
            "commits means the information never arrives at all"
        ),
        inflated_because=(
            "motion that merely ignores prefers-reduced-motion is SC 2.3.3 at Level AAA, so it "
            "belongs in the advisory list under an AA-targeted audit -- record the count and "
            "grade the row none"
        ),
    ),
    "forced-colors": EmulationMode(
        numeric=("Elements Checked", "Text Invisible", "Focus Indicator Lost", "Colour Only"),
        verdicts=(),
        gating=(("Text Invisible", S1), ("Focus Indicator Lost", S1), ("Colour Only", S1)),
        bounds=(("Text Invisible", "Elements Checked"),
                ("Focus Indicator Lost", "Elements Checked"),
                ("Colour Only", "Elements Checked")),
        advisory=(),
        require_nonzero=("Elements Checked",),
        blind="forced colors was never applied and no element was ever inspected",
        s1_because=(
            "text that cannot be read and a focus ring that vanishes are the same defects the "
            "keyboard profile rates S1; colour-only meaning fails SC 1.4.1 at Level A"
        ),
        inflated_because="either a counter is wrong or this route is clean (Severity none)",
    ),
    "print": EmulationMode(
        numeric=("Elements Checked", "Ink Burning", "Print Overflow"),
        verdicts=(),
        # Nothing gates. No WCAG criterion covers print output, and the technique cannot prove
        # page-boundary clipping, so a gate here would rest on neither a citation nor a
        # measurement. An empty tuple makes that boundary enforced in both directions.
        gating=(),
        bounds=(("Ink Burning", "Elements Checked"),
                ("Print Overflow", "Elements Checked")),
        advisory=("Ink Burning", "Print Overflow"),
        require_nonzero=("Elements Checked",),
        blind="the print stylesheet never resolved and no element was ever inspected",
        s1_because="",  # unreachable: nothing in this mode can force a severity
        inflated_because=(
            "no WCAG success criterion covers print output, and emulateMedia cannot prove "
            "page-boundary clipping, so a print row is advisory -- record the counts and grade "
            "it none"
        ),
    ),
}

# Every counter and verdict column any mode uses. A column outside the row's own mode must be
# BLANK: that is this profile's version of the forms Submit Mode rule, and the same failure it
# prevents -- a number in `Colour Only` on a `print` row is a verdict on a media condition the
# row never emulated, and it reads exactly like a real result.
EMULATION_NUMERIC: tuple[str, ...] = tuple(
    dict.fromkeys(column for spec in EMULATION_BY_MODE.values() for column in spec.numeric)
)
EMULATION_VERDICT_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys(column for spec in EMULATION_BY_MODE.values() for column in spec.verdicts)
)


def _emulation_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """An emulated-media row may only carry counts for the condition it actually emulated."""
    mode = row["Mode"].lower()
    if not mode:
        return [
            f"{where}: no Mode ({'/'.join(sorted(EMULATION_BY_MODE))}) -- which condition was "
            "emulated is what decides which columns may carry a number at all"
        ]
    spec = EMULATION_BY_MODE.get(mode)
    if spec is None:
        return [
            f"{where}: Mode {row['Mode']!r} is not one of "
            f"{'/'.join(sorted(EMULATION_BY_MODE))}"
        ]

    findings: list[str] = []
    engine = row["Engine"].lower()
    if not engine:
        findings.append(
            f"{where}: no Engine ({'/'.join(sorted(ENGINES))}) -- forced-colors behaviour is not "
            "the same in every engine, so a result that does not say where it ran cannot be read"
        )
    elif engine not in ENGINES:
        findings.append(
            f"{where}: Engine {row['Engine']!r} is not one of {'/'.join(sorted(ENGINES))}"
        )

    # THE WEBKIT CEILING. WebKit answers the media query but implements none of the forcing, so a
    # result row here is a statement about WebKit, not about the app -- and its most likely value
    # is a clean one, which is why this is a hard finding rather than a Notes requirement.
    if mode == "forced-colors" and engine == "webkit":
        findings.append(
            f"{where}: forced-colors result on webkit -- WebKit matches the media query but "
            "never applies forced colors (no forced-color-adjust support), so it strips no "
            "box-shadow and forces no system colour. A clean row here is a platform ceiling, "
            "not evidence about the app: record it Blocked and run this mode on chromium or "
            "firefox"
        )

    # ---- the mode contract: this mode's columns are required, every other one must be blank ---
    for column in EMULATION_NUMERIC:
        if column in spec.numeric:
            continue
        if row[column]:
            findings.append(
                f"{where}: {column} records {row[column]!r} but Mode {row['Mode']} never "
                f"emulated the condition {column} measures -- that is a count from a media "
                "condition this row did not apply, and it reads exactly like a real result"
            )
    for column in EMULATION_VERDICT_COLUMNS:
        if column in spec.verdicts:
            continue
        if row[column]:
            findings.append(
                f"{where}: {column} claims {row[column]!r} but Mode {row['Mode']} never "
                f"emulated the condition {column} is a verdict on -- leave it blank"
            )

    counts, count_findings = _read_counters(row, where, spec.numeric, spec.blind)
    findings.extend(count_findings)

    for column in spec.require_nonzero:
        if counts.get(column) == 0:
            findings.append(
                f"{where}: 0 {column} -- a pass that inspected nothing is not a result; if there "
                "was nothing to examine on this route, the row is Out of Scope"
            )

    findings.extend(_check_bounds(counts, where, spec.bounds))

    verdicts: dict[str, int] = {}
    for column in spec.verdicts:
        raw = row[column].lower()
        if not raw:
            findings.append(f"{where}: no {column} verdict (Pass / Fail / Not run)")
            continue
        if raw not in VERDICTS:
            findings.append(
                f"{where}: {column} {row[column]!r} is not one of Pass / Fail / Not run"
            )
            continue
        verdicts[column] = 1 if raw == "fail" else 0

    # Grade against this mode's gating columns only, and pass `counts`/`every` over the same set
    # so the all-parsed test compares like with like.
    graded_names = tuple(column for column, _ in spec.gating)
    graded = {name: value for name, value in {**counts, **verdicts}.items()
              if name in graded_names}
    findings.extend(_check_severity(
        row, where, graded, spec.gating, graded_names,
        s1_because=spec.s1_because, inflated_because=spec.inflated_because,
    ))

    severity = row["Severity"].lower()
    if severity == S1 and not row["Evidence"]:
        findings.append(
            f"{where}: S1 without an Evidence path -- the capture taken under the emulated "
            "condition that lets a human re-check it"
        )
    if severity in {S1, S2} and not row["Notes"]:
        findings.append(
            f"{where}: {row['Severity']} without Notes naming the element(s) -- a defect nobody "
            "can locate is not actionable"
        )
    # An advisory count is the whole output of the AAA / no-upstream modes, so it carries the same
    # burden a graded finding does. A bare number nobody can act on is how an advisory list
    # becomes noise and then gets ignored.
    advisory_hits = [c for c in spec.advisory if counts.get(c, 0) > 0]
    if advisory_hits and not row["Notes"]:
        findings.append(
            f"{where}: {', '.join(advisory_hits)} above 0 without Notes naming the element(s) -- "
            "an advisory finding is still a finding, and this row is its only record"
        )
    return findings


EMULATION = Profile(
    name="emulation",
    written_by="a11y-auditor (emulated media conditions pass)",
    columns=(
        "Route",
        "Mode",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Engine",
        "Animations",
        "Motion Not Suppressed",
        "Autoplay No Control",
        "End State Committed",
        "Elements Checked",
        "Text Invisible",
        "Focus Indicator Lost",
        "Colour Only",
        "Ink Burning",
        "Print Overflow",
        "Severity",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"emulated"}),
    ident_columns=("Route", "Mode"),
    extra=_emulation_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: client-side performance capture during the crawl (#117)
#
# `perf-tester` measured CAPACITY with k6 -- server throughput -- and nothing measured what a user
# experiences. The harness already loads every route in a real browser, so LCP, CLS, TTFB, transfer
# bytes and request count are nearly free. What is NOT free is saying anything trustworthy about
# them, and this profile is mostly shaped by three verified facts that contradict the obvious
# implementation.
#
# THE HOLE THIS CLOSES IS A NUMBER THAT WAS NEVER MEASURED READING EXACTLY LIKE ONE THAT WAS.
# Every other profile's blind spot is a check that did not run and left a blank. Here the blind
# spots return a plausible NUMBER -- `CLS 0` from an engine with no LayoutShift implementation,
# `Transfer 180 KB` from an API that reports 0 for every cross-origin asset. A blank is honest; a
# fabricated zero is a gate that cannot fail.
#
# 1. ENGINE SUPPORT IS PER-METRIC, AND THE BLANKET RULE WOULD BE STALE. Verified against MDN
#    browser-compat-data rather than assumed:
#      largest-contentful-paint  Firefox 122 (Jan 2024), Safari 26.2 (Dec 2025)  -> ALL ENGINES
#      layout-shift (CLS)        Firefox `version_added: false`, Safari likewise -> CHROMIUM ONLY
#      renderBlockingStatus      Chromium 107+; Firefox none, Safari none        -> CHROMIUM ONLY
#    LCP shipped everywhere only recently, so "LCP is Chromium-only" -- true until Dec 2025 -- is
#    exactly the stale doctrine this check would otherwise enshrine. The consequence runs the same
#    direction as #116's forced-colors ceiling: on firefox/webkit the CLS observer never fires and
#    the row records `0`, reporting a perfectly stable page from an API that does not exist. So the
#    Chromium-only columns must be BLANK off chromium, and `LCP ms` must NOT be -- that carve-out is
#    what keeps this from degenerating into "webkit is unsupported".
#
# 2. THE INTERACTION PROBE CORRUPTS THE METRICS BESIDE IT. Playwright's `locator.click()` goes
#    through the browser's own input protocol, so `isTrusted` is true (unlike `dispatchEvent`, which
#    the Event Timing spec excludes outright). A trusted input TERMINATES LCP observation, and
#    `layout-shift` entries within 500 ms of input carry `hadRecentInput` and are excluded from CLS.
#    So a click taken before the metrics are read truncates LCP and hides shifts -- the issue
#    proposed exactly that. The probe gets its own visit, and the row records which.
#    It is also not called INP: INP is a whole-visit field metric, and Lighthouse reports TBT (30%
#    of its score) in lab precisely because INP cannot be measured there.
#
# 3. `transferSize` CANNOT CARRY A BYTE BUDGET. Per Resource Timing it is 0 for a CORS-cross-origin
#    resource with no `Timing-Allow-Origin`, 0 for a local cache hit, and the fixed constant 300 for
#    a 304 revalidation. A page pulling 30 CDN assets reports a plausible small total and passes any
#    budget, silently. Playwright's `Request.sizes().responseBodySize` is the encoded wire size read
#    at the network layer on all three engines and is not TAO-gated, so it is the instrument --
#    and `Opaque Requests` is the column that proves which instrument was actually used.
#
# WHAT GATES, AND ON WHOSE AUTHORITY. NO WCAG criterion and no standard of any kind mandates a
# performance budget; the 2.5s/0.1 numbers are Google guidance, published as revisable. Searched for
# and not found, exactly as #116 searched for a forced-colors criterion. So every severity here is a
# MAINTAINER DECISION (recorded on #117), and the decisions are:
#
#   Severity is CAPPED AT S2; `S1` is rejected outright. This is the direction the other profiles
#       leave open -- #114/#115 stop a row grading a defect DOWN, #116 stops it grading an advisory
#       UP, and this caps the ceiling. No client-side timing taken on an unthrottled dev machine
#       against localhost establishes that a release is blocked.
#   Timings NEVER gate. `TTFB ms` / `LCP ms` are recorded and trended, never graded. That is the
#       issue's own instruction ("trends with thresholds, not hard gates") made arithmetic.
#   What gates is what is reproducible off the machine's clock: a CLS above the budget the row
#       itself carries, and a request over the per-resource byte budget. A layout shift observed
#       locally is a shift the page really performs; an LCP observed locally is mostly a statement
#       about the laptop. The asymmetry holds ONE WAY -- a clean local CLS is not evidence of
#       stability, and the doctrine says so rather than letting the column imply it.
#
# WHY THE BUDGET LIVES IN THE ARTIFACT. `CLS Budget` is a column, not a config lookup, for the same
# reason the runtime profile counts `Ignored` even at 0: a threshold quietly relaxed to 10.0 must
# leave a trace in the evidence, or the gate turns green with nobody deciding to.
# ---------------------------------------------------------------------------------------
# Columns whose underlying API exists in Chromium only. Off chromium they must be BLANK: the
# observer never fires, so any value in them was invented rather than measured.
PERF_CHROMIUM_ONLY: tuple[str, ...] = ("CLS", "CLS Budget", "Render Blocking")
# How the interaction probe was sequenced relative to the metric read. `same-visit` is a rejection,
# not a warning: it means the LCP on this row was truncated by the click and the CLS is missing
# every shift within 500 ms of it.
PROBE_MODES = frozenset({"separate-visit", "same-visit", "not run"})
# Counters every engine can honestly produce.
PERF_COUNTERS: tuple[str, ...] = (
    "Samples", "TTFB ms", "LCP ms", "Requests", "Transfer KB", "Opaque Requests",
    "Largest Resource KB", "Oversized Requests", "Fonts No Swap",
)
# 0 here means nothing was measured at all -- a navigation is itself a request, and a route with no
# samples is Out of Scope rather than a clean result.
PERF_NONZERO: tuple[str, ...] = ("Samples", "Requests")
# (counter, the denominator that bounds it). `Largest Resource KB` vs `Transfer KB` is the one that
# catches an encoded/decoded mix-up: a 900 KB bundle inside a 300 KB page means the two numbers came
# from different instruments.
PERF_BOUNDS: tuple[tuple[str, str], ...] = (
    ("Opaque Requests", "Requests"),
    ("Largest Resource KB", "Transfer KB"),
)
# Counted, reported, and NEVER a severity -- the timings plus the two cause counters that have no
# upstream at all.
PERF_ADVISORY: tuple[str, ...] = ("Fonts No Swap", "Render Blocking")
# `CLS Over Budget` is a DERIVED gating name, not a column: the row carries the measurement and the
# threshold, and the checker does the comparison so the verdict cannot be typed in by hand.
CLS_OVER_BUDGET = "CLS Over Budget"
PERF_GATING: tuple[tuple[str, str], ...] = (
    (CLS_OVER_BUDGET, S2),
    ("Oversized Requests", S2),
)


def _ratio(value: str) -> float | None:
    """A finite, non-negative decimal, or None when the cell records no such number.

    `float()` accepts `nan` and `inf`, both of which would sail through a `>` comparison against a
    budget and read as a measurement. A layout-shift score is neither.
    """
    try:
        number = float(value)
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _perf_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """A perf row may only report metrics its engine can measure, and may never grade itself S1."""
    findings: list[str] = []

    engine = row["Engine"].lower()
    if not engine:
        findings.append(
            f"{where}: no Engine ({'/'.join(sorted(ENGINES))}) -- LCP, CLS and render-blocking "
            "status are not implemented in the same set of engines, so a metric that does not say "
            "where it ran cannot be read"
        )
    elif engine not in ENGINES:
        findings.append(
            f"{where}: Engine {row['Engine']!r} is not one of {'/'.join(sorted(ENGINES))}"
        )

    # ---- THE ENGINE CAPABILITY CONTRACT -------------------------------------------------
    # A blank is honest; a zero from an observer that never fired is not. Only enforced once the
    # engine is known -- guessing which columns apply from an unrecognised engine would report the
    # same defect twice in two vocabularies.
    chromium_only_ok = engine == "chromium"
    if engine in ENGINES and not chromium_only_ok:
        for column in PERF_CHROMIUM_ONLY:
            if row[column]:
                findings.append(
                    f"{where}: {column} records {row[column]!r} on {row['Engine']} -- neither "
                    "layout-shift nor renderBlockingStatus is implemented outside Chromium, so "
                    "that observer never fired and the value was not measured. A `0` here reports "
                    "a perfectly stable page from an API that does not exist: leave it blank, and "
                    "run this route on chromium if you need CLS"
                )

    numeric: tuple[str, ...] = PERF_COUNTERS
    if chromium_only_ok:
        numeric = PERF_COUNTERS + ("Render Blocking",)
    counts, count_findings = _read_counters(
        row, where, numeric,
        "the navigation was never timed and no resource entry was ever read",
    )
    findings.extend(count_findings)

    for column in PERF_NONZERO:
        if counts.get(column) == 0:
            findings.append(
                f"{where}: 0 {column} -- a route that was never sampled, or whose own document "
                "request was never counted, is not a measurement; this row is Out of Scope"
            )

    findings.extend(_check_bounds(counts, where, PERF_BOUNDS))

    # ---- THE FALSE-CLEAN BYTE VERDICT ---------------------------------------------------
    # `transferSize` is 0 for a CORS-cross-origin asset with no Timing-Allow-Origin and 0 for a
    # cache hit, so "no request over budget" can mean "no MEASURABLE request over budget" -- and the
    # two read identically. A positive finding is still a valid finding (incomplete, not false), so
    # only the clean direction is rejected.
    if counts.get("Opaque Requests", 0) > 0 and counts.get("Oversized Requests") == 0:
        findings.append(
            f"{where}: 0 Oversized Requests while {counts['Opaque Requests']} request(s) reported "
            "no measurable size -- that is a clean byte verdict over bytes nobody measured. "
            "transferSize is 0 for a cross-origin asset without Timing-Allow-Origin and 0 for a "
            "cache hit; re-measure with Playwright's Request.sizes(), which reads the network layer"
        )

    # A number with no attributable cause is the complaint this issue exists to answer.
    if "LCP ms" in counts and not row["LCP Element"]:
        findings.append(
            f"{where}: LCP {row['LCP ms']} ms with no LCP Element -- a timing nobody can attribute "
            "to an element is a number, not a finding"
        )

    # ---- CLS against the budget the row itself carries ----------------------------------
    cls_over: int | None = None
    if chromium_only_ok:
        measured, budget = _ratio(row["CLS"]), _ratio(row["CLS Budget"])
        for column, value in (("CLS", measured), ("CLS Budget", budget)):
            if value is None:
                findings.append(
                    f"{where}: {column} {row[column]!r} is not a finite, non-negative decimal -- "
                    "use 0 for a route with no layout shift, and record the threshold this run was "
                    "held to so a relaxed budget leaves a trace"
                )
        if measured is not None and budget is not None:
            cls_over = 1 if measured > budget else 0

    probe = row["Interaction Probe"].lower()
    if not probe:
        findings.append(
            f"{where}: no Interaction Probe ({'/'.join(sorted(PROBE_MODES))}) -- whether this page "
            "was clicked before its metrics were read is what decides whether they mean anything"
        )
    elif probe not in PROBE_MODES:
        findings.append(
            f"{where}: Interaction Probe {row['Interaction Probe']!r} is not one of "
            f"{'/'.join(sorted(PROBE_MODES))}"
        )
    elif probe == "same-visit":
        findings.append(
            f"{where}: Interaction Probe same-visit -- Playwright's click is a trusted input, which "
            "terminates LCP observation and marks every layout shift within 500 ms hadRecentInput. "
            "The LCP on this row is truncated and the CLS is missing the shifts the click caused: "
            "probe on a separate visit, or record this row Blocked"
        )

    # ---- severity: recomputed, and capped ------------------------------------------------
    severity = row["Severity"].lower()
    if severity == S1:
        findings.append(
            f"{where}: Severity S1 on a perf row -- no WCAG criterion and no standard of any kind "
            "mandates a performance budget, and a timing taken on an unthrottled dev machine "
            "against localhost cannot establish that the page is broken, which is what S1 means "
            "in every other pass. The ceiling here is S2"
        )
    else:
        graded: dict[str, int] = {}
        every: list[str] = []
        for name, _floor in PERF_GATING:
            if name == CLS_OVER_BUDGET:
                # Off chromium there is no CLS to grade, so it must leave `every` too -- the
                # all-parsed test in _check_severity is a length comparison between the two.
                if not chromium_only_ok:
                    continue
                every.append(name)
                if cls_over is not None:
                    graded[name] = cls_over
            else:
                every.append(name)
                if name in counts:
                    graded[name] = counts[name]
        findings.extend(_check_severity(
            row, where, graded, PERF_GATING, tuple(every),
            s1_because="",  # unreachable: S1 is rejected above, so nothing can force it
            inflated_because=(
                "LCP and TTFB are environment-sensitive and have no normative upstream, so they "
                "are trended and never graded -- record the numbers and grade the row none"
            ),
        ))

    # Every measured row must be re-readable next run: trend comparison is the point of the pass,
    # and a row with no persisted record cannot be compared to anything.
    if not row["Evidence"]:
        findings.append(
            f"{where}: measured without an Evidence path -- the run JSONL entry that makes this "
            "row comparable to the next run's; a metric with no history is not a trend"
        )
    if severity != NO_SEVERITY and not row["Notes"]:
        findings.append(
            f"{where}: {row['Severity']} without Notes naming the resource or element -- a "
            "performance defect nobody can locate is not actionable"
        )
    advisory_hits = [c for c in PERF_ADVISORY if counts.get(c, 0) > 0]
    if advisory_hits and not row["Notes"]:
        findings.append(
            f"{where}: {', '.join(advisory_hits)} above 0 without Notes naming the resource(s) -- "
            "an advisory finding is still a finding, and this row is its only record"
        )
    return findings


PERF = Profile(
    name="perf",
    written_by="perf-tester (client-side performance capture)",
    columns=(
        "Route",
        "State",
        "Status",
        "HTTP",
        "Requested URL",
        "Final URL",
        "Assertion",
        "Engine",
        "Samples",
        "TTFB ms",
        "LCP ms",
        "LCP Element",
        "CLS",
        "CLS Budget",
        "Requests",
        "Transfer KB",
        "Opaque Requests",
        "Largest Resource KB",
        "Oversized Requests",
        "Fonts No Swap",
        "Render Blocking",
        "Interaction Probe",
        "Severity",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"measured"}),
    ident_columns=("Route", "State"),
    extra=_perf_extra,
)


# ---------------------------------------------------------------------------------------
# Profile: qa-reporter's deduplicated findings rollup (#118)
#
# Repeated shared UI inflates raw counts enormously. Measured on a real crawl: **773**
# "disclosure trigger without aria-expanded" and **445** "icon-only control without
# accessible name" -- every instance real, but the DISTINCT defect count was about **18**
# for the first, one navbar defect repeating across 72 pages.
#
# Reported raw those numbers are worse than useless. They bury the small number of real
# fixes, and a developer told "773 a11y defects" disbelieves the report; told "18 defects,
# one of which is on every page", they fix the navbar. The same arithmetic decides whether
# `qa-reporter` files 18 issues or 773.
#
# So one row here is ONE DISTINCT DEFECT, and the guarantees are arithmetic rather than
# stylistic: signatures cannot repeat (that is the dedupe), instances cannot be fewer than
# the routes they span, and the file must be ordered by severity then reach so the ranking
# claim is true of the artifact rather than asserted about it.
# ---------------------------------------------------------------------------------------
FINDING_SEVERITIES = {"s1", "s2", "s3"}
# Every finding source must be able to land here -- #118 is explicit that dedupe applies to
# all of them, not just the a11y pass where the 773 was found.
FINDING_SOURCES = {"a11y", "links", "runtime", "visual", "interaction", "functional", "api",
                   "perf", "security", "keyboard", "forms", "emulation"}
_SEVERITY_RANK = {"s1": 0, "s2": 1, "s3": 2}


def _findings_extra(row: dict[str, str], where: str, status: str) -> list[str]:
    """One distinct defect: its reach must be recorded, and the arithmetic must hold."""
    findings: list[str] = []

    if not row["Signature"]:
        findings.append(
            f"{where}: no Signature -- without a stable one, dedupe cannot be checked and "
            "the same defect lands twice under two raw selectors"
        )

    source = row["Source"].lower()
    if not source:
        findings.append(f"{where}: no Source (which pass found it)")
    elif source not in FINDING_SOURCES:
        findings.append(
            f"{where}: Source {row['Source']!r} is not one of {'/'.join(sorted(FINDING_SOURCES))}"
        )

    severity = row["Severity"].lower()
    if not severity:
        findings.append(f"{where}: no Severity ({'/'.join(sorted(FINDING_SEVERITIES))})")
    elif severity not in FINDING_SEVERITIES:
        findings.append(
            f"{where}: Severity {row['Severity']!r} is not one of "
            f"{'/'.join(sorted(FINDING_SEVERITIES))}"
        )

    counts: dict[str, int] = {}
    for column in ("Instances", "Routes"):
        raw = row[column]
        if not raw:
            findings.append(f"{where}: no {column} count -- reach is what makes this rankable")
            continue
        try:
            value = int(raw)
        except ValueError:
            findings.append(f"{where}: {column} {raw!r} records no number")
            continue
        if value < 1:
            findings.append(
                f"{where}: {column} is {value} -- a reported defect occurs at least once"
            )
            continue
        counts[column] = value

    if len(counts) == 2 and counts["Instances"] < counts["Routes"]:
        findings.append(
            f"{where}: {counts['Instances']} instance(s) across {counts['Routes']} route(s) is "
            "impossible -- a defect appears at least once per route it affects, so one of these "
            "is an occurrence count mistaken for a distinct count"
        )

    examples = [e for e in row["Example Routes"].replace(";", " ").split() if e]
    if not examples:
        findings.append(
            f"{where}: no Example Routes -- a distinct finding nobody can locate is not "
            "actionable, which is the complaint dedupe is supposed to answer"
        )
    elif "Routes" in counts and len(examples) > counts["Routes"]:
        findings.append(
            f"{where}: {len(examples)} example route(s) cited but Routes says "
            f"{counts['Routes']} -- the examples cannot outnumber the affected routes"
        )

    if not row["Evidence"]:
        findings.append(
            f"{where}: no Evidence path -- the full instance list must stay retrievable, or "
            "collapsing 773 occurrences into one row destroys the data instead of summarising it"
        )
    return findings


def _findings_cross(rows: list[dict[str, str]]) -> list[str]:
    """The two guarantees that only exist across the whole file."""
    findings: list[str] = []

    # 1. Dedupe itself. A repeated signature means the rollup did not roll up.
    seen: dict[str, int] = {}
    for offset, row in enumerate(rows):
        sig = row["Signature"]
        if not sig:
            continue
        if sig in seen:
            findings.append(
                f"row {offset + 2}: Signature {sig!r} already appeared on row {seen[sig]} -- "
                "a findings rollup with a repeated signature has not deduplicated, which is the "
                "whole point of the artifact"
            )
        else:
            seen[sig] = offset + 2

    # 2. Ordering, so "ranked by severity x reach" is true of the file rather than claimed
    #    about it. Severity ascending (S1 first), then reach descending.
    keys: list[tuple[int, int, int]] = []
    for offset, row in enumerate(rows):
        if row["Status"].lower() != "confirmed":
            continue  # Blocked / Out of Scope rows are not ranked findings
        rank = _SEVERITY_RANK.get(row["Severity"].lower())
        try:
            reach = int(row["Routes"])
        except ValueError:
            continue
        if rank is None:
            continue
        keys.append((rank, -reach, offset + 2))
    for (r1, n1, line1), (r2, n2, line2) in zip(keys, keys[1:]):
        if (r1, n1) > (r2, n2):
            findings.append(
                f"row {line2}: ordered after row {line1} but outranks it "
                f"(severity/reach) -- the report must rank by distinct severity then reach, so "
                "the highest-impact defect is not buried below a single-page cosmetic one"
            )
            break  # one ordering finding is enough to act on; listing every pair is noise
    return findings


FINDINGS = Profile(
    name="findings",
    written_by="qa-reporter",
    columns=(
        "Signature",
        "Source",
        "Status",
        "Severity",
        "Title",
        "Instances",
        "Routes",
        "Example Routes",
        "Evidence",
        "Notes",
    ),
    result_statuses=frozenset({"confirmed"}),
    ident_columns=("Signature", "Title"),
    extra=_findings_extra,
    page_identity=False,
    cross=_findings_cross,
)


PROFILES: tuple[Profile, ...] = (
    FUNCTIONAL, A11Y, RUNTIME, KEYBOARD, FORMS, EMULATION, PERF, FINDINGS,
)

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
        if profile.page_identity:
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

    # ---- a rollup row: no single page to identify, so its own rules carry it ----------
    if not profile.page_identity:
        findings.extend(profile.extra(row, where, status))
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
    findings.extend(profile.cross(rows))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a QA evidence CSV carries validated page identity."
    )
    parser.add_argument(
        "csv_path", nargs="?",
        help="path to any evidence CSV -- functional summary, a11y pages, runtime capture, "
             "keyboard walk, forms pass, or findings rollup (the kind is detected from the "
             "header; run --contracts to list them)",
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
