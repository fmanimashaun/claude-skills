#!/usr/bin/env python3
"""variant-set conformance — design-flow (#160).

Variant mode generates N compositions of one brief so the human **chooses** rather than
approves. The whole thing rests on one constraint, and it is the constraint that keeps this
from becoming the style menu we declined: **every variant is fully brand-conformant, and the
variants differ in COMPOSITION ONLY** — same tokens, same components, same API. Arrangement
varies; identity does not.

A constraint stated in prose is the claims-vs-enforcement defect this repo warns about most.
So it is checked.

WHAT #160 ASKED FOR, AND WHERE IT WAS WRONG.

Criterion 2 says conformance is *"asserted by running `brand_pack_lint` and the #157 detector
against each [variant], not by inspection"*. Half of that is right and half is a category
error, and implementing it as written would have produced a gate that cannot run:

  * `llm_tell_detector.py` takes FILE paths, so running it per variant file is exactly right.
    It is run here, not reimplemented — a second copy of its seven rules would drift from the
    first, and criterion 7 of #157 forbade that duplication for the same reason.
  * `brand_pack_lint.py` takes a brand-pack DIRECTORY (`brands/<slug>`) and validates
    `brand.json` + `theme.css`. A variant is a set of `.html.erb` partials. It cannot be run
    against one, and it should not be: pack completeness is a property of the PACK, identical
    for every variant drawn from it. Running it N times would prove one thing N times while
    proving nothing at all about the variants. It stays a separate check, run once, on the
    pack (`checks.json` -> `brand-pack`).

So the assertion #160 wanted needs a third thing, which is this file: the per-variant-set
invariants neither existing check covers.

THE RULES, AND WHY EACH ONE IS MECHANICAL RATHER THAN TASTE.

  variant-set-undeclared        a set directory with no readable manifest. The switcher renders
                                what the manifest declares; without one there is no set, only
                                loose partials nobody can discard confidently.
  variant-set-too-small         fewer than two variants. #160: "a single output invites a yes/no,
                                which tends to become yes." One variant is not a choice.
  variant-missing-rationale     criterion 4 — each variant carries a one-line rationale, so the
                                choice is informed rather than aesthetic.
  variant-file-mismatch         a declared file that is absent, or a partial in the set directory
                                that no variant declares. Both directions, because an undeclared
                                partial is scaffolding the discard step will miss.
  variant-declares-styling      a variant that brings its own CSS, `@theme`, `@apply`, a custom
                                property or an inline `style=`. brand.md:149-151 — "Nothing else
                                belongs in a pack: no component CSS, no utilities, no layout
                                rules." A variant has even less licence than a pack: it may
                                arrange, not style.
  variant-names-pack-primitive  a variant naming a primitive the pack declares privately.
                                brand.md:78-82 — "Components consume roles only ... Nothing
                                outside the pack may reference a primitive by name." This is the
                                "same tokens" half of #160's constraint, and it is the one rule
                                here that the context-free detector CANNOT have: knowing whether
                                `fm-navy` is a primitive requires reading the pack. That is the
                                same split as `rendered_conformance.py` (needs a browser) versus
                                `llm_tell_detector.py` (needs nothing) — a real difference in
                                what the check must be handed, not an arbitrary placement.
  variant-set-not-distinct      two variants with an identical composition signature. It detects
                                IDENTITY, never similarity: "these two feel samey" is taste and a
                                rule that cries wolf gets switched off. The signature is the
                                ordered structural tags plus render targets, so two variants whose
                                copy differs but whose arrangement does not are still caught.
  variant-tell                  an `llm_tell_detector` finding in a variant file (criterion 2).
  variant-switcher-unguarded    the switcher route reachable outside development. #160 does not
                                mention this and it is the one omission that could reach a user:
                                a route that renders every rejected variant is a production
                                surface nobody meant to ship.
  variant-scaffolding-left-behind
                                `--verify-discard` — criterion 5 says picking one "removes the
                                others and the switcher, leaving no scaffolding behind". An
                                un-run discard step looks exactly like a completed one, so it is
                                a check rather than a sentence in a command.

WHAT IT DELIBERATELY DOES NOT CHECK.

  * Whether the variants are any GOOD. That is the human's job and the entire point of the
    feature; a checker with an opinion here would be re-introducing the taste it exists to
    delegate.
  * Whether a variant is "different enough". See variant-set-not-distinct above.
  * Rendered output. Contrast, computed cascade and real-viewport behaviour belong to
    `rendered_conformance.py`, which has a browser. This reads files and runs anywhere.

Exit codes:  0 clean · 1 findings · 2 unusable (no app root, nothing to check, bad input)

A run that examined ZERO variant sets exits 2, not 0. "No findings" over no input is
indistinguishable from a pass, and that is the shape this repo keeps catching in its own gates.

Stdlib only — same constraint as `brand_pack_lint.py` and `llm_tell_detector.py`: a user must be
able to run it in a fresh clone with nothing installed.

Usage:
  python3 variant_conformance.py [APP_ROOT]            # lint every variant set in the app
  python3 variant_conformance.py --pack DIR [APP_ROOT]  # force pack resolution
  python3 variant_conformance.py --verify-discard [APP_ROOT]
  python3 variant_conformance.py --list-rules
  python3 variant_conformance.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))

# The detector is RUN, not reimplemented (see the docstring). A failed import is fatal rather
# than a quiet fallback to a private copy of its rules: two rule sets drifting apart is exactly
# what #157 criterion 7 forbade, and a silent fallback is how it would happen.
sys.path.insert(0, HERE)
try:
    import llm_tell_detector as tells
except Exception as exc:  # pragma: no cover - environment, not logic
    print(f"UNUSABLE: cannot import llm_tell_detector: {exc}", file=sys.stderr)
    raise SystemExit(2)

VARIANTS_DIR = os.path.join("app", "views", "design_variants")
CONTROLLER = os.path.join("app", "controllers", "design_variants_controller.rb")
ROUTES = os.path.join("config", "routes.rb")
MANIFEST = "variants.json"


# --------------------------------------------------------------------------------------
# Rules. Named so one can be argued with individually, each citing what it enforces --
# the mechanism borrowed from `llm_tell_detector.py`, and the reason a checker survives
# its first justified exception.
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    name: str
    doctrine: str
    why: str


RULES: tuple[Rule, ...] = (
    Rule("variant-set-undeclared", "#160 criterion 3",
         "a set directory with no readable variants.json — the switcher renders a declared set"),
    Rule("variant-set-too-small", "#160 rationale",
         "fewer than two variants is not a choice; a single output invites a yes/no"),
    Rule("variant-missing-rationale", "#160 criterion 4",
         "each variant carries a one-line rationale so the choice is informed"),
    Rule("variant-file-mismatch", "#160 criterion 5",
         "a declared file is absent, or a partial in the set is undeclared (discard would miss it)"),
    Rule("variant-declares-styling", "brand.md:149-151",
         "a variant brings its own CSS/tokens — it may arrange, never style"),
    Rule("variant-names-pack-primitive", "brand.md:78-82",
         "a variant names a pack-private primitive instead of a role token"),
    Rule("variant-set-not-distinct", "#160 'three is a decision'",
         "two variants share an identical composition signature"),
    Rule("variant-tell", "#157",
         "an LLM design tell in a variant file (the #157 detector, run per variant)"),
    Rule("variant-switcher-unguarded", "#160 omission",
         "the switcher route is reachable outside development"),
    Rule("variant-scaffolding-left-behind", "#160 criterion 5",
         "variant scaffolding survived the discard step"),
)

RULE_NAMES = frozenset(r.name for r in RULES)


@dataclass
class Finding:
    rule: str
    path: str
    message: str
    line: int = 0

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        doctrine = next((r.doctrine for r in RULES if r.name == self.rule), "?")
        return f"  {where}  [{self.rule}]\n      {self.message} ({doctrine})"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    sets: int = 0
    files: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, rule: str, path: str, message: str, line: int = 0) -> None:
        assert rule in RULE_NAMES, f"unregistered rule {rule!r}"
        self.findings.append(Finding(rule, path, message, line))


# --------------------------------------------------------------------------------------
# Composition signature — arrangement, stripped of copy.
# --------------------------------------------------------------------------------------

STRUCTURAL_TAGS = (
    "section", "header", "footer", "aside", "nav", "main", "article", "form", "table",
    "ul", "ol", "dl", "figure", "details", "dialog", "h1", "h2", "h3", "h4", "h5", "h6",
)
_TAG = re.compile(r"<\s*(" + "|".join(STRUCTURAL_TAGS) + r")\b", re.I)
# `render(Ui::Card...`, `render Ui::Card`, `render "shared/hero"`, `render partial: "hero"`.
# Paren-optional deliberately: the #142 blind spot in this repo's own render rules was a
# pattern that required one.
_RENDER = re.compile(
    r"\brender\s*\(?\s*(?:partial:\s*)?([A-Z][A-Za-z0-9_:]*|\"[^\"\n]+\"|'[^'\n]+')")


def composition_signature(text: str) -> tuple[str, ...]:
    """Ordered structural tags + render targets. Copy differences do not move it."""
    marks: list[tuple[int, str]] = []
    for found in _TAG.finditer(text):
        marks.append((found.start(), f"tag:{found.group(1).lower()}"))
    for found in _RENDER.finditer(text):
        marks.append((found.start(), f"render:{found.group(1).strip(chr(34) + chr(39))}"))
    marks.sort()
    return tuple(token for _, token in marks)


# --------------------------------------------------------------------------------------
# Styling a variant must not bring.
# --------------------------------------------------------------------------------------

STYLING = (
    (re.compile(r"<\s*style\b", re.I), "a <style> block"),
    (re.compile(r"@theme\b"), "an @theme layer"),
    (re.compile(r"@apply\b"), "an @apply"),
    (re.compile(r"@utility\b"), "an @utility recipe"),
    (re.compile(r"@layer\b"), "an @layer"),
    (re.compile(r":root\s*\{"), "a :root block"),
    (re.compile(r"--[A-Za-z0-9_-]+\s*:"), "a custom-property definition"),
    (re.compile(r"\bstyle\s*=\s*[\"']"), "an inline style attribute"),
)


def check_styling(text: str, path: str, report: Report) -> None:
    """A comment is prose that happens to sit in a template.

    `llm_tell_detector.COMMENT_LINE` is reused rather than re-derived: doctrine forbidding a
    pattern has to NAME it, so a variant whose ERB comment says "no `--color-*` here" must not
    be a finding. Two copies of that predicate would disagree the first time one is tuned.
    """
    for index, line in enumerate(text.splitlines(), 1):
        if tells.COMMENT_LINE.match(line):
            continue
        for pattern, what in STYLING:
            if pattern.search(line):
                report.add("variant-declares-styling", path,
                           f"{what} — variants differ in composition only, never in styling",
                           index)
                break


# --------------------------------------------------------------------------------------
# Pack primitives.
# --------------------------------------------------------------------------------------

_THEME_OPEN = re.compile(r"@theme\s*(inline\b)?[^{]*\{")
_PROPERTY = re.compile(r"--([A-Za-z0-9_-]+)\s*:")


def pack_primitives(theme_css: str) -> set[str]:
    """Custom properties declared in a pack's `@theme` block — its PRIVATE primitives.

    `@theme inline` is skipped: brand.md puts the ROLE layer there, and roles are the public
    API a variant is supposed to consume. Flagging them would invert the rule.
    """
    names: set[str] = set()
    for opening in _THEME_OPEN.finditer(theme_css):
        if opening.group(1):
            continue                       # `@theme inline` — the role layer
        depth, index = 1, opening.end()
        while index < len(theme_css) and depth:
            if theme_css[index] == "{":
                depth += 1
            elif theme_css[index] == "}":
                depth -= 1
            index += 1
        for found in _PROPERTY.finditer(theme_css[opening.end():index]):
            names.add(found.group(1))
    return names


def primitive_patterns(names: set[str]) -> list[tuple[re.Pattern, str]]:
    """Two forms per primitive: the `var(--name)` reference and the Tailwind utility.

    `--color-fm-navy` yields the utility suffix `fm-navy`, matched as a whole class token so
    `bg-fm-navy`, `hover:bg-fm-navy` and a bare `fm-navy` all hit while `fm-navy-ish` does not.
    Only `--color-*` grows a utility form here: colour is the whole primitive surface brand.md
    gives a pack ("Role **values** — the palette"), and guessing suffixes for every Tailwind
    namespace would invent contract the doctrine does not state.
    """
    out: list[tuple[re.Pattern, str]] = []
    for name in sorted(names):
        out.append((re.compile(r"var\(\s*--" + re.escape(name) + r"\s*\)"), f"--{name}"))
        if name.startswith("color-"):
            suffix = name[len("color-"):]
            if suffix:
                out.append((re.compile(r"(?<![\w-])(?:[a-z]+-)*" + re.escape(suffix) + r"(?![\w-])"),
                            suffix))
    return out


def resolve_pack(app_root: str, brand: str | None, override: str | None) -> tuple[str | None, str]:
    """(theme.css path, explanation). The pack is a PARAMETER of this check, not an assumption."""
    if override:
        theme = os.path.join(override, "theme.css")
        if os.path.isfile(theme):
            return theme, override
        return None, f"--pack {override} has no theme.css"
    if not brand:
        return None, "the manifest declares no `brand`"
    slug = brand.split(":", 1)[0]
    for base in (os.path.join(app_root, "brands", slug),
                 os.path.join(HERE, "..", "brands", slug)):
        theme = os.path.join(base, "theme.css")
        if os.path.isfile(theme):
            return theme, os.path.normpath(base)
    return None, f"no pack `{slug}` under {app_root}/brands or the plugin's bundled packs"


# --------------------------------------------------------------------------------------
# The switcher route.
# --------------------------------------------------------------------------------------

_DEV_GUARD = re.compile(r"Rails\.env\.(?:development|local)\?|unless\s+Rails\.env\.production\?")
_OPENS_IF = re.compile(r"^\s*(?:if|unless)\b")
_OPENS_DO = re.compile(r"\bdo\s*(?:\|[^|]*\|)?\s*(?:#.*)?$")
_CLOSES = re.compile(r"^\s*end\b")


def switcher_route_guarded(routes_rb: str) -> tuple[bool, bool, int]:
    """(route present, guarded, line).

    A small block tracker rather than a Ruby parser: push a frame for a line that OPENS a block
    (`if`/`unless` at line start, or a trailing `do`), pop on `end`, and remember which frames
    carry a development guard. Modifier `if` does not open a block, so a route carrying the
    guard on its own line is checked directly.

    Comment lines are skipped WHOLE, not just for the route match. `# do not remove` ends in a
    word the block-opener pattern reads as `do`, and the stray frame it pushes is popped by the
    next real `end` — which unbalances the stack and can report a genuinely guarded route as
    exposed. A checker that fires on a correct routes.rb is one nobody keeps.
    """
    stack: list[bool] = []
    for index, line in enumerate(routes_rb.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if _CLOSES.match(line) and stack:
            stack.pop()
            continue
        if "design_variants" in line:
            return True, bool(any(stack) or _DEV_GUARD.search(line)), index
        if _OPENS_IF.match(line) or _OPENS_DO.search(line):
            stack.append(bool(_DEV_GUARD.search(line)))
    return False, False, 0


# --------------------------------------------------------------------------------------
# The set check.
# --------------------------------------------------------------------------------------

def check_set(set_dir: str, app_root: str, pack_override: str | None, report: Report) -> None:
    rel = os.path.relpath(set_dir, app_root)
    manifest_path = os.path.join(set_dir, MANIFEST)
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        report.add("variant-set-undeclared", os.path.join(rel, MANIFEST),
                   f"unreadable manifest ({type(exc).__name__}); a set nobody declared cannot be "
                   f"rendered by the switcher or removed by the discard step")
        return
    report.sets += 1

    if not isinstance(manifest, dict) or not isinstance(manifest.get("variants"), list):
        report.add("variant-set-undeclared", os.path.join(rel, MANIFEST),
                   "manifest has no `variants` array")
        return
    for key in ("slug", "brief", "brand"):
        if not manifest.get(key):
            report.add("variant-set-undeclared", os.path.join(rel, MANIFEST),
                       f"manifest is missing `{key}`")

    entries = manifest["variants"]
    if len(entries) < 2:
        report.add("variant-set-too-small", os.path.join(rel, MANIFEST),
                   f"{len(entries)} variant(s) declared; a set of one is an approval, not a choice")

    theme, pack_note = resolve_pack(app_root, manifest.get("brand"), pack_override)
    patterns: list[tuple[re.Pattern, str]] = []
    if theme:
        try:
            with open(theme, encoding="utf-8") as handle:
                patterns = primitive_patterns(pack_primitives(handle.read()))
        except OSError as exc:
            theme = None
            pack_note = f"{pack_note}: {exc}"
    if not theme:
        # NOT a silent skip. A rule that did not run is not a pass, and this one is half of
        # #160's load-bearing constraint.
        report.add("variant-names-pack-primitive", os.path.join(rel, MANIFEST),
                   f"cannot resolve the brand pack ({pack_note}), so the primitive check could "
                   f"not run — a rule that did not run is not a pass")

    declared: set[str] = set()
    signatures: dict[tuple[str, ...], str] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report.add("variant-set-undeclared", os.path.join(rel, MANIFEST),
                       f"variant #{position + 1} is not an object")
            continue
        vid = str(entry.get("id") or position + 1)
        if not str(entry.get("rationale") or "").strip():
            report.add("variant-missing-rationale", os.path.join(rel, MANIFEST),
                       f"variant `{vid}` carries no rationale, so choosing it is aesthetic rather "
                       f"than informed")
        name = entry.get("file")
        if not name:
            report.add("variant-file-mismatch", os.path.join(rel, MANIFEST),
                       f"variant `{vid}` declares no `file`")
            continue
        declared.add(name)
        path = os.path.join(set_dir, name)
        relpath = os.path.join(rel, name)
        if not os.path.isfile(path):
            report.add("variant-file-mismatch", relpath,
                       f"variant `{vid}` declares a file that does not exist")
            continue
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        report.files += 1

        check_styling(text, relpath, report)

        for index, line in enumerate(text.splitlines(), 1):
            if tells.COMMENT_LINE.match(line):
                continue
            for pattern, label in patterns:
                if pattern.search(line):
                    report.add("variant-names-pack-primitive", relpath,
                               f"names the pack-private primitive `{label}`; components consume "
                               f"role tokens only, so a variant that names one is bound to a brand",
                               index)
                    break

        tell_report = tells.Report()
        tells.scan_text(text, relpath, tell_report)
        for finding in tell_report.findings:
            report.add("variant-tell", relpath,
                       f"[{finding.rule}] {finding.message}", finding.line)
        for finding in tell_report.bare_disables:
            report.add("variant-tell", relpath,
                       "a design-flow-disable with no reason", finding.line)

        signature = composition_signature(text)
        twin = signatures.get(signature)
        if twin is not None and signature:
            report.add("variant-set-not-distinct", relpath,
                       f"identical composition to `{twin}` — same structural tags and renders in "
                       f"the same order, so the set offers fewer real options than it claims")
        else:
            signatures[signature] = vid

    for entry in sorted(os.listdir(set_dir)):
        if entry == MANIFEST or entry in declared or not entry.endswith(".erb"):
            continue
        report.add("variant-file-mismatch", os.path.join(rel, entry),
                   "a partial in the set directory that no variant declares — the discard step "
                   "removes what the manifest lists, so this would survive it")


def check_app(app_root: str, pack_override: str | None) -> tuple[Report, str | None]:
    """(report, fatal reason)."""
    report = Report()
    root = os.path.join(app_root, VARIANTS_DIR)
    if not os.path.isdir(root):
        return report, (f"{VARIANTS_DIR} does not exist under {app_root} — nothing to check, and "
                        f"a clean verdict over zero input is not a pass")

    set_dirs = [os.path.join(root, e) for e in sorted(os.listdir(root))
                if os.path.isdir(os.path.join(root, e))]
    if not set_dirs:
        return report, (f"{VARIANTS_DIR} exists but holds no variant set — scaffolding with "
                        f"nothing in it is a discard that stopped half-way")

    for set_dir in set_dirs:
        check_set(set_dir, app_root, pack_override, report)

    routes = os.path.join(app_root, ROUTES)
    if os.path.isfile(routes):
        with open(routes, encoding="utf-8") as handle:
            present, guarded, line = switcher_route_guarded(handle.read())
        if present and not guarded:
            report.add("variant-switcher-unguarded", ROUTES,
                       "the switcher route is not inside a `Rails.env.development?` guard, so "
                       "every rejected variant is reachable in production", line)
    return report, None


def verify_discard(app_root: str) -> Report:
    """Criterion 5: picking one leaves no scaffolding behind."""
    report = Report()
    root = os.path.join(app_root, VARIANTS_DIR)
    if os.path.isdir(root):
        report.add("variant-scaffolding-left-behind", VARIANTS_DIR,
                   "the variant views survived the discard step")
    if os.path.isfile(os.path.join(app_root, CONTROLLER)):
        report.add("variant-scaffolding-left-behind", CONTROLLER,
                   "the switcher controller survived the discard step")
    routes = os.path.join(app_root, ROUTES)
    if os.path.isfile(routes):
        with open(routes, encoding="utf-8") as handle:
            present, _, line = switcher_route_guarded(handle.read())
        if present:
            report.add("variant-scaffolding-left-behind", ROUTES,
                       "the switcher route survived the discard step", line)
    return report


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def emit(report: Report, quiet: bool, header: str) -> int:
    for finding in report.findings:
        print(finding)
    if report.findings:
        print(f"\n{len(report.findings)} finding(s). Variants differ in composition only — same "
              f"tokens, same components, same API.", file=sys.stderr)
        return 1
    if not quiet:
        print(header)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assert a variant set is brand-conformant and differs in composition only.")
    parser.add_argument("app_root", nargs="?", default=".",
                        help="the Rails app root (default: the current directory)")
    parser.add_argument("--pack", metavar="DIR",
                        help="brand pack directory, overriding manifest-based resolution")
    parser.add_argument("--verify-discard", action="store_true",
                        help="assert no variant scaffolding remains (criterion 5)")
    parser.add_argument("--list-rules", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="findings only, no summary")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.list_rules:
        for rule in RULES:
            print(f"  {rule.name:32} {rule.doctrine:24} {rule.why}")
        return 0

    if not os.path.isdir(args.app_root):
        print(f"UNUSABLE: {args.app_root} is not a directory", file=sys.stderr)
        return 2

    if args.verify_discard:
        report = verify_discard(args.app_root)
        return emit(report, args.quiet, "variant scaffolding fully removed.")

    report, fatal = check_app(args.app_root, args.pack)
    if fatal:
        print(f"UNUSABLE: {fatal}", file=sys.stderr)
        return 2
    return emit(report, args.quiet,
                f"{report.sets} variant set(s), {report.files} variant(s): composition-only and "
                f"brand-conformant.")


# --------------------------------------------------------------------------------------
# Selftest. The SILENCE fixtures matter more than the firing ones: this check sits between an
# agent and a user's repo, and a rule that cries wolf is a rule someone deletes.
# --------------------------------------------------------------------------------------

CLEAN_VARIANT = """\
<section class="stack">
  <h1 class="text-primary">Ship faster</h1>
  <%= render Ui::Card.new(variant: :outline) do %>
    <p class="text-muted-foreground">Proof goes here.</p>
  <% end %>
</section>
"""

OTHER_VARIANT = """\
<header class="cluster">
  <h2 class="text-foreground">Ship faster</h2>
</header>
<%= render Ui::Table.new %>
"""

PACK_CSS = """\
@theme {
  --color-fm-navy: #0C1B33;
  --color-fm-cerulean: #0077CC;
}
:root { --primary: var(--color-fm-cerulean); --background: var(--color-fm-navy); }
@theme inline { --color-primary: var(--primary); }
"""


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _app(tmp: str, name: str, variants: dict[str, str], manifest: object,
         routes: str | None = None, pack: bool = True) -> str:
    root = os.path.join(tmp, name)
    set_dir = os.path.join(root, VARIANTS_DIR, "pricing")
    for filename, body in variants.items():
        _write(os.path.join(set_dir, filename), body)
    _write(os.path.join(set_dir, MANIFEST), json.dumps(manifest))
    if pack:
        _write(os.path.join(root, "brands", "fidara", "theme.css"), PACK_CSS)
    if routes is not None:
        _write(os.path.join(root, ROUTES), routes)
    return root


def _manifest(**over: object) -> dict:
    base: dict = {
        "slug": "pricing", "brief": "pricing page", "brand": "fidara:fmworkflows",
        "variants": [
            {"id": "a", "file": "_a.html.erb", "rationale": "denser, leads with the table"},
            {"id": "b", "file": "_b.html.erb", "rationale": "airier, leads with the claim"},
        ],
    }
    base.update(over)
    return base


GUARDED_ROUTES = """\
Rails.application.routes.draw do
  resources :invoices
  if Rails.env.development?
    get "design_variants/:slug", to: "design_variants#show", as: :design_variant
  end
end
"""

UNGUARDED_ROUTES = """\
Rails.application.routes.draw do
  resources :invoices
  get "design_variants/:slug", to: "design_variants#show", as: :design_variant
end
"""


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    passed = 0
    failures: list[str] = []

    def exit_code(argv: list[str]) -> int:
        """`main` through its real entry point, with its own output swallowed.

        The exit code is part of the contract (0 clean / 1 findings / 2 unusable), so it is
        asserted rather than inferred from the Report — but printing a fixture's findings into
        the selftest transcript makes a passing run look like a failing one.
        """
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(argv)

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal passed
        if condition:
            passed += 1
            print(f"  ok   {label}")
        else:
            failures.append(f"{label}: {detail}")
            print(f"  FAIL {label}: {detail}")

    def rules_of(report: Report) -> set[str]:
        return {f.rule for f in report.findings}

    with tempfile.TemporaryDirectory() as tmp:
        # ---- the whole point: a correct set is SILENT --------------------------------
        root = _app(tmp, "clean", {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(), GUARDED_ROUTES)
        report, fatal = check_app(root, None)
        check("a conformant variant set is silent", report.ok and not fatal,
              f"fatal={fatal} findings={[str(f) for f in report.findings]}")
        check("and it counted the set it examined", report.sets == 1 and report.files == 2,
              f"sets={report.sets} files={report.files}")
        check("a clean run exits 0", exit_code([root, "--quiet"]) == 0)

        # ---- variant-set-undeclared ---------------------------------------------------
        root = _app(tmp, "nomanifest", {"_a.html.erb": CLEAN_VARIANT}, _manifest())
        os.remove(os.path.join(root, VARIANTS_DIR, "pricing", MANIFEST))
        report, _ = check_app(root, None)
        check("an undeclared set fires", "variant-set-undeclared" in rules_of(report),
              f"{rules_of(report)}")

        root = _app(tmp, "nobrand", {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(brand=""))
        report, _ = check_app(root, None)
        check("a manifest with no brand fires", "variant-set-undeclared" in rules_of(report),
              f"{rules_of(report)}")

        # ---- variant-set-too-small ----------------------------------------------------
        root = _app(tmp, "solo", {"_a.html.erb": CLEAN_VARIANT},
                    _manifest(variants=[{"id": "a", "file": "_a.html.erb", "rationale": "the one"}]),
                    GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("a set of one fires", "variant-set-too-small" in rules_of(report),
              f"{rules_of(report)}")

        # ---- variant-missing-rationale ------------------------------------------------
        root = _app(tmp, "norationale",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(variants=[
                        {"id": "a", "file": "_a.html.erb", "rationale": "denser"},
                        {"id": "b", "file": "_b.html.erb", "rationale": "   "},
                    ]), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("a blank rationale fires", "variant-missing-rationale" in rules_of(report),
              f"{rules_of(report)}")

        # ---- variant-file-mismatch, both directions -----------------------------------
        root = _app(tmp, "ghostfile", {"_a.html.erb": CLEAN_VARIANT}, _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("a declared file that is absent fires", "variant-file-mismatch" in rules_of(report),
              f"{rules_of(report)}")

        root = _app(tmp, "strayfile",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT,
                     "_leftover.html.erb": CLEAN_VARIANT},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("an undeclared partial in the set fires",
              any(f.rule == "variant-file-mismatch" and "leftover" in f.path
                  for f in report.findings), f"{[str(f) for f in report.findings]}")

        # ---- variant-declares-styling: fires, and stays silent on a comment -----------
        root = _app(tmp, "styling",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": "<style>.x{color:red}</style>\n<header></header>\n"},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("a variant bringing its own CSS fires",
              "variant-declares-styling" in rules_of(report), f"{rules_of(report)}")

        root = _app(tmp, "styledattr",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": '<header style="gap: 12px"></header>\n'},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("an inline style attribute fires",
              "variant-declares-styling" in rules_of(report), f"{rules_of(report)}")

        # THE NEAR-MISS THAT WOULD GET THIS RULE DELETED. An ERB comment naming the forbidden
        # pattern is prose; doctrine that forbids something has to name it.
        root = _app(tmp, "styledcomment",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": "<%# never declare --color-anything: here %>\n<header></header>\n"},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("a comment naming a custom property is NOT a finding",
              "variant-declares-styling" not in rules_of(report),
              f"{[str(f) for f in report.findings]}")

        # ---- variant-names-pack-primitive --------------------------------------------
        root = _app(tmp, "primitive",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": '<header class="bg-fm-navy"></header>\n'},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("naming a pack primitive fires",
              "variant-names-pack-primitive" in rules_of(report), f"{rules_of(report)}")

        # SILENCE: role tokens are the public API and must never be flagged. `bg-primary` is
        # what every conformant variant uses, so a false positive here breaks the whole feature.
        root = _app(tmp, "roles",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": '<header class="bg-primary text-primary-foreground border-border"></header>\n'},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("role tokens are NOT flagged as primitives",
              "variant-names-pack-primitive" not in rules_of(report),
              f"{[str(f) for f in report.findings]}")

        # An unresolvable pack is a FINDING, never a silent skip.
        root = _app(tmp, "nopack",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(brand="acme"), GUARDED_ROUTES, pack=False)
        report, _ = check_app(root, None)
        check("an unresolvable pack is a finding, not a skip",
              any(f.rule == "variant-names-pack-primitive" and "not run" in f.message
                  for f in report.findings), f"{[str(f) for f in report.findings]}")

        # ---- variant-set-not-distinct -------------------------------------------------
        root = _app(tmp, "twins",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": CLEAN_VARIANT.replace("Ship faster", "Move faster")},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("two variants differing only in copy fire",
              "variant-set-not-distinct" in rules_of(report), f"{rules_of(report)}")

        # SILENCE: genuinely different arrangements of the same brief.
        root = _app(tmp, "distinct",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("different arrangements are NOT flagged as twins",
              "variant-set-not-distinct" not in rules_of(report),
              f"{[str(f) for f in report.findings]}")

        # ---- variant-tell: the #157 detector, run rather than reimplemented -----------
        root = _app(tmp, "tell",
                    {"_a.html.erb": CLEAN_VARIANT,
                     "_b.html.erb": '<header class="bg-gradient-to-r"></header>\n'},
                    _manifest(), GUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("an LLM tell inside a variant fires",
              any(f.rule == "variant-tell" and "gradient" in f.message for f in report.findings),
              f"{[str(f) for f in report.findings]}")

        # ---- variant-switcher-unguarded -----------------------------------------------
        root = _app(tmp, "unguarded",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(), UNGUARDED_ROUTES)
        report, _ = check_app(root, None)
        check("an unguarded switcher route fires",
              "variant-switcher-unguarded" in rules_of(report), f"{rules_of(report)}")

        check("a guarded switcher route is silent",
              switcher_route_guarded(GUARDED_ROUTES) == (True, True, 4),
              f"{switcher_route_guarded(GUARDED_ROUTES)}")
        check("a modifier-if guard on the route line counts",
              switcher_route_guarded(
                  'Rails.application.routes.draw do\n  get "design_variants/:slug", to: "x#y" '
                  'if Rails.env.development?\nend\n')[1])
        check("routes with no switcher report none",
              switcher_route_guarded("Rails.application.routes.draw do\n  root \"a#b\"\nend\n")
              == (False, False, 0))
        # A commented-out route is not a route, and a comment ending in the word `do` must not
        # push a phantom frame that the next real `end` pops -- an unbalanced stack reports a
        # GUARDED route as exposed, which is a finding on a correct routes.rb.
        check("a comment does not unbalance the block tracker",
              switcher_route_guarded(
                  "Rails.application.routes.draw do\n  # design_variants used to be here\n"
                  "  if Rails.env.development?\n    # keep this, do\n"
                  "    get \"design_variants/:slug\", to: \"x#y\"\n  end\nend\n")
              == (True, True, 5),
              f"{switcher_route_guarded(chr(10))}")
        # A guard that CLOSED before the route must not count -- the failure mode of a naive
        # backwards search, and the reason this tracks a stack instead.
        check("a closed development block does not launder a later route",
              switcher_route_guarded(
                  "Rails.application.routes.draw do\n  if Rails.env.development?\n"
                  "    get \"letter_opener\"\n  end\n  get \"design_variants/:slug\"\nend\n")
              == (True, False, 5),
              f"{switcher_route_guarded(chr(10))}")

        # ---- zero input is exit 2, never a clean pass ---------------------------------
        empty = os.path.join(tmp, "emptyapp")
        os.makedirs(empty, exist_ok=True)
        _, fatal = check_app(empty, None)
        check("an app with no variant sets is fatal, not clean", bool(fatal), f"{fatal}")
        check("and exits 2", exit_code([empty, "--quiet"]) == 2)

        scaffold_only = os.path.join(tmp, "scaffoldonly")
        os.makedirs(os.path.join(scaffold_only, VARIANTS_DIR), exist_ok=True)
        _, fatal = check_app(scaffold_only, None)
        check("an empty variants directory is fatal too", bool(fatal), f"{fatal}")

        # ---- --verify-discard ----------------------------------------------------------
        root = _app(tmp, "notdiscarded",
                    {"_a.html.erb": CLEAN_VARIANT, "_b.html.erb": OTHER_VARIANT},
                    _manifest(), GUARDED_ROUTES)
        _write(os.path.join(root, CONTROLLER), "class DesignVariantsController; end\n")
        report = verify_discard(root)
        check("an un-run discard reports all three artefacts",
              len(report.findings) == 3
              and {f.rule for f in report.findings} == {"variant-scaffolding-left-behind"},
              f"{[str(f) for f in report.findings]}")

        done = os.path.join(tmp, "discarded")
        _write(os.path.join(done, ROUTES), "Rails.application.routes.draw do\n  root \"a#b\"\nend\n")
        check("a completed discard is silent", verify_discard(done).ok,
              f"{[str(f) for f in verify_discard(done).findings]}")
        check("a completed discard exits 0", exit_code([done, "--verify-discard", "--quiet"]) == 0)

        # ---- the units, fixtured directly ----------------------------------------------
        check("pack primitives come from @theme, not @theme inline",
              pack_primitives(PACK_CSS) == {"color-fm-navy", "color-fm-cerulean"},
              f"{pack_primitives(PACK_CSS)}")
        check("a composition signature ignores copy",
              composition_signature(CLEAN_VARIANT)
              == composition_signature(CLEAN_VARIANT.replace("Ship faster", "Move faster")))
        check("a composition signature notices a different arrangement",
              composition_signature(CLEAN_VARIANT) != composition_signature(OTHER_VARIANT))
        check("a paren-less render is part of the signature",
              "render:Ui::Card" in composition_signature("<% render Ui::Card %>"))
        check("every rule in RULES is reachable by name",
              len(RULE_NAMES) == len(RULES) == 10, f"{len(RULES)} rules")
        check("--list-rules exits 0", exit_code(["--list-rules"]) == 0)

    if failures:
        print(f"\nSELFTEST FAILED — {len(failures)} of {passed + len(failures)}:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"variant_conformance selftest: {passed} checks passed across {len(RULES)} rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
