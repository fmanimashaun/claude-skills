"""Mutation guard: check_vendored_alone. Declared here, run by scripts/mutation_check.py (#1261).

The mutations that matter make the gate VACUOUS: running the script where its siblings are (the state
that hid #1261), ignoring the exit code, or discovering nothing and reporting clean.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_vendored_alone",
    subject="scripts/check_vendored_alone.py",
    selftest="scripts/check_vendored_alone.py",
    mutations=(
        # THE MUTATION THAT RECREATES THE BUG: run the script in its plugin directory, beside the
        # sibling it needs, and every needy script passes.
        Mutation(
            "the script is run beside its siblings instead of alone",
            "        shutil.copy2(script, copy)\n",
            "        shutil.copytree(script.parent, td, dirs_exist_ok=True)\n",
            "a script that needs its sibling fails when run alone",
        ),
        Mutation(
            "a failing selftest is not a finding",
            "        if rc != 0:\n",
            "        if False:\n",
            "the needy script is reported",
        ),
        Mutation(
            "scripts a doc tells projects to vendor are no longer discovered",
            "            named.update(VENDORED_PATH.findall(",
            "            set().update(VENDORED_PATH.findall(",
            "a script a doc tells projects to vendor is discovered",
        ),
        Mutation(
            "scripts promising to work vendored alone are no longer discovered",
            "        if ALONE_PROMISE in path.read_text(",
            "        if False and ALONE_PROMISE in path.read_text(",
            "a script that promises to work vendored alone is discovered",
        ),
        Mutation(
            "a vendoring instruction naming no shipped script stops being a finding",
            '            problems.append(f"a doc tells projects to vendor .claude/scripts/{name}, and no plugin ships it")',
            "            pass",
            "a vendoring instruction naming no shipped script is a finding",
        ),
    ),
)
