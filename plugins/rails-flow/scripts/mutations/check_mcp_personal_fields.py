"""Mutation guard: check_mcp_personal_fields. Declared here, run by scripts/mutation_check.py (#1931).

The mutations that matter make the gate VACUOUS: an undeclared tool passes, a personal column passes, an allow-list covers
more than it names, an aggregate of a personal column passes, or a commented-out declaration counts.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_mcp_personal_fields",
    subject="scripts/check_mcp_personal_fields.py",
    selftest="scripts/check_mcp_personal_fields.py",
    # it imports the inventory reader and the shared tool finder, and the reader imports the wiki's yaml subset
    needs=("scripts/check_privacy_inventory.py", "scripts/build_project_wiki.py",
           "scripts/check_mcp_annotations.py"),
    mutations=(
        Mutation("a tool that declares no sources passes",
                 "        if not tokens:\n            findings.append(",
                 "        if False:\n            findings.append(",
                 "a tool that declares no sources is a finding"),
        Mutation("a personal column passes",
                 '            if category and category != "none" and category not in allowed:',
                 "            if False:",
                 "a tool returning a personal column is a finding"),
        Mutation("an allow-list for any tool covers every tool",
                 "        allowed = set(allow.get(name, []))",
                 "        allowed = {c for cats in allow.values() for c in cats}",
                 "an allow-list for ANOTHER tool does not cover this one"),
        Mutation("an allow-list entry covers every category",
                 '            if category and category != "none" and category not in allowed:',
                 '            if category and category != "none" and not allowed:',
                 "an allow-list for another CATEGORY does not cover this one"),
        Mutation("a sum of a personal column is skipped like a count",
                 "            if agg:\n                tok = agg.group(\"col\")",
                 "            if agg:\n                continue",
                 "a sum of a personal column is held to that column"),
        Mutation("a column the inventory does not list passes",
                 "            if entry is None:\n                findings.append(",
                 "            if entry is None:\n                continue\n                findings.append(",
                 "a column the inventory does not list is a finding"),
        Mutation("a commented-out sources line counts",
                 '            elif ch == "#" and not (kept and kept[-1] == "%"):\n                break',
                 '            elif False:\n                break',
                 "CONTROL: a trailing comment's sources are not a declaration"),
        Mutation("no privacy inventory is a pass, not n/a",
                 "        if inventory is None:\n            return 3,",
                 "        if inventory is None:\n            return 0,",
                 "no privacy inventory must be n/a (exit 3)"),
        Mutation("an unreadable declaration is ignored, so the allow-list reads empty and the gate still decides",
                 '                raise CouldNotCheck(f"{DECLARATION} is not a JSON object ({exc})") from exc',
                 "                allow = {}",
                 "a declaration that is not JSON is could-not-check (exit 2)"),
    ),
)
