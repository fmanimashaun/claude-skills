"""Mutation guard: guard_bash_cases (the table). Declared here, run by scripts/mutation_check.py (#1667).

The runner is guarded by its own file; this guards the DATA. A flipped expectation must be noticed by the fast tier
run against the real hook, which is the claim the table makes: each row says what `guard-bash.sh` does today. One
mutation per kind of row: a block, an allow control, an open row, and a fixture a script case reads.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="guard_bash_cases_data",
    subject="scripts/guard_bash_cases.py",
    selftest="scripts/check_guard_bash_cases.py",
    selftest_args=("--tier", "fast", "--jobs", "2"),
    # Each mutant runs only the row it broke (`--match <its expects>`), after a control run of the unmutated table with the
    # same flag: one real-hook run per mutant, not the whole fast tier (#1599).
    narrow_with="--match",
    # The fast tier drives the real hook, which runs its helper and reads the declared groups.
    needs=("plugins/rails-flow/hooks/scripts",),
    mutations=(
        Mutation(
            "a case the guard blocks is recorded as allowed",
            "('direct:env prefix', 'fast', 'full', 'env @G@ @I@ @C@ -t x -b y', 'block', '')",
            "('direct:env prefix', 'fast', 'full', 'env @G@ @I@ @C@ -t x -b y', 'allow', '')",
            "direct:env prefix",
        ),
        Mutation(
            "a labelled control is recorded as blocked",
            "('ctl:labelled create', 'fast', 'full', '@G@ @I@ @C@ -t x -b y -l comp:a -l type:b -l prio:c', 'allow', '')",
            "('ctl:labelled create', 'fast', 'full', '@G@ @I@ @C@ -t x -b y -l comp:a -l type:b -l prio:c', 'block', '')",
            "ctl:labelled create",
        ),
        Mutation(
            "an open row is recorded as already blocked, as if #1656 had landed",
            "('direct:eval var', 'fast', 'full', 'C=\\'@G@ @I@ @C@ -t x\\'; eval \"$C\"', 'allow',",
            "('direct:eval var', 'fast', 'full', 'C=\\'@G@ @I@ @C@ -t x\\'; eval \"$C\"', 'block',",
            "direct:eval var",
        ),
        Mutation(
            "the script a case reads no longer holds a create",
            "    'bare.sh': 'gh issue create -t x -b y\\n',",
            "    'bare.sh': 'echo nothing here\\n',",
            "script:bash f",
        ),
    ),
)
