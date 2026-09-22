"""Mutation guard: evidence_app_tie. Run by scripts/mutation_check.py (#1133)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="evidence_app_tie",
    subject="scripts/evidence_app_tie.py",
    selftest="scripts/evidence_app_tie.py",   # --selftest lives in the module
    # The pattern compiler is borrowed, not copied, and the selftest drives the entry points that
    # close the import cycle -- both need the real neighbours staged.
    needs=("scripts/route_coverage.py",
           "scripts/validate_evidence.py",
           "scripts/validate_evidence_selftest.py",
           "scripts/qa_config.py"),
    mutations=(
        Mutation(
            # The route tie: a path the app does not serve cannot have returned a status.
            "an unroutable path stops being a finding",
            "    return sorted({p for p in paths if not any(rx.fullmatch(p) for rx in compiled)})",
            "    return []",
            "a path matching no route is reported",
        ),
        Mutation(
            # THE CARVE-OUT THAT KEEPS THIS USABLE, and #1141 moved WHERE it is decided. A model
            # that never adopted a URL-id convention keys on integers CORRECTLY; judging it by a
            # project-wide rule rebuilds the peer-consensus defect from a different source.
            "every model is judged, not just the ones that override `to_param`",
            "        if owner is None:",
            "        if False:",
            "...so integer ids on IT are not a finding",
        ),
        Mutation(
            # The positive side: a model that DID adopt must still be reported, or the per-model
            # carve-out above has simply switched the check off.
            "a model that overrides `to_param` stops being judged",
            "    minted = models_with_url_ids(root)",
            "    minted = set()",
            "integers where the owning model overrides `to_param` are reported",
        ),
        Mutation(
            # A concern confers `to_param` on every model including it -- which is how a real app
            # spells this: 36 of 36 models, none writing `def to_param` themselves.
            "an `include`d concern no longer confers its `to_param`",
            "        if any(_underscore(name) in concerns for name in INCLUDES.findall(text)):",
            "        if False:",
            "a model including a `to_param` concern is known to mint URL ids",
        ),
        Mutation(
            # One odd id is a fixture, a legacy row or a redirect. Only a WHOLLY integer segment is
            # provably unmintable.
            "a single integer among minted ids condemns the whole segment",
            '        if shapes != {"integer"}:',
            "        if False:",
            "one minted id among integers is not a whole-segment verdict",
        ),
        Mutation(
            "a single row is enough to call a segment unmintable",
            "        if count < min_rows:",
            "        if False:",
            "a single row is not enough to call a segment unmintable",
        ),
        Mutation(
            # NOT APPLICABLE IS NOT A PASS. Dropping the note turns a tie that could not run into
            # a silent success -- exactly the shape of the bug being fixed, one level up.
            "a missing route inventory is reported as fine rather than as unrun",
            '            f"no {ROUTES_JSON} under {root} — BOTH ties are unrun, not passed. Generate it: "',
            '            f"no {ROUTES_JSON} under {root} — fine, carry on. Generate it: "',
            "with no routes.json BOTH ties are notes, not findings",
        ),
    Mutation(
        # #1141: `validate_evidence` tells you a row that cannot be validated is a Blocked row.
        # These ties read every row regardless of status, so taking that advice changed nothing --
        # reported by someone who marked the row and watched it fail anyway. A remedy a tool names
        # and does not honour is worse than no remedy: it sends people to do work that does not.
        "a Blocked row is read as if it claimed a result",
        "        if not makes_a_claim(row):",
        "        if False:",
        "a `Blocked` row asserts nothing, so no path is taken from it",
    ),
    Mutation(
        # THE ANTI-GAMING CONTROL. If any row's status silenced the whole FILE, one Blocked row
        # would hide every other row's claims -- the escape hatch becomes a way to assert nothing
        # while still shipping a green artifact.
        "any Blocked row silences its whole file",
        "    for row in rows:\n        if not makes_a_claim(row):\n            continue",
        "    if any(not makes_a_claim(r) for r in rows):\n        return []\n    for row in rows:\n        if False:\n            continue",
        "...and a claiming row beside it is still read",
    ),
    ),
)
