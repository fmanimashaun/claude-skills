"""Mutation guard: doctrine_path. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="doctrine_path",
    subject="scripts/doctrine_path.py",
    selftest="scripts/doctrine_path.py",
    mutations=(
        # #1421 itself: the project's record is never consulted, so every project reads the newest
        # cached rails-stack -- some other project's doctrine.
        Mutation(
            "the machine-wide newest pick returns: the project's install is ignored",
            "    if mine is not None:\n        return [base / SKILL_REL, mine / SKILL_REL]",
            "    if False:\n        return [base / SKILL_REL, mine / SKILL_REL]",
            "the older project reads its own install",
        ),
        # A projectPath record applies everywhere, so the newest record wins for every project.
        Mutation(
            "a project-scoped record applies to every project",
            "    if not owner:\n        return True\n    try:\n        root, here",
            "    if True:\n        return True\n    try:\n        root, here",
            "the older project reads its own install",
        ),
        # Exact-match only: a session started in a subdirectory loses its project's record.
        Mutation(
            "a subdirectory no longer belongs to its project",
            "    dirs = (here, *here.parents)",
            "    dirs = (here,)",
            "a subdirectory reads its project's install",
        ),
        # The worktree mapping is dropped: a linked worktree is its own "project" with no record.
        Mutation(
            "a linked worktree is not mapped to its main checkout",
            'return gitdir.parent.parent.parent if gitdir.parent.name == "worktrees" else d',
            "return d",
            "a linked worktree reads its main checkout's install",
        ),
        # An unreadable file raises instead of falling back, and every caller crashes.
        Mutation(
            "an unreadable installed_plugins.json raises instead of falling back",
            "    except (OSError, ValueError, KeyError, TypeError):\n        return None",
            "    except (OSError, KeyError, TypeError):\n        return None",
            "an unreadable record file falls back to the newest",
        ),
        # No mutation for the case-folding branch (`os.path.samefile`): its fixture runs only on a
        # volume that folds case, and CI's Linux runner does not, so the mutant would survive there.
    ),
)
