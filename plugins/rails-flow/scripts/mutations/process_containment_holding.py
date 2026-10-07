"""Mutation guard: process_containment_holding. Declared here, run by scripts/mutation_check.py (#866).

#1582 slice C. `holding()` reads a process's ENVIRONMENT, and The environment is read as SEPARATE entries (/proc, or sysctl kern.procargs2 on macOS) and compared whole, so neither an
argument nor another variable's value that spells the entry matches (#1646 R1). The fixture that needs a process with such an argument lives in the reaper's selftest, so this guard
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
            "entries are searched as joined text, so another variable's VALUE containing the entry matches (#1646 R1)",
            "needle in (environ_of(pid) or [])",
            "needle in b\" \".join(environ_of(pid) or [])",
            "survives: another session's orphan with a variable whose VALUE contains this session's entry",
        ),
        Mutation(
            "value_of accepts any entry that merely CONTAINS the variable's text, so a spoofed value is read as the id",
            "        if entry.startswith(prefix):",
            "        if prefix in entry:",
            "value_of reads the exact variable",
        ),
    ),
)
