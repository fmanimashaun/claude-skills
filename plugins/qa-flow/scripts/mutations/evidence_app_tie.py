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
            # THE CARVE-OUT THAT KEEPS THIS USABLE. A project keyed on integers is CORRECT, and a
            # check preferring one id format would be wrong for every such project and switched off
            # within a week. Removing the agreement test fails them all.
            "a shape the corpus DOES show is reported anyway",
            "        if shapes & known:",
            "        if False:",
            "an app whose OWN evidence uses integers is not reported for using integers",
        ),
        Mutation(
            # One odd id is a data point -- a fixture, a legacy row, a redirect. Only a TOTAL
            # disagreement is a claim that the file was not driven.
            "a single row is enough to call a whole file fabricated",
            "        if count < min_rows:",
            "        if False:",
            "a single row is not enough to call a shape alien",
        ),
        Mutation(
            # With no corroboration for a segment there is nothing to disagree WITH; judging it
            # anyway invents a verdict out of absence, which is the defect this gate exists for.
            "a segment the corpus never covered is judged against nothing",
            "        if not known:",
            "        if False:",
            "a segment the corpus never covered is not judged",
        ),
        Mutation(
            # NOT APPLICABLE IS NOT A PASS. Dropping the note turns a tie that could not run into
            # a silent success -- exactly the shape of the bug being fixed, one level up.
            "a missing route inventory is reported as fine rather than as unrun",
            '            f"no {ROUTES_JSON} under {root} — BOTH ties are unrun, not passed. Generate it: "',
            '            f"no {ROUTES_JSON} under {root} — fine, carry on. Generate it: "',
            "with no routes.json BOTH ties are notes, not findings",
        ),
    ),
)
