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
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doctrine_path                    # noqa: E402 -- same plugin, one resolver

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
    """Text between the markers, or None when the file is unmanaged."""
    i = css.find(BEGIN)
    j = css.find(END, i + 1) if i != -1 else -1
    return css[i + len(BEGIN):j] if i != -1 and j != -1 else None


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


def compare(css: str, doc_text: str) -> tuple[str, list[str]]:
    """`(state, findings)`. State is `unmanaged`, `drift` or `clean`."""
    block = managed_block(css)
    if block is None:
        return "unmanaged", [
            f"no `{BEGIN}` marker — this file was scaffolded before the marker existed, or by hand. "
            f"Nothing can tell the plugin's tokens from yours, so nothing is checked. This is NOT a "
            f"pass: re-run /design-flow:setup to establish the managed block."]
    theirs = {m.group(1): " ".join(m.group(2).split()) for m in DECL.finditer(block)}
    ours = plugin_tokens(doc_text)
    out: list[str] = []
    for tok in sorted(set(ours) - set(theirs)):
        out.append(f"missing: the plugin declares {tok} and the managed block does not — this "
                   f"project is behind; re-run /design-flow:setup")
    for tok in sorted(set(theirs) - set(ours)):
        out.append(f"extra: {tok} is inside the managed block but the plugin does not declare it — "
                   f"a local extension belongs OUTSIDE the markers, where a re-run will not eat it")
    for tok in sorted(set(ours) & set(theirs)):
        if ours[tok] != theirs[tok]:
            out.append(f"changed: {tok} is {theirs[tok]!r} here and {ours[tok]!r} in the plugin — "
                       f"re-tune it outside the markers, or take the plugin's value")
    return ("drift" if out else "clean"), out


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    doc = "--background: #FFF;\n--primary: #0077CC;\n"
    wrap = lambda body: f"/* {BEGIN} */\n{body}/* {END} */\n"          # noqa: E731

    state, f = compare(wrap("--background: #FFF;\n--primary: #0077CC;\n"), doc)
    check("an in-step managed block is clean", state == "clean" and f == [])

    state, f = compare(wrap("--background: #FFF;\n"), doc)
    check("a token the plugin adds is reported missing",
          state == "drift" and any(x.startswith("missing: ") and "--primary" in x for x in f))

    state, f = compare(wrap("--background: #FFF;\n--primary: #0069B4;\n"), doc)
    check("a re-tuned value is reported changed",
          any(x.startswith("changed: ") and "--primary" in x for x in f))

    state, f = compare(wrap("--background: #FFF;\n--primary: #0077CC;\n--mine: #123;\n"), doc)
    check("a local token INSIDE the markers is reported extra",
          any(x.startswith("extra: ") and "--mine" in x for x in f))

    # THE LINE THAT MAKES THIS SAFE. A project extending OUTSIDE the markers is doing the right
    # thing and must be silent -- a check that flagged it would be switched off within a week.
    outside = wrap("--background: #FFF;\n--primary: #0077CC;\n") + "--mine: #123;\n--yours: #456;\n"
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
    state, f = compare(wrap("--background:   #FFF ;\n--primary:\t#0077CC;\n"), doc)
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
        toks = plugin_tokens(rel.read_text(encoding="utf-8"))
        body = "".join(f"  {k}: {v};\n" for k, v in toks.items())
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
        first = next(iter(toks))
        drifted = "".join(f"  {k}: {'#010203' if k == first else v};\n" for k, v in toks.items())
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
                           doc.read_text(encoding="utf-8"))
    if state == "clean":
        print(f"clean — {a.css}'s managed block is in step with the {why!r} pack")
        return 0
    print(f"{state}: {len(found)} finding(s) in {a.css}", file=sys.stderr)
    for f in found:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
