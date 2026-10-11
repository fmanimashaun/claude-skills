"""Mutation guard: scaffold_qa_marker. Declared here, run by scripts/mutation_check.py (#866). The marker is what the
sign-in helpers and mail readers refuse on, and what teardown looks for; a loosened pattern lets a person's address through (#1835)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_qa_marker",
    subject="scaffold/qa/e2e/support/qa-marker.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/local-target.ts", "scaffold/qa/e2e/support/totp.ts", "scaffold/qa/e2e/support/mail-reader.ts", "scaffold/qa/e2e/support/local-target.test.ts", "scaffold/qa/e2e/support/totp.test.ts", "scaffold/qa/e2e/support/qa-marker.test.ts", "scaffold/qa/e2e/support/mail-reader.test.ts",),
    mutations=(
        Mutation(
            "the marker is matched anywhere in the address, not anchored at the start",
            "const QA_ADDRESS = /^qa\\+",
            "const QA_ADDRESS = /qa\\+",
            "or one that only contains the marker, is refused",
        ),
        Mutation(
            "the marker check is skipped, so any address is a QA address",
            "  if (!isQaAddress(address)) throw new Error(`refusing to ${action}",
            "  if (false) throw new Error(`refusing to ${action}",
            "or one that only contains the marker, is refused",
        ),
    ),
)
