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
            'a CSV row is split on commas, so a quoted Source is cut',
            '            values = next(csv.reader(io.StringIO(line[1:])))',
            '            values = line[1:].split(",")',
            'a quoted Source with a comma is read as one field',
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
            'a docs file named spec is not a spec',
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
            'no catalogue is exit 3',
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
    ),
)
