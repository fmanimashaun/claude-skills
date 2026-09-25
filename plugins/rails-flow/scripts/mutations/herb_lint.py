"""Mutation guard: herb_lint. Declared here, run by scripts/mutation_check.py (#1285).

The mutation that matters recreates the defect: dropping the version from the npx call, so the
verdict again depends on whatever npm published last.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="herb_lint",
    subject="scripts/herb_lint.py",
    selftest="scripts/herb_lint.py",
    mutations=(
        # #1318: herb's file order again, so the row can name a hint while the errors sit below it.
        Mutation(
            "offences are left in herb's file order",
            '    ordered = sorted(offenses, key=lambda o: (rank.get(o.get("severity"), len(rank)),',
            '    ordered = sorted(offenses, key=lambda o: (0,',
            "the ERROR is listed before the hint that herb printed first",
        ),
        Mutation(
            "the summary line is dropped, so project_gates falls back to the first location it finds",
            "    return lines\n\n\ndef main",
            "    return lines[1:]\n\n\ndef main",
            "the summary line leads, with counts per severity",
        ),
        # #1296: back to views-only, so component templates are never linted.
        Mutation(
            "the default scope drops app/components again",
            'TEMPLATE_DIRS = ("app/views", "app/components")',
            'TEMPLATE_DIRS = ("app/views",)',
            "with app/components present, component templates are linted too",
        ),
        Mutation(
            "npx runs the unversioned package again, so npm's latest decides the verdict",
            '    return (["npx", "-y", f"@herb-tools/linter@{version}", *paths],',
            '    return (["npx", "-y", "@herb-tools/linter", *paths],',
            "npx is pinned to the locked version",
        ),
        Mutation(
            "a dependency constraint under another gem is read as the lock",
            'LOCKED = re.compile(r"^ {4}herb \\((\\d+\\.\\d+\\.\\d+)(?:[-.][^)]*)?\\)$", re.M)',
            'LOCKED = re.compile(r"^ +herb \\((?:>= )?(\\d+\\.\\d+)(?:\\.\\d+)?[^)]*\\)$", re.M)',
            "a six-space constraint is not a locked version",
        ),
        Mutation(
            "the project's own pinned binary is ignored",
            "    if local.is_file() and os.access(local, os.X_OK):",
            "    if False:",
            "a local node_modules binary is preferred",
        ),
        Mutation(
            "no locked herb is reported as clean",
            "        return 2\n",
            "        return 0\n",
            "main exits 2 when no version can be pinned, never 0",
        ),
        Mutation(
            "the note naming the linter is not printed",
            '    print(f"NOTE: {note}")\n',
            "",
            "main prints the NOTE naming the linter",
        ),
        Mutation(
            "the linter's failure is swallowed",
            "    sys.stderr.write(proc.stderr)\n    return proc.returncode",
            "    sys.stderr.write(proc.stderr)\n    return 0",
            "main passes the linter's exit status through",
        ),
    ),
)
