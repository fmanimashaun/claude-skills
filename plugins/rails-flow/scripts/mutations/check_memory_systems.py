"""Mutation guard: check_memory_systems. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1181. The check holds a recorded choice against the committed settings. Each mutation removes one
# half of one rule, and names the fixture written for it -- two of these rules are about DEFAULTS
# (a user's global remember, auto-memory on unless disabled), and a check that forgot a default
# passes exactly the project it exists for.
GUARD = Guard(
    name="check_memory_systems",
    subject="scripts/check_memory_systems.py",
    selftest="scripts/check_memory_systems.py",
    mutations=(
        Mutation(
            # THE CASE IT EXISTS FOR: a project that says nothing about remember loads it for every
            # user who enabled it globally. Accepting "unset" as "off" is that bug.
            "remember left unset reads as off",
            '    if "remember" not in chosen and remember is not False:\n',
            '    if "remember" not in chosen and remember is True:\n',
            "remember unset when not chosen fails",
        ),
        Mutation(
            "remember chosen but unset reads as on",
            '    if "remember" in chosen and remember is not True:\n',
            '    if "remember" in chosen and remember is False:\n',
            "remember chosen but unset fails",
        ),
        Mutation(
            # Auto-memory is ON BY DEFAULT; treating a missing key as off passes a project loading it.
            "auto-memory's default is forgotten",
            '    if "auto-memory" not in chosen and auto is not False:\n',
            '    if "auto-memory" not in chosen and auto is True:\n',
            "auto-memory unset when not chosen fails, because it is on by default",
        ),
        Mutation(
            "a brain nobody chose is no longer reported",
            '    if "rails-flow-brain" not in chosen and brain:\n',
            "    if False:\n",
            "a brain present but not chosen fails",
        ),
        Mutation(
            # UNDECLARED and DECLARED-EMPTY collapse, and "load nothing" becomes "nobody decided".
            "an empty choice is read as no choice",
            "        if chosen is None:\n",
            "        if not chosen:\n",
            "an empty choice with auto-memory left on fails -- not treated as undeclared",
        ),
        Mutation(
            "not-applicable is reported as a pass",
            '            return 3, (f"not applicable',
            '            return 0, (f"not applicable',
            "no recorded choice is not-applicable",
        ),
        Mutation(
            # Matched by NAME. A prefix match counts `remember-me` as remember.
            "the plugin match becomes a prefix match",
            'k.split("@", 1)[0] == "remember"',
            'k.startswith("remember")',
            "a different plugin named remember-me is not remember",
        ),
        Mutation(
            "an unknown system name is accepted",
            "    if unknown:\n",
            "    if False:\n",
            "a choice that is unknown system is exit 2",
        ),
    ),
)
