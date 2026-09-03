"""Mutation guard: palette_candidates. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="palette_candidates",
    subject="plugins/design-flow/scripts/palette_candidates.py",
    selftest="plugins/design-flow/scripts/palette_candidates.py",
    # It imports its sibling for the ROLE CONTRACT -- that import is the reuse that makes
    # "the composer covers the whole contract" checkable at all.
    deps=("plugins/design-flow/scripts/brand_pack_lint.py",),
    mutations=(
        Mutation(
            "the contrast bar stops comparing, so an unreadable palette ships",
            "    return [row for row in measure(roles) if not row.passes]",
            "    return []",
            "a failing candidate is reported, not passed",
        ),
        Mutation(
            "the bar drops to the large-text allowance, grandfathering unreadable body text",
            "AA_NORMAL = 4.5",
            "AA_NORMAL = 3.0",
            "3:1 is the LARGE-text allowance",
        ),
        Mutation(
            "every palette is reported as failing (the false-positive direction)",
            "        return self.ratio >= AA_NORMAL",
            "        return False",
            "a conformant candidate is silent",
        ),
        Mutation(
            "measuring zero pairs reports clean",
            "    if not CANDIDATE_PAIRS:",
            "    if False:",
            "measuring nothing is not a pass",
        ),
        Mutation(
            "the composer may omit a role, so a pack falls back to a stock Tailwind colour",
            '    missing = [r for r in bpl.ROLES if r not in light]',
            "    missing = []",
            "a role added to the contract makes snap() fail loudly",
        ),
        Mutation(
            "a surface role may stay put on dark, so dark mode inherits the light surface",
            "    unrepointed = [r for r in bpl.DARK_REQUIRED if dark.get(r) == light.get(r)]",
            "    unrepointed = []",
            "a dark-required role that does not move makes snap() fail loudly",
        ),
        Mutation(
            "nearest_passing hands back the failing input dressed as a fix",
            "    if contrast(colour, surface) >= threshold:\n        return colour, contrast(colour, surface)",
            "    return colour, contrast(colour, surface)",
            "the nearest alternative actually passes",
        ),
        Mutation(
            "nearest_passing rewrites a brand colour that was already fine",
            "    if contrast(colour, surface) >= threshold:",
            "    if False:",
            "a brand colour that already passes is returned unchanged",
        ),
        Mutation(
            "the search drifts off the client's hue instead of only its lightness",
            "            candidate = _from_hls(hue, candidate_light, sat)",
            "            candidate = _from_hls((hue + 0.25) % 1.0, candidate_light, sat)",
            "the nearest alternative keeps the client's hue",
        ),
        Mutation(
            "a constrained search with no answer returns rather than saying so",
            '    raise Unusable(\n        f"no {direction} shade of {colour} clears',
            '    return colour, contrast(colour, surface)\n    raise Unusable(\n        f"no {direction} shade of {colour} clears',
            "a constrained search with no answer returned instead of raising",
        ),
        Mutation(
            "a pack with no .dark block is measured as though light were both modes",
            '    if not dark:\n        raise Unusable(f"{theme_css}: no `.dark` block',
            '    if False:\n        raise Unusable(f"{theme_css}: no `.dark` block',
            "a pack with no .dark block was read instead of refused",
        ),
        Mutation(
            "`.dark` stops inheriting from `:root` (the #304 mechanism, in the reader)",
            '    scopes["dark"] = {**scopes["light"], **dark}',
            '    scopes["dark"] = dict(dark)',
            "a pack read back off disk measures the same as the model that wrote it",
        ),
        Mutation(
            "an emitted manifest claims the chart validation nobody ran",
            '        "chart_palette_validated": False,',
            '        "chart_palette_validated": True,',
            "the emitted manifest never claims a validation it did not run",
        ),
        Mutation(
            "the catalogue is free to grow into the style menu this must not become",
            "CATALOGUE_BAND = (8, 12)",
            "CATALOGUE_BAND = (8, 400)",
            "the catalogue band is the declared 8-12",
        ),
        Mutation(
            "a type pairing may carry its own fluid type scale, forking a system axis",
            "    return sorted(slug for slug, pairing in pairings.items()\n"
            "                  if any(key not in PAIRING_KEYS for key in pairing))",
            "    return []",
            "a pairing that DID carry a type scale would be caught",
        ),
        Mutation(
            "an unparseable colour resolves to something arbitrary instead of raising",
            "    if not isinstance(value, str) or not HEX_RE.match(value.strip()):",
            "    if False:",
            "",   # normalise_hex is called everywhere; the module fails hard, which is honest
        ),
    ),
)
