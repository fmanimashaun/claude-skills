"""Mutation guard: check_brakeman. Declared here, run by scripts/mutation_check.py (#2223).

Every mutation here lets Brakeman's silence, or its absence, read as a clean bill: the one failure a wrapper around another tool can have.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_brakeman",
    subject="scripts/check_brakeman.py",
    selftest="scripts/check_brakeman.py",
    mutations=(
        Mutation(
            "a warning in the report is not counted, so cross-site scripting reads as clean",
            '    for w in report.get("warnings", []):',
            "    for w in []:",
            "a warning (cross-site scripting in a view) is a finding",
        ),
        Mutation(
            "a Brakeman error is not counted",
            '    for e in report.get("errors", []):',
            "    for e in []:",
            "a Brakeman error is a finding too",
        ),
        Mutation(
            "a missing Brakeman is a clean pass instead of a failure to run",
            '        return 2, ["brakeman is not installed for this project',
            '        return 0, ["brakeman is not installed for this project',
            "no Brakeman anywhere is a failure to run, never a skip",
        ),
        Mutation(
            "output that is not JSON is read as clean",
            '        return 2, [f"brakeman gave no JSON report',
            '        return 0, [f"brakeman gave no JSON report',
            "output that is not JSON is a failure to run, not a clean pass",
        ),
        Mutation(
            "a crash with no report is read as clean",
            '        return 2, [f"brakeman could not run',
            '        return 0, [f"brakeman could not run',
            "a crash with no report is a failure to run",
        ),
        Mutation(
            "a JSON report that is not an object is read as clean",
            '        return 2, ["brakeman\'s JSON report is not an object"]',
            '        return 0, ["brakeman\'s JSON report is not an object"]',
            "a JSON report that is not an object is a failure to run",
        ),
        Mutation(
            "the Gemfile route runs a bare brakeman instead of bundle exec",
            '        return ["bundle", "exec", "brakeman"]',
            '        return ["brakeman"]',
            "a Gemfile that names brakeman runs `bundle exec brakeman`",
        ),
        Mutation(
            "the project's own bin/brakeman is no longer preferred",
            '    if binstub.is_file() and os.access(binstub, os.X_OK):',
            "    if False:",
            "the project's own bin/brakeman is preferred over bundle exec",
        ),
    ),
)
