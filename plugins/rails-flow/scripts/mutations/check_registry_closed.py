"""Mutation guard: check_registry_closed. Declared here, run by scripts/mutation_check.py (#1857).

Each mutation lets a registry row that points at a closed issue read as up to date, or turns a check that could not be made into a pass.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_registry_closed",
    subject="scripts/check_registry_closed.py",
    selftest="scripts/check_registry_closed.py",   # --selftest lives in the module itself
    narrow_with="--match",                          # each mutant runs only the row its `expects` names (#1599)
    mutations=(
        Mutation(
            'a stale row is no longer reported',
            '        elif closed and not updated:',
            '        elif False:',
            'a partial row pointing at a closed issue is stale',
        ),
        Mutation(
            'closed: true alone counts as the update, whatever the status',
            '        updated = entry.get("status") == "done" and entry.get("closed") is True',
            '        updated = entry.get("closed") is True',
            'closed: true with a status that is not done is stale',
        ),
        Mutation(
            'status done alone counts as the update, without closed: true',
            '        updated = entry.get("status") == "done" and entry.get("closed") is True',
            '        updated = entry.get("status") == "done"',
            'a done row WITHOUT closed: true is still stale',
        ),
        Mutation(
            'the issues the PR closes are not treated as closed',
            '    state: dict[int, str | None] = {n: "CLOSED" for n in numbers if n in closes}',
            '    state: dict[int, str | None] = {}',
            'a row pointing at an issue this PR closes must already be updated',
        ),
        Mutation(
            'the issues the PR closes are asked of GitHub as well',
            '    asked = [n for n in numbers if n not in closes]',
            '    asked = list(numbers)',
            '--closes issues are not asked of GitHub',
        ),
        Mutation(
            'closed: true on a row whose issue is open is not reported',
            '        elif not closed and entry.get("closed") is True:',
            '        elif False:',
            'closed: true on a row whose issue is open is a finding',
        ),
        Mutation(
            'a row pointing at an issue that does not exist is not reported',
            '        if state.get(issue) is None:',
            '        if False:',
            'a row whose issue does not exist is a finding',
        ),
        Mutation(
            'a boolean is read as an issue number',
            '        if isinstance(issue, bool) or not isinstance(issue, int):',
            '        if not isinstance(issue, int):',
            'a boolean is not an issue number',
        ),
        Mutation(
            'a string is read as an issue number',
            '        if isinstance(issue, bool) or not isinstance(issue, int):',
            '        if isinstance(issue, bool):',
            'an issue that is not a number is a finding',
        ),
        Mutation(
            'gh missing is a pass instead of a skip',
            '    if asked and not gh.available():\n        return 3,',
            '    if asked and not gh.available():\n        return 0,',
            'gh missing is exit 3',
        ),
        Mutation(
            'gh failing is a pass instead of a skip',
            '    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:\n        return 3, findings,',
            '    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:\n        return 0, findings,',
            'gh failing is exit 3',
        ),
        Mutation(
            'a missing registry is a pass instead of a skip',
            '    if not path.is_file():\n        return 3, [],',
            '    if not path.is_file():\n        return 0, [],',
            'no registry is exit 3',
        ),
        Mutation(
            'an unreadable registry line is a pass',
            '    if problems:\n        return 2, problems, []',
            '    if problems:\n        return 0, problems, []',
            'a broken registry line is exit 2',
        ),
        Mutation(
            'the limit of distinct issues is not applied',
            '    if len(asked) > LIMIT:',
            '    if False:',
            'more than the limit of distinct issues is exit 3',
        ),
        Mutation(
            'the registry key of qa.config.yml is ignored',
            '                    chosen = found.group(1)',
            '                    pass',
            'the registry path comes from qa.config.yml',
        ),
        Mutation(
            'a registry path outside the project is accepted',
            '    if not (root / chosen).resolve().is_relative_to(root.resolve()):',
            '    if False:',
            'the registry path must stay inside the project',
        ),
        Mutation(
            'an issue is read once per row, not once per distinct issue',
            '    numbers = sorted({issue for _, issue in rows})',
            '    numbers = [issue for _, issue in rows]',
            'one read per distinct issue',
        ),
    ),
)
