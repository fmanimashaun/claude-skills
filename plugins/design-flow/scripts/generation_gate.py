#!/usr/bin/env python3
"""Decide whether an asset may be generated, compose its prompt, and refuse when it must.

This is #507 — the pay-as-you-go generation path — expressed as machinery rather than advice. The
maintainer decision it implements, verbatim: *"the agent needs to be very economical, knowing when
exactly to generate … if you don't need it, don't generate, and you need to know exactly what you
want to generate and use the cheapest model to get the best output."*

Three of those four requirements are CHECKABLE, so writing them as prose would be the defect this
repo is built around. The precedent is exact: #161, where the README *mandated* `--max-total-usd`
while the flag stayed optional. A budget that is documented and not enforced is not a budget — and
this one has a bill attached.

WHAT IT REFUSES, and why each refusal is a join rather than a judgement:

  1. NO TIER-1/2 REFUSAL RECORDED -> refuse. The asset hierarchy already decides this: tier 1 is a
     product screenshot (the product IS the asset), tier 2 is brand-geometric decoration built from
     `brand.json` tokens — CSS/SVG, free. Only tiers 3/4 are illustration. So generation is
     unreachable until the request records WHICH surface, and what tiers 1 and 2 could not carry.

  2. NO AGGREGATOR CONFIGURED -> refuse, and say so. A shipped plugin cannot depend on an MCP server
     or an API key being present. This is the "say so and stop" degradation, and it is the DEFAULT
     path, not an error path: most installs will never configure a provider, and they must still get
     a coherent answer rather than a stack trace or a placeholder asset.

  3. PROJECTED COST EXCEEDS THE REMAINING CEILING -> refuse. The ceiling lives in project config, is
     compared BEFORE the call, and refusing is the only outcome — there is no warn-and-continue
     branch, because `|| echo` around a cost check is `gate-that-cannot-fail` with a bill.

WHAT IT COMPOSES. The prompt is derived from inputs already held — surface class, the aesthetic
brief for that class, and the pack's palette/type/endorsement — never free-typed. An improvised
prompt produces the stock-art look `visual-assets.md` warns about, AND IT PAYS TWICE, because a
vague prompt is a reroll. A composed prompt is also the only thing that makes the asset
reproducible: without it, a brand change means paying again.

WHY THE LADDER IS NOT IN HERE. Model names and prices change monthly; a list in doctrine rots inside
a quarter. The ladder lives in project config, cheapest first, and this script only enforces the
RULE about it: start at the bottom, climb only when the output fails a stated acceptance check. A
surface with no acceptance check cannot climb, because "best output" would then mean "the agent
liked it".

Exit codes:  0 approved (prompt + provenance on stdout) · 1 REFUSED (reason on stdout)
             2 unusable input or unreadable config

Note that 1 is the working state, not a failure: most calls to this script should refuse. A run that
approves everything has been mis-wired. Stdlib only, no network — this script never calls a
provider; it decides whether the caller may.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CONFIG_PATH = Path(".design-flow/generation.json")

# The tiers that are satisfiable WITHOUT paying anyone. Kept here rather than in config because it
# is a fact about the asset hierarchy, not a per-project preference: a screenshot is free because
# the product exists, and brand-geometric decoration is CSS/SVG built from tokens.
FREE_TIERS = (1, 2)

# A library holds more than flat pictures, and the kinds are split by HOW THEY ARE MADE AND REUSED,
# not by how they look.
#
# `motion` and `video` were one kind for a release, and that was wrong in a way worth recording: it
# routed a loading spinner to a video model. Motion in a product is overwhelmingly Lottie JSON or an
# animated SVG -- a few KB, recoloured from tokens, scrubbable, diffable in review, and authored
# directly by the agent for nothing. Generated video is FOOTAGE: megabytes, fixed palette,
# un-recolourable, expensive, and right for a marketing hero and almost nothing else. Conflating
# them meant the cheap, common case paid the expensive, rare case's price.
#
# `vector` is called out for the same reason: for icons and flat shapes an SVG beats a raster --
# it scales, it diffs in review, and it recolours from tokens without being regenerated.
KINDS = ("static", "vector", "motion", "video")

# Illustration styles as a CLOSED set, because "playful illustration" is not a specification.
# Surveying brands that do this well, the styles are mutually exclusive and instantly
# distinguishable: Mailchimp is monochrome ink line-work on a saturated brand ground; Headspace is
# flat vector with rounded characters, no outlines, faces reduced to two dots and a curve. Both are
# "on-brand" — for different brands. A brief that says only "calm, abstract" can produce either, so
# two runs against one pack drift apart and the second is a reroll nobody planned to pay for.
#
# This list is a taxonomy, not a ladder: it names what the styles ARE, which does not rot the way
# model names and prices do. WHICH style a pack uses is a per-pack decision and lives in config.
STYLES = (
    "minimalist-ink",      # monochrome line-work, high contrast, no gradients (Mailchimp)
    "flat-vector",         # solid fills, no outlines, rounded geometry (Instacart)
    "character-world",     # recurring cast in built environments (Headspace)
    "geometric",           # constructed from primitives — often satisfiable at tier 2
    "vintage-rustic",      # textured, screen-print or letterpress feel
    "3d-render",           # dimensional forms, soft studio lighting
    "cartoon",             # exaggerated proportion, bold outline
    "mixed-media",         # collage of photographic and drawn elements
)


# What a library entry must carry to be USABLE rather than merely present. A manifest that records
# only `file` can dedupe, but it cannot answer the question an agent actually asks -- "may I put this
# here, and will it look right?" -- so the asset gets re-generated by someone who could not tell.
# Each field earns its place by answering one such question:
ENTRY_FIELDS = {
    "file":            "where the asset is",
    "name":            "what to call it in a diff or a conversation",
    "purpose":         "what job it does, so a wrong-but-pretty fit is refusable",
    "use_cases":       "where it MAY go — a list, because reuse is the point",
    "avoid":           "where it must NOT go; without this the set drifts by well-meaning reuse",
    "visual_elements": "what is actually depicted, so a near-duplicate is recognisable as one",
    "style":           "which taxonomy entry, so a mixed set is visible before it ships",
    "kind":            "static / vector / motion — priced, reviewed and reused differently",
    "surface":         "the surface class it was curated for",
}


class Refusal(Exception):
    """A refusal is a normal outcome, so it carries a reason the caller can print verbatim."""


def load_config(root: Path) -> dict:
    path = root / CONFIG_PATH
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"unusable config: {path} is not valid JSON ({exc})")


def check_library(root: Path, request: dict) -> None:
    """The cheapest asset is one that already exists. Check the curated library FIRST.

    The library is a set curated up front from the product's own brief — brainstormed, chosen as a
    coherent family, and recorded in a manifest that says what each asset is and where it belongs.
    That is what makes the set look designed rather than accumulated, and it is also the single
    biggest economy: a hit costs nothing, while a miss is the only thing that should ever reach a
    paid model.

    So this refuses on a MISS THAT WAS NEVER LOOKED FOR. The request must name what it searched the
    manifest for and why nothing fit. Without that, "generate a hero illustration" quietly re-buys
    an asset the project already owns, and the library grows duplicates instead of coverage.
    """
    manifest_path = root / (request.get("library") or "docs/assets/manifest.json")
    if not manifest_path.is_file():
        return  # No library yet — the first asset has nothing to miss against.
    miss = request.get("library_miss")
    if not miss or not miss.get("searched_for") or not miss.get("why_no_fit"):
        raise Refusal(
            f"a curated asset library exists at {manifest_path.parent}, but this request does not "
            f"record a miss against it. State `library_miss.searched_for` and `why_no_fit`: an "
            f"asset the project already owns costs nothing, and re-buying one is how a library "
            f"grows duplicates instead of coverage.")
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8")).get("assets", [])
    except ValueError as exc:
        raise SystemExit(f"unusable library manifest: {manifest_path} ({exc})")
    surface = request["tier_refusal"]["surface"]
    # A manifest entry claiming this exact surface AND kind means the miss is contradicted by the
    # library's own index -- reuse it rather than paying for a second one.
    kind = request.get("kind", "static")
    for entry in entries:
        if entry.get("surface") == surface and entry.get("kind", "static") == kind:
            raise Refusal(
                f"the library already lists a {kind!r} asset for {surface!r} "
                f"({entry.get('file', 'unnamed')}). Reuse it, or retire that entry deliberately — "
                f"generating a second one silently forks the surface's look.")


def check_precondition(request: dict) -> None:
    """Generation is unreachable until tiers 1 and 2 are recorded as unable to carry the surface."""
    refusal = request.get("tier_refusal")
    if not isinstance(refusal, dict):
        raise Refusal(
            "no tier-1/2 refusal recorded. Generation is the LAST resort, not the first: tier 1 is "
            "a product screenshot and tier 2 is brand-geometric decoration built from brand.json — "
            "both free. Record which surface this is, and what tiers 1 and 2 could not carry.")
    surface = refusal.get("surface")
    if not surface:
        raise Refusal("the tier refusal names no surface, so nothing ties this spend to a place in "
                      "the product. Name the surface class from art-direction.md.")
    for tier in FREE_TIERS:
        why = refusal.get(f"tier_{tier}_why_not")
        if not why:
            raise Refusal(
                f"the tier refusal does not say why tier {tier} cannot carry {surface!r}. Both free "
                f"tiers must be ruled out EXPLICITLY — an unstated tier is an unexamined one, and "
                f"tier {tier} costs nothing.")


# Words too common to prove a constraint reached the prompt. "only" appearing in a crafted prompt
# says nothing about whether the palette did, so matching on it would make the check pass on prompts
# that honour nothing -- a gate that cannot fail.
_STOPWORDS = frozenset({
    "only", "with", "that", "this", "from", "into", "onto", "over", "under", "very", "more", "most",
    "some", "such", "than", "then", "they", "them", "have", "been", "were", "will", "your", "just",
    "also", "must", "never", "always", "using", "used", "make", "made", "like", "each", "both",
    "and", "the", "for", "not", "any", "all", "one", "two", "its", "per",
})


def _significant(text: str) -> set[str]:
    """The words in `text` that could actually evidence a constraint: 4+ letters, not a stopword."""
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOPWORDS}


def check_crafted_prompt(request: dict, brief: dict, surface: str) -> str:
    """#629. Accept the agent's own prompt, but hold it to the brief's hard constraints.

    THE TRADE, stated plainly. Derivation guaranteed the constraints reached the prompt and capped
    the quality at string concatenation. Free-typing lifts the cap and drops the guarantee. This
    keeps the guarantee mechanically and gives the phrasing back to the agent, which is the one part
    a model is actually better at than a `"; ".join`.

    The check is deliberately CRUDE and stated rather than clever: for `palette` and `ground`, at
    least one significant word of the brief's value must appear in the prompt; for `avoid`, no
    entry's significant words may ALL appear. A cleverer semantic check would be a second model call
    -- another bill, and a non-deterministic gate. Crude and predictable beats subtle and unbounded
    here, because the whole job is to refuse BEFORE the spend.

    It is a floor, not a proof: an agent can satisfy it and still write a poor prompt. That is fine.
    A floor that catches "the brief said monochrome and the prompt never mentions colour" is exactly
    the #621 regression, and that is what it is for.
    """
    prompt = request["prompt"]
    if not isinstance(prompt, str) or len(prompt.strip()) < 40:
        raise Refusal(
            f"the crafted `prompt` for {surface!r} is empty or too short to be one. A crafted prompt "
            f"replaces a composed one, so it has to carry at least as much: the subject, the style, "
            f"and the brief's constraints. Nothing was spent.")
    # A CRAFTED PROMPT MUST SAY WHY IT IS BETTER. Not ceremony: this is the field that makes the
    # decision reviewable later, and it is the only thing distinguishing "the agent thought about
    # this brief" from "the agent did not read it". It lands in the prompt library beside the prompt.
    if not str(request.get("prompt_rationale") or "").strip():
        raise Refusal(
            f"the request carries a crafted `prompt` for {surface!r} but no `prompt_rationale`. "
            f"Say in one sentence what the composed prompt would have got wrong — a crafted prompt "
            f"with no stated reason cannot be reviewed, and next time nobody can tell whether "
            f"crafting helped. Nothing was spent.")

    words = _significant(prompt)
    for field in ("palette", "ground"):
        value = brief.get(field)
        if not value:
            continue
        wanted = _significant(", ".join(value) if isinstance(value, list) else str(value))
        if wanted and not (wanted & words):
            raise Refusal(
                f"the crafted prompt for {surface!r} never mentions the brief's {field}: "
                f"{value!r}. That is exactly how #621 was paid for — a brief stating "
                f"'monochrome, single-hue only' and a prompt that said nothing about colour, "
                f"answered with a full-colour photograph. Work the constraint into the prompt, or "
                f"change the brief if it is wrong. Nothing was spent.")

    for entry in (brief.get("avoid") or []):
        banned = _significant(str(entry))
        if banned and banned <= words:
            raise Refusal(
                f"the crafted prompt for {surface!r} asks for something the brief's `avoid` list "
                f"forbids: {entry!r}. A prompt requesting what the brief rules out will be answered "
                f"exactly as asked, and the result rejected on arrival. Nothing was spent.")
    return prompt.strip()


def compose_prompt(request: dict, brief: dict, pack: dict) -> str:
    """Derive the prompt. Never accept one from the caller — that is the whole point.

    A `prompt` key in the request is rejected rather than ignored, because silently overriding it
    would let a caller believe their text was used while it was not.
    """
    surface = request["tier_refusal"]["surface"]
    if "prompt" in request:
        # #629. A CRAFTED PROMPT IS NOW ALLOWED, AND CHECKED. This used to be a flat refusal, on the
        # grounds that an improvised prompt produces the stock-art look and pays twice. That was half
        # right, and the half it got wrong cost real money: derivation concatenates brief fields
        # verbatim (#621/#624), so a brief carrying a PIPELINE instruction -- "traced to a
        # single-path SVG (currentColor)" -- posts that sentence to an image model, and a brief that
        # contradicts itself composes a contradictory instruction. Mechanical derivation is a
        # ceiling on quality, not a floor under it.
        #
        # But "record it and trust the agent" would re-open #621, filed days earlier, where the
        # brief's constraints never reached the prompt at all. So neither extreme: the agent writes
        # the words, and the gate still holds it to the brief's hard constraints BEFORE the spend.
        return check_crafted_prompt(request, brief, surface)
    missing = [k for k in ("style", "mood", "subject") if not brief.get(k)]
    if missing:
        raise Refusal(f"the aesthetic brief for {surface!r} is missing {', '.join(missing)}, so a "
                      f"composed prompt would be improvisation wearing a schema.")
    style = brief["style"]
    if style not in STYLES:
        raise Refusal(
            f"unknown illustration style {style!r} for {surface!r}. Pick one of: "
            f"{', '.join(STYLES)}. A free-text style is the same defect as a free-typed prompt "
            f"wearing a shorter name — it is what lets two runs against one pack drift into "
            f"different-looking art and calls the second one a reroll.")
    # THE BRIEF IS THE PER-SURFACE AUTHORITY; the pack is the default. A palette constraint that
    # varies by surface — "monochrome for the accent family, full brand colour for the hero" — has
    # nowhere to live in a pack, which is per BRAND. Reading only the pack meant a brief could state
    # its most important constraint and have it silently dropped, and the composed prompt then
    # invited exactly the output the brief forbade. Constraints are carried, not summarised.
    palette = brief.get("palette") or pack.get("palette") or []
    if isinstance(palette, str):
        palette = [palette]

    # NO PALETTE IS A REFUSAL, NOT A WORD IN THE PROMPT. This used to emit the literal string
    # `palette unspecified`, which is not a missing constraint but an INSTRUCTION — it tells a
    # generator the palette is open, and the model reasonably obliges. Absence must never be
    # narrated into a prompt that costs money; this file's own doctrine is that a vague prompt is a
    # reroll and pays twice, so the honest place to stop is before the spend.
    if not palette:
        raise Refusal(
            f"neither the brief for {surface!r} nor the pack states a `palette`, so the composed "
            f"prompt would carry no colour constraint at all. That is the one thing an illustration "
            f"model will improvise hardest — and the previous version wrote the words 'palette "
            f"unspecified' into the prompt, which reads as permission rather than as a gap.\n"
            f"  Put it in the BRIEF for this surface — `.design-flow/generation.json` → "
            f"`briefs.{surface}.palette` — which is where a per-surface constraint belongs and what "
            f"overrides everything else.\n"
            f"  Or in the plan row's `pack.palette` (`docs/assets/plan.json`), which is where the "
            f"request's `pack` actually comes from. NOT the brand pack's brand.json: nothing in this "
            f"path reads it, and saying so would send you to edit a file that cannot help.\n"
            f"  Nothing was spent.")

    parts = [
        f"{style} illustration",
        brief["subject"],
        f"{brief['mood']} mood",
        f"palette {', '.join(palette)}",
    ]
    # The remaining brief constraints, each carried VERBATIM. A deliverable ("raster line art on a
    # transparent ground") and an exclusion ("no human figures, no text") are the two the model gets
    # wrong most expensively, and both were unreachable before: the schema documented style, subject
    # and mood, so anything else a brief said was decoration.
    # #640. THE SHAPE REACHES THE PROVIDER. Without it we paid for a careful prompt -- palette,
    # ground, avoid-list -- that never said whether it wanted a 21:9 full-bleed band or a square
    # card inset, and then accepted whatever came back. Every provider honours an aspect; we passed
    # nothing.
    if brief.get("aspect"):
        parts.append(f"{brief['aspect']} aspect ratio")
    if brief.get("frame"):
        parts.append(f"composed for a {brief['frame']} frame")
    if brief.get("ground"):
        parts.append(f"on a {brief['ground']} ground")
    if brief.get("deliverable"):
        parts.append(str(brief["deliverable"]))
    avoid = brief.get("avoid")
    if avoid:
        parts.append("avoid " + (", ".join(avoid) if isinstance(avoid, list) else str(avoid)))
    if pack.get("type"):
        parts.append(f"typography {pack['type']}")
    if pack.get("endorsement"):
        parts.append(pack["endorsement"])
    return "; ".join(parts)


def pick_model(config: dict, surface: str, attempt: int, kind: str = "static") -> dict:
    """Bottom of the ladder first; climb only on a FAILED acceptance check.

    A surface with no acceptance check is pinned to the cheapest rung. That is deliberate and it is
    the whole of requirement 3: without a stated check, "climb because the output was not good
    enough" has no trigger and "best output" collapses into "the agent liked it".
    """
    # PER-KIND FIRST, then the shared ladder. A line drawing, an SVG icon and a motion loop do not
    # want the same model: only some models emit SVG at all, and none of the image endpoints emit
    # video. One global ladder forced every kind through whatever suited the most common one, and
    # the mismatch surfaced as a raster named `.svg`.
    ladders = config.get("ladders") or {}
    ladder = ladders.get(kind) or config.get("ladder") or []
    if not ladder:
        raise Refusal(f"no model ladder for kind {kind!r} in project config — neither "
                      f"`ladders.{kind}` nor a shared `ladder`. The ladder is config, not doctrine — "
                      "model names and prices change monthly and a list in doctrine rots inside a "
                      "quarter. Declare one, cheapest first.")
    if attempt > 0 and not config.get("acceptance", {}).get(surface):
        raise Refusal(
            f"cannot climb the ladder for {surface!r}: no acceptance check is stated for it, so "
            f"there is no trigger for 'the cheap model was not good enough'. Write the check down "
            f"per surface, or the cheapest rung is the only rung.")
    # AN UNPRICED RUNG IS REFUSED, never treated as free. Defaulting a missing `cost_usd` to 0 made
    # the ceiling unreachable: every unpriced model cost nothing, so the budget check could not
    # refuse anything -- a gate that cannot fail, guarding the one thing here with a bill attached.
    # The scaffold ships prices UNSET on purpose, because the provider does not expose them and an
    # invented number is worse than an absent one: it looks authoritative and is not.
    for rung in ladder:
        if rung.get("cost_usd") is None:
            raise Refusal(
                f"the ladder rung {rung.get('name', '<unnamed>')!r} has no `cost_usd`. Nothing can "
                f"be budgeted against an unpriced model, and treating it as free would make the "
                f"ceiling unreachable. Look up what this model charges and write it in — the "
                f"provider's model endpoint does not report pricing, which is why the scaffold "
                f"leaves it blank rather than guessing.")
    if attempt >= len(ladder):
        raise Refusal(f"the ladder for {surface!r} is exhausted at {len(ladder)} rung(s); climbing "
                      f"further would be spending with no rung left to justify it.")
    return ladder[attempt]


def check_budget(config: dict, spent: float, projected: float) -> None:
    """Compare BEFORE the call, and refuse. There is deliberately no warn-and-continue branch."""
    ceiling = config.get("budget_usd")
    if ceiling is None:
        raise Refusal("no `budget_usd` ceiling in project config. This path spends real money, so "
                      "an absent ceiling is refused rather than defaulted — a default ceiling is a "
                      "number nobody chose, attached to somebody's card.")
    if spent + projected > ceiling:
        raise Refusal(
            f"budget ceiling would be exceeded: ${spent:.4f} spent + ${projected:.4f} projected "
            f"> ${ceiling:.4f} ceiling. Refused before the call, which is the only useful place to "
            f"refuse it.")


def check_aggregator(config: dict) -> str:
    """Absent an aggregator, say so and stop. This is the default path, not an error path."""
    name = config.get("aggregator")
    if not name:
        raise Refusal(
            "no aggregator configured, so generation is unavailable. This is not a failure — a "
            "shipped plugin cannot depend on an MCP server or an API key being present. Satisfy the "
            "surface from tiers 1-2, or say so and stop. Never improvise, never ship a placeholder.")
    return name


def provenance_row(surface: str, kind: str, model: dict, prompt: str, pack: dict,
                   crafted: bool = False, rationale: str = "",
                   aspect: str | None = None) -> dict:
    """Model, prompt, cost, pack variant — without the prompt the asset is unreproducible.

    #629 added `crafted` and `prompt_rationale`. They travel with the provenance so the prompt
    library can record WHICH prompts the agent wrote and why. Without that column the trade this
    change makes -- agent phrasing over mechanical derivation -- could never be evaluated against
    its own results, and an unevaluatable trade is a preference wearing a decision's clothes.
    """
    return {
        "surface": surface,
        "kind": kind,
        "model": model.get("name"),
        "cost_usd": model.get("cost_usd"),
        "prompt": prompt,
        "crafted": crafted,
        "prompt_rationale": rationale,
        # Travels with the provenance so the returned bytes can be checked against what was ASKED
        # for, without the checker re-reading config and risking a different answer.
        "aspect": aspect,
        "pack_variant": pack.get("variant"),
    }


def decide(root: Path, request: dict) -> dict:
    config = load_config(root)
    check_precondition(request)
    check_library(root, request)
    kind = request.get("kind", "static")
    if kind not in KINDS:
        raise Refusal(f"unknown asset kind {kind!r}; expected one of {', '.join(KINDS)}.")
    aggregator = check_aggregator(config)
    surface = request["tier_refusal"]["surface"]
    brief = (config.get("briefs") or {}).get(surface, {})
    pack = request.get("pack") or {}
    prompt = compose_prompt(request, brief, pack)
    model = pick_model(config, surface, int(request.get("attempt", 0)), kind)
    check_budget(config, float(request.get("spent_usd", 0.0)), float(model.get("cost_usd", 0.0)))
    return {
        "approved": True,
        "aggregator": aggregator,
        "prompt": prompt,
        "provenance": provenance_row(surface, kind, model, prompt, pack,
                                     crafted="prompt" in request,
                                     rationale=str(request.get("prompt_rationale") or ""),
                                     aspect=brief.get("aspect")),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request", help="path to a JSON request, or - for stdin")
    ap.add_argument("--check-library", metavar="MANIFEST",
                    help="validate an asset manifest is usable, not merely present")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.check_library:
        problems = check_manifest(Path(args.check_library))
        for line in problems:
            print(line)
        print("manifest is usable." if not problems else f"{len(problems)} unusable entry field(s).")
        return 1 if problems else 0
    if not args.request:
        print("nothing to decide: pass --request (or --selftest)", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8")
        request = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"unusable request: {exc}", file=sys.stderr)
        return 2

    try:
        print(json.dumps(decide(Path.cwd(), request), indent=2))
        return 0
    except Refusal as why:
        print(json.dumps({"approved": False, "reason": str(why)}, indent=2))
        return 1
    except (KeyError, TypeError) as exc:
        print(f"unusable request: {exc}", file=sys.stderr)
        return 2


def check_manifest(path: Path) -> list[str]:
    """Every entry must carry every ENTRY_FIELD. Reported per field, not per entry.

    Per-field because "entry 3 is incomplete" sends someone to re-read the whole row, while
    "entry 3 has no `avoid`" is the fix. `avoid` is the field most often skipped and the one that
    matters most for a curated SET: without it the family drifts by well-meaning reuse, one
    reasonable-looking placement at a time, and nobody can point at where it went wrong.
    """
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("assets", [])
    except (OSError, ValueError) as exc:
        return [f"{path}: unreadable manifest ({exc})"]
    problems = []
    for i, entry in enumerate(entries):
        label = entry.get("name") or entry.get("file") or f"entry {i}"
        for field, why in ENTRY_FIELDS.items():
            value = entry.get(field)
            if value in (None, "", [], {}):
                problems.append(f"{label}: no `{field}` — {why}")
    return problems


def selftest() -> int:
    import tempfile

    CONFIG = {
        "aggregator": "example-aggregator",
        "budget_usd": 1.00,
        "ladder": [{"name": "cheap-model", "cost_usd": 0.01},
                   {"name": "better-model", "cost_usd": 0.40}],
        "briefs": {"marketing-hero": {"style": "minimalist-ink",
                                    "subject": "an abstract lattice", "mood": "calm"}},
        "acceptance": {},
    }
    OK_REQ = {
        "tier_refusal": {"surface": "marketing-hero",
                         "tier_1_why_not": "nothing to screenshot yet",
                         "tier_2_why_not": "geometry reads as filler at hero scale"},
        "pack": {"palette": ["#101010", "#f5f5f5"], "type": "Inter", "variant": "default"},
    }
    checks, failures = 0, []

    def run(label, config, request, expect_approved, library=None):
        nonlocal checks
        checks += 1
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".design-flow").mkdir()
            if config is not None:
                (root / CONFIG_PATH).write_text(json.dumps(config), encoding="utf-8")
            if library is not None:
                (root / "docs" / "assets").mkdir(parents=True)
                (root / "docs/assets/manifest.json").write_text(json.dumps(library), encoding="utf-8")
            try:
                decide(root, request)
                got = True
            except Refusal:
                got = False
        if got != expect_approved:
            failures.append(f"{label}: expected approved={expect_approved}, got {got}")

    run("a complete request is approved", CONFIG, OK_REQ, True)

    # THE PROMPT MUST CARRY THE BRIEF'S CONSTRAINTS, and must never NARRATE their absence.
    #
    # Reported from a live project after a real spend: a brief stating "monochrome / single-hue
    # ONLY" and "transparent ground" produced a full-colour photographic scene, because the composer
    # read only style/subject/mood plus the PACK's palette — and the shipped fidara pack had no
    # palette, so the prompt literally said `palette unspecified`. That is not a missing constraint;
    # it is an instruction, and the model obliged. Every assertion below is that failure.
    BRIEF = {"style": "minimalist-ink", "subject": "an abstract lattice", "mood": "calm"}
    REQ = OK_REQ
    prompt = compose_prompt(REQ, BRIEF, {"palette": ["#101010"]})
    check = lambda label, cond: (failures.append(label) if not cond else None)
    checks += 1
    check("a pack palette reaches the prompt", "#101010" in prompt)

    # THE REGRESSION, stated as the words that must never appear.
    checks += 1
    check("no prompt ever narrates an absent palette", "unspecified" not in prompt)

    # NO PALETTE ANYWHERE IS A REFUSAL — before the spend, not after it.
    checks += 1
    try:
        compose_prompt(REQ, BRIEF, {})
        failures.append("an unconstrained palette should be refused, not narrated")
    except Refusal as exc:
        check("...and the refusal says nothing was spent", "Nothing was spent" in str(exc))
        checks += 1
        check("...and names both places a palette may live",
              "brief" in str(exc) and "brand.json" in str(exc))
        checks += 1

    # THE BRIEF OVERRIDES THE PACK, because a palette constraint varies per SURFACE and a pack is
    # per BRAND — "monochrome for the accent family, full colour for the hero" has nowhere else to
    # live.
    mono = compose_prompt(REQ, {**BRIEF, "palette": ["monochrome single-hue only"]},
                          {"palette": ["#101010", "#f5f5f5"]})
    checks += 1
    check("the brief's palette wins over the pack's", "monochrome single-hue only" in mono)
    checks += 1
    check("...and the pack's is not also emitted", "#f5f5f5" not in mono)

    # THE DELIVERABLE AND THE EXCLUSIONS are what the model gets wrong most expensively.
    # Wrapped, because this relies on the BRIEF's palette with an empty pack: if that lookup
    # regresses, the call raises and an uncaught Refusal would abort the run and swallow every
    # failure recorded before it. A crash is not a verdict.
    try:
        full = compose_prompt(REQ, {**BRIEF, "palette": ["mono"], "ground": "transparent",
                                    "deliverable": "raster line art, 6-8 separable marks",
                                    "avoid": ["human figures", "text"]}, {})
    except Refusal:
        full = ""
    for needle, label in (("transparent ground", "the ground constraint is carried"),
                          ("6-8 separable marks", "the deliverable is carried"),
                          ("avoid human figures, text", "the exclusions are carried")):
        checks += 1
        check(label, needle in full)

    # THE REFUSAL MUST NAME LEVERS THAT EXIST. An earlier draft of it sent the reader to the brand
    # pack's `brand.json` — which NOTHING in this path reads: the request's `pack` comes from the
    # plan row (`asset_plan.py:585`, `row.get("pack", {})`). Naming a file that cannot help is the
    # #617 failure repeated, so the message is asserted rather than trusted.
    try:
        compose_prompt(REQ, BRIEF, {})
    except Refusal as exc:
        msg = str(exc)
        for needle, label in ((f"briefs.{REQ['tier_refusal']['surface']}.palette",
                               "the refusal names the brief lever, with the surface"),
                              ("plan.json", "...and the plan row's pack"),
                              ("NOT the brand pack", "...and rules OUT brand.json explicitly")):
            checks += 1
            check(label, needle in msg)

    # THE PRECONDITION. Each free tier must be ruled out explicitly -- an unstated tier is an
    # unexamined one, and both cost nothing.
    run("no tier refusal at all", CONFIG, {"pack": {}}, False)
    run("tier refusal naming no surface", CONFIG,
        {**OK_REQ, "tier_refusal": {"tier_1_why_not": "x", "tier_2_why_not": "y"}}, False)
    for tier in FREE_TIERS:
        partial = {k: v for k, v in OK_REQ["tier_refusal"].items() if k != f"tier_{tier}_why_not"}
        run(f"tier {tier} not ruled out", CONFIG, {**OK_REQ, "tier_refusal": partial}, False)

    # THE DEGRADATION (#507 criterion 7). No aggregator is the DEFAULT install, not an error.
    run("no aggregator configured", {k: v for k, v in CONFIG.items() if k != "aggregator"},
        OK_REQ, False)
    run("no config file at all", None, OK_REQ, False)

    # THE BUDGET (#507 criterion 6). The negative test that proves it refuses.
    run("projected cost exceeds the ceiling", {**CONFIG, "budget_usd": 0.005}, OK_REQ, False)
    run("already-spent pushes it over", CONFIG, {**OK_REQ, "spent_usd": 0.999}, False)
    run("no ceiling declared", {k: v for k, v in CONFIG.items() if k != "budget_usd"}, OK_REQ, False)
    # Exactly AT the ceiling is allowed; only exceeding it refuses. A gate that refuses the
    # boundary case would make the declared number unreachable and quietly mean "ceiling minus one".
    run("spending exactly to the ceiling", {**CONFIG, "budget_usd": 0.01}, OK_REQ, True)

    # #629. A CRAFTED PROMPT IS ACCEPTED, AND HELD TO THE BRIEF. This fixture used to read "a
    # free-typed prompt is rejected" and passed `"a cool robot"` -- which after the change still
    # refused, but for LENGTH, so the assertion silently stopped testing what its name claimed. A
    # fixture whose meaning changes under you is worse than one that fails.
    CRAFTED_CFG = {**CONFIG, "briefs": {"marketing-hero": {
        "style": "minimalist-ink", "subject": "an abstract lattice", "mood": "calm",
        "palette": ["monochrome, single-hue only"], "ground": "transparent",
        "avoid": ["photographic backdrops"]}}}
    GOOD = ("A minimalist-ink illustration of an abstract interlocking lattice, calm and precise, "
            "drawn strictly monochrome in a single hue on a transparent ground, six separable "
            "marks at one ink weight.")
    run("a crafted prompt honouring the brief", CRAFTED_CFG,
        {**OK_REQ, "prompt": GOOD, "prompt_rationale": "the composed one reads as a field dump"},
        True)
    # NO RATIONALE, NO CRAFTED PROMPT. Without it nobody can tell later whether crafting helped,
    # which is the only way this trade can ever be re-evaluated.
    run("a crafted prompt with no rationale", CRAFTED_CFG, {**OK_REQ, "prompt": GOOD}, False)
    run("a crafted prompt too short to be one", CRAFTED_CFG,
        {**OK_REQ, "prompt": "a cool robot", "prompt_rationale": "shorter is better"}, False)
    # THE #621 REGRESSION, as a fixture: a prompt that never mentions the brief's palette is how a
    # brief saying "monochrome, single-hue only" was answered with a full-colour photograph.
    run("a crafted prompt that drops the palette constraint", CRAFTED_CFG,
        {**OK_REQ, "prompt": ("A minimalist-ink illustration of an abstract interlocking lattice, "
                              "calm and precise, on a transparent ground, six separable marks."),
         "prompt_rationale": "tighter phrasing"}, False)
    run("a crafted prompt that drops the ground constraint", CRAFTED_CFG,
        {**OK_REQ, "prompt": ("A minimalist-ink illustration of an abstract interlocking lattice, "
                              "calm, strictly monochrome in a single hue, six separable marks."),
         "prompt_rationale": "tighter phrasing"}, False)
    # ASKING FOR WHAT THE BRIEF FORBIDS is answered exactly as asked, then rejected on arrival --
    # a full round trip and a full charge to learn what the brief already said.
    run("a crafted prompt requesting what `avoid` forbids", CRAFTED_CFG,
        {**OK_REQ, "prompt": (GOOD + " Set against rich photographic backdrops for depth."),
         "prompt_rationale": "depth helps"}, False)
    # THE STOPWORD FIXTURE. "monochrome, single-hue only" shares "only" with almost any English
    # sentence, so a check that counted common words would pass on a prompt honouring nothing --
    # a gate that cannot fail. This prompt shares ONLY the stopword and must still refuse.
    run("a crafted prompt sharing only a stopword with the palette", CRAFTED_CFG,
        {**OK_REQ, "prompt": ("A minimalist-ink illustration of an abstract interlocking lattice, "
                              "calm and precise, on a transparent ground, six separable marks and "
                              "only that."),
         "prompt_rationale": "tighter phrasing"}, False)
    # A brief with no palette/ground/avoid constrains nothing, so the check must stay SILENT rather
    # than inventing a requirement -- a gate that fires on correct input gets switched off.
    run("a crafted prompt against an unconstrained brief", CONFIG,
        {**OK_REQ, "prompt": GOOD, "prompt_rationale": "the composed one reads as a field dump"},
        True)
    run("brief missing its mood",
        {**CONFIG, "briefs": {"marketing-hero": {"style": "minimalist-ink", "subject": "x"}}},
        OK_REQ, False)
    # A brief with no STYLE is the gap the reference survey exposed: "calm, abstract" can be
    # rendered as monochrome ink or as rounded flat-vector characters, and both would pass.
    run("brief missing its style",
        {**CONFIG, "briefs": {"marketing-hero": {"subject": "x", "mood": "calm"}}}, OK_REQ, False)
    run("a style outside the taxonomy",
        {**CONFIG, "briefs": {"marketing-hero": {"style": "playful", "subject": "x",
                                                 "mood": "calm"}}}, OK_REQ, False)
    run("no brief for the surface", {**CONFIG, "briefs": {}}, OK_REQ, False)

    # AN UNPRICED RUNG IS REFUSED. Treating it as free made the ceiling unreachable.
    run("an unpriced rung is refused",
        {**CONFIG, "ladder": [{"name": "m"}]}, OK_REQ, False)
    run("...and a priced one is fine",
        {**CONFIG, "ladder": [{"name": "m", "cost_usd": 0.01}]}, OK_REQ, True)
    run("...zero is a price, not an absence",
        {**CONFIG, "ladder": [{"name": "m", "cost_usd": 0.0}]}, OK_REQ, True)

    # PER-KIND LADDERS. Only some models emit SVG, and none of the image endpoints emit video, so
    # one global ladder forced every kind through whatever suited the most common one.
    PERKIND = {**CONFIG, "ladders": {"vector": [{"name": "vector-model", "cost_usd": 0.02}]}}
    run("a kind with its own ladder uses it", PERKIND,
        {**OK_REQ, "kind": "vector",
         "library_miss": {"searched_for": "x", "why_no_fit": "y"}}, True)
    run("...and a kind with none falls back to the shared ladder", PERKIND, OK_REQ, True)
    run("...but no ladder at all for that kind refuses",
        {k: v for k, v in PERKIND.items() if k != "ladder"},
        {**OK_REQ, "kind": "motion"}, False)

    # THE LADDER. Climbing needs a stated acceptance check, or "best output" means "agent liked it".
    run("no ladder declared", {k: v for k, v in CONFIG.items() if k != "ladder"}, OK_REQ, False)
    run("climbing with no acceptance check", CONFIG, {**OK_REQ, "attempt": 1}, False)
    run("climbing WITH an acceptance check",
        {**CONFIG, "acceptance": {"marketing-hero": "reads as brand, not stock"}},
        {**OK_REQ, "attempt": 1}, True)
    run("climbing past the last rung",
        {**CONFIG, "acceptance": {"marketing-hero": "reads as brand, not stock"}},
        {**OK_REQ, "attempt": 2}, False)

    # THE LIBRARY. The cheapest asset is one that already exists, so a library that was never
    # searched is the most expensive mistake available here -- it re-buys what the project owns.
    LIB = {"assets": [{"surface": "pricing-band", "kind": "static", "file": "pricing.svg"}]}
    # pricing-band needs its own brief, or the two fixtures below refuse for a MISSING BRIEF and
    # the library logic they exist to test is never reached -- a fixture stealing another's verdict.
    CONFIG_PB = {**CONFIG, "briefs": {**CONFIG["briefs"],
                 "pricing-band": {"style": "geometric", "subject": "a tiled band",
                                  "mood": "steady"}}}
    run("a library exists but was not searched", CONFIG, OK_REQ, False, library=LIB)
    run("...searched, with a recorded miss", CONFIG,
        {**OK_REQ, "library_miss": {"searched_for": "hero lattice",
                                    "why_no_fit": "only a pricing spot exists"}},
        True, library=LIB)
    # The manifest CONTRADICTING the miss is the sharper case: the index says this surface is
    # already covered, so generating forks the look rather than filling a gap.
    run("...the manifest already covers this surface", CONFIG_PB,
        {**OK_REQ, "tier_refusal": {**OK_REQ["tier_refusal"], "surface": "pricing-band"},
         "library_miss": {"searched_for": "pricing spot", "why_no_fit": "wanted it bigger"}},
        False, library=LIB)
    # ...but a DIFFERENT kind for the same surface is a real gap: a motion accent is not the still.
    run("...a different kind for a covered surface is a real gap", CONFIG_PB,
        {**OK_REQ, "kind": "motion",
         "tier_refusal": {**OK_REQ["tier_refusal"], "surface": "pricing-band"},
         "library_miss": {"searched_for": "pricing motion", "why_no_fit": "only a still exists"}},
        True, library=LIB)
    run("an unknown asset kind", CONFIG, {**OK_REQ, "kind": "hologram"}, False)

    # PROVENANCE (#507 criterion 5). Every field, because a missing one costs a re-generation.
    checks += 1
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / CONFIG_PATH).write_text(json.dumps(CONFIG), encoding="utf-8")
        row = decide(root, OK_REQ)["provenance"]
    for field in ("surface", "model", "cost_usd", "prompt", "pack_variant"):
        if row.get(field) in (None, ""):
            failures.append(f"provenance row is missing {field!r}")
    checks += 1
    if "abstract lattice" not in row["prompt"] or "calm" not in row["prompt"]:
        failures.append("the composed prompt does not carry the brief it was derived from")

    # THE MANIFEST SCHEMA. A library entry that cannot tell an agent where the asset MAY and MAY NOT
    # go will be re-generated by whoever could not tell -- so "present" is not the bar, "usable" is.
    COMPLETE = {field: (["x"] if field == "use_cases" else "x") for field in ENTRY_FIELDS}
    def manifest_check(label, entry, expect_problem_field):
        nonlocal checks
        checks += 1
        with tempfile.TemporaryDirectory() as td:
            m = Path(td) / "manifest.json"
            m.write_text(json.dumps({"assets": [entry]}), encoding="utf-8")
            problems = check_manifest(m)
        hit = any(f"`{expect_problem_field}`" in pr for pr in problems) if expect_problem_field \
            else not problems
        if not hit:
            failures.append(f"{label}: expected {expect_problem_field or 'no problems'}, got {problems}")

    manifest_check("a complete entry is usable", COMPLETE, None)
    for field in ENTRY_FIELDS:
        manifest_check(f"an entry with no {field}",
                       {k: v for k, v in COMPLETE.items() if k != field}, field)
    # An EMPTY list is as unusable as a missing key -- `use_cases: []` says the asset has no home.
    manifest_check("an entry whose use_cases is empty", {**COMPLETE, "use_cases": []}, "use_cases")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} generation-gate assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
