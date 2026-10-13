"""Mutation guard: hook_release_gate_large. Declared here, run by scripts/mutation_check.py (#1952).

The release gate answers a LARGE command, and its degraded fallback answers at any size, within seconds: a hook the harness kills at 15 s lets
the command run, and bash 3.2's `${x//a/b}` passes are quadratic (2 KB took 2 s, 6 KB took 22 s). Each mutant undoes one rule; one fixture names it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_large",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "release_gate_large"),
    # The same staged tree as hook_release_gate: the harness drives the hook from its own location.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/wip_commit.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        Mutation(
            "a payload past _large_bytes enters the full path again, which took 8 s at 390 KB and gave no answer in 70 s at 683 KB",
            """if [ "${#input}" -gt "$_large_bytes" ]; then
  _coarse_looks_promotion
""",
            """if false; then
  _coarse_looks_promotion
""",
            "a 700 KB command with a push to main is refused within seconds",
        ),
        Mutation(
            "the fallback runs its quadratic precise rules on every size again, so a deadline turns a 100 KB command into minutes",
            """  if [ "${#input}" -gt "$_coarse_bytes" ]; then""",
            """  if false; then""",
            "a 700 KB command with a push to main is refused within seconds",     # on bash 5 (Linux) the 100 KB case is fast even with the precise rules; the 700 KB one is not, on either
        ),
        Mutation(
            "a command past the cap is judged by its words again (here: allowed), so a spelling the words miss passes",
            """    _looks_promotion=1      # cannot be read in time: refused, not guessed at""",
            """    _looks_promotion=0""",
            "a large command that names neither git nor gh is refused TOO",
        ),
        Mutation(
            "the oversize branch of the pre-gate allows instead of refusing, so a 700 KB push is let through",
            """if [ "$_looks_promotion" = "1" ]; then
    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: a ${#input}-byte""",
            """if [ "$_looks_promotion" = "9" ]; then
    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: a ${#input}-byte""",
            "a 700 KB command with a push to main is refused within seconds",
        ),
        Mutation(
            "QA_ALLOW_MAIN=1 is ignored for a large command",
            """    [ "${QA_ALLOW_MAIN:-0}" = "1" ] && { echo "qa-flow: a ${#input}-byte""",
            """    [ "0" = "1" ] && { echo "qa-flow: a ${#input}-byte""",
            "QA_ALLOW_MAIN=1 is honoured for a large command and audited",
        ),
    ),
)
