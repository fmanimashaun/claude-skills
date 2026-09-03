"""Mutation guard: check_mandated_gems. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #778. simple_form is marked Always and had neither an installer nor a gate. The second
    # rule is claims-vs-enforcement inside the USER's project: config naming a gem they do not
    # have is a claim nothing makes true.
    name="check_mandated_gems",
    subject="plugins/rails-flow/scripts/check_mandated_gems.py",
    selftest="plugins/rails-flow/scripts/check_mandated_gems.py",
    # The DERIVED artifact joins `needs` (#797): the checker reads it, so without
    # it the staged tempdir yields an empty list and the unmutated selftest fails --
    # the harness reports INERT. Fourth time today a guard's needs fell behind its
    # subject; needs is everything the subject reads, artifacts included.
    needs=("plugins/rails-flow/mandated_gems.json",),
    mutations=(
        # #797. The doctrine wrote 15 gems as literal `gem` lines; 4 were installed by any
        # command and 2 were checked. A project could hold rspec-rails and no simplecov,
        # webmock or vcr and report clean everywhere.
        Mutation(
            "the prescribed testing stack stops being required",
            "    missing = [g for g in testing_stack() if g not in gems]",
            "    missing = []",
            "a Gemfile missing simplecov FAILS",
        ),
        Mutation(
            # DERIVED, not hardcoded: enforcing one gem and ignoring the other eight would pass
            # a fixture that only ever removed simplecov.
            "only the first gem is enforced instead of the whole derived list",
            '        return list(json.loads(MANDATED.read_text(encoding="utf-8")).get("testing_stack") or [])',
            '        return ["rspec-rails"]',
            "EVERY gem in the derived list is required",
        ),
        Mutation(
            "simple_form stops being required, so the Always gem is a preference again",
            '    if "simple_form" not in gems:',
            "    if False:",
            "a Gemfile without simple_form FAILS",
        ),
        Mutation(
            # Conditional on purpose: the doctrine does not say every project carries factory_bot,
            # only that config naming it needs it.
            "factory_bot becomes unconditional, failing projects that never asked for it",
            '    if application_rb and re.search(r"fixture_replacement\\s+:factory_bot", application_rb):',
            "    if application_rb:",
            "no fixture_replacement config, no factory_bot requirement",
        ),
        Mutation(
            "a repo with no Gemfile reads as a pass",
            'return 3, f"not applicable — no {GEMFILE} in this repo (nothing to check, NOT a pass)"',
            'return 0, "ok"',
            "no Gemfile is not-applicable, not a pass",
        ),
        Mutation(
            "GEM loses its line anchor, so a commented-out gem counts as declared",
            'r"""^\\s*gem\\s+',
            'r"""\\s*gem\\s+',
            "a commented-out gem does not count",
        ),
    ),
)
