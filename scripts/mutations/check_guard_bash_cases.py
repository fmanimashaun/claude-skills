"""Mutation guard: check_guard_bash_cases (the runner). Declared here, run by scripts/mutation_check.py (#1667).

The runner is what turns a table of expectations into a gate, so each way it can go quiet is a mutation: the stub
log never read, the stub not first on PATH, an open row that changes accepted, a deadline judged as a verdict,
and each check the table's own validator makes. The selftest drives a fake hook, so a mutant costs about a second.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_guard_bash_cases",
    subject="scripts/check_guard_bash_cases.py",
    selftest="scripts/check_guard_bash_cases.py",
    selftest_args=("--selftest",),
    deps=("scripts/guard_bash_cases.py",),
    mutations=(
        Mutation(
            "the stub log is never read, so a case whose command ran passes",
            "        called = env.log.read_bytes()\n        if called:",
            '        called = b""\n        if called:',
            "a case whose command RAN (the stub was called) fails on the log",
        ),
        Mutation(
            "the stub is last on PATH, so a command that runs `gh` reaches whatever is installed instead of the stub",
            'return os.pathsep.join([str(self._stub), "/usr/bin", "/bin", self._tail])',
            'return os.pathsep.join(["/usr/bin", "/bin", self._tail, str(self._stub)])',
            "a case whose command RAN (the stub was called) fails on the log",
        ),
        Mutation(
            "an open row that changes is accepted, so #1656's progress is never recorded",
            "    if got == case.want:\n        return None\n    if case.open:",
            "    if got == case.want or case.open:\n        return None\n    if case.open:",
            "an open row that CHANGES fails, and says to update the expectation",
        ),
        Mutation(
            "a block case that is allowed is read as a block",
            '    got = "block" if rc == 2 else "allow"',
            '    got = "block"',
            "a block case the guard allows is a BYPASS",
        ),
        Mutation(
            "a deadline is judged as a verdict without the retry",
            "            if rc == 2 and DEADLINE_TEXT in why:         # load, not a verdict: once more, alone (#1664)",
            "            if False:         # load, not a verdict: once more, alone (#1664)",
            "a deadline that clears on the retry is judged on the retry",
        ),
        Mutation(
            "a block case that hit the deadline is reported as not a verdict",
            '                if rc == 2 and DEADLINE_TEXT in why and case.want == "allow":',
            "                if rc == 2 and DEADLINE_TEXT in why:",
            "...while a block case that hit the deadline is still a block",
        ),
        Mutation(
            "a duplicate case id is accepted",
            "    problems += [f\"duplicate id {i!r}\" for i in sorted({i for i in ids if ids.count(i) > 1})]",
            "    problems += []",
            "a duplicate id is refused",
        ),
        Mutation(
            "an expectation that is neither block nor allow is accepted",
            '        if c.want not in ("block", "allow"):',
            "        if False:",
            "a want that is neither block nor allow is refused",
        ),
        Mutation(
            "an open group needs no case in the fast tier",
            "        if not any(c.open == why and c.tier == \"fast\" for c in cases):",
            "        if False:",
            "an open group with no fast case is refused",
        ),
        Mutation(
            "the fast tier may be any size",
            "    if not FAST_RANGE[0] <= len(fast) <= FAST_RANGE[1]:",
            "    if False:",
            "a fast tier of 5 is refused",
        ),
        Mutation(
            "a case may name a fixture the table never builds",
            "            if ref not in names:",
            "            if False:",
            "a case naming a fixture the table does not build is refused",
        ),
    ),
)
