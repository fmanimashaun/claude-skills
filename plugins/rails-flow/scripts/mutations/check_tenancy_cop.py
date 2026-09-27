"""Mutation guard: check_tenancy_cop. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1361. The cop is only as good as its config, and RuboCop validates none of a local cop's keys,
    # so every refusal here is one nothing else in the chain performs.
    name="check_tenancy_cop",
    subject="scripts/check_tenancy_cop.py",
    selftest="scripts/check_tenancy_cop.py",
    # The shipped cop is what an installed copy is compared against; without it the staged tempdir
    # has nothing to compare and the unmutated selftest cannot run.
    needs=("scaffold/tenancy/scoped_lookup.rb",),
    mutations=(
        Mutation(
            "an unknown key under the cop is no longer reported, so a typo configures nothing silently",
            "    for key in sorted(set(section) - KNOWN_KEYS):",
            "    for key in []:",
            "an unknown (typo'd) key is refused by name",
        ),
        Mutation(
            "a tenant-FK table outside TenantOwnedModels passes, so a stale model list cannot fail",
            "            if table not in unscoped and not covered(table, associations):",
            "            if False:",
            "a tenant-FK table outside TenantOwnedModels is refused",
        ),
        Mutation(
            "a hand-edited cop passes as the shipped one",
            '    elif installed.read_text(encoding="utf-8") != shipped:',
            "    elif False:",
            "a hand-edited cop is refused",
        ),
        Mutation(
            "SafeAutoCorrect is no longer required, so `rubocop -a` rewrites queries silently",
            '    if section and section.get("SafeAutoCorrect") is not False:',
            "    if False:",
            "a missing SafeAutoCorrect: false is refused",
        ),
        Mutation(
            "an unscoped table no longer needs a reason",
            "    if not isinstance(unscoped, dict) or not all(isinstance(r, str) and r.strip()",
            "    if not isinstance(unscoped, dict) or not all(isinstance(r, str)",
            "...but WITHOUT a reason it is refused",
        ),
        Mutation(
            "a declared single-tenant app reads as a pass instead of not-applicable",
            "            return 3",
            "            return 0",
            "a declared single-tenant app is not applicable (exit 3)",
        ),
    ),
)
