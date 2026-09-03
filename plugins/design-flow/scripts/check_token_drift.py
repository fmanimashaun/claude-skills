#!/usr/bin/env python3
"""Compare a project's managed token block against the plugin's, and say which side owns each gap.

Run:  python3 check_token_drift.py                       # app/assets/tailwind/application.css
      python3 check_token_drift.py --css path/to.css
      python3 check_token_drift.py --selftest

WHY THIS EXISTS (#750). A live project's `@theme` had diverged from `foundations-tokens.md` in ways
nobody had noticed: a warm ground the plugin could not express, six re-tuned slate steps, and four
roles the plugin never declared. It accumulated **silently** — the scaffold runs once, the plugin
ships new tokens, and nothing ever compares them again. By the time it was found it took a hand-written
repo-vs-plugin diff to see it.

THE LINE BETWEEN OURS AND THEIRS IS THE WHOLE DESIGN. A brand pack is *supposed* to add tokens; a
project is *supposed* to extend. So a check that flagged every difference would fire on correct work
and be switched off within a week -- the failure mode this repo files most. The line is the marker
`/* design-flow:tokens:begin */ … :end`, which `setup` writes and owns:

    inside  -> the plugin's. It must match, and a difference is drift.
    outside -> the project's. Never compared, never reported.

That marker did not exist until #754; the contract said "between markers" and named none. This check
is the reason it now does.

FOUR OUTCOMES, and only one of them is "you have a problem":

  * **missing**   -- the plugin declares a token the managed block does not. The project is behind;
                     re-run setup. This is how a new role never reaches an adopter.
  * **changed**   -- both declare it, values differ. Either the project re-tuned inside the managed
                     block (it belongs outside) or it predates a plugin change.
  * **extra**     -- the managed block declares something the plugin does not. Usually a local
                     extension written on the wrong side of the marker.
  * **unmanaged** -- no marker at all. **Reported as its own state, never as a pass.** Most existing
                     projects are here, and calling that clean would be the exact lie this exists to
                     prevent.

Exit codes:  0 = managed and in step · 1 = drift, or unmanaged · 2 = no CSS to read

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doctrine_path                    # noqa: E402 -- same plugin, one resolver
import brand_pack_lint as bpl           # noqa: E402 -- same plugin, one theme-aware parser

# THE SHARED RESOLVER, not parent-counting (#777). `parents[N]` is calibrated for the marketplace
# CLONE; from an install the cache interposes `<plugin>/<version>/`, and the two shapes differ in
# DEPTH rather than offset -- so no hop count reconciles them and this check simply never ran for
# anyone who installed. That population is the least likely to notice, and the refusal below said
# "the plugin side is missing", which reads as a broken install rather than a resolver bug.
# Third recurrence of #617's class, second after the resolver existed.
# The pack baselines. `parents[1]` is safe where #617's parent-counting was not: this stays INSIDE
# design-flow, whose layout is fixed, rather than reaching across the clone/install boundary.
BRANDS = Path(__file__).resolve().parents[1] / "brands"
BRAND_RB = Path("config/initializers/brand.rb")
# The pack SLUG, which is not `default_variant`. See `resolve_baseline`.
PACK_DECL = re.compile(r"""\bconfig\.x\.brand\.pack\s*=\s*(?P<q>['"])(?P<slug>[a-z0-9_-]+)(?P=q)""")

_DOCTRINE = doctrine_path.find(Path(__file__).resolve())
DOC = ((_DOCTRINE / "references" / "foundations-tokens.md") if _DOCTRINE
       else Path("foundations-tokens.md"))          # unresolvable: main() refuses, naming every root
DEFAULT_CSS = Path("app/assets/tailwind/application.css")

# The one place the marker is spelled. `setup.md` writes it; this reads it. Two spellings would
# drift, and the thing being checked here is drift.
BEGIN = "design-flow:tokens:begin"
END = "design-flow:tokens:end"

DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;\n]+)")


def managed_block(css: str) -> str | None:
    """CSS between the marker COMMENTS, or None when the file is unmanaged.

    It used to slice between the marker STRINGS, so the returned text opened with the rest of the
    begin comment (` */`) and closed with the start of the end comment (`/* `). That was harmless
    while the only consumer was a declaration regex, and it broke the moment a theme-aware parser
    arrived (#814): `selector_block` reads everything before a `{` as the selector prelude, so a
    leading `*/` made `:root {` parse as the selector `*/\n:root` and match nothing. Every block in
    the managed region came back empty and every pack token was reported `missing`.

    So the slice runs to the end of the opening comment and from the start of the closing one.
    """
    i = css.find(BEGIN)
    if i == -1:
        return None
    j = css.find(END, i + 1)
    if j == -1:
        return None
    start = css.find("*/", i + len(BEGIN))
    start = start + 2 if start != -1 and start < j else i + len(BEGIN)
    end = css.rfind("/*", start, j)
    return css[start:end if end != -1 else j]


def plugin_tokens(doc_text: str) -> dict[str, str]:
    """Every token the doctrine declares, normalised for comparison."""
    return {m.group(1): " ".join(m.group(2).split()) for m in DECL.finditer(doc_text)}


def project_pack(root: Path) -> str | None:
    """The pack slug the project records, or None.

    NOT `default_variant` (#788). `config/initializers/brand.rb` has always exposed
    `default_variant` and `variants` -- `Ui::Logo` reads only those -- and for `reliance` the
    default variant happens to EQUAL the slug, which makes the wrong inference look right. For
    `fidara` the default variant is `fmworkflows`, and `brands/fmworkflows/` does not exist. So the
    slug is read from an explicit `config.x.brand.pack`, which `/design-flow:setup` now writes.
    """
    f = root / BRAND_RB
    if not f.is_file():
        return None
    m = PACK_DECL.search(f.read_text(encoding="utf-8"))
    return m.group("slug") if m else None


def resolve_baseline(brand: str | None, root: Path) -> tuple[Path | None, str]:
    """`(baseline, slug)` for the pack this project uses, or `(None, reason)`.

    THE BASELINE IS THE PACK, NOT THE DOCTRINE (#788). The managed block is written by
    `/design-flow:setup <pack>` from `brands/<pack>/theme.css`, so that file is what it must match.
    Comparing every project against `foundations-tokens.md` -- the fidara-flavoured doctrine --
    made a `reliance` project report **119 findings, all false**: every `--color-fm-*` "missing"
    (*re-run setup*), every `--color-rh-*` "extra", and every role the pack deliberately re-pointed
    "changed" with the remediation *"take the plugin's value"*. That last one would have reverted
    `--primary` from `#1171B0` (4.97:1) to `#137CC1` (4.26:1) -- reintroducing the WCAG 1.4.3
    failure the pack exists to avoid (#771).

    REFUSES RATHER THAN DEFAULTING, which is the actual fix. Falling back to fidara is what
    produced confident, wrong remediation; a check that cannot tell which pack a project uses has
    not measured anything, and saying so is the only honest answer.
    """
    slug = brand or project_pack(root)
    if not slug:
        return None, (
            f"cannot determine this project's brand pack, so there is nothing to compare against.\n"
            f"  Pass --brand <slug>, or record it in {BRAND_RB} as "
            f"`config.x.brand.pack = \"<slug>\"`.\n"
            f"  NOT guessed from `default_variant`: for the `fidara` pack that is `fmworkflows`, "
            f"which is a variant, not a pack.\n"
            f"  Comparing against a pack this project does not use would produce confident, wrong "
            f"remediation — refusing instead.")
    doc = BRANDS / slug / "theme.css"
    if not doc.is_file():
        available = sorted(d.name for d in BRANDS.glob("*") if (d / "theme.css").is_file())
        return None, (f"no brand pack {slug!r} — looked for {doc}.\n"
                      f"  This plugin ships: {', '.join(available) or 'none'}")
    return doc, slug


def theme_blocks(css: str) -> dict[str, dict[str, str]]:
    """Declarations per theme, `{"@theme": {...}, ":root": {...}, ".dark": {...}}`.

    THE CHECK USED TO COLLAPSE THEMES (#814). `plugin_tokens` is a dict comprehension over every
    declaration in the file, so a role re-pointed in `.dark` overwrote its `:root` value and the
    comparison was between whichever happened to come last on each side. `--primary-hover` is
    brand-700 in light (darker on hover, because primary is brand-600) and brand-50 in dark (lighter,
    because primary is brand-100) -- both correct, and reported `changed`. Every token a dark theme
    exists to re-point produced a false finding, in every project with a dark theme.

    `@theme` needs its own reader: `selector_block` deliberately skips at-rules (#764), so
    primitives come from `theme_primitives` instead.
    """
    src = bpl.strip_css_comments(css)
    out: dict[str, dict[str, str]] = {}
    for sel in (":root", ".dark"):
        # EVERY block for the selector, merged in source order -- presence is the union, and a later
        # declaration wins the value, which is the cascade. Taking only the last (what
        # `selector_block` does, correctly, for a value) made a project with a second `:root` report
        # every token in the first as missing.
        merged: dict[str, str] = {}
        for body in bpl.selector_blocks(src, sel):
            merged.update({m.group(1): " ".join(m.group(2).split()) for m in DECL.finditer(body)})
        out[sel] = merged
    # VALUES, not just names. `theme_primitives` answers "is it declared"; the comparison needs
    # "is it the same", so a primitive re-tuned inside the managed block is `changed` rather than
    # invisible. Storing `""` also forced a `sel != "@theme"` special case in the comparison, which
    # is gone with it.
    merged_theme: dict[str, str] = {}
    for body in bpl.theme_bodies(src):
        merged_theme.update({m.group(1): " ".join(m.group(2).split())
                             for m in DECL.finditer(body)})
    out["@theme"] = merged_theme
    return out


def pack_all(blocks: dict[str, dict[str, str]]) -> set[str]:
    """Every name the pack declares, across all its theme blocks."""
    return {n for blk in blocks.values() for n in blk}


BRIDGE = re.compile(r"^var\(\s*(--[a-z0-9-]+)\s*\)$")


def pack_knobs(theme_css: Path | None) -> dict:
    """The pack's knobs from the `brand.json` beside its `theme.css`; `{}` when absent."""
    if theme_css is None:
        return {}
    bj = theme_css.parent / "brand.json"
    try:
        return dict(json.loads(bj.read_text(encoding="utf-8")).get("knobs") or {}) if bj.is_file() else {}
    except (OSError, ValueError):
        return {}


def classify(name: str, pack_names: set[str], doctrine_names: set[str], value: str = "",
             knobs: dict | None = None) -> str:
    """Who OWNS this token: `pack`, `system`, or `project` (#814, #899).

    #788 pointed the comparison at the right target and left the KIND wrong: the reference is a
    palette and the subject is a stylesheet. `brands/reliance/theme.css` says so in its own first
    lines -- *"A pack is a theme, not a fork: primitives, role mapping, dark re-points. Nothing
    else. No @utility, no @apply, no component CSS -- those are system-level and shared by every
    pack."* Meanwhile `setup.md` scaffolds the Utopia scale, `--measure/--radius/--shadow-*/`
    `--duration`, the font roles and the `@theme inline` bridges INTO the managed block. So the
    check reported design-flow's own scaffolding as an unexpected local extension -- 68 of 72
    findings -- and its advice, *"a local extension belongs OUTSIDE the markers"*, would have moved
    the plugin's own scale tokens out of the plugin's own managed block, where the next `setup`
    re-emits them inside and the project ends with two definitions of every scale token.

    SYSTEM = DOCTRINE MINUS PACK, deliberately, rather than a hardcoded list of scale names. The
    doctrine's non-colour names include the ROLES, and roles are pack-owned -- classifying them
    system would stop comparing the very thing this check exists for. Doctrine-minus-pack is exactly
    the set `setup` scaffolds and no pack declares, and it self-maintains: add a scale token to the
    doctrine and it is system-owned; add it to a pack and it becomes pack-owned.

    A BRIDGE IS CLASSIFIED BY THE OWNER OF ITS ROLE (#899). `--color-primary: var(--primary)` is named
    after the role it exposes, and the first version of this docstring said "every role is in the
    doctrine, so the clause above already classifies it" -- true of the ROLE, but the clause tests the
    BRIDGE's name. The doctrine bridges only its original 22 roles; `setup` emits a bridge for EVERY
    role, and the pack (`reliance`) declares six the doctrine never bridges (`--overlay`,
    `--primary-hover`, `--primary-ink`, `--signal`, `--signal-foreground`, `--success-ink`). Those six
    bridges were `project` -> `extra`: eight false findings on a conformant project. So: a
    `--color-<r>` whose value is `var(--<r>)` is owned by whoever owns `--<r>` -- pack, system, or
    nobody, in which case it is still `extra`, the one case the old paragraph rightly wanted kept.

    THE RADIUS RAMP (#899). The `radius` knob expands into five steps inside the managed block; the
    doctrine declares three. With the knob set, the steps in `bpl.RADIUS_RAMP_STEPS` are system-owned
    -- one definition, beside the knob's enum. Without the knob, `--radius-md` in the block is what it
    looks like: a local extension.
    """
    if name in pack_names:
        return "pack"
    if name in doctrine_names:
        return "system"
    m = BRIDGE.match(value or "")
    if name.startswith("--color-") and m and name == "--color-" + m.group(1)[2:]:
        role = m.group(1)
        if role in pack_names:
            return "pack"
        if role in doctrine_names:
            return "system"
        return "project"
    if (knobs or {}).get("radius") and name in bpl.RADIUS_RAMP_STEPS:
        return "system"
    return "project"


def compare(css: str, doc_text: str, knobs: dict | None = None) -> tuple[str, list[str]]:
    """`(state, findings)`. State is `unmanaged`, `drift` or `clean`."""
    block = managed_block(css)
    if block is None:
        return "unmanaged", [
            f"no `{BEGIN}` marker — this file was scaffolded before the marker existed, or by hand. "
            f"Nothing can tell the plugin's tokens from yours, so nothing is checked. This is NOT a "
            f"pass: re-run /design-flow:setup to establish the managed block."]
    pack = theme_blocks(doc_text)
    project = theme_blocks(block)
    pack_names = {n for blk in pack.values() for n in blk}
    doctrine_names = plugin_tokens(DOC.read_text(encoding="utf-8")) if DOC.is_file() else {}
    out: list[str] = []

    # PER THEME BLOCK. A role re-pointed in `.dark` is compared against the pack's `.dark`, never
    # against its `:root` -- collapsing them made every dark re-point a false `changed` (#814).
    for sel in ("@theme", ":root", ".dark"):
        ours, theirs = pack.get(sel, {}), project.get(sel, {})
        for tok in sorted(set(ours) - set(theirs)):
            out.append(f"missing: the pack declares {tok} in `{sel}` and the managed block does "
                       f"not — this project is behind; re-run /design-flow:setup")
        for tok in sorted(set(ours) & set(theirs)):
            if ours[tok] and ours[tok] != theirs[tok]:
                out.append(f"changed: {tok} is {theirs[tok]!r} in `{sel}` here and {ours[tok]!r} in "
                           f"the pack — re-tune it outside the markers, or take the pack's value")

    # EXTRA is only ever the PROJECT's. A token the pack does not declare may still be the system's
    # -- `setup` scaffolds the Utopia scale, the radius/shadow/duration/measure set, the font roles
    # and the `@theme inline` bridges into this very block -- and telling someone to move those
    # outside the markers is advice that breaks their app on the next re-run (#814).
    seen: set[str] = set()
    for sel in (":root", ".dark", "@theme"):
        for tok in sorted(project.get(sel, {})):
            if tok in seen:
                continue
            seen.add(tok)
            if classify(tok, pack_names, set(doctrine_names), project.get(sel, {}).get(tok, ""), knobs) == "project":
                out.append(
                    f"extra: {tok} is inside the managed block, and neither the pack nor the design "
                    f"system declares it — a local extension belongs OUTSIDE the markers, where a "
                    f"re-run will not eat it")
    return ("drift" if out else "clean"), out


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # REAL CSS SHAPE, not bare declarations. The comparison is per theme block now (#814), so a
    # fixture without `:root { }` tests a parse that never happens -- and the old fixtures were less
    # structured than every real input, which is how a theme-blind comparison went unnoticed.
    def blk(sel: str, body: str) -> str:
        return f"{sel} {{\n{body}}}\n"

    doc = blk(":root", "  --background: #FFF;\n  --primary: #0077CC;\n")
    wrap = lambda body: f"/* {BEGIN} */\n{body}/* {END} */\n"          # noqa: E731

    state, f = compare(wrap(blk(":root", "  --background: #FFF;\n  --primary: #0077CC;\n")), doc)
    check("an in-step managed block is clean", state == "clean" and f == [])

    state, f = compare(wrap(blk(":root", "  --background: #FFF;\n")), doc)
    check("a token the plugin adds is reported missing",
          state == "drift" and any(x.startswith("missing: ") and "--primary" in x for x in f))

    state, f = compare(wrap(blk(":root", "  --background: #FFF;\n  --primary: #0069B4;\n")), doc)
    check("a re-tuned value is reported changed",
          any(x.startswith("changed: ") and "--primary" in x for x in f))

    state, f = compare(wrap(blk(":root", "  --background: #FFF;\n  --primary: #0077CC;\n  --mine: #123;\n")), doc)
    check("a local token INSIDE the markers is reported extra",
          any(x.startswith("extra: ") and "--mine" in x for x in f))

    # THE LINE THAT MAKES THIS SAFE. A project extending OUTSIDE the markers is doing the right
    # thing and must be silent -- a check that flagged it would be switched off within a week.
    outside = (wrap(blk(":root", "  --background: #FFF;\n  --primary: #0077CC;\n"))
               + blk(":root", "  --mine: #123;\n  --yours: #456;\n"))
    state, f = compare(outside, doc)
    check("a local token OUTSIDE the markers is silent", state == "clean" and f == [])

    # UNMANAGED IS NOT CLEAN. Most existing projects are here.
    state, f = compare("--background: #FFF;\n--primary: #0077CC;\n", doc)
    check("no marker is 'unmanaged', not 'clean'", state == "unmanaged")
    check("...and says so in as many words", any("NOT a pass" in x for x in f))
    # An opening marker with no closing one is also unmanaged, not a block running to EOF.
    state, _ = compare(f"/* {BEGIN} */\n--background: #FFF;\n", doc)
    check("an unterminated marker is unmanaged", state == "unmanaged")

    # Whitespace is normalised, so reformatting is not drift.
    state, f = compare(wrap(blk(":root", "  --background:   #FFF ;\n  --primary:\t#0077CC;\n")), doc)
    check("reformatting is not drift", state == "clean")

    # ---- #788. WHICH pack is the baseline ------------------------------------------------------
    import tempfile as _tf

    def project(pack_rb: str | None) -> Path:
        root = Path(_tf.mkdtemp(prefix="drift-"))
        if pack_rb is not None:
            (root / "config" / "initializers").mkdir(parents=True)
            (root / "config" / "initializers" / "brand.rb").write_text(pack_rb, encoding="utf-8")
        return root

    # THE EXPLICIT FLAG.
    doc, slug = resolve_baseline("reliance", project(None))
    check("--brand selects that pack's theme.css",
          doc is not None and slug == "reliance" and doc.name == "theme.css")
    check("...and it is the pack's file, not the doctrine",
          doc is not None and doc.parent.name == "reliance")

    # THE RECORDED SLUG.
    doc, slug = resolve_baseline(None, project(
        'Rails.application.configure do\n  config.x.brand.pack = "reliance"\nend\n'))
    check("config.x.brand.pack is read from brand.rb", doc is not None and slug == "reliance")

    # THE CLAUSE THAT MAKES THE OBVIOUS FIX WRONG. `brand.rb` has always carried `default_variant`,
    # and for `reliance` that EQUALS the slug -- so inferring from it looks right until `fidara`,
    # whose default variant is `fmworkflows`, a variant with no pack directory. Resolution must not
    # touch it.
    doc, why = resolve_baseline(None, project(
        'Rails.application.configure do\n'
        '  config.x.brand.default_variant = "fmworkflows"\n'
        '  config.x.brand.variants = {}\n'
        'end\n'))
    # Assert WHICH refusal, not merely that it refused. Reading `default_variant` and then failing
    # to find `brands/fmworkflows/` also returns None -- so `doc is None` cannot tell the two apart,
    # and the mutation was caught only incidentally by an unrelated fixture. The correct code never
    # reads the file's default_variant at all, so its reason is "cannot determine", never
    # "no brand pack 'fmworkflows'".
    check("default_variant is NOT taken as the pack slug", doc is None)
    check("...refusing because nothing RECORDS a pack, not because fmworkflows is missing",
          doc is None and "cannot determine" in why and "no brand pack" not in why)

    # REFUSING IS THE FIX. Defaulting to fidara is what produced 100+ false findings and a
    # remediation that would revert a measured WCAG palette.
    doc, why = resolve_baseline(None, project(None))
    check("no recorded pack refuses rather than defaulting", doc is None)
    check("...and never names fidara as the fallback", "fidara" not in why.split("`fidara`")[0])
    check("...and tells the operator both ways to fix it",
          "--brand" in why and "config.x.brand.pack" in why)

    # AN UNKNOWN PACK names what actually ships, rather than a bare miss.
    doc, why = resolve_baseline("nonesuch", project(None))
    check("an unknown pack is refused", doc is None)
    check("...naming the packs that ship", "fidara" in why and "reliance" in why)

    # END TO END against the REAL reliance pack: in step is clean, and real drift is still caught.
    rel = BRANDS / "reliance" / "theme.css"
    if rel.is_file():
        # Rebuild the pack's own theme SHAPE, not a flattened list: the comparison is per block
        # now (#814), and a flat fixture would pass while every real project failed.
        # The honest "in step" case is a managed block carrying the pack's OWN content -- all three
        # blocks, `@theme` included. Rebuilding only `:root`/`.dark` left the 40 primitives
        # correctly reported missing, which was the check working and the fixture being partial.
        rel_src = rel.read_text(encoding="utf-8")
        packed = theme_blocks(rel_src)
        body = bpl.strip_css_comments(rel_src)
        toks = packed[":root"]
        state, f = compare(wrap(body), rel.read_text(encoding="utf-8"))
        check("a reliance block matching its own pack is clean", state == "clean" and f == [])
        # ...and the same block against the DOCTRINE is the reported defect, so the fixture above
        # cannot be passing because the comparison stopped working.
        if DOC.is_file():
            state, f = compare(wrap(body), DOC.read_text(encoding="utf-8"))
            check("...while the fidara doctrine would report it as drift", state == "drift")
            check("...in the volume the report described", len(f) > 50)
        # ...and real drift against the RIGHT pack is still caught, so "clean" above is not the
        # comparison having quietly stopped. Mutate whichever token comes first rather than naming
        # one: `plugin_tokens` is a dict comprehension, so a role re-pointed in `.dark` holds its
        # DARK value here, and naming `--background` picked a string that was no longer present.
        # ---- THE SCAFFOLD SHAPE (#814) --------------------------------------------------------
        # What `/design-flow:setup` actually writes: the pack's content PLUS the system scale and
        # the `@theme inline` bridges. This reported 72 findings, 70 of them false, on an untouched
        # scaffold -- design-flow's own output called an unexpected local extension.
        doctrine = plugin_tokens(DOC.read_text(encoding="utf-8")) if DOC.is_file() else {}
        if doctrine:
            system = sorted(n for n in set(doctrine) - set(pack_all(packed))
                            if not n.startswith("--color-"))
            scale = "".join(f"  {n}: 1rem;\n" for n in system)
            # EVERY role gets a bridge (that is what `setup` writes), including the six the pack declares
            # and the doctrine never bridges (#899); and the knob-expanded five-step radius ramp.
            roles = sorted(n[2:] for n in packed[":root"] if not n.startswith("--color-"))
            bridges = "".join(f"  --color-{r}: var(--{r});\n" for r in roles)
            ramp = "".join(f"  {n}: 0.5rem;\n" for n in bpl.RADIUS_RAMP_STEPS)
            knobs = pack_knobs(rel)
            scaffold = (body + f"@theme inline {{\n{bridges}}}\n" + blk(":root", scale + ramp))
            state, f = compare(wrap(scaffold), rel_src, knobs)
            check("a scaffold-shaped managed block -- every role bridged, the knob's radius ramp -- is CLEAN", state == "clean" and not f)
            check("...and the pack really does declare roles the doctrine never bridges (or the case above proves nothing)",
                  knobs.get("radius") is not None and any(f"--color-{r}" not in doctrine for r in roles))
            # the one bridge that IS a local extension: to a role nobody declares
            state, f = compare(wrap(scaffold + blk("@theme inline", "  --color-nobody: var(--nobody);\n")), rel_src, knobs)
            check("a bridge to a role neither pack nor doctrine declares is still `extra`",
                  len(f) == 1 and f[0].startswith("extra:") and "--color-nobody" in f[0])
            # the ramp WITHOUT the knob is what it looks like: a local extension
            state, f = compare(wrap(scaffold), rel_src, {})
            check("without the radius knob, --radius-md and --radius-xl are `extra`",
                  sorted(x.split()[1] for x in f if x.startswith("extra:")) == ["--radius-md", "--radius-xl"])

            # ...and it still catches every kind of REAL drift, or the line above is a gate that
            # cannot fail. One finding each, so a case cannot pass on someone else's finding.
            re_root = scaffold.replace("--primary: var(--color-rh-brand-600);", "--primary: #BADA55;", 1)
            state, f = compare(wrap(re_root), rel_src, knobs)
            check("a :root role re-tuned is still `changed`",
                  len(f) == 1 and f[0].startswith("changed:") and "`:root`" in f[0])

            # THEME-AWARE: the dark value is compared against the pack's DARK value. Collapsing the
            # blocks made every dark re-point a false `changed` -- in every project with a dark theme.
            re_dark = scaffold.replace("--primary: var(--color-rh-brand-100);", "--primary: #BADA55;", 1)
            state, f = compare(wrap(re_dark), rel_src, knobs)
            check("a .dark role re-tuned is `changed` against the pack's DARK value",
                  len(f) == 1 and f[0].startswith("changed:") and "`.dark`" in f[0])

            # A re-tuned PRIMITIVE, which the old check could not see at all: it stored `@theme`
            # as names only, so a changed hex was invisible. Keeping values bought this.
            prim = scaffold.replace("--color-rh-brand-600: #1171B0", "--color-rh-brand-600: #BADA55", 1)
            state, f = compare(wrap(prim), rel_src, knobs)
            check("a re-tuned primitive is `changed` in `@theme`",
                  len(f) == 1 and f[0].startswith("changed:") and "`@theme`" in f[0])

            gone = scaffold.replace("  --ring: var(--color-rh-brand-600);\n", "", 1)
            state, f = compare(wrap(gone), rel_src, knobs)
            check("a deleted pack role is still `missing`",
                  len(f) == 1 and f[0].startswith("missing:") and "--ring" in f[0])

            # EXTRA survives, but only for a token neither the pack NOR the system declares.
            mine = scaffold.replace(blk(":root", scale + ramp), blk(":root", "  --my-thing: 4px;\n" + scale + ramp), 1)
            assert mine != scaffold, "the local-token fixture must actually add a token"
            state, f = compare(wrap(mine), rel_src, knobs)
            check("a genuinely local token is still `extra`",
                  len(f) == 1 and f[0].startswith("extra:") and "--my-thing" in f[0])

            # ...and the SYSTEM tokens in that same block are NOT extra, which is the whole fix.
            check("the system scale is not reported extra",
                  not any("--radius" in x or "--space-" in x or "--measure" in x for x in f))

        # Re-tune ONE role in `:root` and nothing else, so the finding can only be that value.
        first = next(iter(toks))
        drifted = body.replace(f"{first}: {toks[first]};", f"{first}: #010203;", 1)
        state, f = compare(wrap(drifted), rel.read_text(encoding="utf-8"))
        check("real drift against the right pack is STILL reported",
              state == "drift" and any(x.startswith("changed: ") and first in x for x in f))

    if DOC.is_file():
        toks = plugin_tokens(DOC.read_text(encoding="utf-8"))
        check("the real doctrine parses to a non-trivial token set", len(toks) > 40)
        check("...and includes a role added in this cycle", "--overlay" in toks)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--css", type=Path, default=DEFAULT_CSS)
    ap.add_argument("--brand", metavar="SLUG",
                    help="the brand pack to compare against (default: read "
                         "config.x.brand.pack from config/initializers/brand.rb)")
    ap.add_argument("--root", type=Path, default=Path("."),
                    help="project root holding config/initializers/brand.rb (default: .)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.css.is_file():
        print(f"no {a.css} — nothing to compare", file=sys.stderr)
        return 2
    doc, why = resolve_baseline(a.brand, a.root)
    if doc is None:
        print(f"cannot compare: {why}", file=sys.stderr)
        return 2
    state, found = compare(a.css.read_text(encoding="utf-8"),
                           doc.read_text(encoding="utf-8"), pack_knobs(doc))
    if state == "clean":
        print(f"clean — {a.css}'s managed block is in step with the {why!r} pack")
        return 0
    print(f"{state}: {len(found)} finding(s) in {a.css}", file=sys.stderr)
    for f in found:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
