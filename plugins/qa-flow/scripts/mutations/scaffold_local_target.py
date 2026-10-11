"""Mutation guard: scaffold_local_target. Declared here, run by scripts/mutation_check.py (#866). The guard is the robot's only protection against signing real accounts in on a real system (#1835)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_local_target",
    subject="scaffold/qa/e2e/support/local-target.ts",
    selftest="scripts/scaffold_ts_tests.py",
    needs=("scaffold/qa/e2e/support/totp.ts", "scaffold/qa/e2e/support/qa-marker.ts", "scaffold/qa/e2e/support/mail-reader.ts", "scaffold/qa/e2e/support/local-target.test.ts", "scaffold/qa/e2e/support/totp.test.ts", "scaffold/qa/e2e/support/qa-marker.test.ts", "scaffold/qa/e2e/support/mail-reader.test.ts",),
    mutations=(
        Mutation(
            'userinfo is accepted, so 127.0.0.1:x@prod.example.com dials production',
            '  if (url.username || url.password) {',
            '  if (false) {',
            'userinfo that hides a real host is refused',
        ),
        Mutation(
            'a prefix check replaces the exact host list (the reviewed bypass)',
            '  if (!LOCAL_HOSTS.has(url.hostname)) {',
            '  if (![...LOCAL_HOSTS].some(h => url.hostname.startsWith(h.replace(/[\\[\\]]/g, "")))) {',
            'a host that only STARTS like this machine is refused',
        ),
        Mutation(
            'any scheme is accepted',
            '  if (url.protocol !== "http:" && url.protocol !== "https:") {',
            '  if (false) {',
            'not http(s), not a URL, or missing is refused',
        ),
    ),
)
