"""Mutation guard: session_reaper. Declared here, run by scripts/mutation_check.py (#866).

#1582 slice C. The SessionEnd reaper kills only a session's OWN processes, found by the id in their environment,
and only the ones that are both orphaned and stopped. Each mutation widens or breaks one of those and must be
caught by the fixture that holds the process it would wrongly touch (or miss).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="session_reaper",
    subject="scripts/session_reaper.py",
    selftest="scripts/session_reaper.py",
    selftest_args=("--selftest",),
    needs=("scripts/process_containment.py",),      # imported by the subject
    mutations=(
        Mutation(
            "a RUNNING orphan is reaped too, so a server the session meant to leave is killed",
            'parts[2].startswith("T")',
            "True",
            "survives: this session's RUNNING orphan",
        ),
        Mutation(
            "a stopped process that still has a parent is reaped, so a debugger's target dies under it",
            'parts[1] == "1" and ',
            "",
            "survives: this session's stopped process that still has a parent",
        ),
        Mutation(
            "the id is not validated, so an empty id reaches the environment scan",
            'if not _ID.match(session_id or ""):',
            "if False:",
            "an empty id reaps nothing, even beside a process holding an empty id",
        ),
        Mutation(
            "no KILL after TERM, so an orphan that ignores SIGTERM stays",
            "    for pid in set(holding(SESSION_VAR, session_id)) & set(targets):    # still there after TERM, and still ours\n        try:\n            os.kill(pid, signal.SIGKILL)",
            "    for pid in set():\n        try:\n            os.kill(pid, signal.SIGKILL)",
            "an orphan that IGNORES SIGTERM is killed too",
        ),
        Mutation(
            "another session's orphan is reaped because the id is read from this process's own environment",
            'pids = holding(SESSION_VAR, session_id)',
            'pids = holding(SESSION_VAR, os.environ.get(SESSION_VAR, session_id))',
            "finds exactly the session's stopped orphan, by environment",
        ),
    ),
)
