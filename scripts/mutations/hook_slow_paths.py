"""Mutation guard: hook_slow_paths. Run by scripts/mutation_check.py (#1575, #1570)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_slow_paths",
    subject="scripts/hook_slow_paths.py",
    selftest="scripts/hook_slow_paths.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # THE REASON THE SCRIPT EXISTS. Killing only the parent bash left its awk child computing for
            # 51 minutes; the selftest's hung stub forks a sleeper and must see it dead.
            "the deadline kills only the parent, so its child is orphaned and keeps running",
            "        os.killpg(proc.pid, signal.SIGKILL)",
            "        proc.kill()",
            "no orphaned child survives",
        ),
        Mutation(
            "an over-bound case that is not marked known-slow stops being a failure",
            "    if over and not case.known_slow:",
            "    if False:",
            "over the bound is a failure",
        ),
        Mutation(
            # THE OTHER DIRECTION: a fixed defect with its marker left behind would never be noticed
            # coming back, because the case would stay exempt for good.
            "a known-slow case that got fast stops being a failure, so a stale marker lives forever",
            "    if case.known_slow and not over:",
            "    if False:",
            "stale marker",
        ),
        Mutation(
            "a wrong exit status stops being a failure",
            "    if rc != \"TIMEOUT\" and rc != case.expected_rc:",
            "    if False:",
            "wrong verdict",
        ),
    ),
)
