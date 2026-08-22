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
skills/fidara-design/references/foundations-tokens.md rather than assumed):

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
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# The role contract.
#
# Source of truth is skills/fidara-design/references/foundations-tokens.md (the `:root`
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

# A pack is a THEME, not a fork: it declares colours, a logo, and the proof its chart hues
# still work. fonts / knobs / chart_hues are optional overrides that inherit the system's
# calibrated defaults when absent — so their absence must never be an error, or every client
# pack would be forced to restate choices it is not changing.
REQUIRED_MANIFEST_KEYS = ["slug", "name", "chart_palette_validated", "variants"]
OPTIONAL_OVERRIDES = ["fonts", "knobs", "chart_hues", "default_variant"]
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


def selector_block(src: str, selector: str) -> str:
    """Body of the LAST matching block (a later block wins in CSS).

    Leading whitespace is tolerated on both the selector and its closing brace: a
    formatter that indents `:root { … }` must not make the lint report every role
    missing. Anchoring to column 1 produced exactly that false failure.
    """
    bodies = re.findall(
        r"^[ 	]*" + re.escape(selector) + r"\s*\{(.*?)^[ 	]*\}", src, re.S | re.M
    )
    return bodies[-1] if bodies else ""


def declared_tokens(body: str) -> set[str]:
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", body))


def theme_primitives(src: str) -> set[str]:
    """Tokens defined in any @theme block (the pack's private primitives)."""
    found: set[str] = set()
    for body in re.findall(r"@theme[^{]*\{(.*?)^[ 	]*\}", src, re.S | re.M):
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
    unused = [f for f in present if wanted and f not in wanted]
    if unused:
        report.warn(f"asset(s) not referenced by any variant: {unused}")


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
    parser.add_argument("--include-templates", action="store_true",
                        help="also lint `_`-prefixed template dirs (they fail by design until "
                             "copied and validated)")
    args = parser.parse_args(argv)

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
