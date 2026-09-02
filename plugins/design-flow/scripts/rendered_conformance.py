#!/usr/bin/env python3
"""rendered-page design-system conformance — design-flow (#107).

`/design-flow:audit` judged conformance by **reading source files** — grepping for raw hex,
breakpoint chains, hardcoded sizes. That misses everything that only exists once the cascade
resolves, and it cannot see what the user actually gets: a colour injected by a third-party
partial, a role token that never resolved, a focus rule that no longer matches the element it
was written for. #107 asks for the measurement to move into the browser, where the numbers are
decisive rather than suggestive.

THE SPLIT, and it is the whole design. The browser **measures**; this script **judges**.

  collector (browser, `commands/audit.md`)   ->  snapshot.json  ->  this script (verdicts)

Nothing in the collector decides anything: it resolves the app's own tokens, walks the DOM, and
writes computed values. Every count, threshold and finding is computed here, in stdlib Python,
over a JSON file — so every rule is testable offline against a fixture, which is the only reason
a browser-driven check can carry a `--selftest` and a declared mutation at all.

That split also disposes of the hardest correctness problem for free. Comparing colours across
CSS colour spaces (is `oklch(62.3% 0.214 259.8)` the app's `--primary`?) is a minefield of
rounding and gamut mapping. It never arises: the collector resolves each role token **through the
same browser, in the same run**, so a conformant `bg-primary` and the `--primary` probe are
serialized identically and set membership settles it. Python does not do colour maths, and must
not start.

WHY FALSE POSITIVES DECIDE EVERYTHING HERE. A conformance linter that fires on correct input is
switched off, and then catches nothing at all. So every rule below is written to fail **silent**
rather than loud, and the non-coverage list is as load-bearing as the rule list.

RULES. Severity `drift` is zero-tolerance (any hit fails); `trend` is count-based against a
threshold that only decides *blocking* — the count itself is always printed, because the count is
the metric #107 actually asks for.

  drift  literal-colour             an opaque painted colour tracing to no role token
  drift  numbered-step-binding      markup bound to a numbered palette step (bg-primary-700)
  drift  focus-ring-missing         an interactive element no focus rule styles
  drift  tap-target-small           a non-inline control under 44px tall at a mobile viewport
  drift  icon-only-unnamed          an interactive element with no accessible name
  drift  aria-controls-no-expanded  a disclosure trigger with aria-controls and no aria-expanded
  drift  horizontal-overflow        the document scrolls sideways at the measured viewport
  drift  off-scale-type             a rendered font-size outside the fluid --text-step-* scale
  drift  radius-off-scale           a border-radius tracing to no radius token
  trend  dark-variant-sprawl        `dark:` utility occurrences (a role layer needs ~0)
  trend  breakpoint-driven-layout   breakpoint-variant occurrences (intrinsic layout needs few)

NOT COVERED — three of them are in #107's acceptance list, and dropping them is a finding, not
an omission. Each would fire on doctrine-conformant input, which is the one outcome that ends
with the tool disabled:

  * **px space off the fluid scale.** foundations-tokens.md's *Control density* table prescribes
    `px-3 py-2` (12px/8px) for every control — values that come from Tailwind's numeric scale,
    **not** from `--space-*`. A rule flagging px padding outside the fluid scale therefore fires
    on our own prescription, and no computed px value can tell the two systems apart.
  * **chrome-vs-content type step — UNBLOCKED as of #306, and now the best-justified rule to add
    next.** This entry used to read "two doctrine files disagree, so a rule would fire on our own
    reference implementation". That disagreement is **resolved**: #306 settled it in favour of
    foundations-tokens.md's measured calibration and moved **eleven** sites to `text-step--1` — the
    six named here plus the button `BASE` in two files, the form-input base in a third, and a
    `<table>` in two. The blocker this entry recorded no longer exists.
    Note the failure mode has inverted, so read the exception list before implementing: a rule must
    still NOT fire on the legitimate `text-step-0` uses foundations-tokens.md now enumerates — alert
    body, card description, page lede, `<dd>` values (whose `<dt>` is chrome), and AvatarComponent's
    deliberate sm/md/lg ramp. Chrome is decidable here precisely because this linter resolves real
    elements: `button`, `input`, `select`, `textarea`, `label`, `th`, `[role=menuitem]`.
  * **alpha-modified colours.** `bg-primary/90` compiles (Tailwind v4) to
    `color-mix(in oklab, var(--color-primary) 90%, transparent)`, and `/90` shifts are
    doctrine-blessed (components.md hover, `ring-ring/30`). Decomposing a mix back to its base is
    colour maths this script refuses to do, and there is no declared opacity scale to check the
    step against — so any colour with alpha < 1 is counted as a fact and never judged.
  * **bespoke flex/grid chains where a primitive fits.** A judgement call about intent; the
    breakpoint-occurrence trend is the mechanical half, and the agent's checklist keeps the rest.

EXTERNALLY VERIFIED CLAIMS (each is load-bearing for a rule or a carve-out):

  1. Tailwind v4 opacity modifiers compile to `color-mix(in oklab, <color> N%, transparent)`
     (tailwindcss.com/docs/colors; `in oklab` per tailwindlabs/tailwindcss#15201, chosen over
     oklch for a Safari bug) — so an opacity modifier always lands with alpha < 1, which is what
     makes "judge opaque colours only" a sound carve-out rather than a hole.
  2. The v4 default palette is authored in `oklch()` (tailwindcss.com/docs/colors) — so stock
     palette drift (`bg-blue-700`) resolves to a value no brand role can accidentally match.
  3. Tailwind ring utilities are **box-shadow**, not outline (`--tw-ring-shadow: 0 0 0 2px`,
     tailwindcss.com/docs/box-shadow) — so box-shadow must count as a focus indicator, or every
     doctrine-conformant `focus-visible:ring-2` would be reported.
  4. `box-shadow` and `text-shadow` **compute to `none`** in forced-colors mode
     (css-color-adjust-1 §"Forced Color Palette") — so a shadow-only ring is invisible there.
     Reported as a FACT with its count, never as a finding — but the REASON changed and the old one
     should not be restored. It used to be "our own doctrine prescribes
     `focus-visible:outline-none focus-visible:ring-2`, so a rule would fire on 100% of conformant
     components". **#305 fixed that.** v3's accessible `outline-none` was renamed `outline-hidden` in
     v4 while v4's `outline-none` really does set `outline-style: none`
     (tailwindcss.com/docs/upgrade-guide); our nine sites had been carried through the migration
     unchanged and now all say `outline-hidden`, so a conformant component keeps a forced-colors
     indicator. It stays a counted fact for a narrower reason: this linter measures a page an app
     author wrote, and a shadow-only ring there may be a deliberate choice we do not govern.
     `lint_self_consistency.py`'s `v4-outline-none` rule is what holds OUR doctrine to it.

WHAT A SKIP MEANS. A rule whose basis the app never provided is **skipped and named**, never
counted as clean: no `--text-step-*` resolved means `off-scale-type` did not run, and printing a
clean bill of health for a rule that never executed is the exact defect `build_coverage.py
--selftest` shipped. Two states are worse than skipping and are therefore exit 2: a snapshot with
no elements, and one with no role tokens — with an empty colour basis EVERY colour traces to no
role, so `literal-colour` would flood, which is how this tool would earn being switched off on
its first run.

Stdlib only, no network, no browser: it reads a JSON file. Same constraint as
`brand_pack_lint.py` and `setup_doctrine_crosscheck.py`.

Usage:
  python3 rendered_conformance.py snapshot.json [more.json …]
  python3 rendered_conformance.py --schema           # print the snapshot contract and exit
  python3 rendered_conformance.py --selftest         # near-miss fixtures; prove the rules fire
  python3 rendered_conformance.py --check-collector  # node --check the shipped collector
  python3 rendered_conformance.py snap.json --max-dark 0 --max-breakpoint 10

Exit: 0 conformant (trends under threshold) · 1 drift, or a trend over threshold ·
      2 usage/environment (snapshot missing, unreadable, wrong schema, or nothing to judge).

The 1/2 split is the same one `setup_doctrine_crosscheck.py` documents: 1 means "a defect a
maintainer must fix", 2 means "this check could not run". Collapsing them sends someone hunting a
defect that does not exist.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

SCHEMA = "design-flow/rendered-conformance/1"

# --------------------------------------------------------------------------
# doctrine constants
#
# Deliberately named and module-level so the offline LLM-tell detector (#157) can import them
# instead of restating them — its acceptance criteria require the radius and palette-step rules
# to be defined once. Nothing here is inferred; each cites the doctrine file it comes from.
# --------------------------------------------------------------------------

# `min-h-touch` — foundations-tokens.md "Utilities to keep" (`min-height: 44px`).
TOUCH_MIN_PX = 44.0

# Below this width the tap-target and overflow rules apply. `sm` is Tailwind's 640px breakpoint;
# a snapshot taken at a desktop width says nothing about either.
MOBILE_MAX_WIDTH = 640

# Colour utility prefixes — the families a numbered palette step can be bound through.
# foundations-tokens.md "Never bind markup to a numbered step".
COLOUR_UTILITIES = (
    "bg", "text", "border", "ring", "divide", "from", "via", "to", "outline",
    "decoration", "accent", "caret", "fill", "stroke", "shadow", "placeholder",
)

# A numbered palette step. 50/950 plus the hundreds — Tailwind's shape, and the shape our own
# `--color-fm-slate-*` primitives follow.
PALETTE_STEP = re.compile(r"-(?:50|950|[1-9]00)\Z")

# Tailwind's own breakpoint variants. `min-[…]`/`max-[…]` arbitrary variants are deliberately
# NOT counted: they are rare, and counting them would need a second, looser pattern whose false
# positives land in the trend that decides blocking.
BREAKPOINT_VARIANTS = ("sm", "md", "lg", "xl", "2xl")

# UA-scaled tags: the UA sizes these RELATIVE to their parent, so their computed size is off any
# absolute scale by construction and flagging it would be a false positive on untouched markup.
# Measured in Chrome rather than assumed — all three resolve to 13.3333px inside a 16px parent
# (83.33%: `font-size: smaller` for sub/sup, `0.8333em` for small).
UA_SCALED_TAGS = frozenset({"sub", "sup", "small"})

# Tags that carry no design-system type/colour of their own.
SKIP_TAGS = frozenset({"script", "style", "template", "head", "meta", "link", "title", "br",
                       "svg", "path", "g", "circle", "rect", "line", "polyline", "polygon",
                       "use", "defs", "symbol", "clippath", "mask"})

# Interactive elements, decided HERE rather than in the collector so the definition is testable.
INTERACTIVE_TAGS = frozenset({"button", "select", "textarea", "summary"})
INTERACTIVE_ROLES = frozenset({"button", "link", "menuitem", "menuitemcheckbox", "tab",
                               "checkbox", "radio", "switch", "option", "combobox", "slider"})
# `hidden` inputs paint nothing; `image`/`submit`/`reset`/`checkbox`… all do.
NON_INTERACTIVE_INPUT_TYPES = frozenset({"hidden"})

# A focus indicator must survive being *looked at*. An outline whose style is one of these draws
# nothing, which is exactly what Tailwind v4's `outline-none` emits.
INVISIBLE_OUTLINE_STYLES = frozenset({"none", "hidden", ""})

# Properties that can carry a focus indicator. `--tw-ring-shadow` is here because a v4 ring
# declares the custom property and composes `box-shadow` in a base rule the element also matches
# — reading only `box-shadow` would miss the ring the doctrine actually prescribes.
SHADOW_PROPS = ("box-shadow", "--tw-ring-shadow", "--tw-ring-color", "--tw-inset-ring-shadow",
                "--tw-shadow")
REPAINT_PROPS = ("background-color", "border-color", "border-top-color", "border-bottom-color",
                 "border-left-color", "border-right-color", "color", "border-width",
                 "border-style", "text-decoration-line", "text-decoration")

# A radius that is always legitimate whatever the scale says: a square corner, and a pill.
FULL_RADIUS_MIN_PX = 999.0

# Findings per rule before the report truncates. Truncation is always PRINTED — a silent cap
# reads as "nothing more to see", which is the same lie as a skip reported as a pass.
MAX_FINDINGS_PER_RULE = 12


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

class InputError(Exception):
    """A snapshot could not be read, decoded, or trusted.

    Raised rather than skipped: with one snapshot unread the run has no honest verdict in either
    direction, and returning 1 (drift) for an unreadable file sends a maintainer hunting a defect
    that does not exist. Callers turn this into exit 2.
    """


@dataclass(frozen=True)
class Finding:
    """One rule hit. `severity` is 'drift' (zero-tolerance) or 'trend' (count vs threshold).

    Constructed with the rule name as a literal first argument in the rule that emits it, which
    is the convention `scripts/mutation_check_selftest.py` reads to prove every named rule has a
    declared mutation behind it. Hiding the name behind a variable would make this file's rules
    invisible to that check — a twelfth rule could then be bolted on with nothing proving its
    fixture would fail, which is the #100 defect that check exists for.
    """

    rule: str
    severity: str
    message: str
    ref: str = ""


class Report:
    """Findings, plus the three states a report must distinguish.

    * **fact** — a measurement (the counts #107 asks for). Suppressed by `--quiet`.
    * **notice** — a limit on what was covered (a truncation cap). ALWAYS printed: a cap that
      disappears under `--quiet` reads as "nothing more to see", which is the same lie as a skip
      reported as a pass.
    * **skip** — a rule that did not run, named. Never a pass.
    """

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.findings: list[Finding] = []
        self.facts: list[str] = []
        self.notices: list[str] = []
        self.skipped: list[str] = []
        # Set when the snapshot gave nothing to judge. `main` turns this into exit 2 rather than
        # the clean 0 that "no findings" would otherwise produce.
        self.no_input = False

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def fact(self, message: str) -> None:
        self.facts.append(message)

    def notice(self, message: str) -> None:
        self.notices.append(message)

    def skip(self, rule: str, why: str) -> None:
        """A rule that did not run. Named, never silent: a skip is not a pass."""
        self.skipped.append(f"{rule}: {why}")

    def rules_hit(self) -> list[str]:
        return sorted({f.rule for f in self.findings})

    @property
    def ok(self) -> bool:
        return not self.findings and not self.no_input


# --------------------------------------------------------------------------
# colour canonicalisation
#
# Both sides of every comparison were serialized by the SAME browser in the SAME run, so this
# only has to survive spelling: whitespace, case, and the two ways an opaque colour can be
# written (`rgb(…)` vs `rgba(…, 1)`). It deliberately does no colour-space conversion — see the
# module docstring. A form it does not recognise returns None and is COUNTED, never flagged:
# an unparsed value must not become a finding, or the first browser that serializes something new
# produces a flood.
# --------------------------------------------------------------------------

_HEX = re.compile(r"\A#([0-9a-f]{3,8})\Z")
_FUNC = re.compile(r"\A([a-z][a-z0-9-]*)\((.*)\)\Z", re.S)
_KNOWN_FUNCS = frozenset({"rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch",
                          "color"})


def _num(token: str) -> str:
    """Normalise a numeric token: `0.500` and `.5` and `0.5` all canonicalise the same."""
    token = token.strip()
    suffix = ""
    if token.endswith("%"):
        token, suffix = token[:-1], "%"
    try:
        value = float(token)
    except ValueError:
        return token + suffix
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return (text or "0") + suffix


def _alpha_of(token: str) -> float | None:
    token = token.strip()
    if token in ("none", ""):
        return 1.0
    percent = token.endswith("%")
    try:
        value = float(token[:-1] if percent else token)
    except ValueError:
        return None
    return value / 100.0 if percent else value


def canon_colour(raw: object) -> tuple[str, float] | None:
    """-> (opaque-key, alpha), or None when the form is not recognised.

    The opaque key intentionally drops alpha so `rgb(0, 119, 204)` and `rgba(0, 119, 204, 0.9)`
    share a key: the caller decides what to do with a translucent value (nothing — see the
    docstring), and keeping them comparable is what lets the FACT count them.
    """
    if not isinstance(raw, str):
        return None
    value = " ".join(raw.strip().lower().split())
    if not value:
        return None
    if value in ("transparent", "rgba(0, 0, 0, 0)", "rgba(0,0,0,0)"):
        return ("transparent", 0.0)
    if value == "currentcolor":
        # Never a computed value for a colour property (it resolves to the element's `color`),
        # so seeing it means the collector recorded a specified value. Unjudgeable, not a hit.
        return None

    hexed = _HEX.match(value)
    if hexed:
        digits = hexed.group(1)
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8):
            return None
        red, green, blue = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
        return (f"rgb({red}, {green}, {blue})", alpha)

    func = _FUNC.match(value)
    if not func:
        return None
    name, body = func.group(1), func.group(2)
    if name not in _KNOWN_FUNCS:
        return None

    alpha = 1.0
    if "/" in body:
        body, _, alpha_token = body.rpartition("/")
        parsed = _alpha_of(alpha_token)
        if parsed is None:
            return None
        alpha = parsed
    parts = [p for p in re.split(r"[,\s]+", body.strip()) if p]
    if "," in func.group(2) and len(parts) == 4:
        parsed = _alpha_of(parts.pop())
        if parsed is None:
            return None
        alpha = parsed
    if name == "color":
        if len(parts) < 4:
            return None
        space, channels = parts[0], parts[1:4]
        return (f"color({space} {' '.join(_num(c) for c in channels)})", alpha)
    if len(parts) < 3:
        return None
    base = "rgb" if name == "rgba" else ("hsl" if name == "hsla" else name)
    channels = " ".join(_num(c) for c in parts[:3])
    if base == "rgb":
        channels = ", ".join(_num(c) for c in parts[:3])
    return (f"{base}({channels})", alpha)


# --------------------------------------------------------------------------
# snapshot access
# --------------------------------------------------------------------------

def _basis_colours(snapshot: dict) -> dict[str, str]:
    """canonical opaque key -> the role token that resolves to it.

    Every value the collector probed for a role lands here, including the
    `color-mix(in oklab, … 100%, transparent)` spelling — without that second probe a
    `bg-primary/100` (alpha 1, oklab serialization) would trace to no role and be reported,
    which is a false positive on a class the doctrine permits.
    """
    out: dict[str, str] = {}
    basis = snapshot.get("basis") or {}
    for token, values in sorted((basis.get("color") or {}).items()):
        for value in (values if isinstance(values, list) else [values]):
            canon = canon_colour(value)
            if canon and canon[1] == 1.0:
                out.setdefault(canon[0], token)
    return out


def _basis_lengths(snapshot: dict, key: str) -> dict[str, str]:
    """canonical px string -> token, for a length basis (`fontSize`, `radius`)."""
    out: dict[str, str] = {}
    basis = (snapshot.get("basis") or {}).get(key) or {}
    for token, value in sorted(basis.items()):
        px = canon_px(value)
        if px is not None:
            out.setdefault(px, token)
    return out


def canon_px(raw: object) -> str | None:
    """A computed length as a canonical string, rounded to 0.1px.

    Rounding is not a tolerance for colour-style drift: computed `clamp()` lengths carry
    sub-pixel fractions that differ in the last digit between the probe and the element even when
    both resolve the same token, and a rule that fires on 14.400001 vs 14.4 is a rule nobody
    keeps.
    """
    if isinstance(raw, (int, float)):
        return f"{round(float(raw), 1):.1f}"
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    if text.endswith("px"):
        text = text[:-2]
    try:
        return f"{round(float(text), 1):.1f}"
    except ValueError:
        return None


def _classes(element: dict) -> list[str]:
    raw = element.get("classes")
    if isinstance(raw, list):
        return [str(c) for c in raw]
    if isinstance(raw, str):
        return raw.split()
    return []


def base_utility(cls: str) -> str:
    """Strip variant prefixes: `dark:hover:bg-primary-700` -> `bg-primary-700`.

    Splits on the LAST colon, so an arbitrary variant containing a colon
    (`[&[data-x]:hover]:bg-primary`) yields a fragment that matches no rule. That direction is
    deliberate: an unparsed variant chain goes SILENT rather than producing a finding whose
    class name the reader cannot find in the markup.
    """
    return cls.rpartition(":")[2]


def variant_prefixes(cls: str) -> list[str]:
    head = cls.rpartition(":")[0]
    return [p for p in head.split(":") if p] if head else []


def is_interactive(element: dict) -> bool:
    tag = str(element.get("tag", "")).lower()
    role = str(element.get("role", "") or "").lower()
    if role in INTERACTIVE_ROLES:
        return True
    if role:
        # An explicit non-interactive role wins over the tag: `<button role="presentation">` in a
        # composite widget is not the tab stop, and flagging it would be a false positive.
        return False
    if tag in INTERACTIVE_TAGS:
        return True
    if tag == "input":
        return str(element.get("type", "") or "").lower() not in NON_INTERACTIVE_INPUT_TYPES
    if tag == "a":
        return bool(element.get("href"))
    tabindex = element.get("tabindex")
    return tabindex is not None and str(tabindex) != "-1"


def is_inline_link_in_text(element: dict) -> bool:
    """An `<a>` inside a sentence — the one target-size exemption every design system makes.

    Scoped to `display: inline` on an `<a>`, and NOT to "display starts with inline", which is the
    shape this began as. Every native `<button>` computes to `inline-block` (Chrome UA), so the
    looser test exempted every button on the page from the touch floor — a silent hole found by
    running the collector against a real page. The exemption also requires surrounding text: an
    icon link alone in a toolbar is a tap target, not prose.
    """
    if str(element.get("tag", "")).lower() != "a":
        return False
    if str(element.get("display", "")).strip().lower() != "inline":
        return False
    try:
        own = int(element.get("textLength") or 0)
        around = int(element.get("parentTextLength") or 0)
    except (TypeError, ValueError):
        return False
    return around > own + 1


def is_visible(element: dict) -> bool:
    """Painted and exposed. The `ariaHidden` term is load-bearing for every rule that calls this:
    an element inside an `aria-hidden="true"` subtree is not in the accessibility tree, so
    demanding a name, a focus ring or a touch target from it would be a false positive."""
    rect = element.get("rect") or {}
    try:
        width = float(rect.get("w", 0))
        height = float(rect.get("h", 0))
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0 and not element.get("ariaHidden")


def _ref(element: dict) -> str:
    return str(element.get("ref") or element.get("tag") or "?")


def _emit_capped(report: Report, hits: list[Finding]) -> None:
    """Emit up to MAX_FINDINGS_PER_RULE findings and, if truncated, say so out loud."""
    for finding in hits[:MAX_FINDINGS_PER_RULE]:
        report.add(finding)
    extra = len(hits) - MAX_FINDINGS_PER_RULE
    if extra > 0:
        report.notice(f"{hits[0].rule}: {extra} further hit(s) not listed (cap "
                      f"{MAX_FINDINGS_PER_RULE}/rule) — the total is {len(hits)}")


# --------------------------------------------------------------------------
# rules — one function each, so a mutation can be anchored per rule
# --------------------------------------------------------------------------

def rule_literal_colour(snapshot: dict, report: Report) -> None:
    """A painted colour that traces to no role token.

    Three carve-outs keep this quiet on correct input, and all three are load-bearing:

    * **Painted only.** The collector records a border colour only where a border is actually
      drawn, and `color` only on an element with its own text. An unpainted `border-color`
      inherits `currentcolor` or the UA's black on virtually every element in a document —
      judging it would flood a conformant page.
    * **Opaque only.** Alpha < 1 means an opacity modifier, which the doctrine blesses; see the
      module docstring. Counted as a fact.
    * **Grouped by value.** One finding per distinct colour with its occurrence count and up to
      three example refs, not one per element — 400 elements inheriting one wrong colour is one
      defect, and 400 findings is a report nobody reads.
    """
    basis = _basis_colours(snapshot)
    if not basis:
        report.no_input = True
        report.add(Finding(
            "literal-colour", "drift",
            "no role tokens resolved from the page — either the collector ran before the "
            "stylesheet applied, or this app has no role layer. With an empty basis EVERY colour "
            "traces to no role, so this rule would flood; refusing to run is the honest verdict.",
        ))
        return

    groups: dict[str, list[tuple[str, str]]] = {}
    translucent = 0
    unparsed = 0
    considered = 0
    for element in snapshot.get("elements") or []:
        if str(element.get("tag", "")).lower() in SKIP_TAGS:
            continue
        for prop, raw in sorted((element.get("colours") or {}).items()):
            canon = canon_colour(raw)
            if canon is None:
                unparsed += 1
                continue
            key, alpha = canon
            if key == "transparent":
                continue
            considered += 1
            if alpha != 1.0:
                translucent += 1
                continue
            if key in basis:
                continue
            groups.setdefault(key, []).append((_ref(element), prop))

    report.fact(f"{considered} opaque painted colour value(s) judged against "
                f"{len(basis)} role-token spelling(s); {translucent} alpha-modified skipped")
    if unparsed:
        share = unparsed / max(1, unparsed + considered)
        report.notice(f"{unparsed} colour value(s) in an unrecognised form were NOT judged"
                      + (" — over a quarter of the page, so the canonicaliser has probably "
                         "drifted from what this browser serializes" if share > 0.25 else ""))

    hits = []
    for key in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        sites = groups[key]
        shown = ", ".join(f"{ref} ({prop})" for ref, prop in sites[:3])
        hits.append(Finding(
            "literal-colour", "drift",
            f"`{key}` is painted on {len(sites)} element(s) and traces to no role token "
            f"— e.g. {shown}. Bind to a role (`bg-primary`, `text-muted-foreground`, "
            f"`border-border`), never a literal or a stock palette colour.",
            sites[0][0],
        ))
    _emit_capped(report, hits)


def rule_numbered_step(snapshot: dict, report: Report) -> None:
    """Markup bound to a numbered palette step — the causal root of `dark:` sprawl.

    A numbered step encodes a fixed lightness, so it cannot follow a dark surface and every dark
    adjustment must then be written inline (foundations-tokens.md, "Never bind markup to a
    numbered step" — 20,825 `dark:` classes measured across 72 kit pages).

    The family is NOT allowlisted, deliberately: requiring a known palette name would fail open
    on the first brand primitive nobody added (`bg-acme-600`), the same way an extension
    allowlist fails open on the first file type nobody added. Precision comes from the two ends
    instead — a colour-utility prefix and a palette step — so `text-step-1`, `gap-4`, `z-50`,
    `w-1/2`, `border-2`, `grid-cols-3` and `shadow-md` all fall outside it, and the selftest
    carries all of them plus nine more as near misses.

    Those two conditions are the WHOLE test. An earlier draft also required a family segment
    (`stem.count("-") >= 2`, to reject a hypothetical `bg-50`); the mutation check found that no
    real utility can reach it, because anything with a colour prefix and a bare palette step is
    not a class Tailwind generates. A guard nothing can exercise, with a docstring explaining what
    it protects, is the claims-vs-enforcement defect this repo keeps finding — so it is gone
    rather than covered by a fixture for a class nobody writes.
    """
    groups: dict[str, list[str]] = {}
    for element in snapshot.get("elements") or []:
        for cls in _classes(element):
            base = base_utility(cls)
            prefix = base.split("-", 1)[0]
            if prefix not in COLOUR_UTILITIES:
                continue
            stem = base.rpartition("/")[0] or base   # tolerate an opacity modifier
            if not PALETTE_STEP.search(stem):
                continue
            groups.setdefault(base, []).append(_ref(element))

    hits = []
    for base in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        refs = groups[base]
        hits.append(Finding(
            "numbered-step-binding", "drift",
            f"`{base}` binds markup to a numbered palette step on {len(refs)} "
            f"element(s) (e.g. {', '.join(refs[:3])}) — a fixed lightness cannot follow "
            f"a dark surface, so every dark variant must then be written inline. Use "
            f"the role token.",
            refs[0],
        ))
    _emit_capped(report, hits)


def rule_focus_ring(snapshot: dict, report: Report) -> None:
    """An interactive element that no focus rule styles.

    Decided from the CASCADE, not by focusing anything: the collector reports, per element, the
    declarations of every stylesheet rule carrying `:focus`/`:focus-visible` whose selector the
    element matches. That avoids simulating focus, whose `:focus-visible` heuristics differ by
    browser and by how focus arrived — a programmatic `el.focus()` may not match
    `:focus-visible` at all, and the rule would then fire on every correctly styled button.

    An indicator is: a visible outline, any shadow/ring property, or a repaint (background,
    border, colour, underline). Tailwind's ring is box-shadow, so a shadow counts (claim 3) —
    a doctrine-conformant `focus-visible:outline-none focus-visible:ring-2` is silent here.
    """
    focusable = [e for e in snapshot.get("elements") or []
                 if is_interactive(e) and is_visible(e) and not e.get("disabled")]
    if not focusable:
        report.skip("focus-ring-missing", "no visible, enabled interactive element in the "
                                          "snapshot")
        return

    unmeasured = [e for e in focusable if e.get("focus") is None]
    if unmeasured:
        report.skip("focus-ring-missing",
                    f"{len(unmeasured)} interactive element(s) carry no focus record — the "
                    f"collector could not read the stylesheet rules for them (a cross-origin "
                    f"sheet throws on .cssRules); they were NOT judged")

    shadow_only = 0
    hits = []
    for element in focusable:
        focus = element.get("focus")
        if focus is None:
            continue
        declarations = {str(k).lower(): str(v).strip().lower()
                        for k, v in (focus.get("declarations") or {}).items()}
        # The shorthand counts, and an unreadable width does not veto. `outline: 2px solid
        # var(--ring)` is the fix this rule should be recommending, so reading only
        # `outline-style` would report the one focus style that survives forced colors. Likewise a
        # width of `medium` or a var() is unparseable, and treating unparseable as zero would
        # report a visible outline as missing — only an EXPLICIT zero kills it.
        shorthand = declarations.get("outline", "")
        style_visible = declarations.get("outline-style", "") not in INVISIBLE_OUTLINE_STYLES
        if shorthand:
            style_visible = "none" not in shorthand and "hidden" not in shorthand
        width_token = declarations.get("outline-width")
        width_is_zero = width_token is not None and canon_px(width_token) == "0.0"
        has_outline = style_visible and not width_is_zero
        has_shadow = any(p in declarations and declarations[p] not in ("none", "")
                         for p in SHADOW_PROPS)
        has_repaint = any(p in declarations for p in REPAINT_PROPS)
        if has_outline or has_shadow or has_repaint:
            if has_shadow and not has_outline:
                shadow_only += 1
            continue
        declared = ("no matching focus rule at all" if not declarations
                    else "matched rules declare " + ", ".join(sorted(declarations)))
        hits.append(Finding(
            "focus-ring-missing", "drift",
            f"<{element.get('tag')}> is interactive but no `:focus-visible` rule matching it "
            f"declares any indicator ({declared}) — a keyboard user cannot see where they are.",
            _ref(element),
        ))
    _emit_capped(report, hits)

    if shadow_only:
        # A fact, not a finding: our own doctrine prescribes the shadow-only idiom, so a rule
        # here would fire on 100% of conformant components and be switched off within a day.
        report.fact(
            f"{shadow_only} of {len(focusable)} interactive element(s) rely on a shadow/ring "
            "ALONE for focus. `box-shadow` computes to `none` in forced-colors mode "
            "(css-color-adjust-1), so those rings vanish there; pair the ring with "
            "`outline-hidden` (v4's accessible spelling) or a real outline."
        )


def rule_tap_target(snapshot: dict, report: Report) -> None:
    """A control shorter than the 44px touch floor at a mobile viewport.

    Two carve-outs, both required to keep it honest:

    * **Mobile viewports only.** `min-h-touch` is about touch; a 1280px snapshot says nothing.
    * **Not an inline link in running text.** WCAG's own target-size criteria exempt a link
      inside a sentence, and so does every real design system — flagging every inline `<a>` in a
      paragraph is how this rule would get switched off. See `is_inline_link_in_text`, which is
      deliberately narrower than it looks: a native `<button>` is `inline-block`, so a looser
      test silently exempts every button there is.

    Height only, because `min-h-touch` is `min-height: 44px`: adding an unstated width rule would
    flag doctrine-conformant markup.
    """
    viewport = (snapshot.get("viewport") or {}).get("width")
    try:
        width = float(viewport)
    except (TypeError, ValueError):
        report.skip("tap-target-small", "snapshot records no viewport width")
        return
    if width > MOBILE_MAX_WIDTH:
        report.skip("tap-target-small",
                    f"viewport is {width:.0f}px wide (> {MOBILE_MAX_WIDTH}px) — take a mobile "
                    f"snapshot to judge touch targets")
        return

    hits = []
    for element in snapshot.get("elements") or []:
        if not (is_interactive(element) and is_visible(element)):
            continue
        if is_inline_link_in_text(element):
            continue
        height = float((element.get("rect") or {}).get("h", 0))
        if height >= TOUCH_MIN_PX:
            continue
        hits.append(Finding(
            "tap-target-small", "drift",
            f"<{element.get('tag')}> renders {height:.0f}px tall at a {width:.0f}px "
            f"viewport, under the {TOUCH_MIN_PX:.0f}px touch floor — add `min-h-touch`.",
            _ref(element),
        ))
    _emit_capped(report, hits)


def rule_unnamed_control(snapshot: dict, report: Report) -> None:
    """An interactive element with no accessible name — the icon-only-button defect.

    The collector's name is an approximation of the accname algorithm (own text including
    `sr-only`, `aria-label`, `aria-labelledby` target text, `title`, a child image's `alt`, an
    SVG `<title>`). Approximating in the SILENT direction matters: every source of a name that
    the collector reads silences the rule, so a missed source can only cause a false negative.
    """
    hits = []
    for element in snapshot.get("elements") or []:
        # `is_visible` already excludes an aria-hidden subtree, and a DISABLED control is
        # deliberately still judged: it stays in the accessibility tree and a screen reader still
        # announces it, so "disabled" is no excuse for having no name. An earlier draft skipped
        # both here — the aria-hidden half was dead (is_visible had it) and the disabled half was
        # a carve-out nothing justified.
        if not (is_interactive(element) and is_visible(element)):
            continue
        name = str(element.get("name") or "").strip()
        if name:
            continue
        hits.append(Finding(
            "icon-only-unnamed", "drift",
            f"<{element.get('tag')}> is interactive with no accessible name — add an "
            f"`sr-only` label or `aria-label`; an icon alone names nothing.",
            _ref(element),
        ))
    _emit_capped(report, hits)


def rule_disclosure_expanded(snapshot: dict, report: Report) -> None:
    """A disclosure trigger with `aria-controls` and no `aria-expanded`.

    Narrow on purpose. "Looks like a disclosure" is not decidable from a snapshot, so the trigger
    is the pairing APG actually requires: something that CONTROLS another element and never says
    whether it is open. Elements carrying a different state attribute are excluded, because that
    is a different pattern with a different contract — a `role="tab"` uses `aria-selected` and a
    toggle button uses `aria-pressed`, and demanding `aria-expanded` from either would be wrong.

    `combobox` is deliberately NOT in that carve-out: `aria-expanded` is a **required** state of
    the role in WAI-ARIA, so a combobox with `aria-controls` and no `aria-expanded` is the very
    defect this rule is for. Excluding it because it "is a different pattern" would have hidden a
    real one.
    """
    hits = []
    for element in snapshot.get("elements") or []:
        aria = element.get("aria") or {}
        if not aria.get("controls"):
            continue
        if aria.get("expanded") is not None:
            continue
        role = str(element.get("role") or "").lower()
        if role in ("tab", "tablist", "radio", "option"):
            continue
        if aria.get("selected") is not None or aria.get("pressed") is not None:
            continue
        hits.append(Finding(
            "aria-controls-no-expanded", "drift",
            f"<{element.get('tag')}> has `aria-controls=\"{aria.get('controls')}\"` but no "
            f"`aria-expanded` — a disclosure trigger must announce its state.",
            _ref(element),
        ))
    _emit_capped(report, hits)


def rule_horizontal_overflow(snapshot: dict, report: Report) -> None:
    """The document scrolls sideways at the measured viewport.

    1px of slack, not zero: sub-pixel layout rounding makes an exact comparison fire on pages
    that do not actually scroll.
    """
    overflow = snapshot.get("overflow") or {}
    scroll = overflow.get("scrollWidth")
    client = overflow.get("clientWidth")
    if not isinstance(scroll, (int, float)) or not isinstance(client, (int, float)) or not client:
        report.skip("horizontal-overflow", "snapshot records no document scroll/client width")
        return
    if scroll - client <= 1:
        return
    report.add(Finding(
        "horizontal-overflow", "drift",
        f"the document is {scroll:.0f}px wide in a {client:.0f}px viewport "
        f"({scroll - client:.0f}px of horizontal scroll) — a fixed width, a long unbroken "
        f"string, or a negative margin is escaping the shell.",
        str(snapshot.get("url") or ""),
    ))


def rule_off_scale_type(snapshot: dict, report: Report) -> None:
    """A rendered font-size that no `--text-step-*` produces at this viewport.

    The basis is resolved by the browser at the SAME viewport as the measurement, so a fluid
    `clamp()` step and the element that uses it agree exactly — no interpolation happens here.
    Skipped, and named, when the app resolved no steps: judging type against an empty scale would
    report every size on the page.
    """
    basis = _basis_lengths(snapshot, "fontSize")
    if not basis:
        report.skip("off-scale-type",
                    "no `--text-step-*` token resolved from the page — nothing to judge type "
                    "against (this app may not use the fluid scale at all)")
        return

    groups: dict[str, list[str]] = {}
    for element in snapshot.get("elements") or []:
        tag = str(element.get("tag", "")).lower()
        if tag in SKIP_TAGS or tag in UA_SCALED_TAGS:
            continue
        size = canon_px(element.get("fontSize"))
        if size is None or size in basis:
            continue
        groups.setdefault(size, []).append(_ref(element))

    report.fact(f"type scale: {len(basis)} step(s) resolved "
                f"({', '.join(sorted(basis.values()))})")
    hits = []
    for size in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        refs = groups[size]
        hits.append(Finding(
            "off-scale-type", "drift",
            f"font-size {size}px on {len(refs)} element(s) (e.g. {', '.join(refs[:3])}) comes "
            f"from no `--text-step-*` — a fixed size breaks the fluid scale at every viewport "
            f"but one.",
            refs[0],
        ))
    _emit_capped(report, hits)


def rule_radius(snapshot: dict, report: Report) -> None:
    """A border-radius that traces to no radius token, plus the radius-language distribution.

    The distribution is the measurement #107 asks for (controls `md`, cards `lg`, pills `full`
    — foundations-tokens.md "Validated by measurement"), and it is a FACT: which radius belongs
    on which element is a judgement about what that element IS, and a snapshot cannot tell a card
    from a panel. What is mechanical is whether a value is on the scale at all, which is what
    catches `rounded-[7px]` and hand-written CSS.
    """
    basis = _basis_lengths(snapshot, "radius")
    if not basis:
        report.skip("radius-off-scale",
                    "no `--radius*` token resolved from the page — nothing to judge radii "
                    "against")
        return

    distribution: dict[str, int] = {}
    groups: dict[str, list[str]] = {}
    for element in snapshot.get("elements") or []:
        # Per ELEMENT, not per corner. An element with four equal corners is one radius decision;
        # counting corners multiplied every number by four, so a single `rounded-[7px]` button
        # reported as "4 element(s)" and the distribution read four times too high. Found by
        # running this against a real page, not by a fixture.
        seen: set[str] = set()
        for corner in element.get("radius") or []:
            value = canon_px(corner)
            if value is None or value in seen:
                continue
            seen.add(value)
            if float(value) == 0.0:
                continue
            if float(value) >= FULL_RADIUS_MIN_PX:
                distribution["full"] = distribution.get("full", 0) + 1
                continue
            token = basis.get(value)
            distribution[token or f"{value}px (off-scale)"] = (
                distribution.get(token or f"{value}px (off-scale)", 0) + 1)
            if token is None:
                groups.setdefault(value, []).append(_ref(element))

    if distribution:
        shown = ", ".join(f"{name} x{count}" for name, count in
                          sorted(distribution.items(), key=lambda kv: (-kv[1], kv[0])))
        report.fact(f"radius language: {shown}")
    hits = []
    for value in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        refs = groups[value]
        hits.append(Finding(
            "radius-off-scale", "drift",
            f"border-radius {value}px on {len(refs)} element(s) (e.g. {', '.join(refs[:3])}) "
            f"traces to no `--radius*` token — the radius language is the scale, not an "
            f"arbitrary value.",
            refs[0],
        ))
    _emit_capped(report, hits)


def rule_dark_sprawl(snapshot: dict, report: Report, threshold: int) -> None:
    """`dark:` utility occurrences. A role layer re-points once under `.dark` and needs ~0.

    Occurrences, not distinct classes: the measurement that motivated #107 counted 20,825 across
    72 rendered pages (~289/page), and 50 rows carrying the same `dark:bg-gray-800` is 50 inline
    variants a role token would have removed.
    """
    total = 0
    examples: list[str] = []
    for element in snapshot.get("elements") or []:
        for cls in _classes(element):
            if "dark" in variant_prefixes(cls):
                total += 1
                if len(examples) < 3:
                    examples.append(f"{_ref(element)} `{cls}`")
    report.fact(f"`dark:` occurrences: {total} (threshold {threshold})")
    if total <= threshold:
        return
    report.add(Finding(
        "dark-variant-sprawl", "trend",
        f"{total} `dark:` occurrence(s), over the threshold of {threshold} — a role-token "
        f"system re-points the roles under `.dark` and needs none. Each one is markup "
        f"compensating for a colour that cannot follow its surface. e.g. {'; '.join(examples)}",
    ))


def rule_breakpoint_layout(snapshot: dict, report: Report, threshold: int) -> None:
    """Breakpoint-variant occurrences — the signal for breakpoint-driven layout.

    A trend, never a defect per class: a breakpoint is sometimes exactly right. The number is
    what carries information (6,151 across the 72 measured pages), because an intrinsic layout
    built from `grid-auto`/`Switcher`/`Sidebar` and fluid `clamp()` tokens needs a handful.
    """
    total = 0
    examples: list[str] = []
    for element in snapshot.get("elements") or []:
        for cls in _classes(element):
            if any(p in BREAKPOINT_VARIANTS for p in variant_prefixes(cls)):
                total += 1
                if len(examples) < 3:
                    examples.append(f"{_ref(element)} `{cls}`")
    report.fact(f"breakpoint occurrences: {total} (threshold {threshold})")
    if total <= threshold:
        return
    report.add(Finding(
        "breakpoint-driven-layout", "trend",
        f"{total} breakpoint-variant occurrence(s), over the threshold of {threshold} — reach "
        f"for an intrinsic primitive (`grid-auto`, `Layout::Switcher`, `Layout::Sidebar`) and "
        f"the fluid tokens before a breakpoint pair. e.g. {'; '.join(examples)}",
    ))


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def analyse(snapshot: dict, max_dark: int = 5, max_breakpoint: int = 25,
            label: str = "") -> Report:
    report = Report(label or str(snapshot.get("url") or "snapshot"))

    if snapshot.get("schema") != SCHEMA:
        report.no_input = True
        report.add(Finding(
            "snapshot-schema", "drift",
            f"snapshot schema is {snapshot.get('schema')!r}, expected {SCHEMA!r} — the collector "
            f"and this analyser have drifted apart; re-run the collector from this plugin "
            f"version.",
        ))
        return report

    elements = snapshot.get("elements")
    if not isinstance(elements, list) or not elements:
        report.no_input = True
        report.add(Finding(
            "snapshot-empty", "drift",
            "the snapshot carries no elements — this run judged NOTHING, which is not a pass. "
            "Check the collector ran after the page finished rendering.",
        ))
        return report

    report.fact(f"{len(elements)} element(s) at "
                f"{(snapshot.get('viewport') or {}).get('width', '?')}px, theme "
                f"{snapshot.get('theme', '?')}")
    if snapshot.get("truncated"):
        report.notice(f"the collector stopped at its element cap ({len(elements)}) — the page has "
                      f"more; findings below are therefore a floor, not a total")
    # A cross-origin stylesheet throws on `.cssRules`, so its focus rules are invisible. The
    # collector nulls every element's focus record when it could read NO rules at all (then
    # `focus-ring-missing` skips by name); when it read some, the rule still runs, because an app's
    # own utilities live in its own same-origin sheet. Either way the count is stated: silently
    # judging a page whose stylesheets were partly unreadable is how a false positive gets shipped
    # with a straight face.
    unreadable = snapshot.get("unreadableSheets") or 0
    if unreadable:
        report.notice(f"{unreadable} stylesheet(s) could not be read (cross-origin `.cssRules`); "
                      f"{snapshot.get('focusRuleCount', 0)} focus rule(s) were readable. Focus "
                      f"findings are judged on those only.")

    rule_literal_colour(snapshot, report)
    if report.no_input:
        return report      # an empty colour basis means the snapshot cannot be trusted at all
    rule_numbered_step(snapshot, report)
    rule_focus_ring(snapshot, report)
    rule_tap_target(snapshot, report)
    rule_unnamed_control(snapshot, report)
    rule_disclosure_expanded(snapshot, report)
    rule_horizontal_overflow(snapshot, report)
    rule_off_scale_type(snapshot, report)
    rule_radius(snapshot, report)
    rule_dark_sprawl(snapshot, report, max_dark)
    rule_breakpoint_layout(snapshot, report, max_breakpoint)
    return report


COLLECTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "conformance_collector.js")


def check_collector(node_bin: str = "node", collector: str = COLLECTOR) -> int:
    """Syntax-check the shipped collector.

    It exists because the collector is the one thing here that no other gate reads.
    `lint_markdown_code.py` runs `node --check` over JS in *markdown fences*, and
    `lint_self_consistency.py` proves the command's `${CLAUDE_PLUGIN_ROOT}` pointer resolves — but
    a shipped `.js` FILE is checked by neither, and this repo's own doctrine is that the code we
    hand a user's browser gets verified rather than trusted. Keeping the check next to the
    collector keeps that promise without a second copy of the collector in markdown, which is the
    only other way to earn the coverage.

    A missing `node` prints a SKIP and exits 0: a gate that fails for want of a binary teaches
    people to ignore gates, which is the reasoning `CORPORA_GATES` already encodes. The skip is
    printed, never silent.
    """
    import shutil
    import subprocess

    if not os.path.isfile(collector):
        print(f"rendered_conformance: collector missing at {collector} — /design-flow:audit's "
              f"browser mode points at it, so this is a packaging fault, not a syntax verdict.",
              file=sys.stderr)
        return 2
    if shutil.which(node_bin) is None:
        print(f"  skip:  collector syntax ({collector}) — `{node_bin}` is not on PATH, so the "
              f"check did NOT run. That is not a pass.")
        # Exit 3, not 0 (#829): the doctor maps 0 to PASS, so this printed "not a pass" and was
        # counted as one on every laptop without node. 3 is the gate protocol's "ran, could not
        # check everything", which the doctor renders as SKIP with this line as the reason.
        return 3
    result = subprocess.run([node_bin, "--check", collector], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  error: the shipped collector does not parse:\n{result.stderr.strip()}")
        return 1
    print(f"  ok    collector parses ({os.path.basename(collector)})")
    return 0


def load_snapshot(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read snapshot {path}: {exc}") from exc
    except ValueError as exc:
        raise InputError(f"snapshot {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InputError(f"snapshot {path} is not a JSON object")
    return data


# --------------------------------------------------------------------------
# selftest — near-miss fixtures, weighted toward SILENCE.
#
# Every fixture builds a snapshot dict and asserts a verdict. The failure phrase per fixture is
# unique and appears ONLY on failure, so scripts/mutation_check.py can prove the RIGHT fixture
# tripped rather than merely that something did.
#
# The silence direction is the one that decides whether this survives contact with a real app,
# so it gets more fixtures than the firing direction: a rule that cries wolf is switched off, and
# a switched-off rule catches nothing.
# --------------------------------------------------------------------------

def _snapshot(**overrides) -> dict:
    """A minimal conformant snapshot. Fixtures override one thing at a time."""
    snap = {
        "schema": SCHEMA,
        "url": "http://localhost:3000/",
        "viewport": {"width": 390, "height": 844},
        "theme": "light",
        "overflow": {"scrollWidth": 390, "clientWidth": 390},
        "basis": {
            "color": {"--color-primary": ["rgb(0, 119, 204)", "oklab(0.55 -0.03 -0.14)"],
                      "--color-foreground": ["rgb(15, 21, 32)"],
                      "--color-border": ["rgb(226, 230, 237)"]},
            "fontSize": {"--text-step--1": "14.4px", "--text-step-0": "16px"},
            "radius": {"--radius-sm": "6px", "--radius-lg": "12px"},
        },
        "elements": [_element()],
    }
    snap.update(overrides)
    return snap


def _element(**overrides) -> dict:
    element = {
        "ref": "main > button.btn",
        "tag": "button",
        "classes": "bg-primary text-step--1 rounded-md min-h-touch",
        "colours": {"background-color": "rgb(0, 119, 204)"},
        "fontSize": "14.4px",
        "radius": ["6px", "6px", "6px", "6px"],
        "rect": {"w": 120, "h": 44},
        "name": "Save",
        "role": "",
        "aria": {},
        "focus": {"declarations": {"--tw-ring-shadow": "0 0 0 2px",
                                  "outline-style": "none"}},
    }
    element.update(overrides)
    return element


def selftest() -> int:                                        # noqa: C901 - a fixture list
    passed = 0
    failed = 0

    def check(name: str, condition: bool, fail_phrase: str) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}: {fail_phrase}")

    def rules(report: Report) -> list[str]:
        return report.rules_hit()

    # ---- the conformant baseline must be silent -----------------------------------------
    # If this ever fails, nothing below it means anything: every other fixture differs from this
    # one by a single field.
    base = analyse(_snapshot())
    check("a conformant snapshot is clean",
          base.ok and not base.findings,
          f"the baseline fixture produced findings — every rule is now suspect: "
          f"{[f.rule for f in base.findings]}")

    # ---- literal-colour ------------------------------------------------------------------
    snap = _snapshot(elements=[_element(colours={"background-color": "oklch(0.488 0.243 264.4)"})])
    check("a stock-palette colour is reported",
          "literal-colour" in rules(analyse(snap)),
          "a colour tracing to no role token was not reported")

    snap = _snapshot(elements=[_element(
        colours={"background-color": "oklab(0.55 -0.03 -0.14 / 0.9)"})])
    check("an alpha-modified role colour is not reported",
          "literal-colour" not in rules(analyse(snap)),
          "an opacity modifier (`bg-primary/90`, which the doctrine blesses) was reported as a "
          "literal colour — the opaque-only carve-out has gone")

    # The carve-out that matters when the browser cannot give us the mixed spelling of a role: with
    # `color-mix` unsupported, the oklab probe is absent from the basis and EVERY `/90` utility
    # would trace to no role. A translucent value is therefore never judged, whatever its base.
    snap = _snapshot(elements=[_element(colours={"background-color": "rgba(0, 119, 205, 0.9)"})])
    check("a translucent colour whose base is not in the basis is still not judged",
          "literal-colour" not in rules(analyse(snap)),
          "a colour with alpha < 1 was judged — an opacity modifier is doctrine-blessed, and when "
          "the browser lacks color-mix support this carve-out is all that stands between the rule "
          "and a finding on every `/90` in the app")

    snap = _snapshot(elements=[_element(
        colours={"background-color": "color-mix(in oklab, var(--color-primary) 90%, transparent)"})])
    check("an unrecognised colour form is counted, not reported",
          "literal-colour" not in rules(analyse(snap)),
          "a colour form the canonicaliser cannot parse became a finding — an unparsed value "
          "must fail silent, or the first new browser serialization floods the report")

    snap = _snapshot(elements=[_element(tag="script",
                                        colours={"background-color": "rgb(1, 2, 3)"})])
    check("a non-painting tag is not judged for colour",
          "literal-colour" not in rules(analyse(snap)),
          "a <script>/<svg>-class tag was judged for a painted colour — it paints none, and the "
          "analyser must not depend on the collector having filtered them out")

    snap = _snapshot(elements=[_element(colours={"background-color": "#ff6b35"})])
    check("a hex colour is canonicalised, not skipped as unparseable",
          "literal-colour" in rules(analyse(snap)),
          "a `#rrggbb` value was not judged — the canonicaliser accepts hex, and silently "
          "skipping a form it claims to handle is a rule that quietly covers less than it says")

    snap = _snapshot(elements=[_element(colours={"background-color": "rgba(0, 119, 204, 1)"})])
    check("rgba with alpha 1 matches the rgb basis",
          "literal-colour" not in rules(analyse(snap)),
          "`rgba(r, g, b, 1)` did not match the same colour written `rgb(r, g, b)` — the "
          "canonicaliser no longer survives the two spellings of an opaque colour")

    # Asserted on the COUNT, not just on silence: the alpha carve-out below would silence a
    # transparent value anyway, so "no finding" passes whether or not this guard exists. What only
    # this guard gets right is that transparent is not a colour at all — it must not be counted as
    # an alpha-modified one.
    snap = _snapshot(elements=[_element(colours={"background-color": "rgba(0, 0, 0, 0)"})])
    report = analyse(snap)
    check("a transparent background is neither judged nor counted",
          "literal-colour" not in rules(report)
          and any("0 opaque painted colour value(s) judged" in f and "0 alpha-modified" in f
                  for f in report.facts),
          "a fully transparent background was judged, or was counted as an alpha-modified colour "
          "— nothing is painted, so there is nothing to trace to a role and nothing to count")

    snap = _snapshot(basis={"color": {}, "fontSize": {}, "radius": {}})
    report = analyse(snap)
    check("an empty role basis refuses to run",
          report.no_input and not report.ok,
          "a snapshot with no role tokens reported on colours anyway — with an empty basis every "
          "colour traces to no role and the rule floods")

    # ---- numbered-step-binding -----------------------------------------------------------
    snap = _snapshot(elements=[_element(classes="bg-primary-700 text-step--1")])
    check("a numbered palette step is reported",
          "numbered-step-binding" in rules(analyse(snap)),
          "`bg-primary-700` was not reported — this is the causal root of `dark:` sprawl")

    snap = _snapshot(elements=[_element(classes="dark:hover:bg-fm-slate-800")])
    check("a variant-prefixed numbered step is reported",
          "numbered-step-binding" in rules(analyse(snap)),
          "a numbered step behind `dark:hover:` was missed — variant prefixes are not being "
          "stripped before matching")

    # The near-miss battery. Every one of these is CORRECT Tailwind that ends in a number, and
    # each was a false positive in an earlier draft of the pattern.
    for classes in ("text-step-1", "gap-4", "z-50", "w-1/2", "border-2", "grid-cols-3",
                    "shadow-md", "duration-200", "translate-x-100", "text-step--2",
                    "bg-primary/90", "opacity-50", "delay-150", "top-100"):
        snap = _snapshot(elements=[_element(classes=classes)])
        check(f"correct utility `{classes}` is not a numbered-step binding",
              "numbered-step-binding" not in rules(analyse(snap)),
              f"`{classes}` was reported as a palette-step binding — the pattern has widened "
              f"beyond colour-utility + palette-step and will cry wolf")

    # ---- focus-ring-missing --------------------------------------------------------------
    snap = _snapshot(elements=[_element(focus={"declarations": {}})])
    check("an unstyled focus state is reported",
          "focus-ring-missing" in rules(analyse(snap)),
          "an interactive element that no focus rule styles was not reported")

    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline-style": "none"}})])
    check("outline-none alone is not an indicator",
          "focus-ring-missing" in rules(analyse(snap)),
          "`focus-visible:outline-none` with nothing else was accepted as a focus indicator — "
          "Tailwind v4's outline-none really does set `outline-style: none`")

    # A width WITH an invisible style — what `outline-none` beside an `outline-2` from a base rule
    # actually merges to. Only the style half of the test can catch this; the previous fixture is
    # silenced by the zero width, so it cannot.
    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline-style": "none", "outline-width": "2px"}})])
    check("a width on an invisible outline style is still not an indicator",
          "focus-ring-missing" in rules(analyse(snap)),
          "`outline-style: none` with a 2px width was accepted as a focus indicator — a style of "
          "`none` draws nothing at any width")

    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline-style": "solid", "outline-width": "2px"}})])
    check("a real outline is an indicator",
          "focus-ring-missing" not in rules(analyse(snap)),
          "an element with a visible outline was reported as having no focus indicator")

    # `outline: 2px solid var(--ring)` — the shorthand, and the very focus style this rule should
    # be recommending (it is the one that survives forced colors). Reading only `outline-style`
    # reported it as missing.
    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline": "2px solid var(--color-ring)"}})])
    check("the outline shorthand is an indicator",
          "focus-ring-missing" not in rules(analyse(snap)),
          "`outline: 2px solid` was reported as no focus indicator — the shorthand is not being "
          "read, so the rule flags the exact fix it recommends")

    snap = _snapshot(elements=[_element(focus={"declarations": {"outline": "none"}})])
    check("the outline shorthand set to none is not an indicator",
          "focus-ring-missing" in rules(analyse(snap)),
          "`outline: none` in the shorthand was accepted as an indicator")

    # An unparseable width must not veto a visible style: `medium` is the CSS initial value and a
    # var() is common. Treating unparseable as zero reported visible outlines as missing.
    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline-style": "solid", "outline-width": "medium"}})])
    check("an unparseable outline width does not veto a visible style",
          "focus-ring-missing" not in rules(analyse(snap)),
          "`outline-width: medium` was read as zero, so a visible outline was reported as missing")

    snap = _snapshot(elements=[_element(
        focus={"declarations": {"outline-style": "solid", "outline-width": "0px"}})])
    check("an explicitly zero outline width is not an indicator",
          "focus-ring-missing" in rules(analyse(snap)),
          "a 0px outline was accepted as a focus indicator — it draws nothing")

    # The doctrine's own idiom, and the single most important silence fixture in this file:
    # components.md prescribes `focus-visible:outline-none focus-visible:ring-2
    # focus-visible:ring-ring/30`, and a ring is box-shadow (verified claim 3).
    report = analyse(_snapshot())
    check("the doctrine's ring idiom is not reported",
          "focus-ring-missing" not in rules(report),
          "the shipped `outline-none + ring-2` idiom was reported as having no focus indicator — "
          "this rule now fires on every conformant component and will be switched off")
    check("a shadow-only ring is a counted fact, not a finding",
          any("forced-colors" in f for f in report.facts),
          "the forced-colors exposure of a shadow-only ring was not reported as a fact — "
          "box-shadow computes to none there, and the count is the only honest output while our "
          "own doctrine prescribes the idiom")

    snap = _snapshot(elements=[_element(disabled=True, focus={"declarations": {}})])
    check("a disabled control needs no focus ring",
          "focus-ring-missing" not in rules(analyse(snap)),
          "a disabled control was required to have a focus indicator")

    snap = _snapshot(elements=[_element(tag="div", role="", name="", classes="p-4",
                                        focus={"declarations": {}})])
    check("a non-interactive div needs no focus ring",
          "focus-ring-missing" not in rules(analyse(snap)),
          "a plain <div> was treated as interactive")

    # An explicit non-interactive role beats the tag. `<button role="presentation">` inside a
    # composite widget is not the tab stop — the widget's container is — so demanding a focus ring
    # and a name from it is a false positive on a correct pattern.
    snap = _snapshot(elements=[_element(role="presentation", name="",
                                        focus={"declarations": {}})])
    check("an explicit non-interactive role beats the tag",
          not ({"focus-ring-missing", "icon-only-unnamed"} & set(rules(analyse(snap)))),
          "a `<button role=\"presentation\">` was judged as interactive — the role wins, and this "
          "fires on every composite widget built the way APG prescribes")

    # An unreadable stylesheet is stated, not hidden: judging a page whose CSS was partly
    # unreadable while saying nothing is how a false positive ships with a straight face.
    report = analyse(_snapshot(unreadableSheets=2, focusRuleCount=17))
    check("unreadable stylesheets are reported as a notice",
          any("could not be read" in n for n in report.notices),
          "a snapshot collected over unreadable cross-origin stylesheets was judged without "
          "saying so — the collector counts them and nothing read the count")

    snap = _snapshot(elements=[_element(focus=None)])
    report = analyse(snap)
    check("an unmeasured focus state is skipped, not passed",
          any("focus-ring-missing" in s for s in report.skipped)
          and "focus-ring-missing" not in rules(report),
          "an element whose focus rules could not be read was silently treated as conformant — "
          "a skip is not a pass")

    # ---- tap-target-small ----------------------------------------------------------------
    snap = _snapshot(elements=[_element(rect={"w": 120, "h": 32})])
    check("a short tap target is reported",
          "tap-target-small" in rules(analyse(snap)),
          "a 32px-tall control at a mobile viewport was not reported")

    snap = _snapshot(viewport={"width": 1280, "height": 900},
                     elements=[_element(rect={"w": 120, "h": 32})])
    report = analyse(snap)
    check("a desktop viewport skips the touch rule",
          "tap-target-small" not in rules(report)
          and any("tap-target-small" in s for s in report.skipped),
          "a desktop snapshot was judged against the touch floor, and/or the skip was not named")

    snap = _snapshot(elements=[_element(tag="a", href="/x", display="inline", textLength=16,
                                        parentTextLength=74, rect={"w": 60, "h": 19},
                                        name="terms of service")])
    check("an inline link in running text is exempt",
          "tap-target-small" not in rules(analyse(snap)),
          "an inline link inside a sentence was reported — this fires on every paragraph link "
          "and is how the rule gets switched off")

    # The regression fixture for the hole this exemption started as: `display.startsWith('inline')`.
    # A <button> is saved by the tag test, so the case that actually needs the exact-`inline`
    # comparison is a LINK styled as a button — `<a class="btn inline-flex">`, which is how every
    # CTA in this doctrine is built. Chrome gives native buttons `inline-block` for the same reason,
    # which is how the hole was found: running the collector against a real page, where it exempted
    # every button there was.
    snap = _snapshot(elements=[_element(tag="a", href="/signup", display="inline-flex",
                                        textLength=8, parentTextLength=210,
                                        rect={"w": 96, "h": 32}, name="Sign up")])
    check("a link styled as a button is NOT exempt from the touch floor",
          "tap-target-small" in rules(analyse(snap)),
          "a 32px `<a class=\"inline-flex\">` CTA surrounded by text was exempted as an inline "
          "link — widening the exemption past `display: inline` hides the rule on every "
          "button-shaped link, and on every native button too")

    snap = _snapshot(elements=[_element(tag="a", href="/x", display="inline", textLength=4,
                                        parentTextLength=4, rect={"w": 24, "h": 24},
                                        name="Edit")])
    check("an inline link with no surrounding text is still a tap target",
          "tap-target-small" in rules(analyse(snap)),
          "an icon link alone in its container was exempted as prose — the exemption is for a "
          "link in a sentence, and there is no sentence here")

    # ---- icon-only-unnamed ---------------------------------------------------------------
    snap = _snapshot(elements=[_element(name="")])
    check("an unnamed control is reported",
          "icon-only-unnamed" in rules(analyse(snap)),
          "an interactive element with no accessible name was not reported")

    snap = _snapshot(elements=[_element(name="Dismiss")])
    check("an sr-only name silences the rule",
          "icon-only-unnamed" not in rules(analyse(snap)),
          "a control with an accessible name was reported as unnamed")

    snap = _snapshot(elements=[_element(name="", ariaHidden=True)])
    check("an aria-hidden control is not judged",
          "icon-only-unnamed" not in rules(analyse(snap)),
          "an aria-hidden element was required to have an accessible name — it is not in the "
          "accessibility tree, so there is nothing there to name")

    snap = _snapshot(elements=[_element(name="", disabled=True)])
    check("a disabled control still needs a name",
          "icon-only-unnamed" in rules(analyse(snap)),
          "a disabled unnamed control was skipped — disabled controls stay in the accessibility "
          "tree and are still announced, so being disabled is no excuse for having no name")

    # ---- aria-controls-no-expanded -------------------------------------------------------
    snap = _snapshot(elements=[_element(aria={"controls": "panel-1"})])
    check("a disclosure trigger without aria-expanded is reported",
          "aria-controls-no-expanded" in rules(analyse(snap)),
          "`aria-controls` with no `aria-expanded` was not reported")

    snap = _snapshot(elements=[_element(aria={"controls": "panel-1", "expanded": "false"})])
    check("aria-expanded=false silences the rule",
          "aria-controls-no-expanded" not in rules(analyse(snap)),
          "`aria-expanded=\"false\"` was treated as absent — a collapsed disclosure is correct")

    snap = _snapshot(elements=[_element(role="tab", aria={"controls": "tabpanel-1",
                                                          "selected": "true"})])
    check("a tab uses aria-selected, not aria-expanded",
          "aria-controls-no-expanded" not in rules(analyse(snap)),
          "a correct `role=tab` with `aria-selected` was told to add `aria-expanded` — that is a "
          "different pattern with a different contract")

    snap = _snapshot(elements=[_element(aria={"controls": "menu-1", "pressed": "false"})])
    check("a toggle button using aria-pressed is exempt",
          "aria-controls-no-expanded" not in rules(analyse(snap)),
          "a toggle button carrying `aria-pressed` was required to use `aria-expanded`")

    snap = _snapshot(elements=[_element(role="option", aria={"controls": "desc-1"})])
    check("a role=option is exempt by role",
          "aria-controls-no-expanded" not in rules(analyse(snap)),
          "a `role=option` was told to add `aria-expanded` — the role carve-out has gone")

    # The other half of that carve-out: `aria-expanded` is a REQUIRED state of role=combobox, so a
    # combobox must NOT be exempted. Excluding it would look like consistency and hide a defect.
    snap = _snapshot(elements=[_element(role="combobox", aria={"controls": "listbox-1"})])
    check("a combobox is not exempt (aria-expanded is required on the role)",
          "aria-controls-no-expanded" in rules(analyse(snap)),
          "a combobox with `aria-controls` and no `aria-expanded` went unreported — WAI-ARIA makes "
          "the state required on that role, so this is the defect, not a different pattern")

    # ---- horizontal-overflow -------------------------------------------------------------
    snap = _snapshot(overflow={"scrollWidth": 412, "clientWidth": 390})
    check("horizontal overflow is reported",
          "horizontal-overflow" in rules(analyse(snap)),
          "22px of horizontal scroll at a mobile viewport was not reported")

    snap = _snapshot(overflow={"scrollWidth": 390.6, "clientWidth": 390})
    check("sub-pixel width is not overflow",
          "horizontal-overflow" not in rules(analyse(snap)),
          "0.6px of sub-pixel rounding was reported as horizontal overflow — an exact comparison "
          "fires on pages that do not scroll")

    # ---- off-scale-type ------------------------------------------------------------------
    snap = _snapshot(elements=[_element(fontSize="13px")])
    check("an off-scale font size is reported",
          "off-scale-type" in rules(analyse(snap)),
          "a font-size from no `--text-step-*` was not reported")

    snap = _snapshot(elements=[_element(fontSize="14.40001px")])
    check("sub-pixel drift still matches its step",
          "off-scale-type" not in rules(analyse(snap)),
          "a computed clamp() size that differs from its own token in the sixth decimal was "
          "reported as off-scale")

    snap = _snapshot(elements=[_element(tag="sup", fontSize="10.8px", name="", role="",
                                        classes="", focus=None, aria={})])
    check("a UA-scaled tag is exempt",
          "off-scale-type" not in rules(analyse(snap)),
          "`<sup>`, whose size the UA/preflight sets to a percentage, was reported as off-scale")

    snap = _snapshot(basis={"color": {"--color-primary": ["rgb(0, 119, 204)"]},
                            "fontSize": {}, "radius": {"--radius-sm": "6px"}},
                     elements=[_element(fontSize="13px")])
    report = analyse(snap)
    check("no type basis skips the rule by name",
          "off-scale-type" not in rules(report)
          and any("off-scale-type" in s for s in report.skipped),
          "with no `--text-step-*` resolved the rule either judged anyway or went quiet without "
          "saying so — a skip is not a pass")

    # ---- radius-off-scale ----------------------------------------------------------------
    snap = _snapshot(elements=[_element(radius=["7px", "7px", "7px", "7px"])])
    check("an arbitrary radius is reported",
          "radius-off-scale" in rules(analyse(snap)),
          "`rounded-[7px]` was not reported against the radius scale")

    snap = _snapshot(elements=[_element(radius=["9999px", "9999px", "9999px", "9999px"])])
    check("a pill radius is always legitimate",
          "radius-off-scale" not in rules(analyse(snap)),
          "`rounded-full` was reported as off-scale — it is the doctrine's badge/avatar radius")

    snap = _snapshot(elements=[_element(radius=["0px", "0px", "0px", "0px"])])
    check("a square corner is not off-scale",
          "radius-off-scale" not in rules(analyse(snap)),
          "a 0px corner was reported — every unrounded element on the page would be a finding")

    report = analyse(_snapshot())
    check("the radius distribution is reported as a fact",
          any("radius language" in f for f in report.facts),
          "the radius-language distribution — the measurement #107 asks for — was not reported")

    # Corners are not elements. Counting all four multiplied every radius number by four: one
    # `rounded-[7px]` button was reported as "4 element(s)" and the distribution read
    # `--radius-md x32` for eight buttons. Found against a real page.
    report = analyse(_snapshot(elements=[_element(radius=["7px", "7px", "7px", "7px"])]))
    check("four equal corners are one radius decision",
          any("on 1 element(s)" in f.message for f in report.findings
              if f.rule == "radius-off-scale")
          and any("radius language: 7.0px (off-scale) x1" in f for f in report.facts),
          "an element's four corners were counted as four elements — every radius count, and the "
          "distribution that is the whole point of the rule, reads four times too high")

    # ---- trends --------------------------------------------------------------------------
    dark = _snapshot(elements=[_element(classes="dark:bg-fm-slate-800 dark:text-fm-slate-50")
                               for _ in range(4)])
    check("dark: sprawl over the threshold is a trend finding",
          any(f.rule == "dark-variant-sprawl" and f.severity == "trend"
              for f in analyse(dark, max_dark=5).findings),
          "8 `dark:` occurrences did not exceed a threshold of 5, or were not reported as a "
          "trend")

    check("dark: sprawl under the threshold is silent but counted",
          "dark-variant-sprawl" not in rules(analyse(dark, max_dark=99))
          and any("`dark:` occurrences: 8" in f for f in analyse(dark, max_dark=99).facts),
          "under the threshold the count was not printed — the count IS the metric, so it must "
          "appear whether or not it blocks")

    bp = _snapshot(elements=[_element(classes="grid-cols-1 sm:grid-cols-2 lg:grid-cols-4")
                             for _ in range(3)])
    check("breakpoint sprawl over the threshold is a trend finding",
          any(f.rule == "breakpoint-driven-layout" for f in analyse(bp, max_breakpoint=5).findings),
          "6 breakpoint occurrences did not exceed a threshold of 5")

    check("an unprefixed utility is not counted as a breakpoint occurrence",
          "breakpoint occurrences: 0 (threshold 25)" in analyse(_snapshot()).facts,
          "the conformant baseline (`bg-primary text-step--1 rounded-md min-h-touch`, no variant "
          "on any of them) counted a breakpoint occurrence where there is none")

    # ---- the cap is announced, never silent ----------------------------------------------
    # A truncated list that says nothing reads as "that was all of them" — the same lie as a skip
    # reported as a pass, and CLAUDE.md's `no silent caps` rule.
    many = _snapshot(elements=[_element(ref=f"row-{i}", classes=f"bg-primary-{i}00")
                               for i in range(1, 10)]
                              + [_element(ref=f"cell-{i}", classes=f"text-fm-slate-{i}00")
                                 for i in range(1, 10)])
    report = analyse(many)
    check("a truncated finding list says how many were dropped",
          len([f for f in report.findings if f.rule == "numbered-step-binding"])
          == MAX_FINDINGS_PER_RULE
          and any("further hit(s) not listed" in n for n in report.notices),
          "18 distinct palette-step bindings were capped without a notice — a silent cap reads "
          "as a complete report")

    # ---- schema + empty input ------------------------------------------------------------
    # A fully valid snapshot with ONLY the schema wrong. Handing it a bare dict would pass either
    # way — with the schema check gone it would fail the empty-basis guard instead, and the
    # assertion could not tell which guard answered.
    report = analyse(_snapshot(schema="design-flow/rendered-conformance/0"))
    check("a foreign schema is refused",
          report.no_input and not report.ok,
          "a snapshot from a different collector version was analysed anyway — the collector and "
          "this analyser drift as a pair, so an old snapshot's silence means nothing")

    report = analyse(_snapshot(elements=[]))
    check("an empty element list is not a pass",
          report.no_input and not report.ok,
          "a snapshot with zero elements reported clean — a run that judged nothing is not a "
          "conformant page")

    # ---- exit codes ----------------------------------------------------------------------
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "clean.json")
        with open(clean, "w", encoding="utf-8") as handle:
            json.dump(_snapshot(), handle)
        check("a conformant snapshot exits 0", main([clean, "--quiet"]) == 0,
              "the baseline snapshot did not exit 0")

        drifted = os.path.join(tmp, "drift.json")
        with open(drifted, "w", encoding="utf-8") as handle:
            json.dump(_snapshot(elements=[_element(classes="bg-primary-700")]), handle)
        check("drift exits 1", main([drifted, "--quiet"]) == 1,
              "a snapshot with a numbered-step binding did not exit 1")

        empty = os.path.join(tmp, "empty.json")
        with open(empty, "w", encoding="utf-8") as handle:
            json.dump(_snapshot(elements=[]), handle)
        check("a snapshot with nothing to judge exits 2, not 1", main([empty, "--quiet"]) == 2,
              "a run that judged nothing exited with the code reserved for real drift, sending a "
              "maintainer hunting a defect that does not exist")

        broken = os.path.join(tmp, "broken.json")
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        check("unparseable JSON exits 2, not 1", main([broken, "--quiet"]) == 2,
              "an unreadable snapshot was reported as drift instead of as an environment fault")

        check("a missing snapshot exits 2",
              main([os.path.join(tmp, "nope.json"), "--quiet"]) == 2,
              "a missing file did not exit 2")

        # ---- the contract, the fixtures and the collector must name the same fields -------
        # `--schema` is a printed promise about what the collector emits, and a promise nothing
        # checks goes stale silently: this file's contract still documented `inlineInText` after
        # the field was replaced, and omitted two fields the collector had started emitting. So
        # the three artefacts are compared mechanically instead.
        # The field set comes from what the RULES ACTUALLY READ — every quoted field name passed to
        # an `element.get(...)` or `snapshot.get(...)` in this module — not from the fixture dicts.
        # (Written without a literal example on purpose: the first draft's comment contained one,
        # and the scan below dutifully matched it.) Taking the set from the
        # fixtures was itself a coverage gap: `display` is only ever passed as an override, so it
        # was absent from the baseline dict and the check could not see the field whose contract
        # entry had gone stale in the first place.
        import re as _re

        with open(os.path.abspath(__file__), encoding="utf-8") as handle:
            own_source = handle.read()
        accessor = _re.compile(r"""(?:element|snapshot)\.get\(["']([a-zA-Z]+)["']""")
        read_fields = sorted(set(accessor.findall(own_source)))
        check("the analyser reads a plausible number of snapshot fields",
              len(read_fields) >= 15,
              f"only {len(read_fields)} field(s) were discovered ({read_fields}) — the accessor "
              f"pattern has stopped matching, so the two parity checks below are comparing "
              f"nothing and would pass over any drift")

        undocumented = [f for f in read_fields if f'"{f}"' not in SCHEMA_DOC]
        check("every field the analyser reads is in the printed contract",
              not undocumented,
              f"--schema does not document {undocumented} — the contract a user reads has drifted "
              f"from the snapshot this file actually judges")

        collector_source = ""
        if os.path.isfile(COLLECTOR):
            with open(COLLECTOR, encoding="utf-8") as handle:
                collector_source = handle.read()
        unemitted = [f for f in read_fields if collector_source and f not in collector_source]
        check("every field the analyser reads is emitted by the collector",
              not unemitted,
              f"the collector never emits {unemitted} — a rule is reading a field no real run "
              f"produces, so it judges `None` forever and its silence means nothing")

        # ---- the collector check ---------------------------------------------------------
        check("the shipped collector parses",
              check_collector() == 0,
              "the collector this plugin ships does not parse (or node is absent and the skip "
              "path is broken) — /design-flow:audit's browser mode hands this file to a user's "
              "browser")

        bad = os.path.join(tmp, "bad-collector.js")
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("const broken = () => {\n")
        check("a collector that does not parse exits 1",
              check_collector(collector=bad) == 1,
              "a syntactically broken collector was accepted — the check cannot fail, so it "
              "proves nothing")

        # A missing node must SKIP (0 with a printed skip), not fail: a gate that dies for want of
        # a binary teaches people to ignore gates. Proven by pointing at a binary that cannot
        # exist, which is the only way to exercise this path on a machine that has node.
        # == 3, not == 0 (#829): the old assertion pinned the defect -- 0 renders as PASS in the doctor.
        check("an absent node skips instead of failing",
              check_collector(node_bin="node-that-does-not-exist") == 3,
              "the collector check failed rather than skipping when its interpreter was missing")

        check("a missing collector is an environment fault, not a syntax verdict",
              check_collector(collector=os.path.join(tmp, "gone.js")) == 2,
              "a missing collector exited with a code that reads as a syntax error")

    total = passed + failed
    if failed:
        print(f"\nselftest: {failed} of {total} FAILED")
        return 1
    print(f"\nselftest: {total} checks passed")
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

SCHEMA_DOC = """snapshot contract — design-flow/rendered-conformance/1

The collector (see commands/audit.md) MEASURES; this script JUDGES. Nothing below is a verdict.

{
  "schema":   "design-flow/rendered-conformance/1",
  "url":      "http://localhost:3000/dashboard",
  "viewport": {"width": 390, "height": 844},
  "theme":    "light" | "dark",
  "truncated": false,                       // true when the element cap was hit
  "unreadableSheets": 0,                    // cross-origin sheets whose .cssRules threw
  "focusRuleCount": 42,                     // :focus rules the collector could read
  "overflow": {"scrollWidth": 390, "clientWidth": 390},
  "basis": {                                // the app's OWN tokens, resolved by the browser
    "color":    {"--color-primary": ["rgb(0, 119, 204)", "oklab(...)"], ...},
    "fontSize": {"--text-step-0": "16px", ...},
    "radius":   {"--radius-sm": "6px", ...}
  },
  "elements": [{
    "ref": "main > button.btn",             // pointer a human can find
    "tag": "button", "role": "", "type": null, "href": null,
    "classes": "bg-primary text-step--1",   // string or array
    "colours": {"background-color": "rgb(0, 119, 204)"},   // PAINTED properties only
    "fontSize": "14.4px",                   // only when the element has its own text
    "radius": ["6px", "6px", "6px", "6px"],
    "rect": {"w": 120, "h": 44},
    "name": "Save",                         // approximate accessible name
    "aria": {"controls": null, "expanded": null, "selected": null, "pressed": null},
    "ariaHidden": false, "disabled": false, "tabindex": null,
    "display": "inline-block",              // MEASUREMENTS, not the exemption they feed
    "textLength": 4, "parentTextLength": 210,
    "focus": {"declarations": {"--tw-ring-shadow": "0 0 0 2px", "outline-style": "none"}}
  }]
}

`focus` is null when the collector could not read the matching rules (a cross-origin stylesheet
throws on .cssRules). Null is a SKIP, reported by name — never a pass.

The collector reports measurements and never a verdict: no rule, count or threshold lives in JS.
Where it must scope WHAT it measures, that scoping is part of this contract and is stated above —
a border colour only where a border is drawn, `fontSize` only on an element with its own text, and
no record at all for `display: none`. The line is worth keeping sharp: `inlineInText` used to be a
field here, and deciding it in JS put a judgement somewhere no fixture could reach, which is
exactly how it shipped wide enough to exempt every native `<button>` from the touch floor.

`focus.declarations` merges the matching rules in the order the collector read them, which is
source order, not the full cascade. Enough for Tailwind utilities, which all carry the same
specificity; a hand-written `!important` focus rule could in principle be overridden here.
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="rendered_conformance.py",
        description="Judge design-system conformance from a rendered-page snapshot.",
    )
    parser.add_argument("snapshots", nargs="*", help="snapshot JSON file(s) from the collector")
    parser.add_argument("--max-dark", type=int, default=5, metavar="N",
                        help="`dark:` occurrences allowed before it is a finding (default 5; a "
                             "role layer needs 0, a couple for media is not drift)")
    parser.add_argument("--max-breakpoint", type=int, default=25, metavar="N",
                        help="breakpoint-variant occurrences allowed (default 25; the kit that "
                             "motivated #107 averaged ~85 per page)")
    parser.add_argument("--schema", action="store_true",
                        help="print the snapshot contract and exit")
    parser.add_argument("--check-collector", action="store_true",
                        help="node --check the shipped browser collector and exit")
    parser.add_argument("--node-bin", default="node", metavar="BIN",
                        help="node executable for --check-collector (the selftest points this at "
                             "a nonexistent binary to prove the skip path is a skip)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the near-miss fixtures and exit")
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if args.schema:
        print(SCHEMA_DOC)
        return 0
    if args.check_collector:
        return check_collector(args.node_bin)
    if args.selftest:
        return selftest()
    if not args.snapshots:
        parser.print_usage(sys.stderr)
        print("rendered_conformance: give at least one snapshot JSON "
              "(`--schema` prints the contract, `--selftest` proves the rules fire).",
              file=sys.stderr)
        return 2

    reports = []
    for path in args.snapshots:
        if not os.path.isfile(path):
            print(f"rendered_conformance: snapshot not found at {path}", file=sys.stderr)
            return 2
        try:
            snapshot = load_snapshot(path)
        except InputError as exc:
            # Environment, not a finding. Letting this exit 1 would report a broken file as
            # design drift.
            print(f"rendered_conformance: {exc}", file=sys.stderr)
            return 2
        reports.append(analyse(snapshot, max_dark=args.max_dark,
                               max_breakpoint=args.max_breakpoint, label=path))

    environment = 0
    drifted = 0
    for report in reports:
        drift = [f for f in report.findings if f.severity == "drift"]
        trend = [f for f in report.findings if f.severity == "trend"]
        # no_input FIRST: an unjudgeable snapshot is an environment fault, and labelling it FAIL
        # (which the finding it carries would otherwise do) is exactly the 1/2 conflation the
        # exit codes exist to avoid.
        status = "UNJUDGED" if report.no_input else ("FAIL" if report.findings else "OK")
        print(f"{status:8s} {report.label}")
        if not args.quiet:
            for fact in report.facts:
                print(f"        {fact}")
        for notice in report.notices:
            print(f"  note:  {notice}")
        for finding in drift + trend:
            where = f" [{finding.ref}]" if finding.ref else ""
            print(f"  {finding.severity}: {finding.rule}{where} — {finding.message}")
        for skip in report.skipped:
            print(f"  skip:  {skip}   (NOT a pass — this rule did not run)")
        if report.no_input:
            environment += 1
        elif report.findings:
            drifted += 1

    if environment:
        print(f"\n{environment} snapshot(s) could not be judged. That is an environment fault, "
              f"not a conformance verdict — fix the collection and re-run.")
        return 2
    if drifted:
        print(f"\n{drifted} of {len(reports)} snapshot(s) drift from the design system. "
              f"Rules hit: {', '.join(sorted({f.rule for r in reports for f in r.findings}))}.")
        return 1
    if not args.quiet:
        print(f"\n{len(reports)} snapshot(s) conform.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
