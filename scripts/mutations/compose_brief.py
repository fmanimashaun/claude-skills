"""Mutation guard: compose_brief. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #639. The composition brief. Every mutation below leaves it PRODUCING A PLAUSIBLE BRIEF —
    # bands present, assets named, a table rendered — while answering the one question it exists
    # for wrongly. That is this flow's signature failure, so the fixtures must be provably able
    # to see it.
    name="compose_brief",
    subject="plugins/design-flow/scripts/compose_brief.py",
    selftest="plugins/design-flow/scripts/compose_brief.py",
    # It reads the real band table through the doctrine resolver, so the skill and the resolver
    # are both needs -- and without them every mutation dies on "cannot find design-system",
    # which reads as "caught" while proving nothing.
    needs=("plugins/design-flow/scripts/doctrine_path.py",
           "skills/design-system/references/page-anatomies.md"),
    mutations=(
        Mutation(
            # #676, second root cause. The surface only ever EXCLUDED -- `avoid` saw it and
            # `surfaces` scoped by it, and nothing let a row be RELEVANT because of it. So a row
            # saying "I am for /problem" was invisible on /problem: dead metadata.
            "surface-scoped rows stop being reported, so the metadata is dead again",
            '            if surface_relevant(e, surface)',
            "            if False",
            "a row scoped to this surface is relevant here, with zero band overlap",
        ),
        Mutation(
            # #676. Every surface composes from the one structured band table, which scopes
            # itself "for a product landing page". A pricing brief that is silently a landing
            # brief is the correct-looking-but-wrong output this flow keeps producing.
            "a borrowed anatomy stops being declared, so a pricing brief looks like pricing's",
            "    if anatomy.get(\"borrowed\"):",
            "    if False:",
            "a surface the catalogue governs is found",
        ),
        Mutation(
            # #676. Without it a `use_case` written for one page suggests the asset on another,
            # which a second real run reported as noise on the wrong surface.
            "a row scoped to other surfaces is suggested anyway",
            "        if surface_scoped_out(entry, surface):",
            "        if False:",
            "a row scoped elsewhere is excluded",
        ),
        Mutation(
            # #672 defect 1. A synonym miss used to be a silent `none`; naming the inventory is
            # the difference between an absence a reader investigates and one they skim past.
            "a band with no candidate stops naming what the project owns",
            "        elif inventory:",
            "        elif False:",
            "...but a stated `bands` entry names it outright",
        ),
        Mutation(
            # #672 defect 3. UNREPRESENTABLE before: pick_asset ran per band with no accumulator,
            # so a per-surface cap could not be checked however it was phrased.
            "the per-surface cap stops being counted across bands",
            "        if isinstance(cap, int) and cap >= 0 and len(bands_used) > cap:",
            "        if False:",
            "three bands against a cap of two is reported",
        ),
        Mutation(
            # #672 defect 4. `avoid "money CTAs"` could not fire on a "Closing CTA" band.
            "plurals stop matching singulars, so a prohibition misses its band",
            '    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}',
            "    return words",
            "`CTAs` and `CTA` are the same token",
        ),
        Mutation(
            # `avoid` is "the one people skip and the one that matters most". A stated
            # prohibition must outrank a stated permission, or the field means nothing at the
            # only moment it could act.
            "`avoid` stops excluding, so a forbidden asset fills the band it is barred from",
            "        if blocked:",
            "        if False:",
            "`avoid` excludes an asset whose use_cases match",
        ),
        Mutation(
            # Folding the surface into the match context made every band on `marketing-hero`
            # take the asset whose use case said "marketing hero" -- one asset, whole page.
            "the surface name rejoins the match, so every band takes the same asset",
            '    context = significant(f"{band.band} {band.composed}")',
            '    context = significant(f"{band.band} {band.composed} {surface}")',
            "a band with no matching asset gets no candidate",
        ),
        Mutation(
            # A brief pointing at an asset that is not there sends the builder looking for it.
            "a band may name an asset that is not on disk",
            '        if b.get("suggested") and not (root / b["suggested"]).is_file():',
            "        if False:",
            "...and one naming a missing asset does not",
        ),
        Mutation(
            # Degraded-but-honest is the contract: a silently thinner brief reads as a simpler
            # page rather than as missing inputs.
            "a brief stops saying which inputs it was composed without",
            '                              ("manifest.json", bool(owned))) if not present],',
            '                              ("manifest.json", bool(owned))) if False],',
            "...that names what it was composed without",
        ),
    ),
)
