#!/usr/bin/env python3
"""Judge what a page NEWLY hides when its text is enlarged: WCAG 2.2 SC 1.4.4 and SC 1.4.12 (#1367).

Run:  python3 text_resize.py qa/manual-tests/text-resize.json
      python3 text_resize.py qa/manual-tests/text-resize.json --config qa/qa.config.yml
      python3 text_resize.py qa/manual-tests/text-resize.json --json
      python3 text_resize.py --schema      # what the collector must emit
      python3 text_resize.py --selftest

THE CRITERIA, verified against w3.org by doctrine-verifier on 2026-09-27 (recorded on #1367):

  * SC 1.4.4 Resize Text (AA): "Except for captions and images of text, text can be resized without
    assistive technology up to 200 percent without loss of content or functionality."
  * SC 1.4.12 Text Spacing (AA): no loss of content or functionality when line height is set to
    1.5 times the font size, spacing following paragraphs to 2 times, letter spacing to 0.12 times
    and word spacing to 0.16 times.

Understanding 1.4.4 accepts "at least one text scaling mechanism supported by user agents" and names
text-only resizing among them, so doubling the root font size is a legitimate test of the criterion.

WHY (#1367). Nothing shipped checked a page with its text enlarged. `layout_fit.py` judges what a
page hides at the size it was served; a card with a fixed height looks finished at 16px and cuts its
second paragraph in half at 32px, and every existing layer passes it.

THE BROWSER MEASURES THREE TIMES, THIS FILE COMPARES. `crawl_collector.js --text-resize` measures
each route as served (`base`), with the root font size doubled (`scaled`) and with the four SC 1.4.12
overrides applied (`spacing`), recording on BOTH axes every element whose content exceeds its box.
A finding is loss the enlargement CAUSED: an element that hides at least `min_hidden` of its
content on an axis in `scaled` or `spacing`, where the same element did not on that axis in `base`.
What was already hidden as served belongs to `layout_fit.py` -- one owner per defect.

TWO RULES PER MODE, partitioned by the computed overflow on the axis that overflowed:

  * `hidden` / `clip` -> **resize-clipped** / **spacing-clipped**: content cut off, unreachable.
  * `visible`         -> **resize-overlap** / **spacing-overlap**: content drawn outside its box, on
    top of whatever is beside or below it.
  * `auto` / `scroll` -> silent, counted. The content is still reachable by scrolling, and whether a
    scroll container shows it scrolls is `layout_fit.py`'s affordance rule, not this one.

A PAGE WHOSE TEXT DID NOT GROW IS UNVERIFIED, NEVER CLEAN. Text sized in `px` ignores the root font
size, so doubling it measures nothing -- and "no findings" over text that never changed size is a
statement about the method, not the page. The collector counts how many text-bearing elements grew
by at least 1.9x; below half of them, the `scaled` mode is reported unverified with that reason.
Browser zoom enlarges px text too, and that is what to check such a page with. Spacing is judged
regardless: its overrides apply to px text as much as to rem text.

SO IS A ROUTE THAT REDIRECTED, a mode whose probe threw (`null`), and any mode's list the collector
truncated at its cap. A clip missing from a truncated base list cannot be proven new, and one
missing from a truncated scaled or spacing list may simply have been cut from it.

KNOWN LIMIT. Elements are matched across modes by their ref (tag and first two classes, root to
leaf). Twenty identical cards share one ref, so if ANY of them clipped as served, a new clip in
another is read as pre-existing. That errs toward silence on a page that already has a
`layout_fit.py` finding for the same ref, never toward a false report.

Exit: 0 clean · 1 findings or unverified · 3 unusable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# One home each: the visually-hidden exemption, the threshold default and the `layout:` config reader
# are layout_fit's. A second copy here would drift the first time sr-only changed shape.
from layout_fit import (  # noqa: E402
    CLIPS, DEFAULT_MIN_HIDDEN, MAX_EXAMPLES, SCROLLS, Unusable, is_visually_hidden, read_config,
)

SCHEMA = "qa-flow/text-resize/1"
COLLECTOR = "crawl_collector.js"
MODES = ("scaled", "spacing")
PREFIX = {"scaled": "resize", "spacing": "spacing"}
CRITERION = {"scaled": "SC 1.4.4, text at 200%", "spacing": "SC 1.4.12, WCAG text spacing"}
# Below this share of text-bearing elements reaching 1.9x, the page did not really enlarge.
MIN_GREW_SHARE = 0.5
RULES = tuple(f"{PREFIX[m]}-{kind}" for m in MODES for kind in ("clipped", "overlap"))

_ROW = {
    "ref": "main > div.card > p", "tag": "p",
    "clientWidth": 320, "clientHeight": 96, "scrollWidth": 320, "scrollHeight": 160,
    "overflowX": "visible", "overflowY": "hidden", "clipPath": "none",
}
SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "viewport": "1280x900",
    "routes": [{
        "route": "/requests",
        "viewport": "1280x900",
        "landedOn": "/requests",
        "modes": {
            # NULL when that probe threw -- unverified, never "nothing hidden".
            "base": {"textElements": 212, "grew": 0, "truncated": False, "elements": []},
            "scaled": {"textElements": 212, "grew": 208, "truncated": False, "elements": [_ROW]},
            "spacing": {"textElements": 212, "grew": 0, "truncated": False, "elements": []},
        },
    }],
}


@dataclass
class Finding:
    rule: str
    ref: str
    detail: str
    worst_ratio: float
    count: int
    examples: list[str]


@dataclass
class Judged:
    findings: list[Finding] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    routes: int = 0
    judged: int = 0
    preexisting: int = 0       # already hidden as served: layout_fit's, not ours
    scrollable: int = 0        # reachable by scrolling, so no loss of content
    visually_hidden: int = 0
    below_threshold: int = 0
    excluded: int = 0


def load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unusable(f"{path} does not exist — run `crawl_collector.js --text-resize` first")
    except json.JSONDecodeError as err:
        raise Unusable(f"{path} is not valid JSON ({err}) — a truncated collector run is not a clean run")
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        got = doc.get("schema") if isinstance(doc, dict) else type(doc).__name__
        raise Unusable(f"{path} declares schema {got!r}, not {SCHEMA!r} — refusing to judge a "
                       "document whose shape these rules were not written for")
    if not isinstance(doc.get("routes"), list):
        raise Unusable(f"{path} has no `routes` list — nothing was measured, which is not a pass")
    return doc


def _ratios(row: dict) -> dict[str, float]:
    """Hidden fraction of the box's own content, per axis. Python computes it, not the browser."""
    out = {}
    for axis, client, scroll in (("x", "clientWidth", "scrollWidth"), ("y", "clientHeight", "scrollHeight")):
        c, s = row.get(client), row.get(scroll)
        if not isinstance(c, (int, float)) or not isinstance(s, (int, float)):
            raise Unusable(f"{row.get('ref')!r} has no numeric {client}/{scroll} — the collector's "
                           "own measurement is missing, so nothing here can be judged")
        out[axis] = (s - c) / s if s > 0 and s > c else 0.0
    return out


def _mode(entry: dict, name: str, route: str) -> dict | None:
    mode = (entry.get("modes") or {}).get(name)
    if mode is None:
        return None
    if not isinstance(mode, dict) or not isinstance(mode.get("elements"), list):
        raise Unusable(f"{route}: mode {name!r} is not an object with an `elements` list")
    return mode


def judge(doc: dict, *, min_hidden: float = DEFAULT_MIN_HIDDEN,
          exclude: list[str] | None = None) -> Judged:
    out = Judged()
    exclude = exclude or []
    grouped: dict[tuple[str, str], dict] = {}

    for entry in doc["routes"]:
        if not isinstance(entry, dict):
            raise Unusable(f"a route entry is {type(entry).__name__}, not an object")
        route = str(entry.get("route", "?"))
        out.routes += 1
        landed = entry.get("landedOn")
        if isinstance(landed, str) and landed.strip() and landed != route:
            out.unverified.append(f"{route}: measured at {landed}")
            continue
        base = _mode(entry, "base", route)
        if base is None:
            out.unverified.append(f"{route}: the as-served probe did not run")
            continue
        if base.get("truncated"):
            out.unverified.append(f"{route}: the as-served list was truncated, so no clip can be "
                                  "proven new")
            continue
        # What was already hidden as served, per axis: that is layout_fit's defect, not ours.
        served: set[tuple[str, str]] = set()
        for row in base["elements"]:
            for axis, ratio in _ratios(row).items():
                if ratio >= min_hidden:
                    served.add((str(row.get("ref")), axis))

        for name in MODES:
            mode = _mode(entry, name, route)
            if mode is None:
                out.unverified.append(f"{route} ({CRITERION[name]}): the probe did not run")
                continue
            # The collector caps each mode's list (400 rows). A clip missing from a truncated list may
            # simply have been cut from it, so the mode says nothing -- the same reason a truncated
            # base list is unverified, applied to the lists the findings actually come from.
            if mode.get("truncated"):
                out.unverified.append(f"{route} ({CRITERION[name]}): the list was truncated at the "
                                      "collector's cap, so a clip may have been cut from it")
                continue
            if name == "scaled":
                texts, grew = mode.get("textElements"), mode.get("grew")
                if not isinstance(texts, int) or not isinstance(grew, int):
                    raise Unusable(f"{route}: the scaled probe has no textElements/grew counts")
                if texts == 0:
                    out.unverified.append(f"{route} ({CRITERION[name]}): no text-bearing element")
                    continue
                if grew / texts < MIN_GREW_SHARE:
                    out.unverified.append(
                        f"{route} ({CRITERION[name]}): only {grew} of {texts} text elements grew "
                        "— text sized in px ignores the root font size; check it with browser zoom")
                    continue
            for row in mode["elements"]:
                ref = str(row.get("ref") or "(unnamed)")
                if any(token and token in ref for token in exclude):
                    out.excluded += 1
                    continue
                for axis, ratio in _ratios(row).items():
                    if ratio < min_hidden:
                        out.below_threshold += 1
                        continue
                    if (ref, axis) in served:
                        out.preexisting += 1
                        continue
                    if is_visually_hidden(row):
                        out.visually_hidden += 1
                        continue
                    overflow = str(row.get(f"overflow{axis.upper()}") or "visible").strip().lower()
                    if overflow in SCROLLS:
                        out.scrollable += 1
                        continue
                    out.judged += 1
                    # Anything not scrolling and not clipping is drawn outside its box -- including
                    # an unrecognised value, which fails toward a report rather than toward silence.
                    kind = "clipped" if overflow in CLIPS else "overlap"
                    key = (f"{PREFIX[name]}-{kind}", ref)
                    bucket = grouped.setdefault(key, {"routes": [], "ratio": 0.0, "row": row,
                                                      "axis": axis, "mode": name})
                    if route not in bucket["routes"]:
                        bucket["routes"].append(route)
                    if ratio > bucket["ratio"]:
                        bucket.update(ratio=ratio, row=row, axis=axis)

    for (rule, ref), b in grouped.items():
        row, axis = b["row"], b["axis"]
        client = row["clientWidth" if axis == "x" else "clientHeight"]
        scroll = row["scrollWidth" if axis == "x" else "scrollHeight"]
        verb = ("clips" if rule.endswith("clipped") else "draws outside its box")
        out.findings.append(Finding(
            rule=rule, ref=ref,
            detail=(f"{verb} {int(scroll - client)}px of {int(scroll)}px "
                    f"{'wide' if axis == 'x' else 'tall'} content at {CRITERION[b['mode']]}, "
                    f"which it did not as served (`overflow-{axis}: {row.get(f'overflow{axis.upper()}')}`)"),
            worst_ratio=b["ratio"], count=len(b["routes"]), examples=sorted(b["routes"])[:MAX_EXAMPLES],
        ))
    out.findings.sort(key=lambda f: (-f.worst_ratio, f.rule, f.ref))
    return out


def render(result: Judged, viewport: str) -> str:
    lines = [f"text resize @ {viewport} — {result.routes} route(s), {result.judged} newly hidden "
             "element-axis pair(s) judged"]
    if result.unverified:
        lines.append(f"UNVERIFIED — {len(result.unverified)} measurement(s) say nothing. Not a pass:")
        lines.extend(f"    {u}" for u in result.unverified[:MAX_EXAMPLES * 3])
    for f in result.findings:
        lines.append(f"[{f.rule}] {f.ref}")
        lines.append(f"    {round(f.worst_ratio * 100)}% hidden — {f.detail}")
        lines.append(f"    {f.count} route(s): {', '.join(f.examples)}")
    if not result.findings:
        lines.append("no findings.")
    lines.append(f"  {result.preexisting} already hidden as served (layout_fit's); {result.scrollable} "
                 f"reachable by scrolling; {result.visually_hidden} visually-hidden; "
                 f"{result.below_threshold} below threshold; {result.excluded} excluded by config")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge what enlarged text newly hides (WCAG 1.4.4, 1.4.12).")
    ap.add_argument("document", nargs="?", type=Path, help="text-resize.json from the collector")
    ap.add_argument("--config", type=Path, help="qa.config.yml; reads the `layout:` section")
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
        ap.error("a text-resize document is required (or --schema / --selftest)")
    try:
        doc = load(args.document)
        threshold, exclude = read_config(args.config)
        result = judge(doc, min_hidden=threshold, exclude=exclude)
    except Unusable as err:  # layout_fit's class, so its config reader's refusals land here too
        print(f"UNUSABLE: {err}", file=sys.stderr)
        return 3
    viewport = str(doc.get("viewport") or "?")
    if args.json:
        print(json.dumps({"viewport": viewport, **{k: v for k, v in result.__dict__.items() if k != "findings"},
                          "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        print(render(result, viewport))
    return 1 if (result.findings or result.unverified) else 0


# ------------------------------------------------------------------------------------ selftest

def selftest() -> int:  # noqa: PLR0915 -- a fixture list; each firing case sits beside its control
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def row(**over) -> dict:
        r = {"ref": "main > div.card > p", "tag": "p", "clientWidth": 320, "clientHeight": 96,
             "scrollWidth": 320, "scrollHeight": 96, "overflowX": "visible", "overflowY": "visible",
             "clipPath": "none"}
        r.update(over)
        return r

    def mode(*rows, texts=100, grew=0, truncated=False) -> dict:
        return {"textElements": texts, "grew": grew, "truncated": truncated, "elements": list(rows)}

    def doc(base=None, scaled=None, spacing=None, route="/r", landed=None, **extra) -> dict:
        modes = {"base": base if base is not None else mode(),
                 "scaled": scaled if scaled is not None else mode(grew=100),
                 "spacing": spacing if spacing is not None else mode()}
        modes.update(extra)
        return {"schema": SCHEMA, "viewport": "1280x900",
                "routes": [{"route": route, "viewport": "1280x900", "landedOn": landed or route,
                            "modes": modes}]}

    def rules(d) -> set[str]:
        return {f.rule for f in judge(d).findings}

    # A fixed-height box (overflow-y: hidden) that holds its text as served and cuts it at 200%.
    clip = row(overflowY="hidden", scrollHeight=160)

    # ---- THE NEGATIVE FIXTURE AND ITS CONTROL (the issue's pair) --------------------------------
    check("a fixed-height box that clips at 200% text is resize-clipped",
          rules(doc(scaled=mode(clip, grew=100))) == {"resize-clipped"}, str(rules(doc(scaled=mode(clip, grew=100)))))
    # The control: a box that grows with its text overflows nothing, so the collector records no row.
    check("...and a box that grows with its text is silent", rules(doc()) == set())

    # ---- each rule, and the partition ------------------------------------------------------------
    check("visible overflow at 200% is resize-overlap",
          rules(doc(scaled=mode(row(scrollHeight=160), grew=100))) == {"resize-overlap"})
    check("a clip under the WCAG spacing overrides is spacing-clipped",
          rules(doc(spacing=mode(clip))) == {"spacing-clipped"})
    check("visible overflow under the spacing overrides is spacing-overlap",
          rules(doc(spacing=mode(row(scrollWidth=400)))) == {"spacing-overlap"})
    check("a horizontal clip counts too, not only a vertical one",
          rules(doc(scaled=mode(row(overflowX="clip", scrollWidth=480), grew=100))) == {"resize-clipped"})
    check("content reachable by scrolling is not loss",
          rules(doc(scaled=mode(row(overflowY="auto", scrollHeight=160), grew=100))) == set())
    check("an unrecognised overflow value reports rather than falls silent",
          rules(doc(scaled=mode(row(overflowY="weird", scrollHeight=160), grew=100))) == {"resize-overlap"})

    # ---- ONE OWNER PER DEFECT: what was hidden as served is layout_fit's --------------------------
    served = doc(base=mode(clip), scaled=mode(row(overflowY="hidden", scrollHeight=300), grew=100))
    check("a clip already present as served is not reported again", rules(served) == set(),
          str(rules(served)))
    check("...and is counted, so the silence is visible", judge(served).preexisting >= 1)
    # Its control: pre-existing on the OTHER axis does not excuse a new vertical clip.
    other_axis = doc(base=mode(row(overflowX="hidden", scrollWidth=400)), scaled=mode(clip, grew=100))
    check("...but a clip on the other axis as served does not excuse a new one",
          rules(other_axis) == {"resize-clipped"}, str(rules(other_axis)))

    # ---- exemptions and threshold -------------------------------------------------------------
    sr = row(clientWidth=1, clientHeight=1, scrollWidth=200, scrollHeight=40, overflowX="hidden",
             overflowY="hidden", clipPath="inset(50%)")
    check("visually-hidden text is exempt", rules(doc(scaled=mode(sr, grew=100))) == set())
    check("a hidden strip below the threshold is silent",
          rules(doc(scaled=mode(row(overflowY="hidden", scrollHeight=99), grew=100))) == set())
    ex = judge(doc(scaled=mode(clip, grew=100)), exclude=["div.card"])
    check("a ref excluded by config is silent and counted", not ex.findings and ex.excluded == 1)

    # ---- UNVERIFIED, NEVER CLEAN ----------------------------------------------------------------
    px = judge(doc(scaled=mode(clip, texts=100, grew=10), spacing=mode(clip)))
    check("text that did not grow leaves the 200% check unverified",
          any("10 of 100" in u for u in px.unverified), str(px.unverified))
    check("...and its clips are not reported as 200% findings", "resize-clipped" not in {f.rule for f in px.findings})
    check("...while spacing is still judged on the same page",
          "spacing-clipped" in {f.rule for f in px.findings}, str([f.rule for f in px.findings]))
    check("half the text growing is enough to judge",
          rules(doc(scaled=mode(clip, texts=100, grew=50))) == {"resize-clipped"})
    check("a page with no text is unverified", bool(judge(doc(scaled=mode(texts=0, grew=0))).unverified))
    nulled = doc()
    nulled["routes"][0]["modes"]["scaled"] = None
    check("a probe that threw is unverified", any("did not run" in u for u in judge(nulled).unverified))
    nobase = doc()
    nobase["routes"][0]["modes"]["base"] = None
    check("no as-served measurement means nothing can be proven new",
          bool(judge(nobase).unverified) and not judge(nobase).findings)
    for name, crit in (("scaled", "SC 1.4.4"), ("spacing", "SC 1.4.12")):
        kw = {name: mode(clip, truncated=True, **({"grew": 100} if name == "scaled" else {}))}
        tr = judge(doc(**kw))
        check(f"a truncated {name} list is unverified, never a pass",
              any(crit in u and "truncated" in u for u in tr.unverified), str(tr.unverified))
        check(f"...and a truncated {name} list reports no finding from its partial rows",
              not any(f.rule.startswith(PREFIX[name]) for f in tr.findings), str([f.rule for f in tr.findings]))
    # The control: truncating ONE mode does not silence the other.
    ctl = judge(doc(scaled=mode(clip, grew=100), spacing=mode(truncated=True)))
    check("CONTROL: a truncated spacing list leaves the 200% check judged",
          "resize-clipped" in {f.rule for f in ctl.findings}, str([f.rule for f in ctl.findings]))
    check("a truncated as-served list is unverified",
          bool(judge(doc(base=mode(truncated=True), scaled=mode(clip, grew=100))).unverified))
    check("a route measured somewhere else is unverified",
          any("measured at /sign_in" in u for u in judge(doc(landed="/sign_in")).unverified))

    # ---- grouping --------------------------------------------------------------------------------
    two = doc(scaled=mode(clip, grew=100))
    two["routes"].append({**two["routes"][0], "route": "/s", "landedOn": "/s"})
    g = judge(two).findings
    check("one shared card on two routes is one finding with a count of 2",
          len(g) == 1 and g[0].count == 2, str([(f.rule, f.count) for f in g]))
    check("the finding says how much, at which criterion",
          bool(g) and "64px of 160px" in g[0].detail and "SC 1.4.4" in g[0].detail, g[0].detail if g else "")

    # ---- the exit code carries the verdict --------------------------------------------------------
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        def code(d) -> int:
            p = Path(tmp) / "t.json"
            p.write_text(json.dumps(d), encoding="utf-8")
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main([str(p)])
        check("a clean run exits 0", code(doc()) == 0)
        check("a finding exits 1", code(doc(scaled=mode(clip, grew=100))) == 1)
        check("an unverified run exits 1", code(doc(scaled=mode(texts=0))) == 1)
        check("a document of the wrong schema exits 3", code({"schema": "other", "routes": []}) == 3)

    # ---- THE COLLECTOR MUST EMIT WHAT THIS FILE READS, and apply the verified values --------------
    js_path = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", js_path.is_file())
    if js_path.is_file():
        js = js_path.read_text(encoding="utf-8")
        entry = SCHEMA_EXAMPLE["routes"][0]
        fields = (list(entry) + list(entry["modes"]["scaled"]) + list(_ROW))
        missing = [f for f in fields if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing, f"never emits {missing}")
        check("the collector stamps the schema tag", SCHEMA in js)
        check("the collector measures all three modes",
              all(f"measure('{m}')" in js for m in ("base", "scaled", "spacing")))
        # The measurement is the criterion: a collector that enlarged by 1.5x, or spaced by other
        # values, would produce a clean run against a test nobody verified.
        check("the collector doubles the root font size", "px * 2" in js)
        for value in ("line-height: 1.5", "letter-spacing: 0.12em", "word-spacing: 0.16em", "margin-bottom: 2em"):
            check(f"the collector applies SC 1.4.12's {value}", value in js)

    if failures:
        print(f"text_resize selftest: {len(failures)} failure(s) of {n}", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"ran {n} text-resize assertion(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
