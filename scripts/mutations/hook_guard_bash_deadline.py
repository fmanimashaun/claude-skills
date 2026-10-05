"""Mutation guard: hook_guard_bash_deadline. The deadline block at the bottom of guard-bash.sh. Run by scripts/mutation_check.py (#1575)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_bash_deadline",
    subject="plugins/rails-flow/hooks/scripts/guard-bash.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the deadline fixtures drive this subject; the whole harness per mutant is ~90 CPU-seconds.
    selftest_args=("--only", "deadline"),
    needs=("plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json",
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # release-gate.sh and guard-bash.sh run these; unstaged, the harness's other fixtures fail in the staged
           # tempdir and every mutation reads as caught for an environmental reason (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py"),
    mutations=(
        # A fail-closed gate: "took too long to read" must refuse, never allow.
        Mutation(
            'a timeout is no longer a denial, so a hung normaliser lets the command through',
            'if [ "$_rc" -ge 128 ]; then',
            'if false; then',
            'refuses a command its normaliser cannot read in time',
        ),
        # Past hooks.json's 10 s Claude Code stops waiting, so the deadline would never deny.
        Mutation(
            "the default and ceiling move above the hook's own timeout",
            'deadline_seconds 6 8',
            'deadline_seconds 12 20',
            "default and ceiling sit below the hook's configured timeout",
        ),
    ),
)
