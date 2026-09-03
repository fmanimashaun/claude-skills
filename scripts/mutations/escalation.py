"""Mutation guard: escalation. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="escalation",
    subject="plugins/rails-flow/scripts/escalation.py",
    selftest="plugins/rails-flow/scripts/escalation_selftest.py",
    mutations=(
        Mutation(
            # The agent and the human share a login, so authorship cannot distinguish them --
            # only the marker can, and only anchored at the START. Matching it anywhere means a
            # QUOTED question counts as the agent's own writing, and the thread parks forever.
            "the marker matches anywhere, so a quoted question reads as agent-authored",
            r'    return body.lstrip("\ufeff").startswith(MARKER)',
            "    return MARKER in body",
            "quoted-marker: a quoted question is not agent-authored",
        ),
    ),
)
