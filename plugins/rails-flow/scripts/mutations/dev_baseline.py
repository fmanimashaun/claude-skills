"""Mutation guard: dev_baseline. Declared here, run by scripts/mutation_check.py (#1567)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="dev_baseline",
    subject="scripts/dev_baseline.py",
    selftest="scripts/dev_baseline.py",   # --selftest lives in the module
    # The selftest builds its temp repo through fixture_git (#1588), which the staged mutant must carry.
    deps=("scripts/fixture_git.py",),
    mutations=(
        Mutation(
            # THE WHOLE POINT OF THE BASELINE BEING A RATCHET: evidence about another commit is not evidence.
            "a baseline measured at any commit is trusted as fresh",
            "    if recorded == base:",
            "    if True:",
            "a baseline at a commit that is not the merge base is stale",
        ),
        Mutation(
            # An output we cannot read must not record "no failures": that would bless every later red as NEW and
            # every real baseline failure as a regression, or the reverse.
            "unreadable output records an empty baseline",
            '    if re.search(r"\\b\\d+ examples?, 0 failures?\\b", text):',
            "    if True:",
            "unreadable output is None, never an empty baseline",
        ),
        Mutation(
            "a description that mentions `rspec ./x` counts as a failed row",
            'FAILED_ROW = re.compile(r"^rspec (\\./\\S+)", re.MULTILINE)',
            'FAILED_ROW = re.compile(r"rspec (\\./\\S+)", re.MULTILINE)',
            "a description that mentions rspec is not a row",
        ),
        Mutation(
            "a json run records every example, passing ones too",
            '                if example.get("status") != "failed":',
            "                if False:",
            "a json run reads the failed examples only",
        ),
        Mutation(
            # #1567 review (1): a dev that fails to LOAD prints no failed examples, so it would read as clean.
            "a run with errors outside of examples reads as a clean baseline",
            "    if OUTSIDE_ERRORS.search(text):",
            "    if False:",
            "a run with errors outside of examples is unreadable, never an empty baseline",
        ),
        Mutation(
            "the json errors_outside_of_examples_count is ignored",
            '            return (data["summary"].get("errors_outside_of_examples_count") or 0) > 0',
            "            return False",
            "a json run with errors_outside_of_examples_count > 0 is unreadable",
        ),
        Mutation(
            # #1567 review (3): an unreadable changed-file set must not read as "the branch touched nothing".
            "an unreadable changed-file set reads as empty, so everything looks untouched",
            "    except RuntimeError:\n        return None\n    return {normalise",
            "    except RuntimeError:\n        return set()\n    return {normalise",
            "a ref that does not exist leaves the changed set unknown, not empty",
        ),
        Mutation(
            "the changed set leaves out uncommitted edits",
            '        names = git("diff", "--name-only", base, cwd=cwd)',
            '        names = git("diff", "--name-only", base + "..HEAD", cwd=cwd)',
            "the files this branch changed since the merge base are read, committed or not",
        ),
        Mutation(
            "record measures whatever is checked out, whatever ref it claims",
            "            if head != want:",
            "            if False:",
            "record refuses to measure a ref that is not checked out",
        ),
        Mutation(
            "check exits 0 on a stale baseline, so a script cannot tell",
            "    return 0 if fresh else 3",
            "    return 0",
            "check exits 3 on a stale baseline",
        ),
    ),
)
