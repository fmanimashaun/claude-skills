"""Mutation guard: check_privacy_inventory. Declared here, run by scripts/mutation_check.py (#1310).

The mutations that matter make the inventory VACUOUS: a missing file read as clean, an unlisted
column passed, `none` required to carry a basis, or a stale entry left to mislead the policy.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_privacy_inventory",
    subject="scripts/check_privacy_inventory.py",
    selftest="scripts/check_privacy_inventory.py",
    deps=("scripts/build_project_wiki.py",),   # the one schema.rb and YAML reader
    mutations=(
        # Every comma a separator again, so a quoted value with a comma breaks the entry.
        Mutation(
            "a comma inside quotes splits the entry",
            "            quote = ch\n            cur.append(ch)",
            "            cur.append(ch)",
            "a quoted value may contain a comma",
        ),
        Mutation(
            "no inventory at all reads as clean",
            "        return 1, [f\"no {INVENTORY}: all {len(columns)} column(s)",
            "        return 0, [f\"no {INVENTORY}: all {len(columns)} column(s)",
            "no inventory is a finding naming the count, never clean",
        ),
        Mutation(
            "an unlisted column passes",
            "        if entry is None:\n            findings.append(",
            "        if entry is None:\n            continue\n            findings.append(",
            "a new column fails until it is classified",
        ),
        Mutation(
            "a personal column needs no basis or retention",
            '        elif category != "none":',
            "        elif False:",
            "a personal column with no basis or retention is a finding",
        ),
        Mutation(
            "`none` is treated as personal, so every not-personal column needs a basis",
            '        elif category != "none":',
            "        elif True:",
            "CONTROL: a complete inventory is clean",
        ),
        Mutation(
            "stale entries are never reported",
            "            if (t, c) not in columns:",
            "            if False:",
            "an entry for a vanished column is a finding",
        ),
        # #1695: a second database's schema file.
        Mutation(
            "a second db/*_schema.rb is never read",
            "    return [root / SCHEMA, *others]",
            "    return [root / SCHEMA]",
            "a new column in the SECOND schema fails until it is classified, and the finding names its file",
        ),
        Mutation(
            "the Solid trio is read as well",
            "if p.name not in FRAMEWORK_SCHEMAS)",
            "if True)",
            "the Solid trio is framework-owned: a solid_* table in cache_schema.rb, queue_schema.rb or cable_schema.rb is not reported",
        ),
        Mutation(
            "a table in two schema files is picked silently",
            "            if table in tables:\n                duplicates.append(",
            "            if False:\n                duplicates.append(",
            "a table in two schema files is a finding, not a silent pick",
        ),
        Mutation(
            "a finding does not say which file a column came from",
            '        return "" if source[table] == str(SCHEMA) else f" (in {source[table]})"',
            '        return ""',
            "a new column in the SECOND schema fails until it is classified, and the finding names its file",
        ),
        Mutation(
            "a stale table is judged against db/schema.rb alone",
            "        if t not in tables:",
            "        if t not in {name for name, file in source.items() if file == str(SCHEMA)}:",
            "CONTROL: a second schema file's columns, classified, are clean and counted",
        ),
        Mutation(
            "an inline { } entry is not parsed",
            '    m = FLOW.match(str(value).strip())\n    if not m:',
            '    m = None\n    if not m:',
            "CONTROL: a complete inventory is clean",
        ),
    ),
)
