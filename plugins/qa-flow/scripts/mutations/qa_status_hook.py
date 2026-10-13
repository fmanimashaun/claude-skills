"""Mutation guard: qa-status.sh. Declared here, run by scripts/mutation_check.py (#1955)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The SessionStart banner said "cleared for main" on a stamp's sha and verdict alone. It now asks the release gate (a child run of release-gate.sh on the command that promotes dev's tip) and says what
# the gate answered. Each mutation puts one of the old behaviours back, and each is caught by running the REAL banner in a real repository.
GUARD = Guard(
    name="qa_status_hook",
    subject="hooks/scripts/qa-status.sh",
    selftest="scripts/qa_status_selftest.py",
    needs=("scripts/fixture_git.py", "hooks/scripts", "scripts/read_certification.py", "scripts/push_targets.py", "scripts/release_evidence.py", "scripts/remote_evidence.py"),
    mutations=(
        Mutation(
            "the banner says cleared whatever the gate answered",
            """  if [ "$rc" = 0 ] && printf '%s' "$said" | grep -q 'certification valid for'; then""",
            "  if true; then",
            "an UNCOMMITTED stamp whose sha is dev's tip",
        ),
        Mutation(
            "the gate is asked with the session's QA_ALLOW_MAIN override, so an override reads as certified",
            "env -u QA_ALLOW_MAIN RAILS_FLOW_HOOK_DEADLINE=6",
            "env RAILS_FLOW_HOOK_DEADLINE=6",
            "QA_ALLOW_MAIN=1 in the session's environment never reads as certified",
        ),
        Mutation(
            "a refusal by the gate is not reported with its reason",
            """  elif [ "$rc" = 2 ]; then""",
            "  elif false; then",
            "a PASS stamp whose release-only evidence has a HOLE",
        ),
        Mutation(
            "a deadline exit is reported as a refusal again",
            '''      "the gate took longer than "*) echo''',
            '''      "NEVER MATCHES"*) echo''',
            "a gate that hits its deadline is reported as unable to judge in time",
        ),
        Mutation(
            "an allow with no confirmation falls into the could-not-be-run message again",
            '''  elif [ "$rc" = 0 ]; then''',
            '''  elif false; then''',
            "a gate that answers 0 without confirming the certification",
        ),
        Mutation(
            "a gate that could not be run still reads as an allow",
            """  said=""; rc=1""",
            """  said="certification valid for"; rc=0""",
            "where the gate cannot be run, the banner says so",
        ),
        Mutation(
            "the stamp's sha must equal dev's tip again, which a committed stamp never does",
            """if [ -n "$devsha" ] && [ "$verdict" = "PASS" ]; then""",
            """if [ -n "$devsha" ] && [ "$csha" = "$devsha" ] && [ "$verdict" = "PASS" ]; then""",
            "a committed stamp with passing evidence, dev at its tip",
        ),
    ),
)
