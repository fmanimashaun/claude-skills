"""Mutation guard: canvas_manifest. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #908. Each mutation makes the checklist shorter or the check softer -- the two ways "done" loses its denominator.
GUARD = Guard(
    name="canvas_manifest",
    subject="plugins/design-flow/scripts/canvas_manifest.py",
    selftest="plugins/design-flow/scripts/canvas_manifest.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a void <input> control is dropped from the manifest (it never closes)",
            "            if tag in VOID:                       # <input> never closes: record it now or lose it\n                self._flush_control(ctl)",
            "            if False:\n                self._flush_control(ctl)",
            "controls carry their label",
        ),
        Mutation(
            "a bound text with inner spaces is recorded as copy again",
            'BIND = re.compile(r"\\{\\{\\s*([A-Za-z_$][\\w$]*)(?:[.\\[][^}]*?)?\\s*\\}\\}")',
            'BIND = re.compile(r"\\{\\{([A-Za-z_$][\\w$]*)\\}\\}")',
            "is never copy",
        ),
        Mutation(
            "the x-dc data script is not read, so most of the spec is missing from the checklist",
            "    m = SCRIPT_RE.search(html)\n    if not m:\n        return []",
            "    m = None\n    if not m:\n        return []",
            "label pairs are items",
        ),
        Mutation(
            "an unaccounted item is no longer a gap, so a report may skip what it likes",
            '        if e is None:\n            problems.append(f"{item[\'id\']} ({item[\'kind\']}: {item[\'text\'][:60]!r}) is not accounted for")\n            continue',
            '        if e is None:\n            continue',
            "an unaccounted item is a gap",
        ),
        Mutation(
            "`implemented` is taken at its word: the named file is never searched for the text",
            "                if n and len(n) >= 4 and n not in body and n not in locales:",
            "                if False:",
            "is in neither the named file nor the locales is a gap",
        ),
        Mutation(
            "a deferral needs no reason",
            '        if st == "deferred" and not e.get("reason"):',
            '        if False:',
            "a deferral without a reason is a gap",
        ),
    ),
)
