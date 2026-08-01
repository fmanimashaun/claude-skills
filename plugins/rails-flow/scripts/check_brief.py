#!/usr/bin/env python3
"""Reject a product brief that duplicates its own sources, or that hides a gap instead of recording it.

Run:  python3 check_brief.py docs/brain/BRIEF.md
      python3 check_brief.py docs/brain/BRIEF.md --decisions docs/brain/DECISIONS.md
      python3 check_brief.py docs/brain/BRIEF.md --root .
      python3 check_brief.py --selftest

WHY (rails-flow #130). `/rails-flow:brief` runs the intake that turns "we need a site for X" into
something buildable, and writes `docs/brain/BRIEF.md`. The command makes four promises a reader
cannot check by reading the file, and each fails in a way that looks fine:

  1. **"The brief never duplicates an existing PRD; it links into it."** A brief that pasted the
     PRD's requirements reads *better* than one that cites them -- it is self-contained and
     complete. It is also a second source of truth that will disagree with the PRD within a week,
     with no rule saying which wins. That is the doc-drift this toolchain exists to prevent, and
     the copy is invisible unless something compares the two documents.
  2. **"It links into the source."** A link is only a link while it resolves. `check_handoff.py`
     already learned this on `AC-n` ids: *an id that resolves to nothing is worse than no citation,
     because it reads as traceable.* A brief pointing at `docs/prd.md § "Pricing"` when the PRD has
     no such heading has re-invented duplication with extra steps.
  3. **"It emits a coverage map, so the human can see why each question is being asked."** A map
     that omits a section is not a map of that section's absence -- it is silence, and silence
     reads as covered.
  4. **"Open questions are recorded rather than forced."** An open question with no owner is not
     recorded, it is deferred; and a brief with gaps and no open questions has dropped them.

All four are the `claims-vs-enforcement` class from the bundled `code-review` skill: a guarantee
stated in prose with nothing making it true. So they become a check.

THE REFERENCE SYNTAX, AND WHY IT IS NOT THE ONE THE ISSUE ASKED FOR
    #130 specified `PRD S7.2`-style references, "matching the citation convention already used in
    `docs/brain/`". There is no such convention -- `grep -rn "PRD S"` over this repo returns
    nothing, and what `docs/brain/` actually carries is `D-nnn` decision ids and the four
    provenance tags. `PRD S7.2` also names no file and no checkable target, so it could never
    resolve. The syntax here is therefore ours, decided on the issue:

        `docs/prd.md` § "Pricing tiers"

    a real path plus a string that literally occurs in that file. It works unchanged for CODE --
    `app/models/booking.rb` § "class Booking" -- which is what lets ONE mechanism serve Mode A
    (documents) and Mode B (an existing codebase) instead of two.

THE FOURTH COVERAGE STATE
    #130 gives three: answered-with-source / thin / missing. Greenfield intake has no document to
    cite, so every Mode C row would have had to lie in the `answered` cell. A fourth state,
    `decided`, cites a `D-nnn` -- which must exist in `docs/brain/DECISIONS.md`. That is what makes
    the issue's "decisions taken during the interview are written to DECISIONS.md" a checkable
    claim rather than a hope, and it reuses the `[decided]` provenance tag the brain already
    defines rather than inventing a fifth vocabulary.

WHAT THIS GUARANTEES
    The brief carries all ten sections; declares one of the three intake modes; maps every content
    section to a state; backs every `answered` row with a source reference that opens and contains
    its locator, and every `decided` row with a `D-nnn` that exists; reproduces no long contiguous
    run of a cited source outside a quotation; states non-goals that are neither empty nor hedged;
    gives every open question an owner; records a gap somewhere when the map has one; and points at
    no conversation, no `<placeholder>` and no undecided `TBD` outside the section for undecided
    things.

WHAT IT DOES NOT
    It cannot tell whether the intake asked good questions, whether one was asked at a time, or
    whether each carried a recommendation -- those are runtime behaviour that leaves no trace in the
    artifact, so the command states them as prose and labels them as prose (harness-doctrine section
    1). It cannot tell whether the brief STOPPED at the right point: "decidable" is the judgement
    the human owns. It does not grade success criteria for falsifiability -- that is
    `check_criteria.py`'s job on `docs/acceptance/<slug>.md`, and enforcing the same property twice
    at two fidelities is the second-source-of-truth failure this file exists to prevent. The
    provenance rule proves a Mode B brief distinguishes inference from fact AT ALL; it cannot
    prove every inference is tagged. And a resolving reference is not a RELEVANT one: the locator
    exists in the file, which is not the same as the section answering the question.

Exit codes:  0 clean · 1 findings · 2 unusable input (no file / not a brief / unusable --root)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SECTION_RE = re.compile(r"^\s{0,3}##\s+(?P<text>.*\S)\s*$")
FENCE_RE = re.compile(r"^\s*(?P<ticks>`{3,})")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>\S.*)$")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
D_ID_RE = re.compile(r"\bD-(\d+)\b")
WORD_RE = re.compile(r"[a-z0-9']+")

# Straight and curly quotes both, because an editor that autocorrects quotes must not silently
# unhook every citation in the file.
_Q = "\"'“”‘’"
SOURCE_REF_RE = re.compile(
    rf"`?(?P<path>[\w.@+-]+(?:/[\w.@+-]+)*\.\w+)`?\s*§\s*[{_Q}](?P<locator>[^{_Q}\n]{{2,160}})[{_Q}]"
)

# The ten sections. Each is one of #130's stated brief contents, or one of its acceptance criteria
# that has nowhere else to live. Aliases are generous because a human edits this file after the
# command writes it -- but the SET is fixed.
#
# The third element is a DISQUALIFIER list, and it is load-bearing: `scope` word-matches inside
# "Non-goals (out of scope)", so without it a brief with that heading and no `## Scope` reports
# clean while the scope section is missing. check_handoff.py hit the same class from the other
# direction ("Interface" collecting the in-scope list) and solved it by ordering, which does not
# generalise to headings a human may write in either order.
REQUIRED_SECTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("coverage map", ("coverage map", "coverage", "intake coverage"), ()),
    ("what and for whom", ("what and for whom", "what we are building", "what we're building",
                           "what and who", "product"), ()),
    ("problem", ("problem", "the problem"), ()),
    ("scope", ("scope", "in scope"), ("non-goal", "non goal", "nongoal")),
    ("non-goals", ("non-goals", "non goals", "nongoals", "not building", "explicitly out"), ()),
    ("constraints", ("constraints", "constraint"), ()),
    ("journeys", ("journeys", "journey", "user journeys"), ()),
    ("success", ("success", "what success looks like", "outcomes"), ()),
    ("open questions", ("open questions", "open question", "unknowns"), ()),
    ("decisions", ("decisions", "decisions taken", "decisions recorded"), ()),
)

# The seven the coverage map must classify. The map itself is not mapped (it is the map), and
# `open questions` / `decisions` are OUTPUTS of intake rather than things a source can answer.
MAPPED_SECTIONS = ("what and for whom", "problem", "scope", "non-goals", "constraints",
                   "journeys", "success")

MODES: dict[str, str] = {"a": "documents", "b": "codebase", "c": "greenfield"}
MODE_LETTER_RE = re.compile(r"\bmode\s*[:=]\s*\**\s*([abc])\b", re.I)
MODE_WORD_RE = re.compile(r"\b(documents?|codebase|greenfield)\b", re.I)

STATES = ("answered", "decided", "thin", "missing")

# A non-goal that says nothing. #130 calls non-goals "as load-bearing as goals" -- they are what
# stops scope creep mid-build -- so an empty list with a heading over it is the failure, not the
# absence of the heading.
HEDGES = frozenset({
    "none", "none yet", "nothing", "nothing yet", "n/a", "na", "tbd", "todo", "unknown",
    "to be decided", "to be determined", "not decided", "-", "--", "—", "–", "?",
})
# ...but Open questions is allowed to be empty, because "there are none" is a real answer there
# and forcing an invented question is worse than recording zero.
NONE_ONLY_RE = re.compile(r"^\s*(?:[-*+]\s*)?[_*]*\s*none[._*)\s]*$", re.I)

OWNER_RE = re.compile(r"\bowner\s*[:=]\s*\S", re.I)

# The brain's provenance vocabulary (setup-flow.md section 4), plus `[inferred]` for the case that
# vocabulary has no tag for: a fact the agent read out of the codebase rather than being told.
PROVENANCE_RE = re.compile(r"\[(observed|decided|assumed|reported|inferred)\]", re.I)

# Words of contiguous source text reproduced in the brief before it stops being a coincidence.
# 12 rather than 8: a brief and its PRD describe the same product, so short runs of shared
# vocabulary are expected and flagging them would teach authors to paraphrase the product's own
# nouns. 12 consecutive identical words is a copy.
DUP_WINDOW = 12


class Unusable(Exception):
    """The input cannot be checked -- never report clean for it."""


def _heading_says(title: str, aliases: tuple[str, ...],
                  disqualifiers: tuple[str, ...] = ()) -> bool:
    """Alias match on whole words, unless the heading is disqualified.

    `\\b` matters for the same reason it does in check_handoff.py: without it `in` matches inside
    "Invariants". The disqualifier list matters because a heading can honestly contain two section
    names ("Non-goals (out of scope)") and only one of them is what it IS.

    The disqualifier match carries an optional plural, and it is not cosmetic: `\\bnon-goal\\b`
    does NOT match "Non-goals" -- the `\\b` fails against the trailing `s` -- so the first version
    of this disqualified nothing, "Non-goals (out of scope)" was collected as the scope section,
    and a brief with no scope section at all reported clean. Found by the fixture, not by reading.
    """
    low = title.lower()
    if any(re.search(rf"\b{re.escape(d)}s?\b", low) for d in disqualifiers):
        return False
    return any(re.search(rf"\b{re.escape(a)}\b", low) for a in aliases)


def _strip_code(line: str) -> str:
    """Blank out inline code so a prose rule never reads a path or a tag as prose."""
    return INLINE_CODE_RE.sub("``", line)


def _tokens(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Section:
    title: str
    start: int
    lines: list[str] = field(default_factory=list)
    # Parallel to `lines`. A fenced line is code; a quoted line is attributed borrowing. Both are
    # exempt from the prose rules, and each exemption has a near-miss fixture.
    fenced: list[bool] = field(default_factory=list)
    first_body_line: int = 0

    def matches(self, aliases: tuple[str, ...], disqualifiers: tuple[str, ...] = ()) -> bool:
        return _heading_says(self.title, aliases, disqualifiers)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def bullets(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for offset, line in enumerate(self.lines):
            if offset < len(self.fenced) and self.fenced[offset]:
                continue
            bullet = BULLET_RE.match(line)
            if bullet:
                out.append((self.first_body_line + offset, bullet.group("text")))
        return out


@dataclass(frozen=True)
class CoverageRow:
    section: str
    state: str
    source: str
    line: int


def parse(path: Path) -> list[Section]:
    """Split a brief into its `##` sections, or refuse to bless the file."""
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    sections: list[Section] = []
    current: Section | None = None
    in_fence = False
    ticks = ""
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if fence:
            if not in_fence:
                in_fence, ticks = True, fence.group("ticks")
            elif fence.group("ticks").startswith(ticks):
                in_fence, ticks = False, ""
            if current is not None:
                current.lines.append(line)
                current.fenced.append(True)
            continue
        heading = SECTION_RE.match(line) if not in_fence else None
        if heading:
            current = Section(title=heading.group("text"), start=line_no,
                              first_body_line=line_no + 1)
            sections.append(current)
            continue
        if current is not None:
            current.lines.append(line)
            current.fenced.append(in_fence)

    if not sections:
        raise Unusable(
            f"{path} carries no `## ` sections -- refusing to report a file clean as a brief when "
            "none of its ten required sections can even be located"
        )
    if not any(s.matches(a, d) for s in sections for _, a, d in REQUIRED_SECTIONS):
        raise Unusable(
            f"{path} has `## ` sections but not one of the ten a brief requires "
            f"({', '.join(label for label, _, _ in REQUIRED_SECTIONS)}) -- this is not a brief"
        )
    return sections


# ------------------------------------------------------------------------------------------------
# The coverage map: which sections the sources already answer, and which the interview had to.
# ------------------------------------------------------------------------------------------------

def parse_coverage(section: Section) -> list[CoverageRow]:
    rows: list[CoverageRow] = []
    for offset, line in enumerate(section.lines):
        if offset < len(section.fenced) and section.fenced[offset]:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        name = cells[0].strip("`* ")
        if not name or set(name) <= {"-", ":", " "} or name.lower() in ("brief section", "section"):
            continue
        rows.append(CoverageRow(section=name, state=cells[1].strip("`* ").lower(),
                                source=cells[2], line=section.first_body_line + offset))
    return rows


def _check_mode(section: Section, findings: list[str]) -> str | None:
    """The declared intake mode, or None. Returned so downstream rules can be mode-aware.

    The letter/word cross-check reads only the DECLARATION LINE. Scanning the whole section was the
    first version and it could not fire: a Mode-A coverage map says "read the documents first" in
    its own prose, so the expected word was always present somewhere no matter what the declaration
    said. Worse, the mirror of that is a false positive -- a Mode B brief legitimately writes "no
    documents exist". A contradiction is `Mode: A — greenfield` on one line; a later sentence is
    not.
    """
    body = _strip_code(section.text)
    letters = {m.group(1).lower() for m in MODE_LETTER_RE.finditer(body)}
    if not letters:
        findings.append(
            f"coverage map (line {section.start}): declares no intake mode -- say "
            "`Mode: A` (documents), `Mode: B` (codebase) or `Mode: C` (greenfield). The mode is "
            "what says whether an unanswered section means nobody wrote it down or nobody has "
            "decided it, and those need different conversations."
        )
        return None
    if len(letters) > 1:
        findings.append(
            f"coverage map (line {section.start}): declares {len(letters)} modes "
            f"({', '.join(sorted(letters))}) -- one intake, one mode."
        )
        return None
    mode = next(iter(letters))
    expected = MODES[mode].rstrip("s")
    for line in body.splitlines():
        found = MODE_LETTER_RE.search(line)
        if not found:
            continue
        # Only the DECLARATION CLAUSE -- from the letter to the end of that sentence. Scoping to
        # the whole line was still too wide: the template writes the declaration and its prose as
        # one line ("**Mode: A — documents.** Intake read the documents first"), so the expected
        # word was always present and the rule could not fire. Both failures were the same
        # mistake at two widths, and the fixture caught it twice.
        clause = re.split(r"[.|]", line[found.end():], maxsplit=1)[0][:60]
        words = {m.group(1).lower().rstrip("s") for m in MODE_WORD_RE.finditer(clause)}
        if words and expected not in words:
            findings.append(
                f"coverage map (line {section.start}): declares `Mode: {mode.upper()}` "
                f"({MODES[mode]}) but calls it {', '.join(sorted(words))} on the same line -- the "
                "letter and the word disagree, so a reader cannot tell which intake actually ran."
            )
            break
    return mode


def check_coverage(section: Section, mode: str | None, findings: list[str]) -> list[CoverageRow]:
    rows = parse_coverage(section)
    if not rows:
        findings.append(
            f"coverage map (line {section.start}): holds no rows -- the map is what lets the human "
            "point at a document instead of answering, and an empty one reports every section "
            "covered while checking nothing."
        )
        return rows

    for label in MAPPED_SECTIONS:
        aliases = next(a for name, a, _ in REQUIRED_SECTIONS if name == label)
        disqualifiers = next(d for name, _, d in REQUIRED_SECTIONS if name == label)
        if not any(_heading_says(row.section, aliases, disqualifiers) for row in rows):
            findings.append(
                f"coverage map (line {section.start}): no row for `{label}` -- an omitted row is "
                "not a record of that section's absence, it is silence, and silence reads as "
                "covered."
            )

    for row in rows:
        if row.state not in STATES:
            findings.append(
                f"coverage map line {row.line}: `{row.section}` has state {row.state!r}, not one "
                f"of {', '.join(STATES)} -- a state nobody defined cannot be acted on."
            )
            continue
        if row.state == "answered" and not SOURCE_REF_RE.search(row.source):
            findings.append(
                f"coverage map line {row.line}: `{row.section}` is `answered` but cites no source "
                "-- answered by WHAT? Cite it as `path` § \"locator\", or mark the row "
                "`decided` and record the decision as a `D-nnn`."
            )
        if row.state == "decided" and not D_ID_RE.search(row.source):
            findings.append(
                f"coverage map line {row.line}: `{row.section}` is `decided` but cites no `D-nnn` "
                "-- a decision taken during intake and not written to DECISIONS.md is rationale "
                "that has to be reconstructed later, which is the failure this brief exists to "
                "prevent."
            )

    if mode == "a" and not any(r.state == "answered" for r in rows):
        findings.append(
            f"coverage map (line {section.start}): `Mode: A` (documents) but not one row is "
            "`answered` from a source -- if the documents answer nothing, this was not document "
            "intake, and the mode is what stops the interview re-asking what the PRD already says."
        )
    return rows


def _check_gap_recorded(rows: list[CoverageRow], open_questions: Section | None,
                        findings: list[str]) -> None:
    gaps = [r for r in rows if r.state in ("thin", "missing")]
    if not gaps or open_questions is None:
        return
    if open_questions.bullets():
        return
    findings.append(
        f"open questions (line {open_questions.start}): {len(gaps)} coverage row(s) are "
        f"thin or missing ({', '.join(sorted({r.section for r in gaps}))}) and not one open "
        "question is recorded -- a gap the brief neither resolved nor recorded is a gap the build "
        "will silently guess at."
    )


# ------------------------------------------------------------------------------------------------
# Source references: the whole anti-duplication design rests on these resolving.
# ------------------------------------------------------------------------------------------------

def _read_source(root: Path, ref_path: str) -> str | None:
    candidate = (root / ref_path).resolve()
    if not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def check_sources(sections: list[Section], root: Path,
                  findings: list[str]) -> dict[str, str]:
    """Every `path § "locator"` opens and contains its locator. Returns the sources that resolved."""
    resolved: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for section in sections:
        for offset, raw in enumerate(section.lines):
            if offset < len(section.fenced) and section.fenced[offset]:
                continue
            line_no = section.first_body_line + offset
            for match in SOURCE_REF_RE.finditer(raw):
                ref_path, locator = match.group("path"), match.group("locator")
                if (ref_path, locator) in seen:
                    continue
                seen.add((ref_path, locator))
                body = resolved.get(ref_path)
                if body is None:
                    body = _read_source(root, ref_path)
                    if body is None:
                        findings.append(
                            f"line {line_no}: cites `{ref_path}`, which does not exist under "
                            f"{root} -- a reference that resolves to nothing is worse than no "
                            "reference, because it reads as traceable and the brief looks thin "
                            "for the right reason."
                        )
                        continue
                    resolved[ref_path] = body
                if _collapse(locator) not in _collapse(body):
                    findings.append(
                        f"line {line_no}: `{ref_path}` does not contain {locator!r} -- the file "
                        "resolves but the locator does not, so the row points at a document and "
                        "not at the part of it that answers the question."
                    )
    return resolved


def _dup_blocks(sections: list[Section]) -> list[tuple[int, str]]:
    """Contiguous runs of eligible prose, as (first line number, text).

    Three kinds of line are EXEMPT, and each exemption is a claim about what duplication means.
    Each has a near-miss fixture and a declared mutation, because a carve-out nothing tests is how
    a similarity rule quietly stops finding anything:
      * fenced code -- a quoted config block is meant to be identical.
      * a blockquote -- #130 asks for "the problem in the user's words". Attributed quotation is
        the opposite of silent duplication; flagging it would delete the one place the brief is
        supposed to borrow.
      * a table row -- the coverage map's Source cell quotes the source's own heading BY DESIGN.
        The citation mechanism would flag itself.

    A heading is not an exemption but a BOUNDARY, exactly like a blank line: it ends the block. That
    matters in the firing direction rather than the silent one -- without it, prose either side of a
    subheading is concatenated and two short runs bridge into one long false match.
    """
    blocks: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for section in sections:
        for offset, raw in enumerate(section.lines):
            fenced = offset < len(section.fenced) and section.fenced[offset]
            stripped = raw.strip()
            eligible = (
                not fenced and bool(stripped)
                and not stripped.startswith(">")
                and not stripped.startswith("|")
                and not HEADING_RE.match(raw)
            )
            if eligible:
                if not buffer:
                    start = section.first_body_line + offset
                buffer.append(stripped)
            elif buffer:
                blocks.append((start, " ".join(buffer)))
                buffer = []
        if buffer:
            blocks.append((start, " ".join(buffer)))
            buffer = []
    return blocks


def check_duplication(sections: list[Section], sources: dict[str, str],
                      findings: list[str]) -> None:
    """No long contiguous run of a cited source reproduced in the brief.

    #130's own heading: "BRIEF.md must not become a second source of truth". A brief that pasted
    the PRD reads BETTER than one that cites it -- complete, self-contained, no indirection -- and
    is exactly the doc-drift the toolchain exists to prevent. Nothing but a comparison can see it.
    """
    if not sources:
        return
    shingles: dict[tuple[str, ...], str] = {}
    for name, body in sources.items():
        words = _tokens(body)
        for i in range(len(words) - DUP_WINDOW + 1):
            shingles.setdefault(tuple(words[i:i + DUP_WINDOW]), name)

    for line_no, block in _dup_blocks(sections):
        words = _tokens(block)
        index = 0
        while index <= len(words) - DUP_WINDOW:
            window = tuple(words[index:index + DUP_WINDOW])
            owner = shingles.get(window)
            if owner is None:
                index += 1
                continue
            run = list(window)
            cursor = index + DUP_WINDOW
            while cursor < len(words) and tuple(
                    words[cursor - DUP_WINDOW + 1:cursor + 1]) in shingles:
                run.append(words[cursor])
                cursor += 1
            findings.append(
                f"line {line_no}: reproduces {len(run)} consecutive words of `{owner}` "
                f"(\"{' '.join(run[:10])}...\") -- the brief is an index over the source, not a "
                "copy of it. Two documents saying the same thing will disagree within a week and "
                "nothing says which wins. Cite it as `" + owner + "` § \"...\" instead, or "
                "quote it as a blockquote if the wording itself is the point."
            )
            index = cursor
            break   # one finding per block: a copied paragraph is one defect, not forty.


# ------------------------------------------------------------------------------------------------
# The remaining section rules.
# ------------------------------------------------------------------------------------------------

def check_non_goals(section: Section, findings: list[str]) -> None:
    bullets = section.bullets()
    real = [text for _, text in bullets
            if _collapse(_strip_code(text)).strip(".") not in HEDGES and len(_tokens(text)) >= 3]
    if not real:
        findings.append(
            f"non-goals (line {section.start}): lists no real non-goal -- \"none\" is scope creep "
            "with a heading over it. Non-goals are as load-bearing as goals: they are the thing "
            "that stops \"add a booking form\" becoming a CRM mid-build. Name what this is NOT."
        )


def check_open_questions(section: Section, findings: list[str]) -> None:
    body = "\n".join(line for line in section.lines if line.strip())
    if body and all(NONE_ONLY_RE.match(line) for line in body.splitlines()):
        return   # "there are none" is a real answer; forcing an invented question is worse.
    for line_no, text in section.bullets():
        if not OWNER_RE.search(_strip_code(text)):
            findings.append(
                f"open questions line {line_no}: names no owner ({text[:60]!r}) -- an open "
                "question with nobody against it is not recorded, it is deferred, and it will be "
                "answered by whoever hits it first at build time. Add `owner: <who>`."
            )


def check_decisions(sections: list[Section], decisions: Path | None,
                    findings: list[str]) -> None:
    cited = sorted({int(n) for s in sections for n in D_ID_RE.findall(_strip_code(s.text))})
    if decisions is None:
        return
    if not decisions.is_file():
        if cited:
            findings.append(
                f"decisions: the brief cites {len(cited)} `D-nnn` id(s) but {decisions} does not "
                "exist -- the rationale they point at was never written down, so it has to be "
                "reconstructed later from memory. That is the failure intake exists to prevent."
            )
        return
    defined = {int(n) for n in D_ID_RE.findall(decisions.read_text(encoding="utf-8"))}
    for num in cited:
        if num not in defined:
            findings.append(
                f"decisions: cites D-{num:03d}, which {decisions} does not define -- an id that "
                "resolves to nothing reads as traceable while carrying no rationale at all."
            )


def _self_containment_rules():  # -> module | None
    """`check_handoff`, or None when it is not beside this script.

    Imported rather than copied: "what counts as a reference to the conversation" is one decision,
    and two copies of it will diverge -- the second-source-of-truth failure this whole file is
    about, committed in the checker that polices it. A seam, not indirection: the caller turns
    None into a FINDING rather than a silent skip.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import check_handoff  # noqa: PLC0415 -- used by the self-containment rules only
    except ImportError:
        return None
    return check_handoff


def check_self_contained(sections: list[Section], open_questions: Section | None,
                         findings: list[str]) -> None:
    rules = _self_containment_rules()
    if rules is None:
        findings.append(
            "self-containment: check_handoff.py is not beside this script, so the "
            "conversation-reference, placeholder and unresolved-token rules could not run. They "
            "are UNVERIFIED, not satisfied."
        )
        return
    for section in sections:
        for offset, raw in enumerate(section.lines):
            if offset < len(section.fenced) and section.fenced[offset]:
                continue
            line = _strip_code(raw)
            line_no = section.first_body_line + offset
            for pattern in rules.CHAT_REFS:
                hit = pattern.search(line)
                if hit:
                    findings.append(
                        f"line {line_no}: points at the conversation ({hit.group(0)!r}) -- the "
                        "brief exists because the intake conversation does not survive a fresh "
                        "session, a resume, or the second engagement. Write what it referred to."
                    )
                    break
            placeholder = rules.PLACEHOLDER_RE.search(line)
            if placeholder:
                findings.append(
                    f"line {line_no}: unresolved placeholder {placeholder.group(0)!r} -- a brief "
                    "shipped with its template still in it plans the wrong product confidently."
                )
            # `TBD` inside Open questions is the SECTION'S JOB: a recorded unknown with an owner.
            # Anywhere else it is an unrecorded one, and the difference is the whole point.
            if section is open_questions:
                continue
            unresolved = rules.UNRESOLVED_RE.search(line)
            if unresolved:
                findings.append(
                    f"line {line_no}: {unresolved.group(0)} outside `## Open questions` -- an "
                    "undecided thing recorded nowhere has no owner and no prompt to revisit it. "
                    "Move it to the open questions, with who answers it."
                )


def check_provenance(sections: list[Section], mode: str | None, findings: list[str]) -> None:
    """Mode B states what it INFERRED, so the human can correct it.

    #130: "Reads an existing codebase and never asks what it can infer; states what it inferred so
    it can be corrected." The first half is runtime behaviour with no trace. The second half is
    checkable, and it is the half that matters: an inference presented as a fact reads exactly like
    something the client said, and nobody knows to correct it.
    """
    if mode != "b":
        return
    if any(PROVENANCE_RE.search(section.text) for section in sections):
        return
    findings.append(
        "provenance: `Mode: B` (codebase) but the brief carries no `[inferred]`/`[assumed]` tag -- "
        "everything in it therefore reads as something the client told you. Tag what you read out "
        "of the code, using the brain's provenance vocabulary, so it can be corrected."
    )


def check(sections: list[Section], root: Path, decisions: Path | None = None) -> list[str]:
    findings: list[str] = []
    found: dict[str, Section] = {}
    for label, aliases, disqualifiers in REQUIRED_SECTIONS:
        for section in sections:
            if section.matches(aliases, disqualifiers):
                found[label] = section
                break
        else:
            findings.append(
                f"no `## {label}` section -- a brief missing it hands the build a question it will "
                "answer by guessing, and the guess is invisible until it ships."
            )

    mode: str | None = None
    rows: list[CoverageRow] = []
    if "coverage map" in found:
        mode = _check_mode(found["coverage map"], findings)
        rows = check_coverage(found["coverage map"], mode, findings)
    _check_gap_recorded(rows, found.get("open questions"), findings)
    if "non-goals" in found:
        check_non_goals(found["non-goals"], findings)
    if "open questions" in found:
        check_open_questions(found["open questions"], findings)
    check_decisions(sections, decisions, findings)
    sources = check_sources(sections, root, findings)
    check_duplication(sections, sources, findings)
    check_self_contained(sections, found.get("open questions"), findings)
    check_provenance(sections, mode, findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a rails-flow product brief (docs/brain/BRIEF.md)."
    )
    parser.add_argument("brief_path", nargs="?", help="docs/brain/BRIEF.md")
    parser.add_argument(
        "--root", metavar="DIR", default=".",
        help="the project root that source references resolve against (default: .)",
    )
    parser.add_argument(
        "--decisions", metavar="FILE",
        help="docs/brain/DECISIONS.md; every cited D-nnn must exist there",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the rules fire AND stay silent"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_brief_selftest as st

        return st.run()

    if not args.brief_path:
        parser.error("give a brief path, or --selftest")

    root = Path(args.root)
    if not root.is_dir():
        print(f"UNUSABLE: --root {root} is not a directory, so no source reference can resolve "
              "and every citation would be reported dangling", file=sys.stderr)
        return 2

    try:
        sections = parse(Path(args.brief_path))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    findings = check(sections, root, Path(args.decisions) if args.decisions else None)
    if findings:
        print(f"{len(findings)} brief finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nFix the brief, do not soften the check. An under-specified brief does not fail "
            "loudly: it produces a confidently built product nobody asked for.",
            file=sys.stderr,
        )
        return 1

    print(f"validated: {len(sections)} sections in {args.brief_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
