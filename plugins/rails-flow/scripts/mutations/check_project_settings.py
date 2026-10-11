"""Mutation guard: check_project_settings. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1827. The dead-config check. Each mutation breaks ONE rule, and the check's own selftest must notice it.
GUARD = Guard(
    name='check_project_settings',
    subject='scripts/check_project_settings.py',
    selftest='scripts/check_project_settings.py',
    mutations=(
        Mutation('autoMode is not flagged', '    if "autoMode" in data:', '    if False:', 'autoMode in settings.json is dead'),
        Mutation('bypassPermissions is not flagged', 'if isinstance(mode, str) and mode in DEAD_MODES:', 'if isinstance(mode, str) and mode == "auto":', 'defaultMode bypassPermissions is dead'),
        Mutation('plan is flagged as dead', 'DEAD_MODES = ("auto", "bypassPermissions")', 'DEAD_MODES = ("auto", "bypassPermissions", "plan")', 'CONTROL: defaultMode plan'),
        Mutation('settings.local.json is not read', '".claude/settings.local.json", ', '', 'autoMode in settings.local.json is dead'),
        Mutation('the example file is not read', ', ".claude/settings.example.json")', ')', 'autoMode in the example file is dead once copied'),
        Mutation('a top-level defaultMode is read as the setting', '    perms = data.get("permissions")', '    perms = data', 'CONTROL: a top-level defaultMode'),
        Mutation('a file that is not JSON is read as clean', '    except ValueError as exc:\n        raise Unusable(f"{label}: is not valid JSON ({exc}), so it cannot be judged")', '    except ValueError:\n        return [], 0', 'not JSON is unusable'),
        Mutation("an elided template's defaultMode is not judged", '            if m2:', '            if False:', 'a template with elisions'),
        Mutation('a shell block is read as a settings template', '        if lang not in ("json", "jsonc", ""):\n            continue', '        if False:\n            continue', 'CONTROL: a template with another mode'),
        Mutation('the Manual-mode consequence is dropped', 'else "it doesn\'t take effect, and the session starts in Manual mode")', 'else "it doesn\'t take effect")', 'defaultMode bypassPermissions is dead'),
        Mutation('a missing markdown path is read as empty', '    raise Unusable(f"{target}: not a file or a directory")', '    return []', 'a markdown path that does not exist'),
        Mutation('the exit code is 0 with findings', '    return (1 if found else 0), found,', '    return 0, found,', 'autoMode in settings.json is dead'),
    ),
)
