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
    deps=("scripts/mutation_check.py", "scripts/mutation_types.py", "scripts/proc_group.py", "plugins/rails-flow/scripts/process_containment.py",),
    mutations=(
        Mutation(
            "a caller's GIT_CONFIG pairs are overwritten",
            '    start = int(count) if count else 0',
            '    start = 0',
            "#1510: hermetic_git.env must append after a caller's GIT_CONFIG pairs",
        ),
        Mutation(
            'a negative count is accepted, so our keys land at KEY_-1 where git drops them',
            '    if count and not (count.isascii() and count.isdigit()):',
            '    if count and not count.lstrip("-").isdigit():',
            '#1510: a count git rejects',
        ),
        Mutation(
            "Python's int() rules: ' 2 ' and '٣' read as counts",
            '    if count and not (count.isascii() and count.isdigit()):',
            '    if count and not (count.strip().isdigit()):',
            '#1510: a count git rejects',
        ),
        Mutation(
            'auto-maintenance is left on',
            'SETTINGS: tuple[tuple[str, str], ...] = (("maintenance.auto", "false"), ("gc.auto", "0"))',
            'SETTINGS: tuple[tuple[str, str], ...] = (("core.quotePath", "true"), ("core.safecrlf", "false"))',
            '#1510: the baseline and the mutant must run with git maintenance off',
        ),
        Mutation(
            # #1588
            'an inherited GIT_DIR survives hermetic_git.env, so a fixture commit lands in the real repo (#1588)',
            '    out = {k: v for k, v in (os.environ if base is None else base).items() if k not in REPO_LOCATORS}',
            '    out = dict(os.environ if base is None else base)',
            '#1588: hermetic_git.env must drop the repository-locating variables',
        ),
    ),
)
