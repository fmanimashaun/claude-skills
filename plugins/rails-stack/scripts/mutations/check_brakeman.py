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
            "the ignored count is not printed, so a file that suppresses everything is silent",
            '    ignored_line = f"{len(ignored) if isinstance(ignored, list) else 0} ignored (config/brakeman.ignore)"',
            '    ignored_line = ""',
            "a report in which every warning is ignored passes, and says how many were ignored",
        ),
        Mutation(
            "a non-Rails project is a failure instead of not applicable",
            '        return 3, ["not a Rails project',
            '        return 2, ["not a Rails project',
            "a project with no config/application.rb is not applicable (exit 3), not a failure",
        ),
        Mutation(
            "brakeman in a comment counts as naming it",
            """    names_it = gemfile.is_file() and re.search(r\"\"\"^\\s*gem\\s+["']brakeman["']\"\"\", gemfile.read_text(encoding="utf-8", errors="replace"), re.M)""",
            '    names_it = gemfile.is_file() and "brakeman" in gemfile.read_text(encoding="utf-8", errors="replace")',
            "brakeman in a comment or in a longer gem name does not count as naming it",
        ),
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
            "a Brakeman that cannot be executed or times out is read as clean",
            '        return 2, [f"brakeman could not run',
            '        return 0, [f"brakeman could not run',
            "a Brakeman that cannot be executed is a failure to run",
        ),
        Mutation(
            "a crash with no report is read as clean",
            '        return 2, [f"brakeman gave no JSON report (exit {done.returncode}): {tail}"]',
            '        return 0, [f"brakeman gave no JSON report (exit {done.returncode}): {tail}"]',
            "a crash with no report is a failure to run, naming its exit code",
        ),
        Mutation(
            "a timeout is read as clean",
            "    except (OSError, subprocess.TimeoutExpired) as exc:",
            "    except OSError as exc:",
            "a Brakeman that outlives the timeout is a failure to run, not a clean pass",
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
