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
import sys
from pathlib import Path

CONFIG_PATH = Path(".design-flow/generation.json")

# The tiers that are satisfiable WITHOUT paying anyone. Kept here rather than in config because it
# is a fact about the asset hierarchy, not a per-project preference: a screenshot is free because
# the product exists, and brand-geometric decoration is CSS/SVG built from tokens.
FREE_TIERS = (1, 2)

# A library holds more than flat pictures. `motion` is separate from `static` because it is priced,
# reviewed and REUSED differently -- a looping accent is a different artefact from the still it
# animates, and a manifest that conflates them cannot tell you whether a surface has both.
# `vector` is called out because for icons and flat shapes an SVG from a text model beats a raster:
# it scales, it diffs in review, and it recolours from tokens without being regenerated.
KINDS = ("static", "vector", "motion")

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


def compose_prompt(request: dict, brief: dict, pack: dict) -> str:
    """Derive the prompt. Never accept one from the caller — that is the whole point.

    A `prompt` key in the request is rejected rather than ignored, because silently overriding it
    would let a caller believe their text was used while it was not.
    """
    if "prompt" in request:
        raise Refusal(
            "the request carries a free-typed `prompt`. Prompts are DERIVED from surface class, the "
            "aesthetic brief for that class, and the pack — never improvised. An improvised prompt "
            "produces the stock-art look, and it pays twice, because a vague prompt is a reroll.")
    surface = request["tier_refusal"]["surface"]
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
    parts = [
        f"{style} illustration",
        brief["subject"],
        f"{brief['mood']} mood",
        f"palette {', '.join(pack.get('palette', [])) or 'unspecified'}",
    ]
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


def provenance_row(surface: str, kind: str, model: dict, prompt: str, pack: dict) -> dict:
    """Model, prompt, cost, pack variant — without the prompt the asset is unreproducible."""
    return {
        "surface": surface,
        "kind": kind,
        "model": model.get("name"),
        "cost_usd": model.get("cost_usd"),
        "prompt": prompt,
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
        "provenance": provenance_row(surface, kind, model, prompt, pack),
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

    # THE COMPOSED PROMPT. A free-typed prompt is REJECTED, not ignored -- silently dropping it
    # would let a caller believe their text was used.
    run("a free-typed prompt", CONFIG, {**OK_REQ, "prompt": "a cool robot"}, False)
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
