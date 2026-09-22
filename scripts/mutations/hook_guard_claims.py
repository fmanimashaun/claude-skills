"""Mutation guard: hook_guard_claims. Declared here, run by scripts/mutation_check.py (#1141).

THE FAIL-CLOSED HOOK THAT HAD NO GUARD. `guard-claims.sh` is the only thing in this toolchain that
has actually stopped a wrong number reaching a person -- it blocks a PR body or an issue comment
carrying load-bearing claims with no evidence any were checked -- and nothing proved it could still
fail. Its siblings (`guard-bash`, `guard-lane`, `release-gate`, `stop-gate`) all had one.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_claims",
    subject="plugins/rails-flow/hooks/scripts/guard-claims.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # The harness resolves every hook from the selftest's own location, so the whole directory is
    # staged; `extract_claims.py` is what this hook shells out to, and without it every mutation
    # reads as caught against an unrun check (#1109).
    needs=("plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py"),
    mutations=(
        Mutation(
            # #1141: the scope was `gh pr create|edit` alone. On the day this hook fired on a PR
            # body carrying eight unverified claims, four ISSUE COMMENTS carrying counts went out
            # unchecked -- the same artifact, durable and read by someone else, through a hole.
            "an issue comment is out of scope again, so its claims go unchecked",
            'printf \'%s\' "$cmd" | grep -qE \'\\bgh[[:space:]]+(pr[[:space:]]+(create|edit)|issue[[:space:]]+comment)\\b\' || exit 0',
            'printf \'%s\' "$cmd" | grep -qE \'\\bgh[[:space:]]+pr[[:space:]]+(create|edit)\\b\' || exit 0',
            "guard-claims: an unchecked numeric claim in an ISSUE COMMENT is blocked",
        ),
        Mutation(
            # THE OTHER HALF, and the one that keeps the guard alive: a hook that blocked every
            # `gh pr create` would be switched off within a day, and then nothing is checked at all.
            "every body is blocked, verified or not",
            'if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "1" ]; then',
            'if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "unreachable" ]; then',
            "guard-claims: RAILS_FLOW_CLAIMS_OK=1 overrides, and says so",
        ),
    ),
)
