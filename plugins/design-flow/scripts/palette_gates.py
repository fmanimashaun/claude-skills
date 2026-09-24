#!/usr/bin/env python3
"""The computable hard gates of a categorical chart palette (#1235).

WHY THIS EXISTS. `brand_pack_lint.py` required `chart_palette_validated: true` and never ran the
validation the flag asserts, so both shipped packs claimed a validated palette while failing it:
reliance on lightness, chroma and normal-vision separation; fidara on colour-vision separation
(`#22C55E` next to `#FF6B35`, dE 4.8 for deuteranopia). A flag nothing checks is a claim, so the
lint now COMPUTES the verdict with these gates.

THE METHOD, and where each number comes from (`skills/design-system/references/data-viz.md`
#Validation names the data-viz method these follow):

  lightness band   OKLCH L within the mode's band -- light 0.43-0.77, dark 0.48-0.67
  chroma floor     OKLCH C >= 0.10 (below it a hue reads as grey)
  CVD separation   OKLab dE x100 between ADJACENT slots under simulated protanopia and
                   deuteranopia, worst of the two -- FAIL below 6 (6-8 is legal only with
                   secondary encoding, which the doctrine already mandates)
  normal vision    OKLab dE x100 between adjacent slots, unsimulated -- FAIL below 15

OKLab is Bjorn Ottosson's (2020). The CVD simulation is Machado, Oliveira & Fernandes (2009) at
severity 1.0, applied in linear RGB; the matrices are the paper's published values.

Contrast against the surface is deliberately NOT a gate here: under 3:1 the doctrine requires
relief (direct labels or a table view), which is a rule about the chart, not about the hues.
"""
from __future__ import annotations

import math

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_FLOOR = 6.0
NORMAL_FLOOR = 15.0

MACHADO_2009 = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
}


def _linear(hex_colour: str) -> tuple[float, float, float]:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    h = hex_colour.lstrip("#")
    return tuple(channel(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))  # type: ignore[return-value]


def _oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _simulate(rgb: tuple[float, float, float], kind: str) -> tuple[float, float, float]:
    m = MACHADO_2009[kind]
    return tuple(min(1.0, max(0.0, sum(m[i][j] * rgb[j] for j in range(3)))) for i in range(3))  # type: ignore[return-value]


def _delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return 100 * math.dist(a, b)


def lch(hex_colour: str) -> tuple[float, float]:
    """(OKLCH L, OKLCH C) of one colour."""
    L, a, b = _oklab(_linear(hex_colour))
    return L, math.hypot(a, b)


def measure(hues: list[str]) -> dict:
    """Every number the gates read, so a report can show the worst case, not just the verdict."""
    rgb = [_linear(h) for h in hues]
    pairs = list(zip(range(len(hues)), range(1, len(hues))))

    def worst(transform) -> tuple[float, str, str]:
        return min((_delta_e(transform(rgb[i]), transform(rgb[j])), hues[i], hues[j]) for i, j in pairs)

    cvd = min(worst(lambda c, k=k: _oklab(_simulate(c, k))) for k in MACHADO_2009)
    return {"lch": {h: lch(h) for h in hues}, "cvd": cvd, "normal": worst(_oklab)}


def failures(hues: list[str], mode: str = "light") -> list[str]:
    """Hard-gate failures, each a sentence naming the offending hues. Empty means the palette passes."""
    m = measure(hues)
    lo, hi = BAND[mode]
    out = []
    band = [f"{h} L {L:.3f}" for h, (L, _) in m["lch"].items() if not lo <= L <= hi]
    if band:
        out.append(f"lightness outside the {mode} band {lo}-{hi}: {', '.join(band)}")
    grey = [f"{h} C {C:.3f}" for h, (_, C) in m["lch"].items() if C < CHROMA_FLOOR]
    if grey:
        out.append(f"chroma below {CHROMA_FLOOR} (reads as grey): {', '.join(grey)}")
    dE, a, b = m["cvd"]
    if dE < CVD_FLOOR:
        out.append(f"colour-blind separation {a}<->{b} dE {dE:.1f} is below {CVD_FLOOR}")
    dE, a, b = m["normal"]
    if dE < NORMAL_FLOOR:
        out.append(f"normal-vision separation {a}<->{b} dE {dE:.1f} is below {NORMAL_FLOOR}")
    return out


def selftest() -> int:
    """Every expectation is a number the data-viz method's own validator printed for these palettes.

    The port is checked against that authority, never against itself: a fixture that recomputes the
    formula proves only that the formula agrees with the formula.
    """
    checks, fails = 0, []

    def expect(label: str, ok: bool) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(label)

    old_reliance = ["#137CC1", "#8ACAEF", "#288D68", "#DC6803", "#CB193B"]
    old_fidara = ["#0077CC", "#00A3FF", "#00D4FF", "#FF6B35", "#22C55E"]
    validated = ["#0077CC", "#FF6B35", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

    r = measure(old_reliance)
    expect("reliance: #8ACAEF L 0.809 and C 0.084",
           round(r["lch"]["#8ACAEF"][0], 3) == 0.809 and round(r["lch"]["#8ACAEF"][1], 3) == 0.084)
    expect("reliance: worst colour-blind pair dE 8.4", round(r["cvd"][0], 1) == 8.4)
    expect("reliance: worst normal-vision pair #DC6803/#CB193B dE 14.9",
           round(r["normal"][0], 1) == 14.9 and {r["normal"][1], r["normal"][2]} == {"#DC6803", "#CB193B"})
    f = failures(old_reliance)
    expect("reliance FAILS the band gate", any(x.startswith("lightness") for x in f))
    expect("reliance FAILS the chroma gate", any(x.startswith("chroma") for x in f))
    expect("reliance FAILS the normal-vision gate", any(x.startswith("normal-vision") for x in f))

    r = measure(old_fidara)
    expect("fidara: worst colour-blind pair #FF6B35/#22C55E dE 4.8 (deuteranopia)",
           round(r["cvd"][0], 1) == 4.8 and {r["cvd"][1], r["cvd"][2]} == {"#FF6B35", "#22C55E"})
    expect("fidara FAILS the colour-blind gate", any(x.startswith("colour-blind") for x in failures(old_fidara)))

    # THE CONTROL: the doctrine's validated palette passes every gate, with its recorded figures.
    r = measure(validated)
    expect("validated palette: colour-blind dE 9.1, normal dE 19.6",
           round(r["cvd"][0], 1) == 9.1 and round(r["normal"][0], 1) == 19.6)
    expect("validated palette passes every gate", failures(validated) == [])

    # THE 6-SERIES THRESHOLD in data-viz.md (#1267) rests on two printed figures for the default
    # DARK series: its first five slots clear the 8 band, and the sixth brings the 5<->6 pair to 6.1.
    dark = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#33a852", "#9085e9", "#e66767"]
    r = measure(dark[:5])
    expect("dark, 5 series: worst colour-blind pair #c98500/#199e70 dE 8.4 (no relief needed)",
           round(r["cvd"][0], 1) == 8.4 and {r["cvd"][1], r["cvd"][2]} == {"#c98500", "#199e70"})
    r = measure(dark)
    expect("dark, 8 series: worst colour-blind pair #33a852/#d55181 dE 6.1 (the 6+ series rule)",
           round(r["cvd"][0], 1) == 6.1 and {r["cvd"][1], r["cvd"][2]} == {"#33a852", "#d55181"})
    expect("dark, 8 series passes every hard gate", failures(dark, "dark") == [])

    for label in fails:
        print(f"FAIL {label}")
    print(f"palette_gates selftest: {checks} checks, {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else (print("usage: palette_gates.py --selftest") or 2))
