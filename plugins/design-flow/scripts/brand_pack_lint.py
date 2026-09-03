#!/usr/bin/env python3
"""brand-pack completeness lint — design-flow.

A brand pack that omits a role the components consume does not fail loudly: the role
falls back to a stock Tailwind colour and the brand quietly breaks in one corner of the
app. So completeness is CHECKED, not trusted. A pack is not finished until this exits 0.

What it verifies:
  1. brand.json  — required keys, knob values from the documented enums, chart hues
                   present and `chart_palette_validated: true`
  2. theme.css   — every role in the contract is defined in :root
  3.              — surface roles carry their `-foreground` companion
  4.              — surface roles are re-pointed under .dark
  5.              — no var() reference points at a primitive the pack never defines
  6.              — no component-level CSS leaked into the pack

Two subtleties this encodes, both easy to get wrong by hand (and both measured from
skills/design-system/references/foundations-tokens.md rather than assumed):

  * `--background`'s companion is `--foreground`, NOT `--background-foreground`.
  * The feedback roles and `--ring` are deliberately NOT re-pointed on dark. Requiring a
    dark value for every role would fail every correct pack — a wrong check is worse
    than no check, because people stop believing the ones that are right.

Stdlib only, by design: a pack must be lintable in any clone with nothing installed.

Usage:
  python3 brand_pack_lint.py brands/acme            # lint one pack
  python3 brand_pack_lint.py brands/*               # lint all real packs
                                                    #   (`_`-prefixed dirs are templates,
                                                    #    skipped — see --include-templates)
  python3 brand_pack_lint.py --list-contract        # print the role contract and exit
  python3 brand_pack_lint.py --roles-from <md> …     # re-derive the contract from doctrine

Exit: 0 all packs complete · 1 at least one problem · 2 usage/environment.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# The role contract.
#
# Source of truth is skills/design-system/references/foundations-tokens.md (the `:root`
# and `.dark` blocks). It is duplicated here so the lint runs with no skill installed —
# and because two copies drift, `--roles-from` re-derives it from that file and reports
# any disagreement. Same discipline as the release-workflow/local-script mirror: if you
# change one, check the other.
# --------------------------------------------------------------------------

ROLES = [
    "--background", "--foreground",
    "--card", "--card-foreground",
    "--popover", "--popover-foreground",
    "--primary", "--primary-foreground",
    "--secondary", "--secondary-foreground",
    "--muted", "--muted-foreground",
    "--accent", "--accent-foreground",
    "--destructive", "--destructive-foreground",
    "--success", "--warning", "--info",
    "--border", "--input", "--ring",
    # #750. Added with the roles themselves, in the same commit, because this list is the ONLY thing
    # that makes a role required -- `foundations-tokens.md` declaring one and this list omitting it
    # means no pack must supply it, nothing downstream can rely on it, and the doctrine is a suggestion.
    # That is exactly what happened for the five below until a live project reported reaching for
    # `bg-fm-navy/50` because `--overlay` existed nowhere.
    "--overlay",
    "--signal", "--signal-foreground",
    "--primary-ink", "--primary-hover",
    "--success-ink",
]

# Surfaces whose value MUST change between light and dark. Everything else may legitimately
# hold one value across both themes.
DARK_REQUIRED = [
    "--background", "--foreground",
    "--card", "--card-foreground",
    "--popover", "--popover-foreground",
    "--secondary", "--secondary-foreground",
    "--muted", "--muted-foreground",
    "--accent", "--accent-foreground",
    "--border", "--input",
    "--primary",
]

# `--background` pairs with `--foreground`, not `--background-foreground`.
FOREGROUND_EXCEPTIONS = {"--background": "--foreground"}

# Roles that are a surface (i.e. something is drawn on top of them) and therefore need a
# readable companion. Derived from the contract: a role X is a surface when X-foreground
# exists, plus the --background/--foreground exception.
def surface_pairs() -> dict[str, str]:
    pairs = {r: r + "-foreground" for r in ROLES if r + "-foreground" in ROLES}
    pairs.update(FOREGROUND_EXCEPTIONS)
    return pairs


KNOB_ENUMS = {
    "section_rhythm": {"generous", "compact"},
    "radius": {"md-controls-lg-cards", "soft"},
    "heading_ramp": {"mid-range", "hero-heavy"},
}

# The `radius` knob expands into a five-step ramp inside the managed block -- `setup` writes all five,
# the doctrine declares only three (`--radius`, `--radius-sm`, `--radius-lg`). ONE definition of the
# step NAMES, here beside the knob that produces them, so `check_token_drift` and `setup` cannot
# disagree about what a knob-bearing pack owns (#899). Values are the knob's call, not compared.
RADIUS_RAMP_STEPS = ("--radius", "--radius-sm", "--radius-md", "--radius-lg", "--radius-xl")

# A pack is a THEME, not a fork: it declares colours, a logo, and the proof its chart hues
# still work. fonts / knobs / chart_hues are optional overrides that inherit the system's
# calibrated defaults when absent — so their absence must never be an error, or every client
# pack would be forced to restate choices it is not changing.
REQUIRED_MANIFEST_KEYS = ["slug", "name", "chart_palette_validated", "variants"]
OPTIONAL_OVERRIDES = ["fonts", "knobs", "chart_hues", "default_variant", "wordmark"]
REQUIRED_FONT_ROLES = ["sans", "display", "mono"]

# A pack is tokens only. These signal component/layout CSS leaking in.
LEAK_PATTERNS = [
    (r"@utility\b", "@utility recipe (layout primitives are system-level, not per-brand)"),
    (r"@apply\b", "@apply (components are system-level)"),
    (r"^\s*\.(btn|card|badge|alert|modal|sidebar)\b", "component class"),
]


# --------------------------------------------------------------------------
# css parsing (regex, deliberately: a pack theme.css is a known, small shape)
# --------------------------------------------------------------------------

def strip_css_comments(src: str) -> str:
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def selector_blocks(src: str, selector: str) -> list[str]:
    """EVERY block whose selector list contains `selector`, in source order.

    `selector_block` returns only the last, which is right for a VALUE (the cascade) and wrong for
    PRESENCE: a stylesheet may legitimately declare `:root` more than once -- `/design-flow:setup`
    scaffolds roles and the scale separately -- and taking the last made every token in the earlier
    block read as absent. #814 hit that as 28 spurious `missing` findings. One implementation, two
    views: `selector_block` is the last of these.
    """
    out = []
    for m in re.finditer(r"^[ \t]*([^{}@]*?)\{(.*?)^[ \t]*\}", src, re.S | re.M):
        if selector in [part.strip() for part in m.group(1).split(",")]:
            out.append(m.group(2))
    return out


def selector_block(src: str, selector: str) -> str:
    r"""Body of the LAST block whose selector LIST contains `selector` (a later block wins).

    Leading whitespace is tolerated on both the selector and its closing brace: a
    formatter that indents `:root { … }` must not make the lint report every role
    missing. Anchoring to column 1 produced exactly that false failure.

    A SELECTOR LIST IS MATCHED BY MEMBERSHIP, not by the selector abutting its brace
    (#764). `:root, .light { … }` is ordinary CSS and is what design-system's own
    dark-mode guidance leads to -- a `.light` island re-lighting a subtree, since custom
    properties inherit. The old pattern required `\s*\{` right after the selector, so the
    `, .light` made the whole block invisible and every caller read the empty string as
    "declares nothing" rather than "not found": a real pack's 24 role tokens were reported
    as zero, `brand_pack_lint` raised a hard error and abandoned every downstream check,
    and the canvas prompt silently omitted its token list. That is the same false failure
    the paragraph above records for column-1 anchoring, one case further out.

    MEMBERSHIP IS EXACT, so a compound narrows rather than matches: `:root.theme-a { … }`
    is a different selector and does NOT count as `:root`, because it applies only when the
    class is also present and its declarations are therefore not unconditional. Splitting on
    `,` and comparing trimmed members gives that for free -- `:root.theme-a` != `:root`.
    """
    blocks = selector_blocks(src, selector)
    return blocks[-1] if blocks else ""


def declared_tokens(body: str) -> set[str]:
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", body))


def theme_bodies(src: str) -> list[str]:
    """The body of every `@theme` block — `@theme`, `@theme inline`, any variant.

    Separated from `theme_primitives` so a caller that needs VALUES has them. Names alone were
    enough while the only question was "is this token declared"; #814 needs the value, because an
    `@theme inline` bridge is recognised by pointing at a role (`--color-primary: var(--primary)`)
    rather than by its name — a positive signal needs no list to go stale.
    """
    return re.findall(r"@theme[^{]*\{(.*?)^[ 	]*\}", src, re.S | re.M)


def theme_primitives(src: str) -> set[str]:
    """Tokens defined in any @theme block (the pack's private primitives)."""
    found: set[str] = set()
    for body in theme_bodies(src):
        found |= declared_tokens(body)
    return found


def var_references(body: str) -> set[str]:
    return set(re.findall(r"var\(\s*(--[a-z0-9-]+)", body))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

class Report:
    def __init__(self, pack: str):
        self.pack = pack
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.facts: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def fact(self, msg: str) -> None:
        self.facts.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_manifest(path: str, report: Report) -> dict:
    if not os.path.exists(path):
        report.error("brand.json is missing — a pack without a manifest has no identity, "
                     "no knob choices, and no recorded palette validation.")
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except ValueError as exc:
        report.error(f"brand.json is not valid JSON: {exc}")
        return {}

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            report.error(f"brand.json: missing required key `{key}`")

    # ---- variants: identity only, never values (that is what prevents drift) ----
    variants = data.get("variants")
    if isinstance(variants, dict):
        if not variants:
            report.error("brand.json: `variants` is empty — declare at least one "
                         "(a single-brand pack has one variant with endorsement: null)")
        for slug, v in sorted(variants.items()):
            if not isinstance(v, dict):
                report.error(f"brand.json: variants.{slug} must be an object")
                continue
            if not v.get("name"):
                report.error(f"brand.json: variants.{slug}.name is required (the display label)")
            if "endorsement" not in v:
                report.error(f"brand.json: variants.{slug}.endorsement is required — use null "
                             "for a parent or standalone brand. A parent does not endorse itself; "
                             "the endorsement ties a PRODUCT to its parent.")
            if not v.get("mark"):
                report.warn(f"variants.{slug}.mark not set — Ui::Logo will fall back to the "
                            "scaffolded placeholder mark")
            leaked = sorted(set(v) - {"name", "endorsement", "mark"})
            if leaked:
                report.error(f"brand.json: variants.{slug} carries {leaked} — a variant re-LABELS, "
                             "it does not re-theme. Values belong to the pack, or it is a "
                             "separate pack.")
        default = data.get("default_variant")
        if default is not None and default not in variants:
            report.error(f"brand.json: default_variant {default!r} is not one of "
                         f"{sorted(variants)}")
        if default is None and len(variants) > 1:
            report.error("brand.json: default_variant is required when a pack has more than one "
                         "variant (otherwise selection is ambiguous)")
    elif "variants" in data:
        report.error("brand.json: `variants` must be an object keyed by variant slug")

    # ---- optional overrides: validated IF present, never required ----
    # Absence means "inherit the system default", which is the normal case for a client pack.
    fonts = data.get("fonts")
    if fonts is not None:
        if isinstance(fonts, dict):
            for role in REQUIRED_FONT_ROLES:
                if not fonts.get(role):
                    report.error(f"brand.json: fonts is present but fonts.{role} is missing — "
                                 "override all three roles or omit `fonts` entirely to inherit")
            report.fact("overrides fonts (rare — records a deliberate deviation)")
        else:
            report.error("brand.json: `fonts` must be an object keyed by sans/display/mono")

    knobs = data.get("knobs")
    if knobs is not None:
        if isinstance(knobs, dict):
            for knob, value in sorted(knobs.items()):
                if knob not in KNOB_ENUMS:
                    report.error(f"brand.json: unknown knob {knob!r} "
                                 f"(known: {sorted(KNOB_ENUMS)})")
                elif value not in KNOB_ENUMS[knob]:
                    report.error(f"brand.json: knobs.{knob} = {value!r} is not one of "
                                 f"{sorted(KNOB_ENUMS[knob])}")
            report.fact(f"overrides knob(s): {', '.join(sorted(knobs))}")
        else:
            report.error("brand.json: `knobs` must be an object")

    hues = data.get("chart_hues")
    if hues is not None:
        if isinstance(hues, list):
            if len(hues) < 3:
                report.error(f"brand.json: chart_hues has {len(hues)} entries; a categorical "
                             "palette needs at least 3 to be worth validating")
            bad = [h for h in hues if not (isinstance(h, str)
                                           and re.fullmatch(r"#[0-9A-Fa-f]{6}", h))]
            if bad:
                report.error(f"brand.json: chart_hues entries must be #RRGGBB — bad: {bad}")
            report.fact(f"overrides {len(hues)} chart hue(s)")
        else:
            report.error("brand.json: `chart_hues` must be a list of #RRGGBB strings")

    unknown = sorted(set(data) - set(REQUIRED_MANIFEST_KEYS) - set(OPTIONAL_OVERRIDES)
                     - {"voice"})
    if unknown:
        report.warn(f"brand.json: unrecognised key(s) {unknown} — a pack is colours + logo; "
                    "anything else is probably system-level and belongs in the skill, not here")

    if data.get("chart_palette_validated") is not True:
        report.error("brand.json: chart_palette_validated must be true. Hues that separate "
                     "cleanly on one brand's surface can collide on another's — run the "
                     "data-viz validator for THIS pack, then set the flag.")

    if data.get("slug") and os.path.basename(os.path.normpath(os.path.dirname(path))) != data["slug"]:
        report.warn(f"brand.json: slug {data['slug']!r} does not match the directory name "
                    f"{os.path.basename(os.path.normpath(os.path.dirname(path)))!r}")
    return data


def lint_theme(path: str, report: Report) -> None:
    if not os.path.exists(path):
        report.error("theme.css is missing — the pack defines no theme layer at all.")
        return
    raw = open(path, encoding="utf-8").read()
    src = strip_css_comments(raw)

    root = selector_block(src, ":root")
    dark = selector_block(src, ".dark")
    if not root:
        report.error("theme.css has no top-level `:root { … }` block, so it defines no roles.")
        return

    defined = declared_tokens(root)
    dark_defined = declared_tokens(dark)
    primitives = theme_primitives(src)
    report.fact(f"{len(primitives)} primitive(s) in @theme, {len(defined)} role(s) in :root, "
                f"{len(dark_defined)} dark re-point(s)")

    missing = [r for r in ROLES if r not in defined]
    if missing:
        report.error(f"{len(missing)} role(s) never defined — each would fall back to a stock "
                     f"colour: {' '.join(missing)}")

    for surface, companion in sorted(surface_pairs().items()):
        if surface in defined and companion not in defined:
            report.error(f"{surface} is defined without its companion {companion} "
                         "(always write bg-X together with text-X-foreground)")

    if dark:
        missing_dark = [r for r in DARK_REQUIRED if r in defined and r not in dark_defined]
        if missing_dark:
            report.error(f"{len(missing_dark)} surface role(s) not re-pointed under .dark: "
                         f"{' '.join(missing_dark)}")
    else:
        report.error("theme.css has no `.dark { … }` block, so dark mode would inherit light "
                     "surfaces. Re-point the surface roles.")

    # Every var() must resolve to something this pack defines (primitive or role).
    known = primitives | defined | dark_defined
    unresolved = sorted((var_references(root) | var_references(dark)) - known)
    if unresolved:
        report.error(f"var() references not defined anywhere in this pack: "
                     f"{' '.join(unresolved)}")

    extra = sorted(defined - set(ROLES))
    if extra:
        report.warn(f"role-layer token(s) outside the contract (harmless, but components "
                    f"cannot consume them): {' '.join(extra)}")

    for pattern, label in LEAK_PATTERNS:
        if re.search(pattern, src, re.M):
            report.error(f"{label} found in theme.css — a pack is tokens only. If a pack "
                         "needs to change a component, the component is wrong.")


def lint_assets(pack_dir: str, report: Report, manifest: dict) -> None:
    """The logo is HALF of what a pack declares, so a mark that brand.json points at must
    actually exist. Without this a pack lints clean and then renders no logo at all."""
    assets = os.path.join(pack_dir, "assets")
    variants = manifest.get("variants") if isinstance(manifest.get("variants"), dict) else {}
    wanted = sorted({v["mark"] for v in variants.values()
                     if isinstance(v, dict) and v.get("mark")})

    if not os.path.isdir(assets):
        if wanted:
            report.error(f"brand.json references mark(s) {wanted} but there is no assets/ "
                         "directory — the logo would be missing at render time")
        else:
            report.warn("no assets/ directory — the pack carries no logo/mark, so Ui::Logo will "
                        "fall back to the scaffolded placeholder")
        return

    present = [f for f in sorted(os.listdir(assets)) if f.endswith(".svg")]
    missing = [m for m in wanted if not os.path.exists(os.path.join(assets, m))]
    if missing:
        report.error(f"mark file(s) referenced by brand.json but absent from assets/: "
                     f"{missing} (present: {present or 'none'})")
    if not present:
        report.warn("assets/ contains no .svg — expected at least a mark")
    else:
        report.fact(f"{len(present)} svg asset(s): {', '.join(present)}"
                    + (f" — marks in use: {', '.join(wanted)}" if wanted else ""))
    # THE PACK-LEVEL WORDMARK (#771). A landscape logo is not a variant's property -- a variant
    # re-LABELS (name, endorsement, mark), it does not re-theme -- so there was nowhere for a
    # second published lockup to live, and every pack shipping one carried a permanent
    # "not referenced by any variant" warning it could never clear. A warning nobody can clear is
    # one everybody learns to ignore, which costs more than the orphan-detection it provides.
    #
    # So the PACK may name one, and it is then referenced rather than orphaned. This stays
    # deliberately narrow: one optional string, validated for existence exactly like a mark. It is
    # NOT a variant key, because the reason a variant cannot carry it still holds.
    wordmark = manifest.get("wordmark")
    if wordmark is not None:
        # Each clause guards ITSELF rather than leaning on the one above. Written as an if/elif,
        # removing the type check sent a non-string straight into os.path.join, which raised
        # TypeError -- so the mutation proving that clause CRASHED the suite instead of failing it,
        # and a crash is not a verdict. `named` short-circuits, so join only ever sees a str.
        named = isinstance(wordmark, str) and wordmark.endswith(".svg")
        # Its OWN isinstance, not `named and ...`: a mutation forcing `named` True defeated
        # the short-circuit and crashed join. Each guard has to hold on its own.
        exists = isinstance(wordmark, str) and os.path.exists(os.path.join(assets, wordmark))
        if not named:
            report.error(f"brand.json: wordmark must be an .svg filename, got {wordmark!r}")
        elif not exists:
            report.error(f"brand.json references wordmark {wordmark!r} but it is absent from "
                         f"assets/ (present: {present or 'none'})")
        else:
            report.fact(f"wordmark: {wordmark}")

    referenced = set(wanted) | ({wordmark} if isinstance(wordmark, str) else set())
    unused = [f for f in present if referenced and f not in referenced]
    if unused:
        report.warn(f"asset(s) not referenced by any variant or wordmark: {unused}")


def lint_pack(pack_dir: str) -> Report:
    report = Report(pack_dir)
    if not os.path.isdir(pack_dir):
        report.error("not a directory")
        return report
    manifest = lint_manifest(os.path.join(pack_dir, "brand.json"), report)
    lint_theme(os.path.join(pack_dir, "theme.css"), report)
    lint_assets(pack_dir, report, manifest)
    return report


# --------------------------------------------------------------------------
# contract parity with the doctrine file
# --------------------------------------------------------------------------

def roles_from_doctrine(path: str) -> tuple[list[str], list[str]]:
    src = open(path, encoding="utf-8").read()

    def body(sel: str) -> str:
        m = re.search(r"^" + re.escape(sel) + r"\s*\{(.*?)^\}", src, re.S | re.M)
        return m.group(1) if m else ""

    light = sorted(declared_tokens(body(":root")))
    dark = sorted(declared_tokens(body(".dark")))
    return light, dark


def check_contract_parity(path: str) -> int:
    if not os.path.exists(path):
        print(f"brand_pack_lint: {path} not found", file=sys.stderr)
        return 2
    light, dark = roles_from_doctrine(path)
    embedded, doctrine = set(ROLES), set(light)
    problems = 0
    only_doc = sorted(doctrine - embedded)
    only_emb = sorted(embedded - doctrine)
    if only_doc:
        print(f"  doctrine defines role(s) the lint does not know: {' '.join(only_doc)}")
        problems += 1
    if only_emb:
        print(f"  lint requires role(s) doctrine does not define: {' '.join(only_emb)}")
        problems += 1
    stale = sorted(set(DARK_REQUIRED) - set(dark))
    if stale:
        print(f"  lint requires dark re-points doctrine does not make: {' '.join(stale)}")
        problems += 1
    if problems:
        print("\n  CONTRACT DRIFT — reconcile ROLES/DARK_REQUIRED with the doctrine file.")
        return 1
    print(f"  contract in sync: {len(embedded)} roles, "
          f"{len(DARK_REQUIRED)} required dark re-points "
          f"(doctrine re-points {len(dark)}, the rest legitimately share one value)")
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def selftest() -> int:
    """Fixtures for the CSS parser five call sites share (#764).

    `selector_block` had no suite of its own -- it was only ever exercised incidentally, as a
    dependency of other guards -- which is exactly how a selector list stayed invisible to it while
    `brand_pack_lint`, `palette_candidates` and `design_prompt` all read its empty string as "this
    pack declares nothing". A shared parser with no direct fixtures is a single point of silent
    failure for every consumer.
    """
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def toks(css: str) -> list[str]:
        return sorted(declared_tokens(selector_block(strip_css_comments(css), ":root")))

    def block(sel: str) -> str:
        return "@theme {\n  --color-brand: #0077CC;\n}\n" + sel + "\n  --background: #FAF7F2;\n  --primary: var(--color-brand);\n}\n"

    WANT = ["--background", "--primary"]

    # THE CONTROL. Without it every membership case below could pass on a parser that matched
    # anything at all, and the bug being fixed would be untestable in the other direction.
    check("a bare :root is read", toks(block(":root {")) == WANT, f"{toks(block(':root {'))}")

    # #764, the reported shape and its whitespace variants. Each is ordinary CSS a formatter emits.
    for label, sel in (("grouped", ":root, .light {"), ("no spaces", ":root,.light{"),
                       ("spaced", ":root , .light {"), ("reversed", ".light, :root {"),
                       ("indented", "  :root, .light {")):
        check(f"a {label} selector list is read", toks(block(sel)) == WANT, f"{toks(block(sel))}")

    ml = "@theme {\n  --x: 1px;\n}\n.light,\n:root {\n  --background: #FAF7F2;\n}\n"
    check("a multi-line selector list is read", toks(ml) == ["--background"], f"{toks(ml)}")

    # THE NEGATIVE, and it is the one that keeps the fix honest. A compound NARROWS the selector --
    # `:root.theme-a` applies only when the class is present, so its declarations are not
    # unconditional and must not be read as the pack's roles. Without this, "match if `:root`
    # appears in the prelude" would pass every case above and be wrong.
    check("a compound is NOT a member", toks(block(":root.theme-a {")) == [],
          f"{toks(block(':root.theme-a {'))}")
    check("a different selector is not matched", toks(block(".light {")) == [],
          f"{toks(block('.light {'))}")

    # AT-RULES are not selector lists. `@theme { ... }` must not be mistaken for a block.
    check("an at-rule is not a selector block",
          selector_block(strip_css_comments("@theme {\n  --color-x: red;\n}\n"), ":root") == "")

    # ...and the `@` in the prelude character class is what makes a NESTED :root still reachable.
    # Without it the regex matches the at-rule's own prelude first, consumes the inner block as its
    # body, and the `:root` inside is never offered -- so a pack declaring roles inside `@media`
    # would silently read as empty. The pre-#764 parser found that block, so dropping the guard
    # would be a regression this fix introduced rather than a behaviour it preserved. A mutation
    # removing `@` survived until this case existed; the `@theme` check above could not see it,
    # because `["@theme"]` does not contain `":root"` either way.
    nested = "@media (min-width: 40rem) {\n:root, .light {\n  --background: #000;\n}\n}\n"
    check("a :root nested in an at-rule is still read",
          declared_tokens(selector_block(strip_css_comments(nested), ":root")) == {"--background"},
          repr(selector_block(strip_css_comments(nested), ":root")))

    # LAST BLOCK WINS -- CSS cascade order, and the property the docstring promised before #764.
    # Both directions, because one alone would pass on a parser that always returned the grouped
    # block or always returned the bare one.
    later_grouped = ":root {\n  --background: #111;\n}\n:root, .light {\n  --background: #FAF7F2;\n}\n"
    later_bare = ":root, .light {\n  --background: #FAF7F2;\n}\n:root {\n  --background: #111;\n}\n"
    check("a later grouped block wins", "#FAF7F2" in selector_block(strip_css_comments(later_grouped), ":root"),
          repr(selector_block(strip_css_comments(later_grouped), ":root")))
    check("a later bare block wins", "#111" in selector_block(strip_css_comments(later_bare), ":root"),
          repr(selector_block(strip_css_comments(later_bare), ":root")))

    # THE REAL PACK, so the fixtures above cannot drift away from the shape actually shipped.
    # `parents[1]` is safe here where #617's parent-counting was not: this stays INSIDE one plugin,
    # whose layout is fixed, rather than reaching across the clone/install boundary where the cache
    # interposes `<bundle>/<version>/` and the two shapes differ in depth.
    theme = Path(__file__).resolve().parents[1] / "brands" / "fidara" / "theme.css"
    if theme.is_file():
        got = declared_tokens(selector_block(strip_css_comments(theme.read_text(encoding="utf-8")), ":root"))
        check("the shipped fidara pack still parses", len(got) >= 20, f"only {len(got)} role token(s)")
    else:
        print(f"  [skip] the shipped fidara pack ({theme}) is absent — that check did NOT run")

    # ---- THE PACK-LEVEL WORDMARK (#771) ------------------------------------------------------
    # Four clauses, four fixtures. The LAST one is the one that matters: without it this change
    # would be indistinguishable from simply deleting orphan detection, which is the failure mode
    # of every "silence the warning" fix.
    import tempfile as _tf

    def assets_report(files: list[str], manifest: dict) -> Report:
        with _tf.TemporaryDirectory() as td:
            a = Path(td) / "assets"
            a.mkdir()
            for f in files:
                (a / f).write_text("<svg/>", encoding="utf-8")
            r = Report(td)
            lint_assets(td, r, manifest)
            return r

    base = {"variants": {"v": {"name": "V", "endorsement": None, "mark": "m.svg"}}}

    r = assets_report(["m.svg", "logo.svg"], {**base, "wordmark": "logo.svg"})
    check("a declared wordmark is not an orphan",
          not any("not referenced" in w for w in r.warnings), f"{r.warnings}")
    check("...and it is reported as a fact", any("wordmark: logo.svg" in f for f in r.facts),
          f"{r.facts}")

    r = assets_report(["m.svg"], {**base, "wordmark": "logo.svg"})
    check("a wordmark naming a missing file is an ERROR",
          any("absent from assets" in e for e in r.errors), f"{r.errors}")

    r = assets_report(["m.svg", "logo.svg"], {**base, "wordmark": 7})
    check("a non-string wordmark is an ERROR",
          any("must be an .svg filename" in e for e in r.errors), f"{r.errors}")

    # THE NEGATIVE. An asset that nothing names is STILL an orphan -- the check this change
    # narrowed must not have been switched off by it.
    r = assets_report(["m.svg", "stale.svg"], base)
    check("an unnamed asset is STILL reported as an orphan",
          any("stale.svg" in w for w in r.warnings), f"{r.warnings}")
    r = assets_report(["m.svg", "logo.svg", "stale.svg"], {**base, "wordmark": "logo.svg"})
    check("...even alongside a declared wordmark",
          any("stale.svg" in w for w in r.warnings) and not any("logo.svg" in w for w in r.warnings),
          f"{r.warnings}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} brand-pack-lint assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="brand_pack_lint.py",
        description="Verify a brand pack defines every role the components consume.",
    )
    parser.add_argument("packs", nargs="*", help="pack directories (e.g. brands/acme)")
    parser.add_argument("--list-contract", action="store_true",
                        help="print the role contract and exit")
    parser.add_argument("--roles-from", metavar="FILE",
                        help="re-derive the contract from foundations-tokens.md and report drift")
    parser.add_argument("--quiet", action="store_true", help="only report problems")
    parser.add_argument("--selftest", action="store_true",
                        help="run the parser fixtures and exit")
    parser.add_argument("--include-templates", action="store_true",
                        help="also lint `_`-prefixed template dirs (they fail by design until "
                             "copied and validated)")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if args.list_contract:
        print(f"role contract ({len(ROLES)}):")
        for i in range(0, len(ROLES), 4):
            print("   ", "  ".join(ROLES[i:i + 4]))
        print(f"\nmust be re-pointed under .dark ({len(DARK_REQUIRED)}):")
        for i in range(0, len(DARK_REQUIRED), 4):
            print("   ", "  ".join(DARK_REQUIRED[i:i + 4]))
        print("\nnot required on dark (one value legitimately serves both):")
        print("   ", "  ".join(sorted(set(ROLES) - set(DARK_REQUIRED))))
        return 0

    if args.roles_from:
        return check_contract_parity(args.roles_from)

    if not args.packs:
        parser.print_usage(sys.stderr)
        print("brand_pack_lint: give at least one pack directory.", file=sys.stderr)
        return 2

    # `brands/*` is the documented invocation, and the shipped `_template` fails by design
    # until it is copied and its palette validated. Skipping `_`-prefixed dirs keeps the glob
    # honest — otherwise the documented command always exits non-zero even when every real
    # pack is complete, and a check that always fails gets ignored.
    packs = list(args.packs)
    skipped = []
    if not args.include_templates:
        keep = []
        for path in packs:
            if os.path.basename(os.path.normpath(path)).startswith("_"):
                skipped.append(path)
            else:
                keep.append(path)
        packs = keep
    if skipped and not args.quiet:
        for path in skipped:
            print(f"SKIP  {path} (template; --include-templates to lint it)")
    if not packs:
        print("brand_pack_lint: nothing to lint (only template dirs were given).",
              file=sys.stderr)
        return 0 if skipped else 2

    reports = [lint_pack(p) for p in packs]
    failed = 0
    for report in reports:
        header = f"{report.pack}"
        if report.ok and not report.warnings:
            if not args.quiet:
                print(f"OK    {header}")
                for fact in report.facts:
                    print(f"        {fact}")
            continue
        print(f"{'FAIL ' if not report.ok else 'WARN '} {header}")
        for fact in report.facts:
            print(f"        {fact}")
        for msg in report.errors:
            print(f"  error: {msg}")
        for msg in report.warnings:
            print(f"  warn:  {msg}")
        if not report.ok:
            failed += 1

    if failed:
        print(f"\n{failed} of {len(reports)} pack(s) incomplete. A missing role does not "
              "error at runtime — it silently renders a stock colour, which is why this "
              "check exists.")
        return 1
    if not args.quiet:
        print(f"\n{len(reports)} pack(s) complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
