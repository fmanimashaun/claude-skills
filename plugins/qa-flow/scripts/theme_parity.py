#!/usr/bin/env python3
"""Compare a light and a dark snapshot of one route: what breaks in ONE theme only.

Run:  python3 theme_parity.py light.json dark.json
      python3 theme_parity.py light.json dark.json --json
      python3 theme_parity.py --selftest

WHY (#105, criterion 3 — "renders light + dark and flags theme-only failures"). Every other rule in
this toolchain judges **one** rendering. A theme-only failure is invisible to all of them by
construction: each snapshot is individually conformant, and the defect is the *difference*.

The failure this is really for is **text that disappears in dark mode** — a hardcoded colour, or a
role token used for text against a surface that inverts underneath it. In light it is a paragraph;
in dark it is the same colour as its background. Nothing that reads a single snapshot can see that,
because in each one the element is simply "some colour on some colour".

IT CONSUMES design-flow's SNAPSHOT, and does not re-run its RULES. That distinction is the point:
re-implementing `tap-target-small` here would be a second rule with a second owner drifting from the
first. The snapshot is data; the rules stay where they live.

WHAT IT COMPARES. Elements matched by the collector's `ref`, then three differences that are
decidable from two snapshots and mean something:

  contrast-regression   readable in one theme, under 4.5:1 in the other
  vanished              painted and sized in one theme, gone or zero-sized in the other
  colour-frozen         an element whose painted colour is IDENTICAL in both themes while its
                        surroundings inverted -- the signature of a hardcoded value

WHAT IT DOES NOT DO. It does not judge either theme on its own: a page equally broken in both is
`rendered_conformance.py`'s finding, not a parity failure, and reporting it here would double-count.
It does not crawl or screenshot. It does not diff pixels.

Exit codes:  0 clean · 1 findings · 2 the snapshots are unusable

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

AA_NORMAL = 4.5
RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)")


class Unusable(RuntimeError):
    """The pair cannot be compared -- reported, never treated as parity."""


MAX_EXAMPLES = 3


def _grouped(findings):
    """[( (rule, detail), [ref, ...] ), ...] in first-seen order, refs de-duplicated.

    #108 item J. A defect in a SHARED LAYOUT is found once per page, so one line per finding
    reports a single broken control 72 times. `ref` here is `"<route> <selector>"`, so the
    refs differ even when the defect does not — grouping is on `(rule, detail)`, which is the
    part that is genuinely the same. Details carrying per-instance counts therefore do not
    group, and that is correct: it never merges two defects to make a shorter report.

    Deliberately duplicated across the judges rather than extracted. They are standalone by
    design — an agent runs one file — and a shared module would trade that for ten lines.
    """
    out: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        refs = out.setdefault((f.rule, f.detail), [])
        if f.ref not in refs:
            refs.append(f.ref)
    return list(out.items())


@dataclass
class Finding:
    ref: str
    rule: str
    detail: str


def parse_rgb(value: str) -> tuple[float, float, float, float] | None:
    m = RGB_RE.match((value or "").strip())
    if not m:
        return None
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return r, g, b, a


SRGB_LINEAR_BREAKPOINT = 0.04045  # WCAG 2.2 — see luminance()


def luminance(rgb: tuple[float, float, float, float]) -> float:
    chan = []
    for v in rgb[:3]:
        c = v / 255
        # 0.04045 is WCAG 2.2's sRGB linearisation breakpoint (2.0 said 0.03928; the current
        # normative text does not). design-flow's palette_candidates.py already used 2.2's value, so
        # the two shipped plugins disagreed on luminance for channels in [0.03928, 0.04045] (#830).
        chan.append(c / 12.92 if c <= SRGB_LINEAR_BREAKPOINT else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]


def contrast(fg: str, bg: str) -> float | None:
    a, b = parse_rgb(fg), parse_rgb(bg)
    if not a or not b:
        return None
    # A translucent foreground cannot be judged without compositing the whole stack, and guessing
    # would invent a number. Refuse rather than report a fiction.
    if a[3] < 1.0 or b[3] < 1.0:
        return None
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def load(path: Path, expect_theme: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or "elements" not in data:
        raise Unusable(f"{path}: not a conformance snapshot (no `elements`)")
    theme = data.get("theme")
    if theme != expect_theme:
        # Comparing two snapshots of the SAME theme would report perfect parity and prove nothing.
        raise Unusable(
            f"{path}: theme is {theme!r}, expected {expect_theme!r}. Two snapshots of the same theme "
            "always agree, so this would report parity while testing nothing.")
    return data


def background_of(el: dict) -> str | None:
    return (el.get("colours") or {}).get("background-color")


def compare(light: dict, dark: dict) -> list[Finding]:
    out: list[Finding] = []
    by_ref_dark = {e.get("ref"): e for e in dark.get("elements", [])}

    # The page's own surface, used when an element paints no background of its own -- which is most
    # of them. Without it, text on the page surface could never be judged at all.
    def surface(snapshot: dict) -> str | None:
        for el in snapshot.get("elements", []):
            if el.get("tag") in ("body", "html") and background_of(el):
                return background_of(el)
        return None

    light_surface, dark_surface = surface(light), surface(dark)

    for el in light.get("elements", []):
        ref = el.get("ref")
        twin = by_ref_dark.get(ref)
        if twin is None:
            continue                     # absent from dark: handled below, once, in one direction

        lc = (el.get("colours") or {}).get("color")
        dc = (twin.get("colours") or {}).get("color")
        lbg = background_of(el) or light_surface
        dbg = background_of(twin) or dark_surface

        if lc and dc and lbg and dbg:
            l_ratio, d_ratio = contrast(lc, lbg), contrast(dc, dbg)
            if l_ratio is not None and d_ratio is not None:
                if (l_ratio >= AA_NORMAL) != (d_ratio >= AA_NORMAL):
                    good, bad = ("light", "dark") if l_ratio >= AA_NORMAL else ("dark", "light")
                    out.append(Finding(ref, "contrast-regression",
                                       f"{l_ratio:.2f}:1 light vs {d_ratio:.2f}:1 dark — "
                                       f"readable in {good}, under {AA_NORMAL}:1 in {bad}"))
            # A colour identical across themes is only suspicious when the SURROUNDINGS moved. A
            # brand mark is legitimately fixed, so the signal is sameness against an inverted
            # backdrop, never sameness alone.
            if lc == dc and lbg != dbg:
                out.append(Finding(ref, "colour-frozen",
                                   f"text stays {lc} while its surface moved {lbg} -> {dbg}"))

        lr, dr = el.get("rect") or {}, twin.get("rect") or {}
        painted = bool((el.get("colours") or {})) or bool((twin.get("colours") or {}))
        if painted and (lr.get("w"), lr.get("h")) != (0, 0) and (dr.get("w"), dr.get("h")) == (0, 0):
            out.append(Finding(ref, "vanished", "sized in light, zero-sized in dark"))

    # Built ONCE. It was a comprehension inside the loop below, which does not depend on the loop
    # variable -- so the whole light-side element list was walked again for every dark element,
    # quadratic in a page's element count on a rule whose entire input is a page of elements.
    # Behaviour is unchanged; #360's `efficiency` dimension found it, and the `present only in
    # dark` fixture below covers the branch.
    light_refs = {e.get("ref") for e in light.get("elements", [])}

    for ref, el in by_ref_dark.items():
        if ref not in light_refs:
            lr = el.get("rect") or {}
            if (lr.get("w"), lr.get("h")) != (0, 0):
                out.append(Finding(ref, "vanished", "present in dark, absent from light"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag theme-only failures between two snapshots.")
    ap.add_argument("light", nargs="?", type=Path)
    ap.add_argument("dark", nargs="?", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.light or not args.dark:
        ap.error("both a light and a dark snapshot are required")
    try:
        findings = compare(load(args.light, "light"), load(args.dark, "dark"))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for f in findings:
            print(f"  [{f.rule}] {f.ref}\n      {f.detail}")
        print(f"\n{len(findings)} theme-only finding(s).")
    return 1 if findings else 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def snap(theme, elements):
        return {"theme": theme, "elements": elements}

    def el(ref, colour=None, bg=None, w=100.0, h=20.0, tag="p"):
        colours = {}
        if colour:
            colours["color"] = colour
        if bg:
            colours["background-color"] = bg
        return {"ref": ref, "tag": tag, "colours": colours, "rect": {"w": w, "h": h}}

    body_l = el("body", bg="rgb(255, 255, 255)", tag="body")
    body_d = el("body", bg="rgb(12, 27, 51)", tag="body")

    # The case this file exists for: readable in light, invisible in dark.
    f = compare(snap("light", [body_l, el("p", "rgb(15, 21, 32)")]),
                snap("dark", [body_d, el("p", "rgb(20, 33, 58)")]))
    check("text readable in light and not in dark fires",
          any(x.rule == "contrast-regression" for x in f), f"{f}")

    # SILENCE: a page that is fine in both themes.
    f = compare(snap("light", [body_l, el("p", "rgb(15, 21, 32)")]),
                snap("dark", [body_d, el("p", "rgb(248, 249, 251)")]))
    check("a page fine in both themes is silent", not f, f"{f}")

    # SILENCE, and the near-miss that matters: equally BAD in both themes is
    # rendered_conformance's finding, not a parity failure. Reporting it here double-counts.
    f = compare(snap("light", [body_l, el("p", "rgb(250, 250, 250)")]),
                snap("dark", [body_d, el("p", "rgb(20, 33, 58)")]))
    check("bad in BOTH themes is not a parity finding",
          not any(x.rule == "contrast-regression" for x in f), f"{f}")

    # colour-frozen: same text colour while the surface inverted.
    f = compare(snap("light", [body_l, el("p", "rgb(15, 21, 32)")]),
                snap("dark", [body_d, el("p", "rgb(15, 21, 32)")]))
    check("a frozen colour against an inverted surface fires",
          any(x.rule == "colour-frozen" for x in f), f"{f}")
    # ...but NOT when the surface did not move: a fixed brand colour on a fixed surface is fine.
    same = el("body", bg="rgb(255, 255, 255)", tag="body")
    f = compare(snap("light", [same, el("p", "rgb(15, 21, 32)")]),
                snap("dark", [same, el("p", "rgb(15, 21, 32)")]))
    check("a frozen colour on an unmoved surface is silent",
          not any(x.rule == "colour-frozen" for x in f), f"{f}")

    # vanished, both directions.
    f = compare(snap("light", [body_l, el("p", "rgb(15, 21, 32)")]),
                snap("dark", [body_d, el("p", "rgb(248, 249, 251)", w=0.0, h=0.0)]))
    check("an element that goes zero-sized in dark fires",
          any(x.rule == "vanished" for x in f), f"{f}")
    f = compare(snap("light", [body_l]),
                snap("dark", [body_d, el("extra", "rgb(248, 249, 251)")]))
    check("an element present only in dark fires",
          any(x.rule == "vanished" for x in f), f"{f}")

    # A translucent colour cannot be judged without compositing; refusing beats inventing a number.
    check("a translucent foreground yields no ratio",
          contrast("rgba(0, 0, 0, 0.5)", "rgb(255, 255, 255)") is None)
    check("the maths matches the standard control",
          abs(contrast("rgb(118, 118, 118)", "rgb(255, 255, 255)") - 4.54) < 0.01,
          "the reference 4.54:1 pair no longer computes")
    # THE BREAKPOINT (#830). A channel of 10.25/255 = 0.0402 sits BETWEEN WCAG 2.0's 0.03928 and 2.2's
    # 0.04045: under 2.2 it linearises as c/12.92; under 2.0 it takes the power branch. (10/255 =
    # 0.0392 is below both, and a first draft of this fixture used it -- the regression mutation
    # survived, because the probe never reached the region where the two formulas disagree.)
    check("luminance uses the WCAG 2.2 breakpoint (0.04045), not 2.0's",
          abs(luminance((10.25, 10.25, 10.25, 1.0)) - (10.25 / 255) / 12.92) < 1e-9,
          f"got {contrast('rgb(118, 118, 118)', 'rgb(255, 255, 255)')}")

    # SAME-THEME PAIRS MUST BE REFUSED: they always agree, so they would report parity while
    # testing nothing -- a gate that cannot fail.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.json"
        p.write_text(json.dumps(snap("light", [])), encoding="utf-8")
        n += 1
        try:
            load(p, "dark")
            failures.append("a light snapshot passed as dark: same-theme pairs must be refused")
        except Unusable:
            pass
        p.write_text("{}", encoding="utf-8")
        n += 1
        try:
            load(p, "light")
            failures.append("a document with no elements parsed as a snapshot")
        except Unusable:
            pass

    # ---- #108 item J: collapse a shared-layout defect, never merge two distinct ones -------
    G = Finding
    shared = [G("/a nav>a", "RULE", "DETAIL"), G("/b nav>a", "RULE", "DETAIL"),
              G("/c nav>a", "RULE", "DETAIL")]
    check("one defect across three pages collapses to one group", len(_grouped(shared)) == 1,
          f"{_grouped(shared)}")
    check("the group keeps every ref",
          _grouped(shared)[0][1] == ["/a nav>a", "/b nav>a", "/c nav>a"], f"{_grouped(shared)}")
    # THE FAILURE THAT WOULD MATTER: a shorter report that hid a defect.
    two = [G("/a x", "RULE", "DETAIL"), G("/b x", "RULE", "OTHER DETAIL")]
    check("same rule, different detail stays two groups", len(_grouped(two)) == 2, f"{_grouped(two)}")
    two_rules = [G("/a x", "RULE", "DETAIL"), G("/a x", "OTHER RULE", "DETAIL")]
    check("same detail, different rule stays two groups", len(_grouped(two_rules)) == 2,
          f"{_grouped(two_rules)}")
    dup = [G("/a x", "RULE", "DETAIL"), G("/a x", "RULE", "DETAIL")]
    check("a repeated ref is counted once", _grouped(dup)[0][1] == ["/a x"], f"{_grouped(dup)}")
    check("no findings groups to nothing", _grouped([]) == [], f"{_grouped([])}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f_ in failures:
            print(f"  - {f_}", file=sys.stderr)
        return 1
    print(f"theme_parity selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
