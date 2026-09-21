#!/usr/bin/env python3
"""Every catalogue row declares the seven states, or declares which do not apply (#1068).

Run:  python3 scripts/check_component_states.py
      python3 scripts/check_component_states.py --selftest

WHY THIS EXISTS. `components.md` opens by stating a rule about itself: *"Every entry covers the
states, or says which do not apply (#978): default, hover, focused, loading, disabled, and error or
empty. An entry that specifies four is where drift enters -- the loading and empty states are the
ones always missing."*

**The file's prediction about itself was correct, and nothing enforced it.** Measured on `dev` when
this was written: `loading` appeared as a state of the component being described in **1 of 44
rows**, and the escape hatch -- "says which do not apply" -- was used **zero times**. Five rows
named none of the six. `Table (CRUD)`, the central admin row, had no empty state while its sibling
`Stacked list` sent the zero-row case to `Empty state`.

WHY IT IS NOT A WORD COUNT, which is the obvious implementation and a worthless one. Getting
`loading` down to a true 1 of 44 took a human separating *a state of the component described* from
*a row that **is** a loading indicator* (`Skeleton`, `Spinner`, `Background operation`), from a
Toast `:loading` variant, and from `Activity feed`'s "no scroll-loading". A grep for the six words
scores every one of those as compliant. So would a row saying **"see Skeleton for loading"**, which
passes a word count and tells a consumer nothing.

So the row makes a CLAIM, in a form a script can read, and this reads the claim and never the prose
around it. There is no English to parse and no sentence that can accidentally satisfy it.

TWO VERDICTS, because one alone fails differently from how it looks.

  1. **Every declaration that exists must be COMPLETE** -- all six slots named, and an `n/a` must
     carry a reason. This is a hard failure and it fires on a malformed row the day it is written.
  2. **The number of rows carrying a declaration is RATCHETED** -- it may not drop, and growth must
     be recorded. A fixed "44 of 44" would be red on day one and stay red until the last row lands,
     which teaches everyone to ignore a red build; a fixed "1 of 44" is inert. The floor moves up
     one PR at a time and never back.

An `n/a` WITHOUT A REASON IS REFUSED, and that is the load-bearing half of rule 1. A bare `n/a` is
the escape hatch becoming a loophole -- and the measurement above says nobody reaches for the hatch
even when it costs nothing, so the first thing that would happen to a free one is 43 rows of it. A
reason is the part a reviewer can disagree with.

WHAT IT DELIBERATELY DOES NOT ASSERT. That the declaration is TRUE -- that a row claiming a hover
state really describes one. That is not decidable from the text, and a check claiming it would be a
gate that cannot fail. This asserts that a decision was made and written down, which is exactly what
the rule in the file asks for and exactly what was missing.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CATALOGUE = REPO / "skills/design-system/references/components.md"

# SEVEN SLOTS, AND #978 NAMED SIX. `error or empty` was one slot until #1068's follow-up, and
# splitting it is a widening of the rule rather than a tidy-up: they are not two spellings of one
# state, they are two different absences with two different remedies.
#
#   empty   the query returned nothing, and here is what the person does next
#   error   the request failed, and here is how they retry
#
# As one slot a row satisfied it by covering whichever was easier, and the parser could not see the
# hole. `Table (CRUD)` is the case that made it concrete: it is missing EMPTY specifically, on the
# central admin row, while its sibling `Stacked list` sends the zero-row case to `Empty state`.
SLOTS = ("default", "hover", "focused", "loading", "disabled", "error", "empty")

# `error or empty` is a single slot naming two different concerns -- a form field's error and a
# table's zero-row state are not the same thing, and a row can satisfy the slot by covering
# whichever is easier. Accepting either spelling is what the file's own wording requires today;
# splitting the slot is a doctrine change and needs a maintainer decision, not a quiet fix here.
# ACCEPT THE FILE'S OWN VOCABULARY rather than making 44 rows adopt this script's. The catalogue
# has written `focus-visible` since it was created -- it is the Tailwind variant the recipes use and
# the thing a reader searches for -- so demanding the word "focused" would be a checker renaming
# doctrine to suit its parser.
SLOT_ALIASES = {
    "focused": ("focused", "focus-visible", "focus"),
    # A row that genuinely has one state for both still says so once per slot -- `error/empty`
    # satisfies neither on its own, deliberately. Accepting the old combined spelling would let
    # every row written before the split keep passing while covering one of the two.
}

# A section that is doctrine rather than a component says so, in the file, next to itself. The
# alternative is a list of exceptions in this script -- a second list nobody compares against the
# first, which is the defect `Listing.sortable` and this whole file exist to refuse.
NOT_A_COMPONENT = "<!-- states: not-a-component -->"

MARKER = "**States:**"

# THE RATCHET. Rows carrying a complete declaration, as measured on the tree this floor was
# committed with. Raise it in the same PR that converts a row; it never goes down.
DECLARED_FLOOR = 1

# `n/a` and the reason that must follow it. An em dash, an en dash or a plain hyphen, because the
# file uses all three and refusing a punctuation choice is not what this is for.
NA = re.compile(r"\bn/a\b\s*(?:[—–-]\s*(?P<reason>[^·]+))?", re.I)


class Row:
    """One `## ` section of the catalogue."""

    def __init__(self, name: str, line: int, body: str) -> None:
        self.name, self.line, self.body = name, line, body

    @property
    def exempt(self) -> bool:
        return NOT_A_COMPONENT in self.body

    @property
    def declaration(self) -> str | None:
        """The text of the `**States:**` claim, or None.

        It runs to the end of the bullet that contains it, NOT to the end of the line: the one row
        that already had a `States:` line wrapped it across two, and a line-based reader would have
        silently dropped `loading` -- scoring the single compliant row in the file as incomplete.
        """
        if MARKER not in self.body:
            return None
        tail = self.body.split(MARKER, 1)[1]
        out = []
        for i, raw in enumerate(tail.splitlines()):
            # A new top-level bullet, a heading or a fence ends the claim. A continuation line is
            # indented; the first line is the remainder of the marker's own line.
            if i and (raw.startswith(("- ", "#", "```")) or not raw.strip()):
                break
            out.append(raw.strip())
        return " ".join(out).strip()


def parse(text: str) -> list[Row]:
    rows, name, line, buf = [], None, 0, []
    for n, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("## "):
            if name is not None:
                rows.append(Row(name, line, "\n".join(buf)))
            name, line, buf = raw[3:].strip(), n, []
        elif name is not None:
            buf.append(raw)
    if name is not None:
        rows.append(Row(name, line, "\n".join(buf)))
    return rows


# THE PRE-SPLIT SPELLING, REFUSED BY NAME. `error/empty` reads as one treatment for both, which is
# exactly the ambiguity #1068's follow-up removes -- and it would otherwise slip through, because a
# `/` is a word boundary, so a regex looking for each slot matches BOTH inside the single token. A
# row claiming the same handling for a failed request and a zero-row result is making the claim the
# split exists to stop; it says so twice or it says so once and is wrong.
COMBINED = re.compile(r"\berror\s*(?:/|\bor\b)\s*empty\b", re.I)


def slot_findings(row: Row) -> list[str]:
    """What is wrong with this row's declaration. Empty means complete."""
    claim = row.declaration
    if claim is None:
        return []  # not declared at all -- the ratchet's business, not this one's
    out = []
    if COMBINED.search(claim):
        out.append("uses the pre-split 'error or empty' spelling -- name 'error' and 'empty' "
                   "separately, each covered or n/a with a reason")
    for slot in SLOTS:
        spellings = SLOT_ALIASES.get(slot, (slot,))
        hit = next((s for s in spellings if re.search(rf"\b{re.escape(s)}\b", claim, re.I)), None)
        if hit is None:
            out.append(f"does not name {slot!r}")
            continue
        # Everything from this slot's name up to the next slot's name, or the end.
        start = re.search(rf"\b{re.escape(hit)}\b", claim, re.I).end()
        rest = claim[start:]
        nxt = [m.start() for s2 in SLOTS for sp in SLOT_ALIASES.get(s2, (s2,))
               if s2 != slot and (m := re.search(rf"\b{re.escape(sp)}\b", rest, re.I))]
        segment = rest[: min(nxt)] if nxt else rest
        na = NA.search(segment)
        if na and not (na.group("reason") or "").strip():
            out.append(f"{slot!r} is 'n/a' with no reason")
        elif not na and not segment.strip(" ·.,;:-—–"):
            out.append(f"{slot!r} is named with nothing after it")
    return out


def check(path: Path, floor: int) -> tuple[int, list[str]]:
    rows = parse(path.read_text(encoding="utf-8"))
    findings, declared = [], 0

    for row in rows:
        if row.exempt:
            # Spelled with the marker rather than `row.declaration is not None` so the two
            # conditions in this function are distinguishable: an identical expression twice means
            # a mutation aimed at one lands on the other and is 'caught' by the wrong fixture,
            # which reads as a pass while the intended fixture goes quiet.
            if MARKER in row.body:
                findings.append(f"{path.name}:{row.line} {row.name!r} is marked "
                                f"not-a-component AND declares states -- it is one or the other")
            continue
        bad = slot_findings(row)
        if row.declaration is not None:
            declared += 1
            for b in bad:
                findings.append(f"{path.name}:{row.line} {row.name!r} {b}")

    if declared < floor:
        findings.append(f"{path.name}: {declared} rows declare their states, below the recorded "
                        f"floor of {floor}. A declaration was removed; put it back.")
    elif declared > floor:
        findings.append(f"{path.name}: {declared} rows declare their states and the floor is "
                        f"{floor}. Raise DECLARED_FLOOR to {declared} in this PR, or the next "
                        f"removal goes unnoticed.")
    return declared, findings


# --------------------------------------------------------------------------- selftest

COMPLETE = """## Widget
- **States:** default `bg-card` · hover `/90` · focused ring-2 · loading `aria-busy` ·
  disabled `opacity-50` · error `aria-invalid` · empty n/a - always has content
"""
MISSING_LOADING = """## Widget
- **States:** default `bg-card` · hover `/90` · focused ring-2 · disabled `opacity-50` ·
  error `aria-invalid` · empty `Empty state`
"""

# THE CASE THE SPLIT EXISTS FOR. Covers `empty` and is SILENT on `error` -- which is what a row
# looked like under the old combined slot, and it passed. `Table (CRUD)` is the real instance,
# inverted: it covers neither, but a row covering one and not the other is the shape that was
# invisible.
EMPTY_BUT_NO_ERROR = """## Widget
- **States:** default `bg-card` · hover `/90` · focused ring-2 · loading `aria-busy` ·
  disabled `opacity-50` · empty `Empty state`
"""

# The old spelling, which must NOT satisfy either slot on its own -- otherwise every row written
# before the split keeps passing while covering one of the two.
COMBINED_SPELLING = """## Widget
- **States:** default `bg-card` · hover `/90` · focused ring-2 · loading `aria-busy` ·
  disabled `opacity-50` · error/empty `Empty state`
"""
BARE_NA = """## Widget
- **States:** default `bg-card` · hover n/a · focused ring-2 · loading `aria-busy` ·
  disabled `opacity-50` · error `aria-invalid` · empty n/a - always has content
"""
DOCTRINE = f"""## A rule about the file
{NOT_A_COMPONENT}
Prose, not a component.
"""
WORD_SOUP = """## Widget
- It has a default look, changes on hover, takes focus, shows a loading spinner, can be
  disabled, and has an empty state. Six words, no claim.
"""


def selftest() -> int:
    failures = []

    def run(label, text, *, floor, expect_findings, matching=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "components.md"
            p.write_text(text, encoding="utf-8")
            _, found = check(p, floor)
        got = len(found) > 0
        if got != expect_findings:
            failures.append(f"{label}: expected findings={expect_findings}, got {found}")
        elif matching and not any(matching in f for f in found):
            failures.append(f"{label}: no finding mentioning {matching!r}; got {found}")

    # THE DISCRIMINATING PAIR. A complete row passes and a row missing ONE slot fails -- run
    # against inputs that differ only in that slot, or the check could be refusing everything.
    run("a complete declaration passes", COMPLETE, floor=1, expect_findings=False)
    run("a declaration missing 'loading' fails", MISSING_LOADING, floor=1,
        expect_findings=True, matching="'loading'")

    # THE SPLIT'S OWN DISCRIMINATING PAIR (#1068 follow-up). `error` and `empty` are two slots, so
    # a row covering one and silent on the other must fail -- that row PASSED under the combined
    # slot, which is the defect. Paired with COMPLETE above, which differs only in having both.
    run("covering 'empty' while silent on 'error' fails", EMPTY_BUT_NO_ERROR, floor=1,
        expect_findings=True, matching="'error'")
    run("the old combined 'error/empty' spelling is refused by name", COMBINED_SPELLING, floor=1,
        expect_findings=True, matching="pre-split")

    # The escape hatch must not become a loophole.
    run("a bare n/a is refused", BARE_NA, floor=1, expect_findings=True, matching="no reason")

    # THE WHOLE POINT, AND THE ONE A WORD COUNT WOULD GET WRONG. This row contains all six words
    # in prose and makes no claim; it must NOT count as declared, so the floor of 1 is unmet.
    run("prose containing all six words is not a declaration", WORD_SOUP, floor=1,
        expect_findings=True, matching="below the recorded floor")
    run("...and the same prose with a floor of 0 is simply undeclared", WORD_SOUP, floor=0,
        expect_findings=False)

    # A doctrine section is exempt because the FILE says so, not because this script knows its name.
    run("a not-a-component section is exempt", DOCTRINE, floor=0, expect_findings=False)
    run("...but it may not be exempt and declare states at once", DOCTRINE + COMPLETE.replace(
        "## Widget", ""), floor=0, expect_findings=True, matching="one or the other")

    # THE RATCHET, BOTH DIRECTIONS. Neither alone is a ratchet: drop-only lets the floor go stale,
    # growth-only lets a declaration be deleted.
    run("a drop below the floor fails", COMPLETE, floor=2, expect_findings=True,
        matching="below the recorded floor")
    run("unrecorded growth fails", COMPLETE, floor=0, expect_findings=True, matching="Raise")

    # AGAINST THE REAL FILE, not only fixtures. A selftest built from synthetic rows proves the
    # parser and not the rule. `Button`'s declaration wraps across two lines, which a line-based
    # reader drops the tail of -- so assert the wrapped half is seen.
    rows = {r.name: r for r in parse(CATALOGUE.read_text(encoding="utf-8"))}
    button = rows.get("Button")
    if button is None:
        failures.append("the real catalogue has no 'Button' row -- has it been renamed?")
    elif button.declaration is None:
        failures.append("'Button' declares states in the real file and the parser did not see it")
    elif "loading" not in button.declaration.lower():
        failures.append("'Button' declaration was truncated at the line break -- "
                        f"got {button.declaration!r}")

    for name in ("Every component takes `**attrs` and renders them on its root element",
                 "The focus ring: `outline-hidden`, never `outline-none` (Tailwind v4)"):
        row = rows.get(name)
        if row is None:
            failures.append(f"the real catalogue has no {name!r} section")
        elif not row.exempt:
            failures.append(f"{name!r} is doctrine and is not marked {NOT_A_COMPONENT}")

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"selftest: {'FAILED' if failures else 'ok'} "
          f"({len(failures)} failure{'' if len(failures) == 1 else 's'})")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    declared, findings = check(CATALOGUE, DECLARED_FLOOR)
    if findings:
        print(f"component states: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    total = sum(1 for r in parse(CATALOGUE.read_text(encoding="utf-8")) if not r.exempt)
    print(f"component states: {declared} of {total} rows declare all seven, floor {DECLARED_FLOOR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
