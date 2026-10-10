"""Mutation guard: triage_failures. Declared here, run by scripts/mutation_check.py (#1567)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="triage_failures",
    subject="scripts/triage_failures.py",
    selftest="scripts/triage_failures.py",   # --selftest lives in the module
    # The parser and the freshness rule it imports, and the git helper that module imports.
    deps=("scripts/dev_baseline.py", "scripts/fixture_git.py"),
    mutations=(
        Mutation(
            # A stale baseline hiding a regression is the failure this exists to refuse.
            "a stale baseline still marks a known id PREEXISTING",
            "        if fresh and example_id in known:",
            "        if example_id in known:",
            "with a STALE baseline nothing is PREEXISTING",
        ),
        Mutation(
            "ids are matched as substrings, so a baseline line 1 covers line 12",
            "        if fresh and example_id in known:",
            "        if fresh and any(example_id in k or k in example_id for k in known):",
            "an id that is only a substring-prefix of a baseline id is NEW, not PREEXISTING",
        ),
        Mutation(
            # One pass in two is not stable. Calling it FLAKY hides a real, intermittent regression.
            "one passing rerun in two is called FLAKY",
            "        if reruns and passed == reruns:",
            "        if reruns and passed >= 1:",
            "a failure that fails one of two reruns is NEW, with 1/2 shown",
        ),
        Mutation(
            "zero reruns marks everything FLAKY",
            "        if reruns and passed == reruns:",
            "        if passed == reruns:",
            "zero reruns never calls anything FLAKY",
        ),
        Mutation(
            "a NEW failure no longer fails the run",
            '    return render(rows, baseline, fresh, why), (1 if any(r["klass"] == NEW for r in rows) else 0)',
            "    return render(rows, baseline, fresh, why), 0",
            "the exit code is 1 when a NEW failure exists",
        ),
        Mutation(
            "unreadable output is triaged as a clean run",
            "    if failures is None:\n        return None,",
            "    if False:\n        return None,",
            "unreadable output is refused, not triaged as clean",
        ),
    ),
)
