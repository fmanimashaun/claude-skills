"""Mutation guard: close_on_dev_merge. Declared here, run by scripts/mutation_check.py.

The closing rule is the whole safety of the workflow: close too eagerly and a partial fix, or a
sentence that merely mentions an issue, closes it; too narrowly and nothing closes at all.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="close_on_dev_merge",
    subject="scripts/close_on_dev_merge.py",
    selftest="scripts/close_on_dev_merge.py",
    mutations=(
        Mutation(
            "a keyword mid-sentence closes the issue",
            'FIXES = re.compile(r"^\\s*(?:[-*]\\s+)?Fixes\\s+#(\\d+)\\s*$", re.M | re.I)',
            'FIXES = re.compile(r"Fixes\\s+#(\\d+)", re.M | re.I)',
            "'This fixes #12 only partly.'",
        ),
        Mutation(
            "Refs closes an issue too, so partial work is marked done",
            'FIXES = re.compile(r"^\\s*(?:[-*]\\s+)?Fixes\\s+#(\\d+)\\s*$", re.M | re.I)',
            'FIXES = re.compile(r"^\\s*(?:[-*]\\s+)?(?:Fixes|Refs)\\s+#(\\d+)\\s*$", re.M | re.I)',
            "'Refs #12'",
        ),
        Mutation(
            "a repeated Fixes line closes twice",
            "        if n not in seen:\n            seen.append(n)",
            "        seen.append(n)",
            "Fixes #12",
        ),
        # #1637: v1.154.0 cited #1628, #1626 and #1607 as `(Fixes #n; ...)` and none was told it shipped.
        Mutation(
            "a (Fixes #n) or (Closes #n) citation is not read, so those issues are never told they shipped",
            r'CITATION = re.compile(r"\(\s*(?:(?:Fixes|Closes)\s+)?(#\d+(?:\s*[,/]\s*#\d+)*)", re.I)',
            r'CITATION = re.compile(r"\((#\d+(?:\s*[,/]\s*#\d+)*)")',
            "shipped_issues reads (Fixes #n; ...) and (Closes #n)",
        ),
        Mutation(
            "(Refs #n) opens a citation too, so a partial fix is told it shipped",
            r'CITATION = re.compile(r"\(\s*(?:(?:Fixes|Closes)\s+)?(#\d+(?:\s*[,/]\s*#\d+)*)", re.I)',
            r'CITATION = re.compile(r"\(\s*(?:(?:Fixes|Closes|Refs)\s+)?(#\d+(?:\s*[,/]\s*#\d+)*)", re.I)',
            "shipped_issues leaves (Refs #n) out",
        ),
        Mutation(
            "the shipped note reads every #n in the notes, not only the (#n) citations",
            '    return sorted({int(n) for run in CITATION.findall(notes) for n in re.findall(r"#(\\d+)", run)})',
            '    return sorted({int(n) for n in re.findall(r"#(\\d+)", notes)})',
            'shipped_issues reads single, grouped and annotated citations',
        ),
        Mutation(
            # review of PR #1488: every real run crashed
            "the PR is read through a JSON field gh does not have (the first version's bug)",
            '    data = json.loads(gh("pr", "view", str(pr), "-R", REPO, "--json", "body,state,baseRefName"))',
            '    data = json.loads(gh("pr", "view", str(pr), "-R", REPO, "--json", "body,merged,baseRefName"))',
            "close_for_pr runs against gh's real field set",
        ),
        Mutation(
            'merged state is no longer required, so an open PR closes its issues',
            '    if data.get("state") != "MERGED" or data.get("baseRefName") != "dev":',
            '    if data.get("baseRefName") != "dev":',
            'an unmerged PR closes nothing',
        ),
        Mutation(
            # review of PR #1488
            'a Fixes line naming a pull request closes that PR',
            '            if is_pull_request(gh, n):',
            '            if False:',
            'a Fixes line naming a PULL REQUEST never touches it',
        ),
        Mutation(
            # review of PR #1488
            "one issue's failure aborts the loop, leaving the rest open",
            '        except (RuntimeError, ValueError, KeyError) as exc:\n            errors += 1',
            '        except ZeroDivisionError as exc:\n            errors += 1',
            "one issue's failure still closes the rest",
        ),
        Mutation(
            # review of PR #1488
            'a grouped citation (#a, #b) is read as nothing',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+(?:\\s*[,/]\\s*#\\d+)*)", re.I)',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+)", re.I)',
            'shipped_issues reads single, grouped and annotated citations',
        ),
        Mutation(
            # v1.153.0 missed #1404 this way
            'a citation whose annotation holds a markdown link is missed again',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+(?:\\s*[,/]\\s*#\\d+)*)", re.I)',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+[^()]*)\\)", re.I)',
            'shipped_issues reads single, grouped and annotated citations',
        ),
        Mutation(
            # independent review of PR #1533
            'a slash pair (#a/#b) loses its second number again',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+(?:\\s*[,/]\\s*#\\d+)*)", re.I)',
            'CITATION = re.compile(r"\\(\\s*(?:(?:Fixes|Closes)\\s+)?(#\\d+(?:\\s*,\\s*#\\d+)*)", re.I)',
            'shipped_issues reads single, grouped and annotated citations',
        ),
    ),
)
