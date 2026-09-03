"""Mutation guard: research_record. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="research_record",
    subject="plugins/design-flow/scripts/research_record.py",
    selftest="plugins/design-flow/scripts/research_record.py",   # --selftest lives in the module
    # #636 added the import of `STYLES`, and the standing rule applies: a guard's `needs` is
    # EVERYTHING the subject opens, so an added import is an added need. Without it every
    # mutation dies on ModuleNotFoundError and reads as "caught" while proving nothing.
    needs=("plugins/design-flow/scripts/generation_gate.py",),
    # Otherwise every fixture is a dict literal and nothing here touches the network -- which
    # matters more than usual, because the subject is about BROWSING other people's sites.
    mutations=(
        Mutation(
            # #636. Presence-only let a record settle on a style every brief would later refuse
            # -- discovered by the generator three steps on, after the plan was costed.
            "the chosen style stops being held to the taxonomy",
            "    if chosen and chosen not in STYLES:",
            "    if False:",
            "a style outside the taxonomy is reported",
        ),
        Mutation(
            # #637. Without traits `design-critic` has the references and no list to walk, so its
            # output is as good as the model's taste that day.
            "a record may choose a direction and never say how to recognise it",
            '    if record.get("style") and not traits:',
            "    if False:",
            "a record that chose a style and stated no traits is reported",
        ),
        Mutation(
            # #632. The record is the ONLY place an exception may be declared, so its validation
            # is the only thing standing between "a decision, made once, in the open" and any
            # style at all appearing in the list unexplained.
            "an exception needs no `why`, so the record cannot tell a decision from drift",
            '        if not str(exc.get("why") or "").strip():',
            "        if False:",
            "an exception with no `why` is reported",
        ),
        Mutation(
            # The generated skill is doctrine the PROJECT'S agent reads. Dropped, it keeps
            # asserting that every brief carries the one style -- against a project whose
            # research sanctioned a second one. A wrong rule written into the user's own skill.
            "the generated skill omits the declared exception it is meant to license",
            "    if exceptions:",
            "    if False:",
            "a declared exception reaches the generated skill",
        ),
        Mutation(
            # Emitting doctrine from an unreviewable record publishes a decision nobody made,
            # in the place agents trust most. The skill is only written from a record that
            # PASSES -- a record that gathers and does not choose must not become guidance.
            "an unreviewable record still emits a skill, publishing a decision nobody made",
            "    problems = check(record)   # emit_skill: refuse at the point of writing",
            "    problems = []", 
            "a record with no style should not emit a skill",
        ),
        Mutation(
            # "Three or more sources disagree, and the choosing IS the design." A record that
            # gathers and does not choose is a mood board.
            "a record may gather without choosing, so the research produces no decision",
            '    if record.get("references") and not record.get("style"):',
            "    if False:",
            "a record with references and no style is reported",
        ),
        Mutation(
            # Direct competitors converged on one look by copying each other. A record sampled
            # only from them inherits the convergence and produces the median.
            "an all-competitor record passes, so the output inherits their convergence",
            "    if refs and cats == {\"direct\"}:",
            "    if False:",
            "an all-direct record is reported",
        ),
        Mutation(
            # A login wall returns a PAGE, not an error -- so the capture can be the wall, filed
            # as research, and nothing downstream can tell.
            "a sign-in capture passes unmarked, so the wall is filed as a reference",
            '        if re.search(r"(login|signin|sign-in|auth)", cap, re.I) and not ref.get("gated"):',
            "        if False:",
            "a sign-in-looking capture with no `gated` is reported",
        ),
        Mutation(
            "everything-adopted stops being reported, so a shopping list passes as research",
            "    if refs and not any(r.get(\"reject\") for r in refs):",
            "    if False:",
            "a record rejecting nothing is reported",
        ),
    ),
)
