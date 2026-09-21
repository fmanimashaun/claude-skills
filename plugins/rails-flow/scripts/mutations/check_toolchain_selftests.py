"""Mutation guard: check_toolchain_selftests. Run by scripts/mutation_check.py (#1109)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_toolchain_selftests",
    subject="scripts/check_toolchain_selftests.py",
    selftest="scripts/check_toolchain_selftests.py",
    mutations=(
        Mutation(
            # The whole point. A shipped gate that has rotted against the project's framework or
            # Python version must be reported, or the project reads its silence as health.
            "a failing selftest stops being reported",
            "        if not ok:",
            "        if False:",
            "a FAILING selftest is reported",
        ),
        Mutation(
            # THE DISTINCTION THAT KEEPS IT USABLE. "The gate is broken here" is not "your code is
            # wrong"; collapsing them makes a team chase their own code, or ignore the gate. Same
            # defect as #1097's timeout-reported-as-FAIL, one level out.
            "the finding stops saying the GATE is broken rather than the project's code",
            '                f"this project, which is not the same as your code being wrong: it may have rotted "',
            '                f"this project. "',
            "says the gate is broken here, not that the project's code is wrong",
        ),
        Mutation(
            # A check nobody proved must be counted, not silently accepted -- that is the vacuous
            # pass this whole file exists to refuse.
            "a shipped check with no selftest is silently accepted",
            "        if not supports_selftest(path):",
            "        if False:",
            "a check with no selftest is counted as unproven, not as a pass",
        ),
        Mutation(
            # A manifest naming a script that is not there means the gate never ran at all, and
            # "0 findings" over a gate that never ran is the flattering reading.
            "a manifest naming a missing script stops being a finding",
            "        if not path.is_file():",
            "        if False:",
            "a manifest naming a missing script is a finding",
        ),
    ),
)
