"""Mutation guard: check_token_drift. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #750/#754. The marker is the line between "the plugin's" and "yours", and every mutation
    # here erases that line in a different direction.
    name="check_token_drift",
    subject="plugins/design-flow/scripts/check_token_drift.py",
    selftest="plugins/design-flow/scripts/check_token_drift.py",
    # `doctrine_path.py` joins `needs` with #777: these now resolve the doctrine through the
    # shared resolver, so without it the staged tempdir fails at IMPORT and the harness
    # reports the guard INERT -- every mutation "caught" whether or not it breaks anything.
    # A guard's needs is everything its subject imports, and that changed when the subject did.
    # `brands/` joins `needs` with #788: the baseline is now the PACK, and the fixtures
    # parse the real reliance theme, so without it the staged tempdir fails and the
    # harness reports the guard INERT -- every mutation "caught" regardless. A guard's
    # needs is everything its subject reads, and that changed when the baseline did.
    # `brand_pack_lint` joins `needs` with #814: the comparison is theme-aware now and uses
    # that module's parser. Fifth time this week a guard's needs fell behind its subject.
    needs=("skills", "plugins/design-flow/scripts/doctrine_path.py",
           "plugins/design-flow/scripts/brand_pack_lint.py",
           "plugins/design-flow/brands"),
    mutations=(
        # #814. #788 pointed the comparison at the right TARGET and left its KIND wrong: the
        # reference is a palette, the subject is a stylesheet. 72 findings on an untouched
        # scaffold, 70 false, and the advice would have moved design-flow's own scale tokens
        # out of design-flow's own managed block.
        Mutation(
            "the changed clause is off, so a re-tuned pack value passes",
            "            if ours[tok] and ours[tok] != theirs[tok]:",
            "            if False:",
            "real drift against the right pack is STILL reported",
        ),
        Mutation(
            # System = doctrine MINUS pack. Without it, `setup`'s own scale is reported as an
            # unexpected local extension -- 40 of the 72.
            "the system scale is reported as a local extension again",
            '    if name in doctrine_names:\n        return "system"',
            "    if False:\n        return \"system\"",
            "the system scale is not reported extra",
        ),
        Mutation(
            # Presence is the union across blocks; only the VALUE is last-wins. Taking the last
            # block made every token in an earlier `:root` read as missing.
            "only the last block per selector is read",
            "        for body in bpl.selector_blocks(src, sel):",
            "        for body in bpl.selector_blocks(src, sel)[-1:]:",
            "a genuinely local token is still `extra`",
        ),
        Mutation(
            # The slice used to run between the marker STRINGS, so it opened with ` */` and a
            # theme-aware parser read `*/\n:root` as the selector. Every block came back empty.
            "managed_block keeps the marker comment fragment",
            '    start = css.find("*/", i + len(BEGIN))',
            "    start = -1",
            "reformatting is not drift",
        ),
        Mutation(
            "@theme is never read, so primitives are invisible",
            "    for body in bpl.theme_bodies(src):",
            "    for body in bpl.theme_bodies(src)[:0]:",
            "a re-tuned primitive is `changed` in `@theme`",
        ),
        Mutation(
            # Names alone answer "is it declared"; the comparison needs "is it the same".
            "@theme values are dropped, so a re-tuned primitive is invisible",
            "                             for m in DECL.finditer(body)})",
            "                             for m in list(DECL.finditer(body))[:0]})",
            "a re-tuned primitive is `changed` in `@theme`",
        ),
        # #788. The baseline was ONE fixed file -- the fidara-flavoured doctrine -- so a
        # reliance project read as 100+ false findings whose remediation ("take the plugin's
        # value") would have reverted --primary from #1171B0 (4.97:1) to #137CC1 (4.26:1),
        # reintroducing the WCAG 1.4.3 failure the pack exists to avoid.
        Mutation(
            "an undeterminable pack falls back to fidara instead of refusing",
            "    slug = brand or project_pack(root)",
            '    slug = brand or project_pack(root) or "fidara"',
            "...and never names fidara as the fallback",
        ),
        Mutation(
            # THE CLAUSE THAT MAKES THE OBVIOUS FIX WRONG. brand.rb has always carried
            # default_variant, and for `reliance` it EQUALS the slug -- so the wrong inference
            # looks right until `fidara`, whose default variant is `fmworkflows`, a variant with
            # no pack directory.
            "the pack is inferred from default_variant, which is a variant not a pack",
            '    m = PACK_DECL.search(f.read_text(encoding="utf-8"))',
            '    import re as _r; m = _r.search(r"default_variant\\s*=\\s*.(?P<slug>[a-z0-9_-]+)", f.read_text(encoding="utf-8"))',
            "...refusing because nothing RECORDS a pack, not because fmworkflows is missing",
        ),
        Mutation(
            "the baseline goes back to the doctrine, ignoring the pack entirely",
            '    doc = BRANDS / slug / "theme.css"',
            '    doc = _DOCTRINE / "references" / "foundations-tokens.md"',
            "an unknown pack is refused",
        ),
        Mutation(
            "a pack that does not ship is no longer refused",
            "    if not doc.is_file():",
            "    if False:",
            "an unknown pack is refused",
        ),
        Mutation(
            # The one that would get the check switched off: flagging correct work.
            "the whole file is compared, so extending OUTSIDE the markers reads as drift",
            "    project = theme_blocks(block)",
            "    project = theme_blocks(css)",
            "a local token OUTSIDE the markers is silent",
        ),
        Mutation(
            # Target the VERDICT, not the branch: skipping the branch makes `finditer(None)`
            # raise, and a crash is not a verdict.
            "an unmanaged file reports clean, which is the lie this exists to prevent",
            '        return "unmanaged", [',
            '        return "clean", [',
            "no marker is 'unmanaged', not 'clean'",
        ),
        Mutation(
            "a token the plugin added stops being reported, so an adopter never learns",
            "    for tok in sorted(set(ours) - set(theirs)):",
            "    for tok in ():",
            "a token the plugin adds is reported missing",
        ),
        Mutation(
            # Without normalisation a reformat reads as a value change -- noise that teaches
            # people to ignore the report.
            # The CSS side is what the fixture varies; normalising only the doc side would
            # leave this undetectable, which is how the first attempt survived.
            "whitespace stops being normalised, so reformatting reads as drift",
            '            merged.update({m.group(1): " ".join(m.group(2).split())',
            '            merged.update({m.group(1): m.group(2)',
            "reformatting is not drift",
        ),
    ),
)
