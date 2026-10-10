"""Mutation guard: asset_home. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1779. An old place must stop every script and command that would misread it; --migrate must move all three whole, never merge, and rewrite only OUR paths.
    name="asset_home",
    subject="scripts/asset_home.py",
    selftest="scripts/asset_home.py",   # --selftest lives in the module
    needs=(),                            # a leaf: stdlib only, every fixture builds its own tempdir project
    mutations=(
        Mutation(
            'a library at the old place is no longer seen, so any content there goes unnoticed',
            '    return [(old, new) for old, new in MOVES if _has_content(root / old)]',
            '    return []',
            'ANY content at docs/assets/ counts, not only the known files',
        ),
        Mutation(
            'an empty old directory counts as a library to move',
            '        return any(path.iterdir())',
            '        return True',
            'an EMPTY old directory is not a library to move',
        ),
        Mutation(
            'the prompts move is no longer refused',
            '    (Path("docs/design-system/prompts"), Path("docs/design/prompts")),\n',
            '',
            'prompts at docs/design-system/prompts/ are refused too',
        ),
        Mutation(
            'the brand-logos move is no longer refused',
            '    (Path("docs/design-system/brand-assets"), BRAND),\n',
            '',
            'brand logos at docs/design-system/brand-assets/ are refused too',
        ),
        Mutation(
            '--migrate reports success when a destination blocked a move',
            '    return (1 if left else 0), said',
            '    return 0, said',
            '--migrate refuses to merge two libraries',
        ),
        Mutation(
            '--migrate leaves the old paths inside the moved files',
            '                new_text = pattern.sub(replacement, new_text)',
            '                pass',
            '...rewriting the old path inside the manifest',
        ),
        Mutation(
            'the path rewrite is not anchored, so mydocs/assets/ is rewritten too',
            'REWRITES = tuple((re.compile(r"(?<![\\w/.-])" + re.escape(',
            'REWRITES = tuple((re.compile(r"" + re.escape(',
            '...but not a path that merely ENDS like ours (mydocs/assets/)',
        ),
        Mutation(
            '--migrate reports success without moving anything',
            '        shutil.move(str(src), str(dst))',
            '        pass',
            '...moving the library',
        ),
        Mutation(
            '--migrate leaves the emptied docs/design-system/ behind',
            '        parent.rmdir()                         # the two moves emptied it',
            '        pass',
            '...removing the docs/design-system/ it emptied',
        ),
        Mutation(
            'a file at an old path is ignored',
            '    return path.exists() or path.is_symlink()',
            '    return False',
            'a FILE at an old path counts as something there',
        ),
        Mutation(
            'the brand/ collision is not named after the move',
            '            if new.parent in arrived:',
            '            if False:',
            '...and names the brand/ collision in the NOT moved text',
        ),
        Mutation(
            'the brand/ collision is not warned about before the move',
            '        elif new == BRAND and _has_content(root / LEGACY / BRAND.name):',
            '        elif False:',
            'a library holding its own brand/ is warned about BEFORE the move, naming the collision',
        ),
    ),
)
