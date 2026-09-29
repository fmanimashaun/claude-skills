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
        Mutation(
            "the shipped note reads every #n in the notes, not only the (#n) citations",
            'return sorted({int(n) for n in re.findall(r"\\(#(\\d+)\\)", notes)})',
            'return sorted({int(n) for n in re.findall(r"#(\\d+)", notes)})',
            "shipped_issues: expected [1410, 1444]",
        ),
    ),
)
