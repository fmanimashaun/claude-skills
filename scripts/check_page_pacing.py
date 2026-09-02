#!/usr/bin/env python3
"""Reconcile the page-pacing doctrine against the repo it describes (#92, Phase 5).

Run:  python3 scripts/check_page_pacing.py            # measure, fail on a stale claim
      python3 scripts/check_page_pacing.py --selftest  # prove the rules fire AND stay silent

WHY. `page-anatomies.md` -> *How a page is paced* exists because of a defect visible in our own
generated data: 14 marketing-section rows of `coverage.md` carry a byte-identical `Build from`
string, so a landing page built from them literally is fourteen identical centred stacks. The
section states that count, states a band range, and ships a worked band sequence whose whole point
is that consecutive bands differ. Every one of those is a claim about the repo, and a claim in prose
rots silently -- the `claims-vs-enforcement` class the `code-review` skill is built around.

Same shape as `check_shared_shapes.py`: it refuses only a **number or a name in shipped doctrine
disagreeing with the repo**. It is not a design gate. Nothing here judges whether a band sequence is
good; it judges whether the one we ship obeys the rules we wrote next to it and names rows that
exist.

THE SIX RULES, and each is a join, never a taste:

  identical-row-count   the stated count of identical `Build from` rows != what coverage.md holds
  band-count            the worked table's band count falls outside the range its own prose states
  unknown-composition   a band's `Composed from` names no row of coverage.md
  unknown-tone          a Tone value names no role declared in foundations-tokens.md
  tone-repeat           two consecutive bands share a Tone (rule 1: tone alternates)
  shape-repeat          two consecutive bands share BOTH Columns and Width (rule 2)

WHY THE VOCABULARY IS JOINED, NOT LISTED. `unknown-tone` resolves each Tone through the
`@theme inline` block of `foundations-tokens.md` rather than a hardcoded {card, background}. The
section promises it introduces no new token; a hardcoded pair would let a future edit add
`bg-surface` to the table and pass, which is the promise going unenforced in the file that makes it.

FOUR RULES DELIBERATELY NOT ADDED (#476), and the measurement that decided each. An external
catalogue names four more "monotony" axes that look like they belong beside the two repeat rules
above. None of them earns a gate here, and the reasons differ:

  LAY-017  layout family repeated > 2x. MEASURED AGAINST OUR OWN TABLE AND REJECTED: the shipped
           band sequence uses shape ('1', 'prose') for 3 of its 7 bands -- hero, a prose band and
           the closing band legitimately share the shape for centred prose. Their threshold would
           flag our own correct doctrine, which is the definition of a rule that is not a join.
           A gate needing a carve-out on the first real input is taste wearing a count.

  LAY-015  repeated closing CTA. REJECTED AS A DOCTRINE CONTRADICTION: `page-anatomies.md` states
           the opposite and gives its reason -- *"One primary action, repeated ... The same CTA
           appears in the hero, once mid-page, and in the closing band"*, because the failure is
           two COMPETING primary actions, not one repeated. Adopting it would have this gate
           enforce against the file it exists to reconcile.

  VIS-012  surface and elevation monotony, and
  LAY-024  divider monotony. REJECTED AS UNMEASURABLE HERE: their own detection is *"remove them
           and see whether structure survives"*, which is a judgement, and neither surface
           treatment nor divider style appears in the band table this gate reads. There is no
           column to join against.

Recorded rather than re-litigated, for the same reason `marketing-copy.md` §6 lists what it
deliberately did not write: an idea that looks obviously good gets proposed again every few months
unless the measurement that killed it is written next to the code.

Exit codes:  0 the doctrine matches the repo * 1 it does not * 2 a file could not be read or parsed

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFS = REPO / "skills" / "design-system" / "references"
DOC = REFS / "page-anatomies.md"
COVERAGE = REFS / "coverage.md"
TOKENS = REFS / "foundations-tokens.md"

BEGIN = "<!-- page-pacing:begin -->"
END = "<!-- page-pacing:end -->"

# A band row: `| 1 | Hero -- ... | Hero section | card | 1 | prose |`. The leading integer is what
# rejects the header and the `|---|` separator, so no extra parsing state is needed -- the same
# trick `check_shared_shapes.py` plays with its digit column.
#
# #639. IMPORTED FROM THE PLUGIN, not kept here. `compose_brief.py` reads the same table at runtime
# to build a composition brief, and two parsers of one table drift -- after which the maintainer
# gate and the shipped generator disagree about what the doctrine says. The direction is deliberate:
# maintainer tooling may read shipped code, never the reverse (`plugin-boundaries` rule 3).
sys.path.insert(0, str(REPO / "plugins" / "design-flow" / "scripts"))
from compose_brief import BAND_ROW as BAND  # noqa: E402

# The two prose claims. Applied to the marked block with newlines collapsed, so a claim staying on
# one line is not something an author has to remember.
COUNT_CLAIM = re.compile(r"\*\*(\d+)\*\*\s+marketing-section rows carry a byte-identical")
RANGE_CLAIM = re.compile(r"\*\*(\d+)[–-](\d+) bands\*\*")

# A row of either coverage.md table: the first cell is the component name. Six cells in both, which
# is what separates them from the Totals / how-to-read / interaction-pattern tables.
COVERAGE_ROW = re.compile(r"^\|([^|]+)\|([^|]*\|){4}[^|]*\|\s*$")

# `--color-card: var(--card);` inside `@theme inline` -- the roles a band may legally paint.
THEME_INLINE = re.compile(r"@theme inline\s*\{(.*?)\}", re.S)
COLOUR_ROLE = re.compile(r"--color-([a-z0-9-]+)\s*:")


@dataclass(frozen=True)
class Band:
    n: int
    band: str
    composed: str
    tone: str
    columns: str
    width: str

    @property
    def shape(self) -> tuple[str, str]:
        return (self.columns, self.width)


@dataclass(frozen=True)
class Pacing:
    """Everything the marked block claims, parsed."""

    identical_rows: int
    band_min: int
    band_max: int
    bands: tuple[Band, ...]


class Unreadable(RuntimeError):
    """An input did not yield what this check needs -- reported, never a silent pass."""


# --------------------------------------------------------------------------
# measurement -- the repo side of every join
# --------------------------------------------------------------------------

def coverage_rows(text: str) -> list[tuple[str, ...]]:
    """Every six-cell row of coverage.md, cells stripped."""
    rows: list[tuple[str, ...]] = []
    for line in text.splitlines():
        line = line.strip()
        if not COVERAGE_ROW.match(line):
            continue
        cells = tuple(c.strip() for c in line.strip("|").split("|"))
        if cells[1] in {"Kind", "---"}:      # the header and separator of either table
            continue
        rows.append(cells)
    if not rows:
        raise Unreadable(
            f"{COVERAGE.name}: no six-cell component rows. Either the generator's table shape "
            "changed or the file is truncated; a join against nothing is not a join.")
    return rows


def identical_build_from(rows: list[tuple[str, ...]]) -> int:
    """How many rows share the single most common `Build from` string.

    Selecting on the marketing where-clause picks the DERIVABLE table for free, and that is the
    point rather than a happy accident: the two tables put different things in the same columns --
    cell 4 is `Build from` in the derivable table and `Where / when to use it` in the documented
    one, cell 5 is the where-clause and `Watch out for` respectively. Only a derivable row can carry
    that where-clause in cell 5, so the filter is also the table discriminator, and no fragile
    "which section am I in" state is needed.
    """
    marketing = [r for r in rows
                 if r[5] == "a section of a marketing page, stacked inside the landing / pricing "
                            "/ about anatomy"]
    if not marketing:
        raise Unreadable(
            f"{COVERAGE.name}: no rows carry the marketing-section where-clause, so the count the "
            "doctrine states cannot be measured. The generator's wording changed; update this "
            "check rather than leaving the comparison dead.")
    counts: dict[str, int] = {}
    for row in marketing:
        counts[row[4]] = counts.get(row[4], 0) + 1
    return max(counts.values())


def component_names(rows: list[tuple[str, ...]]) -> set[str]:
    return {r[0] for r in rows}


def colour_roles(text: str) -> set[str]:
    """Role names bound in `@theme inline` -- `--color-card` -> `card`."""
    block = THEME_INLINE.search(text)
    if not block:
        raise Unreadable(
            f"{TOKENS.name}: no `@theme inline` block, so the legal band tones cannot be resolved. "
            "A tone vocabulary checked against nothing is not checked.")
    roles = set(COLOUR_ROLE.findall(block.group(1)))
    if not roles:
        raise Unreadable(f"{TOKENS.name}: the `@theme inline` block declares no `--color-*` role")
    return roles


# --------------------------------------------------------------------------
# the doctrine side
# --------------------------------------------------------------------------

def declared(text: str) -> Pacing:
    if BEGIN not in text or END not in text:
        raise Unreadable(
            f"{DOC.name}: no {BEGIN} / {END} markers. Without them this check would parse whatever "
            "table it found first, which is how a gate starts reading the wrong input.")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    flat = " ".join(block.split())

    count = COUNT_CLAIM.search(flat)
    if not count:
        raise Unreadable(
            f"{DOC.name}: the marked block states no identical-row count. It is the finding the "
            "whole section rests on; without it there is nothing to re-measure.")
    rng = RANGE_CLAIM.search(flat)
    if not rng:
        raise Unreadable(f"{DOC.name}: the marked block states no `**N-M bands**` range")

    bands = tuple(Band(int(m.group("n")), m.group("band"), m.group("composed"),
                       m.group("tone"), m.group("columns"), m.group("width"))
                  for line in block.splitlines()
                  for m in [BAND.match(line.strip())] if m)
    if not bands:
        raise Unreadable(f"{DOC.name}: the marked block has no band rows")
    return Pacing(int(count.group(1)), int(rng.group(1)), int(rng.group(2)), bands)


# --------------------------------------------------------------------------
# the join
# --------------------------------------------------------------------------

def reconcile(doc_text: str, coverage_text: str, tokens_text: str) -> list[str]:
    """Findings, one string each. Empty means the doctrine matches the repo."""
    pacing = declared(doc_text)
    rows = coverage_rows(coverage_text)
    names = component_names(rows)
    roles = colour_roles(tokens_text)
    findings: list[str] = []

    measured = identical_build_from(rows)
    if measured != pacing.identical_rows:
        findings.append(
            f"identical-row-count: the section says {pacing.identical_rows} marketing-section rows "
            f"share a `Build from` string; {COVERAGE.name} has {measured}. The finding this section "
            f"exists for has moved -- update the number, or the section's premise.")

    if not pacing.band_min <= len(pacing.bands) <= pacing.band_max:
        findings.append(
            f"band-count: the worked sequence has {len(pacing.bands)} bands, and its own prose says "
            f"{pacing.band_min}-{pacing.band_max}. A table that breaks the rule printed above it "
            f"teaches the rule is optional.")

    for band in pacing.bands:
        if band.composed not in names:
            findings.append(
                f"unknown-composition: band {band.n} composes from {band.composed!r}, which is no "
                f"row of {COVERAGE.name}. The section promises it composes only from rows that "
                f"already exist.")
        if band.tone not in roles:
            findings.append(
                f"unknown-tone: band {band.n} is toned {band.tone!r}, which is no role in "
                f"{TOKENS.name}'s `@theme inline`. The section promises no new token.")

    for prev, nxt in zip(pacing.bands, pacing.bands[1:]):
        if prev.tone == nxt.tone:
            findings.append(
                f"tone-repeat: bands {prev.n} and {nxt.n} are both {prev.tone!r}. Rule 1 is that "
                f"tone alternates at every boundary -- it is what gives a band an edge without a "
                f"border.")
        if prev.shape == nxt.shape:
            findings.append(
                f"shape-repeat: bands {prev.n} and {nxt.n} are both {prev.columns} column(s) at "
                f"{prev.width} width. Rule 2 is that consecutive bands never share both -- sharing "
                f"both is the fourteen-identical-stacks defect this section names.")
    return findings


def run() -> int:
    try:
        doc = DOC.read_text(encoding="utf-8")
        findings = reconcile(doc, COVERAGE.read_text(encoding="utf-8"),
                             TOKENS.read_text(encoding="utf-8"))
        pacing = declared(doc)
    except (OSError, Unreadable) as exc:
        print(f"CANNOT RECONCILE: {exc}", file=sys.stderr)
        return 2
    if findings:
        print(f"{len(findings)} stale claim(s) in {DOC.relative_to(REPO)} -> "
              f"How a page is paced:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print("\nThis is not a design gate. It only refuses a number or a name in shipped doctrine "
              "disagreeing with the repo.", file=sys.stderr)
        return 1
    print(f"page pacing: {len(pacing.bands)} bands in "
          f"{pacing.band_min}-{pacing.band_max}, {pacing.identical_rows} identical "
          f"`Build from` rows -- {DOC.relative_to(REPO)} matches the repo.")
    return 0


# --------------------------------------------------------------------------
# selftest -- fixtures, weighted toward SILENCE.
#
# Synthetic on purpose. The mutation checker runs this file from a temp directory containing the
# module and nothing else, so a fixture reading the real tree would die there on a missing file --
# reading as a caught mutation when it is only a crash, and a crash is not a verdict.
# --------------------------------------------------------------------------

_WHERE = "a section of a marketing page, stacked inside the landing / pricing / about anatomy"
_BUILD = "`center` > `stack` of Heading + prose"

_COVERAGE = "\n".join([
    "| Component | Kind | In TW | In FB | Where / when to use it | Watch out for |",
    "|---|---|---|---|---|---|",
    "| Button | component | y | y | any action | - |",
    "",
    "| Component | Kind | In TW | In FB | Build from | Where / when to use it |",
    "|---|---|---|---|---|---|",
    f"| Hero section | composition | y | y | {_BUILD} | {_WHERE} |",
    f"| Feature section | composition | y | - | {_BUILD} | {_WHERE} |",
    f"| CTA section | composition | y | - | {_BUILD} | {_WHERE} |",
    f"| Logo cloud | composition | y | - | {_BUILD} | {_WHERE} |",
    f"| Footer | composition | y | y | `center` > `cluster` of links | {_WHERE} |",
    "| Grid list | composition | y | - | `grid-auto` of Cards | a region of an app screen |",
])

_TOKENS = """\
@theme inline {
  --color-background: var(--background); --color-foreground: var(--foreground);
  --color-card: var(--card); --color-card-foreground: var(--card-foreground);
  --color-primary: var(--primary);
}
"""

# The fixture's band sequence, as (composed, tone, columns, width). Four bands, alternating tone and
# never repeating a shape -- the CLEAN case every FIRES fixture below perturbs by exactly one thing.
_BANDS = (
    ("Hero section", "card", "1", "prose"),
    ("Feature section", "background", "n", "shell"),
    ("Logo cloud", "card", "1", "shell"),
    ("CTA section", "background", "1", "prose"),
)


def _doc(identical: int = 4, lo: int = 3, hi: int = 6,
         bands: tuple[tuple[str, str, str, str], ...] = _BANDS) -> str:
    rows = "\n".join(
        f"| {i} | Band {i} | {c} | {t} | {col} | {w} |"
        for i, (c, t, col, w) in enumerate(bands, start=1))
    return (
        f"## How a page is paced\n\n{BEGIN}\n\n"
        f"In coverage.md, **{identical}**\nmarketing-section rows carry a byte-identical "
        f"`Build from` string.\n\n"
        f"**{lo}–{hi} bands** sit between the header and the footer.\n\n"
        "| # | Band | Composed from | Tone | Columns | Width |\n|---|---|---|---|---|---|\n"
        f"{rows}\n\n{END}\n")


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    rows = coverage_rows(_COVERAGE)
    check("the coverage walk finds both tables' component rows", len(rows) == 7,
          f"found {len(rows)}: {[r[0] for r in rows]}")
    check("the identical-Build-from count is measured over marketing rows only",
          identical_build_from(rows) == 4, f"{identical_build_from(rows)}")
    check("the role vocabulary comes from @theme inline",
          colour_roles(_TOKENS) == {"background", "foreground", "card", "card-foreground",
                                    "primary"},
          f"{sorted(colour_roles(_TOKENS))}")

    # SILENCE, and it is the half that matters: a checker that fires on correct input is a checker
    # that gets switched off, and then nothing checks pacing at all.
    out = reconcile(_doc(), _COVERAGE, _TOKENS)
    check("a correct section is silent", out == [], f"{out}")

    # The count claim survives being split across a line break, because prose wraps.
    check("the count claim is read across a newline",
          declared(_doc(identical=9)).identical_rows == 9, "")

    # SILENCE: a band count at either end of its own stated range is inside it.
    out = reconcile(_doc(lo=4, hi=4), _COVERAGE, _TOKENS)
    check("a band count equal to both ends of the range is silent", out == [], f"{out}")

    # SILENCE: two non-adjacent bands may share a shape. Rule 2 is about CONSECUTIVE bands, and a
    # rule that forbade every repeat would forbid the closing CTA mirroring the hero, which the
    # shipped sequence does on purpose.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Feature section", "background", "n", "shell"),
        ("Logo cloud", "card", "1", "shell"),
        ("CTA section", "background", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("a shape reused NON-adjacently is silent", out == [], f"{out}")

    # FIRES: the stated count disagrees with the file.
    out = reconcile(_doc(identical=13), _COVERAGE, _TOKENS)
    check("a wrong identical-row count is reported",
          any(f.startswith("identical-row-count") for f in out), f"{out}")

    # FIRES: more bands than the section's own prose allows.
    out = reconcile(_doc(lo=6, hi=8), _COVERAGE, _TOKENS)
    check("a band count outside the stated range is reported",
          any(f.startswith("band-count") for f in out), f"{out}")

    # FIRES: a band composing from something that is not a row.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Video hero section", "background", "n", "shell"),
        ("Logo cloud", "card", "1", "shell"),
        ("CTA section", "background", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("a band naming no coverage row is reported",
          any(f.startswith("unknown-composition") for f in out), f"{out}")

    # SILENCE: the join is by NAME across the whole file, not by section. A band may legitimately
    # compose from a row the marketing where-clause does not cover, and refusing that would push
    # authors to invent a marketing-flavoured duplicate of a row that already exists.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Grid list", "background", "n", "shell"),
        ("Logo cloud", "card", "1", "shell"),
        ("CTA section", "background", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("a real row from the other table is accepted", out == [], f"{out}")

    # FIRES: a tone naming no role. This is the promise "no new token" being enforced.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Feature section", "surface", "n", "shell"),
        ("Logo cloud", "card", "1", "shell"),
        ("CTA section", "background", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("a tone naming no role is reported",
          any(f.startswith("unknown-tone") for f in out), f"{out}")

    # FIRES: two consecutive bands on the same tone.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Feature section", "card", "n", "shell"),
        ("Logo cloud", "background", "1", "shell"),
        ("CTA section", "card", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("two consecutive bands on one tone are reported",
          any(f.startswith("tone-repeat") for f in out), f"{out}")

    # FIRES: the fourteen-identical-stacks shape itself -- tone still alternates, but the two bands
    # are the same column count at the same width, so the boundary does not read.
    out = reconcile(_doc(bands=(
        ("Hero section", "card", "1", "prose"),
        ("Feature section", "background", "1", "prose"),
        ("Logo cloud", "card", "1", "shell"),
        ("CTA section", "background", "1", "prose"),
    )), _COVERAGE, _TOKENS)
    check("two consecutive bands of the same shape are reported",
          any(f.startswith("shape-repeat") for f in out), f"{out}")

    # An input that cannot be parsed must RAISE, never parse the nearest thing that looks right. A
    # gate that silently reads the wrong input reports clean over something it never examined.
    for label, fn in (
        ("a document with no markers", lambda: declared("| 1 | a | b | c | d | e |\n")),
        ("a marked block with no count claim",
         lambda: declared(f"{BEGIN}\n**3–6 bands**\n| 1 | a | b | c | d | e |\n{END}\n")),
        ("a marked block with no range",
         lambda: declared(f"{BEGIN}\n**4** marketing-section rows carry a byte-identical x\n"
                          f"| 1 | a | b | c | d | e |\n{END}\n")),
        ("a marked block with no band rows",
         lambda: declared(f"{BEGIN}\n**4** marketing-section rows carry a byte-identical x\n"
                          f"**3–6 bands**\n{END}\n")),
        ("coverage with no component rows", lambda: coverage_rows("# nothing\n")),
        ("coverage with no marketing rows",
         lambda: identical_build_from(coverage_rows(
             "| A | component | y | y | where | watch |\n"))),
        ("tokens with no @theme inline", lambda: colour_roles(":root { --card: #fff; }\n")),
    ):
        n += 1
        try:
            fn()
            failures.append(f"{label} parsed instead of raising")
        except Unreadable:
            pass

    # The docstring's LAY-017 rejection rests on a NUMBER about this repo -- "3 of its 7 bands".
    # An unchecked number in a rationale rots exactly like an unchecked number in doctrine, and
    # then the decision reads as authoritative while being false. Re-derive it. If the band table
    # legitimately changes, this fails and the RATIONALE gets rewritten -- which is the point:
    # the measurement is what makes the rejection honest, so it must survive with the table.
    import collections as _c
    try:
        _bands = declared(DOC.read_text(encoding="utf-8")).bands
        _top = max(_c.Counter(b.shape for b in _bands).values())
        check("the LAY-017 rejection's measurement still holds",
              (_top, len(_bands)) == (3, 7),
              f"docstring says 3 of 7; the table now has {_top} of {len(_bands)} -- "
              f"rewrite the rationale, do not just change the number")
    except Exception as exc:  # noqa: BLE001 -- ANY failure must be a verdict, never a crash.
        # Deliberately broad. A mutation elsewhere in this file can make `declared` raise, or
        # leave no bands for `max()`; if that propagates, the selftest dies before it prints a
        # single verdict and every OTHER fixture looks like it went quiet. A crash is not a
        # verdict -- the harness cannot tell one from a broken selftest.
        check("the LAY-017 rejection's measurement still holds", False,
              f"could not re-derive it: {type(exc).__name__}: {exc}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_page_pacing selftest: {n} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile page-anatomies.md's pacing section against the repo.")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
