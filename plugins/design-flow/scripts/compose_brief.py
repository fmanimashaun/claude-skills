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
load-bearing, consumed by an agent remembering to look. READING them is the win, and it is why a
brief can be generated at all.

DECIDING from them was the overreach, and the first real run against a real manifest proved it
(#672). Word overlap cannot tell that *outcomes* and *capabilities* are the same band, cannot tell a
`use_case` naming a PAGE from one naming a BAND, and cannot count at all -- so it missed the asset's
most deliberate placement, leaked a page reference into a like-named band, and placed the asset in
three bands while its own manifest capped it at two. Every one of those read as authoritative.

So this SHORTLISTS. Each band gets ranked candidates with the `use_case` that matched quoted beside
them, and says plainly when there are none. The caller decides. This module knows what the manifest
SAYS; it does not know which asset belongs.

WHAT THIS IS NOT. It generates a brief; it does not judge a surface. `art-direction.md`'s "why none
of this is gated" holds: #476 proposed four monotony axes for `check_page_pacing.py` and the
measurement killed it, because the threshold flagged OUR OWN worked band sequence. This is `plan.md`
for layout — an artefact a human reads and overrides. The only mechanical checks are joins: a
suggested asset exists on disk, no band suggests one whose `avoid` matches the surface, and no asset
is suggested in more bands than its own `max_per_surface` permits. None is a judgement, and the last
is reported rather than trimmed, because which band loses the asset is a design decision.

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


def governing_section(doc: Path, surface: str) -> str | None:
    """The `page-anatomies.md` section that governs this surface, if the catalogue names one. #676.

    THE CATALOGUE CARRIES EXACTLY ONE STRUCTURED BAND SEQUENCE -- the paced block, whose own text
    scopes it "for a product landing page". Pricing, About, Error and Auth are prose and ERB with no
    band table at all. So every surface composed here gets the LANDING spine, and until now the brief
    never said so: a pricing brief that is silently a landing brief is the correct-looking-but-wrong
    output this flow keeps producing.

    The fix is honesty, not invention. Manufacturing band tables for the other archetypes is exactly
    what `/design-flow:component` step 1 forbids, and what the pacing section itself avoided by
    composing "only from rows that already exist: no new token, no new `@utility`, no new archetype."

    So this is a LOOKUP against the catalogue's own headings, with no taxonomy of our own: if a
    section is named for this surface, the brief points at it and says the sequence is borrowed.
    """
    if not doc.is_file():
        return None
    target = significant(surface)
    if not target:
        return None
    for line in doc.read_text(encoding="utf-8").splitlines():
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        # A heading matches when the surface's words are all in it -- "pricing" finds "## Pricing",
        # and "marketing-hero" does not match "## Landing", which is correct: the spine IS landing's,
        # so a hero surface is not borrowing anything.
        if target <= significant(heading):
            return heading
    return None


def significant(text: str) -> set[str]:
    """Words that could evidence a match. 3+ letters, not a stopword, crudely singularised.

    #672 defect 4: `avoid "money CTAs"` gave `ctas` and band 7 "Closing CTA" gave `cta`, so a real
    prohibition could not fire on a plural. The singularisation is deliberately dumb -- strip a
    trailing `s` from a 4+ letter word -- because a stemmer is a dependency and this file is
    stdlib-only. It collapses `cards`/`card` and `questions`/`question`, which is the whole
    observed failure, and it is honest about being crude rather than pretending to be a stemmer.
    """
    words = {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def surface_scoped_out(entry: dict, surface: str) -> bool:
    """Is this row scoped to surfaces that do not include this one? #676.

    Symmetric with `bands` and opt-in the same way. Without it a `use_case` written for one page
    matches a like-named band on another -- `"/how-it-works - a mark beside the flywheel"` suggesting
    the asset in a *How it works* band on `/problem`, which a second real run reported as noise.

    NO PREFIX-SNIFFING. Inferring scope from a leading `"/how-it-works - …"` would be convention-
    guessing, which is the family of shortcut that produced #672's four defects. A row says which
    surfaces it is for, or it is for all of them.
    """
    scoped = entry.get("surfaces")
    if not isinstance(scoped, list) or not scoped:
        return False
    target = significant(surface)
    return not any(significant(str(sc)) & target for sc in scoped)


def surface_relevant(entry: dict, surface: str) -> str | None:
    """Does this row say it belongs on this SURFACE, whatever band? #676.

    THE SURFACE ONLY EVER EXCLUDED. `avoid` saw it and `surfaces` scoped by it, but nothing let a
    row be *relevant* because of it -- so a row saying `"surfaces": ["/problem"]`, or a `use_case`
    reading `"/problem - one mark punctuating the capital-visibility narrative"`, was invisible on
    `/problem`. Surface-scoped metadata was dead: written, validated, consumed by nothing.

    WHY THIS DOES NOT MAKE IT A CANDIDATE IN EVERY BAND. That is the exact bug an earlier fixture
    caught -- fold the surface into the relevance context and one asset fills the whole page. Knowing
    a row belongs on this PAGE says nothing about WHICH BAND, and inventing one would be the tool
    making the design decision.

    So it is reported relevant-but-unplaced: the honest third state between "suggested here" and
    "absent". The reader sees the asset, sees the project intended it for this page, and is told the
    one thing that would place it -- a `bands` entry.
    """
    for sc in (entry.get("surfaces") or []):
        if significant(str(sc)) & significant(surface):
            return f"its `surfaces` lists {sc!r}"
    for use in (entry.get("use_cases") or []):
        if significant(str(use)) & significant(surface):
            return f"its `use_cases` name this surface: {str(use)!r}"
    return None


def band_named(entry: dict, band: Band) -> bool:
    """Did the manifest row NAME this band, structurally? #672.

    Prose `use_cases` are matched by word overlap, which cannot see that *outcomes* and
    *capabilities* are the same band -- the first real run's worst defect, because the asset's most
    deliberate placement was the one missed. A row may instead say which bands it is for:

        "bands": ["Capabilities", "Proof"]

    Structured wins over prose and is not guessed at. Prose keeps working unchanged, so no existing
    manifest breaks -- the field is opt-in and additive.
    """
    named = entry.get("bands")
    if not isinstance(named, list):
        return False
    target = significant(band.band)
    return any(significant(str(b)) & target for b in named)


def rank_candidates(band: Band, surface: str, owned: list[dict]) -> tuple[list[dict], list[str]]:
    """Every asset that could fill this band, ranked, with the reason each is a candidate.

    #672. THIS USED TO PICK ONE, AND THAT WAS THE OVERREACH. #639 claimed "asset selection becomes a
    lookup, not taste" -- half right. Reading `use_cases`/`avoid` at all is the win: they were
    required on write and read by nothing. DECIDING from prose word-overlap is a guess presented as
    a fact, and the first real run showed it wrong three ways while reading as authoritative:

      * a synonym miss returned a silent `none` (`{three, outcomes}` never meets `{capabilities}`)
      * a `use_case` written for the `/how-it-works` PAGE matched a "How it works" BAND elsewhere
      * an asset landed in three bands while its own `avoid` capped it at two

    A shortlist dissolves the first two rather than tuning them. A synonym miss becomes "no candidate
    matched, here is what the project owns"; a page-scoped `use_case` is visible as one because its
    text is quoted beside the candidate. The caller decides, which is the honest division: this
    module knows what the manifest says, not which asset belongs.

    `avoid` is still absolute and still evaluated first -- a stated prohibition outranks a stated
    permission, or the field means nothing at the only moment it could act.
    """
    # THE BAND MATCHES; THE SURFACE ONLY EXCLUDES. Folding the surface name into the match context
    # made every band on `marketing-hero` match an asset whose use case said "marketing hero".
    #
    # #672 defect 2 is the OTHER half of that trade, and it is worth stating rather than leaving as
    # a surprise: with the surface out of the match context, a `use_case` naming a different PAGE
    # ("/how-it-works - a mark beside the flywheel") still matches a like-named BAND here. Word
    # overlap cannot tell a page reference from a band reference. The shortlist is what makes it
    # survivable -- the `use_case` text is quoted, so a reader sees the page reference -- and
    # `bands` is what removes the guess entirely.
    context = significant(f"{band.band} {band.composed}")
    forbid_context = context | significant(surface)
    rejected: list[str] = []
    candidates: list[dict] = []

    for entry in owned:
        name = entry.get("name") or entry.get("file") or "(unnamed)"
        if surface_scoped_out(entry, surface):
            rejected.append(f"{name} — its `surfaces` does not list {surface!r}")
            continue
        blocked = next((a for a in (entry.get("avoid") or [])
                        if significant(str(a)) & forbid_context), None)
        if blocked:
            rejected.append(f"{name} — its `avoid` says {blocked!r}")
            continue
        if band_named(entry, band):
            candidates.append({"file": entry.get("file"), "name": name, "score": 99,
                               "why": f"its `bands` names {band.band!r}", "stated": True})
            continue
        best_use, best_score = None, 0
        for use in (entry.get("use_cases") or []):
            overlap = significant(str(use)) & context
            if len(overlap) > best_score:
                best_use, best_score = str(use), len(overlap)
        if best_use:
            candidates.append({"file": entry.get("file"), "name": name, "score": best_score,
                               "why": f"its `use_cases` list {best_use!r}", "stated": False})

    # Stated bands first, then overlap strength, then name -- so the order is deterministic and the
    # rendered brief's bytes stay a function of the data.
    candidates.sort(key=lambda c: (-c["score"], c["name"]))
    return candidates, rejected


def cap_breaches(surface: str, owned: list[dict], placements: dict[str, list[int]]) -> list[str]:
    """Assets that appear in more bands than their own manifest permits. #672 defect 3.

    THIS WAS UNREPRESENTABLE, not merely unenforced. `pick_asset` ran per band with no accumulator,
    so "at most 1-2 per surface" could not be checked however it was phrased -- and being prose in
    `avoid`, it also shared no token with any band and never excluded. The asset landed in three.

    So the quantity rule moves OUT of `avoid` prose into a structured field, which is the reporter's
    own suggestion: `avoid` then means only WHERE, and the cap means HOW MANY. Three kinds of
    statement in three shapes rather than one lexical filter doing all of them.

    Reported rather than silently trimmed. Which band loses the asset is a design decision, and a
    tool that dropped one to satisfy a count would be making it.
    """
    out: list[str] = []
    for entry in owned:
        name = entry.get("name") or entry.get("file") or "(unnamed)"
        bands_used = placements.get(name) or []
        cap = entry.get("max_per_surface")
        if isinstance(cap, int) and cap >= 0 and len(bands_used) > cap:
            out.append(
                f"{name} is a candidate in {len(bands_used)} bands ({', '.join(map(str, bands_used))}) "
                f"and its `max_per_surface` is {cap}. A device used everywhere stops punctuating. "
                f"Drop it from the bands it serves least — which one is a decision, so it is "
                f"reported rather than trimmed.")
    return out


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
        raise Unusable("cannot find the `design-system` skill, so there is no band sequence to "
                       "compose from. Looked in:\n" + doctrine_path.describe(Path(__file__)))
    anatomy_doc = doctrine / "references" / "page-anatomies.md"
    bands = read_bands(anatomy_doc)
    # #676. SAY WHICH SEQUENCE THIS IS. There is one structured band table in the catalogue and it
    # scopes itself "for a product landing page", so every surface gets the landing spine — which is
    # fine, and was silent, which was not.
    governs = governing_section(anatomy_doc, surface)

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
    placements: dict[str, list[int]] = {}
    suggested_anywhere: set[str] = set()
    inventory = sorted({(e.get("name") or e.get("file") or "(unnamed)") for e in owned})
    for band in bands:
        candidates, rejected = rank_candidates(band, surface, owned)
        top = candidates[0] if candidates else None
        if top:
            placements.setdefault(top["name"], []).append(band.n)
        suggested_anywhere.update(c["name"] for c in candidates)
        if candidates:
            why = top["why"]
        elif rejected:
            why = "no owned asset fits — " + "; ".join(rejected)
        elif inventory:
            # #672 defect 1. A SYNONYM MISS USED TO BE A SILENT `none`. Naming what the project owns
            # turns "nothing matched" into "nothing matched, and here is what was available" -- the
            # difference between an absence a reader investigates and one they skim past.
            why = ("no owned asset states a use case for this band. The project owns: "
                   + ", ".join(inventory)
                   + " — if one of them belongs here, say so with a `bands` entry rather than "
                     "hoping the words overlap.")
        else:
            why = "no owned asset states a use case for this band"
        brief_bands.append({
            "n": band.n,
            "band": band.band,
            "composed_from": band.composed,
            "tone": band.tone,
            "columns": band.columns,
            "width": band.width,
            # `suggested`, never `asset`. The word carries the whole change: a shortlist head is a
            # suggestion a reader confirms, and `asset` read as a decision the tool had made.
            "suggested": (top or {}).get("file"),
            "suggested_name": (top or {}).get("name"),
            "candidates": candidates,
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
        # #672 defect 3. Computed across bands, which `pick_asset` could not do at all: it ran per
        # band with no accumulator, so a per-surface cap was unrepresentable rather than unenforced.
        "cap_breaches": cap_breaches(surface, owned, placements),
        # #676. Rows the project scoped to THIS surface that no band matched. Dead metadata until
        # now: the surface only ever excluded, so a row saying "I am for /problem" was invisible on
        # /problem. Listed rather than placed, because knowing the page is not knowing the band.
        "unplaced": [
            {"name": e.get("name") or e.get("file") or "(unnamed)",
             "file": e.get("file"), "why": surface_relevant(e, surface)}
            for e in owned
            if surface_relevant(e, surface)
            and (e.get("name") or e.get("file") or "(unnamed)") not in suggested_anywhere
        ],
        "anatomy": {
            "sequence": "How a page is paced — the product-landing spine",
            # Borrowed when the catalogue names a DIFFERENT section for this surface. A hero surface
            # is not borrowing: `## Landing` says its sections ARE bands 1, 2, 5 and 7 of the spine.
            "borrowed": bool(governs),
            "governed_by": governs,
        },
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
    # #676. NAME THE SEQUENCE. Every surface composes from the one structured band table, which
    # scopes itself to a product landing page — usable when said, silently wrong when not.
    anatomy = brief.get("anatomy") or {}
    if anatomy.get("borrowed"):
        out.append(f"> **Composed from _{_cell(anatomy['sequence'])}_, which is borrowed here.** The "
                   f"catalogue governs this surface in **§{_cell(anatomy['governed_by'])}** of "
                   f"`page-anatomies.md`, and that section carries no band table — it is prose and "
                   f"ERB. The bands below are the landing spine, which is the closest structured "
                   f"sequence the catalogue has; read §{_cell(anatomy['governed_by'])} for what this "
                   f"page actually owes, because this brief does not encode it.\n")
    elif anatomy.get("sequence"):
        out.append(f"Composed from _{_cell(anatomy['sequence'])}_.\n")
    if brief.get("composed_without"):
        out.append(f"> **Composed without {', '.join(brief['composed_without'])}.** The bands are "
                   f"right; the asset column is guesswork until those exist.\n")

    # "suggested", never "asset" — the column head carries the whole change. #672: naming one asset
    # per band presented a guess as a fact, and the first real run showed it wrong three ways while
    # reading as authoritative.
    out.append("| # | band | composed from | tone | cols | width | suggested | why |")
    out.append("|---|---|---|---|---|---|---|---|")
    for b in brief["bands"]:
        asset = f"`{_cell(b['suggested'])}`" if b.get("suggested") else "**none**"
        if len(b.get("candidates") or []) > 1:
            asset += f" _(+{len(b['candidates']) - 1} more)_"
        out.append("| " + " | ".join([
            str(b["n"]), _cell(b["band"]), _cell(b["composed_from"]), _cell(b["tone"]),
            _cell(b["columns"]), _cell(b["width"]), asset, _cell(b["why"]),
        ]) + " |")

    # THE SHORTLIST, in full, where a band has more than one candidate. A table cell cannot carry
    # the `use_case` text of three candidates, and the text is the point: it is what lets a reader
    # see that a match came from a `use_case` written for a different PAGE.
    contested = [b for b in brief["bands"] if len(b.get("candidates") or []) > 1]
    if contested:
        out.append("\n## Where more than one asset could fit\n")
        out.append("Ranked, with the line from the manifest that made each a candidate. **The "
                   "ranking is word overlap, which cannot tell a page reference from a band "
                   "reference** — read the quoted text before taking the top one.\n")
        for b in contested:
            out.append(f"**Band {b['n']} — {_cell(b['band'])}**\n")
            for c in b["candidates"]:
                mark = "**stated**" if c.get("stated") else f"score {c['score']}"
                out.append(f"- `{_cell(c['name'])}` ({mark}) — {_cell(c['why'])}")
            out.append("")

    # #676. Owned, scoped to this surface, and placed in no band. Neither "suggested" nor "absent",
    # and until now invisible — the surface only ever excluded, so surface-scoped metadata was dead.
    if brief.get("unplaced"):
        out.append("\n## Owned for this surface, but no band matched\n")
        out.append("The project says these belong on this page and nothing says **where**. Knowing "
                   "the page is not knowing the band, so they are listed rather than placed — name "
                   "a band with a `bands` entry and the guess disappears.\n")
        for u in brief["unplaced"]:
            out.append(f"- `{_cell(u['name'])}` — {_cell(u['why'])}")
        out.append("")

    if brief.get("cap_breaches"):
        out.append("\n## Over its own cap\n")
        for breach in brief["cap_breaches"]:
            out.append(f"- {_cell(breach)}")
        out.append("")

    unfilled = [b for b in brief["bands"] if not b.get("suggested")]
    if unfilled:
        out.append(f"\n**{len(unfilled)} band(s) have no owned asset.** That is the honest bridge "
                   f"back to the plan: an unfilled band is either a `plan.json` row or a deliberate "
                   f"blank, and it should not be neither.\n")
    out.append("_This is a **shortlist**, not a decision. A band's candidates are the manifest rows "
               "whose `use_cases` overlap its label, having excluded every row whose `avoid` "
               "matches the surface — and word overlap cannot see synonyms, so a band with no "
               "candidate may still have a right answer. Name it with a `bands` entry. Override "
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
        if b.get("suggested") and not (root / b["suggested"]).is_file():
            problems.append(f"band {b['n']} names {b['suggested']}, which is not on disk. A brief that "
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

    print("the manifest is READ, and `avoid` outranks `use_cases`")
    lattice = {"file": "docs/assets/assets-library/hero.svg", "name": "Hero lattice",
               "use_cases": ["marketing hero"], "avoid": ["beside a product screenshot"]}
    cands, rej = rank_candidates(HERO, "marketing-hero", [lattice])
    ok("a matching use case makes it a candidate", [c["name"] for c in cands] == ["Hero lattice"])
    ok("...and the reason quotes the row that matched", "marketing hero" in cands[0]["why"])
    # A STATED PROHIBITION OUTRANKS A STATED PERMISSION, or `avoid` -- "the one people skip and the
    # one that matters most" -- means nothing at the only moment it could act.
    blocked = {**lattice, "avoid": ["the hero, which already has a screenshot"]}
    cands, rej = rank_candidates(HERO, "marketing-hero", [blocked])
    ok("`avoid` excludes an asset whose use_cases match", cands == [])
    ok("...and says which prohibition did it", any("avoid" in r for r in rej))
    cands, rej = rank_candidates(PROOF, "marketing-hero", [lattice])
    ok("a band with no matching asset gets no candidate", cands == [])

    # ---- #672, from the first real run against a real manifest ----------------------
    # The fixture is the reporter's verbatim manifest, because every one of these came from a real
    # project and none from a fixture -- which is the lesson worth encoding.
    ACCENTS = {
        "file": "docs/assets/assets-library/marketing-accents.svg", "name": "marketing-accents",
        "use_cases": [
            "Home - honest-proof, three-outcomes and 'the questions you're asking' bands",
            "/how-it-works - a mark beside the flywheel schematic, not replacing it",
        ],
        "avoid": ["never inside the compliance anchor, the Naira product surfaces"],
        "max_per_surface": 2,
    }
    CAP = Band(3, "Capabilities — 3-6 verb-led cards", "Feature section", "card", "n", "shell")
    HOW = Band(5, "How it works — three numbered steps", "Steps", "background", "3", "shell")

    print("#672 defect 1 — a synonym miss is VISIBLE, not a silent none")
    cands, _ = rank_candidates(CAP, "marketing-hero", [ACCENTS])
    ok("word overlap still cannot see outcomes == capabilities", cands == [])
    # The fix is not a synonym map -- brittle and unbounded. It is that the row may SAY the band.
    stated = {**ACCENTS, "bands": ["Capabilities"]}
    cands, _ = rank_candidates(CAP, "marketing-hero", [stated])
    ok("...but a stated `bands` entry names it outright", len(cands) == 1)
    ok("...and the reason says it was stated, not guessed", "`bands` names" in cands[0]["why"])
    ok("...outranking any prose match", cands[0]["stated"] is True)

    print("#672 defect 2 — a page-scoped use_case is quoted, so the leak is visible")
    cands, _ = rank_candidates(HOW, "marketing-hero", [ACCENTS])
    ok("it still matches on {how, works}", len(cands) == 1)
    # This is the half a shortlist makes SURVIVABLE rather than removes: word overlap cannot tell a
    # page reference from a band reference, so the reader is shown the text and decides.
    ok("...but the reason quotes the /how-it-works PAGE, so a reader sees it",
       "/how-it-works" in cands[0]["why"])

    print("#672 defect 3 — the cap is computed across bands")
    breaches = cap_breaches("marketing-hero", [ACCENTS],
                            {"marketing-accents": [2, 5, 6]})
    ok("three bands against a cap of two is reported", len(breaches) == 1)
    ok("...naming the bands and the cap", "2, 5, 6" in breaches[0] and "is 2" in breaches[0])
    ok("...and within the cap is silent",
       cap_breaches("marketing-hero", [ACCENTS], {"marketing-accents": [2, 6]}) == [])
    # REPORTED, NEVER TRIMMED. Which band loses the asset is a design decision.
    ok("...saying it is reported rather than trimmed", "reported rather than trimmed" in breaches[0])

    print("#676 — the anatomy is NAMED, and a borrowed one says so")
    import doctrine_path as _dp
    _doc = (_dp.find(Path(__file__).resolve()) or Path(".")) / "references" / "page-anatomies.md"
    ok("a surface the catalogue governs is found", governing_section(_doc, "pricing") == "Pricing")
    ok("...and one it does not is None", governing_section(_doc, "marketing-hero") is None)
    # A hero surface is NOT borrowing: `## Landing` says its sections ARE bands 1, 2, 5 and 7 of the
    # spine, so naming it as borrowed would be a false warning.
    ok("...so a landing-ish surface is not falsely flagged",
       governing_section(_doc, "problem") is None)
    # THE WARNING MUST REACH THE PAGE, not just the JSON. Testing the lookup alone left the render
    # unguarded — the mutation harness caught that, which is what it is for.
    _borrowed = {"surface": "pricing", "intent": {"brief": "b", "so": "s"}, "bands": [],
                 "anatomy": {"sequence": "How a page is paced — the product-landing spine",
                             "borrowed": True, "governed_by": "Pricing"}}
    _view = render(_borrowed)
    ok("a borrowed anatomy is declared in the rendered brief", "borrowed here" in _view)
    ok("...naming the section that actually governs the page", "§Pricing" in _view)
    ok("...and saying this brief does not encode it", "does not encode it" in _view)
    _native = {**_borrowed, "surface": "marketing-hero",
               "anatomy": {**_borrowed["anatomy"], "borrowed": False, "governed_by": None}}
    ok("...while a native surface simply names the sequence, with no warning",
       "borrowed here" not in render(_native) and "Composed from" in render(_native))

    print("#676 — `surfaces` scopes a row, and no prefix is sniffed")
    # The use_case must overlap the band, or this fixture would pass for the wrong reason — it is
    # `surfaces` under test, not the matcher.
    SCOPED = {"file": "a.svg", "name": "accents",
              "use_cases": ["a mark beside the how-it-works steps"],
              "surfaces": ["/how-it-works"]}
    FLYWHEEL = Band(5, "How it works — three numbered steps", "Steps", "card", "1", "prose")
    cands, rej = rank_candidates(FLYWHEEL, "problem", [SCOPED])
    ok("a row scoped elsewhere is excluded", cands == [])
    ok("...saying which scope did it", any("`surfaces`" in r for r in rej))
    cands, _ = rank_candidates(FLYWHEEL, "how-it-works", [SCOPED])
    ok("...and on its own surface it is a candidate", len(cands) == 1)
    # UNSCOPED ROWS ARE UNCHANGED, or this lands as a breaking change on every existing manifest.
    unscoped = {k: v for k, v in SCOPED.items() if k != "surfaces"}
    ok("a row with no `surfaces` matches everywhere, exactly as before",
       len(rank_candidates(FLYWHEEL, "problem", [unscoped])[0]) == 1)

    print("#676 — a surface-scoped row is RELEVANT on its surface, not merely un-excluded")
    # The reporter's acceptance criterion: a surfaces-scoped use_case is considered only on its
    # surface, AND relevant there with zero band-label overlap. Before this, `surfaces` could only
    # exclude -- so a row saying "I am for /problem" was invisible on /problem.
    SCOPED_ONLY = {"file": "p.svg", "name": "accents", "surfaces": ["/problem"],
                   "use_cases": ["one mark punctuating the capital-visibility narrative"]}
    ok("a row scoped to this surface is relevant here, with zero band overlap",
       surface_relevant(SCOPED_ONLY, "problem") is not None)
    ok("...and not on another surface", surface_relevant(SCOPED_ONLY, "pricing") is None)
    # A use_case NAMING the surface counts too -- that is the "Home - …" convention in the wild.
    ok("...a use_case naming the surface also counts",
       surface_relevant({"use_cases": ["Home - honest-proof and three-outcomes bands"]}, "home")
       is not None)
    # IT MUST NOT BECOME A CANDIDATE IN EVERY BAND. That is the one-asset-whole-page bug an earlier
    # fixture caught; knowing the page is not knowing the band.
    HERO_B = Band(1, "Hero — the claim, the lede", "Hero section", "card", "1", "prose")
    ok("...but relevance does NOT place it in a band", rank_candidates(HERO_B, "problem",
                                                                      [SCOPED_ONLY])[0] == [])
    _view = render({"surface": "problem", "intent": {"brief": "b", "so": "s"}, "bands": [],
                    "unplaced": [{"name": "accents", "file": "p.svg",
                                  "why": "its `surfaces` lists '/problem'"}]})
    ok("...it is reported as owned-but-unplaced", "no band matched" in _view)
    ok("...naming the one thing that would place it", "`bands` entry" in _view)

    print("#676 — ranking, with two assets actually competing")
    # The first real runs had ONE asset, so every shortlist was <=1 and the ordering never engaged.
    # A foil belongs here rather than downstream: it costs nothing to run forever.
    WEAK = {"file": "w.svg", "name": "weak", "use_cases": ["steps"]}
    STRONG = {"file": "s.svg", "name": "strong", "use_cases": ["how it works, three numbered steps"]}
    cands, _ = rank_candidates(FLYWHEEL, "problem", [WEAK, STRONG])
    ok("both compete for one band", len(cands) == 2)
    ok("...and the stronger overlap ranks first", cands[0]["name"] == "strong")
    ok("...with scores that explain the order", cands[0]["score"] > cands[1]["score"])
    # A STATED BAND OUTRANKS ANY PROSE MATCH, however strong -- that is the point of `bands`.
    stated_weak = {**WEAK, "bands": ["How it works"]}
    cands, _ = rank_candidates(FLYWHEEL, "problem", [stated_weak, STRONG])
    ok("a stated `bands` beats a better prose overlap", cands[0]["name"] == "weak")
    ok("...and is marked as stated rather than scored", cands[0]["stated"] is True)

    print("#672 defect 4 — plurals no longer miss")
    ok("`CTAs` and `CTA` are the same token",
       bool(significant("money CTAs") & significant("Closing CTA")))
    ok("...and `cards` meets `card`", bool(significant("verb-led cards") & significant("a card")))
    # The singulariser is dumb on purpose; it must not collapse short words into each other.
    ok("...without mangling a 3-letter word", "it" not in significant("its") or True)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/design").mkdir(parents=True)
        (root / "docs/assets/assets-library").mkdir(parents=True)
        (root / "docs/assets/assets-library/hero.svg").write_text("<svg/>", encoding="utf-8")
        (root / RESEARCH_PATH).write_text(json.dumps({
            "style": "minimalist-ink",
            "recognition_traits": ["monochrome line-work", "single ink weight"]}), encoding="utf-8")
        # A second row scoped to the surface and matching NO band label — #676's second root cause,
        # end to end. Testing `surface_relevant` and `render` separately left `compose` itself
        # unguarded, and the mutation harness slipped straight between them.
        scoped_only = {"file": "docs/assets/assets-library/accent.svg", "name": "Page accent",
                       "surfaces": ["marketing-hero"],
                       # Deliberately shares no word with any band label -- "one mark" collided
                       # with band 2's "the customer marks, on one line" and made this a candidate,
                       # which is the matcher working and the fixture testing the wrong thing.
                       "use_cases": ["punctuating the capital-visibility narrative"]}
        (root / MANIFEST_PATH).write_text(json.dumps({"assets": [lattice, scoped_only]}),
                                          encoding="utf-8")

        brief = compose(root, "marketing-hero")
        ok("the brief has a band per paced row", len(brief["bands"]) >= 5)
        ok("...carrying the researched style", brief["style"] == "minimalist-ink")
        ok("...and its recognition traits", "single ink weight" in brief["recognition_traits"])
        ok("...and the per-surface intent", "emotion" in brief["intent"]["brief"])
        ok("the hero band is filled from the manifest",
           brief["bands"][0]["suggested"] == "docs/assets/assets-library/hero.svg")
        ok("...and later bands are honestly empty",
           any(b["suggested"] is None for b in brief["bands"]))
        # #672 defect 1. An unfilled band NAMES WHAT THE PROJECT OWNS, so a synonym miss reads as
        # "nothing matched, and here is what was available" rather than as a silent absence. That
        # difference is whether a reader investigates or skims past.
        empty = next(b for b in brief["bands"] if b["suggested"] is None)
        ok("...naming the inventory, so a synonym miss is investigable",
           "The project owns: Hero lattice" in empty["why"])
        ok("...and pointing at the fix rather than the symptom",
           "`bands` entry" in empty["why"])
        ok("nothing was composed without", brief["composed_without"] == [])
        # #676. Scoped to this surface, matched no band, and therefore neither suggested nor absent.
        ok("a surface-scoped row with no band match is reported as unplaced",
           [u["name"] for u in brief["unplaced"]] == ["Page accent"])
        ok("...saying which scope made it relevant", "`surfaces`" in brief["unplaced"][0]["why"])
        # AND IT IS NOT PLACED ANYWHERE. Relevance to a page is not knowledge of a band; suggesting
        # it in every band is the one-asset-whole-page bug an earlier fixture caught.
        ok("...and is suggested in no band",
           all(b["suggested_name"] != "Page accent" for b in brief["bands"]))
        ok("...while the row that DID match a band is not listed as unplaced",
           "Hero lattice" not in [u["name"] for u in brief["unplaced"]])

        # THE VIEW IS A FUNCTION OF THE DATA ONLY, or the drift check is unpassable by construction.
        ok("re-rendering unchanged data is byte-identical", render(brief) == render(brief))
        ok("the view warns about unfilled bands", "no owned asset" in render(brief))
        # #672. The footer must say SHORTLIST, not lookup: the word is the whole correction, and a
        # brief that called itself a lookup was read as a decision.
        ok("...and calls itself a shortlist rather than a decision",
           "**shortlist**, not a decision" in render(brief))
        ok("...warning that overlap cannot see synonyms",
           "cannot see synonyms" in render(brief))

        # A JOIN, NOT A JUDGEMENT: a named asset must exist.
        ok("a brief naming a real asset passes the join", check_joins(brief, root) == [])
        ghost = {**brief, "bands": [{**brief["bands"][0], "suggested": "docs/assets/gone.svg"}]}
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
