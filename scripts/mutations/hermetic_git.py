"""Mutation guard: hermetic_git. Declared here, run by scripts/mutation_check.py (#866).

#1510. The env every runner subprocess gets. Its selftest is mutation_check's, which drives it through
run_guard (a fixture that refuses to go on if a traced commit starts git maintenance) and checks that it
appends to a caller's own GIT_CONFIG pairs.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hermetic_git",
    subject="scripts/hermetic_git.py",
    selftest="scripts/mutation_check_selftest.py",
    deps=("scripts/mutation_check.py", "scripts/mutation_types.py"),
    mutations=(
        Mutation(
            "a caller's GIT_CONFIG pairs are overwritten",
            '        start = int(out.get("GIT_CONFIG_COUNT", "0") or 0)',
            '        start = 0',
            "#1510: hermetic_git.env must append after a caller's GIT_CONFIG pairs",
        ),
        Mutation(
            'auto-maintenance is left on',
            'SETTINGS: tuple[tuple[str, str], ...] = (("maintenance.auto", "false"), ("gc.auto", "0"))',
            'SETTINGS: tuple[tuple[str, str], ...] = (("core.quotePath", "true"), ("core.safecrlf", "false"))',
            '#1510: the baseline and the mutant must run with git maintenance off',
        ),
    ),
)
