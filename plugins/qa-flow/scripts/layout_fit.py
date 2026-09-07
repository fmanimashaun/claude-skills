#!/usr/bin/env python3
"""Judge what a page hides INSIDE the viewport, which no boundary assertion can see.

Run:  python3 layout_fit.py qa/manual-tests/layout.json
      python3 layout_fit.py qa/manual-tests/layout.json --config qa/qa.config.yml
      python3 layout_fit.py qa/manual-tests/layout.json --json
      python3 layout_fit.py --schema      # what the collector must emit
      python3 layout_fit.py --selftest

WHY (#953). A downstream app's suite reported 26 pass / 0 fail, route coverage 49/49, axe clean and
zero console errors, while a human browser review found 71-83% of every data table hidden at a phone
width, five of ten sub-tabs undiscoverable on a laptop, and a row's only action clipped mid-letter.
Every green number was true and about something else.

THE MEASUREMENT EVERY BOUNDARY ASSERTION MISSES. The usual responsive checks are

    document.documentElement.scrollWidth <= clientWidth      # the page must not scroll sideways
    el.getBoundingClientRect().right <= viewportWidth        # nothing past the viewport edge

and both PASS on the defect that caused all of the above: a page-level grid that kept a 232px rail at
a 406px viewport, so main content was crushed to 118px. Nothing crossed the viewport edge -- the
content was destroyed *inside* it. The comparison that catches it is per element and yields a
number:

    (el.scrollWidth - el.clientWidth) / el.scrollWidth       # what fraction of THIS box is hidden

That fraction is the whole point. "It overflows" is a boolean a developer can argue with; "82% of
this table is hidden" is not.

THREE RULES, PARTITIONED BY `overflow-x`, so exactly one can fire per element. Two rules for one
element would be two owners for one defect -- the failure mode this repo already records elsewhere:

  * `visible` (the default) -> **spilled-content**. The content renders on top of whatever is beside
    it. This is the case that reads as a rendering bug rather than a layout one: a card's text
    overlapping the panel next to it, words cut mid-syllable by a sibling rather than by a clip.
  * `hidden` / `clip` -> **clipped-unreachable**. Cut off with no way to reach it: no scroll, no
    drag, no keyboard. The most severe of the three even when the number is small, because 10px of
    an unreachable label is 10px nobody can ever read.
  * `auto` / `scroll` -> **scroll-without-affordance**, and only when nothing says it scrolls. The
    content is reachable in principle and invisible in practice.

THE AFFORDANCE RULE IS THE ONE THAT PAYS FOR ITSELF, and it exists because `overflow-x: auto` is
where the previous generation of this check gave up. A widely copied responsive assertion carries

    if (parent && ["auto","scroll"].includes(getComputedStyle(parent).overflowX)) return false;
    // "A scroll container is allowed to hold something wider than itself"

which is correct for "the page must not scroll" and removes an entire defect class from measurement.
On macOS, overlay scrollbars reserve NO space: `offsetHeight - clientHeight` is 0 even though the
element scrolls, so a tab strip holding 1650px in 938px looks finished. Half a section of an app was
undiscoverable for that reason, including two tabs its own dashboard linked to.

So a scroll container is silent only on EVIDENCE, of which there are three kinds and each has a
fixture proving it silences and that its absence still fires:

  * **A reserved gutter** -- `offsetHeight - clientHeight >= 3`. A classic scrollbar shows itself.
  * **`scrollbar-gutter: stable`** -- the app asked for reserved space explicitly.
  * **`data-qa-scroll-affordance`** -- the app declares an edge fade, chevrons, or whatever it drew.
    A gradient painted in a `::after` is not readable from script, so the app says so rather than
    this rule guessing. Same split as the visual masks: the browser records, Python judges, and the
    app declares what only it can know.

BROWSER MEASURES, PYTHON JUDGES. `crawl_collector.js --layout` records widths, computed overflow,
reserved gutter and the declared attribute. Every threshold and every exemption is here, which is
what lets this run in CI with no browser.

VISUALLY-HIDDEN TEXT IS EXEMPT, AND THAT WAS FOUND BY RUNNING THIS, NOT BY READING IT. The first
run against a real app reported four `clipped-unreachable` findings at 98-100% hidden, every one of
them an `.sr-only` span: screen-reader-only text is a 1x1 clipped box holding a whole sentence, so it
hides ~100% of its own content BY DESIGN and is perfectly reachable by the assistive technology it
exists for. A rule that reports the accessibility pattern as an accessibility defect is a rule that
gets switched off in a week, taking every real finding with it.

The exemption is keyed on the BOX, never a class name -- `sr-only`, `visually-hidden`, `a11y-hidden`
and every hand-rolled variant collapse to the same measurable shape, and an allowlist of names would
miss the fifth one:

  * a client box of a few pixels in either direction (a 1x1 box hiding 297px is hidden text), or
  * a `clip-path` / `clip` that hides the whole element (`inset(50%)`, `rect(0, 0, 0, 0)`).

A ROUTE THE PROBE COULD NOT MEASURE IS UNVERIFIED, NEVER CLEAN. `elements: null` means the probe
threw; `elements: []` means it ran and found nothing hidden. Those are different answers and
collapsing them is how a layer reports a pass on a page it never read.

SO IS A ROUTE THAT REDIRECTED, and this one is not hypothetical. On a signed-in crawl the
interaction sweep force-clicks every control it finds, and one of them is "Sign out": measured on a
real app, five admin routes silently degraded to the landing page after the FIRST route's sweep, and
every later measurement was filed under the route that had been asked for. `landedOn` is compared to
the route requested and a mismatch is unverified, naming both paths. A route that legitimately
redirects should be measured at its destination, which is the address a person actually gets.

ONE CRUSHED FOOTER IS ONE FINDING. Findings group by element ref with a route count and up to three
examples, because a shared table wrapper on 40 screens is one defect, and a developer handed 40 rows
stops reading.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_config  # noqa: E402 -- sibling module, one reader for qa.config.yml (#792)

SCHEMA = "qa-flow/layout-fit/1"
COLLECTOR = "crawl_collector.js"

# The document the collector must produce. ONE definition, printed by `--schema` and cross-checked
# against the shipped collector by the selftest -- separate files in separate languages, so nothing
# else stops them drifting, and a collector that quietly stops emitting a field makes the rule
# reading it go silent rather than fail.
SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "viewport": "390x844",
    "routes": [{
        "route": "/requests",
        "viewport": "390x844",
        # Where the browser actually ended up. A route that redirected was measured somewhere else,
        # and the number belongs to that somewhere else.
        "landedOn": "/requests",
        # NULL when the probe threw -- unverified, never "nothing hidden". `[]` is the clean answer.
        "elements": [{
            "ref": "div.grid > div.min-w-0 > div.overflow-x-auto",
            "tag": "div",
            "role": "table",
            "clientWidth": 364,
            # For the visually-hidden exemption: a 1x1 clipped box is sr-only text, not a defect.
            "clientHeight": 46,
            "clipPath": "none",
            "scrollWidth": 650,
            "hiddenRatio": 0.44,
            "overflowX": "auto",
            "scrollbarGutter": "auto",
            # Reserved scrollbar space. 0 under macOS overlay scrollbars even while scrolling.
            "gutterPx": 0,
            # What the app DECLARES it drew, since a pseudo-element gradient is unreadable here.
            "declaredAffordance": None,
        }],
    }],
}

# Partition of computed `overflow-x`. Every value the CSS Overflow spec allows lands in exactly one
# bucket, and an unrecognised one is reported rather than silently dropped into the mildest rule.
SPILLS = frozenset({"visible"})
CLIPS = frozenset({"hidden", "clip"})
SCROLLS = frozenset({"auto", "scroll", "overlay"})

# Below this fraction it is rounding, a 1px border, or a sub-pixel font metric -- not something a
# person can see. Counted as examined so `--json` shows the rule read them and chose not to report.
DEFAULT_MIN_HIDDEN = 0.05

# A client box this small in either direction is hidden text, not a layout defect. Tailwind's
# sr-only is exactly 1px; a few px of slack covers the hand-rolled variants without reaching
# anything a person could read.
VISUALLY_HIDDEN_PX = 4

# A clip that hides the element entirely. Both spellings, because the CSS moved: `clip-path:
# inset(50%)` is the current sr-only recipe and `clip: rect(0, 0, 0, 0)` is the one it replaced.
TOTAL_CLIPS = ("inset(50%)", "rect(0px, 0px, 0px, 0px)", "rect(0, 0, 0, 0)")

# A gutter this wide is a real scrollbar occupying real space, which is its own affordance.
# Deliberately not 1: a 1-2px value is a border or a rounding artefact, not a scrollbar.
GUTTER_IS_VISIBLE_PX = 3

MAX_EXAMPLES = 3

RULES = ("spilled-content", "clipped-unreachable", "scroll-without-affordance")


class Unusable(RuntimeError):
    """The document cannot be judged -- reported, never treated as a clean run."""


@dataclass
class Finding:
    rule: str
    ref: str
    detail: str
    worst_ratio: float
    count: int                 # DISTINCT routes affected
    examples: list[str]


@dataclass
class Judged:
    findings: list[Finding] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    redirected: list[str] = field(default_factory=list)
    routes: int = 0
    elements: int = 0          # rows the collector handed us
    judged: int = 0            # rows at or above the threshold, so actually ruled on
    below_threshold: int = 0
    excluded: int = 0
    afforded: int = 0          # scroll containers silent BECAUSE they carry an affordance
    visually_hidden: int = 0   # sr-only and friends: clipped on purpose, reachable by AT


def load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unusable(f"{path} does not exist — run `crawl_collector.js --layout` first")
    except json.JSONDecodeError as err:
        raise Unusable(f"{path} is not valid JSON ({err}) — a truncated collector run is not a "
                       "clean run")
    if not isinstance(doc, dict):
        raise Unusable(f"{path} is not an object — run `--schema` to see what the collector emits")
    if doc.get("schema") != SCHEMA:
        raise Unusable(f"{path} declares schema {doc.get('schema')!r}, not {SCHEMA!r} — refusing to "
                       "judge a document whose shape is not the one these rules were written for")
    if not isinstance(doc.get("routes"), list):
        raise Unusable(f"{path} has no `routes` list — nothing was measured, which is not a pass")
    return doc


def read_config(path: Path | None) -> tuple[float, list[str]]:
    """`min_hidden` and `exclude` from the `layout:` section, with the built-in default otherwise."""
    if path is None:
        return DEFAULT_MIN_HIDDEN, []
    section = qa_config.load_section(path, "layout")
    raw = section.get("min_hidden")
    threshold = DEFAULT_MIN_HIDDEN
    if isinstance(raw, str) and raw.strip():
        try:
            threshold = float(raw)
        except ValueError:
            raise Unusable(f"layout.min_hidden in {path} is {raw!r}, which is not a number")
        if not 0 < threshold < 1:
            raise Unusable(f"layout.min_hidden in {path} is {threshold}, which is not a fraction "
                           "between 0 and 1 — it is a ratio of a box's own content, not a pixel "
                           "count")
    exclude = section.get("exclude")
    return threshold, [str(x) for x in exclude] if isinstance(exclude, list) else []


def has_affordance(row: dict) -> bool:
    """Does anything on screen say this element scrolls? Three kinds of evidence, no guessing."""
    gutter = row.get("gutterPx")
    if isinstance(gutter, (int, float)) and gutter >= GUTTER_IS_VISIBLE_PX:
        return True
    gutter_prop = str(row.get("scrollbarGutter") or "")
    if gutter_prop.startswith("stable"):
        return True
    declared = row.get("declaredAffordance")
    return isinstance(declared, str) and declared.strip() != ""


def is_visually_hidden(row: dict) -> bool:
    """Is this the visually-hidden pattern rather than a layout defect? Keyed on the box, not a name."""
    for key in ("clientWidth", "clientHeight"):
        size = row.get(key)
        # A missing clientHeight means an older collector: fall back to the other dimension rather
        # than guessing "hidden", which would silence real findings on every stale document.
        if isinstance(size, (int, float)) and size <= VISUALLY_HIDDEN_PX:
            return True
    clip = str(row.get("clipPath") or "none").strip().lower().replace(" ", "")
    return any(clip == c.replace(" ", "").lower() for c in TOTAL_CLIPS)


def rule_for(row: dict) -> str | None:
    """Which rule owns this element, by its computed `overflow-x`. None means silent."""
    overflow = str(row.get("overflowX") or "visible").strip().lower()
    if overflow in CLIPS:
        return "clipped-unreachable"
    if overflow in SCROLLS:
        return None if has_affordance(row) else "scroll-without-affordance"
    if overflow in SPILLS:
        return "spilled-content"
    # An unrecognised value is reported as a spill rather than dropped: `overflow-x` gained values
    # before and an allowlist that fails open is how a rule stops finding anything.
    return "spilled-content"


DETAIL = {
    "spilled-content": ("renders {hidden}px of content outside its own {client}px box, on top of "
                        "whatever is beside it"),
    "clipped-unreachable": ("clips {hidden}px of its own content with `overflow-x: {overflow}` — "
                            "unreachable by scroll, drag or keyboard"),
    "scroll-without-affordance": ("scrolls to reach {hidden}px of content and nothing on screen "
                                  "says so (reserved gutter {gutter}px, "
                                  "`scrollbar-gutter: {gutter_prop}`, no "
                                  "`data-qa-scroll-affordance`)"),
}


def judge(doc: dict, *, min_hidden: float = DEFAULT_MIN_HIDDEN,
          exclude: list[str] | None = None) -> Judged:
    out = Judged()
    exclude = exclude or []
    # rule -> ref -> {routes, worst row}
    grouped: dict[tuple[str, str], dict] = {}

    for entry in doc["routes"]:
        if not isinstance(entry, dict):
            raise Unusable(f"a route entry is {type(entry).__name__}, not an object")
        route = str(entry.get("route", "?"))
        out.routes += 1
        landed = entry.get("landedOn")
        if isinstance(landed, str) and landed.strip() and landed != route:
            # Named in full: "/requests measured at /" is the whole diagnosis, and a bare
            # "unverified" would send someone looking for a defect on the wrong page.
            out.redirected.append(f"{route} measured at {landed}")
            continue
        rows = entry.get("elements")
        if rows is None:
            out.unverified.append(route)
            continue
        if not isinstance(rows, list):
            raise Unusable(f"{route}: `elements` is {type(rows).__name__}, not a list or null")
        for row in rows:
            if not isinstance(row, dict):
                raise Unusable(f"{route}: an element row is {type(row).__name__}, not an object")
            out.elements += 1
            ref = str(row.get("ref") or "(unnamed)")
            if any(token and token in ref for token in exclude):
                out.excluded += 1
                continue
            ratio = row.get("hiddenRatio")
            if not isinstance(ratio, (int, float)):
                raise Unusable(f"{route}: {ref} has no numeric hiddenRatio — the collector's own "
                               "measurement is missing, so nothing here can be judged")
            if ratio < min_hidden:
                out.below_threshold += 1
                continue
            if is_visually_hidden(row):
                out.visually_hidden += 1
                continue
            out.judged += 1
            rule = rule_for(row)
            if rule is None:
                out.afforded += 1
                continue
            key = (rule, ref)
            bucket = grouped.setdefault(key, {"routes": [], "worst": row})
            if route not in bucket["routes"]:
                bucket["routes"].append(route)
            if float(ratio) > float(bucket["worst"].get("hiddenRatio") or 0):
                bucket["worst"] = row

    for (rule, ref), bucket in grouped.items():
        row = bucket["worst"]
        client = int(row.get("clientWidth") or 0)
        scroll = int(row.get("scrollWidth") or 0)
        detail = DETAIL[rule].format(
            hidden=scroll - client,
            client=client,
            overflow=str(row.get("overflowX") or "?"),
            gutter=row.get("gutterPx"),
            gutter_prop=row.get("scrollbarGutter") or "?",
        )
        out.findings.append(Finding(
            rule=rule,
            ref=ref,
            detail=detail,
            worst_ratio=float(row.get("hiddenRatio") or 0),
            count=len(bucket["routes"]),
            examples=sorted(bucket["routes"])[:MAX_EXAMPLES],
        ))

    # Worst first: the fraction is the ranking, which is the reason it is measured at all.
    out.findings.sort(key=lambda f: (-f.worst_ratio, f.rule, f.ref))
    return out


def render(result: Judged, viewport: str) -> str:
    lines = [f"layout fit @ {viewport} — {result.routes} route(s), {result.elements} element(s) "
             f"recorded, {result.judged} judged"]
    if result.unverified:
        lines.append(f"UNVERIFIED — the probe did not run on {len(result.unverified)} route(s): "
                     f"{', '.join(result.unverified[:MAX_EXAMPLES])}. Not a pass.")
    if result.redirected:
        lines.append(f"UNVERIFIED — {len(result.redirected)} route(s) were measured somewhere else: "
                     f"{'; '.join(result.redirected[:MAX_EXAMPLES])}. On a signed-in crawl this is "
                     "usually the sweep having clicked sign-out. Not a pass.")
    for f in result.findings:
        lines.append(f"[{f.rule}] {f.ref}")
        lines.append(f"    {round(f.worst_ratio * 100)}% hidden — {f.detail}")
        lines.append(f"    {f.count} route(s): {', '.join(f.examples)}")
    if not result.findings:
        lines.append("no findings.")
    lines.append(f"  {result.below_threshold} below the {DEFAULT_MIN_HIDDEN:.0%} threshold; "
                 f"{result.visually_hidden} visually-hidden; "
                 f"{result.afforded} scroll container(s) silent on a declared affordance; "
                 f"{result.excluded} excluded by config")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge what a page hides inside the viewport.")
    ap.add_argument("document", nargs="?", type=Path, help="layout.json from the collector")
    ap.add_argument("--config", type=Path, help="qa.config.yml, for the `layout:` section")
    ap.add_argument("--min-hidden", type=float, help="override the fraction below which a hidden "
                                                     "strip is not reported")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--schema", action="store_true", help="print what the collector must emit")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if args.document is None:
        ap.error("a layout document is required (or --schema / --selftest)")

    try:
        doc = load(args.document)
        threshold, exclude = read_config(args.config)
        if args.min_hidden is not None:
            threshold = args.min_hidden
        result = judge(doc, min_hidden=threshold, exclude=exclude)
    except Unusable as err:
        print(f"UNUSABLE: {err}", file=sys.stderr)
        return 3

    viewport = str(doc.get("viewport") or "?")
    if args.json:
        print(json.dumps({
            "viewport": viewport,
            "routes": result.routes,
            "elements": result.elements,
            "judged": result.judged,
            "below_threshold": result.below_threshold,
            "afforded": result.afforded,
            "visually_hidden": result.visually_hidden,
            "excluded": result.excluded,
            "unverified": result.unverified,
            "redirected": result.redirected,
            "findings": [f.__dict__ for f in result.findings],
        }, indent=2))
    else:
        print(render(result, viewport))

    # Unverified fails too: a route the probe never measured, or measured elsewhere, is not a route
    # that passed.
    return 1 if (result.findings or result.unverified or result.redirected) else 0


def selftest() -> int:
    import re
    import tempfile

    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def row(**over) -> dict:
        base = {"ref": "div.wrap > div.box", "tag": "div", "role": None,
                "clientWidth": 364, "clientHeight": 46, "clipPath": "none",
                "scrollWidth": 650, "hiddenRatio": 0.44,
                "overflowX": "visible", "scrollbarGutter": "auto", "gutterPx": 0,
                "declaredAffordance": None}
        base.update(over)
        return base

    def doc(*rows, route="/requests", landed=None) -> dict:
        return {"schema": SCHEMA, "viewport": "390x844",
                "routes": [{"route": route, "viewport": "390x844",
                            "landedOn": landed if landed is not None else route,
                            "elements": list(rows)}]}

    def rules(*rows, **kw) -> set[str]:
        return {f.rule for f in judge(doc(*rows), **kw).findings}

    # ---- the partition: exactly one rule per element, chosen by overflow-x ---------------------
    check("visible overflow spills", rules(row(overflowX="visible")) == {"spilled-content"},
          f"{rules(row(overflowX='visible'))}")
    check("an absent overflow value defaults to a spill",
          rules(row(overflowX=None)) == {"spilled-content"}, f"{rules(row(overflowX=None))}")
    check("hidden overflow is unreachable",
          rules(row(overflowX="hidden")) == {"clipped-unreachable"},
          f"{rules(row(overflowX='hidden'))}")
    check("clip is the same defect as hidden",
          rules(row(overflowX="clip")) == {"clipped-unreachable"},
          f"{rules(row(overflowX='clip'))}")
    check("auto with no affordance is reported",
          rules(row(overflowX="auto")) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='auto'))}")
    check("scroll with no affordance is reported",
          rules(row(overflowX="scroll")) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='scroll'))}")
    # A value nobody anticipated must not land in silence.
    check("an unknown overflow value is still reported",
          rules(row(overflowX="future-value")) != set(), "silent on an unrecognised value")
    # ONE element, ONE rule -- two would be two owners for one defect.
    for value in ("visible", "hidden", "clip", "auto", "scroll"):
        got = judge(doc(row(overflowX=value))).findings
        check(f"{value} produces exactly one finding", len(got) <= 1, f"{[f.rule for f in got]}")

    # ---- THE AFFORDANCE EXEMPTION, in both directions ------------------------------------------
    # THE DEFECT: macOS overlay scrollbars reserve nothing, so the strip looks finished.
    check("a scrolling strip with no reserved gutter is reported",
          rules(row(overflowX="auto", gutterPx=0)) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='auto', gutterPx=0))}")
    # THE THREE KINDS OF EVIDENCE, each silent -- and each fixture still CONTAINS a scrolling
    # element hiding 44%, or it would prove silence for the wrong reason.
    check("a reserved gutter is an affordance",
          rules(row(overflowX="auto", gutterPx=15)) == set(),
          f"{rules(row(overflowX='auto', gutterPx=15))}")
    check("scrollbar-gutter: stable is an affordance",
          rules(row(overflowX="auto", scrollbarGutter="stable")) == set(),
          f"{rules(row(overflowX='auto', scrollbarGutter='stable'))}")
    check("scrollbar-gutter: stable both-edges is an affordance",
          rules(row(overflowX="auto", scrollbarGutter="stable both-edges")) == set(),
          f"{rules(row(overflowX='auto', scrollbarGutter='stable both-edges'))}")
    check("a declared affordance silences it",
          rules(row(overflowX="auto", declaredAffordance="edge-fade")) == set(),
          f"{rules(row(overflowX='auto', declaredAffordance='edge-fade'))}")
    # NEAR MISSES on the exemption: an empty or whitespace attribute is a claim with nothing behind
    # it, and a 1-2px gutter is a border, not a scrollbar.
    check("an empty declared affordance does not silence it",
          rules(row(overflowX="auto", declaredAffordance="")) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='auto', declaredAffordance=''))}")
    check("a whitespace declared affordance does not silence it",
          rules(row(overflowX="auto", declaredAffordance="   ")) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='auto', declaredAffordance='   '))}")
    check("a 2px gutter is a border, not a scrollbar",
          rules(row(overflowX="auto", gutterPx=2)) == {"scroll-without-affordance"},
          f"{rules(row(overflowX='auto', gutterPx=2))}")
    # And the exemption must NOT leak to the other two rules: a clipped box cannot be excused by a
    # gutter, because nothing about a scrollbar makes clipped content reachable.
    check("a gutter does not excuse clipping",
          rules(row(overflowX="hidden", gutterPx=15)) == {"clipped-unreachable"},
          f"{rules(row(overflowX='hidden', gutterPx=15))}")
    check("a declared affordance does not excuse a spill",
          rules(row(overflowX="visible", declaredAffordance="edge-fade")) == {"spilled-content"},
          f"{rules(row(overflowX='visible', declaredAffordance='edge-fade'))}")

    # ---- THE VISUALLY-HIDDEN EXEMPTION, found by running this against a real app ---------------
    # THE FALSE POSITIVE, exactly as it came back: an sr-only span clipping a whole sentence.
    sr_only = row(ref="a.flex > span.sr-only", overflowX="hidden", clientWidth=1,
                  clientHeight=1, clipPath="rect(0px, 0px, 0px, 0px)",
                  scrollWidth=297, hiddenRatio=0.997)
    check("sr-only text is not a clipped-content finding", rules(sr_only) == set(), f"{rules(sr_only)}")
    # Each half of the signature alone is enough -- variants set one or the other.
    check("a 1px-wide box alone is visually hidden",
          rules(row(overflowX="hidden", clientWidth=1, clipPath="none")) == set(),
          "a 1px box was reported")
    check("a 1px-tall box alone is visually hidden",
          rules(row(overflowX="hidden", clientHeight=1, clipPath="none")) == set(),
          "a 1px-tall box was reported")
    check("clip-path: inset(50%) alone is visually hidden (Tailwind v4)",
          rules(row(overflowX="hidden", clipPath="inset(50%)")) == set(),
          "an inset(50%) clip was reported")
    # NEAR MISSES. The exemption must not swallow an ordinary box, must not be defeated by
    # whitespace or case in the computed value, and must not fire on a clip that hides nothing.
    check("an ordinary box is still reported",
          rules(row(overflowX="hidden", clientWidth=364, clientHeight=46)) ==
          {"clipped-unreachable"}, f"{rules(row(overflowX='hidden'))}")
    check("a partial clip is not a total one",
          rules(row(overflowX="hidden", clipPath="inset(10%)")) == {"clipped-unreachable"},
          "inset(10%) silenced a real finding")
    check("a 5px box is above the visually-hidden floor",
          rules(row(overflowX="hidden", clientWidth=5, clientHeight=5)) ==
          {"clipped-unreachable"}, "a 5px box was exempted")
    check("the clip comparison ignores spacing",
          rules(row(overflowX="hidden", clipPath="rect(0, 0, 0, 0)")) == set(),
          "an unspaced clip spelling was not recognised")
    # A document from an older collector has no clientHeight and no clipPath. It must still judge
    # on what it has rather than exempting everything, which would be a silent pass.
    legacy = {"ref": "div.box", "clientWidth": 364, "scrollWidth": 650, "hiddenRatio": 0.44,
              "overflowX": "hidden", "gutterPx": 0}
    check("a document with no clientHeight still fires",
          rules(legacy) == {"clipped-unreachable"}, f"{rules(legacy)}")
    counted = judge(doc(sr_only))
    check("an exempted row is counted, not silently dropped",
          counted.visually_hidden == 1 and counted.judged == 0,
          f"visually_hidden={counted.visually_hidden} judged={counted.judged}")

    # ---- the threshold ------------------------------------------------------------------------
    check("a 1% strip is rounding, not a finding", rules(row(hiddenRatio=0.01)) == set(),
          f"{rules(row(hiddenRatio=0.01))}")
    check("the threshold is inclusive at its own value",
          rules(row(hiddenRatio=DEFAULT_MIN_HIDDEN)) == {"spilled-content"},
          f"{rules(row(hiddenRatio=DEFAULT_MIN_HIDDEN))}")
    check("a threshold override reports what the default would not",
          rules(row(hiddenRatio=0.01), min_hidden=0.005) == {"spilled-content"},
          f"{rules(row(hiddenRatio=0.01), min_hidden=0.005)}")
    below = judge(doc(row(hiddenRatio=0.01)))
    check("a below-threshold row is counted as examined, not ignored",
          below.below_threshold == 1 and below.elements == 1,
          f"below={below.below_threshold} elements={below.elements}")

    # ---- grouping: one shared wrapper is one finding -------------------------------------------
    many = {"schema": SCHEMA, "viewport": "390x844", "routes": [
        {"route": f"/r{i}", "viewport": "390x844", "elements": [row()]} for i in range(40)]}
    grouped = judge(many).findings
    check("one wrapper on forty routes is one finding", len(grouped) == 1, f"{len(grouped)}")
    check("...carrying the route count", grouped and grouped[0].count == 40,
          f"{grouped[0].count if grouped else 'none'}")
    check("...and at most three examples", grouped and len(grouped[0].examples) == MAX_EXAMPLES,
          f"{grouped[0].examples if grouped else 'none'}")
    # Two different elements are two findings, or the grouping would swallow the second defect.
    two = judge(doc(row(ref="a"), row(ref="b"))).findings
    check("two distinct refs are two findings", len(two) == 2, f"{len(two)}")

    # ---- the worst ratio survives grouping, because it is the ranking --------------------------
    mixed = {"schema": SCHEMA, "viewport": "390x844", "routes": [
        {"route": "/a", "viewport": "390x844", "elements": [row(hiddenRatio=0.20)]},
        {"route": "/b", "viewport": "390x844", "elements": [row(hiddenRatio=0.82)]}]}
    worst = judge(mixed).findings
    check("grouping keeps the WORST ratio", worst and abs(worst[0].worst_ratio - 0.82) < 1e-9,
          f"{worst[0].worst_ratio if worst else 'none'}")
    order = judge(doc(row(ref="mild", hiddenRatio=0.10),
                      row(ref="severe", hiddenRatio=0.80))).findings
    check("findings are worst-first", [f.ref for f in order] == ["severe", "mild"],
          f"{[f.ref for f in order]}")

    # ---- config exclusion, both directions -----------------------------------------------------
    check("an excluded ref is silent", rules(row(ref="div.third-party > iframe"),
                                             exclude=["third-party"]) == set(),
          "exclusion did not apply")
    check("...and an unrelated ref still fires",
          rules(row(ref="div.wrap > div.box"), exclude=["third-party"]) == {"spilled-content"},
          "exclusion swallowed an unrelated element")
    check("an empty exclusion token does not match everything",
          rules(row(), exclude=[""]) == {"spilled-content"}, "an empty token silenced a finding")

    # ---- AN UNUSABLE DOCUMENT IS NOT A CLEAN ONE -----------------------------------------------
    null_probe = {"schema": SCHEMA, "viewport": "390x844",
                  "routes": [{"route": "/x", "viewport": "390x844", "elements": None}]}
    unver = judge(null_probe)
    check("a null probe is unverified, not clean",
          unver.unverified == ["/x"] and unver.findings == [], f"{unver}")
    check("an empty list IS clean, and is a different answer from null",
          judge(doc()).unverified == [], "an empty element list was reported unverified")

    # THE SILENT DEGRADATION, exactly as it was measured: the sweep clicked sign-out and every
    # later route was filed under the route asked for while showing the landing page.
    signed_out = judge(doc(row(), route="/requests", landed="/"))
    check("a route measured somewhere else is unverified",
          signed_out.redirected == ["/requests measured at /"] and signed_out.findings == [],
          f"{signed_out}")
    check("...and arriving where you asked is silent",
          judge(doc(row(), route="/requests", landed="/requests")).redirected == [],
          "an honest arrival was reported as a redirect")
    # A document from a collector that does not record it must still be judged, not all-unverified.
    no_landing = {"schema": SCHEMA, "viewport": "390x844",
                  "routes": [{"route": "/requests", "elements": [row()]}]}
    check("a document with no landedOn is still judged",
          judge(no_landing).redirected == [] and len(judge(no_landing).findings) == 1,
          f"{judge(no_landing)}")

    for label, body in (("not json", "{["),
                        ("not an object", "[]"),
                        ("wrong schema", json.dumps({"schema": "qa-flow/other/1", "routes": []})),
                        ("no routes list", json.dumps({"schema": SCHEMA}))):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "layout.json"
            p.write_text(body, encoding="utf-8")
            try:
                load(p)
                check(f"{label} is refused", False, "load() accepted it")
            except Unusable:
                check(f"{label} is refused", True)
    try:
        load(Path("/nonexistent/layout.json"))
        check("a missing document is refused", False, "load() accepted it")
    except Unusable:
        check("a missing document is refused", True)
    # A row with no measurement must be refused rather than treated as 0% hidden.
    try:
        judge(doc(row(hiddenRatio=None)))
        check("a row with no hiddenRatio is refused", False, "judge() accepted it")
    except Unusable:
        check("a row with no hiddenRatio is refused", True)

    # ---- the exit code carries the verdict ------------------------------------------------------
    # stdout swallowed: these assert the CODE, and four rendered reports in the middle of a
    # selftest's output is how a real failure line gets scrolled past.
    import contextlib
    import io as _io

    def code(args: list[str]) -> int:
        with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
            return main(args)

    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.json"
        clean.write_text(json.dumps(doc()), encoding="utf-8")
        check("a clean run exits 0", code([str(clean)]) == 0)
        dirty = Path(tmp) / "dirty.json"
        dirty.write_text(json.dumps(doc(row())), encoding="utf-8")
        check("a finding exits 1", code([str(dirty)]) == 1)
        unusable = Path(tmp) / "bad.json"
        unusable.write_text("{[", encoding="utf-8")
        check("an unusable document exits 3", code([str(unusable)]) == 3)
        # UNVERIFIED MUST FAIL TOO, or a probe that never ran reads as a pass.
        nulled = Path(tmp) / "null.json"
        nulled.write_text(json.dumps(null_probe), encoding="utf-8")
        check("an unverified route exits 1", code([str(nulled)]) == 1)

    # ---- THE COLLECTOR MUST EMIT EVERY FIELD THIS SCHEMA DECLARES ------------------------------
    # Object shorthand counts: `{ route, viewport }` is the same as `route: route`.
    collector = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", collector.is_file(), f"{collector} is missing")
    if collector.is_file():
        js = collector.read_text(encoding="utf-8")
        fields = list(SCHEMA_EXAMPLE["routes"][0]) + list(SCHEMA_EXAMPLE["routes"][0]["elements"][0])
        missing = [f for f in fields if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing,
              f"{COLLECTOR} never emits {missing} — the rule reading it would go quiet")
        check("the collector stamps the schema tag", SCHEMA in js, f"{SCHEMA} absent")
        # The measurement itself, not merely the field name: a collector that stopped subtracting
        # would emit a hiddenRatio of 0 forever and every rule here would go silent on real defects.
        check("the collector computes the hidden fraction",
              "scrollWidth - clientWidth" in js or "hidden / scrollWidth" in js,
              f"{COLLECTOR} no longer derives hiddenRatio from the two widths")
        # And the viewport must be settable, or nothing measured here can ever be a phone.
        check("the collector takes a --viewport", "arg('viewport'" in js,
              f"{COLLECTOR} pins the viewport again, so a phone width is unreachable")
        # Without these two the visually-hidden exemption cannot fire and every sr-only span on
        # every page comes back as a finding -- the state this layer was in on its first real run.
        check("the collector records the visually-hidden signature",
              "clientHeight:" in js and "clipPath:" in js,
              f"{COLLECTOR} stopped recording clientHeight/clipPath, so sr-only text reads as a defect")
        # And authenticated routes must stay reachable, or the layer measures sign-in pages.
        check("the collector records where it landed", "landedOn:" in js,
              f"{COLLECTOR} stopped recording landedOn, so a signed-out crawl reads as clean")
        check("the collector takes a --storage-state", "arg('storage-state'" in js,
              f"{COLLECTOR} cannot carry a session, so every authenticated route is measured as its "
              "sign-in page")

    if failures:
        print(f"layout_fit selftest: {len(failures)} failure(s) of {n}", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"ran {n} layout-fit assertion(s)")
    print("every rule fires on a violation and stays silent on an afforded, excluded or "
          "sub-threshold one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
