"""Mutation guard: apm_advisory. Declared here, run by scripts/mutation_check.py (#1366)."""
from mutation_types import Guard, Mutation  # noqa: F401

# An advisory fails in two quiet directions: it stops saying anything (the reminder is gone and
# nothing reports it), or it says it always (it gets ignored, which is the same thing). The third is
# a substring match, which lets any gem with an APM's name inside it silence the line.
GUARD = Guard(
    name="apm_advisory",
    subject="scripts/apm_advisory.py",
    selftest="scripts/apm_advisory.py",
    needs=("commands/deploy-cloud.md", "commands/release.md"),
    mutations=(
        Mutation(
            "the advisory is never printed",
            "    return None if gems_in(lockfile) & APM_GEMS else ADVICE",
            "    return None",
            "a lockfile with no APM gem gets the advisory",
        ),
        Mutation(
            "the advisory is printed even when an APM is present",
            "    return None if gems_in(lockfile) & APM_GEMS else ADVICE",
            "    return ADVICE",
            "a lockfile with rails_pulse is silent",
        ),
        Mutation(
            "gem names are matched as substrings of the lockfile",
            "    return None if gems_in(lockfile) & APM_GEMS else ADVICE",
            "    return None if any(g in lockfile for g in APM_GEMS) else ADVICE",
            "a near-miss name is not an APM",
        ),
        Mutation(
            "an advisory that blocks: the entry point exits non-zero when it advises",
            "    if line:\n        print(line)\n    return 0",
            "    if line:\n        print(line)\n        return 1\n    return 0",
            "the advisory exits 0",
        ),
        # A lockfile that is not UTF-8 raised past the OSError handler and exited 1 -- found by
        # checking the PR body's "always exits 0" against the code. The mutant crashes, so any
        # failure counts.
        Mutation(
            "an undecodable lockfile crashes the advisory instead of skipping",
            "    except (OSError, UnicodeDecodeError):",
            "    except OSError:",
            "",
        ),
    ),
)
