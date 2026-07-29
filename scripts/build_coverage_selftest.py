#!/usr/bin/env python3
"""Prove the coverage builder's guards fire -- and stay silent on a conforming mapping.

Run:  python3 scripts/build_coverage.py --selftest   (or execute this file directly)

The totality guard IS the deliverable of #124. A coverage matrix nobody can trust is worse
than no matrix, because it gets cited as proof of completeness. So the guard has to be shown
failing, not just passing: a check never observed failing is not known to work.

Fixtures are synthetic mappings, deliberately adversarial rather than realistic -- an omitted
entry, a ghost reference, the SAME entry claimed twice (which a set would merge silently), an
out-of-scope row with no reason. Realistic input would only exercise the happy path.

Costs nothing: no network, no corpora needed for the guard tests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_coverage as bc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

# A tiny synthetic corpus so the guard tests never depend on the licensed kits being present.
TW = {"application-ui/elements/buttons", "application-ui/elements/badges"}
FB = {"Buttons", "Badge"}


def _tick() -> None:
    global CHECKS
    CHECKS += 1


# Evidence strings for the synthetic rows. These must genuinely occur in the real reference
# docs, because the evidence guard reads the real docs -- a fake string here would make the
# "clean" fixtures pass for the wrong reason.
SYNTH_EVIDENCE = {"Button": "## Button\n", "Badge": "## Badge / Tag / Chip"}


def _run_guard(entries, evidence, tw, fb):
    """Swap BOTH module tables, run the guard, restore. They are cross-checked, so patching
    only ENTRIES makes every fixture fail on orphaned evidence keys."""
    orig_entries, orig_evidence = bc.ENTRIES, bc.DOCUMENTED_EVIDENCE
    bc.ENTRIES = entries
    bc.DOCUMENTED_EVIDENCE = SYNTH_EVIDENCE if evidence is None else evidence
    try:
        bc.verify_totality(TW if tw is None else tw, FB if fb is None else fb)
    finally:
        bc.ENTRIES, bc.DOCUMENTED_EVIDENCE = orig_entries, orig_evidence


def expect_ok(label: str, entries: tuple[bc.Entry, ...], *, tw=None, fb=None, evidence=None) -> None:
    """The guard must STAY SILENT on a complete, consistent mapping."""
    _tick()
    try:
        _run_guard(entries, evidence, tw, fb)
    except bc.BuildError as exc:
        FAILURES.append(f"{label}: expected clean, got BuildError:\n{exc}")


def expect_error(label: str, entries: tuple[bc.Entry, ...], *, contains: str,
                 tw=None, fb=None, evidence=None) -> None:
    """The guard must FIRE, and say something actionable."""
    _tick()
    try:
        _run_guard(entries, evidence, tw, fb)
    except bc.BuildError as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message does not mention {contains!r}:\n{exc}")
        return
    FAILURES.append(f"{label}: expected BuildError, mapping was accepted")


COMPLETE = (
    bc.E("Button", bc.COMPONENT, "documented", tw=["application-ui/elements/buttons"], fb=["Buttons"]),
    bc.E("Badge", bc.COMPONENT, "documented", tw=["application-ui/elements/badges"], fb=["Badge"]),
)


def run() -> int:
    # ---- the silence proof -------------------------------------------------------------
    expect_ok("complete mapping", COMPLETE)

    # ---- the guarantee: an unclassified corpus entry FAILS the build -------------------
    expect_error(
        "a Tailwind directory nobody classified",
        (COMPLETE[0],),  # drops the Badge row, so application-ui/elements/badges is orphaned
        contains="not classified",
    )
    expect_error(
        "a Flowbite entry nobody classified",
        (
            bc.E("Button", bc.COMPONENT, "documented",
                 tw=["application-ui/elements/buttons", "application-ui/elements/badges"],
                 fb=["Buttons"]),
        ),
        contains="not classified",
    )
    # The message must name the straggler, or it cannot be acted on.
    _tick()
    original = bc.ENTRIES
    bc.ENTRIES = (COMPLETE[0],)
    try:
        bc.verify_totality(TW, FB)
        FAILURES.append("straggler naming: expected BuildError")
    except bc.BuildError as exc:
        for expected in ("application-ui/elements/badges", "Badge"):
            if expected not in str(exc):
                FAILURES.append(f"straggler naming: message omits {expected!r}:\n{exc}")
    finally:
        bc.ENTRIES = original

    # ---- a reference to something the corpus does not have ----------------------------
    expect_error(
        "ghost Tailwind reference (renamed upstream)",
        COMPLETE + (bc.E("Ghost", bc.COMPONENT, "derivable", build="x", tw=["application-ui/elements/nope"]),),
        contains="do not exist in the corpus",
    )
    expect_error(
        "ghost Flowbite reference",
        COMPLETE + (bc.E("Ghost", bc.COMPONENT, "derivable", build="x", fb=["Nonexistent"]),),
        contains="do not exist in the corpus",
    )

    # ---- the same corpus entry claimed twice ------------------------------------------
    # A dict/set keyed by the reference would MERGE these silently, so the double-claim is
    # checked explicitly. Two rows each asserting they own `buttons` means one of them is
    # wrong, and the matrix would double-count coverage.
    expect_error(
        "two rows claim the same Tailwind directory",
        COMPLETE + (
            bc.E("Button (duplicate owner)", bc.COMPONENT, "derivable", build="x",
                 tw=["application-ui/elements/buttons"]),
        ),
        contains="claimed by 2 rows",
    )
    expect_error(
        "two rows claim the same Flowbite entry",
        COMPLETE + (bc.E("Badge (duplicate owner)", bc.COMPONENT, "derivable", build="x", fb=["Badge"]),),
        contains="claimed by 2 rows",
    )

    # ---- the guidance axis must be honest ----------------------------------------------
    # Retired vocabulary: `deferred` / `declined` answered "will we offer this?", which is the
    # wrong question for a JIT kit -- components are built on demand, so nothing is withheld.
    # These fixtures pin the replacement: every row says HOW to build it and WHERE to use it.
    BUTTON_ONLY = {"Button": SYNTH_EVIDENCE["Button"]}

    def badge(status, **kw):
        return (COMPLETE[0], bc.E("Badge", bc.COMPONENT, status,
                                  tw=["application-ui/elements/badges"], fb=["Badge"], **kw))

    expect_ok(
        "a complete derivable row",
        badge("derivable", build="a `size-2 rounded-full` span plus sr-only text"),
        evidence=BUTTON_ONLY,
    )
    expect_ok(
        "a complete needs-doctrine row",
        badge("needs doctrine #95", build="the documented Select until the entry lands"),
        evidence=BUTTON_ONLY,
    )
    expect_error(
        "derivable that does not say what to build it FROM",
        badge("derivable"),
        contains="does not say what to build it FROM", evidence=BUTTON_ONLY,
    )
    expect_error(
        "whitespace-only build guidance is not guidance",
        badge("derivable", build="   "),
        contains="does not say what to build it FROM", evidence=BUTTON_ONLY,
    )
    expect_error(
        "needs doctrine with no issue number — an untracked gap",
        badge("needs doctrine", build="the documented Select"),
        contains="names no issue", evidence=BUTTON_ONLY,
    )
    expect_error(
        "needs doctrine with no nearest-guidance fallback",
        badge("needs doctrine #95"),
        contains="no nearest-guidance fallback", evidence=BUTTON_ONLY,
    )
    # The retired statuses must be rejected outright, not silently accepted as free-text.
    for retired in ("deferred", "declined", "out of scope (no product need)", "planned #95"):
        expect_error(
            f"the retired status {retired!r} is rejected",
            badge(retired, build="something"),
            contains="not one of documented / derivable / needs doctrine",
            evidence=BUTTON_ONLY,
        )
    # WHERE/WHEN guidance is required for every row. This fixture uses a (kind, family) pair
    # with no USE default and no USE entry, so `resolve_use` genuinely returns "" -- without it
    # the guard has no reachable failure path and would be a gate that cannot fail.
    expect_error(
        "a row whose kind/family combination resolves no WHERE/WHEN guidance",
        (
            bc.E("Nameless marketing primitive", bc.PRIMITIVE, "derivable", build="a `@utility`",
                 tw=["marketing/sections/heroes"]),
        ),
        contains="no WHERE/WHEN guidance",
        tw={"marketing/sections/heroes"}, fb=set(), evidence={},
    )
    expect_ok(
        "the same row once USE covers it",
        (
            bc.E("Hero section", bc.COMPOSITION, "derivable", build="a `@utility`",
                 tw=["marketing/sections/heroes"]),
        ),
        tw={"marketing/sections/heroes"}, fb=set(), evidence={},
    )

    # Belt-and-braces over the REAL tables, independent of the fixtures above.
    _tick()
    missing_use = [e.name for e in bc.ENTRIES if not bc.resolve_use(e).strip()]
    if missing_use:
        FAILURES.append(f"rows with no WHERE/WHEN guidance: {missing_use}")
    _tick()
    missing_build = [
        e.name for e in bc.ENTRIES
        if not e.is_documented and not bc.resolve_build(e).strip()
    ]
    if missing_build:
        FAILURES.append(f"non-documented rows with no build guidance: {missing_build}")


    # ---- an empty status, and duplicate canonical names ------------------------------
    expect_error(
        "a row with no status",
        (COMPLETE[0], bc.E("Badge", bc.COMPONENT, "",
                           tw=["application-ui/elements/badges"], fb=["Badge"])),
        contains="no guidance level",
        evidence=BUTTON_ONLY,
    )
    expect_error(
        "whitespace-only status",
        (COMPLETE[0], bc.E("Badge", bc.COMPONENT, "   ",
                           tw=["application-ui/elements/badges"], fb=["Badge"])),
        contains="no guidance level",
        evidence=BUTTON_ONLY,
    )
    expect_error(
        "duplicate canonical names",
        (
            COMPLETE[0],
            bc.E("Button", bc.COMPONENT, "derivable", build="x", tw=["application-ui/elements/badges"], fb=["Badge"]),
        ),
        contains="duplicate canonical names",
        evidence=BUTTON_ONLY,
    )

    # ---- the `shipped` column must be evidenced, not asserted -------------------------
    # This is the guard that caught a real wrong claim while #124 was being written: "Link"
    # was marked shipped on the strength of a Button `link` VARIANT, with no standalone
    # inline-link token anywhere. A wrong `shipped` is the dangling reference v1.26.0 fixed.
    expect_error(
        "documented with no evidence entry",
        COMPLETE,
        contains="no entry in DOCUMENTED_EVIDENCE",
        evidence={"Button": "## Button\n"},  # Badge is shipped but uncited
    )
    expect_error(
        "documented citing a string that is not in the docs",
        COMPLETE,
        contains="does not appear in any reference doc",
        evidence={"Button": "## Button\n", "Badge": "## Badge That Was Never Written"},
    )
    expect_error(
        "a non-documented row citing evidence",
        (
            COMPLETE[0],
            bc.E("Badge", bc.COMPONENT, "derivable", build="x",
                 tw=["application-ui/elements/badges"], fb=["Badge"]),
        ),
        contains="only shipped rows cite doc evidence",
        evidence=SYNTH_EVIDENCE,
    )
    expect_error(
        "an evidence key matching no row",
        COMPLETE,
        contains="matching no row",
        evidence=dict(SYNTH_EVIDENCE, **{"Ghost Component": "## Button\n"}),
    )
    # Near miss: a heading that is a PREFIX of another must not satisfy the longer one. If
    # evidence were "## Button" without the newline, a docs file containing only
    # "## Button group" would wrongly satisfy a Button row.
    _tick()
    if "## Button\n" not in bc.reference_blob():
        FAILURES.append("expected '## Button\\n' in the reference docs — evidence anchoring is wrong")
    if "## Button group\n" not in bc.reference_blob():
        FAILURES.append("expected '## Button group\\n' in the reference docs")

    # ---- the real mapping must be complete against the real corpus, when present ------
    _tick()
    try:
        tw = bc.discover_tw()
        bc.verify_totality(tw, bc.discover_fb())
    except bc.BuildError as exc:
        if "corpus not found" in str(exc):
            print("note: licensed corpora absent — skipped the live totality check", file=sys.stderr)
        else:
            FAILURES.append(f"live mapping is not total:\n{exc}")

    # ---- the committed file must match what the builder produces ---------------------
    _tick()
    if bc.TW_ROOT.is_dir():
        if not bc.OUT.is_file():
            FAILURES.append(f"{bc.OUT} does not exist — the generated matrix is not committed")
        elif bc.OUT.read_text(encoding="utf-8") != bc.build():
            FAILURES.append(
                f"{bc.OUT.name} is stale — regenerate with `python3 scripts/build_coverage.py`"
            )

    # ---- unreadable docs must fail CLOSED, not silently skip the evidence check -------
    # Without this fixture the `if not blob:` branch is never exercised, and a fail-open
    # there would let every `shipped` claim through unverified whenever the docs move.
    _tick()
    real_out = bc.OUT
    bc.OUT = Path(tempfile.mkdtemp(prefix="coverage-nodocs-")) / "gone" / "coverage.md"
    try:
        problems = bc.verify_shipped_evidence()
        if not any("cannot read the reference docs" in p for p in problems):
            FAILURES.append(
                "unreadable docs: expected a problem, got "
                f"{problems or 'silence'} — the evidence check must fail closed"
            )
    finally:
        bc.OUT = real_out

    # ---- the builder refuses to emit a hollow file when the corpus is missing --------
    _tick()
    real_root = bc.TW_ROOT
    bc.TW_ROOT = Path(tempfile.mkdtemp(prefix="coverage-absent-")) / "does-not-exist"
    try:
        bc.build()
        FAILURES.append("absent corpus: expected BuildError, but a file was produced")
    except bc.BuildError as exc:
        if "corpus not found" not in str(exc):
            FAILURES.append(f"absent corpus: unexpected message: {exc}")
    finally:
        bc.TW_ROOT = real_root

    # ---- the two Flowbite names #124 misattributed must stay out of the catalogue ----
    # Recorded as a test because the issue asserted both, and re-adding them from the issue
    # text would put components in the matrix that Flowbite does not have.
    _tick()
    fb = bc.discover_fb()
    for absent in ("Separator", "Cookie Consent", "Cookie-consent"):
        if absent in fb:
            FAILURES.append(
                f"{absent!r} is in FLOWBITE_CATALOG but is not a Flowbite component "
                "(their separator is `HR`; no cookie-consent component exists)"
            )
    if "HR" not in fb:
        FAILURES.append("`HR` missing from the Flowbite catalogue — it is their separator")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"build_coverage selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
