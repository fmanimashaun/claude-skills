"""Mutation guard: check_case_in_diff. Declared here, run by scripts/mutation_check.py (#1858).

Each mutation lets a change that closes an issue pass without the case that proves it, or without the spec a fix needs, or turns a check that could not be made into a pass.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_case_in_diff",
    subject="scripts/check_case_in_diff.py",
    selftest="scripts/check_case_in_diff.py",   # --selftest lives in the module itself
    narrow_with="--match",                      # each mutant runs only the row its `expects` names (#1599)
    # the subject imports check_registry_closed (closing keywords), and its selftest builds throwaway repositories with fixture_git (#1588)
    needs=("scripts/check_registry_closed.py", "scripts/fixture_git.py"),
    mutations=(
        Mutation(
            'a fix whose diff adds no case passes',
            '        if not any(names_issue(row, number) for row in rows):',
            '        if False:',
            'a fix whose diff adds no case is a finding',
        ),
        Mutation(
            'an issue number is matched as a prefix, so #55 names #5',
            're.fullmatch(rf"(?:[A-Za-z]+:)?#{number}", token.strip("()[]\\"\'`."))',
            're.match(rf"(?:[A-Za-z]+:)?#{number}", token.strip("()[]\\"\'`."))',
            '#55 is not #5',
        ),
        Mutation(
            'only the first closed issue needs a case',
            '    for number in sorted(closes):',
            '    for number in sorted(closes)[:1]:',
            'every closed issue needs its own case',
        ),
        Mutation(
            'the catalogue is parsed line by line, so a quoted field that spans lines forges a row',
            '        return list(csv.DictReader(io.StringIO(done.stdout.lstrip("\\ufeff"))))',
            '        return [dict(zip(next(csv.reader([done.stdout.splitlines()[0]])), next(csv.reader([ln])))) for ln in done.stdout.splitlines()[1:]]',
            'a multi-line quoted field cannot forge a Source',
        ),
        Mutation(
            'every row at HEAD counts as changed, so an untouched or moved row satisfies the rule',
            '        return [r for r in rows_at(root, "HEAD", catalogue) if fingerprint(r) not in before], None',
            '        return rows_at(root, "HEAD", catalogue), None',
            'a row that already named the issue at the base and is untouched does not count',
        ),
        Mutation(
            'a test or spec directory is not recognised',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'TEST_FILE = re.compile(r"(?:_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'a test/ directory file is a spec',
        ),
        Mutation(
            'an e2e directory is not recognised',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests)/|_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'an e2e/ directory file is a spec',
        ),
        Mutation(
            'a _spec file name is not recognised',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|\\.spec\\.|\\.test\\.|_test\\.)")',
            'a _spec file is a spec',
        ),
        Mutation(
            'any path containing spec is a spec',
            'TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|_spec\\.|\\.spec\\.|\\.test\\.|_test\\.)")',
            'TEST_FILE = re.compile(r"spec")',
            'a source file named specification is not a spec (near miss)',
        ),
        Mutation(
            'a note under a test directory counts as a spec (N2)',
            'TEST_FILE.search(p) and CODE.search(p)',
            'TEST_FILE.search(p)',
            'a note under a test directory is not a spec',
        ),
        Mutation(
            'a deleted spec counts as a spec this change brings (N1)',
            '"--name-only", "--diff-filter=ACMR", f"{base}...HEAD")',
            '"--name-only", f"{base}...HEAD")',
            'a deleted spec is not a spec this change brings',
        ),
        Mutation(
            "a feature is held to the fix's spec rule",
            '    if kind == "fix":',
            '    if True:',
            'a feature needs the case but not a spec file',
        ),
        Mutation(
            'the red/green section is not required of a fix',
            '        if body is not None and not red_green(body):',
            '        if False:',
            'a fix body with no red/green section is a finding',
        ),
        Mutation(
            'a red/green section needs only one of the two words',
            '    return bool(re.search(r"\\bred\\b", rest, re.I)) and bool(re.search(r"\\bgreen\\b", rest, re.I))',
            '    return bool(re.search(r"\\bred\\b", rest, re.I)) or bool(re.search(r"\\bgreen\\b", rest, re.I))',
            'a red/green section that never says green is a finding',
        ),
        Mutation(
            'a change that closes no issue is a finding',
            '    if not closes:\n        return 0,',
            '    if not closes:\n        return 1,',
            'a change that closes no issue needs no case',
        ),
        Mutation(
            'no catalogue is a pass instead of not applicable',
            '        return 3, [], [f"{catalogue}: no catalogue here',
            '        return 0, [], [f"{catalogue}: no catalogue here',
            'the default catalogue absent everywhere is still exit 3',
        ),
        Mutation(
            'a removed or moved catalogue reads as a pass',
            '        return 1, [f"{catalogue} exists at {base} but not in this change',
            '        return 0, [f"{catalogue} exists at {base} but not in this change',
            'a catalogue renamed in this change is a finding',
        ),
        Mutation(
            'a removed or moved catalogue is not looked for',
            '    if not at_head:\n',
            '    if False:\n',
            'a catalogue renamed in this change is a finding',
        ),
        Mutation(
            'an explicitly named catalogue that exists nowhere reads as no catalogue (N3)',
            '        if explicit:\n',
            '        if False:\n',
            'a catalogue named with --catalogue that exists nowhere is exit 2',
        ),
        Mutation(
            "the catalogue's existence is read from the working tree (N4)",
            '    at_head, at_base = exists_at(root, "HEAD", catalogue), exists_at(root, base, catalogue)',
            '    at_head, at_base = (root / catalogue).is_file(), exists_at(root, base, catalogue)',
            'a catalogue that exists only in the working tree is not read',
        ),
        Mutation(
            'existence at a ref is read from the working tree (N4)',
            '    return git(root, "cat-file", "-e", f"{ref}:{path}").returncode == 0',
            '    return (root / path).is_file()',
            'a catalogue deleted in the commit but still in the working tree is still a removal',
        ),
        Mutation(
            'an unreadable base is a pass',
            '        return 2, [], [f"the base {base} cannot be read',
            '        return 0, [], [f"the base {base} cannot be read',
            'an unreadable base is exit 2',
        ),
        Mutation(
            'an unreadable base is graded not applicable',
            '        return 2, [], [f"the base {base} cannot be read',
            '        return 3, [], [f"the base {base} cannot be read',
            'an unreadable base is exit 2',
        ),
        Mutation(
            'a row is the same row only when the WHOLE record is unchanged, so a header-only change counts every old row as changed',
            '    return (repr(row.get("Test ID")), repr(" ".join((row.get("Source") or "").split())))',
            '    return tuple(sorted((str(key), repr(value)) for key, value in row.items()))',
            'a header-only change (a new column) cannot make an old row that already names the issue satisfy the rule',
        ),
        Mutation(
            'a Source is compared with its whitespace, so a cosmetic edit counts as a change',
            '    return (repr(row.get("Test ID")), repr(" ".join((row.get("Source") or "").split())))',
            '    return (repr(row.get("Test ID")), repr(row.get("Source") or ""))',
            'whitespace in a Source is not a change',
        ),
        Mutation(
            'a Notes edit counts as a change (the row is compared by its Title too)',
            '    return (repr(row.get("Test ID")), repr(" ".join((row.get("Source") or "").split())))',
            '    return (repr(row.get("Test ID")), repr(row.get("Notes")), repr(" ".join((row.get("Source") or "").split())))',
            'a cosmetic edit (Notes) to a row that already names the issue is not a change',
        ),
    ),
)
