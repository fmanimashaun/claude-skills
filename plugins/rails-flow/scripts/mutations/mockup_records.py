"""Mutation guard: mockup_records (#2226). Declared here, run by scripts/mutation_check.py.

The reader and the audit are tested through check_mockup_gate.py's selftest, which is the one that drives them; each mutation lets a design
that shipped with no Story through, or fails one that should not fail.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="mockup_records",
    subject="scripts/mockup_records.py",
    selftest="scripts/check_mockup_gate.py",
    selftest_args=("--selftest",),     # the selftest is a different script from the subject
    needs=("scripts/fixture_git.py", "scripts/classify_door.py", "commands/setup-flow.md", "reference/mockup-vocabulary.json"),
    mutations=(
        Mutation(
            'a record with a Story is audited as unlinked',
            '        if fields.get("Story"):\n            judged += 1\n            continue',
            '        if False:\n            judged += 1\n            continue',
            'the same record with a Story passes',
        ),
        Mutation(
            'a legacy record fails the audit',
            '        if not fields.get("Template"):\n            legacy.append(rel)\n            continue',
            '        if False:\n            legacy.append(rel)\n            continue',
            'a LEGACY record (no Template) without a Story is listed, never failed',
        ),
        Mutation(
            'an open issue fails the audit',
            '        elif verdict == "CLOSED":',
            '        elif True:',
            'an OPEN issue means it is not built yet',
        ),
        Mutation(
            'an unreadable issue passes the audit',
            '        if verdict is None:\n            unjudged.append(',
            '        if False:\n            unjudged.append(',
            'an issue gh cannot read is UNJUDGED',
        ),
        Mutation(
            'an unjudged record is no verdict',
            '    return (1 if failing else 2 if unjudged else 0), lines',
            '    return (1 if failing else 0), lines',
            'an issue gh cannot read is UNJUDGED',
        ),
        Mutation(
            'an unjudged record outranks a failure',
            '    return (1 if failing else 2 if unjudged else 0), lines',
            '    return (2 if unjudged else 1 if failing else 0), lines',
            'a failure outranks an unjudged record',
        ),
        Mutation(
            'the README and the shell are audited as screens',
            '        if rel == SHELL_RECORD or path.name.lower() == "readme.md":',
            '        if False:',
            'the README and the shell record are not screens',
        ),
        Mutation(
            'an issue URL is never read',
            'else (issue if ISSUE_REF.match(issue) else "")',
            'else ""',
            'an issue given as a URL is read too',
        ),
        Mutation(
            'any gh output is a state',
            '    return out if r.returncode == 0 and out in ("OPEN", "CLOSED") else None',
            '    return out if r.returncode == 0 else None',
            'the issue lookup reads a banner that is not a state',
        ),
        Mutation(
            'a failing gh still answers',
            '    return out if r.returncode == 0 and out in ("OPEN", "CLOSED") else None',
            '    return out if out in ("OPEN", "CLOSED") else None',
            'the issue lookup reads a failing gh',
        ),
    ),
)
