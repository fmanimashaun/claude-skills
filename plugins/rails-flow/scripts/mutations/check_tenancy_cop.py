"""Mutation guard: check_tenancy_cop. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1361. The review of #1403 BLOCKED a checker that re-derived RuboCop's config in Python: every
    # gap in that copy was a hole. The checker now asks RuboCop itself; each mutation below removes one
    # refusal, and the fixture named in `expects` must be the one that notices.
    name="check_tenancy_cop",
    subject="scripts/check_tenancy_cop.py",
    selftest="scripts/check_tenancy_cop.py",
    needs=("scaffold/tenancy/scoped_lookup.rb",),
    mutations=(
        Mutation(
            'an unknown key under the cop is no longer reported, so a typo configures nothing silently',
            '    for key in sorted(set(section) - KNOWN_KEYS):',
            '    for key in []:',
            "an unknown (typo'd) key is refused by name",
        ),
        Mutation(
            "the probe's verdict is ignored, so a cop that is off, pending or excluded passes",
            '        for key in probe(project, keys) if section is not None else []:',
            '        for key in []:',
            'a key the PROBE does not flag (cop off / excluded / pending) is refused',
        ),
        Mutation(
            "a model key that maps to no tenant table passes (the reviewer's `Invocie`)",
            '        if not set(names) & set(tables):',
            '        if False:',
            'a misspelt model KEY is refused -- the value alone proves nothing',
        ),
        Mutation(
            'a tenant-FK table no key maps to passes, so a stale model list cannot fail',
            '        if table not in unscoped and table not in reached:',
            '        if False:',
            'a tenant-FK table no key maps to is refused',
        ),
        Mutation(
            'a hand-edited cop passes as the shipped one',
            '    if installed.read_text(encoding="utf-8") != shipped:',
            '    if False:',
            'a hand-edited cop is refused',
        ),
        Mutation(
            'SafeAutoCorrect is no longer required, so `rubocop -a` rewrites queries silently',
            '    if section.get("SafeAutoCorrect") is not False:',
            '    if False:',
            'a missing SafeAutoCorrect: false is refused',
        ),
        Mutation(
            'a foreign key no table carries passes, so the coverage check reads nothing',
            '    if not tables:',
            '    if False:',
            'a foreign key no table carries is refused -- zero tables is not a pass',
        ),
        Mutation(
            'a RuboCop that will not run is swallowed, so a broken config reads as clean',
            '        out.append(f"cannot run the project\'s RuboCop/Ruby: {exc}")',
            '        pass',
            'a RuboCop that will not run is a FINDING, not a silent pass',
        ),
        Mutation(
            'a declared single-tenant app reads as a pass instead of not-applicable',
            '            return 3',
            '            return 0',
            'a declared single-tenant app is not applicable (exit 3)',
        ),
        Mutation(
            'an unscoped table no longer needs a reason',
            'all(isinstance(r, str) and r.strip() for r in unscoped.values())',
            'all(isinstance(r, str) for r in unscoped.values())',
            '...but WITHOUT a reason it is refused',
        ),
        Mutation(
            'a blank association passes, and the cop autocorrects to broken Ruby',
            '            if not (isinstance(assoc, str) and IDENTIFIER.match(assoc)):',
            '            if False:',
            'a blank association is refused (it would autocorrect to broken Ruby)',
        ),
        Mutation(
            "the probe counts every cop's offenses, so an unrelated one masks a missing tenancy offense",
            '             if o.get("cop_name") == COP_NAME}',
            '             }',
            "the probe report: only THIS cop's offenses count, by line",
        ),
    ),
)
