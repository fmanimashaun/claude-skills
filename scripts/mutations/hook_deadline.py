"""Mutation guard: hook_deadline. The shared wall-clock deadline helper. Run by scripts/mutation_check.py (#1575)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_deadline",
    subject="plugins/rails-flow/hooks/scripts/lib/deadline.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the deadline fixtures drive this subject; the whole harness per mutant is ~90 CPU-seconds.
    selftest_args=("--only", "deadline"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json",
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # release-gate.sh and guard-bash.sh run these; unstaged, the harness's other fixtures fail in the staged
           # tempdir and every mutation reads as caught for an environmental reason (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        # THE REASON THE HELPER EXISTS: killing only the parent left awk computing for 51 minutes and, once, 23 hours.
        Mutation(
            "the deadline kills the child by pid only, so the stub's sleeper is orphaned",
            'kill -KILL -- "-$_child" 2>/dev/null',
            'kill -KILL "$_child" 2>/dev/null',
            'no process the hook started outlives it',
        ),
        # Claude Code SIGKILLs the hook at its own timeout; without the poll the child runs on until the deadline.
        Mutation(
            'the watchdog never notices its parent died, so an orphan runs to the full deadline',
            'kill -0 "$_parent" 2>/dev/null || break',
            ':',
            'the group dies within a poll of its PARENT being SIGKILLed',
        ),
        # A watchdog that cannot wait reaches the deadline instantly and would deny every command.
        Mutation(
            'the missing-sleep guard is gone, so a PATH without sleep fires the deadline at once',
            'if ! type -P sleep >/dev/null 2>&1; then',
            'if false; then',
            'with no `sleep` on PATH an ordinary command still passes',
        ),
        # The shell prints "Killed: 9 ..." on its own stderr and Claude reads stderr; measured: 91 bytes without this.
        Mutation(
            "the supervisor leaves fd 2 open, so bash's own job-control notice reaches Claude",
            'exec 9>&2 2>/dev/null',
            'exec 9>&2',
            'ONE line on stderr',
        ),
        # A deadline above the hook's timeout never gets to deny: Claude Code has stopped waiting.
        Mutation(
            "the ceiling is gone, so an env value can exceed the hook's own timeout",
            '[ "$_deadline_s" -gt "$2" ] && _deadline_s="$2"',
            ':',
            "the knob '99' with default 6 and ceiling 8 gives 8",
        ),
        # Only an integer >= 1 is a deadline; anything else falls back to the default.
        Mutation(
            'a non-integer or zero value is accepted, so the knob can disable the deadline',
            '\'\'|*[!0-9]*) _deadline_s="$1" ;;',
            '\'\') _deadline_s="$1" ;;',
            "the knob 'abc'",
        ),
        # #1602 review F2: 19+ digits overflow bash's integer comparison, the clamp never ran, and every command was denied.
        Mutation(
            'the length clamp is gone, so a value past 2^63 wraps negative and the deadline is not clamped',
            '[ "${#_deadline_s}" -gt 4 ] && _deadline_s="$2"',
            ':',
            "the knob '9223372036854775808'",
        ),
        # A zero deadline reaches the watchdog's deadline immediately.
        Mutation(
            'a zero deadline is accepted, so it fires at once and denies every command',
            '[ "$_deadline_s" -lt 1 ] && _deadline_s="$1"',
            ':',
            "the knob '00'",
        ),
    ),
)
