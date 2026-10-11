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
            'a hand-edited records.json with a non-QA author is returned on read',
            '  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as SeededRecord[]).map(checkedRecord) : [];',
            '  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as SeededRecord[]) : [];',
            'a hand-edited records.json with a non-QA author, or no id, is refused on read',
        ),
        Mutation(
            'an existing wider manifest keeps its mode on overwrite (no chmod)',
            '  chmodSync(file, 0o600);',
            '',
            'an existing WIDER file is narrowed to owner-only on overwrite',
        ),
        Mutation(
            'a new manifest is created with the default (world-readable) mode',
            '  writeFileSync(file, body, { mode: 0o600 });\n  chmodSync(file, 0o600);',
            '  writeFileSync(file, body);',
            'a new records.json is created owner-only',
        ),
    ),
)
