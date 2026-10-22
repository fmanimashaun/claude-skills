"""Mutation guard: rf_tmp (#2306). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="rf_tmp",
    subject="scripts/rf_tmp.py",
    selftest="scripts/rf_tmp.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "the dirs are no longer removed at exit",
            "    atexit.register(_clean)",
            "    pass",
            "removed at a normal exit",
        ),
        Mutation(
            "a SIGTERM no longer removes the dirs",
            "def _on_signal(signum, _frame) -> None:\n    _clean()",
            "def _on_signal(signum, _frame) -> None:\n    pass",
            "removed on SIGTERM",
        ),
        Mutation(
            "a script's own SIGTERM handler is replaced",
            "            if signal.getsignal(sig) in (signal.SIG_DFL, None):",
            "            if True:",
            "a script's own SIGTERM handler is kept",
        ),
        Mutation(
            "the rf- name is dropped, so --fix cannot tell ours from another program's",
            "PREFIX = \"rf-\"",
            "PREFIX = \"\"",
            "removed at a normal exit",
        ),
    ),
)
