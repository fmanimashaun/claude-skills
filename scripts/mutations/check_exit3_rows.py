"""Mutation guard: check_exit3_rows. Declared here, run by scripts/mutation_check.py (#1873)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1873. The gate that keeps "could not look" out of exit 3. Each break lets an unproven 3 through, or credits a row that is not one.
    name="check_exit3_rows",
    subject="scripts/check_exit3_rows.py",
    selftest="scripts/check_exit3_rows.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            'a row with no n/a reason counts',
            '        if WHY.search(window):',
            '        if True:',
            'a row asserting 3 with no reason is a finding',
        ),
        Mutation(
            'a labelled row borrows its reason from the rows beside it',
            '        window = line if LABEL.search(line) else " ".join(lines[max(0, i - 1):i + 2])',
            '        window = " ".join(lines[max(0, i - 1):i + 2])',
            "a neighbouring row's reason is not this row's",
        ),
        Mutation(
            'an argv string counts as a label, so the label above is ignored',
            '[A-Za-z]{2} [A-Za-z]{2}',
            '[A-Za-z]{2}',
            'an argv string is not a label',
        ),
        Mutation(
            'a print of the verdict counts as a row',
            ' or SITE.search(line) or "print(" in line:',
            ' or SITE.search(line):',
            'a print of the n/a verdict is output, not a row',
        ),
        Mutation(
            'the return 3 itself counts as its own row',
            'if not ROW.search(line) or SITE.search(line) or',
            'if not ROW.search(line) or',
            "a return 3 on the row's own line is a site, not a row",
        ),
        Mutation(
            'one row covers any number of sites',
            '        if have < need:',
            '        if have < 1:',
            'two sites and one row is a finding',
        ),
        Mutation(
            'the sibling selftest is not read',
            '(rows(sibling.read_text(encoding="utf-8")) if sibling.is_file() else 0)',
            '0',
            'a row in the sibling <stem>_selftest.py counts',
        ),
        Mutation(
            '3 passed as an expected exit is not a row',
            'ROW = re.compile(r"[=!]=\\s*3\\b|,\\s*3\\s*,")',
            'ROW = re.compile(r"[=!]=\\s*3\\b")',
            '3 passed as the expected exit is a row',
        ),
        Mutation(
            'an exit 30 counts as an exit 3',
            'SITE = re.compile(r"\\breturn 3\\b|\\bexit\\(3\\)")',
            'SITE = re.compile(r"\\breturn 3|\\bexit\\(3\\)")',
            'a 30 is not an exit 3',
        ),
        Mutation(
            'a script checks.json names but is missing passes',
            '        if not path.is_file():\n            out.append(',
            '        if not path.is_file():\n            continue\n            out.append(',
            'a named script that is not there is a finding',
        ),
    ),
)
