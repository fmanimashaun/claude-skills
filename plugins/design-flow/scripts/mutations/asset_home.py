"""Mutation guard: asset_home. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1779. A library left at docs/assets/ must stop every entry point, never read as empty; --migrate must move it whole.
    name="asset_home",
    subject="scripts/asset_home.py",
    selftest="scripts/asset_home.py",   # --selftest lives in the module
    needs=(),                            # a leaf: stdlib only, every fixture builds its own tempdir project
    mutations=(
        Mutation(
            "a library at the old place is no longer seen, so it reads as empty",
            "    return [name for name in MARKERS if (root / LEGACY / name).exists()]",
            "    return []",
            "a library at the old place stops the script",
        ),
        Mutation(
            "--migrate merges into an existing library instead of refusing",
            '        return 1, refusal(root) or ""',
            '        return 0, ""',
            "--migrate refuses to merge two libraries",
        ),
        Mutation(
            "--migrate leaves the old path inside the moved files",
            '            new = text.replace(f"{LEGACY.as_posix()}/", f"{HOME.as_posix()}/")',
            "            new = text",
            "...rewriting the old path inside the manifest",
        ),
        Mutation(
            "--migrate reports success without moving anything",
            "    shutil.move(str(root / LEGACY), str(root / HOME))",
            "    pass",
            "...moving the library",
        ),
    ),
)
