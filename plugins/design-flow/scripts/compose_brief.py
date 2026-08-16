#!/usr/bin/env python3
"""The composition brief: which assets, in which bands, at what tone — generated, not derived again.

#639. The asymmetry this closes, stated plainly:

    what to buy    ->  docs/assets/plan.json + a generated plan.md, one row per asset, reviewable
    how to compose ->  nothing

We generate a concrete, reviewable artefact for the decision that costs MONEY, and nothing at all for
the decision that determines whether the page looks professional. `/design-flow:component`'s order of
operations is thorough and correct — and it is a READING LIST. It tells the agent which files to open
and then leaves it to derive, per surface and from scratch, which assets this surface needs and where
they go. Every derivation is a fresh chance to differ from the last one.

THE JOIN THAT MAKES THIS GENERATABLE RATHER THAN A SECOND OPINION. `generation_gate.ENTRY_FIELDS`
already REQUIRES every manifest row to carry `use_cases` ("where it MAY go — a list, because reuse is
the point") and `avoid` ("where it must NOT go; without this the set drifts by well-meaning reuse").
`/design-flow:generate` calls `avoid` "the one people skip and the one that matters most".

Nothing read them. Grepping every command, agent and skill for a composition-time consumer of
`use_cases` returned only the three places that DOCUMENT the field. Required on write, declared
load-bearing, consumed by an agent remembering to look. So asset selection here is a LOOKUP, not
taste — which is the whole reason a brief can be generated at all.

WHAT THIS IS NOT. It generates a brief; it does not judge a surface. `art-direction.md`'s "why none
of this is gated" holds: #476 proposed four monotony axes for `check_page_pacing.py` and the
measurement killed it, because the threshold flagged OUR OWN worked band sequence. This is `plan.md`
for layout — an artefact a human reads and overrides. The only mechanical checks are joins: a band
naming an owned asset names one that exists, and no band uses an asset whose `avoid` matches the
surface. Neither is a judgement.

Two files, one source, exactly as the plan and the prompt library do it:

    docs/design/compositions/<surface>.json   the source — agents read this
    docs/design/compositions/<surface>.md     a VIEW of it — generated, drift-checked

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctrine_path  # noqa: E402

COMPOSITION_DIR = Path("docs/design/compositions")
RESEARCH_PATH = Path("docs/design/reference-research.json")
MANIFEST_PATH = Path("docs/assets/manifest.json")

# The marked block in `page-anatomies.md` that carries the paced band sequence. Bounded by the same
# markers `scripts/check_page_pacing.py` uses, so both read the same region rather than two
# hand-aligned line ranges.
BEGIN = "<!-- page-pacing:begin -->"
END = "<!-- page-pacing:end -->"

# A band row: `| 1 | Hero -- ... | Hero section | card | 1 | prose |`. The leading integer is what
# rejects the header and the `|---|` separator, so no parsing state is needed.
BAND_ROW = re.compile(
    r"^\|\s*(?P<n>\d+)\s*\|\s*(?P<band>[^|]+?)\s*\|\s*(?P<composed>[^|]+?)\s*\|"
    r"\s*(?P<tone>[^|]+?)\s*\|\s*(?P<columns>[^|]+?)\s*\|\s*(?P<width>[^|]+?)\s*\|\s*$")

# Per-surface aesthetic intent, from `art-direction.md` §3. Kept here as a mapping rather than parsed
# out of that file's table: it is a CLASSIFICATION of surfaces, and the table states the brief for
# each class in prose that no generator should be re-wording.
SURFACE_INTENT = {
    "marketing": ("emotion, then comprehension",
                  "generous negative space, one large claim, imagery that carries meaning"),
    "dense-app": ("clarity and density, no drama",
                  "tighten spacing, drop decoration, let alignment do the work"),
    "focused-task": ("calm and singular",
                     "remove everything that is not the task; the focal point is the submit"),
    "empty-error": ("orientation, then a way out",
                    "one sentence of plain language and one action; never decorate a dead end"),
}

# Words too common to evidence a match between a band and an asset's stated use case.
_STOP = frozenset({"the", "and", "for", "with", "a", "an", "of", "on", "in", "to", "one", "its",
                   "section", "page", "band", "this", "that", "from", "into", "same", "three"})


class Unusable(Exception):
    """The brief cannot be composed from what the project holds."""


@dataclass(frozen=True)
class Band:
    n: int
    band: str
    composed: str
    tone: str
    columns: str
    width: str


def read_bands(doc: Path) -> list[Band]:
    """The paced band sequence, from the marked block in `page-anatomies.md`.

    THE TABLE IS THE SOURCE, not a rendering of one, so reading it is not the defect
    `derived-artifacts` warns about — there is no structured original being bypassed. What that rule
    does forbid is a SECOND parser drifting from the first, which is why `check_page_pacing.py`
    imports this one rather than keeping its own.
    """
    if not doc.is_file():
        raise Unusable(f"no page-anatomies.md at {doc}. The band sequence lives there, and without "
                       f"it a composition brief would be inventing page structure — which is the "
                       f"thing `/design-flow:component` step 1 forbids.")
    text = doc.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise Unusable(f"{doc} has no `{BEGIN}` / `{END}` block. The markers bound the paced "
                       f"sequence; without them this would scrape every table in the file.")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    bands = [Band(int(m.group("n")), m.group("band"), m.group("composed"),
                  m.group("tone"), m.group("columns"), m.group("width"))
             for line in block.splitlines() if (m := BAND_ROW.match(line.strip()))]
    if not bands:
        raise Unusable(f"the page-pacing block in {doc} contains no band rows. An empty sequence "
                       f"would compose a brief with no bands and read as though the page had none.")
    return bands


def significant(text: str) -> set[str]:
    """Words that could evidence a match. 3+ letters, not a stopword."""
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def pick_asset(band: Band, surface: str, owned: list[dict]) -> tuple[dict | None, str]:
    """Which owned asset fills this band, and WHY that one. A lookup, never taste.

    `avoid` is evaluated FIRST and is absolute. `/design-flow:generate` calls it "the one people skip
    and the one that matters most": without it a curated family drifts by well-meaning reuse, one
    reasonable-looking placement at a time. An asset whose `avoid` matches this band is excluded even
    if its `use_cases` match perfectly — a stated prohibition outranks a stated permission, or the
    field means nothing.

    Returns the entry and the reason, or (None, why not). The reason is the deliverable: "the manifest
    row whose use_cases said 'marketing hero'" is reviewable; "the agent chose it" is not.
    """
    # THE BAND MATCHES; THE SURFACE ONLY EXCLUDES. Folding the surface name into the match context
    # made every band on `marketing-hero` match an asset whose use case said "marketing hero" --
    # the surface name dominated and the whole page filled with one asset. Caught by this module's
    # own fixture, which is why the band-with-no-match case is asserted rather than assumed.
    #
    # `avoid` still sees the surface: "anywhere beside a product screenshot" is a statement about
    # the PAGE, not about one band, and evaluating it band-only would let a forbidden asset in.
    context = significant(f"{band.band} {band.composed}")
    forbid_context = context | significant(surface)
    rejected: list[str] = []
    best: tuple[int, dict, str] | None = None

    for entry in owned:
        name = entry.get("name") or entry.get("file") or "(unnamed)"
        blocked = next((a for a in (entry.get("avoid") or [])
                        if significant(str(a)) & forbid_context), None)
        if blocked:
            rejected.append(f"{name} — its `avoid` says {blocked!r}")
            continue
        for use in (entry.get("use_cases") or []):
            overlap = significant(str(use)) & context
            if overlap:
                score = len(overlap)
                if best is None or score > best[0]:
                    best = (score, entry, f"its `use_cases` list {use!r}")

    if best:
        return best[1], best[2]
    if rejected:
        return None, "no owned asset fits — " + "; ".join(rejected)
    return None, "no owned asset states a use case for this band"


def compose(root: Path, surface: str, intent: str = "marketing") -> dict:
    """One surface's composition brief, from what the project already holds."""
    if intent not in SURFACE_INTENT:
        raise Unusable(f"unknown surface intent {intent!r}; expected one of "
                       f"{', '.join(SURFACE_INTENT)}. The classes come from `art-direction.md` §3, "
                       f"and the point of them is that the same composition is right on one surface "
                       f"and wrong on another.")
    # REFUSE ON None rather than degrading — doctrine_path's own contract, and #617's lesson: the
    # message must list every root tried, or "the catalogue is missing" is indistinguishable from
    # "I looked in the wrong place".
    doctrine = doctrine_path.find(Path(__file__))
    if doctrine is None:
        raise Unusable("cannot find the `fidara-design` skill, so there is no band sequence to "
                       "compose from. Looked in:\n" + doctrine_path.describe(Path(__file__)))
    bands = read_bands(doctrine / "references" / "page-anatomies.md")

    research: dict = {}
    rpath = root / RESEARCH_PATH
    if rpath.is_file():
        try:
            research = json.loads(rpath.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise Unusable(f"{RESEARCH_PATH} is not valid JSON ({exc}).")

    owned: list[dict] = []
    mpath = root / MANIFEST_PATH
    if mpath.is_file():
        try:
            owned = json.loads(mpath.read_text(encoding="utf-8")).get("assets", [])
        except ValueError as exc:
            raise Unusable(f"{MANIFEST_PATH} is not valid JSON ({exc}).")

    brief_bands = []
    for band in bands:
        entry, why = pick_asset(band, surface, owned)
        brief_bands.append({
            "n": band.n,
            "band": band.band,
            "composed_from": band.composed,
            "tone": band.tone,
            "columns": band.columns,
            "width": band.width,
            "asset": (entry or {}).get("file"),
            "asset_name": (entry or {}).get("name"),
            "why": why,
        })

    brief, so = SURFACE_INTENT[intent]
    return {
        "surface": surface,
        "intent": {"class": intent, "brief": brief, "so": so},
        # DEGRADED RATHER THAN ABSENT. A project with no research or no manifest still gets a brief,
        # and the brief SAYS what it was composed without -- a silently thinner document reads as a
        # simpler page rather than as missing inputs.
        "style": research.get("style"),
        "recognition_traits": research.get("recognition_traits") or [],
        "composed_without": [n for n, present in
                             (("reference-research.json", bool(research)),
                              ("manifest.json", bool(owned))) if not present],
        "bands": brief_bands,
    }


BANNER = ("<!-- GENERATED from the sibling .json by compose_brief.py --render.\n"
          "     Do not hand-edit: the JSON is the source, this is a view of it.\n"
          "     Rebuild:  python3 <plugin>/scripts/compose_brief.py --surface <name> --render -->\n")


def _cell(value) -> str:
    text = str(value if value not in (None, "", []) else "—").replace("|", "\\|")
    return " ".join(text.split())


def render(brief: dict) -> str:
    """The brief as markdown — GENERATED, and its bytes a function of the data only.

    No timestamp, no git SHA, no absolute path: anything else makes the drift check unpassable by
    construction, which is the lesson `docs/coverage.html` paid for.
    """
    out = [BANNER, f"# Composition brief — {brief['surface']}\n",
           f"**{brief['intent']['brief']}** — {brief['intent']['so']}.\n"]
    if brief.get("style"):
        out.append(f"Style: `{brief['style']}`.\n")
    if brief.get("recognition_traits"):
        out.append("Recognise it by: "
                   + ", ".join(f"**{_cell(t)}**" for t in brief["recognition_traits"]) + ".\n")
    if brief.get("composed_without"):
        out.append(f"> **Composed without {', '.join(brief['composed_without'])}.** The bands are "
                   f"right; the asset column is guesswork until those exist.\n")

    out.append("| # | band | composed from | tone | cols | width | asset | why |")
    out.append("|---|---|---|---|---|---|---|---|")
    for b in brief["bands"]:
        asset = f"`{_cell(b['asset'])}`" if b.get("asset") else "**none**"
        out.append("| " + " | ".join([
            str(b["n"]), _cell(b["band"]), _cell(b["composed_from"]), _cell(b["tone"]),
            _cell(b["columns"]), _cell(b["width"]), asset, _cell(b["why"]),
        ]) + " |")

    unfilled = [b for b in brief["bands"] if not b.get("asset")]
    if unfilled:
        out.append(f"\n**{len(unfilled)} band(s) have no owned asset.** That is the honest bridge "
                   f"back to the plan: an unfilled band is either a `plan.json` row or a deliberate "
                   f"blank, and it should not be neither.\n")
    out.append("_Asset selection is a **lookup**, not a judgement: a band takes the manifest row "
               "whose `use_cases` match it, having excluded every row whose `avoid` does. Override "
               "any of it — this is a brief, not a gate._\n")
    return "\n".join(out)


def paths_for(root: Path, surface: str) -> tuple[Path, Path]:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", surface).strip("-")
    return (root / COMPOSITION_DIR / f"{safe}.json", root / COMPOSITION_DIR / f"{safe}.md")


def check_joins(brief: dict, root: Path) -> list[str]:
    """The only mechanical checks: a named asset exists, and no band uses a forbidden one.

    Both are JOINS, not judgements — which is what keeps this on the right side of
    `art-direction.md`'s "a gate on judgement gets switched off".
    """
    problems = []
    for b in brief["bands"]:
        if b.get("asset") and not (root / b["asset"]).is_file():
            problems.append(f"band {b['n']} names {b['asset']}, which is not on disk. A brief that "
                            f"points at a missing asset sends the builder looking for it.")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--surface", help="the surface to compose a brief for")
    ap.add_argument("--intent", default="marketing", choices=sorted(SURFACE_INTENT),
                    help="per-surface aesthetic intent (art-direction.md §3)")
    ap.add_argument("--render", action="store_true", help="write the JSON and its markdown view")
    ap.add_argument("--check", action="store_true", help="report drift in a committed view")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = Path.cwd()
    try:
        if args.check:
            problems = []
            for jpath in sorted((root / COMPOSITION_DIR).glob("*.json")):
                brief = json.loads(jpath.read_text(encoding="utf-8"))
                mpath = jpath.with_suffix(".md")
                if mpath.is_file() and mpath.read_text(encoding="utf-8") != render(brief):
                    problems.append(f"{mpath.relative_to(root)} no longer matches its JSON. It is "
                                    f"generated, so rebuild it rather than editing it.")
                problems.extend(check_joins(brief, root))
            for p in problems:
                print(p, file=sys.stderr)
            return 1 if problems else 0
        if not args.surface:
            print("nothing to compose: pass --surface (or --check / --selftest)", file=sys.stderr)
            return 2
        brief = compose(root, args.surface, args.intent)
        if args.render:
            jpath, mpath = paths_for(root, args.surface)
            jpath.parent.mkdir(parents=True, exist_ok=True)
            jpath.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
            mpath.write_text(render(brief), encoding="utf-8")
            print(f"wrote {jpath.relative_to(root)} and {mpath.relative_to(root)}")
            return 0
        print(json.dumps(brief, indent=2))
        return 0
    except Unusable as why:
        print(f"cannot compose: {why}", file=sys.stderr)
        return 2


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    HERO = Band(1, "Hero — the claim, the lede", "Hero section", "card", "1", "prose")
    PROOF = Band(2, "Proof — the customer marks", "Logo cloud", "background", "1", "shell")

    print("asset selection is a lookup, and `avoid` outranks `use_cases`")
    lattice = {"file": "docs/assets/assets-library/hero.svg", "name": "Hero lattice",
               "use_cases": ["marketing hero"], "avoid": ["beside a product screenshot"]}
    entry, why = pick_asset(HERO, "marketing-hero", [lattice])
    ok("a matching use case fills the band", entry is lattice)
    ok("...and the reason names the row that matched", "marketing hero" in why)
    # A STATED PROHIBITION OUTRANKS A STATED PERMISSION, or `avoid` -- "the one people skip and the
    # one that matters most" -- means nothing at the only moment it could act.
    blocked = {**lattice, "avoid": ["the hero, which already has a screenshot"]}
    entry, why = pick_asset(HERO, "marketing-hero", [blocked])
    ok("`avoid` excludes an asset whose use_cases match", entry is None)
    ok("...and says which prohibition did it", "avoid" in why)
    entry, why = pick_asset(PROOF, "marketing-hero", [lattice])
    ok("a band with no matching asset takes none", entry is None)
    ok("...and says so rather than guessing", "no owned asset" in why)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/design").mkdir(parents=True)
        (root / "docs/assets/assets-library").mkdir(parents=True)
        (root / "docs/assets/assets-library/hero.svg").write_text("<svg/>", encoding="utf-8")
        (root / RESEARCH_PATH).write_text(json.dumps({
            "style": "minimalist-ink",
            "recognition_traits": ["monochrome line-work", "single ink weight"]}), encoding="utf-8")
        (root / MANIFEST_PATH).write_text(json.dumps({"assets": [lattice]}), encoding="utf-8")

        brief = compose(root, "marketing-hero")
        ok("the brief has a band per paced row", len(brief["bands"]) >= 5)
        ok("...carrying the researched style", brief["style"] == "minimalist-ink")
        ok("...and its recognition traits", "single ink weight" in brief["recognition_traits"])
        ok("...and the per-surface intent", "emotion" in brief["intent"]["brief"])
        ok("the hero band is filled from the manifest",
           brief["bands"][0]["asset"] == "docs/assets/assets-library/hero.svg")
        ok("...and later bands are honestly empty",
           any(b["asset"] is None for b in brief["bands"]))
        ok("nothing was composed without", brief["composed_without"] == [])

        # THE VIEW IS A FUNCTION OF THE DATA ONLY, or the drift check is unpassable by construction.
        ok("re-rendering unchanged data is byte-identical", render(brief) == render(brief))
        ok("the view warns about unfilled bands", "no owned asset" in render(brief))
        ok("...and states that selection was a lookup", "not a judgement" in render(brief))

        # A JOIN, NOT A JUDGEMENT: a named asset must exist.
        ok("a brief naming a real asset passes the join", check_joins(brief, root) == [])
        ghost = {**brief, "bands": [{**brief["bands"][0], "asset": "docs/assets/gone.svg"}]}
        ok("...and one naming a missing asset does not",
           any("not on disk" in p for p in check_joins(ghost, root)))

    # DEGRADED RATHER THAN ABSENT. A project with neither research nor manifest still gets a brief,
    # and the brief says what it lacked -- a silently thinner document reads as a simpler page.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        brief = compose(root, "marketing-hero")
        ok("a bare project still gets a brief", len(brief["bands"]) >= 5)
        ok("...that names what it was composed without",
           set(brief["composed_without"]) == {"reference-research.json", "manifest.json"})
        ok("...and says so in the view", "asset column is guesswork" in render(brief))

    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
