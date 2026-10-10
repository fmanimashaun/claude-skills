"""Mutation guard: label_new_issue. Declared here, run by scripts/mutation_check.py (#1791).

The labeller is only safe if it is quiet on a complete issue, never guesses, and never repeats its comment; each mutant
breaks one of those.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="label_new_issue",
    subject="scripts/label_new_issue.py",
    selftest="scripts/label_new_issue.py",
    mutations=(
        Mutation(
            "a prefix pattern matches inside a word, so `xcomp:a` satisfies `comp:*`",
            "    return label.startswith(pattern[:-1]) if pattern.endswith(\"*\") else label == pattern",
            "    return pattern[:-1] in label if pattern.endswith(\"*\") else label == pattern",
            "missing_groups: a prefix is not a substring",
        ),
        Mutation(
            "an exact pattern matches by prefix, so `comp:ab` satisfies `comp:a`",
            "    return label.startswith(pattern[:-1]) if pattern.endswith(\"*\") else label == pattern",
            "    return label.startswith(pattern.rstrip(\"*\"))",
            "an exact pattern needs the exact label",
        ),
        Mutation(
            "a `when` group is applied to every issue",
            "        if when and not any(matches(x, when) for x in labels):\n            continue\n",
            "",
            "a `when` group does not apply to another type",
        ),
        Mutation(
            "a closed issue is labelled",
            '    if api.get("state") != "open":\n',
            "    if False:\n",
            "a closed issue is left alone",
        ),
        Mutation(
            "a pull request is labelled",
            '    if "pull_request" in api:\n',
            "    if False:\n",
            "a pull request is left alone",
        ),
        Mutation(
            "the comment is posted again instead of edited",
            "    mine = next((c for page in comments for c in page if MARK in (c.get(\"body\") or \"\")), None)",
            "    mine = None",
            "the old comment is edited, not repeated",
        ),
        Mutation(
            "a completed issue keeps its flag",
            "    elif flagged:\n        gh(\"issue\", \"edit\", str(issue), \"-R\", REPO, \"--remove-label\", LABEL)",
            "    elif False:\n        pass",
            "a complete issue that was flagged is unflagged",
        ),
        Mutation(
            "--dry-run changes the issue",
            "    if dry_run:\n        print(f\"#{issue}: would",
            "    if False:\n        print(f\"#{issue}: would",
            "--dry-run changes nothing",
        ),
        Mutation(
            "an already-flagged incomplete issue is flagged and commented again",
            "        if not flagged:\n            gh(\"issue\", \"edit\", str(issue), \"-R\", REPO, \"--add-label\", LABEL)\n",
            "        gh(\"issue\", \"edit\", str(issue), \"-R\", REPO, \"--add-label\", LABEL)\n",
            "a still-incomplete flagged issue is not flagged or commented again",
        ),
        Mutation(
            "a declaration with no `groups` reads as an empty rule",
            "    if not isinstance(groups, list):\n        raise ValueError(f\"{path}: no `groups` list\")\n",
            "    groups = groups if isinstance(groups, list) else []\n",
            "a declaration with no `groups` is an error",
        ),
    ),
)
