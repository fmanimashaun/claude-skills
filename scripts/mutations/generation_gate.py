"""Mutation guard: generation_gate. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="generation_gate",
    subject="plugins/design-flow/scripts/generation_gate.py",
    selftest="plugins/design-flow/scripts/generation_gate.py",   # --selftest lives in the module
    # No `needs`: every fixture builds its own config in a tempdir. This path spends real money,
    # so each mutation removes exactly ONE refusal and names the fixture that catches it -- a
    # mutation caught by the wrong fixture would mean some other check is doing the work.
    # The reference pack: a fixture asserts the SHIPPED brand satisfies the palette
    # contract its own composer depends on — it did not, which is the bug.
    needs=("plugins/design-flow/brands/fidara/brand.json",),
    mutations=(
        Mutation(
            # #629. The crafted-prompt path replaced a flat refusal, so the ONLY thing now
            # guaranteeing the brief's hard constraints reach the prompt is this check. Without
            # it #621 comes straight back: a brief saying "monochrome, single-hue only" and a
            # prompt that never mentions colour, answered with a full-colour photograph.
            "a crafted prompt is accepted without checking it against the brief's palette",
            '        if wanted and not (wanted & words):',
            "        if False:",
            "a crafted prompt that drops the palette constraint",
        ),
        Mutation(
            # A prompt asking for what the brief forbids is answered exactly as asked, then
            # rejected on arrival -- a full round trip and a full charge to learn what the
            # brief already said.
            "a crafted prompt may request what the brief's `avoid` list forbids",
            "        if banned and banned <= words:",
            "        if False:",
            "a crafted prompt requesting what `avoid` forbids",
        ),
        Mutation(
            # Without a rationale nobody can tell later whether crafting helped, and the trade
            # this change makes can never be re-evaluated against its own results.
            "a crafted prompt needs no rationale, so the trade cannot be judged later",
            '    if not str(request.get("prompt_rationale") or "").strip():',
            "    if False:",
            "a crafted prompt with no rationale",
        ),
        Mutation(
            # Matching on stopwords would make the constraint check pass on prompts honouring
            # nothing -- the palette "monochrome, single-hue only" shares "only" with almost any
            # prose. A gate that cannot fail is the defect this whole file exists to catch.
            "stopwords count as evidence, so the constraint check passes on anything",
            "    return {w for w in re.findall(r\"[a-z]{4,}\", text.lower()) if w not in _STOPWORDS}",
            "    return {w for w in re.findall(r\"[a-z]{1,}\", text.lower())}",
            "a crafted prompt sharing only a stopword with the palette",
        ),
        Mutation(
            # Reported after a real spend: a brief saying "monochrome only" produced a
            # full-colour photographic scene, because absence was NARRATED as `palette
            # unspecified` — an instruction, not a gap. Restoring that is restoring the bug.
            "an absent palette is narrated into the prompt instead of refused",
            "    if not palette:",
            "    if False:",
            "an unconstrained palette should be refused",
        ),
        Mutation(
            # The brief is the per-surface authority; reading only the pack is what silently
            # dropped the one constraint that mattered.
            "the brief's palette stops overriding the pack's",
            '    palette = brief.get("palette") or pack.get("palette") or []',
            '    palette = pack.get("palette") or []',
            "the brief's palette wins over the pack's",
        ),

        Mutation(
            # An unpriced rung treated as free makes the ceiling unreachable: every unpriced
            # model costs nothing, so the budget check cannot refuse -- a gate that cannot fail,
            # guarding the one thing here with a bill attached.
            "an unpriced rung stops refusing, so the budget compares against nothing",
            '        if rung.get("cost_usd") is None:',
            "        if False:",
            "an unpriced rung is refused",
        ),
        Mutation(
            # #161's shape with a bill attached: a ceiling documented and unenforced.
            "the budget comparison inverts, so spending past the ceiling is approved",
            "    if spent + projected > ceiling:",
            "    if False:",
            "projected cost exceeds the ceiling",
        ),
        Mutation(
            # #629 changed what this guards. It used to be "a free-typed prompt is REJECTED";
            # a crafted prompt is now accepted, so what must not be lost is the ROUTING -- drop
            # this branch and the crafted prompt is silently discarded and a composed one used
            # instead, which is the original defect wearing the opposite face: the caller
            # believes their text was used when it was not.
            "a crafted prompt is silently discarded and the composed one used instead",
            '    if "prompt" in request:',
            "    if False:",
            "a crafted prompt requesting what `avoid` forbids",
        ),
        Mutation(
            # Climbing with no stated check is how "best output" becomes "the agent liked it".
            "the ladder climbs with no acceptance check, so a reroll needs no justification",
            '    if attempt > 0 and not config.get("acceptance", {}).get(surface):',
            "    if False:",
            "climbing with no acceptance check",
        ),
        Mutation(
            # The DEFAULT install has no aggregator. If this stops refusing, the common case
            # walks into a provider that is not there.
            "a missing aggregator stops refusing, so the default install proceeds",
            "    if not name:",
            "    if False:",
            "no aggregator configured",
        ),
        Mutation(
            # `avoid` is the field most often skipped and the one that matters most to a
            # curated SET: without it the family drifts by well-meaning reuse.
            "an empty field passes, so a manifest can be present without being usable",
            "            if value in (None, \"\", [], {}):",
            "            if value is None and False:",
            "an entry with no avoid",
        ),
        Mutation(
            # The most expensive mistake available here: re-buying an asset the project owns.
            "a library is never required to have been searched, so owned assets get re-bought",
            '    if not miss or not miss.get("searched_for") or not miss.get("why_no_fit"):',
            "    if False:",
            "a library exists but was not searched",
        ),
        Mutation(
            # The manifest contradicting the miss is the sharper case -- generating anyway
            # forks the surface's look instead of filling a gap.
            "a covered surface stops being detected, so the same surface forks in two looks",
            '        if entry.get("surface") == surface and entry.get("kind", "static") == kind:',
            "        if False:",
            "...the manifest already covers this surface",
        ),
        Mutation(
            # The gap the reference survey exposed: "calm, abstract" renders as monochrome ink
            # OR as rounded flat-vector characters, and without a named style both pass.
            "any style string is accepted, so one pack can drift across two looks",
            "    if style not in STYLES:",
            "    if False:",
            "a style outside the taxonomy",
        ),
        Mutation(
            # Both free tiers must be ruled out EXPLICITLY. Drop this and a request reaches the
            # paying path while claiming a refusal it never made.
            "a free tier stops needing an explicit refusal, so generation is reachable first",
            '        why = refusal.get(f"tier_{tier}_why_not")',
            '        why = "assumed"',
            "tier 1 not ruled out",
        ),
    ),
)
