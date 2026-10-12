"""Mutation guard: pipeline-status.sh. Declared here, run by scripts/mutation_check.py (#1946)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The SessionStart hook found pipeline.yml and qa/CERTIFICATION relative to the working directory, so a session started in a subdirectory got no nudge. Each mutation puts one of those reads
# back (or drops the opt-in), and each is caught by running the REAL hook from a subdirectory of a real repository.
GUARD = Guard(
    name="pipeline_status_hook",
    subject="hooks/scripts/pipeline-status.sh",
    selftest="scripts/pipeline_status_selftest.py",
    needs=("scripts/fixture_git.py", "hooks/scripts/lib"),   # its selftest's git goes through fixture_git (#1588); the hook sources lib/trusted-env.sh (#1850)
    mutations=(
        Mutation(
            "pipeline.yml is read relative to the working directory again",
            '[ -f "$top/pipeline.yml" ] || exit 0',
            "[ -f pipeline.yml ] || exit 0",
            "the post-merge nudge is printed from a subdirectory",
        ),
        Mutation(
            "qa/CERTIFICATION is read relative to the working directory again",
            'if [ -f "$top/qa/CERTIFICATION" ]; then',
            "if [ -f qa/CERTIFICATION ]; then",
            "the 'dev is certified' line is printed from a subdirectory",
        ),
        Mutation(
            "the interpreter imports from the working directory again, so a committed json.py runs",
            "python3 -I -c 'import json,sys;",
            "python3 -c 'import json,sys;",
            "a json.py committed in the repository is not imported by the hook",
        ),
        Mutation(
            "a repository with no pipeline.yml is nudged anyway",
            '[ -f "$top/pipeline.yml" ] || exit 0',
            ":",
            "CONTROL: a repository with no pipeline.yml prints nothing from the root",
        ),
    ),
)
