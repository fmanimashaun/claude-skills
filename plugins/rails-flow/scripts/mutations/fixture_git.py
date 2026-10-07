"""Mutation guard: fixture_git. Declared here, run by scripts/mutation_check.py (#866).

#1588 / #1577. The lock that keeps a fixture's git inside its own temp repo. Each mutation removes one
layer, and the selftest's stand-in "real" repo must catch it gaining a commit.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="fixture_git",
    subject="scripts/fixture_git.py",
    selftest="scripts/fixture_git.py",
    mutations=(
        Mutation(
            "an inherited GIT_DIR survives into the fixture's environment (the #1588 cause)",
            "    out = {k: v for k, v in (os.environ if base is None else base).items() if k not in REPO_LOCATORS}",
            "    out = dict(os.environ if base is None else base)",
            "an inherited GIT_DIR cannot redirect a fixture commit into the repo it names",
        ),
        Mutation(
            "a repo whose init failed is searched past instead of refused",
            '    if not dot.exists():\n        raise NotATempRepo(',
            '    if False:\n        raise NotATempRepo(',
            "a commit in a repo whose init failed is REFUSED",
        ),
        Mutation(
            "a path outside the temp root is accepted",
            "    if path == root or root not in path.parents:\n        raise NotATempRepo(",
            "    if False:\n        raise NotATempRepo(",
            "a path outside the temp root is refused",
        ),
        Mutation(
            "git is not bound to the temp repo, so it may discover another",
            '    out["GIT_DIR"] = str(path / ".git")\n',
            "",
            'a stray -C in the arguments cannot commit into another repo',
        ),
        Mutation(
            "the background-maintenance settings are dropped (#1577)",
            '    out["GIT_CONFIG_COUNT"] = str(start + len(SETTINGS))\n',
            "",
            "fixture git runs with maintenance.auto=false",
        ),
        Mutation(
            # #1594 S1
            'a .git gitlink or symlink pointing at another repo is followed (#1594 review S1)',
            '    if target != path and path not in target.parents:\n        raise NotATempRepo(',
            '    if False:\n        raise NotATempRepo(',
            'a .git gitlink file pointing at another repo is refused',
        ),
        Mutation(
            # #1594 S2
            'an explicit --git-dir/--work-tree in the arguments overrides the binding (#1594 review S2)',
            'GLOBAL_WITH_VALUE = ("-C", "-c", "--namespace", "--config-env", "--attr-source")',
            'GLOBAL_WITH_VALUE = ("-C", "-c", "--namespace", "--config-env", "--attr-source", "--git-dir", "--work-tree")',
            'an explicit --git-dir in the arguments is refused',
        ),
        Mutation(
            "an unknown leading option is let through, so `--config-env x=y --git-dir REAL` rebinds the repo (#1660 R2)",
            '        else:\n            raise NotATempRepo(f"{a!r} before the subcommand',
            '        elif False:\n            raise NotATempRepo(f"{a!r} before the subcommand',
            "a leading --config-env core.x=HOME ... is refused",
        ),
    ),
)
