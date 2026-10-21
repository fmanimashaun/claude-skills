"""Mutation guard: audit_findings. Declared here, run by scripts/mutation_check.py (#2221).

The contract's whole value is that an audit cannot overclaim: authority comes from the rule's basis,
not from whoever found the defect. Each mutation switches off one refusal that keeps that true, and
names the fixture that must notice.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="audit_findings",
    subject="scripts/audit_findings.py",
    selftest="scripts/audit_findings.py",
    selftest_args=("--selftest",),
    needs=("reference/architecture-rules.json",),
    mutations=(
        Mutation(
            "a finding naming no real rule stops being refused",
            "        if rule is None:",
            "        if False:",
            "an unknown rule is refused",
        ),
        Mutation(
            "a finding may write its own authority",
            "            if k in f:",
            "            if False:",
            "a written authority is refused",
        ),
        Mutation(
            "a screenshot that does not exist counts as evidence",
            '        elif ev["kind"] == "screenshot" and not (root / ev["ref"]).is_file():',
            "        elif False:",
            "a screenshot that is not a file is refused",
        ),
        Mutation(
            "a house rule may claim a standard",
            '        if rule is not None and rule["authority"] == "house" and STANDARD_WORDS.search(text):',
            "        if False:",
            "a house rule that claims WCAG is refused",
        ),
        Mutation(
            "a report over zero screens passes",
            "    if not isinstance(examined, int) or isinstance(examined, bool) or examined < 1:",
            "    if False:",
            "zero screens examined is refused",
        ),
        Mutation(
            "a standard no longer outranks a house rule",
            '    out.sort(key=lambda d: (d["authority"] != "standard", -d["reach"]',
            '    out.sort(key=lambda d: (False, -d["reach"]',
            "a standard outranks a house rule whatever its reach and instance count",
        ),
        Mutation(
            "a judge's count is lost",
            '"instances": max(int(it.get("count") or 1), 1)',
            '"instances": 1',
            "a judge's count becomes the instance count",
        ),
        Mutation(
            "layout_fit findings are filed against the wrong rule",
            '"layout_fit": "A23"',
            '"layout_fit": "A24"',
            "a judge's finding maps to its framework rule",
        ),
    ),
)
