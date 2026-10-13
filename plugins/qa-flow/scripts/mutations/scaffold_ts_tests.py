"""Mutation guard: scaffold_ts_tests. Declared here, run by scripts/mutation_check.py (#1979)."""
from mutation_types import Guard, Mutation  # noqa: F401

# `scaffold_ts_tests.py` decides pass or fail for the robot's TypeScript helper tests, and six guards lean on it as their selftest (scaffold_totp and the rest). Its OWN rules (a run with no tests is not a
# pass, a failing test is not a pass, the Node floor, the CI exit-1 rule) had rows in `--selftest` and nothing that proved a row could fail. The decisions are pure functions now, and `--selftest-only` runs
# their rows without Node, so this guard needs none and runs in the Linux container. Each mutation breaks ONE rule, and the row that names it must fail.
GUARD = Guard(
    name="scaffold_ts_tests",
    subject="scripts/scaffold_ts_tests.py",
    selftest="scripts/scaffold_ts_tests.py",
    selftest_args=("--selftest-only",),
    mutations=(
        Mutation(
            "a run that executed no tests counts as a pass",
            "and tests > 0 and fail == 0",
            "and fail == 0",
            "a run that executed no tests is a pass",
        ),
        Mutation(
            "a run with failing tests counts as a pass",
            "and tests > 0 and fail == 0",
            "and tests > 0",
            "a run with failing tests is a pass",
        ),
        Mutation(
            "a non-zero exit from the runner is ignored",
            "return returncode == 0 and tests is not None",
            "return tests is not None",
            "a non-zero exit from the runner is a pass",
        ),
        Mutation(
            "a footer that is not there is read as zero counts",
            "return int(m.group(1)) if m else None",
            "return int(m.group(1)) if m else 0",
            "summary invents counts for a run that printed no footer",
        ),
        Mutation(
            "the Node floor is lowered",
            "MIN_NODE = (22, 6)",
            "MIN_NODE = (20, 0)",
            "Node 22.5, below the type-stripping floor, is usable",
        ),
        Mutation(
            "the floor itself is too old",
            "return have is None or have < MIN_NODE",
            "return have is None or have <= MIN_NODE",
            "Node 22.6, the floor itself, is too old",
        ),
        Mutation(
            "a Node whose version cannot be read is usable",
            "return have is None or have < MIN_NODE",
            "return have is not None and have < MIN_NODE",
            "a Node whose version could not be read is usable",
        ),
        Mutation(
            "under CI a missing or old Node is a skip again",
            "return 1 if ci else 3",
            "return 3",
            "under CI, a missing or old Node is not exit 1",
        ),
        Mutation(
            "a blank CI value is treated as CI",
            'ci = bool(env.get("CI", "").strip())',
            'ci = bool(env.get("CI", ""))',
            "a blank CI value is treated as CI",
        ),
        Mutation(
            "an empty list of test files is not 'no tests'",
            "return not files",
            "return False",
            "an empty list of test files is not 'no tests'",
        ),
    ),
)
