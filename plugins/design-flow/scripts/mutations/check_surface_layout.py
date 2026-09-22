"""Mutation guard: check_surface_layout. Run by scripts/mutation_check.py (#1117)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_surface_layout",
    subject="scripts/check_surface_layout.py",
    selftest="scripts/check_surface_layout.py",   # --selftest lives in the module
    needs=("scripts/source_text.py",),   # comments are blanked here (#1128)
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
            '    if not renders_a_slot(source, declared_slots(source, strip_comments(sibling))):',
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
    Mutation(
        # Comments are prose (#1128). Without this call the gate reports a file for DESCRIBING the
        # anti-pattern -- and the file that describes it is usually the one that fixed it.
        "comments are matched as if they were code",
        '    source = strip_comments(source)',
        '    source = source',
        'a comment describing the wrapper is not the wrapper',
    ),
    Mutation(
        # #1141: the pattern matched ANY bare identifier, so a constructor keyword and a
        # CSS-class helper read as slots and an innocent table was reported. This is #1128's
        # "match the construct, never the word" surviving one variant along -- fixed for the word
        # `content`, left open for `[a-z_]+`.
        "any bare identifier counts as a slot again",
        '    return any(re.search(r"<%=\\s*" + re.escape(name) + r"\\s*%>", source) for name in slots)',
        '    return bool(re.search(r"<%=\\s*[a-z_]+\\s*%>", source))',
        "an attribute reader is not a slot, so a recipe elsewhere is not a finding",
    ),
    Mutation(
        # THE CONTROL SIDE: narrowing what counts as a slot must not switch the check off. A
        # component that DECLARES one and wraps it is the thing this gate exists for.
        "a declared slot stops being recognised, so nothing is ever reported",
        "    return {\"content\"} | set(SLOT_DECLARATION.findall(source)) | set(SLOT_DECLARATION.findall(sibling))",
        "    return set()",
        "...while a DECLARED slot wrapped in a recipe is still reported",
    ),
    Mutation(
        # The declaration lives in the `.rb` and the rendering in the `.html.erb`. Reading one
        # without the other is why attribute readers looked like slots in the first place.
        "the paired .rb is no longer read, so no slot is ever declared",
        "        sibling = _sibling_source(path)",
        '        sibling = ""',
        "...while a DECLARED slot wrapped in a recipe is still reported",
    ),
    ),
)
