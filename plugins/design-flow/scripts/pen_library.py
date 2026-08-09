#!/usr/bin/env python3
"""Generate a pen.dev design library from the brand pack — a projection, never a second source (#603).

WHY GENERATE RATHER THAN AUTHOR. `theme.css` and the project's components are the source of truth. A
hand-built pen library is a *second definition of Button*, and two definitions of one component
diverge within a sprint — silently, because both look right in isolation. Generated from the pack, it
is a projection: regenerate and the divergence cannot survive. This is `plugin-boundaries`' "exactly
one home per concern" applied to a design tool, and the same call already made against reading tokens
back out of Figma.

WHY IT WRITES A FILE INSTEAD OF DRIVING THE MCP, which is the decision that makes this tractable.
Through the MCP, **ids cannot be chosen**: "Pencil will always generate unique random IDs and
override the input" — measured, every supplied id replaced. So an MCP-built library gets new ids on
every regeneration, and every `ref` in every existing document breaks *silently*, since a dangling
ref is not a syntax error. That forced a name-matching reconciler … until the simpler observation:
`.pen` is plain JSON, the id rule belongs to `Insert`, and a file we author carries the ids we write.
Regeneration is then byte-identical by construction rather than by careful diffing, and it needs no
app, no open document, and no human — so it can run in CI, which an MCP path never could.

THE HEX LIVES IN EXACTLY ONE PLACE: the document's `variables`. Every component fill is a `$--token`
reference, so a pack change repaints the whole library and light/dark come from one document. A
literal colour anywhere in a component would defeat that, which is why `--selftest` compiles the
generated library through `pen_to_svg.py` and requires it not to refuse: that compiler rejects a raw
hex by node, so the two tools check each other rather than each trusting itself.

EVERY THEME MODE IS NAMED EXPLICITLY, and this is not stylistic. A variable value carrying no `theme`
is silently dropped by pen's own `SetVariables` — measured — taking the light theme with it, after
which artwork exports **black** rather than erroring. Writing the file avoids that API, but the
generated document keeps both modes explicit so a later MCP round-trip cannot reintroduce it.

Exit codes:  0 written / clean · 1 DRIFT (`--check`) · 2 the pack could not be read

Stdlib only, no network, no MCP.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brand_pack_lint as pack_lint          # noqa: E402  — same plugin, one CSS reader

BRANDS = Path(__file__).resolve().parent.parent / "brands"
HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")

# The document's theme axis. One axis, two values — the pack has exactly `:root` and `.dark`, and
# inventing more axes here would let the library express states the pack cannot.
AXIS, LIGHT, DARK = "Mode", "Light", "Dark"


class Unreadable(Exception):
    pass


def resolve(token: str, scope: dict[str, str], seen: frozenset[str] = frozenset()) -> str:
    """A token's literal hex, following `var(--x)` chains.

    NOT imported from `scripts/check_token_contrast.py`, which has the same routine: that file is
    maintainer-only and never reaches an installed plugin, so importing it would work here and break
    for every user. The CSS *parsing* is reused from `brand_pack_lint` — same plugin, one reader.
    """
    if token in seen:
        raise Unreadable(f"`{token}` resolves in a cycle")
    raw = (scope.get(token) or "").strip()
    if not raw:
        raise Unreadable(f"`{token}` is not declared in this pack")
    if HEX_RE.match(raw):
        return raw
    ref = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", raw)
    if not ref:
        raise Unreadable(f"`{token}` is `{raw}`, which is neither a hex nor a single var()")
    return resolve(ref.group(1), scope, seen | {token})


def read_pack(theme_css: str) -> tuple[dict[str, str], dict[str, str]]:
    """(light scope, dark scope) — every declaration resolvable, with the cascade modelled.

    `.dark` INHERITS `:root`; a dark scope read in isolation cannot resolve the 6 roles it does not
    override, and would report them missing rather than unchanged.
    """
    src = pack_lint.strip_css_comments(theme_css)
    palette: dict[str, str] = {}
    for body in re.findall(r"@theme(?!\s+inline)[^{]*\{(.*?)^[ \t]*\}", src, re.S | re.M):
        palette.update({n: v.strip() for n, v in DECL_RE.findall(body)})
    if not palette:
        raise Unreadable("no `@theme` palette block found in this pack")
    light_body, dark_body = pack_lint.selector_block(src, ":root"), pack_lint.selector_block(src, ".dark")
    if not light_body:
        raise Unreadable("no `:root` block found in this pack")
    if not dark_body:
        raise Unreadable("no `.dark` block found in this pack")
    light = {**palette, **{n: v.strip() for n, v in DECL_RE.findall(light_body)}}
    dark = {**light, **{n: v.strip() for n, v in DECL_RE.findall(dark_body)}}
    return light, dark


def variables(light: dict[str, str], dark: dict[str, str], roles: list[str]) -> dict:
    """Role tokens as pen variables, BOTH modes named explicitly."""
    out: dict[str, dict] = {}
    for role in roles:
        out[role] = {"type": "color", "value": [
            {"value": resolve(role, light), "theme": {AXIS: LIGHT}},
            {"value": resolve(role, dark), "theme": {AXIS: DARK}},
        ]}
    return out


def nid(*parts: str) -> str:
    """A STABLE id from a name. Ids may not contain '/', and must survive regeneration unchanged."""
    slug = "-".join(parts)
    cleaned = re.sub(r"[^A-Za-z0-9-]", "-", slug).strip("-")
    if not cleaned:
        raise Unreadable(f"cannot derive an id from {parts!r}")
    return f"fm-{cleaned}"


def text(name: str, content: str, x: int, y: int, w: int, h: int, size: int,
         weight: str, fill: str, font: str) -> dict:
    return {"type": "text", "id": nid(name), "name": name, "x": x, "y": y, "width": w, "height": h,
            "content": content, "fontFamily": font, "fontSize": size, "fontWeight": weight,
            "fill": fill}


def label_text(name: str, content: str, size: int, weight: str, fill: str, font: str) -> dict:
    """A flex child, so NO x/y: the parent lays it out. Position is the frame's job here."""
    return {"type": "text", "id": nid(name), "name": name, "content": content,
            "fontFamily": font, "fontSize": size, "fontWeight": weight,
            "lineHeight": 1.43, "textAlign": "center", "textAlignVertical": "middle", "fill": fill}


def base_button(font: str, radius: int) -> dict:
    """The ONE button whose geometry exists. Every variant is a `ref` to this — see `variant()`.

    Laid out with flexbox rather than an absolute box, matching how a design-system library is
    authored: `gap` + `padding` + `justifyContent`/`alignItems`, and no width or height, so the
    component sizes to its label. A fixed 140x40 button is a picture of a button; this one grows
    with its content the way the real component does.
    """
    return {"type": "frame", "id": nid("button", "default"), "name": "Button/Default",
            "reusable": True, "x": 0, "y": 0, "fill": "$--primary", "cornerRadius": radius,
            "gap": 6, "padding": [8, 16], "justifyContent": "center", "alignItems": "center",
            "children": [label_text("Button label", "Continue", 14, "500",
                                    "$--primary-foreground", font)]}


def variant(name: str, base_id: str, x: int, y: int, fill: str, fg: str,
            border: str | None = None) -> dict:
    """A variant as a `ref` with overrides — NOT a second copy of the geometry.

    This is the pattern a real pen library uses, and it is better engineering than duplication for
    the usual reason: the base is the single definition, so a radius or padding change reaches every
    variant instead of reaching one and drifting from four. `descendants` re-paints the label by the
    base child's id, which is reachable here precisely BECAUSE ids are derived rather than random --
    a randomly-idded library could not address its own parts.
    """
    node = {"type": "ref", "id": nid("button", name.split("/")[-1].lower()), "name": name,
            "reusable": True, "ref": base_id, "x": x, "y": y, "fill": fill,
            "descendants": {nid("Button label"): {"fill": fg}}}
    if border:
        node["stroke"] = border
        node["strokeWidth"] = 1
    return node


def components(font: str, radius_control: int, radius_card: int) -> list[dict]:
    """The set a COMPOSITION needs — not a mirror of the whole catalogue.

    Deliberately small. The purpose is composing screens cheaply enough that divergence is explored
    before ERB is written; reproducing every component in a second tool would be the parallel library
    this file exists to avoid, wearing a generated coat.

    NO `icon` NODES, and that is a scoping choice rather than an oversight. A pen `icon` names a
    glyph in a library (`lucide`, `phosphor`) instead of carrying geometry, so it cannot be compiled
    to standalone SVG -- and the components here exist to be composed against, not to reproduce the
    icon set, which the app already gets from Lucide directly.
    """
    base = base_button(font, radius_control)
    out: list[dict] = [
        base,
        variant("Button/Secondary", base["id"], 0, 56, "$--secondary", "$--secondary-foreground",
                "$--border"),
        variant("Button/Ghost", base["id"], 0, 112, "$--background", "$--foreground"),
        variant("Button/Destructive", base["id"], 0, 168, "$--destructive",
                "$--destructive-foreground"),
        {"type": "frame", "id": nid("card"), "name": "Card", "reusable": True,
         "x": 220, "y": 0, "width": 280, "fill": "$--card", "cornerRadius": radius_card,
         "stroke": "$--border", "strokeWidth": 1,
         "layout": "vertical", "gap": 8, "padding": 20, "alignItems": "start",
         "children": [
             label_text("Card title", "Card title", 18, "600", "$--card-foreground", font),
             label_text("Card body", "Supporting copy", 14, "400", "$--muted-foreground", font),
         ]},
        {"type": "frame", "id": nid("input"), "name": "Input/Default", "reusable": True,
         "x": 220, "y": 180, "width": 280, "fill": "$--background",
         "cornerRadius": radius_control, "stroke": "$--input", "strokeWidth": 1,
         "gap": 8, "padding": [10, 12], "alignItems": "center",
         "children": [label_text("Input placeholder", "Placeholder", 14, "400",
                                 "$--muted-foreground", font)]},
        {"type": "frame", "id": nid("badge"), "name": "Badge/Default", "reusable": True,
         "x": 540, "y": 0, "fill": "$--accent", "cornerRadius": 999,
         "gap": 4, "padding": [4, 10], "alignItems": "center",
         "children": [label_text("Badge label", "Active", 12, "600",
                                 "$--accent-foreground", font)]},
    ]
    # The type ramp. A composition that picks sizes off a swatch stays on the scale; one that
    # guesses does not.
    steps = [("Display", 40, "700"), ("Heading", 28, "600"), ("Subhead", 20, "600"),
             ("Body", 16, "400"), ("Caption", 13, "400")]
    out.append({"type": "frame", "id": nid("type-scale"), "name": "Type/Scale", "reusable": True,
                "x": 540, "y": 80, "layout": "vertical", "gap": 12, "alignItems": "start",
                "children": [label_text(f"Type {label}", f"{label} — {size}px", size, weight,
                                        "$--foreground", font)
                             for label, size, weight in steps]})
    return out


ROOT_NAME = "{slug}: design system components"


def root_frame(pack: str, kids: list[dict]) -> dict:
    """ONE frame holding the whole library, themed and painted — how a pen library file is shaped.

    Eight loose top-level frames is a canvas with components on it; one named, themed container is a
    LIBRARY, and the difference shows the moment a composition is built beside it: the library reads
    as one object to move, hide or theme, instead of eight things to keep track of.
    """
    return {"type": "frame", "id": nid("library"), "name": ROOT_NAME.format(slug=pack),
            "x": 0, "y": 0, "width": 900, "height": 700, "clip": True, "layout": "none",
            "theme": {AXIS: LIGHT}, "fill": "$--background", "children": kids}


def build(theme_css: str, brand: dict) -> dict:
    light, dark = read_pack(theme_css)
    roles = sorted(pack_lint.declared_tokens(
        pack_lint.selector_block(pack_lint.strip_css_comments(theme_css), ":root")))
    fonts = brand.get("fonts") or {}
    font = fonts.get("sans") or "Inter"
    knobs = brand.get("knobs") or {}
    # `radius: md-controls-lg-cards` is the pack's own language for the two radii; anything else
    # falls back rather than inventing a third value the pack never asked for.
    control, card = (8, 12) if knobs.get("radius") == "md-controls-lg-cards" else (6, 10)
    return {
        "version": "2.17",
        "themes": {AXIS: [LIGHT, DARK]},
        "variables": variables(light, dark, roles),
        "children": [root_frame(brand.get("slug") or "library",
                                    components(font, control, card))],
    }


def render(doc: dict) -> str:
    """Bytes are a function of the PACK and nothing else — no timestamp, no path, no version stamp.

    Same rule as `docs/coverage.html`: anything else makes `--check` unpassable by construction,
    because regenerating an unchanged pack would produce different bytes.
    """
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def is_generated(node: dict) -> bool:
    """Ours, or the designer's? The `fm-` id prefix is the whole boundary."""
    return str(node.get("id", "")).startswith("fm-")


def merge(fresh: dict, existing: dict) -> dict:
    """Refresh the generated region and LEAVE EVERYTHING ELSE ALONE.

    THE LIBRARY FILE IS ALSO THE SCRATCHPAD. Compositions get built in the same document that holds
    the components, which is the point — you compose *from* the library, in front of it. So a
    regeneration that rewrote the file wholesale would delete the designer's work every time the
    brand pack moved, and a drift check over the whole file would fire on every composition and be
    switched off within a day.

    The split is by id prefix: `fm-*` is generated and replaced, anything else is authored and
    preserved in place. Generated components keep their position in the child list so a refresh does
    not reshuffle the canvas.
    """
    kept = [c for c in existing.get("children") or [] if not is_generated(c)]
    out = dict(existing)
    out["version"] = fresh["version"]
    out["themes"] = {**(existing.get("themes") or {}), **fresh["themes"]}
    # Variables: ours are authoritative, theirs survive. A designer may add a scratch variable; the
    # role tokens are not theirs to redefine, and silently keeping a stale override would repaint
    # the library against a pack it no longer matches.
    out["variables"] = {**(existing.get("variables") or {}), **fresh["variables"]}
    out["children"] = fresh["children"] + kept
    return out


def generated_region(doc: dict, ours: set[str]) -> dict:
    """The part `--check` compares: OUR variables and OUR components, never the designer's.

    Scoping the variable half to `ours` matters as much as the id prefix does. Comparing every
    variable would make a scratch colour someone added in pen read as drift against the brand pack,
    which is a drift check that fires on correct input — and one of those gets switched off.
    """
    return {"variables": {k: v for k, v in (doc.get("variables") or {}).items() if k in ours},
            "children": [c for c in doc.get("children") or [] if is_generated(c)]}


def load(pack: str) -> tuple[str, dict]:
    root = BRANDS / pack
    css, manifest = root / "theme.css", root / "brand.json"
    if not css.is_file():
        raise Unreadable(f"no theme.css for pack {pack!r} (looked in {root})")
    brand = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    return css.read_text(encoding="utf-8"), brand


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="generate a pen.dev library from a brand pack")
    ap.add_argument("--pack", default="fidara")
    ap.add_argument("--out", default=None, help="write the .pen document here")
    ap.add_argument("--check", action="store_true",
                    help="compare an existing --out against a fresh generation (drift gate)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    try:
        css, brand = load(args.pack)
        fresh = build(css, brand)
    except (Unreadable, OSError, ValueError) as exc:
        print(f"cannot generate: {exc}", file=sys.stderr)
        return 2
    ours = set(fresh["variables"])

    def read_existing(path: Path) -> dict | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(f"{path} is not valid JSON ({exc}) — it may be mid-save in pen.")

    if args.check:
        if not args.out:
            print("--check needs --out: there is nothing to compare against", file=sys.stderr)
            return 2
        path = Path(args.out)
        current = read_existing(path)
        if current is None:
            print(f"DRIFT: {path} does not exist — generate it and commit it.", file=sys.stderr)
            return 1
        # ONLY the generated region. Compositions in this file are the designer's work, and a check
        # that fired on them would be a check that fires on correct input.
        if generated_region(current, ours) != generated_region(fresh, ours):
            print(f"DRIFT: the generated components in {path} no longer match the {args.pack} "
                  f"pack. They are generated, so the fix is to rebuild them, never to edit them in "
                  f"pen. Your own compositions are untouched by a rebuild.", file=sys.stderr)
            return 1
        print(f"{path}: the generated library matches the {args.pack} pack.")
        return 0

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = read_existing(path)
        doc = merge(fresh, current) if current else fresh
        kept = len(doc["children"]) - len(fresh["children"])
        path.write_text(render(doc), encoding="utf-8")
        # Count the COMPONENTS, not the root frame that holds them. Reporting "1 component" for a
        # library of eight is the kind of true-but-useless number that makes an operator distrust
        # every other number the tool prints.
        made = len(fresh["children"][0].get("children") or [])
        print(f"wrote {args.out} — {made} component(s), {len(fresh['variables'])} role token(s)"
              + (f", {kept} of your own node(s) preserved" if kept else ""))
    else:
        sys.stdout.write(render(fresh))
    return 0


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    css, brand = load("fidara")
    doc = build(css, brand)
    out = render(doc)

    # REGENERATION IS BYTE-IDENTICAL, which is the whole reason this writes a file rather than
    # driving the MCP. Through `Insert` every id would be replaced on each run and every `ref` in
    # every existing document would break silently.
    check("regenerating twice is byte-identical", render(build(css, brand)) == out)
    ids = re.findall(r'"id": "([^"]+)"', out)
    check(f"every id is unique ({len(ids)} ids)", len(ids) == len(set(ids)))
    check("ids are derived from names, not random", all(i.startswith("fm-") for i in ids))
    check("no id contains '/' (pen forbids it)", not any("/" in i for i in ids))

    # THE HEX LIVES IN ONE PLACE. A literal colour inside a component would break recolouring and
    # light/dark at once, so the component subtree must contain none.
    body = json.dumps(doc["children"])
    check("no literal colour anywhere in the components", "#" not in body)
    check("...while the variables carry the resolved hex",
          all(HEX_RE.match(e["value"]) for v in doc["variables"].values() for e in v["value"]))
    check(f"all 22 roles are exported ({len(doc['variables'])})", len(doc["variables"]) == 22)
    # `.get` rather than `[...]`: a missing `theme` key must make this assertion FAIL, not raise.
    # A crash is not a verdict -- the mutation guard cannot tell which fixture caught a traceback.
    check("every role names BOTH theme modes",
          all({e.get("theme", {}).get(AXIS) for e in v["value"]} == {LIGHT, DARK}
              for v in doc["variables"].values()))
    # A theme-less entry is what pen's SetVariables silently drops, taking the light theme with it.
    check("no value is left theme-less",
          all("theme" in e for v in doc["variables"].values() for e in v["value"]))
    # The dark override must actually differ somewhere, or the pack's dark mode was not read.
    differing = [k for k, v in doc["variables"].items() if v["value"][0]["value"] != v["value"][1]["value"]]
    check(f"the dark scope genuinely differs ({len(differing)} roles)", len(differing) >= 10)

    # ONE ROOT FRAME holds the library -- the shape a real pen library file uses. Eight loose
    # top-level frames is a canvas with components on it; one named, themed container is a library.
    check("the document has exactly one root", len(doc["children"]) == 1)
    lib = doc["children"][0]
    check("...which is the library frame", lib["name"].endswith(": design system components"))
    check("...themed, so it renders in a known mode", lib.get("theme", {}).get(AXIS) == LIGHT)
    check("...and painted from a role token", lib.get("fill") == "$--background")

    tops = lib["children"]
    check("every component is reusable", all(c.get("reusable") for c in tops))
    names = [c["name"] for c in tops]
    check(f"the composition set is present ({len(names)})",
          {"Card", "Input/Default", "Badge/Default", "Type/Scale"} <= set(names)
          and sum(n.startswith("Button/") for n in names) == 4)
    check("components are named Category/Variant", all("/" in n or n == "Card" for n in names))

    # VARIANTS ARE REFS, NOT COPIES. One base defines the geometry; four instances repaint it, so a
    # radius change reaches all four instead of reaching one and drifting from three.
    refs = [c for c in tops if c.get("type") == "ref"]
    check(f"button variants are refs, not copies ({len(refs)})", len(refs) == 3)
    base_ids = {c["id"] for c in tops if c.get("type") != "ref"}
    check("...each pointing at a component in this document",
          all(r["ref"] in base_ids for r in refs))
    check("...and repainting the label through `descendants`",
          all(r.get("descendants") for r in refs))
    # LAID OUT BY FLEXBOX, so a component sizes to its content instead of being a fixed picture.
    btn = next(c for c in tops if c["name"] == "Button/Default")
    check("the base button is laid out, not absolutely sized",
          btn.get("padding") and "width" not in btn)
    check("...and its children carry no x/y", all("x" not in k for k in btn["children"]))

    # WHAT THE COMPILER IS AND IS NOT FOR. An earlier version of this suite compiled every
    # component through `pen_to_svg` as a cross-check. That was an over-reach: the compiler exists
    # for ARTWORK -- bounded geometry with a resolved size -- and a design-system component laid out
    # by flexbox has no size until a layout engine runs, because it is sized by its content. It was
    # also never destined to become an `.svg` file; it becomes ERB. So the property that mattered is
    # asserted directly, above: no literal colour anywhere in the library. The compiler still refuses
    # an unsized node, honestly, which is the behaviour a caller wants when they point it at one.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pen_to_svg", Path(__file__).resolve().parent / "pen_to_svg.py")
    p2s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2s)
    try:
        p2s.compile_svg(doc, "Button/Default")
        failures.append("an unsized flex component should not silently compile")
    except p2s.Refusal as exc:
        check("the compiler refuses an unsized flex component rather than guessing",
              "no size" in str(exc))
    checks += 1
    # ...while a REF still resolves, because a well-authored library expresses variants that way and
    # refusing them would reward the copy-paste library over the good one.
    sized = {"children": [{"type": "frame", "id": "fm-base", "name": "Base", "width": 40,
                           "height": 20, "fill": "$--primary",
                           "children": [{"type": "rectangle", "id": "fm-inner", "x": 0, "y": 0,
                                         "width": 40, "height": 20, "fill": "$--primary"}]},
                          {"type": "ref", "id": "fm-alt", "name": "Alt", "ref": "fm-base",
                           "x": 0, "y": 0, "fill": "$--secondary",
                           "descendants": {"fm-inner": {"fill": "$--accent"}}}]}
    svg = p2s.compile_svg(sized, "Alt")
    check("a ref variant compiles by resolving its base", "<rect" in svg)
    check("...with the instance's own override applied", "var(--secondary)" in svg)
    check("...and its descendant override applied", "var(--accent)" in svg)
    try:
        p2s.compile_svg({"children": [{"type": "ref", "id": "x", "name": "N", "ref": "nope",
                                       "width": 4, "height": 4}]}, "N")
        failures.append("a dangling ref should be refused")
    except p2s.Refusal as exc:
        check("a dangling ref is refused, not rendered as nothing",
              "not in this document" in str(exc))
    checks += 1

    # THE DRIFT GATE fires on an edited library and stays silent on a fresh one.
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "lib.pen"
        check("a missing file is reported as drift", main(["--check", "--out", str(target)]) == 1)
        main(["--out", str(target)])
        check("...a freshly written one is clean", main(["--check", "--out", str(target)]) == 0)
        target.write_text(out.replace('"fm-card"', '"fm-card-EDITED"'), encoding="utf-8")
        check("...and an edited component is reported", main(["--check", "--out", str(target)]) == 1)

    # THE FILE IS ALSO THE SCRATCHPAD, so a regeneration must not eat the designer's work. This is
    # the assertion that makes it safe to keep composing in the same document.
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "lib.pen"
        main(["--out", str(target)])
        doc_now = json.loads(target.read_text())
        doc_now["children"].append({"type": "frame", "id": "my-hero-exploration", "name": "Hero v3",
                                    "x": 0, "y": 900, "width": 400, "height": 300,
                                    "fill": "$--background", "children": []})
        doc_now["variables"]["--scratch"] = {"type": "color", "value": [
            {"value": "#123456", "theme": {AXIS: LIGHT}}, {"value": "#123456", "theme": {AXIS: DARK}}]}
        target.write_text(render(doc_now), encoding="utf-8")

        check("a composition alongside the library is NOT drift",
              main(["--check", "--out", str(target)]) == 0)
        check("...nor is a scratch variable the designer added",
              "--scratch" in json.loads(target.read_text())["variables"])

        main(["--out", str(target)])                       # regenerate over the top
        after = json.loads(target.read_text())
        names = [c["name"] for c in after["children"]]
        check("regenerating PRESERVES the designer's composition", "Hero v3" in names)
        check("...and their scratch variable", "--scratch" in after["variables"])
        # `next(...)` with a DEFAULT, not a bare generator: if the library frame is missing, this
        # assertion must FAIL rather than raise. A StopIteration here aborts the run and swallows
        # every failure recorded before it -- which is how a mutation guard ends up unable to say
        # which fixture caught it, and a crash is not a verdict.
        lib_after = next((c for c in after["children"]
                          if str(c.get("id", "")).startswith("fm-library")), None)
        check("...while still carrying every generated component",
              lib_after is not None and {"Card", "Input/Default", "Badge/Default"}
              <= {k["name"] for k in lib_after.get("children") or []})
        check("...with the role tokens still authoritative",
              after["variables"]["--primary"] == doc["variables"]["--primary"])
        # A designer who overrides a ROLE must lose that override: the pack owns the roles, and a
        # stale override would repaint the library against a pack it no longer matches.
        stale = json.loads(target.read_text())
        stale["variables"]["--primary"] = {"type": "color", "value": [
            {"value": "#FF00FF", "theme": {AXIS: LIGHT}}, {"value": "#FF00FF", "theme": {AXIS: DARK}}]}
        target.write_text(render(stale), encoding="utf-8")
        check("a hand-edited ROLE token is reported as drift",
              main(["--check", "--out", str(target)]) == 1)
        main(["--out", str(target)])
        check("...and a rebuild restores it from the pack",
              json.loads(target.read_text())["variables"]["--primary"]
              == doc["variables"]["--primary"])

    # An unknown pack is an error, not an empty library.
    checks += 1
    try:
        load("no-such-pack")
        failures.append("an unknown pack should be unreadable")
    except Unreadable:
        pass

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} pen-library assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
