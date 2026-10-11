"""Mutation guard: check_registry_closed. Declared here, run by scripts/mutation_check.py (#1857).

Each mutation lets a registry row that points at a closed issue read as up to date, or turns a check that could not be made into a pass or into "not applicable".
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_registry_closed",
    subject="scripts/check_registry_closed.py",
    selftest="scripts/check_registry_closed.py",   # --selftest lives in the module itself
    needs=("scripts/fixture_git.py",),              # the end-to-end row builds a throwaway repository with a remote (#1588)
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
            '    state: dict[int, tuple[str | None, str]] = {n: ("CLOSED", "") for n in numbers if n in closes}',
            '    state: dict[int, tuple[str | None, str]] = {}',
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
            '        if current is None:',
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
            'gh missing is graded not applicable (exit 3) instead of an error',
            '    if asked and not gh.available():\n        return 2,',
            '    if asked and not gh.available():\n        return 3,',
            'gh missing is exit 2',
        ),
        Mutation(
            'gh missing is a pass',
            '    if asked and not gh.available():\n        return 2,',
            '    if asked and not gh.available():\n        return 0,',
            'gh missing is exit 2',
        ),
        Mutation(
            'gh failing is graded not applicable (exit 3) instead of an error',
            '    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:\n        return 2, findings,',
            '    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:\n        return 3, findings,',
            'gh failing is exit 2',
        ),
        Mutation(
            'the limit of distinct issues is graded not applicable instead of an error',
            '    if len(asked) > LIMIT:\n        return 2,',
            '    if len(asked) > LIMIT:\n        return 3,',
            'more than the limit of distinct issues is exit 2',
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
            'more than the limit of distinct issues is exit 2',
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
        Mutation(
            'an issue closed as not planned is treated like any closed issue',
            '        elif closed and reason in NOT_FIXED:',
            '        elif False:',
            'an issue closed as not planned: a done row cannot stand',
        ),
        Mutation(
            'a not-planned issue accepts any status',
            '            if entry.get("status") not in ("owner-decision", "deviates"):',
            '            if False:',
            'a partial row is stale and the remedy is a decision, never done',
        ),
        Mutation(
            'an owner-decision row is rejected for a not-planned issue',
            '            if entry.get("status") not in ("owner-decision", "deviates"):',
            '            if entry.get("status") not in ("deviates",):',
            'an owner-decision row is up to date',
        ),
        Mutation(
            'a deviates row is rejected for a not-planned issue',
            '            if entry.get("status") not in ("owner-decision", "deviates"):',
            '            if entry.get("status") not in ("owner-decision",):',
            'a deviates row is up to date',
        ),
        Mutation(
            'a duplicate-closed issue is treated as completed',
            'NOT_FIXED = ("NOT_PLANNED", "DUPLICATE")',
            'NOT_FIXED = ("NOT_PLANNED",)',
            'an issue closed as a duplicate is treated like not planned',
        ),
        Mutation(
            'a key repeated within an entry is accepted, so the last value hides the first',
            '        if key in entries[-1]:',
            '        if False:',
            'a repeated key within an entry is refused',
        ),
        Mutation(
            'closing keywords are matched case-sensitively',
            '/issues/(\\d+)\\b)", re.I)',
            '/issues/(\\d+)\\b)")',
            'closing keywords in any case and every form',
        ),
        Mutation(
            'the colon form of a closing keyword is missed',
            'resolve[sd]?):?\\s+(?:#(\\d+)',
            'resolve[sd]?)\\s+(?:#(\\d+)',
            'closing keywords in any case and every form',
        ),
        Mutation(
            'the resolve keywords are missed',
            '(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?',
            '(?:close[sd]?|fix(?:e[sd])?):?',
            'closing keywords in any case and every form',
        ),
        Mutation(
            'a keyword inside another word is matched',
            'CLOSING = re.compile(r"(?<![\\w-])',
            'CLOSING = re.compile(r"',
            'a word that only ends in a keyword is not a keyword',
        ),
        Mutation(
            'a closing keyword in a code fence closes the issue',
            '    body = re.sub(r"```.*?```|~~~.*?~~~", " ", body, flags=re.S)',
            '    pass',
            'a closing keyword in a code fence or a code span closes nothing',
        ),
        Mutation(
            'a closing keyword in a code span closes the issue',
            '    body = re.sub(r"`[^`\\n]*`", " ", body)',
            '    pass',
            'a closing keyword in a code fence or a code span closes nothing',
        ),
        Mutation(
            'a same-repository qualified reference is not collected',
            '        elif m.group(3) and repo and m.group(2).lower() == repo.lower():',
            '        elif False:',
            'a same-repository qualified reference closes the issue',
        ),
        Mutation(
            'a same-repository issue URL is not collected',
            '        elif m.group(5) and repo and m.group(4).lower() == repo.lower():',
            '        elif False:',
            'a same-repository full issue URL closes the issue',
        ),
        Mutation(
            "another repository's qualified reference is collected",
            '        elif m.group(3) and repo and m.group(2).lower() == repo.lower():',
            '        elif m.group(3) and repo:',
            "another repository's qualified reference and URL close nothing",
        ),
        Mutation(
            "another repository's issue URL is collected",
            '        elif m.group(5) and repo and m.group(4).lower() == repo.lower():',
            '        elif m.group(5) and repo:',
            "another repository's qualified reference and URL close nothing",
        ),
        Mutation(
            'the repository name is compared case-sensitively',
            'm.group(2).lower() == repo.lower()',
            'm.group(2) == repo',
            'a same-repository qualified reference closes the issue',
        ),
        Mutation(
            'a github remote URL is not parsed',
            '    return f"{m.group(1)}/{m.group(2)}" if m else None',
            '    return None',
            'an https remote names this repository',
        ),
        Mutation(
            'the .git suffix of a remote is kept in the repository name',
            '([\\w.-]+?)(?:\\.git)?/?$',
            '([\\w.-]+?)/?$',
            'an https remote names this repository',
        ),
        Mutation(
            'this repository is never told from the origin remote',
            '    return slug_from_remote(done.stdout) if done.returncode == 0 else None',
            '    return None',
            'the origin remote tells this repository',
        ),
        Mutation(
            "the body's closing keywords are read without this repository's name",
            'closing_numbers(Path(args.closes_from_body).read_text(encoding="utf-8-sig"), repo_slug(Path(args.root).resolve()))',
            'closing_numbers(Path(args.closes_from_body).read_text(encoding="utf-8-sig"), None)',
            'the origin remote tells this repository',
        ),
    ),
)
