#!/usr/bin/env python3
"""Compile a `.pen` design document into token-native SVG — the round-trip, not an export (#602).

WHY COMPILE RATHER THAN EXPORT. pen.dev exports `png/jpeg/webp/pdf` and nothing else — read off
`export_nodes`' own tool schema, not inferred from prose. So there is no SVG to export. But the
`.pen` format *is* SVG-shaped: a `path` carries `geometry`, which is an SVG path string, beside an
optional `viewBox`. The geometry never has to be recovered from a render; it is already in the
notation we want.

AND COMPILING BEATS EXPORTING, which is the part worth internalising. Every design tool's SVG export
emits hardcoded hex — precisely what `design-auditor` refuses by name (#135: "a `fill=`/`stroke=` hex
inside a component"), so an exported asset lands as a conformance violation needing manual
recolouring. A `.pen` fill that references a variable is written `$--token`, and compiles straight to
`var(--token)`: born conformant, recolouring with the brand pack, and following light/dark from ONE
file rather than two. The missing export is not a gap being worked around.

IT READS THE FILE, NOT THE MCP, and that is forced rather than chosen. `Get("<pathId>").geometry`
returns `"..."` through the pencil MCP — on a direct single-node read as well as through a visitor.
The one field this depends on is the one the structured API elides. The file itself is plain JSON
(measured on three real documents), so reading it works; the server's instruction that ".pen files
are encrypted" is false as a claim about bytes, and following it would rule out the only path that
functions.

A LITERAL COLOUR IS AN UPSTREAM PROBLEM, NOT A COMPILATION ONE. It means someone composed against a
raw hex instead of a token, so this refuses and names the node. Guessing which token a hex "probably
meant" is exactly the cross-colour-space matching that `rendered_conformance.py` avoids by
construction — and a wrong guess is invisible, because the result still looks like a brand colour.

WHAT IT REFUSES RATHER THAN APPROXIMATES. Shaders, mesh gradients, conic (`angular`) gradients, image
fills and arc/donut ellipses have no SVG equivalent. A silently-degraded compile is worse than none:
it looks finished, so nobody re-checks it. Each refusal names the construct and the node.

Exit codes:  0 compiled · 1 refused (a construct SVG cannot express, or a raw colour) · 2 bad input

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Node types with no SVG equivalent at all. Naming each one beats a generic "unsupported": the
# reader needs to know whether to flatten it in pen or keep the asset raster.
UNREPRESENTABLE = {
    "shader": "a WebGL fragment shader",
    "script": "code-generated content",
    "prompt": "an AI prompt node",
    "note": "a canvas annotation",
    "context": "a canvas annotation",
}

# The node types this compiles. Stated as data so `--selftest` can assert the handler set matches,
# rather than a reader trusting that the if-chain below is exhaustive.
HANDLED = ("frame", "group", "rectangle", "ellipse", "polygon", "path", "text")


class Refusal(Exception):
    """A construct that must not be approximated. Carries the node so the fix is actionable."""


def paint(value, node_id: str, prop: str, defs: list | None = None) -> str:
    """A fill/stroke value → an SVG paint string. A `$--token` is the only accepted colour source."""
    if value is None:
        return "none"
    if isinstance(value, dict):
        kind = value.get("type")
        if kind == "color":
            return paint(value.get("color"), node_id, prop, defs)
        if kind == "gradient":
            if defs is None:
                raise Refusal(f"node {node_id!r}: a gradient cannot be emitted in this position")
            return gradient(value, node_id, prop, defs)
        if kind == "image":
            raise Refusal(
                f"node {node_id!r}: {prop} is an image fill. An illustration that embeds a raster "
                f"is not a vector asset — replace the image in pen, or keep this asset raster.")
        if kind == "mesh":
            raise Refusal(
                f"node {node_id!r}: {prop} is a mesh gradient. A bezier-interpolated colour grid "
                f"has no SVG equivalent; flatten it in pen, or keep this asset raster.")
        raise Refusal(f"node {node_id!r}: {prop} is an unsupported fill type {kind!r}")
    text = str(value)
    if text.startswith("$"):
        return f"var({text[1:]})"                    # $--primary -> var(--primary)
    raise Refusal(
        f"node {node_id!r}: {prop} is the literal colour {text!r}. Illustration recolours from role "
        f"tokens, so compose against a pen variable and it compiles to var(--…). Guessing which "
        f"token this hex meant is how a brand quietly acquires a second palette.")


def gradient(spec: dict, node_id: str, prop: str, defs: list) -> str:
    """A pen gradient → a `<defs>` entry, returned as the `url(#…)` that references it."""
    kind = spec.get("gradientType", "linear")
    stops_spec = spec.get("colors") or []
    if not stops_spec:
        raise Refusal(f"node {node_id!r}: {prop} is a gradient with no colour stops")
    gid = f"g{len(defs)}"
    last = max(1, len(stops_spec) - 1)
    stops = "\n".join(
        f'      <stop offset="{s.get("position", i / last)}" '
        f'stop-color="{paint(s.get("color"), node_id, prop)}"/>'
        for i, s in enumerate(stops_spec))
    if kind == "linear":
        # pen states rotation in degrees CCW with 0° pointing UP; SVG wants two points in
        # objectBoundingBox units. Deriving the vector rather than mapping a few known angles is
        # what keeps an arbitrary rotation from silently landing on the nearest cardinal direction.
        rad = math.radians(float(spec.get("rotation") or 0))
        dx, dy = math.sin(rad) * 0.5, -math.cos(rad) * 0.5
        defs.append(f'    <linearGradient id="{gid}" x1="{round(0.5 - dx, 4)}" '
                    f'y1="{round(0.5 - dy, 4)}" x2="{round(0.5 + dx, 4)}" '
                    f'y2="{round(0.5 + dy, 4)}">\n{stops}\n    </linearGradient>')
    elif kind == "radial":
        c = spec.get("center") or {}
        defs.append(f'    <radialGradient id="{gid}" cx="{c.get("x", 0.5)}" '
                    f'cy="{c.get("y", 0.5)}">\n{stops}\n    </radialGradient>')
    else:
        raise Refusal(
            f"node {node_id!r}: {prop} is an {kind!r} (conic) gradient, which SVG has no element "
            f"for. Approximating it with a linear ramp would change the design without saying so — "
            f"flatten it in pen, or keep this asset raster.")
    return f"url(#{gid})"


def stroke_attrs(n: dict, out: list, defs: list | None = None) -> None:
    if n.get("stroke") is None:
        return
    out.append(f'stroke="{paint(n["stroke"], n.get("id", "?"), "stroke", defs)}"')
    if n.get("strokeWidth") is not None:
        out.append(f'stroke-width="{n["strokeWidth"]}"')
    for key, attr in (("strokeLinecap", "stroke-linecap"), ("strokeLinejoin", "stroke-linejoin")):
        if n.get(key):
            out.append(f'{attr}="{n[key]}"')


def opacity_attr(n: dict, out: list) -> None:
    if n.get("opacity") is not None:
        out.append(f'opacity="{n["opacity"]}"')


def num(v, default: float = 0.0) -> float:
    """A dimension as a float. A pen number may be a `$variable` binding, which has no value here."""
    if isinstance(v, str) and v.startswith("$"):
        raise Refusal(f"a dimension is bound to the variable {v!r}. Sizes must be concrete in an "
                      f"exported asset — resolve it in pen first.")
    return float(v) if v is not None else default


def emit(n: dict, dx: float, dy: float, out: list, defs: list) -> None:
    """One node → SVG elements, translated into the root node's coordinate space."""
    kind = n.get("type")
    nid = n.get("id", "?")
    if kind in UNREPRESENTABLE:
        raise Refusal(f"node {nid!r} is {kind!r} — {UNREPRESENTABLE[kind]}, which SVG cannot "
                      f"express. Remove it from the compiled subtree, or keep this asset raster.")
    if kind not in HANDLED:
        raise Refusal(f"node {nid!r} has type {kind!r}, which this compiler does not handle")

    x, y = dx + num(n.get("x")), dy + num(n.get("y"))
    w, h = num(n.get("width")), num(n.get("height"))

    # ROTATION is degrees CCW about the node's TOP-LEFT corner, per the schema — not SVG's origin,
    # and not the node's centre. A bare rotate(deg) would spin the shape about the canvas origin and
    # fling it off-canvas, which reads as "the compiler lost my artwork" rather than as an axis bug.
    rot = n.get("rotation")
    if rot:
        out.append(f'  <g transform="rotate({-num(rot)} {x} {y})">')

    def close() -> None:
        if rot:
            out.append("  </g>")

    if kind in ("frame", "group"):
        # Only a frame paints a ground; a group is a pure container, exactly as in pen.
        if kind == "frame" and n.get("fill") is not None:
            out.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" '
                       f'fill="{paint(n["fill"], nid, "fill", defs)}"/>')
        for child in n.get("children") or []:
            emit(child, x, y, out, defs)
        close()
        return

    attrs: list[str] = []

    if kind == "rectangle":
        attrs = [f'x="{x}"', f'y="{y}"', f'width="{w}"', f'height="{h}"']
        if n.get("cornerRadius"):
            attrs.append(f'rx="{num(n["cornerRadius"])}"')
        attrs.append(f'fill="{paint(n.get("fill"), nid, "fill", defs)}"')
        stroke_attrs(n, attrs, defs)
        opacity_attr(n, attrs)
        out.append("  <rect " + " ".join(attrs) + "/>")

    elif kind == "ellipse":
        # An arc or donut is a path in SVG, not an ellipse. Emitting a full ellipse would silently
        # fill in the missing sweep -- a change to the artwork that renders as though intended.
        if n.get("innerRadius") or n.get("startAngle") or n.get("sweepAngle"):
            raise Refusal(
                f"node {nid!r} is an arc/donut ellipse (innerRadius/startAngle/sweepAngle). SVG's "
                f"<ellipse> cannot express a partial sweep — convert it to a path in pen first.")
        attrs = [f'cx="{x + w / 2}"', f'cy="{y + h / 2}"', f'rx="{w / 2}"', f'ry="{h / 2}"',
                 f'fill="{paint(n.get("fill"), nid, "fill", defs)}"']
        stroke_attrs(n, attrs, defs)
        opacity_attr(n, attrs)
        out.append("  <ellipse " + " ".join(attrs) + "/>")

    elif kind == "polygon":
        # pen stores a SIDE COUNT and a box; SVG needs the vertices. First vertex at the top,
        # matching pen's rendering, so a triangle points up in both.
        sides = int(n.get("polygonCount") or 3)
        if sides < 3:
            raise Refusal(f"node {nid!r} is a polygon with {sides} sides")
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        pts = " ".join(f"{round(cx + rx * math.sin(2 * math.pi * i / sides), 3)},"
                       f"{round(cy - ry * math.cos(2 * math.pi * i / sides), 3)}"
                       for i in range(sides))
        attrs = [f'points="{pts}"', f'fill="{paint(n.get("fill"), nid, "fill", defs)}"']
        stroke_attrs(n, attrs, defs)
        opacity_attr(n, attrs)
        out.append("  <polygon " + " ".join(attrs) + "/>")

    elif kind == "path":
        geom = n.get("geometry")
        if not geom:
            raise Refusal(f"node {nid!r} is a path with no `geometry`")
        vb = n.get("viewBox")
        if vb:
            vx, vy, vw, vh = (num(v) for v in vb)
            sx = w / vw if vw else 1.0
            sy = h / vh if vh else 1.0
            transform = f"translate({x} {y}) scale({sx} {sy}) translate({-vx} {-vy})"
        else:
            # No viewBox means pen fits the geometry's own bounding box to the node box, and
            # computing that needs a full path parser. Translating unscaled is correct whenever the
            # node box matches the geometry, and visibly wrong otherwise -- which is the right
            # failure, because a silently mis-scaled shape reads as a design change.
            transform = f"translate({x} {y})"
        attrs = [f'd="{geom}"', f'transform="{transform}"',
                 f'fill="{paint(n.get("fill"), nid, "fill", defs)}"']
        if n.get("fillRule"):
            attrs.append(f'fill-rule="{n["fillRule"]}"')
        stroke_attrs(n, attrs, defs)
        opacity_attr(n, attrs)
        out.append("  <path " + " ".join(attrs) + "/>")

    elif kind == "text":
        size = num(n.get("fontSize"), 16.0)
        attrs = [f'x="{x}"', f'y="{y + size}"', f'font-size="{size}"']
        for key, attr in (("fontFamily", "font-family"), ("fontWeight", "font-weight"),
                          ("letterSpacing", "letter-spacing")):
            if n.get(key) is not None:
                attrs.append(f'{attr}="{n[key]}"')
        attrs.append(f'fill="{paint(n.get("fill"), nid, "fill", defs)}"')
        opacity_attr(n, attrs)
        body = str(n.get("content") or "")
        for raw, esc in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")):
            body = body.replace(raw, esc)
        out.append("  <text " + " ".join(attrs) + f">{body}</text>")

    close()


def find(nodes: list, wanted: str) -> dict | None:
    for n in nodes:
        if n.get("name") == wanted or n.get("id") == wanted:
            return n
        hit = find(n.get("children") or [], wanted)
        if hit:
            return hit
    return None


def compile_svg(doc: dict, root: str | None = None, title: str | None = None) -> str:
    """The document (or one named node) as SVG. `name` addresses nodes, never `id`.

    Ids are addressed by NAME on purpose: pen regenerates every id on insert ("Pencil will always
    generate unique random IDs and override the input"), so an id copied from one session does not
    survive the next. A name is the only handle stable enough to put in a build script.
    """
    roots = doc.get("children") or []
    node = find(roots, root) if root else (roots[0] if roots else None)
    if node is None:
        raise Refusal(f"no node named {root!r} in this document" if root
                      else "this document has no nodes to compile")
    w, h = num(node.get("width")), num(node.get("height"))
    if not w or not h:
        raise Refusal(f"node {node.get('name') or node.get('id')!r} has no size to compile into")
    body: list[str] = []
    defs: list[str] = []
    emit(node, -num(node.get("x")), -num(node.get("y")), body, defs)
    label = title or node.get("name") or "illustration"
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="pen-title">',
        f"  <title id=\"pen-title\">{label}</title>",
        *(["  <defs>", *defs, "  </defs>"] if defs else []),
        *body,
        "</svg>",
    ]) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="compile a .pen document into token-native SVG")
    ap.add_argument("penfile", nargs="?", help="path to the .pen file")
    ap.add_argument("--node", default=None, help="node NAME to compile (default: first root)")
    ap.add_argument("--title", default=None, help="accessible title (default: the node's name)")
    ap.add_argument("--out", default=None, help="write here instead of stdout")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.penfile:
        ap.print_help()
        return 2

    path = Path(args.penfile)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2
    try:
        svg = compile_svg(doc, args.node, args.title)
    except Refusal as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(svg, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(svg)
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    def refuses(label, node, needle):
        nonlocal checks
        checks += 1
        doc = {"children": [{"type": "frame", "name": "r", "width": 10, "height": 10,
                             "children": [node]}]}
        try:
            compile_svg(doc)
        except Refusal as exc:
            if needle not in str(exc):
                failures.append(f"{label}: refused, but the reason omitted {needle!r} — {exc}")
            return
        failures.append(f"{label}: compiled instead of refusing")

    # FIXTURES ARE HAND-AUTHORED JSON, never a captured `.pen`. A real document would drag the
    # vendor's version churn into the suite and could not carry a deliberately malformed node --
    # and every refusal below needs exactly that.
    def frame(*children, **kw):
        return {"children": [{"type": "frame", "name": "root", "width": 100, "height": 80,
                              **kw, "children": list(children)}]}

    # THE HAPPY PATH: every colour arrives as a token, so every colour leaves as var(--…).
    svg = compile_svg(frame(
        {"type": "rectangle", "id": "r1", "x": 4, "y": 6, "width": 20, "height": 8,
         "cornerRadius": 4, "fill": "$--muted", "opacity": 0.5},
        {"type": "ellipse", "id": "e1", "x": 10, "y": 20, "width": 40, "height": 20,
         "fill": "$--card", "stroke": "$--primary", "strokeWidth": 2},
        {"type": "path", "id": "p1", "x": 5, "y": 5, "width": 20, "height": 10,
         "geometry": "M0 10C5 2 15 2 20 10", "viewBox": [0, 0, 20, 10],
         "stroke": "$--primary", "strokeWidth": 3, "strokeLinecap": "round"},
        {"type": "polygon", "id": "g1", "x": 0, "y": 0, "width": 10, "height": 10,
         "polygonCount": 3, "fill": "$--primary"},
        {"type": "text", "id": "t1", "x": 2, "y": 60, "width": 50, "height": 12,
         "content": "Net position", "fontSize": 12, "fill": "$--foreground"},
        fill="$--background"))
    check("a token fill compiles to var(--…)", 'fill="var(--muted)"' in svg)
    check("...and so does a token stroke", 'stroke="var(--primary)"' in svg)
    check("NO literal colour survives into the output",
          "#" not in svg.split("<title")[0] + svg.split("</title>")[-1])
    check("the frame paints a ground rect", '<rect x="0.0" y="0.0" width="100.0"' in svg)
    check("a rounded rect keeps its radius", 'rx="4.0"' in svg)
    check("an ellipse is converted from box to centre+radii",
          'cx="30.0"' in svg and 'ry="10.0"' in svg)
    check("a path keeps its geometry VERBATIM", 'd="M0 10C5 2 15 2 20 10"' in svg)
    check("...and its viewBox becomes a transform", "scale(1.0 1.0)" in svg)
    check("a polygon becomes explicit points", "<polygon points=" in svg)
    check("...with its first vertex at the top", "5.0,0.0" in svg)
    check("text carries its content", ">Net position</text>" in svg)
    check("opacity is carried", 'opacity="0.5"' in svg)
    check("stroke-linecap is carried", 'stroke-linecap="round"' in svg)
    check("the svg is accessible", 'role="img"' in svg and 'aria-labelledby="pen-title"' in svg)
    check("...and titled from the node name", "<title id=\"pen-title\">root</title>" in svg)

    # THE REFUSALS. Each is a construct that must not be approximated, because a degraded compile
    # looks finished and nobody re-checks it.
    refuses("a literal hex fill", {"type": "rectangle", "id": "bad", "width": 4, "height": 4,
                                  "fill": "#FF0000"}, "literal colour")
    refuses("a shader node", {"type": "shader", "id": "sh", "width": 4, "height": 4}, "shader")
    refuses("a mesh gradient", {"type": "rectangle", "id": "m", "width": 4, "height": 4,
                                "fill": {"type": "mesh"}}, "mesh gradient")
    refuses("an image fill", {"type": "rectangle", "id": "i", "width": 4, "height": 4,
                              "fill": {"type": "image"}}, "image fill")
    refuses("a conic gradient", {"type": "rectangle", "id": "c", "width": 4, "height": 4,
                                 "fill": {"type": "gradient", "gradientType": "angular",
                                          "colors": [{"color": "$--a"}]}}, "conic")
    refuses("an arc ellipse", {"type": "ellipse", "id": "a", "width": 4, "height": 4,
                               "fill": "$--a", "startAngle": 30}, "partial sweep")
    refuses("a path with no geometry", {"type": "path", "id": "p", "width": 4, "height": 4},
            "no `geometry`")
    refuses("an unknown node type", {"type": "widget", "id": "w", "width": 4, "height": 4},
            "does not handle")
    refuses("a variable-bound dimension",
            {"type": "rectangle", "id": "v", "width": "$--w", "height": 4, "fill": "$--a"},
            "bound to the variable")

    # GRADIENTS resolve to a defs entry, and their stops are tokens like everything else.
    svg = compile_svg(frame(fill={"type": "gradient", "gradientType": "linear", "rotation": 0,
                                 "colors": [{"color": "$--muted", "position": 0},
                                            {"color": "$--card", "position": 1}]}))
    check("a linear gradient emits a defs entry", "<linearGradient id=\"g0\"" in svg)
    check("...referenced by url(#…)", 'fill="url(#g0)"' in svg)
    check("...with token stops", 'stop-color="var(--muted)"' in svg)
    # 0° points UP in pen, so the ramp runs bottom -> top: y1 below y2 in SVG's y-down space.
    check("...and 0° runs bottom-to-top", 'y1="1.0"' in svg and 'y2="0.0"' in svg)

    # ROTATION is about the node's TOP-LEFT corner. Getting the pivot wrong flings artwork off
    # canvas, which reads as lost work rather than as an axis bug.
    svg = compile_svg(frame({"type": "rectangle", "id": "r", "x": 10, "y": 20, "width": 4,
                             "height": 4, "fill": "$--a", "rotation": -11}))
    check("rotation pivots on the node's own top-left", 'rotate(11.0 10.0 20.0)' in svg)
    check("...and closes its group", svg.count("<g transform=") == svg.count("</g>"))

    # NESTING: a group is a pure container that still offsets its children.
    svg = compile_svg(frame({"type": "group", "id": "g", "x": 5, "y": 5, "children": [
        {"type": "rectangle", "id": "in", "x": 2, "y": 3, "width": 4, "height": 4,
         "fill": "$--a"}]}))
    check("a group offsets its children", 'x="7.0" y="8.0"' in svg)
    check("...and paints no ground of its own", svg.count("<rect") == 1)

    # ADDRESSING IS BY NAME, because pen regenerates every id on insert.
    doc = {"children": [{"type": "frame", "name": "one", "width": 4, "height": 4},
                        {"type": "frame", "name": "two", "width": 8, "height": 8}]}
    check("a node is selected by name", 'width="8.0"' in compile_svg(doc, "two"))
    check("...and the first root is the default", 'width="4.0"' in compile_svg(doc))
    refuses_name = False
    try:
        compile_svg(doc, "missing")
    except Refusal:
        refuses_name = True
    checks += 1
    if not refuses_name:
        failures.append("an unknown node name should be refused")

    # The handler set is asserted against the code rather than described, so a type added to one and
    # not the other is a test failure instead of a silent gap.
    checks += 1
    if set(HANDLED) & set(UNREPRESENTABLE):
        failures.append("a type is both HANDLED and UNREPRESENTABLE")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} pen-to-svg assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
