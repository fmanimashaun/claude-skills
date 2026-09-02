#!/usr/bin/env python3
"""Curated, MEASURED starting palettes for a brand pack — and the snap path for a client's own.

Run:  python3 palette_candidates.py --list                 # the catalogue + its measured figures
      python3 palette_candidates.py --list-fonts           # the optional type pairings
      python3 palette_candidates.py --emit harbor --out brands/acme
      python3 palette_candidates.py --snap "#C8102E"       # the client HAS a brand colour
      python3 palette_candidates.py --check                # gate: every candidate clears the bar
      python3 palette_candidates.py --selftest

WHY THIS EXISTS (#129). A brand pack's required surface is colours + logo + the chart-palette
validation result, and a new client routinely arrives with **no usable palette** — a logo and a
vibe. Authoring one by hand is slow and the quality depends on who is doing it that day. So there
is a small, measured candidate set.

WHAT IT IS NOT — and this is the part to keep. It is **not a style menu**. The skill this ships
inside is prescriptive on purpose: one radius language, one type scale, one component API, because
consistency is the product. A catalogue of 192 palettes would directly undo the drift-killing
design-system exists to do. Ten candidates exist to make the FIRST HOUR of a client engagement
fast and correct; after that a pack has exactly one palette, like every other pack.

THE ONE MECHANISM. A palette is not stored as 22 hand-written roles. It is stored as a handful of
ANCHORS and composed through `snap()` into the full role contract. That matters because it makes
the catalogue path and the client-brand path **the same code**: "snap the client's colours to our
role structure" is not a second feature, it is `snap()` with anchors derived from their hex. A
second composer would be a second place for the role contract to be got wrong.

MEASURED, NOT ASSERTED. Every candidate is measured against WCAG 2.2 SC 1.4.3 (4.5:1 for normal
text) in BOTH modes, by `--check`, which is a gate. A palette that fails contrast is worse than no
palette, because it ships in a client's colours and nobody re-checks it.
  https://www.w3.org/TR/WCAG22/#contrast-minimum
  "The visual presentation of text and images of text has a contrast ratio of at least 4.5:1"

WHY THE MATHS IS DUPLICATED FROM scripts/check_token_contrast.py. It has to be: a plugin must run
in a user's clone with nothing else installed, and `scripts/` is maintainer tooling that is never
distributed. So the copies are COMPARED rather than trusted — `check_token_contrast.py --selftest`
imports this module and asserts both implementations agree to 1e-9 and share one threshold. Same
discipline `brand_pack_lint --roles-from` applies to the role contract.

Exit: 0 clean · 1 a candidate is under threshold / a pack could not be written · 2 usage.

Stdlib only, no network — a pack must be authorable in any clone with nothing installed.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_pack_lint as bpl  # noqa: E402  — sibling module; the role contract lives there

AA_NORMAL = 4.5

# WCAG 2.2's relative-luminance definition linearises an sRGB channel at 0.04045 (WCAG 2.0 said
# 0.03928; the current normative text does not).
#   https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
SRGB_LINEAR_BREAKPOINT = 0.04045

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class Unusable(ValueError):
    """Input this tool cannot honestly work from -- never a silent fallback."""


# ---------------------------------------------------------------------------
# colour maths (see the module docstring for why it is not imported)
# ---------------------------------------------------------------------------

def linearise(channel: float) -> float:
    if channel <= SRGB_LINEAR_BREAKPOINT:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def normalise_hex(value: str) -> str:
    if not isinstance(value, str) or not HEX_RE.match(value.strip()):
        raise Unusable(f"{value!r} is not a #RGB or #RRGGBB colour")
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def luminance(hex_colour: str) -> float:
    h = normalise_hex(hex_colour).lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [linearise(c) for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _to_hls(hex_colour: str) -> tuple[float, float, float]:
    h = normalise_hex(hex_colour).lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(hue: float, light: float, sat: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, min(max(light, 0.0), 1.0), sat)
    return "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r, g, b)))


# The scan resolution for `nearest_passing`. 1/512 is finer than 8-bit quantisation, so the
# returned colour is the closest REPRESENTABLE one rather than the closest one on a coarse grid.
_L_STEPS = 512


DIRECTIONS = ("any", "lighter", "darker")


def nearest_passing(colour: str, surface: str, threshold: float = AA_NORMAL,
                    direction: str = "any") -> tuple[str, float]:
    """The closest colour of the same HUE that clears `threshold` on `surface`.

    Returns (hex, ratio). If `colour` already clears it, `colour` is returned UNCHANGED -- a tool
    that "improves" a brand colour which was already fine gets rejected the first time a client
    notices, and then nobody runs it on the one that was not fine.

    `direction` constrains the search. On a dark surface the answer must be `lighter`: a colour
    darkened toward the background is technically closer in lightness while being exactly the
    wrong move, and an unconstrained search on a near-black card will happily propose black.

    With `direction="any"` there is always an answer -- a surface light enough that black fails is
    light enough that white passes, and vice versa -- so the empty case can only arise from a
    constrained search. That one raises rather than returning the failing input.
    """
    colour = normalise_hex(colour)
    surface = normalise_hex(surface)
    if direction not in DIRECTIONS:
        raise Unusable(f"unknown direction {direction!r}; known: {list(DIRECTIONS)}")
    if contrast(colour, surface) >= threshold:
        return colour, contrast(colour, surface)

    hue, light, sat = _to_hls(colour)
    offsets = {"any": (-1, 1), "lighter": (1,), "darker": (-1,)}[direction]
    for step in range(1, _L_STEPS + 1):
        delta = step / _L_STEPS
        for sign in offsets:
            candidate_light = light + sign * delta
            if not 0.0 <= candidate_light <= 1.0:
                continue
            candidate = _from_hls(hue, candidate_light, sat)
            ratio = contrast(candidate, surface)
            if ratio >= threshold:
                return candidate, ratio
    raise Unusable(
        f"no {direction} shade of {colour} clears {threshold}:1 on {surface} — the brand colour "
        "cannot be adapted in that direction, so the surface has to move instead"
    )


# ---------------------------------------------------------------------------
# the palette model: anchors -> the full role contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ramp:
    """A neutral scale plus the dark surface trio that goes with it."""

    name: str
    steps: dict[str, str]
    dark: tuple[str, str, str]          # background, card, popover


RAMPS: dict[str, Ramp] = {
    "cool": Ramp("cool", {
        "50": "#F8F9FB", "100": "#F1F3F7", "200": "#E2E6ED", "300": "#C8CDD8",
        "400": "#8F96A3", "500": "#5E6775", "600": "#3D4654", "700": "#2A3240",
        "800": "#1C2531", "900": "#0F1520", "950": "#0A0E16",
    }, ("#0D1219", "#171E28", "#1C2530")),
    "warm": Ramp("warm", {
        "50": "#FAF9F7", "100": "#F4F2EE", "200": "#E7E3DC", "300": "#D2CCC1",
        "400": "#9C9488", "500": "#6B6459", "600": "#4B463E", "700": "#35312B",
        "800": "#272420", "900": "#171512", "950": "#0E0D0B",
    }, ("#141210", "#201D19", "#26221E")),
    "pure": Ramp("pure", {
        "50": "#FAFAFA", "100": "#F4F4F5", "200": "#E4E4E7", "300": "#D4D4D8",
        "400": "#9A9AA2", "500": "#64646D", "600": "#47474E", "700": "#333338",
        "800": "#232327", "900": "#131316", "950": "#0A0A0C",
    }, ("#0D0D0F", "#18181B", "#1E1E22")),
}


@dataclass(frozen=True)
class Anchors:
    """Everything a palette needs. Identical shape whether it came from the catalogue or from a
    client's brand colour -- that sameness is what makes the two paths one mechanism."""

    slug: str
    ramp: str
    primary_light: str
    primary_dark: str
    dark_surfaces: tuple[str, str, str] | None = None   # None -> the ramp's own trio
    destructive: str = "#C42B2B"
    success: str = "#1A7F4B"
    warning: str = "#8A5A00"
    info: str = "#1F6FB2"

    def surfaces(self) -> tuple[str, str, str]:
        return self.dark_surfaces or RAMPS[self.ramp].dark


def snap(anchors: Anchors) -> dict[str, dict[str, str]]:
    """Anchors -> {"light": {role: hex}, "dark": {role: hex}} over the WHOLE role contract.

    THIS is "snap to our role structure". Both entry points go through it, and the role names come
    from `brand_pack_lint.ROLES` rather than a local list, so a role added to the contract makes
    this function fail loudly instead of quietly emitting a pack with a hole in it.
    """
    ramp = RAMPS.get(anchors.ramp)
    if ramp is None:
        raise Unusable(f"unknown neutral ramp {anchors.ramp!r}; known: {sorted(RAMPS)}")
    n = {k: normalise_hex(v) for k, v in ramp.steps.items()}
    dbg, dcard, dpop = (normalise_hex(s) for s in anchors.surfaces())
    p_light = normalise_hex(anchors.primary_light)
    p_dark = normalise_hex(anchors.primary_dark)
    white = "#FFFFFF"

    light = {
        "--background": n["50"],        "--foreground": n["900"],
        "--card": white,                "--card-foreground": n["900"],
        "--popover": white,             "--popover-foreground": n["900"],
        "--primary": p_light,           "--primary-foreground": white,
        "--secondary": n["100"],        "--secondary-foreground": n["900"],
        "--muted": n["100"],            "--muted-foreground": n["500"],
        "--accent": n["100"],           "--accent-foreground": n["900"],
        "--destructive": normalise_hex(anchors.destructive),
        "--destructive-foreground": white,
        "--success": normalise_hex(anchors.success),
        "--warning": normalise_hex(anchors.warning),
        "--info": normalise_hex(anchors.info),
        "--border": n["200"],           "--input": n["200"],
        "--ring": p_light,
        # #750. Composed here because `bpl.ROLES` requires them and this function's own contract
        # check (below) refuses a pack that omits any role -- which is what caught their absence.
        #
        # `--signal-foreground` is the DARKEST neutral, never white, and that is measured rather
        # than stylistic: a mid-orange accent carries white at ~2.8:1 (fails AA) and dark ink at
        # ~6.5:1 (passes). Same rule `--primary-foreground` follows on dark.
        "--overlay": n["900"],
        "--signal": normalise_hex(anchors.warning),
        "--signal-foreground": n["900"],
        "--primary-ink": p_light,       "--primary-hover": p_light,
        "--success-ink": normalise_hex(anchors.success),
    }
    # Dark re-points the SURFACE roles. `--primary-foreground` is re-pointed too, and that is the
    # #304 defect in one line: re-pointing `--primary` alone leaves the label inheriting the light
    # value, which is how white ended up on electric blue at 2.73:1 on every primary button.
    dark = dict(light)
    dark.update({
        "--background": dbg,            "--foreground": n["50"],
        "--card": dcard,                "--card-foreground": n["50"],
        "--popover": dpop,              "--popover-foreground": n["50"],
        "--primary": p_dark,            "--primary-foreground": dbg,
        "--secondary": n["800"],        "--secondary-foreground": n["50"],
        "--muted": n["800"],            "--muted-foreground": n["400"],
        "--accent": n["800"],           "--accent-foreground": n["50"],
        "--border": n["800"],           "--input": n["800"],
        # A navy scrim over a navy ground separates nothing, so dark uses the darkest neutral.
        "--overlay": n["900"],
        "--primary-ink": p_dark,        "--primary-hover": p_dark,
    })

    missing = [r for r in bpl.ROLES if r not in light]
    if missing:
        raise Unusable(
            f"snap() does not compose {len(missing)} role(s) the contract requires: "
            f"{' '.join(missing)} — an emitted pack would fall back to a stock Tailwind colour "
            "for each one"
        )
    unrepointed = [r for r in bpl.DARK_REQUIRED if dark.get(r) == light.get(r)]
    if unrepointed:
        raise Unusable(
            f"snap() leaves {len(unrepointed)} surface role(s) identical on dark: "
            f"{' '.join(unrepointed)} — dark mode would inherit the light surface"
        )
    return {"light": light, "dark": dark}


# The pairs measured for a palette WE AUTHOR. A superset of `scripts/check_token_contrast.py`'s
# canonical set by exactly one pair: `--destructive-foreground` on `--destructive`. That pair is
# excluded from the canonical set because fidara's shipped red measures 3.76:1 and which red a
# brand uses is a maintainer decision. Here there is no legacy value to grandfather -- we pick
# these hexes from scratch, so the wider bar is free.
#
# `--success` / `--warning` / `--info` are NOT enumerated. They carry no `-foreground` companion in
# the role contract, so the contract does not define what text sits on them; inventing a pair for
# them here would be inventing doctrine, not measuring it.
CANDIDATE_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("text-primary on the page",      "--primary",                "--background"),
    ("text-primary on a card",        "--primary",                "--card"),
    ("primary button label",          "--primary-foreground",     "--primary"),
    ("body text on the page",         "--foreground",             "--background"),
    ("body text on a card",           "--card-foreground",        "--card"),
    ("muted text on a muted surface", "--muted-foreground",       "--muted"),
    ("destructive button label",      "--destructive-foreground", "--destructive"),
)


@dataclass(frozen=True)
class Measurement:
    mode: str
    label: str
    foreground: str
    background: str
    ratio: float

    @property
    def passes(self) -> bool:
        return self.ratio >= AA_NORMAL


def measure(roles: dict[str, dict[str, str]]) -> list[Measurement]:
    """Every text pair, both modes. Refuses to measure nothing."""
    if not CANDIDATE_PAIRS:
        raise Unusable("CANDIDATE_PAIRS is empty, so a clean verdict would mean nothing")
    rows: list[Measurement] = []
    for mode in ("light", "dark"):
        scope = roles[mode]
        for label, fg, bg in CANDIDATE_PAIRS:
            if fg not in scope or bg not in scope:
                raise Unusable(f"{mode}: pair {label!r} names a role the palette does not define")
            rows.append(Measurement(mode, label, scope[fg], scope[bg],
                                    contrast(scope[fg], scope[bg])))
    # No second `if not rows` guard: with CANDIDATE_PAIRS non-empty the loop cannot produce an
    # empty list, so it would be a branch that can never run -- the `gate-that-cannot-fail` class
    # our own code-review skill lints for, sitting inside the guard against measuring nothing.
    return rows


def failures(roles: dict[str, dict[str, str]]) -> list[Measurement]:
    return [row for row in measure(roles) if not row.passes]


# ---------------------------------------------------------------------------
# reading a pack back off disk
# ---------------------------------------------------------------------------
#
# `--emit` writes a pack and then the pack gets EDITED, which is the point of emitting one. So the
# generated header's "re-run --check" has to be a promise this tool can keep for an arbitrary
# pack, not only for the catalogue it shipped. Without `--measure` that line would be a
# claims-vs-enforcement defect written by the tool into every pack it produces.

_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _declarations(body: str) -> dict[str, str]:
    return {name: value.strip() for name, value in _DECL.findall(body)}


def read_pack(theme_css: Path) -> dict[str, dict[str, str]]:
    """A pack's theme.css -> {"light": {role: hex}, "dark": {role: hex}}.

    `.dark` INHERITS from `:root`, and modelling that is the entire point rather than a
    convenience: the #304 defect was a `.dark` block re-pointing `--primary` and letting
    `--primary-foreground` inherit white from `:root`.
    """
    src = bpl.strip_css_comments(theme_css.read_text(encoding="utf-8"))
    # `@theme inline` re-exports roles as `--color-*` aliases for Tailwind; folding it in would
    # let an alias shadow the role it aliases.
    primitives: dict[str, str] = {}
    for block in re.findall(r"@theme(?!\s+inline)[^{]*\{(.*?)^[ \t]*\}", src, re.S | re.M):
        primitives.update(_declarations(block))
    light = _declarations(bpl.selector_block(src, ":root"))
    dark = _declarations(bpl.selector_block(src, ".dark"))
    if not light:
        raise Unusable(f"{theme_css}: no `:root` block, so the pack declares no roles")
    if not dark:
        raise Unusable(f"{theme_css}: no `.dark` block, so dark mode inherits light surfaces")
    scopes = {"light": {**primitives, **light}}
    scopes["dark"] = {**scopes["light"], **dark}

    def resolve(token: str, scope: dict[str, str], seen: frozenset[str] = frozenset()) -> str:
        if token in seen:
            raise Unusable(f"`{token}` resolves in a cycle")
        raw = scope.get(token)
        if raw is None:
            raise Unusable(f"`{token}` is not declared in {theme_css.name}")
        if HEX_RE.match(raw):
            return normalise_hex(raw)
        ref = re.fullmatch(r"var\((--[a-z0-9-]+)\)", raw)
        if not ref:
            raise Unusable(f"`{token}` is `{raw}`, neither a hex nor a single var()")
        return resolve(ref.group(1), scope, seen | {token})

    needed = {role for _label, fg, bg in CANDIDATE_PAIRS for role in (fg, bg)}
    return {mode: {role: resolve(role, scopes[mode]) for role in sorted(needed)}
            for mode in ("light", "dark")}


# ---------------------------------------------------------------------------
# the catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    anchors: Anchors
    name: str
    character: str
    choose_when: str


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        Anchors("harbor", "cool", "#0B5FA5", "#5AB0F5", ("#0C1622", "#16212F", "#1B2736")),
        "Harbor", "Deep marine blue on cool greys — the least surprising choice in the set.",
        "Blue logo, or no strong colour at all. Professional services, B2B SaaS, fintech, "
        "anything where 'trustworthy and unremarkable' is the brief.",
    ),
    Candidate(
        Anchors("pine", "cool", "#1A6B47", "#4FBF8B", ("#0D1714", "#16221E", "#1B2925")),
        "Pine", "Forest green on cool greys — calm, clinical rather than eco-cliché.",
        "Green logo. Health, sustainability, agriculture, insurance. Avoid where success/error "
        "state is the primary signal on screen: a green brand competes with a green status.",
    ),
    Candidate(
        Anchors("garnet", "warm", "#A32338", "#F0808F", ("#1A1113", "#26191C", "#2D1F22"),
                destructive="#B52D2D"),
        "Garnet", "Deep crimson on warm greys — appetite and confidence.",
        "Red or burgundy logo. Food, retail, hospitality, sport. Note the destructive role sits "
        "next to the brand hue; lean on the icon + label rule, never colour alone.",
    ),
    Candidate(
        Anchors("amethyst", "cool", "#6A3BC4", "#B79BF2", ("#14111F", "#1F1B2E", "#262137")),
        "Amethyst", "Violet on cool greys — modern without being a toy.",
        "Purple logo. Creative tools, media, edtech, community products.",
    ),
    Candidate(
        Anchors("ember", "warm", "#9A4A15", "#F0964F", ("#1B1410", "#271D17", "#2E231C"),
                destructive="#B52D2D"),
        "Ember", "Burnt orange on warm greys — high-visibility, workwear energy.",
        "Orange or amber logo. Trades, logistics, construction, field service. Reads as "
        "'operational' rather than 'consumer'.",
    ),
    Candidate(
        Anchors("teal", "cool", "#0F6B72", "#41C3CC", ("#0B1719", "#152325", "#1A2A2C")),
        "Teal", "Deep teal on cool greys — institutional calm.",
        "Teal or cyan logo. Healthcare, wellness, public sector, education.",
    ),
    Candidate(
        Anchors("graphite", "pure", "#333338", "#C9C9D1", ("#0F0F11", "#1A1A1D", "#202024")),
        "Graphite", "Near-black brand on pure greys — the brand-light option.",
        "A logo whose colour must not be echoed in the UI, or a client with no palette who wants "
        "the product to recede. Luxury, editorial, agencies, portfolios.",
    ),
    Candidate(
        Anchors("indigo", "pure", "#3B47C4", "#96A0F5", ("#101120", "#1B1D2E", "#212337")),
        "Indigo", "Blue-violet on pure greys — the developer-tool default.",
        "Indigo or blue-violet logo. Developer tools, infrastructure, technical B2B.",
    ),
    Candidate(
        Anchors("clay", "warm", "#8A4A32", "#E39B7F", ("#1A1310", "#261C18", "#2D221D"),
                destructive="#B52D2D"),
        "Clay", "Terracotta on warm greys — handmade, unhurried.",
        "Brown, rust or earth-toned logo. Artisan brands, hospitality, non-profits, "
        "anything positioning against a tech aesthetic.",
    ),
    Candidate(
        Anchors("cobalt", "pure", "#0A5CD6", "#7FAEFF", ("#0D1018", "#181C26", "#1E222D")),
        "Cobalt", "Bright saturated blue on pure greys — louder than Harbor.",
        "Bright blue logo. Consumer products, marketplaces, mobility. Pick this over Harbor when "
        "the brand is meant to be noticed rather than trusted.",
    ),
)

# The catalogue is deliberately small. See the module docstring: a bigger one would be a style
# menu, which is the thing this must not become.
CATALOGUE_BAND = (8, 12)


# ---------------------------------------------------------------------------
# type pairings — an OFFER, never a prompt
# ---------------------------------------------------------------------------
#
# A pack that omits `fonts` inherits the system stack, and inheriting is the RIGHT default: it
# keeps a client pack closer to the system, which is what preserves the one-update-benefits-every-
# project property. So onboarding offers these; it never requires a choice.
#
# NOTE WHAT IS ABSENT: per-pairing fluid type steps. #129 asked for them, and they would be wrong.
# `--text-step-*` is a SYSTEM-owned axis (brand.md: "Spacing/type scale" sits in the "system owns —
# never in a pack" column), so it is one scale shared by every pack and every pairing. Precomputing
# a scale per pairing would fork the axis the pack model exists to keep central. A pairing changes
# three family names; the scale they are rendered at is not the pairing's business.
#
# The families are named, not vouched for: availability and licensing are the pack author's check,
# not a claim from this repo.

PAIRINGS: dict[str, dict[str, str]] = {
    "grotesque": {"sans": "Bricolage Grotesque", "display": "Newsreader",
                  "mono": "Overpass Mono",
                  "character": "The system default, written out. Editorial serif display over a "
                               "quirky grotesque — omit `fonts` entirely to get this."},
    "editorial": {"sans": "Inter", "display": "Newsreader", "mono": "JetBrains Mono",
                  "character": "Serif headline over a neutral UI face. Content-forward; the "
                               "display face does the talking and the UI stays quiet."},
    "industrial": {"sans": "Archivo", "display": "Archivo", "mono": "IBM Plex Mono",
                   "character": "One condensed family throughout. Utilitarian, dense, "
                                "signage-like — suits operational and field products."},
    "humanist": {"sans": "Source Sans 3", "display": "Fraunces", "mono": "Source Code Pro",
                 "character": "Warm and approachable. The soft display face reads friendly "
                              "without reading childish."},
    "geometric": {"sans": "Inter", "display": "Poppins", "mono": "JetBrains Mono",
                  "character": "Round geometric display over a neutral UI face. Consumer, "
                               "contemporary, the safest 'modern' choice."},
    "technical": {"sans": "IBM Plex Sans", "display": "IBM Plex Sans", "mono": "IBM Plex Mono",
                  "character": "One engineered superfamily. Nothing decorative; the mono is a "
                               "true sibling, which matters when refs and timers are everywhere."},
}
PAIRING_BAND = (6, 8)
PAIRING_ROLES = ("sans", "display", "mono")
# A pairing may carry these and nothing else. `character` is prose for the chooser.
PAIRING_KEYS = frozenset({*PAIRING_ROLES, "character"})


def pairings_with_own_scale(pairings: dict[str, dict[str, str]]) -> list[str]:
    """Pairings that smuggle a type SCALE in alongside their three families.

    Enforced rather than assumed, because the pull to add one is real: #129 asked for per-pairing
    fluid steps outright. `--text-step-*` is system-owned (brand.md puts the type scale in the
    "system owns — never in a pack" column), so a per-pairing scale forks the axis the pack model
    exists to keep central, and it would do it one plausible-looking key at a time.
    """
    return sorted(slug for slug, pairing in pairings.items()
                  if any(key not in PAIRING_KEYS for key in pairing))


# ---------------------------------------------------------------------------
# emitting a pack
# ---------------------------------------------------------------------------

def theme_css(anchors: Anchors, name: str, note: str = "") -> str:
    roles = snap(anchors)
    ramp = RAMPS[anchors.ramp]
    slug = anchors.slug
    dbg, dcard, dpop = (normalise_hex(s) for s in anchors.surfaces())

    primitives = [f"  --color-{slug}-brand:       {normalise_hex(anchors.primary_light)};"
                  "   /* --primary in light */",
                  f"  --color-{slug}-brand-light: {normalise_hex(anchors.primary_dark)};"
                  "   /* --primary on DARK surfaces */"]
    for step in ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"):
        primitives.append(f"  --color-{slug}-n-{step}: {normalise_hex(ramp.steps[step])};")
    primitives += [
        f"  --color-{slug}-surface:  {dbg};",
        f"  --color-{slug}-elevated: {dcard};",
        f"  --color-{slug}-overlay:  {dpop};",
        f"  --color-{slug}-error:    {normalise_hex(anchors.destructive)};",
        f"  --color-{slug}-success:  {normalise_hex(anchors.success)};",
        f"  --color-{slug}-warning:  {normalise_hex(anchors.warning)};",
        f"  --color-{slug}-info:     {normalise_hex(anchors.info)};",
    ]

    # hex -> the primitive that holds it, so the role layer reads as var() rather than raw hex.
    by_value: dict[str, str] = {}
    for line in primitives:
        match = re.search(r"(--color-[a-z0-9-]+):\s*(#[0-9A-F]{6});", line)
        if match and match.group(2) not in by_value:
            by_value[match.group(2)] = match.group(1)

    def ref(value: str) -> str:
        primitive = by_value.get(value)
        return f"var({primitive})" if primitive else value

    def block(scope: dict[str, str], only: list[str]) -> str:
        return "\n".join(f"  {role}: {ref(scope[role])};" for role in only)

    worst = min(row.ratio for row in measure(roles))
    header_lines = [
        f"/* {name} — brand pack theme layer ONLY. Generated by palette_candidates.py.",
        "   A pack is a theme, not a fork: primitives, role mapping, dark re-points. Nothing else.",
    ]
    if note:
        header_lines.append(f"   {note}")
    header_lines += [
        "",
        "   Every text pair here was measured against WCAG 1.4.3 (4.5:1 normal text) in both",
        f"   modes; the worst is {worst:.2f}:1. Change a colour and that number is stale —",
        f"   re-measure THIS pack:  python3 scripts/palette_candidates.py --measure brands/{slug}",
        "",
        "   Still to do before this pack is finished:",
        "     1. drop the client's mark into assets/ and name it in brand.json's variant",
        "     2. run the data-viz palette validator against THESE surfaces, then set",
        "        chart_palette_validated: true — false until you have actually run it",
        f"     3. python3 scripts/brand_pack_lint.py brands/{slug}                         */",
    ]
    header = "\n".join(header_lines) + "\n"

    light_roles = list(bpl.ROLES)
    # Only the roles whose value actually moves. Re-stating an unchanged role under `.dark` is
    # noise a reader has to diff by eye; `brand_pack_lint` checks the ones that must move.
    dark_roles = [r for r in bpl.ROLES if roles["dark"][r] != roles["light"][r]]

    return (
        header
        + "\n@theme {\n  /* Primitives are PRIVATE to this pack — nothing outside may name them. */\n"
        + "\n".join(primitives)
        + "\n}\n"
        + "\n/* Semantic roles — THE PUBLIC API. Components consume only these. */\n:root {\n"
        + block(roles["light"], light_roles)
        + "\n}\n"
        + "\n/* Dark re-points the surface roles. --primary-foreground is re-pointed WITH\n"
          "   --primary; re-pointing one without the other is how a button label goes unreadable. */\n"
          ".dark {\n"
        + block(roles["dark"], dark_roles)
        + "\n}\n"
    )


def brand_json(anchors: Anchors, name: str) -> str:
    return json.dumps({
        "slug": anchors.slug,
        "name": name,
        # FALSE on purpose. The chart-palette validator is a separate tool and this script has not
        # run it, so claiming the result would be the one thing a manifest must never do. The pack
        # fails `brand_pack_lint` until you run it -- that failure IS the reminder. It is also the
        # ONLY error an emitted pack carries, which the selftest pins: everything else about the
        # pack is complete, so a second error means the composer regressed.
        "chart_palette_validated": False,
        # null, not a filename: the mark is the client's to supply, and pointing at a file that is
        # not there would be an error rather than the reminder it is meant to be.
        "variants": {anchors.slug: {"name": name, "endorsement": None, "mark": None}},
    }, indent=2) + "\n"


def write_pack(anchors: Anchors, name: str, out: Path, note: str = "") -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    written = []
    for filename, body in (("theme.css", theme_css(anchors, name, note)),
                           ("brand.json", brand_json(anchors, name))):
        target = out / filename
        target.write_text(body, encoding="utf-8")
        written.append(target)
    return written


# ---------------------------------------------------------------------------
# the client-brand path
# ---------------------------------------------------------------------------

def snap_client(brand_hex: str, ramp_name: str = "cool", slug: str = "client",
                ) -> tuple[Anchors, list[str]]:
    """The client HAS a brand colour. Snap it to the role structure and report honestly.

    Returns (anchors, notes). A note is emitted for every place their colour had to move, with the
    measured before/after — because "your brand blue is 3.1:1 on white, the nearest passing one is
    this and it is 4.6:1" is a conversation, and "it failed" is an argument.
    """
    ramp = RAMPS.get(ramp_name)
    if ramp is None:
        raise Unusable(f"unknown neutral ramp {ramp_name!r}; known: {sorted(RAMPS)}")
    brand = normalise_hex(brand_hex)
    notes: list[str] = []

    # LIGHT. The binding surface is `--background` (darker than the card), and white-on-primary is
    # the same comparison read the other way, so one fix satisfies the button label too.
    light_surface = ramp.steps["50"]
    p_light, light_ratio = nearest_passing(brand, light_surface)
    if p_light == brand:
        notes.append(f"light: {brand} clears {AA_NORMAL}:1 on {light_surface} "
                     f"({light_ratio:.2f}:1) — used as --primary unchanged")
    else:
        notes.append(f"light: {brand} is {contrast(brand, light_surface):.2f}:1 on "
                     f"{light_surface}, under {AA_NORMAL}:1. Nearest passing colour of the same "
                     f"hue is {p_light} ({light_ratio:.2f}:1) — used as --primary. Keep {brand} "
                     f"for the mark, which is exempt: WCAG 1.4.3 excludes logotypes.")

    # DARK. `--card` is the binding surface (lighter than the page), and the search is constrained
    # to LIGHTER: darkening a brand colour toward a near-black card is the wrong direction even
    # when it is the smaller move, and unconstrained it would eventually propose black.
    dark_bg, dark_card, _ = ramp.dark
    p_dark, dark_ratio = nearest_passing(brand, dark_card, direction="lighter")
    if p_dark == brand:
        notes.append(f"dark: {brand} clears {AA_NORMAL}:1 on {dark_card} already "
                     f"({dark_ratio:.2f}:1) — used as --primary on dark unchanged")
    else:
        notes.append(f"dark: a light step of the same hue is needed on {dark_card}; "
                     f"{brand} is {contrast(brand, dark_card):.2f}:1 there, {p_dark} is "
                     f"{dark_ratio:.2f}:1")
    notes.append(f"dark: --primary-foreground re-points to {dark_bg} "
                 f"({contrast(dark_bg, p_dark):.2f}:1) — NOT white, and not inherited from light")

    anchors = Anchors(slug=slug, ramp=ramp_name, primary_light=p_light, primary_dark=p_dark)
    remaining = failures(snap(anchors))
    if remaining:
        notes.append("STILL FAILING after the snap — do not ship this: "
                     + "; ".join(f"{r.mode} {r.label} {r.foreground} on {r.background} "
                                 f"{r.ratio:.2f}:1" for r in remaining))
    return anchors, notes


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def _by_slug(slug: str) -> Candidate:
    for candidate in CANDIDATES:
        if candidate.anchors.slug == slug:
            return candidate
    raise Unusable(f"no candidate {slug!r}; known: "
                   f"{', '.join(c.anchors.slug for c in CANDIDATES)}")


def cmd_list() -> int:
    print(f"{len(CANDIDATES)} candidate palettes — a starting point for client onboarding, "
          "NOT a style menu.\n")
    for candidate in CANDIDATES:
        rows = measure(snap(candidate.anchors))
        worst = min(rows, key=lambda r: r.ratio)
        print(f"  {candidate.anchors.slug:9} {candidate.name:10} "
              f"{candidate.anchors.ramp:5} neutrals   worst pair {worst.ratio:5.2f}:1 "
              f"({worst.mode} {worst.label})")
        print(f"            {candidate.character}")
        print(f"            choose when: {candidate.choose_when}\n")
    print("Emit one:   palette_candidates.py --emit <slug> --out brands/<slug>")
    print("Client has a brand colour instead:   palette_candidates.py --snap \"#RRGGBB\"")
    return 0


def cmd_list_fonts() -> int:
    print(f"{len(PAIRINGS)} type pairings — an OFFER, not a step. Omitting `fonts` from "
          "brand.json\ninherits the system stack, and inheriting is the right default.\n")
    for slug, pairing in PAIRINGS.items():
        print(f"  {slug:11} sans {pairing['sans']} · display {pairing['display']} · "
              f"mono {pairing['mono']}")
        print(f"              {pairing['character']}\n")
    print("There are no per-pairing fluid type steps, deliberately: --text-step-* is a SYSTEM")
    print("axis shared by every pack (brand.md), so a per-pairing scale would fork it.")
    print("Availability and licensing of a family are the pack author's check, not ours.")
    return 0


def cmd_check() -> int:
    problems: list[str] = []
    low, high = CATALOGUE_BAND
    if not low <= len(CANDIDATES) <= high:
        problems.append(f"the catalogue holds {len(CANDIDATES)} candidates, outside the declared "
                        f"{low}-{high} band — it is a starting point, not a style menu")
    slugs = [c.anchors.slug for c in CANDIDATES]
    duplicated = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicated:
        problems.append(f"duplicate candidate slug(s): {duplicated}")

    measured = 0
    for candidate in CANDIDATES:
        try:
            rows = measure(snap(candidate.anchors))
        except Unusable as exc:
            problems.append(f"{candidate.anchors.slug}: {exc}")
            continue
        measured += len(rows)
        worst = min(rows, key=lambda r: r.ratio)
        bad = [r for r in rows if not r.passes]
        mark = "ok  " if not bad else "FAIL"
        print(f"  [{mark}] {candidate.anchors.slug:9} {len(rows):2} pairs, "
              f"worst {worst.ratio:5.2f}:1 ({worst.mode} {worst.label})")
        for row in bad:
            problems.append(f"{candidate.anchors.slug}: {row.mode} {row.label} — "
                            f"{row.foreground} on {row.background} is {row.ratio:.2f}:1, under "
                            f"{AA_NORMAL}:1")
    if not measured:
        problems.append("measured no pairs at all — a clean verdict over nothing is not a pass")

    for slug, pairing in PAIRINGS.items():
        for role in PAIRING_ROLES:
            if not pairing.get(role):
                problems.append(f"type pairing {slug!r} declares no {role} family")
    low, high = PAIRING_BAND
    if not low <= len(PAIRINGS) <= high:
        problems.append(f"{len(PAIRINGS)} type pairings, outside the declared {low}-{high} band")
    for slug in pairings_with_own_scale(PAIRINGS):
        problems.append(f"type pairing {slug!r} carries something beyond three families: "
                        f"{sorted(set(PAIRINGS[slug]) - PAIRING_KEYS)}. The type SCALE is "
                        "system-owned (brand.md); a per-pairing scale forks it.")

    if problems:
        print(f"\nPALETTE CHECK FAILED — {len(problems)}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"\n{len(CANDIDATES)} candidates × {len(CANDIDATE_PAIRS)} pairs × 2 modes = {measured} "
          f"text pairs, all at or above {AA_NORMAL}:1. {len(PAIRINGS)} type pairings complete.")
    return 0


def _pack_slug(explicit: str | None, out: str | None, fallback: str) -> str:
    """The slug a pack should carry. Defaults to the DIRECTORY it is written into, because
    `brand_pack_lint` warns when the two disagree and a generated pack should not arrive already
    warning about itself."""
    if explicit:
        return explicit
    if out:
        return os.path.basename(os.path.normpath(out)) or fallback
    return fallback


def cmd_emit(slug: str, out: str | None, explicit_slug: str | None) -> int:
    candidate = _by_slug(slug)
    anchors = candidate.anchors
    target = _pack_slug(explicit_slug, out, anchors.slug)
    if target != anchors.slug:
        anchors = Anchors(target, anchors.ramp, anchors.primary_light, anchors.primary_dark,
                          anchors.dark_surfaces, anchors.destructive, anchors.success,
                          anchors.warning, anchors.info)
    bad = failures(snap(anchors))
    if bad:
        print(f"refusing to emit {slug}: {len(bad)} pair(s) under {AA_NORMAL}:1", file=sys.stderr)
        return 1
    if out is None:
        print(theme_css(anchors, candidate.name, candidate.character), end="")
        print("\n/* --- brand.json --- */")
        print(brand_json(anchors, candidate.name), end="")
        return 0
    for path in write_pack(anchors, candidate.name, Path(out), candidate.character):
        print(f"wrote {path}")
    print(f"\nNext: drop the mark into {out}/assets/ and name it in brand.json, run the data-viz "
          f"palette validator\nagainst these surfaces, set chart_palette_validated: true, then "
          f"`python3 brand_pack_lint.py {out}`.")
    return 0


def cmd_measure(pack: str) -> int:
    """Measure a pack that already exists on disk — including one edited after `--emit`."""
    path = Path(pack)
    theme = path / "theme.css" if path.is_dir() else path
    if not theme.is_file():
        raise Unusable(f"{theme} does not exist; point --measure at a pack directory")
    rows = measure(read_pack(theme))
    for row in rows:
        mark = "ok  " if row.passes else "FAIL"
        print(f"  [{mark}] {row.mode:5} {row.label:30} {row.foreground} on "
              f"{row.background} = {row.ratio:.2f}:1")
    bad = [r for r in rows if not r.passes]
    if bad:
        print(f"\n{len(bad)} of {len(rows)} pair(s) under WCAG 1.4.3's {AA_NORMAL}:1. This pack "
              f"is not shippable — it would render unreadable in the client's own colours.",
              file=sys.stderr)
        return 1
    print(f"\n{len(rows)} text pairs, all at or above {AA_NORMAL}:1.")
    return 0


def cmd_snap(brand_hex: str, ramp: str, slug: str, out: str | None) -> int:
    anchors, notes = snap_client(brand_hex, ramp, _pack_slug(None, out, slug))
    print(f"snapping {normalise_hex(brand_hex)} onto the role structure ({ramp} neutrals)\n")
    for note in notes:
        print(f"  {note}")
    print()
    rows = measure(snap(anchors))
    for row in rows:
        mark = "ok  " if row.passes else "FAIL"
        print(f"  [{mark}] {row.mode:5} {row.label:30} {row.foreground} on "
              f"{row.background} = {row.ratio:.2f}:1")
    bad = [r for r in rows if not r.passes]
    if bad:
        print(f"\n{len(bad)} pair(s) still under {AA_NORMAL}:1 — this palette is not shippable.",
              file=sys.stderr)
        return 1
    if out:
        for path in write_pack(anchors, slug.title(), Path(out),
                               f"Snapped from the client brand colour {normalise_hex(brand_hex)}."):
            print(f"wrote {path}")
    return 0


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
#
# Roughly half of these are SILENCE fixtures, and they are the half that decides whether this tool
# survives contact with a real client brand. A checker that flags a palette which is already fine
# gets switched off, and then nothing measures the one that is not fine.

def selftest() -> int:
    import tempfile   # noqa: PLC0415 — only the selftest needs it

    failures_found: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures_found.append(f"{label}: {detail}")

    def attempt(label: str, fn):
        """Run `fn`, turning an unexpected raise into a LABELLED failure.

        Without this an `Unusable` from anywhere in the selftest unwinds past every finding
        collected so far, and the run reports an exit code with no fixture named. A crash is not
        a verdict: a mutation that kills the module before a labelled assertion has not been
        caught by that assertion, and reading it as caught is how a fixture goes quiet unnoticed.
        """
        nonlocal checks
        checks += 1
        try:
            return fn()
        except Exception as exc:                                    # noqa: BLE001 — deliberate
            failures_found.append(f"{label}: raised {type(exc).__name__}: {exc}")
            return None

    # ---- the maths, against the two standard controls -------------------------------------
    # Without these the whole file is unfalsifiable, and the parity assertion in
    # scripts/check_token_contrast.py --selftest would be comparing two copies of the same bug.
    check("control: #767676 on white is 4.54", round(contrast("#767676", "#FFFFFF"), 2) == 4.54,
          f"got {contrast('#767676', '#FFFFFF'):.4f}")
    check("control: white on black is 21.00", round(contrast("#FFFFFF", "#000000"), 2) == 21.00,
          f"got {contrast('#FFFFFF', '#000000'):.4f}")
    check("contrast is symmetric",
          abs(contrast("#0072C4", "#FFFFFF") - contrast("#FFFFFF", "#0072C4")) < 1e-9)
    check("the sRGB linearisation breakpoint is WCAG 2.2's 0.04045",
          abs(linearise(0.04) - 0.04 / 12.92) < 1e-12,
          f"0.04 linearised to {linearise(0.04)!r}")

    # ---- the catalogue: fires ---------------------------------------------------------------
    # A candidate that fails must be REPORTED. This is the fixture the "gate stops comparing"
    # mutations have to trip, so it is asserted through `failures()` rather than by eye.
    unreadable = Anchors("bad", "cool", "#9BD4FF", "#0A0A0A")   # pale blue on near-white
    bad = failures(snap(unreadable))
    check("a failing candidate is reported, not passed", len(bad) >= 2,
          f"only {len(bad)} pair(s) flagged on a deliberately unreadable palette")

    # THE NEAR MISS, which is the only fixture that can tell 4.5 from 3. A pair at 4.08:1 is
    # comfortably over 1.4.3's LARGE-text allowance and under its normal-text bar, and every pair
    # this tool measures is body-sized in at least one documented use. Without this, dropping
    # AA_NORMAL to 3.0 leaves every other fixture in the file perfectly happy.
    near = Measurement("light", "near miss", "#FFFFFF", "#0080DE",
                       contrast("#FFFFFF", "#0080DE"))
    check("the near-miss fixture really is a near miss", 3.0 <= near.ratio < AA_NORMAL,
          f"{near.ratio:.3f}:1 is not between the large-text allowance and the normal-text bar")
    check("a pair at 4.08:1 is under the bar — 3:1 is the LARGE-text allowance, not this one",
          not near.passes, f"{near.ratio:.3f}:1 was accepted")

    # ---- the catalogue: stays silent --------------------------------------------------------
    # The direction that matters more. Every shipped candidate must be clean, and a rule that
    # fires on correct input is a rule someone deletes.
    noisy: list[str] = []
    for candidate in CANDIDATES:
        for row in failures(snap(candidate.anchors)):
            noisy.append(f"{candidate.anchors.slug} {row.mode} {row.label} {row.ratio:.2f}")
    check("a conformant candidate is silent", not noisy, f"flagged: {noisy}")

    checks += 1
    if cmd_check() != 0:
        failures_found.append("--check reports a failure against the shipped catalogue")

    # ---- the composer covers the WHOLE contract ---------------------------------------------
    # Reading the role names off brand_pack_lint rather than a local list is the reuse that makes
    # this checkable at all: a role added to the contract must break this, loudly.
    composed = snap(CANDIDATES[0].anchors)
    check("composed roles match the brand_pack_lint contract",
          set(composed["light"]) == set(bpl.ROLES),
          f"missing {sorted(set(bpl.ROLES) - set(composed['light']))}, "
          f"extra {sorted(set(composed['light']) - set(bpl.ROLES))}")
    unmoved = [r for r in bpl.DARK_REQUIRED if composed["dark"][r] == composed["light"][r]]
    check("every dark-required role is re-pointed", not unmoved, f"unmoved: {unmoved}")
    check("--primary-foreground is re-pointed with --primary (the #304 defect)",
          composed["dark"]["--primary-foreground"] != composed["light"]["--primary-foreground"])

    # The two assertions above only prove the CURRENT contract is satisfied. They say nothing about
    # what happens when the contract MOVES, which is the case the guards inside snap() exist for
    # and the case that actually arrives. So the contract is moved, here, and the guards have to
    # fire. Without this both guards are unreachable code that every fixture agrees with.
    saved_roles, saved_dark = list(bpl.ROLES), list(bpl.DARK_REQUIRED)
    try:
        bpl.ROLES.append("--sidebar")
        checks += 1
        try:
            snap(CANDIDATES[0].anchors)
            failures_found.append(
                "a role added to the contract makes snap() fail loudly: it composed a pack "
                "silently missing --sidebar, which would render a stock Tailwind colour")
        except Unusable:
            pass
    finally:
        bpl.ROLES[:] = saved_roles
    try:
        # --ring is in the contract and legitimately holds one value across both themes, so
        # demanding a dark re-point of it must raise.
        bpl.DARK_REQUIRED.append("--ring")
        checks += 1
        try:
            snap(CANDIDATES[0].anchors)
            failures_found.append(
                "a dark-required role that does not move makes snap() fail loudly: it composed "
                "a pack whose --ring never re-points")
        except Unusable:
            pass
    finally:
        bpl.DARK_REQUIRED[:] = saved_dark

    # ---- measuring nothing is not a pass ----------------------------------------------------
    checks += 1
    saved = globals()["CANDIDATE_PAIRS"]
    globals()["CANDIDATE_PAIRS"] = ()
    try:
        measure(composed)
        failures_found.append("measuring nothing is not a pass: an empty pair set measured clean "
                              "instead of raising")
    except Unusable:
        pass
    finally:
        globals()["CANDIDATE_PAIRS"] = saved

    # ---- nearest_passing: fires -------------------------------------------------------------
    pale = "#9BD4FF"
    fixed, ratio = nearest_passing(pale, "#FFFFFF")
    check("the nearest alternative actually passes", ratio >= AA_NORMAL,
          f"{pale} -> {fixed} is {ratio:.2f}:1 on white")
    check("the nearest alternative keeps the client's hue",
          abs(_to_hls(fixed)[0] - _to_hls(pale)[0]) < 0.02,
          f"hue moved from {_to_hls(pale)[0]:.4f} to {_to_hls(fixed)[0]:.4f}")

    # ---- nearest_passing: stays silent ------------------------------------------------------
    already = "#0B5FA5"
    same, _ = nearest_passing(already, "#FFFFFF")
    check("a brand colour that already passes is returned unchanged", same == already,
          f"{already} was rewritten to {same}")

    # A constrained search can genuinely have no answer, and must say so rather than hand back
    # the failing input dressed as a fix.
    checks += 1
    try:
        nearest_passing("#FFFFFF", "#FFFFFF", direction="lighter")
        failures_found.append("a constrained search with no answer returned instead of raising")
    except Unusable:
        pass

    # An answer always exists when the direction is unconstrained. Proved over a spread of
    # surfaces rather than asserted in the docstring.
    for surface in ("#000000", "#333333", "#767676", "#BBBBBB", "#FFFFFF", "#7F7F7F"):
        checks += 1
        try:
            _, got = nearest_passing("#808080", surface)
            if got < AA_NORMAL:
                failures_found.append(f"unconstrained search on {surface} returned {got:.2f}:1")
        except Unusable as exc:
            failures_found.append(f"unconstrained search found nothing on {surface}: {exc}")

    # ---- the client-brand path --------------------------------------------------------------
    # A hex that fails on our light surface must come back adapted AND shippable, with the
    # movement reported. Silence about a change would be worse than the change.
    snapped = attempt("a failing client brand is snapped to a shippable palette",
                      lambda: snap_client("#9BD4FF", "cool", "acme"))
    if snapped is not None:
        anchors, notes = snapped
        remaining = failures(snap(anchors))
        check("a failing client brand is snapped to a shippable palette", not remaining,
              f"{[f'{r.mode} {r.label} {r.ratio:.2f}' for r in remaining]}")
        check("the snap reports where the client's colour had to move",
              any("under" in n or "needed" in n for n in notes), f"notes: {notes}")

    # ---- the emitted pack -------------------------------------------------------------------
    checks += 1
    with tempfile.TemporaryDirectory(prefix="palette-candidates-selftest-") as tmp:
        pack = Path(tmp) / "acme"
        write_pack(CANDIDATES[0].anchors, CANDIDATES[0].name, pack)
        report = bpl.lint_pack(str(pack))
        # EXACTLY one error, and it is the un-run chart validation. Pinning the count is what makes
        # this an assertion about completeness rather than a shrug: a composer that dropped a role
        # would add a second error here.
        chart_errors = [e for e in report.errors if "chart_palette_validated" in e]
        check("the emitted pack's only lint error is the chart validation nobody has run yet",
              len(report.errors) == 1 and len(chart_errors) == 1,
              f"errors: {report.errors}")
        css = (pack / "theme.css").read_text(encoding="utf-8")
        declared = bpl.declared_tokens(bpl.selector_block(bpl.strip_css_comments(css), ":root"))
        check("the emitted pack defines every role",
              set(bpl.ROLES) <= declared,
              f"missing from :root: {sorted(set(bpl.ROLES) - declared)}")
        manifest = json.loads((pack / "brand.json").read_text(encoding="utf-8"))
        check("the emitted manifest never claims a validation it did not run",
              manifest["chart_palette_validated"] is False)

        # READ BACK. The generated header tells the reader to re-measure this pack after editing
        # it, so reading a pack off disk has to produce the same numbers as composing it. If it
        # did not, the emitted advice would be worse than none. Wrapped, because a reader that
        # RAISES must be a named failure and not an unwind past every other fixture.
        from_disk = attempt("a pack read back off disk measures the same as the model that "
                            "wrote it", lambda: measure(read_pack(pack / "theme.css")))
        if from_disk is not None:
            from_model = measure(snap(CANDIDATES[0].anchors))
            drift = [f"{a.mode} {a.label} disk {a.ratio:.4f} vs model {b.ratio:.4f}"
                     for a, b in zip(from_disk, from_model) if abs(a.ratio - b.ratio) > 1e-9]
            check("a pack read back off disk measures the same as the model that wrote it",
                  not drift, f"{drift}")

        # And an EDITED pack must be caught. This is the whole reason --measure exists: the header
        # written into every emitted pack promises it.
        edited = pack / "theme.css"
        rewritten, swapped = re.subn(r"^  --primary: .*$", "  --primary: #9BD4FF;",
                                     edited.read_text(encoding="utf-8"), count=1, flags=re.M)
        check("the selftest's own edit actually applied", swapped == 1,
              "the anchor did not match, so the check below would pass over an unedited pack")
        edited.write_text(rewritten, encoding="utf-8")
        broken = attempt("an edited pack that broke contrast is caught by --measure",
                         lambda: [r for r in measure(read_pack(edited)) if not r.passes])
        if broken is not None:
            check("an edited pack that broke contrast is caught by --measure", len(broken) >= 2,
                  f"only {len(broken)} pair(s) flagged after replacing --primary with a pale blue")

    # A pack with no `.dark` block must be refused, not measured as if light were both modes.
    # The fixture's `:root` is COMPLETE on purpose: with a partial one, a disabled guard still
    # raises on the first unresolvable role and the fixture passes for the wrong reason.
    checks += 1
    with tempfile.TemporaryDirectory(prefix="palette-candidates-selftest-") as tmp:
        lone = Path(tmp) / "theme.css"
        complete_root = "\n".join(f"  {role}: {value};"
                                  for role, value in composed["light"].items())
        lone.write_text(f"@theme {{\n  --color-x: #123456;\n}}\n:root {{\n{complete_root}\n}}\n",
                        encoding="utf-8")
        try:
            read_pack(lone)
            failures_found.append("a pack with no .dark block was read instead of refused")
        except Unusable:
            pass

    # ---- the catalogue stays a starting point, not a style menu -----------------------------
    # The BAND ITSELF is pinned, not just membership in it. "8 <= len <= high" is satisfied by
    # widening `high`, so a band-relative assertion cannot notice the catalogue turning into the
    # style menu this must not become. Same shape as CORPORA_GATES being pinned exactly: either
    # direction takes a deliberate edit here, with a reason.
    low, high = CATALOGUE_BAND
    check("the catalogue band is the declared 8-12", CATALOGUE_BAND == (8, 12),
          f"CATALOGUE_BAND is {CATALOGUE_BAND}; widening it is how a curated set becomes a menu")
    check("the catalogue holds 8-12 candidates", low <= len(CANDIDATES) <= high,
          f"{len(CANDIDATES)} candidates")
    slugs = [c.anchors.slug for c in CANDIDATES]
    check("candidate slugs are unique", len(set(slugs)) == len(slugs), f"{slugs}")
    check("every candidate names a real ramp",
          all(c.anchors.ramp in RAMPS for c in CANDIDATES))
    check("every candidate carries selection guidance",
          all(c.choose_when.strip() and c.character.strip() for c in CANDIDATES))

    # ---- type pairings ----------------------------------------------------------------------
    low, high = PAIRING_BAND
    check("the pairing band is the declared 6-8", PAIRING_BAND == (6, 8), f"{PAIRING_BAND}")
    check("the pairing set holds 6-8 entries", low <= len(PAIRINGS) <= high,
          f"{len(PAIRINGS)} pairings")
    incomplete = [s for s, p in PAIRINGS.items() if not all(p.get(r) for r in PAIRING_ROLES)]
    check("every type pairing declares sans, display and mono", not incomplete,
          f"incomplete: {incomplete}")
    # The absence that is doctrine, not an omission. BOTH directions, because the silent half is
    # a tautology on its own: with no pairing carrying a scale, a rule that matches nothing agrees
    # with a rule that works. The positive control is what tells them apart.
    check("no type pairing carries its own fluid type scale",
          not pairings_with_own_scale(PAIRINGS), f"forked: {pairings_with_own_scale(PAIRINGS)}")
    smuggled = {"rogue": {"sans": "A", "display": "B", "mono": "C",
                          "text-step-0": "clamp(1rem, 1vw, 1.125rem)"}}
    check("a pairing that DID carry a type scale would be caught",
          pairings_with_own_scale(smuggled) == ["rogue"],
          f"got {pairings_with_own_scale(smuggled)}")

    # ---- input handling ---------------------------------------------------------------------
    checks += 1
    try:
        normalise_hex("cornflowerblue")
        failures_found.append("an unparseable colour resolved instead of raising")
    except Unusable:
        pass
    check("a 3-digit hex expands", normalise_hex("#abc") == "#AABBCC")
    checks += 1
    try:
        snap(Anchors("x", "chartreuse", "#000000", "#FFFFFF"))
        failures_found.append("an unknown ramp composed instead of raising")
    except Unusable:
        pass

    if failures_found:
        print(f"SELFTEST FAILED -- {len(failures_found)} of {checks} checks:", file=sys.stderr)
        for failure in failures_found:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"palette_candidates selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="palette_candidates.py",
        description="Measured starting palettes for a brand pack, and the snap path for a "
                    "client's own brand colour.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="the catalogue + measured figures")
    group.add_argument("--list-fonts", action="store_true", help="the optional type pairings")
    group.add_argument("--emit", metavar="SLUG", help="write a complete pack for one candidate")
    group.add_argument("--snap", metavar="HEX", help="snap a client brand colour to the roles")
    group.add_argument("--measure", metavar="PACK",
                       help="measure a pack that exists on disk (use after editing an emitted one)")
    group.add_argument("--check", action="store_true",
                       help="gate: every candidate clears WCAG 1.4.3 in both modes")
    group.add_argument("--selftest", action="store_true", help="prove the rules fire AND stay quiet")
    parser.add_argument("--out", metavar="DIR", help="pack directory to write into")
    parser.add_argument("--neutral", default="cool", choices=sorted(RAMPS),
                        help="neutral ramp for --snap (default: cool)")
    parser.add_argument("--slug", help="pack slug; defaults to the --out directory name")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    # OUTSIDE the handler below, deliberately. Routed through it, an unexpected `Unusable` from
    # anywhere in the selftest unwinds past every finding already collected and the run reports
    # exit 2 with no fixture named — which reads, to a mutation checker, exactly like a caught
    # mutation. A crash is not a verdict.
    if args.selftest:
        return selftest()

    try:
        if args.list:
            return cmd_list()
        if args.list_fonts:
            return cmd_list_fonts()
        if args.check:
            return cmd_check()
        if args.emit:
            return cmd_emit(args.emit, args.out, args.slug)
        if args.snap:
            return cmd_snap(args.snap, args.neutral, args.slug or "client", args.out)
        if args.measure:
            return cmd_measure(args.measure)
    except Unusable as exc:
        print(f"palette_candidates: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
