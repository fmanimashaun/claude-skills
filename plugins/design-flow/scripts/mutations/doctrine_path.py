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
            "    if not owner:\n        return True\n    try:\n        # BOTH",
            "    if True:\n        return True\n    try:\n        # BOTH",
            "the older project reads its own install",
        ),
        # Exact-match only: a session started in a subdirectory loses its project's record.
        Mutation(
            "a subdirectory no longer belongs to its project",
            "    dirs = tuple(d for here in sessions for d in (here, *here.parents))",
            "    dirs = tuple(sessions)",
            "a subdirectory reads its project's install",
        ),
        # The worktree mapping is dropped: a linked worktree is its own "project" with no record.
        Mutation(
            "a linked worktree is not mapped to its main checkout",
            "                return gitdir.parent.parent.parent / project.relative_to(d)\n            return project",
            "                return project\n            return project",
            "a linked worktree reads its main checkout's install",
        ),
        # An unreadable file raises instead of falling back, and every caller crashes.
        Mutation(
            "an unreadable installed_plugins.json raises instead of falling back",
            "    except (OSError, ValueError, KeyError, TypeError):\n        return None",
            "    except (OSError, KeyError, TypeError):\n        return None",
            "an unreadable record file falls back to the newest",
        ),
        # Only the main checkout compared: a record naming the worktree itself stops matching.
        Mutation(
            "only the main checkout is compared, not the session's own path",
            "{project.resolve(), _main_checkout(project).resolve()}",
            "{_main_checkout(project).resolve()}",
            "a record naming the worktree itself applies in it",
        ),
        # The case-only branch dropped. Its fixture stubs `samefile`, so this runs on Linux too.
        Mutation(
            "a projectPath differing only in case no longer applies",
            "        return root.exists() and any(str(d).lower() == str(root).lower() and os.path.samefile(root, d)",
            "        return False and any(str(d).lower() == str(root).lower() and os.path.samefile(root, d)",
            "a projectPath differing only in case still applies",
        ),
        # #1473 review B1: a worktree maps to the main ROOT, so `<wt>/app` misses `<main>/app`.
        Mutation(
            "a worktree subdirectory maps to the main checkout's root",
            "                return gitdir.parent.parent.parent / project.relative_to(d)",
            "                return gitdir.parent.parent.parent",
            "the same subdirectory of a worktree",
        ),
        # A bare clone's worktree maps to the directory that holds `repo.git`.
        Mutation(
            "a bare clone's worktree is mapped like a checkout's",
            '            if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":',
            '            if gitdir.parent.name == "worktrees":',
            "a bare clone's worktree is not mapped",
        ),
        # An install without the skill wins, so find() returns None though another version is cached.
        Mutation(
            "a record whose install lacks the skill still wins",
            "            and (Path(r[\"installPath\"]) / SKILL_REL).is_dir() and _applies(r, project)]",
            "            and _applies(r, project)]",
            "an install without the skill falls back",
        ),
        # A non-string projectPath raises TypeError out of find(), and all six callers crash.
        Mutation(
            "a malformed projectPath raises out of find()",
            "    except (OSError, TypeError):         # a projectPath that is not a path string",
            "    except OSError:",
            "malformed fields are skipped",
        ),
        Mutation(
            # #1475
            'the cache-layout check is dropped, so a staged copy globs the whole temp root again',
            '    if base.parent.name != "cache":\n        return [base / SKILL_REL]\n',
            '',
            'does not find a sibling tempdir',
        ),
    ),
)
