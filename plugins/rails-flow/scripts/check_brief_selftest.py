#!/usr/bin/env python3
"""Prove every brief rule fires -- and, harder, that it stays silent on a good brief.

Run:  python3 check_brief.py --selftest   (or execute this file directly)

The silent direction is what decides whether this survives contact with a real engagement, because
the duplication rule is a **similarity** rule and similarity rules are false-positive machines. A
brief and the PRD it indexes describe the same product, in the same domain vocabulary, to the same
reader. Four shapes look exactly like duplication and are not:

  * a **blockquote** -- #130 asks for "the problem in the user's words", so the one place the brief
    is SUPPOSED to borrow verbatim is the place a naive rule flags first.
  * a **fenced block** -- a quoted config or schema is meant to be byte-identical.
  * a **table row** -- the coverage map's Source cell quotes the source's own heading text BY
    DESIGN, so the citation mechanism would flag itself.
  * a run **just under** the threshold -- shared product nouns are not a copy.

Two more near-misses guard rules that read ordinary prose: `TBD` inside `## Open questions` is that
section's whole job (a recorded unknown with an owner) while `TBD` anywhere else is an unrecorded
one; and `## Non-goals (out of scope)` must not be collected as the scope section, which is the
class check_handoff.py hit from the other side when `### Interface` swallowed its in-scope list.

The last check runs the REAL shipped command against the checker's own section contract. Everything
else here is a fixture, and a fixture cannot notice that the template we ship writes a brief our own
gate would reject on its first run.

Costs nothing: no network, no Rails, no bundler.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_brief as cb  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TICK = "`" * 3

PRD = """# Bramley Dental — product requirements

## Who this is for
Single-site private dental practices in the UK with two to six chairs, whose front desk books
appointments on paper today.

## The problem
Reception spends the first hour of every day reconciling the paper diary against the whiteboard by
the door, and a double booking still reaches the chair about twice a week.

## Milestones
Booking, then reminders, then reporting.

## What good looks like
Reception stops reconciling by hand, and no double booking reaches a chair for a full month.
"""

COVERAGE = """## Coverage map

**Mode: A — documents.** Intake read the documents first and interviewed only the gaps.

| Brief section | State | Source |
|---|---|---|
| What and for whom | answered | `docs/prd.md` § "Who this is for" |
| Problem | answered | `docs/prd.md` § "The problem" |
| Scope | thin | `docs/prd.md` § "Milestones" — three nouns, not a boundary |
| Non-goals | decided | D-016 |
| Constraints | decided | D-014 |
| Journeys | decided | D-015 |
| Success | answered | `docs/prd.md` § "What good looks like" |
"""

WHAT = """## What and for whom
Indexed at `docs/prd.md` § "Who this is for". Nothing below supersedes that file.
"""

PROBLEM = """## Problem
> "We check the book against the board every morning and it still goes wrong twice a week, and
> then someone sits in reception for forty minutes."

Written up at `docs/prd.md` § "The problem".
"""

SCOPE = """## Scope
First slice is the diary only: create, move and cancel one appointment against one chair.
"""

NON_GOALS = """## Non-goals
- No patient-facing self-service booking in the first slice; the desk stays the only writer.
- No clinical notes, ever — that belongs to the practice management system and its auditors.
- No SMS reminders until the diary is trusted; a reminder for a wrong slot is worse than silence.
"""

CONSTRAINTS = """## Constraints
Rails 8 on one Hetzner box, shipped with Kamal, no managed platform. Recorded as D-014.
"""

JOURNEYS = """## Journeys
A receptionist seats a walk-in on a free chair; a receptionist slides three bookings when the
hygienist runs late. Recorded as D-015.
"""

SUCCESS = """## Success
The board by the door comes down, and a clash becomes an incident rather than a Tuesday.
"""

OPEN = """## Open questions
- Does the group plan bill per site in year one? owner: practice manager
- Which chair is the default when nobody picks one? owner: Fisayo
"""

DECISIONS = """## Decisions
- D-014 — one box with Kamal, over a managed platform: the practice has no ops budget.
- D-015 — the two journeys above are the first slice; reporting waits for real diary data.
- D-016 — self-service booking is out of the first slice, and out of the quote.
"""

GOOD = "# Product brief — Bramley Dental diary\n\n" + "\n".join(
    (COVERAGE, WHAT, PROBLEM, SCOPE, NON_GOALS, CONSTRAINTS, JOURNEYS, SUCCESS, OPEN, DECISIONS)
)

DECISIONS_FILE = """# Decisions

## D-014 — one box with Kamal
Alternatives: Heroku, Fly. Reversal condition: a second practice signs.

## D-015 — diary first
Alternatives: reminders first. Reversal condition: the diary lands and nobody uses it.

## D-016 — no self-service booking in slice one
Alternatives: patient portal. Reversal condition: the desk asks for it.
"""


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _project(body: str, *, prd: str = PRD, decisions: str | None = None) -> tuple[Path, Path]:
    """A throwaway project root holding the brief and the source it cites."""
    root = Path(tempfile.mkdtemp(prefix="railsflow-brief-"))
    (root / "docs").mkdir()
    (root / "docs" / "prd.md").write_text(prd, encoding="utf-8")
    brief = root / "docs" / "BRIEF.md"
    brief.write_text(body, encoding="utf-8")
    if decisions is not None:
        (root / "docs" / "DECISIONS.md").write_text(decisions, encoding="utf-8")
    return brief, root


def swap(section: str, replacement: str) -> str:
    """The good brief with one section replaced -- so every fixture differs by one thing."""
    assert section in GOOD, f"fixture drift: {section[:40]!r} is not in GOOD"
    return GOOD.replace(section, replacement)


def drop(section: str) -> str:
    return swap(section, "")


def expect_clean(label: str, body: str, *, prd: str = PRD, decisions: str | None = None) -> None:
    _tick()
    brief, root = _project(body, prd=prd, decisions=decisions)
    dec = (root / "docs" / "DECISIONS.md") if decisions is not None else None
    try:
        findings = cb.check(cb.parse(brief), root, dec)
    except cb.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_findings(label: str, body: str, *, contains: str, prd: str = PRD,
                    decisions: str | None = None) -> None:
    _tick()
    brief, root = _project(body, prd=prd, decisions=decisions)
    dec = (root / "docs" / "DECISIONS.md") if decisions is not None else None
    try:
        findings = cb.check(cb.parse(brief), root, dec)
    except cb.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings omit {contains!r}: {blob}")


def expect_unusable(label: str, body: str, *, contains: str) -> None:
    _tick()
    brief, _root = _project(body)
    try:
        cb.parse(brief)
    except cb.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message omits {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, input was accepted")


# 20 words lifted verbatim out of PRD's "The problem" -- the copy the whole rule exists to catch.
LIFTED = ("Reception spends the first hour of every day reconciling the paper diary against the "
          "whiteboard by the door.")
# 11 tokens of the same sentence: one under DUP_WINDOW, so it must stay silent.
ELEVEN = "Reception spends the first hour of every day reconciling the paper"


def run() -> int:  # noqa: PLR0915 -- a flat list of fixtures reads better than nested helpers
    # ---- the silence proof --------------------------------------------------------------
    expect_clean("a well-formed brief", GOOD)
    expect_clean("...and with the decisions file present", GOOD, decisions=DECISIONS_FILE)

    # ---- unusable: this is not a brief ---------------------------------------------------
    expect_unusable(
        "a file with no sections at all",
        "# Brief\n\nSome prose and nothing else.\n",
        contains="carries no `## ` sections",
    )
    expect_unusable(
        "sections, but not one of the ten",
        "## Notes\n\nprose\n\n## Links\n\nmore prose\n",
        contains="this is not a brief",
    )
    _tick()
    try:
        cb.parse(Path(tempfile.mkdtemp(prefix="railsflow-brief-")) / "absent.md")
        FAILURES.append("missing file: expected UNUSABLE")
    except cb.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- every required section is required ----------------------------------------------
    for label, section in (
        ("coverage map", COVERAGE), ("what and for whom", WHAT), ("problem", PROBLEM),
        ("scope", SCOPE), ("non-goals", NON_GOALS), ("constraints", CONSTRAINTS),
        ("journeys", JOURNEYS), ("success", SUCCESS), ("open questions", OPEN),
        ("decisions", DECISIONS),
    ):
        expect_findings(
            f"a brief with no {label!r} section", drop(section),
            contains=f"no `## {label}` section",
        )

    # NEAR MISS: a heading may honestly name two sections, and only one of them is what it IS.
    # Without the disqualifier list, `scope` word-matches inside "Non-goals (out of scope)", that
    # heading is collected as the scope section, and a brief with NO scope section reports clean.
    expect_findings(
        "`## Non-goals (out of scope)` is not the scope section",
        swap(SCOPE, "").replace("## Non-goals", "## Non-goals (out of scope)"),
        contains="no `## scope` section",
    )
    expect_clean(
        "...and with a real scope section beside it, both resolve",
        GOOD.replace("## Non-goals", "## Non-goals (out of scope)"),
    )

    # ---- the coverage map: the mode ------------------------------------------------------
    expect_findings(
        "a coverage map declaring no mode",
        swap(COVERAGE, COVERAGE.replace("**Mode: A — documents.** Intake read the documents "
                                        "first and interviewed only the gaps.",
                                        "Intake read the documents first.")),
        contains="declares no intake mode",
    )
    expect_findings(
        "a coverage map declaring two modes",
        swap(COVERAGE, COVERAGE.replace("**Mode: A — documents.**",
                                        "**Mode: A — documents**, then **Mode: B**.")),
        contains="declares 2 modes",
    )
    expect_findings(
        "the mode letter and the mode word disagree",
        swap(COVERAGE, COVERAGE.replace("**Mode: A — documents.**", "**Mode: A — greenfield.**")),
        contains="the letter and the word disagree",
    )
    # NEAR MISS for the same rule, and the reason it is scoped to the declaration clause: a Mode B
    # brief says "no documents exist" as a plain statement of fact. A rule reading the rest of the
    # line — or the section — flags that as a contradiction and gets the mode declaration deleted.
    expect_clean(
        "a mode word in the prose after the declaration is not a contradiction",
        swap(COVERAGE, COVERAGE.replace(
            "**Mode: A — documents.** Intake read the documents first and interviewed only the "
            "gaps.",
            "**Mode: B — codebase.** No documents exist; read the routes and the schema. "
            "[inferred]")),
    )
    expect_clean(
        "Mode B with its inferences tagged",
        swap(COVERAGE, COVERAGE.replace("**Mode: A — documents.**", "**Mode: B — codebase.**"))
        .replace("First slice is the diary only",
                 "First slice is the diary only [inferred] from `config/routes.rb`"),
    )
    expect_findings(
        "Mode B stating nothing as inferred",
        swap(COVERAGE, COVERAGE.replace("**Mode: A — documents.**", "**Mode: B — codebase.**")),
        contains="carries no `[inferred]`",
    )

    # ---- the coverage map: the rows ------------------------------------------------------
    expect_findings(
        "a coverage map with no rows at all",
        swap(COVERAGE, "## Coverage map\n\n**Mode: A — documents.** Read the docs.\n"),
        contains="holds no rows",
    )
    expect_findings(
        "a mapped section with no row",
        swap(COVERAGE, COVERAGE.replace(
            "| Constraints | decided | D-014 |\n", "")),
        contains="no row for `constraints`",
    )
    expect_findings(
        "a row in a state nobody defined",
        swap(COVERAGE, COVERAGE.replace("| Scope | thin |", "| Scope | probably |")),
        contains="not one of answered, decided, thin, missing",
    )
    expect_findings(
        "an `answered` row citing no source",
        swap(COVERAGE, COVERAGE.replace(
            '| Problem | answered | `docs/prd.md` § "The problem" |',
            "| Problem | answered | the PRD covers it |")),
        contains="is `answered` but cites no source",
    )
    expect_findings(
        "a `decided` row citing no `D-nnn`",
        swap(COVERAGE, COVERAGE.replace("| Constraints | decided | D-014 |",
                                        "| Constraints | decided | agreed at intake |")),
        contains="is `decided` but cites no `D-nnn`",
    )
    expect_findings(
        "`Mode: A` with not one row answered from a source",
        swap(COVERAGE, COVERAGE.replace("answered", "decided").replace(
            '`docs/prd.md` § "Who this is for"', "D-020").replace(
            '`docs/prd.md` § "The problem"', "D-021").replace(
            '`docs/prd.md` § "What good looks like"', "D-022")),
        contains="not one row is `answered` from a source",
    )
    expect_findings(
        "a gap in the map and no open question recorded",
        swap(OPEN, "## Open questions\nNone.\n"),
        contains="not one open question is recorded",
    )
    expect_clean(
        "...and `None.` is fine once the map has no gaps",
        swap(OPEN, "## Open questions\nNone.\n").replace(
            '| Scope | thin | `docs/prd.md` § "Milestones" — three nouns, not a boundary |',
            "| Scope | decided | D-017 |"),
    )

    # ---- source references have to RESOLVE ------------------------------------------------
    expect_findings(
        "a reference to a file that does not exist",
        GOOD.replace("`docs/prd.md` § \"Who this is for\"", "`docs/brief-notes.md` § \"Audience\""),
        contains="which does not exist under",
    )
    expect_findings(
        "a reference whose locator is not in the file",
        GOOD.replace('`docs/prd.md` § "Milestones"', '`docs/prd.md` § "Release plan"'),
        contains="does not contain 'Release plan'",
    )
    expect_clean(
        "a locator that wraps across lines in the source still resolves",
        GOOD.replace('`docs/prd.md` § "Milestones"',
                     '`docs/prd.md` § "reconciling the paper diary against the whiteboard"'),
    )

    # ---- duplication: the rule, and the four shapes that are NOT duplication --------------
    expect_findings(
        "a brief that pastes a paragraph of its own source",
        swap(SCOPE, f"## Scope\n{LIFTED}\n"),
        contains="consecutive words of `docs/prd.md`",
    )
    expect_clean(
        "a blockquote of the same words is attributed quotation, not duplication",
        swap(SCOPE, f"## Scope\nFirst slice is the diary only.\n\n> {LIFTED}\n"),
    )
    expect_clean(
        "a fenced block of the same words is quoted code, not duplication",
        swap(SCOPE, f"## Scope\nFirst slice is the diary only.\n\n{TICK}text\n{LIFTED}\n{TICK}\n"),
    )
    expect_clean(
        "a table row quoting the source's own heading is the citation mechanism working",
        swap(COVERAGE, COVERAGE.replace(
            '| Scope | thin | `docs/prd.md` § "Milestones" — three nouns, not a boundary |',
            f"| Scope | thin | {LIFTED} |")),
    )
    expect_clean(
        # The 12th word has to DIVERGE, or this fixture proves nothing: the first version ended
        # "...the paper diary", and the PRD's next word is "diary" too, so it was a 12-word run
        # and fired -- a threshold fixture that tested the threshold from the wrong side.
        "eleven shared words is shared vocabulary, not a copy",
        swap(SCOPE, f"## Scope\n{ELEVEN} record, one chair at a time.\n"),
    )
    # A heading is a BOUNDARY, not an exemption: without it these two seven-word halves — each
    # genuinely from the PRD, neither long enough to matter — concatenate into a 14-word run that
    # exists in no document. A bridged match is a false positive that no author can act on, because
    # the sentence it names was never written.
    expect_clean(
        "a subheading ends a block, so two short runs do not bridge into one",
        swap(SCOPE, "## Scope\nReception spends the first hour of every\n\n### Later\n"
                    "day reconciling the paper diary against the whiteboard by the door.\n"),
    )
    expect_clean(
        "nothing is compared when the brief cites no source that resolves",
        # The duplication rule rides on resolution: with no readable source there is no corpus,
        # and inventing one from the filesystem would compare the brief against files it never
        # claimed to index.
        swap(COVERAGE, COVERAGE.replace("answered", "decided").replace(
            '`docs/prd.md` § "Who this is for"', "D-020").replace(
            '`docs/prd.md` § "The problem"', "D-021").replace(
            '`docs/prd.md` § "Milestones" — three nouns, not a boundary', "D-023").replace(
            '`docs/prd.md` § "What good looks like"', "D-022")).replace(
            "**Mode: A — documents.**", "**Mode: C — greenfield.**").replace(
            'Indexed at `docs/prd.md` § "Who this is for". Nothing below supersedes that file.',
            "Two to six chairs, one site, one front desk.").replace(
            'Written up at `docs/prd.md` § "The problem".',
            "Recorded at intake, in the practice manager's words.").replace(
            "| Scope | thin |", "| Scope | decided |"),
    )

    # ---- non-goals: the section that stops scope creep ------------------------------------
    for empty in ("## Non-goals\n- None.\n", "## Non-goals\n- TBD\n", "## Non-goals\n\n"):
        expect_findings(
            f"non-goals that say nothing: {empty.splitlines()[-1]!r}",
            swap(NON_GOALS, empty),
            contains="lists no real non-goal",
        )

    # ---- open questions: an owner, or it is deferred rather than recorded ------------------
    expect_findings(
        "an open question with no owner",
        swap(OPEN, "## Open questions\n- Does the group plan bill per site in year one?\n"),
        contains="names no owner",
    )
    expect_clean(
        # Written as a BULLET on purpose. `_None._` is not one, so it would pass the owner rule by
        # never reaching it -- a fixture that proves the carve-out only because the carve-out was
        # never needed, and a mutation removing it would survive.
        "an explicitly empty open-questions section is a real answer",
        swap(OPEN, "## Open questions\n- None.\n").replace(
            '| Scope | thin | `docs/prd.md` § "Milestones" — three nouns, not a boundary |',
            "| Scope | decided | D-017 |"),
    )

    # ---- decisions: the cited ids have to exist -------------------------------------------
    expect_findings(
        "a cited `D-nnn` the decisions file does not define",
        GOOD.replace("D-016", "D-099"),
        contains="cites D-099",
        decisions=DECISIONS_FILE,
    )
    # A decisions file that is not there, with ids citing it: written out rather than routed
    # through `expect_findings`, because that helper only creates the file when a body is given
    # and the point here is its ABSENCE.
    _tick()
    brief, root = _project(GOOD)
    absent = root / "docs" / "DECISIONS.md"
    missing_file_findings = cb.check(cb.parse(brief), root, absent)
    if not any("was never written down" in f for f in missing_file_findings):
        FAILURES.append(
            "a brief citing D-nnn with no DECISIONS.md must be a finding; got "
            f"{missing_file_findings}"
        )

    # ---- self-containment ------------------------------------------------------------------
    for phrase in (
        "Use the pricing rule as we discussed.",
        "Scope is what you mentioned on the call.",
        "Follow the plan I described in our conversation.",
    ):
        expect_findings(
            f"a brief pointing at the conversation: {phrase[:34]!r}",
            swap(SCOPE, SCOPE.rstrip() + f"\n{phrase}\n"),
            contains="points at the conversation",
        )
    expect_clean(
        "document-internal references must pass -- `above` is not `as we discussed`",
        swap(SCOPE, SCOPE.rstrip() + "\nThe coverage map above lists what the PRD already "
                                     "answers.\n"),
    )
    expect_findings(
        "an unresolved placeholder",
        swap(SCOPE, SCOPE.rstrip() + "\nThe client is <client name> and the deadline is <date>.\n"),
        contains="unresolved placeholder",
    )
    expect_findings(
        "TBD outside the open questions",
        swap(CONSTRAINTS, CONSTRAINTS.rstrip() + "\nBudget: TBD.\n"),
        contains="outside `## Open questions`",
    )
    expect_clean(
        # The carve-out that makes the rule usable: an open question is a RECORDED unknown with an
        # owner. Flagging TBD there would delete the section's whole purpose.
        "TBD inside the open questions is that section's job",
        swap(OPEN, OPEN.rstrip() + "\n- Compliance review date: TBD. owner: practice manager\n"),
    )

    # An unreachable failure path is the one that is wrong when it finally runs, so the
    # rules-module-absent branch is exercised through the seam. It must be a FINDING: "could not
    # check" reported as clean is a skip masquerading as a pass.
    _tick()
    original = cb._self_containment_rules
    cb._self_containment_rules = lambda: None
    try:
        brief, root = _project(GOOD)
        without = cb.check(cb.parse(brief), root)
    finally:
        cb._self_containment_rules = original
    if not any("UNVERIFIED, not satisfied" in f for f in without):
        FAILURES.append(
            "with check_handoff.py absent the self-containment rules cannot run, and that has to "
            f"be a finding rather than a clean pass; got: {without}"
        )

    # ---- the CLI has to refuse an unusable invocation too ----------------------------------
    _tick()
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            cb.main([])
        FAILURES.append("no path and no --selftest: expected a usage error")
    except SystemExit as exc:
        if exc.code != 2:
            FAILURES.append(f"no path and no --selftest: exited {exc.code}, expected 2")
    _tick()
    brief, root = _project(GOOD)
    with contextlib.redirect_stderr(io.StringIO()):
        code = cb.main([str(brief), "--root", str(root / "does-not-exist")])
    if code != 2:
        FAILURES.append(f"--root pointing at nothing: exited {code}, expected 2 (unusable)")
    _tick()
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        code = cb.main([str(brief), "--root", str(root)])
    if code != 0:
        FAILURES.append(f"the good brief through the CLI: exited {code}, expected 0")
    _tick()
    bad, bad_root = _project(swap(NON_GOALS, "## Non-goals\n- None.\n"))
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        code = cb.main([str(bad), "--root", str(bad_root)])
    if code != 1:
        FAILURES.append(f"a brief with findings through the CLI: exited {code}, expected 1")

    # ---- the check a fixture cannot make: the REAL command vs this checker's contract ------
    # The template the command tells an agent to write must satisfy the checker that would reject
    # it otherwise. Checked as a CONTRACT (the ten headings) rather than by running the checker on
    # the command, because the template's placeholders are deliberate. If the paths stop resolving
    # that is a FAILURE and not a skip.
    _tick()
    brief_cmd = PLUGIN_ROOT / "commands" / "brief.md"
    if not brief_cmd.is_file():
        FAILURES.append(f"{brief_cmd} is missing -- the checker has no command that produces it")
    else:
        template = brief_cmd.read_text(encoding="utf-8").lower()
        for label, aliases, _ in cb.REQUIRED_SECTIONS:
            if not any(f"## {alias}" in template for alias in aliases):
                FAILURES.append(
                    f"{brief_cmd} never shows a `## {label}` heading, but check_brief.py requires "
                    "one -- the template and the checker disagree, and the template is what an "
                    "agent copies"
                )
        _tick()
        for state in cb.STATES:
            if state not in template:
                FAILURES.append(
                    f"{brief_cmd} never names the `{state}` coverage state, which check_brief.py "
                    "accepts -- an author cannot use a vocabulary the command does not show them"
                )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_brief selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
