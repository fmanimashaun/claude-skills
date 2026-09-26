"""Mutation guard: hook_issue_labels. Declared here, run by scripts/mutation_check.py (#1311).

The mutations that matter let an unlabelled or under-labelled issue through: no label accepted,
a `when` group ignored, a prefix never matching, a broken declaration read as "allow", or a
compound command whose create is never seen.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_issue_labels",
    subject="plugins/rails-flow/hooks/scripts/lib/issue_labels.py",
    selftest="plugins/rails-flow/hooks/scripts/lib/issue_labels.py",
    mutations=(
        # #1336: a heredoc body is tokenised again, so prose apostrophes refuse a labelled create.
        Mutation(
            "heredoc bodies are no longer stripped before tokenising",
            "    cmd = strip_heredocs(cmd)\n",
            "",
            "a heredoc body with apostrophes does not break a labelled create",
        ),
        Mutation(
            "a <<- heredoc keeps its tab-indented closing tag unrecognised",
            '            while i < len(lines) and (lines[i].lstrip("\\t") if dash else lines[i]) != tag:',
            "            while i < len(lines) and lines[i] != tag:",
            "a <<- heredoc (tab-indented close) is stripped too",
        ),
        Mutation(
            "a create with no label is allowed",
            "        if not labels:\n            where =",
            "        if False:\n            where =",
            "no label: refused",
        ),
        Mutation(
            "a `when` group applies to every issue, so a feature is asked for a severity",
            '            if g.get("when") and not any(matches(l, g["when"]) for l in labels):\n                continue',
            '            if False:\n                continue',
            "CONTROL: a feature is allowed",
        ),
        Mutation(
            "a `when` group is never applied, so a bug needs no severity",
            '            if g.get("when") and not any(matches(l, g["when"]) for l in labels):\n                continue',
            '            if g.get("when"):\n                continue',
            "a bug without a severity: refused, saying why",
        ),
        Mutation(
            "a prefix pattern never matches",
            '    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern',
            "    return label == pattern",
            "prefix groups: comp/type/prio all present is allowed",
        ),
        Mutation(
            "an unreadable declaration allows the command",
            '            return False, f"{CONFIG} is unreadable ({exc}); fix it so labels can be checked"',
            '            return True, ""',
            "an unreadable declaration refuses rather than allowing",
        ),
        Mutation(
            "only the first segment of a compound command is read",
            "                    out.append(cur[i + 3:])\n                    break\n            cur = []",
            "                    out.append(cur[i + 3:])\n                    break\n            break",
            "a create later in a compound command is checked",
        ),
        Mutation(
            "another repo's issue is held to this project's groups",
            "        foreign = repo is not None and repo != mine",
            "        foreign = False",
            "another repo: one label is enough",
        ),
    ),
)
