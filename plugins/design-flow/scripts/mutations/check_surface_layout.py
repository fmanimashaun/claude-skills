"""Mutation guard: check_surface_layout. Run by scripts/mutation_check.py (#1117)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_surface_layout",
    subject="scripts/check_surface_layout.py",
    selftest="scripts/check_surface_layout.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # The rule. A surface wrapping arbitrary content silently overrode 77 of 112 callers'
            # spacing, with no error and no glitch on most screens.
            "a surface may wrap its slot in a layout recipe again",
            "    for classes in CLASS_ATTR.findall(source):",
            "    for classes in []:",
            "a surface wrapping its slot in a recipe is caught",
        ),
        Mutation(
            # THE MUST-PASS HALF. A page shell and a dialog legitimately arrange their own parts;
            # a gate that failed them on day one would get an exclusion list or be switched off.
            "a declared composition stops being accepted",
            "        if DECLARES.search(source):",
            "        if False:",
            # The TREE-level fixture, not the regex one: this mutation breaks the `run()`
            # path, and asserting on DECLARES directly would pass with it broken.
            "the declared composition is not reported",
        ),
        Mutation(
            # MATCH SLOT RENDERING, NOT THE WORD. Keying on the bare word produced four false
            # positives in one real run -- a prose comment, a --content-cols property, a
            # "hidden-content" comment, and Tailwind's own before:content-[''] utility.
            "the detector matches the WORD content rather than a rendered slot",
            '    if not (SLOT_ERB.search(source) or SLOT_RUBY.search(source)):',
            '    if "content" not in source:',
            "NOT a finding: Tailwind's own before:content-[''] utility",
        ),
        Mutation(
            # A component arranging its OWN fixed parts is composing, not imposing on somebody
            # else's content. Dropping the slot requirement flags every layout in the app.
            "a recipe with no slot rendered becomes a finding",
            "        return None                      # renders no slot; nothing arbitrary to arrange",
            "        pass",
            "a recipe with no slot rendered is not this rule's business",
        ),
    ),
)
