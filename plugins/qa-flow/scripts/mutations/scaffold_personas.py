"""Mutation guard: scaffold_personas. Declared here, run by scripts/mutation_check.py (#866). The manifests must never hold or attribute anything to a non-QA address (#1836)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_personas",
    subject="scaffold/qa/e2e/support/personas.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/personas.test.ts", "scaffold/qa/e2e/support/qa-marker.ts",),
    mutations=(
        Mutation(
            'a non-QA persona address is written',
            '    assertQaAddress(p.email, "record the persona");',
            '    p.email.trim();',
            'a non-QA address is refused on write AND on read',
        ),
        Mutation(
            'a record made by a non-QA address is kept',
            '  assertQaAddress(rec.by, "record a record made by");',
            '  rec.by.trim();',
            'a record made by a non-QA address, or without kind/id, is refused',
        ),
        Mutation(
            'a duplicate persona handle is accepted',
            '    if (handles.has(p.handle)) throw',
            '    if (false) throw',
            'a duplicate handle is refused',
        ),
        Mutation(
            'the manifests are written world-readable',
            '  writeFileSync(join(dir, "personas.json"), JSON.stringify(checked(m), null, 2) + "\\n", { mode: 0o600 });',
            '  writeFileSync(join(dir, "personas.json"), JSON.stringify(checked(m), null, 2) + "\\n");',
            'files are owner-only',
        ),
    ),
)
