"""Mutation guard: toolchain_version. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="toolchain_version",
    subject="scripts/toolchain_version.py",
    selftest="scripts/toolchain_version_selftest.py",
    mutations=(
        Mutation(
            # Two records for one plugin coexist in the cache, ordered ONLY by lastUpdated.
            # Picking arbitrarily reports the stale one as installed, so an out-of-date
            # toolchain reads as current -- which is the single thing pillar 1 exists to catch.
            "the newest install record stops winning, so a stale version reads as installed",
            '    return max(records, key=lambda r: (r or {}).get("lastUpdated") or "")',
            "    return records[0]",
            "shadowed-record: newest wins",
        ),
        Mutation(
            "a plugin whose published version did not resolve is folded into 'up to date' again (#923)",
            '    if unresolved:\n        for n in unresolved:',
            '    if False:\n        for n in unresolved:',
            "unresolved-published",
        ),
        # #1407. THE MACHINE-WIDE MUTATION: every record applies to every project, which is the
        # old behaviour -- a project on an older version reads as current because another
        # project on the same machine updated later.
        Mutation(
            "install records stop being scoped to their project",
            '    owner = (record or {}).get("projectPath")\n    if not owner:\n        return True',
            '    owner = (record or {}).get("projectPath")\n    if True:\n        return True',
            "per-project: A resolves its own, older record",
        ),
        # main() must hand its --project to the resolver, or the helper is proven and the gate is not.
        Mutation(
            "main() resolves machine-wide, ignoring --project",
            "    installed, problems = resolve_installed(args.home, project=args.project)",
            "    installed, problems = resolve_installed(args.home)",
            "per-project: a project behind the machine's newest install is drift",
        ),
        Mutation(
            "--installed-path prints nothing and exits 0 when this project has no record",
            "        if not path:\n            for p in problems:",
            "        if False:\n            for p in problems:",
            "installed-path: no record for this project",
        ),
        # #1411 review S2/S3: the path comparison was untested; string equality passed 40/40.
        Mutation(
            "project paths compare as strings, so a symlinked or trailing-slash path misses",
            "        root, here = Path(owner).resolve(), main_checkout(project).resolve()",
            "        root, here = Path(owner), main_checkout(project)",
            "per-project: symlinked path is the same project",
        ),
        Mutation(
            "a subdirectory of the project is treated as another project",
            "    dirs = (here, *here.parents)",
            "    dirs = (here,)",
            "per-project: a subdirectory is the same project",
        ),
        Mutation(
            "a same-prefix sibling counts as inside the project",
            "    if root in dirs:\n        return True",
            "    if str(here).startswith(str(root)):\n        return True",
            "per-project: a same-prefix sibling is another project",
        ),
        # #1427: a linked worktree outside the root is its own "project" again, with no record.
        Mutation(
            "a linked worktree is not mapped to its main checkout",
            'return gitdir.parent.parent.parent if gitdir.parent.name == "worktrees" else project',
            "return project",
            "per-project: a linked worktree of A is A",
        ),
        # No mutation for the case-folding `samefile` branch: its fixture runs only on a volume that
        # folds case, and CI's Linux runner does not, so the mutant would survive there.
    ),
)
