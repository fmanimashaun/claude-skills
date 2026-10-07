"""Mutation guard: process_containment_holding. Declared here, run by scripts/mutation_check.py (#866).

#1582 slice C. `holding()` reads a process's ENVIRONMENT, and `ps -E` prints the command line and the environment as
one string, so an argument spelling `CLAUDE_CODE_SESSION_ID=<id>` looked like an environment entry. It strips the
command line first. The fixture that needs a process with such an argument lives in the reaper's selftest, so this guard
runs that selftest against `process_containment.py`.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="process_containment_holding",
    subject="scripts/process_containment.py",
    selftest="scripts/session_reaper.py",
    selftest_args=("--selftest",),
    needs=("scripts/session_reaper.py",),
    mutations=(
        Mutation(
            "the command line is not stripped, so an argument that spells the entry matches (a name-based kill by another route)",
            "env_part = line[len(argv):] if line.startswith(argv) else line",
            "env_part = line",
            "survives: a command line that only MENTIONS the id (not its environment)",
        ),
    ),
)
