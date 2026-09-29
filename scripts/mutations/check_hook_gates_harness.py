"""Mutation guard: check_hook_gates (the harness itself). Declared here, run by scripts/mutation_check.py (#1469).

The hook guards mutate the HOOKS and use check_hook_gates.py as their selftest; nothing mutated the
harness. #1469 was a harness defect: a subprocess timeout raised and crashed the suite, so fixtures
after it never printed, and under parallel load a mutation read as "caught by the wrong fixture".
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_hook_gates_harness",
    subject="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Staged exactly as hook_guard_bash stages it: the suite drives every plugin's hooks.
    needs=("plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            "an unexpected timeout is not recorded, so a setup step that times out passes silently",
            "            if not _EXPECTING_TIMEOUT:\n                check(note, False)",
            "            if False:\n                check(note, False)",
            "an UNEXPECTED timeout is recorded as a failure",
        ),
        Mutation(
            "a subprocess timeout raises again, crashing the suite before later fixtures print",
            "        except subprocess.TimeoutExpired:\n            try:\n                os.killpg(proc.pid, signal.SIGKILL)",
            "        except OSError:\n            try:\n                os.killpg(proc.pid, signal.SIGKILL)",
            "a timed-out hook fixture fails by name and the suite still finishes",
        ),
        Mutation(
            "the hook shares the suite's process group, so its stubs outlive a timeout",
            "    with subprocess.Popen(*args, start_new_session=True, **kw) as proc:",
            "    with subprocess.Popen(*args, **kw) as proc:",
            "returns promptly, because nothing it started still holds the output pipe",
        ),
        Mutation(
            "a timeout kills only the direct child, orphaning the stubs it started",
            "                os.killpg(proc.pid, signal.SIGKILL)",
            "                proc.kill()",
            "leaving no orphaned stub",
        ),
    ),
)
