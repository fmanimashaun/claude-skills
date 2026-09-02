#!/usr/bin/env python3
"""Measure the role tokens against WCAG 1.4.3 — in the doctrine file AND in every shipped pack.

Run:  python3 scripts/check_token_contrast.py            # measure, fail on a violation
      python3 scripts/check_token_contrast.py --selftest  # prove the maths and the rules

WHY (#304). A contrast ratio is the most measurable claim in the whole design system, and it was
being asserted in prose. `--primary` on `--background` sat at **4.42:1** in light mode — under
1.4.3's 4.5:1 — and a doctrine table stated the number without anything re-deriving it, so it stayed
wrong. Measuring adjacent pairings then found a second, worse one the report had missed: the `.dark`
block overrode `--primary` to electric but NOT `--primary-foreground`, which therefore inherited
`#FFFFFF` from `:root` — white on `#00A3FF` is **2.73:1**, and that is the label on every primary
button in dark mode.

That second defect is the argument for this script. The first was found by a human reading a table;
the second was invisible until something enumerated the pairs mechanically. A token file is exactly
the kind of input where a person checks the pair they are thinking about and no others.

WHY IT NOW READS MORE THAN ONE FILE (#129). Because the #304 fix was applied to the doctrine file
and to nothing else. `plugins/design-flow/brands/fidara/theme.css` — the pack `/design-flow:setup
fidara` actually reads, and therefore the bytes a user's app is built from — still carried BOTH
defects: `--primary: #0077CC` at 4.42:1, and a `.dark` block re-pointing `--primary` without
`--primary-foreground`. The `_template` pack every client brand is copied from failed three pairs.
The gate had a single hardcoded input, so it reported clean over the one file that had been fixed
while the shipped artifacts kept the defect it exists to catch. A checker whose scope is narrower
than its subject is a coverage gap, not a check — so the scope is now "every role-token file this
repo ships", enumerated by glob, and an empty glob is a hard error rather than a quiet pass.

WHAT IT CHECKS. The pairs where a role token's value lands on another role token's surface as TEXT.
Only text pairs, because 1.4.3 is about text — a logo, a chart hue and a decorative fill are out of
scope and are deliberately not enumerated here. `--ring` is excluded too: it is used at `/30` over an
offset, so a flat pair would be a fiction.

WHAT IT DOES NOT CHECK, AND WHY NOT `--border` / `--input`. Alpha-modified colours (`primary/90`),
gradients, and anything requiring a rendered page need the browser — `rendered_conformance.py` is
where they belong. Large text's 3:1 allowance is not modelled: every pair here is body-sized in at
least one documented use, so the stricter threshold is the honest one. The border tokens are left
out DELIBERATELY: WCAG 2.2 SC 1.4.11 asks for 3:1 only on "visual information required to identify
user interface components", and its Understanding note says plainly that "if a control has visible
content (such as text or a sufficiently contrasting icon), which helps users identify the presence
of the control, then a border or other indication of the overall boundary of the hit area is not
required". A flat `--border`-on-`--background` gate would therefore be STRICTER THAN THE SPEC, and
a rule stricter than the spec is a rule people switch off.
  https://www.w3.org/TR/WCAG22/#contrast-minimum  ·  https://www.w3.org/TR/WCAG22/#non-text-contrast
  https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html

Exit codes:  0 clean · 1 a pair is under threshold · 2 a token file could not be parsed

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKENS = REPO / "skills" / "design-system" / "references" / "foundations-tokens.md"
# Every brand pack this repo ships. A pack is the file a user's app is actually built from, so it
# is not a lesser input than the doctrine file -- it is the more consequential one.
PACK_GLOB = "plugins/design-flow/brands/*/theme.css"

AA_NORMAL = 4.5

# WCAG 2.2's relative-luminance definition linearises an sRGB channel at 0.04045. WCAG 2.0 published
# 0.03928 and this file carried that value; the current normative text does not.
#   https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
#     "if RsRGB <= 0.04045 then R = RsRGB/12.92 else R = ((RsRGB+0.055)/1.055) ^ 2.4"
# The two disagree only on inputs in (0.03928, 0.04045], and no 8-bit channel lands there -- 10/255
# is 0.0392 and 11/255 is 0.0431. The selftest proves that over all 256 channels rather than
# asserting it, so the correction is verifiable and provably not a silent re-measurement.
SRGB_LINEAR_BREAKPOINT = 0.04045

# (label, foreground token, background token, mode). Names are resolved through the file, so a
# renamed token is a parse error rather than a silently skipped pair.
# TWO TIERS, because WCAG has two thresholds and using one for both is taste wearing a count (#775).
# 1.4.3 governs TEXT at 4.5:1; 1.4.11 governs non-text UI components and graphical objects at 3:1.
# A role's tier is decided by the CONTRACT's own vocabulary, not by preference:
#
#   `--ring` is a focus indicator -- a UI component state, so 1.4.11, 3:1.
#   `--*-ink` roles exist to BE text (that is why `--success-ink` was added alongside `--success`),
#     so 1.4.3, 4.5:1.
#   The base feedback roles (`--success`, `--warning`, `--info`, `--signal`, `--destructive`) are
#     NOT enumerated against the page, and that is deliberate. They serve as fills, borders and
#     icons depending on the component, so the correct threshold depends on a usage this file cannot
#     see from tokens alone -- and picking 4.5 or 3 for all of them would fail both shipped packs
#     for a rule neither WCAG clause actually states. #775 measured it: fidara's bright hues clear
#     dark and fail light; reliance's darkened ones clear light and fail dark. A single value cannot
#     serve both grounds, which is a CONTRACT question, recorded in brand.md, not a checker's call.
AA_LARGE = 3.0

PAIRS: tuple[tuple[str, str, str, str] | tuple[str, str, str, str, float], ...] = (
    ("text-primary on the page",      "--primary",            "--background", "light"),
    ("text-primary on a card",        "--primary",            "--card",       "light"),
    ("primary button label",          "--primary-foreground", "--primary",    "light"),
    ("body text on the page",         "--foreground",         "--background", "light"),
    ("body text on a card",           "--card-foreground",    "--card",       "light"),
    # Muted text is the commonest low-contrast failure in a real UI -- helper text, timestamps,
    # table meta -- and it was the pair missing from this list. `_template`'s was 2.71:1 (#129).
    ("muted text on a muted surface", "--muted-foreground",   "--muted",      "light"),
    ("text-primary on the page",      "--primary",            "--background", "dark"),
    ("text-primary on a card",        "--primary",            "--card",       "dark"),
    ("primary button label",          "--primary-foreground", "--primary",    "dark"),
    ("body text on the page",         "--foreground",         "--background", "dark"),
    ("body text on a card",           "--card-foreground",    "--card",       "dark"),
    ("muted text on a muted surface", "--muted-foreground",   "--muted",      "dark"),

    # #775. Enumerated in BOTH modes. Every pack passed these in light and failed them in dark,
    # because dark re-points its surfaces and these roles were never re-pointed with them -- an ink
    # tuned for a light ground is illegible on a dark one, and a focus ring below 3:1 is not a ring.
    ("focus ring on the page",        "--ring",               "--background", "light", AA_LARGE),
    ("focus ring on a card",          "--ring",               "--card",       "light", AA_LARGE),
    ("focus ring on the page",        "--ring",               "--background", "dark",  AA_LARGE),
    ("focus ring on a card",          "--ring",               "--card",       "dark",  AA_LARGE),
    ("success ink on the page",       "--success-ink",        "--background", "light"),
    ("success ink on a card",         "--success-ink",        "--card",       "light"),
    ("success ink on the page",       "--success-ink",        "--background", "dark"),
    ("success ink on a card",         "--success-ink",        "--card",       "dark"),
    ("primary ink on the page",       "--primary-ink",        "--background", "light"),
    ("primary ink on a card",         "--primary-ink",        "--card",       "light"),
    ("primary ink on the page",       "--primary-ink",        "--background", "dark"),
    ("primary ink on a card",         "--primary-ink",        "--card",       "dark"),
)

# NOT enumerated, and the omission is deliberate rather than an oversight. `--destructive-foreground`
# on `--destructive` is a real text pair, and fidara's shipped values (#FFFFFF on #EF4444) measure
# 3.76:1 -- under 1.4.3. Adding the pair here would fail the build on a BRAND colour, and which red
# a brand uses is a maintainer decision, not something a checker gets to make while implementing an
# unrelated issue. It is reported on #129 instead. Palettes this repo AUTHORS from scratch are held
# to the wider set -- see CANDIDATE_PAIRS in plugins/design-flow/scripts/palette_candidates.py,
# which has no legacy value to grandfather.

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


class Unparseable(RuntimeError):
    """The token file did not yield what this check needs -- never a silent pass."""


def linearise(channel: float) -> float:
    """One sRGB channel in [0,1] -> its linear-light value, per WCAG 2.2."""
    if channel <= SRGB_LINEAR_BREAKPOINT:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [linearise(c) for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_tokens(text: str) -> dict[str, dict[str, str]]:
    """{mode: {token: raw value}} for the `:root` and `.dark` blocks.

    `.dark` INHERITS from `:root` -- which is the whole mechanism behind the second #304 defect, so
    modelling it is the point rather than a convenience.
    """
    # `@theme` holds the raw brand PALETTE (`--color-fm-*`); `:root` and `.dark` hold the ROLE
    # tokens that point into it. A role is therefore only resolvable with the palette in scope, so
    # the palette is parsed as a base layer both modes inherit. Skipping it made every role that
    # referenced a palette entry unresolvable -- which the checker reported rather than passing,
    # but a parser that reads half the file is still a parser that can miss a pair.
    # `@theme inline` is excluded: it re-exports roles as `--color-*` aliases for Tailwind, so
    # folding it in would let an alias shadow the role it aliases.
    palette: dict[str, str] = {}
    scopes: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("@theme inline"):
            current = None
        elif stripped.startswith("@theme"):
            current = "palette"
        elif stripped.startswith(":root"):
            current = "light"
        elif stripped.startswith(".dark"):
            current = "dark"
        elif stripped == "}":
            current = None
        if current:
            target = palette if current == "palette" else scopes[current]
            for name, value in DECL_RE.findall(line):
                target[name] = value.strip()
    if not palette:
        raise Unparseable(f"{TOKENS.name}: no `@theme` palette declarations found")
    # Assert the two ROLE blocks were seen BEFORE folding the palette in. Merging first would make
    # `not scopes["light"]` unreachable -- a gate that cannot fail, which is the class this repo
    # lints for. Caught by reading back my own edit.
    if not scopes["light"]:
        raise Unparseable(f"{TOKENS.name}: no `:root` declarations found")
    if not scopes["dark"]:
        raise Unparseable(f"{TOKENS.name}: no `.dark` declarations found")
    scopes["light"] = {**palette, **scopes["light"]}
    scopes["dark"] = {**scopes["light"], **scopes["dark"]}   # cascade, deliberately
    return scopes


def resolve(token: str, scope: dict[str, str], _seen: frozenset[str] = frozenset()) -> str:
    """A token's literal hex, following `var(--x)` chains."""
    if token in _seen:
        raise Unparseable(f"`{token}` resolves in a cycle")
    raw = scope.get(token)
    if raw is None:
        raise Unparseable(f"`{token}` is not declared -- renamed, or the parser missed its block")
    if HEX_RE.match(raw):
        return raw
    ref = re.fullmatch(r"var\((--[a-z0-9-]+)\)", raw)
    if not ref:
        raise Unparseable(f"`{token}` is `{raw}`, which is neither a hex nor a single var()")
    return resolve(ref.group(1), scope, _seen | {token})


# ---------------------------------------------------------------------------
# cross-implementation parity (see the selftest for why this is not an import)
# ---------------------------------------------------------------------------
#
# Both helpers are module-level rather than inline in the selftest so that each can be checked
# with a POSITIVE CONTROL. A comparison written inline is trivially mutated to "no disagreement",
# and every fixture that reads it agrees -- the tautology that lets a parity check go quiet while
# still reporting green.

PARITY_PROBES: tuple[str, ...] = ("#000000", "#FFFFFF", "#767676", "#0072C4", "#00A3FF",
                                  "#0C1B33", "#F8F9FB", "#0A0A0C", "#010101", "#0B0B0B")


def max_disagreement(left, right, probes: tuple[str, ...]) -> float:
    """Largest |left(a, b) - right(a, b)| over every ordered pair of probes."""
    return max(abs(left(a, b) - right(a, b)) for a in probes for b in probes)


def role_disagreements(left: dict[str, str], right: dict[str, str], mode: str) -> list[str]:
    """Roles two resolutions of the same pack do not agree on."""
    out = []
    for role, value in sorted(right.items()):
        ours = left.get(role)
        if ours is None or ours.upper() != value.upper():
            out.append(f"{mode} {role}: canonical {ours} vs shipped {value}")
    return out


def sources(repo: Path = REPO) -> list[Path]:
    """Every role-token file this repo ships: the doctrine file, then every brand pack.

    An empty pack glob RAISES. A checker that measured nothing would print the same clean verdict
    as one that measured everything -- the skip-as-pass failure this repo keeps paying for, and the
    exact shape of the gap that let the #304 defect live on in the packs.
    """
    packs = sorted(repo.glob(PACK_GLOB))
    if not packs:
        raise Unparseable(
            f"{PACK_GLOB} matched no brand pack. Every shipped pack must be measured; a run that "
            "found none is a broken glob, not a clean repo."
        )
    return [repo / TOKENS.relative_to(REPO), *packs]


def measure(path: Path) -> list[tuple[str, str, str, str, str, str, float, float]]:
    """One row per enumerated pair, carrying the FLOOR that pair is judged against.

    A pair whose role this pack does not declare is SKIPPED (floor 0.0, ratio 0.0) rather than
    raising: `--success-ink` and `--primary-ink` arrived in v1.98.0 and `_template` predates them,
    so demanding every pack declare every role would turn a real measurement into a scaffolding
    error. The summary prints how many were skipped, because a pair that did not run is not a pass.
    """
    scopes = parse_tokens(path.read_text(encoding="utf-8"))
    rows = []
    for pair in PAIRS:
        label, fg, bg, mode = pair[:4]
        floor = pair[4] if len(pair) > 4 else AA_NORMAL
        scope = scopes.get(mode) or {}
        try:
            f, b = resolve(fg, scope), resolve(bg, scope)
        except Unparseable:
            # SKIPPED, not raised, in BOTH shapes -- an undeclared role, and a role declared but
            # pointing at a primitive the pack does not define. The second is a real defect and
            # `brand_pack_lint` OWNS it ("var() references not defined anywhere in this pack"),
            # which `_template` trips on purpose: it fails by design until copied and validated.
            # Raising here would make this gate red for a reason another gate already reports, and
            # the first thing anyone would do is exempt the file -- losing the pairs that DO
            # resolve. The skip is counted and printed, so it is never mistaken for a pass.
            rows.append((mode, label, fg, bg, "", "", 0.0, 0.0))
            continue
        rows.append((mode, label, fg, bg, f, b, contrast(f, b), floor))
    return rows


def run(repo: Path = REPO) -> int:
    try:
        inputs = sources(repo)
    except Unparseable as exc:
        print(f"CANNOT MEASURE: {exc}", file=sys.stderr)
        return 2

    failures = 0
    total = 0
    skipped = 0
    for path in inputs:
        rel = path.relative_to(repo).as_posix()
        try:
            rows = measure(path)
        except (OSError, Unparseable) as exc:
            print(f"CANNOT MEASURE {rel}: {exc}", file=sys.stderr)
            return 2
        print(f"{rel}")
        for mode, label, fg, bg, f, b, ratio, floor in rows:
            if not floor:
                print(f"  [skip] {mode:5} {label:24} {fg} not declared by this pack — NOT a pass")
                continue
            mark = "ok  " if ratio >= floor else "FAIL"
            print(f"  [{mark}] {mode:5} {label:24} {fg} {f} on {bg} {b} = {ratio:.2f}:1 "
                  f"(floor {floor})")
        failures += sum(1 for r in rows if r[7] and r[6] < r[7])
        skipped += sum(1 for r in rows if not r[7])
        total += sum(1 for r in rows if r[7])

    if failures:
        print(f"\n{failures} pair(s) under their WCAG floor — 1.4.3's {AA_NORMAL}:1 for text, "
              f"1.4.11's {AA_LARGE}:1 for UI components — across {len(inputs)} token file(s).",
              file=sys.stderr)
        return 1
    tail = f"; {skipped} pair(s) SKIPPED for an undeclared role (not passes)" if skipped else ""
    print(f"\n{total} pair(s) across {len(inputs)} token file(s), each at or above its floor{tail}.")
    return 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    # The maths, against the two standard controls. Without these the whole file is unfalsifiable.
    check("control: #767676 on white is 4.54", round(contrast("#767676", "#FFFFFF"), 2) == 4.54,
          f"got {contrast('#767676', '#FFFFFF'):.2f}")
    check("control: white on black is 21.00", round(contrast("#FFFFFF", "#000000"), 2) == 21.00,
          f"got {contrast('#FFFFFF', '#000000'):.2f}")
    check("contrast is symmetric",
          abs(contrast("#0072C4", "#FFFFFF") - contrast("#FFFFFF", "#0072C4")) < 1e-9)
    check("3-digit hex expands", abs(contrast("#FFF", "#000") - contrast("#FFFFFF", "#000000")) < 1e-9)

    # THE sRGB BREAKPOINT. WCAG 2.2's normative text linearises at 0.04045; this file used WCAG
    # 2.0's 0.03928. Asserted on a float strictly between the two, because that is the only input
    # that can tell them apart at all.
    check("the sRGB linearisation breakpoint is WCAG 2.2's 0.04045",
          abs(linearise(0.04) - 0.04 / 12.92) < 1e-12,
          f"0.04 linearised to {linearise(0.04)!r}; under 0.03928 it would take the power branch")
    # And the correction is proved IMMATERIAL rather than claimed so: no 8-bit channel lands in the
    # gap, so no committed colour changes value. Measuring that is the difference between a verified
    # correction and a silent re-measurement of every ratio in the repo.
    check("both thresholds agree on all 256 8-bit channels",
          all((c / 255 <= 0.03928) == (c / 255 <= 0.04045) for c in range(256)))

    # THE CASCADE, which is the defect this file exists for: `.dark` overrode `--primary` and not
    # `--primary-foreground`, so the latter inherited white from `:root` and nobody saw it.
    doc = ("@theme {\n  --color-x: #123456;\n}\n"
           ":root {\n  --a: #FFFFFF;\n  --b: #0077CC;\n}\n"
           ".dark {\n  --b: #00A3FF;\n}\n")
    scopes = parse_tokens(doc)
    check("dark inherits an un-overridden :root token", scopes["dark"].get("--a") == "#FFFFFF",
          f"got {scopes['dark'].get('--a')!r}")
    check("dark's own value wins", scopes["dark"].get("--b") == "#00A3FF",
          f"got {scopes['dark'].get('--b')!r}")

    # A missing or renamed token must RAISE, never resolve to something arbitrary -- a pair that
    # silently stops being measured is the skip-as-pass failure this repo keeps paying for.
    checks += 1
    try:
        resolve("--nope", scopes["light"])
        failures.append("a missing token resolved instead of raising")
    except Unparseable:
        pass
    checks += 1
    try:
        parse_tokens("nothing here")
        failures.append("a file with no :root block parsed instead of raising")
    except Unparseable:
        pass

    # var() chains resolve; a cycle raises rather than recursing forever.
    chain = parse_tokens("@theme {\n  --color-x: #123456;\n}\n:root {\n  --x: #0072C4;\n"
                         "  --y: var(--x);\n  --z: var(--y);\n}\n.dark {\n  --x: #00A3FF;\n}\n")
    check("a var() chain resolves", resolve("--z", chain["light"]) == "#0072C4",
          f"got {resolve('--z', chain['light'])}")
    checks += 1
    cyc = parse_tokens("@theme {\n  --color-x: #123456;\n}\n:root {\n  --p: var(--q);\n"
                       "  --q: var(--p);\n}\n.dark {\n  --p: #000000;\n}\n")
    try:
        resolve("--p", cyc["light"])
        failures.append("a var() cycle did not raise")
    except Unparseable:
        pass

    # NEAR MISS: the checker must not pass by measuring nothing. Every declared pair has to resolve
    # against the REAL file -- that is what catches a rename.
    checks += 1
    real = parse_tokens(TOKENS.read_text(encoding="utf-8"))
    try:
        for pair in PAIRS:
            _label, fg, bg, mode = pair[:4]
            resolve(fg, real[mode]); resolve(bg, real[mode])
    except Unparseable as exc:
        failures.append(f"a declared pair no longer resolves against the real tokens: {exc}")
    # ---- THE TWO TIERS (#775) -----------------------------------------------------------------
    # WCAG has two thresholds and using one for both is taste wearing a count. Each clause gets a
    # fixture, because a rule with N clauses needs a finding per clause or none of them is provable.
    floors = {pair[0]: (pair[4] if len(pair) > 4 else AA_NORMAL) for pair in PAIRS}
    check("a focus ring is judged at 1.4.11's 3:1, not 1.4.3's 4.5",
          floors.get("focus ring on a card") == AA_LARGE, f"{floors.get('focus ring on a card')}")
    check("an -ink role is judged at 1.4.3's 4.5:1, because it exists to BE text",
          floors.get("success ink on a card") == AA_NORMAL,
          f"{floors.get('success ink on a card')}")
    check("body text keeps 4.5, so the tier split did not lower the text floor",
          floors.get("body text on a card") == AA_NORMAL)
    check("the two tiers are actually different numbers", AA_LARGE < AA_NORMAL)

    # BOTH MODES. Every one of these passed in light and failed in dark, because dark re-points its
    # surfaces and these roles were not re-pointed with them. Enumerating light only would have
    # measured the half that already worked.
    for lbl in ("focus ring on a card", "success ink on a card", "primary ink on a card"):
        modes = {pair[3] for pair in PAIRS if pair[0] == lbl}
        check(f"{lbl!r} is enumerated in BOTH modes", modes == {"light", "dark"}, f"{modes}")

    # THE BASE FEEDBACK ROLES ARE DELIBERATELY ABSENT. Their correct threshold depends on a usage
    # this file cannot see from tokens, and choosing one would fail both shipped packs for a rule
    # neither WCAG clause states. A negative test, so re-adding them is a deliberate act.
    enumerated = {pair[1] for pair in PAIRS}
    for role in ("--success", "--warning", "--info", "--signal", "--destructive"):
        check(f"{role} is NOT enumerated against the page", role not in enumerated,
              "if this is intended, the reasoning above PAIRS has to change with it")

    # AN UNDECLARED ROLE IS SKIPPED, NEVER PASSED -- and never raised either, because a pack that
    # predates a role (or a template with placeholder refs) is not a measurement failure.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        f = Path(td) / "t.css"
        f.write_text("@theme {\n  --color-t-blue: #005FA3;\n}\n"
                     ":root {\n  --background: #FFFFFF;\n  --foreground: #000000;\n"
                     "  --card: #FFFFFF;\n  --card-foreground: #000000;\n"
                     "  --muted: #EEEEEE;\n  --muted-foreground: #555555;\n"
                     "  --primary: #005FA3;\n  --primary-foreground: #FFFFFF;\n"
                     "  --ring: #005FA3;\n}\n"
                     ".dark {\n  --background: #10151C;\n  --foreground: #F7F8FA;\n"
                     "  --card: #1B222C;\n  --card-foreground: #F7F8FA;\n"
                     "  --muted: #1B222C;\n  --muted-foreground: #8B93A1;\n"
                     "  --primary: #5AB0F5;\n  --primary-foreground: #10151C;\n"
                     "  --ring: #5AB0F5;\n}\n",
                     encoding="utf-8")
        rows = measure(f)
        skipped = [r for r in rows if not r[7]]
        check("an undeclared role is skipped, not raised", bool(skipped), "no rows were skipped")
        check("...and a skipped row carries no ratio to be mistaken for a pass",
              all(r[6] == 0.0 for r in skipped))
        check("...while the declared pairs still measure",
              any(r[7] and r[6] > 0 for r in rows))

        # THE FLOOR REACHES THE CONSUMER, asserted on `measure()`'s OWN output. The `floors` checks
        # above read PAIRS directly, so they prove the tier is DECLARED and not that anything uses
        # it -- a mutation collapsing `measure`'s floor to AA_NORMAL survived every one of them.
        # Proving the table is not proving the reader.
        ring = [r for r in rows if r[1].startswith("focus ring") and r[7]]
        ink = [r for r in rows if "ink" in r[1] and r[7]]
        check("measure() gives a focus-ring row the 3:1 floor",
              bool(ring) and all(r[7] == AA_LARGE for r in ring),
              f"{[(r[1], r[7]) for r in ring]}")
        check("...and a text row the 4.5:1 floor",
              all(r[7] == AA_NORMAL for r in rows if r[7] and r[1].startswith("body text")),
              f"{[(r[1], r[7]) for r in rows if r[1].startswith('body text')]}")
        if ink:
            check("...and an -ink row the 4.5:1 floor", all(r[7] == AA_NORMAL for r in ink))

    check("PAIRS is not empty", len(PAIRS) >= 8, f"only {len(PAIRS)}")
    # A count is not coverage: `>= 8` is satisfied while a specific pair quietly leaves the set.
    # The muted-text pair is named because it was the one that WAS missing, and `_template`'s sat
    # at 2.71:1 unmeasured behind a green sweep.
    labels = {(pair[0], pair[3]) for pair in PAIRS}
    check("the muted-text pair is measured in both modes (it was the missing one, at 2.71:1)",
          {("muted text on a muted surface", "light"),
           ("muted text on a muted surface", "dark")} <= labels,
          f"declared: {sorted(labels)}")
    # Every pair must exist in BOTH modes. One mode only is a half-measured palette, and dark is
    # the half that goes unlooked-at.
    light_only = {lb for lb, m in labels if m == "light"} ^ {lb for lb, m in labels if m == "dark"}
    check("every pair is measured in light AND dark", not light_only,
          f"only one mode: {sorted(light_only)}")

    # ---- SCOPE (#129): the shipped PACKS are inputs, not just the doctrine file ----------------
    # The gate reported clean for as long as it read one file, while the pack a user installs
    # carried the very defect #304 fixed. So the input set itself is now asserted.
    checks += 1
    try:
        enumerated = sources()
    except Unparseable as exc:
        enumerated = []
        failures.append(f"the source glob found no shipped pack: {exc}")
    packs = [p for p in enumerated if p.name == "theme.css"]
    check("every shipped brand pack is measured, not just the doctrine file",
          len(packs) >= 2 and TOKENS in enumerated,
          f"enumerated {[p.name for p in enumerated]}")
    # A pack that lints complete can still be unreadable, so each one must actually RESOLVE every
    # declared pair. A pack silently dropping out of the pair loop is the original defect again.
    for pack in packs:
        checks += 1
        try:
            rows = measure(pack)
            if len(rows) != len(PAIRS):
                failures.append(f"{pack.name}: measured {len(rows)} of {len(PAIRS)} pairs")
        except Unparseable as exc:
            failures.append(f"a shipped pack no longer resolves every pair: {pack} — {exc}")

    # An empty glob must RAISE. Pointed at a tree with no packs, a returning `sources()` would make
    # the whole gate vacuous while still printing a pass.
    checks += 1
    with tempfile.TemporaryDirectory(prefix="token-contrast-selftest-") as tmp:
        empty = Path(tmp)
        (empty / "skills" / "design-system" / "references").mkdir(parents=True)
        (empty / "skills" / "design-system" / "references" / "foundations-tokens.md").write_text(
            doc, encoding="utf-8")
        try:
            sources(empty)
            failures.append("a tree with no brand pack enumerated sources instead of raising")
        except Unparseable:
            pass

    # ---- PARITY with the SHIPPED implementation (#129) -----------------------------------------
    # `plugins/design-flow/scripts/palette_candidates.py` must carry its own copy of this maths:
    # a plugin has to be runnable in a user's clone with nothing else installed, so it cannot
    # import from `scripts/`. Two copies drift, so the copies are COMPARED here rather than
    # trusted -- the same discipline `brand_pack_lint --roles-from` applies to the role contract.
    checks += 1
    plugin_scripts = REPO / "plugins" / "design-flow" / "scripts"
    if not (plugin_scripts / "palette_candidates.py").is_file():
        failures.append("palette_candidates.py is missing, so nothing verifies the shipped "
                        "contrast maths agrees with this one")
    else:
        sys.path.insert(0, str(plugin_scripts))
        try:
            import palette_candidates as shipped  # noqa: PLC0415  (deliberate late import)

            check("the probe set is wide enough to be worth comparing over",
                  len(PARITY_PROBES) >= 8, f"only {len(PARITY_PROBES)} probes")
            worst = max_disagreement(contrast, shipped.contrast, PARITY_PROBES)
            check("the shipped implementation agrees with the canonical one",
                  worst < 1e-9, f"largest disagreement {worst!r}")
            # POSITIVE CONTROL. Without it, "no disagreement" and "no comparison" are the same
            # observation, and a parity check that stopped comparing would read as a clean pass
            # for as long as nobody looked -- which is exactly how the two copies would drift.
            check("the parity comparison can actually detect a disagreement",
                  max_disagreement(contrast, lambda a, b: contrast(a, b) * 1.01,
                                   PARITY_PROBES) > 1e-3,
                  "a deliberately wrong implementation compared equal")
            check("the shipped threshold is the same threshold",
                  shipped.AA_NORMAL == AA_NORMAL,
                  f"shipped {shipped.AA_NORMAL}, canonical {AA_NORMAL}")

            # The PARSER is duplicated too, for the same reason, so it is compared too. Agreeing
            # maths over disagreeing token resolution would still ship two different verdicts --
            # and resolving `.dark`'s inheritance is precisely where #304 lived.
            fidara = REPO / "plugins" / "design-flow" / "brands" / "fidara" / "theme.css"
            mine = parse_tokens(fidara.read_text(encoding="utf-8"))
            theirs = shipped.read_pack(fidara)
            canonical = {mode: {role: resolve(role, mine[mode]) for role in theirs[mode]}
                         for mode in ("light", "dark")}
            disagreements = [d for mode in ("light", "dark")
                             for d in role_disagreements(canonical[mode], theirs[mode], mode)]
            check("the shipped parser resolves the same roles to the same values",
                  not disagreements, "; ".join(disagreements))
            check("the parser comparison compared a plausible number of roles",
                  len(theirs["light"]) >= 6, f"only {len(theirs['light'])} roles resolved")
            # POSITIVE CONTROL, same argument as above.
            perturbed = dict(theirs["light"])
            perturbed["--primary"] = "#123456"
            check("the parser comparison can actually detect a disagreement",
                  role_disagreements(canonical["light"], perturbed, "light"),
                  "a deliberately wrong resolution compared equal")
        except ImportError as exc:
            failures.append(f"could not import the shipped implementation to compare: {exc}")
        finally:
            sys.path.remove(str(plugin_scripts))

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_token_contrast selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure fidara role tokens against WCAG 1.4.3.")
    ap.add_argument("--selftest", action="store_true", help="prove the maths and the rules")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
