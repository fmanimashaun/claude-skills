"""Mutation guard: check_section_landmarks. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #92 (Phase 5). Same argument as `check_shared_shapes` above, one skill along: every mutation
# here makes a STALE CLAIM read as a fresh one. Two are structural rather than per-rule — the
# corpus walk going vacuous, and the measurement widening from "marketing rows" to "all of
# them" — because a gate whose INPUT quietly changed reports clean exactly like a gate over a
# correct repo. The last one breaks the checker the other way, so the silence direction has a
# mutation too: a pacing gate that fires on our own shipped sequence is a gate someone deletes.
# #91. The rule was PRACTISED in 16 of 18 sections and stated nowhere, so the mutations ask
# the two questions that matter: can it still fire, and can prose make it fire wrongly.
GUARD = Guard(
    name="check_section_landmarks",
    subject="scripts/check_section_landmarks.py",
    selftest="scripts/check_section_landmarks.py",
    needs=("skills/design-system/references",),
    mutations=(
        Mutation(
            "the name test accepts any aria-* attribute, so aria-hidden passes as a name",
            'NAMED = re.compile(r"(?<![-\\w])aria-(?:label|labelledby)\\s*=", re.I)',
            'NAMED = re.compile(r"(?<![-\\w])aria-[a-z]+\\s*=", re.I)',
            "'<section aria-hidden=\"true\">' does not name the section",
        ),
        Mutation(
            # A `data-` prefixed attribute is not an ARIA attribute. `\b` matched inside
            # `data-aria-label`; this gate's own fixture caught it.
            "the token boundary relaxes, so data-aria-label counts as an accessible name",
            'NAMED = re.compile(r"(?<![-\\w])aria-(?:label|labelledby)\\s*=", re.I)',
            'NAMED = re.compile(r"\\baria-(?:label|labelledby)\\s*=", re.I)',
            "'<section data-aria-label=\"x\">' does not name the section",
        ),
        Mutation(
            "the exemption matches by prefix, so any hero-ish tag is waved through",
            "            if tag in exempt:",
            "            if any(tag.startswith(e[:20]) for e in exempt):",
            "a lookalike hero tag still fails",
        ),
        Mutation(
            "prose is scanned as markup, making the gate unpassable beside its own doctrine",
            "    for offset, raw in code_blocks(text):",
            "    for offset, raw in [(0, text)]:",
            "a bare <section> in PROSE is not a finding",
        ),
        Mutation(
            # `return [] or [...]` would be a NO-OP -- `[]` is falsy, so `or` yields the
            # comprehension. Mutate the pattern to one that cannot match instead.
            "the fence pattern matches nothing, so every file reports clean",
            'FENCE = re.compile(r"^(?P<t>`{3,})',
            'FENCE = re.compile(r"^(?P<t>`{99,})',
            # Killing the extractor makes the very FIRST fixture fail, before the one that
            # probes `code_blocks` directly. That earlier fixture is the honest expectation.
            "a bare section is a finding",
        ),
        Mutation(
            # #475. The footer rule and the section rule are the same join over the same
            # markup, deliberately in one file so they cannot drift apart.
            "a nested footer stops being reported, so a page footer loses contentinfo silently",
            "        for offset_c, tag, parent in nested_footers(body):",
            "        for offset_c, tag, parent in []:",
            "a footer inside <section> is reported",
        ),
        Mutation(
            "a CLOSED ancestor still counts, flagging every footer that follows a band",
            "            if stack and stack[-1] == tag:",
            "            if False:",
            "a footer AFTER a closed section is silent",
        ),
        Mutation(
            # The bug this gate's own doctrine triggered: `<nav>` written inside an ERB comment
            # opened an element that never closed.
            "comments are scanned as markup again, so prose in a comment opens elements",
            "        body = strip_non_markup(raw)",
            "        body = raw",
            "an ERB comment naming <nav> does not open one",
        ),
        Mutation(
            "comment blanking drops the newlines, so every later line number is wrong",
            'return NON_MARKUP.sub(lambda m: re.sub(r"[^\\n]", " ", m.group(0)), body)',
            'return NON_MARKUP.sub("", body)',
            "a line number after a comment is still correct",
        ),
        Mutation(
            "a stale exemption stops being reported, so a carve-out outlives its markup",
            "        if declared and used < declared:",
            "        if False:",
            "a declared exemption matching nothing is reported",
        ),
    ),
)
