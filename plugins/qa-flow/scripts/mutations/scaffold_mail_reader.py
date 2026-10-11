"""Mutation guard: scaffold_mail_reader. Declared here, run by scripts/mutation_check.py (#866). The reader must refuse a non-QA address before any request, and read only a catcher on this machine (#1835)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_mail_reader",
    subject="scaffold/qa/e2e/support/mail-reader.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/local-target.ts", "scaffold/qa/e2e/support/totp.ts", "scaffold/qa/e2e/support/qa-marker.ts", "scaffold/qa/e2e/support/local-target.test.ts", "scaffold/qa/e2e/support/totp.test.ts", "scaffold/qa/e2e/support/qa-marker.test.ts", "scaffold/qa/e2e/support/mail-reader.test.ts",),
    mutations=(
        Mutation(
            'a non-QA address reaches Mailpit',
            '    const want = assertQaAddress(address, "read the mail of");',
            '    const want = address.trim().toLowerCase();',
            'a non-QA address is refused BEFORE any request is made',
        ),
        Mutation(
            "the catcher's URL is not guarded, so a real mailbox could be read",
            '    this.baseUrl = assertLocalTarget(baseUrl);',
            '    this.baseUrl = baseUrl.replace(/\\/$/, "");',
            'the catcher itself must be on this machine',
        ),
        Mutation(
            'a link is rebased onto any host, not the guarded local stack',
            '  const origin = assertLocalTarget(baseURL);',
            '  const origin = baseURL.replace(/\\/$/, "");',
            'the link is rebased onto the local stack',
        ),
        Mutation(
            "a message to ANOTHER recipient that the catcher returns is kept",
            "    const summaries = (found.messages ?? []).filter(s => s.To.some(t => t.Address.toLowerCase() === want));",
            "    const summaries = found.messages ?? [];",
            "a message the catcher returns for ANOTHER recipient is dropped",
        ),
        Mutation(
            "the first-six-digits fallback is back, so a postcode becomes a second-factor code",
            "  const code = mail.text.match(/\\bcode\\b\\D{0,20}?(\\d{6})\\b/i)?.[1];",
            "  const code = (mail.text.match(/\\bcode\\b\\D{0,20}?(\\d{6})\\b/i) ?? mail.text.match(/\\b(\\d{6})\\b/))?.[1];",
            "the code and the sign-in link are read from the message",
        ),
    ),
)
