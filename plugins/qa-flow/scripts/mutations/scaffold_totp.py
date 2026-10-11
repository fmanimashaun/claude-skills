"""Mutation guard: scaffold_totp. Declared here, run by scripts/mutation_check.py (#866). A wrong code fails the real second factor; the RFC 6238 vectors are the oracle (#1835)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_totp",
    subject="scaffold/qa/e2e/support/totp.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/local-target.ts", "scaffold/qa/e2e/support/qa-marker.ts", "scaffold/qa/e2e/support/mail-reader.ts", "scaffold/qa/e2e/support/local-target.test.ts", "scaffold/qa/e2e/support/totp.test.ts", "scaffold/qa/e2e/support/qa-marker.test.ts", "scaffold/qa/e2e/support/mail-reader.test.ts",),
    mutations=(
        Mutation(
            'the dynamic-truncation offset uses three bits instead of four',
            '  const offset = mac.readUInt8(mac.length - 1) & 0x0f;',
            '  const offset = mac.readUInt8(mac.length - 1) & 0x07;',
            'every RFC 6238 SHA-1 test vector',
        ),
        Mutation(
            'a character outside base32 is skipped instead of refused',
            '    if (i < 0) throw new Error(`not base32: ${c}`);',
            '    if (i < 0) continue;',
            'a character outside base32 is refused',
        ),
    ),
)
