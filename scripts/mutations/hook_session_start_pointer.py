"""Mutation guard: hook_session_start_pointer. Declared here, run by scripts/mutation_check.py (#1585, part 2b).

SessionStart fires again after every compaction, so what it prints is paid each time, and a hook that waits on its stdin
holds the start of every session. The pointer must print when it concerns the session and wait for nothing.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_session_start_pointer",
    subject="plugins/rails-flow/hooks/scripts/session-start.sh",
    selftest="plugins/rails-flow/hooks/scripts/lib/coordination.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            'the pointer is never called',
            '  printf \'%s\' "$_payload" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/lib/coordination.py" pointer --stdin 2>/dev/null || true',
            '  :',
            'session-start.sh prints ONE coordination line',
        ),
        Mutation(
            'the payload read waits for ever on an open stdin',
            "IFS= read -r -t 2 -d '' _payload",
            "IFS= read -r -d '' _payload",
            'an open stdin with no payload does not hold the hook',
        ),
    ),
)
