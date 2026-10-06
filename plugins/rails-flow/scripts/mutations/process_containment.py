"""Mutation guard: process_containment. Declared here, run by scripts/mutation_check.py (#866).

#1582. The helper that keeps a process fixture from outliving itself: every process started inside
`contained()` inherits a token, and the teardown kills every process carrying it. Each mutation breaks
one half of that promise and must be caught by the selftest's leaking fixture (a stopped child and an
orphaned new-session grandchild -- the shape of the 2026-10-03 leak).
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="process_containment",
    subject="scripts/process_containment.py",
    selftest="scripts/process_containment.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "contained() never sweeps, so a leaking fixture's processes outlive it",
            "        box.killed = sweep(token)",
            "        box.killed = []",
            "under contained(), a leaking fixture leaves NOTHING behind",
        ),
        Mutation(
            "the sweep freezes but never kills, so the tree is left STOPPED -- the incident itself",
            '        _signal(pid, signal.SIGKILL)\n    # REAP ONLY WHAT WE KILLED',
            '        pass\n    # REAP ONLY WHAT WE KILLED',
            "under contained(), a leaking fixture leaves NOTHING behind",
        ),
        Mutation(
            "children are not tagged, so the sweep finds nothing to kill",
            "    os.environ[TOKEN_VAR] = token\n    try:",
            "    try:",
            "a leaking fixture's processes are tagged while it runs",
        ),
        Mutation(
            "the token is left in the environment after the block",
            "        if saved is None:\n            os.environ.pop(TOKEN_VAR, None)",
            "        if saved is None:\n            pass",
            "contained() restores the environment",
        ),
        Mutation(
            "the CLI reports success whatever the command returned",
            "    return rc\n",
            "    return 0\n",
            "the CLI returns the command's own exit status",
        ),
        Mutation(
            # #1589 F2
            "the sweep reaps any child again, stealing a caller's other child's exit status (#1589 review F2)",
            '                done, _ = os.waitpid(pid, os.WNOHANG)',
            '                done, _ = os.waitpid(-1, os.WNOHANG)',
            "the sweep leaves a caller's OTHER child alone",
        ),
        Mutation(
            # #1589 F3
            'the CLI ignores SIGTERM and SIGHUP again, so its teardown never runs (#1589 review F3)',
            '    for sig in (signal.SIGTERM, signal.SIGHUP):\n        signal.signal(sig, _raise_on)\n',
            '',
            "a SIGTERM to the CLI still kills the command's tree",
        ),
        Mutation(
            # #1582 slice B, #1589 re-review S1
            "the sweep is no longer shielded from a second signal, so one landing mid-sweep aborts it (#1589 re-review S1)",
            "        with _deferred_signals():\n            box.killed = sweep(token)\n",
            "        box.killed = sweep(token)\n",
            "does not abort the sweep",
        ),
    ),
)
