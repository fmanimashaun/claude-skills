"""Mutation guard: stack_toolchain (#2168). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="stack_toolchain",
    subject="scripts/stack_toolchain.py",
    selftest="scripts/stack_toolchain.py",
    selftest_args=("--selftest",),
    # stack_toolchain asks the detector which stacks matched and reads their `toolchain` blocks.
    needs=("scripts/detect_stack.py",),
    mutations=(
        Mutation(
            "a plugin no settings file enables counts as present",
            '            if enabled.get(row["id"]):',
            '            if True:',
            "a plugin no settings file enables is flagged with its install line",
        ),
        Mutation(
            "a CLI missing from PATH counts as present",
            '    found = on_path(row["bin"])\n    if found:',
            '    found = on_path(row["bin"]) or Path("/bin/sh")\n    if found:',
            "a CLI not on PATH is flagged with its install line",
        ),
        Mutation(
            "a failing ready check counts as ready",
            '    return done.returncode == 0, f"exit {done.returncode}"',
            '    return True, f"exit {done.returncode}"',
            "a CLI whose ready check fails is flagged with its hint",
        ),
        Mutation(
            "the ready check is never run",
            '            if row.get("ready"):',
            '            if False:',
            "a CLI whose ready check fails is flagged with its hint",
        ),
        Mutation(
            "the least specific scope wins, so a project cannot disable a user plugin",
            '    return [home / ".claude" / "settings.json", project / ".claude" / "settings.json", project / ".claude" / "settings.local.json"]',
            '    return [project / ".claude" / "settings.local.json", project / ".claude" / "settings.json", home / ".claude" / "settings.json"]',
            "a project scope that disables a user plugin wins",
        ),
        Mutation(
            "the local settings file is never read",
            ', project / ".claude" / "settings.local.json"]',
            ']',
            "the local scope wins over the project scope",
        ),
        Mutation(
            "an unreadable settings file is skipped as if absent",
            '            problems.append(f"{path}: cannot be read: {err}")',
            '            pass',
            "an unreadable settings file is exit 2, not a list of missing plugins",
        ),
        Mutation(
            "an enabledPlugins that is not an object is ignored",
            '            problems.append(f"{path}: enabledPlugins is not an object")',
            '            pass',
            "an enabledPlugins that is not an object is exit 2",
        ),
        Mutation(
            "a findings list is reported as exit 0",
            '    return (1 if findings else 0), findings, notes',
            '    return 0, findings, notes',
            "a missing tool is exit 1",
        ),
        Mutation(
            "a project that cannot be judged is reported clean",
            '    if code == 2:\n        return 2,',
            '    if code == 2:\n        return 0,',
            "a project that cannot be judged is exit 2, never 0",
        ),
        Mutation(
            "the project's own copy of a CLI is executed for its version and ready check",
            '            if in_project:',
            '            if False:',
            "the project's own copy of a CLI is never executed by the audit",
        ),
        Mutation(
            'a project path may resolve outside the project',
            '        if candidate.is_relative_to(root) and candidate.is_file()',
            '        if candidate.is_file()',
            'a project path that is a symlink out of the project is not the CLI',
        ),
        Mutation(
            "a PATH hit is never judged by where it lives, so the project's node_modules/.bin on PATH is run",
            '        return str(found), found.is_relative_to(root)',
            '        return str(found), False',
            'a project binary reached through PATH is never executed',
        ),
        Mutation(
            'relative PATH entries are searched',
            '        if not entry or not os.path.isabs(entry):',
            '        if not entry:',
            'a relative PATH entry is not searched',
        ),
        Mutation(
            "PATH is checked before the project's own paths, so a global CLI hides the pinned one",
            '    for rel in row.get("project_paths") or []:\n        candidate = (project / rel).resolve()',
            '    for rel in ([] if on_path(row["bin"]) else row.get("project_paths") or []):\n        candidate = (project / rel).resolve()',
            'the project-pinned CLI is found before a global one',
        ),
        Mutation(
            "a ready probe that is the project's own binary is run",
            '                if probe is None or probe.resolve().is_relative_to(project.resolve()):',
            '                if probe is None:',
            "a ready probe that is the project's own binary is not run",
        ),
    ),
)
