"""Mutation guard: maintainer_doctor. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="maintainer_doctor",
    subject="scripts/maintainer_doctor.py",
    selftest="scripts/maintainer_doctor_selftest.py",
    needs=(
        # + `scripts`: GATES names ~55 sibling scripts; listing them by hand is the same rot that made check_handoff inert.
        ".gitignore",
        "scripts",
        # ...and `plugins`, because GATES names checkers in BOTH trees. Reaching this second
        # missing path only after fixing the first is the point of `run_baseline`: an inert
        # guard hides every downstream problem behind the first one.
        "plugins",
        "evals",
    ),
    mutations=(
        # #895. The doctor only MAPS the shipped checker's exit code; the two ways to get that wrong are
        # a FAIL read as PASS and n/a read as PASS. Each is one branch.
        Mutation(
            "a failing ruleset check is reported as PASS",
            '        if code == 0:\n            self.add(PASS, "`main` merges only (ruleset)", first)',
            '        if code in (0, 1):\n            self.add(PASS, "`main` merges only (ruleset)", first)',
            "no ruleset is FAIL",
        ),
        Mutation(
            "not-applicable (no gh, no GitHub origin) is reported as PASS",
            '        elif code == 3:\n            self.add(SKIP, "`main` merges only (ruleset)", first, "gh auth login, then re-run")',
            '        elif code == 3:\n            self.add(PASS, "`main` merges only (ruleset)", first)',
            "SKIP (n/a), never a pass",
        ),
        # #820. The doctor kept `out.splitlines()[-1]` of a failing gate, and most of our gates end
        # with `N finding(s).` -- so what survived was reliably the count. On a runner the doctor is
        # the ONLY thing that runs the gate (capture_output=True), so the findings were printed
        # nowhere at all: a red build reading `1 finding(s).` and nothing else.
        Mutation(
            "a failing gate's findings are dropped again, leaving only its count",
            '    rest = lines[:-1]',
            '    rest = []',
            "a failing gate's FINDING is dropped",
        ),
        # Bottom-anchored, opposite to project_gates.summarise: our gates put the preamble first
        # (lint_self_consistency opens with a 40-clause stats line) and the report last. Keeping the
        # EARLIEST lines keeps the throat-clearing and drops the findings.
        Mutation(
            'the cap keeps the EARLIEST lines, so a long gate reports its preamble',
            '        rest = [f"… {dropped} earlier line(s) dropped — run the command below for the rest"] + \\\n            rest[-MAX_GATE_FINDING_LINES:]',
            '        rest = rest[:MAX_GATE_FINDING_LINES]',
            'the cap keeps the EARLIEST lines',
        ),
        Mutation(
            'the cap truncates silently, so a reader cannot tell the report was cut',
            '        rest = [f"… {dropped} earlier line(s) dropped — run the command below for the rest"] + \\\n            rest[-MAX_GATE_FINDING_LINES:]',
            '        rest = rest[-MAX_GATE_FINDING_LINES:]',
            'the cap truncates SILENTLY',
        ),
        Mutation(
            'the cap is removed, so one noisy gate buries the other 97',
            '    if len(rest) > MAX_GATE_FINDING_LINES:',
            '    if False:',
            'the cap does not bound the output',
        ),
        Mutation(
            "the summary stops being the gate's last line",
            '    return lines[-1], tuple(rest)',
            '    return lines[0], tuple(rest)',
            "the summary line is no longer the gate's last line",
        ),
        Mutation(
            'a gate that failed with NO output reports nothing at all',
            '        return f"exit {code}", ()',
            '        return "", ()',
            'a gate that failed with NO output',
        ),
        # Proving `gate_output` carries them is not proving `report` PRINTS them: emptying this
        # survived every fixture that only called the helper, in #812 and again here.
        Mutation(
            'report() stops printing the findings',
            '            for finding_line in r.findings:\n                print(f"             {finding_line}")',
            '            for finding_line in ():\n                print(f"             {finding_line}")',
            'report() prints the count but not the findings',
        ),
        Mutation(
            'the findings print after the remedy instead of before it',
            '            for finding_line in r.findings:\n                print(f"             {finding_line}")\n            if r.remedy and r.status in (FAIL, SKIP):\n                print(f"           -> {r.remedy}")',
            '            if r.remedy and r.status in (FAIL, SKIP):\n                print(f"           -> {r.remedy}")\n            for finding_line in r.findings:\n                print(f"             {finding_line}")',
            'the findings print AFTER the remedy',
        ),

        # The gate tally must exclude preconditions. Widening the filter is how the count goes
        # back to being off by one, which put three wrong numbers in shipped text.
        Mutation(
            "the gate tally counts preconditions and diagnostics as gates",
            '        return [r for r in self.results if r.name.startswith("gate: ")]',
            "        return list(self.results)",
            "the gate tally counted",
        ),
        Mutation(
            "an unignored corpora path stops being reported",
            "                if not verdict:",
            "                if False:",
            "slashed ignore",
        ),
        Mutation(
            "a SKIP is allowed to render as a PASS",
            'if not missing:\n            self.add(PASS, "design corpora present"',
            'if True:\n            self.add(PASS, "design corpora present"',
            "corpora",
        ),
        # Both directions of the corpora exemption. Too NARROW was the live defect: `coverage
        # artifact drift` was missing, so a machine without the optional licensed kits was told
        # to fix failures before doing maintenance work. Too BROAD silently shrinks the sweep.
        Mutation(
            "the artifact drift gate is exempted again, hiding a stripped committed page",
            'CORPORA_GATES = frozenset({"coverage matrix drift"})',
            'CORPORA_GATES = frozenset({"coverage matrix drift", "coverage artifact drift"})',
            "CORPORA_GATES is",
        ),
        Mutation(
            "the corpora exemption goes broad and skips a gate that needs nothing",
            'CORPORA_GATES = frozenset({"coverage matrix drift"})',
            'CORPORA_GATES = frozenset({"coverage matrix drift", "packaging determinism"})',
            "CORPORA_GATES is",
        ),
        # #129 added a SECOND name-keyed carve-out, so it gets the same three mutations the
        # first one has: a name that matches nothing, a set that grew, and the direction
        # nobody thinks of -- an "allowance" that is really a tightening.
        Mutation(
            "the slow-gate allowance is keyed on a gate that does not exist",
            '    "mutation coverage": 900,',
            '    "mutatoin coverage": 900,',
            "SLOW_GATES names no such gate",
        ),
        Mutation(
            "the slow-gate allowance widens to a gate that reads the tree once",
            '    "mutation coverage": 900,',
            '    "mutation coverage": 900,\n    "packaging determinism": 900,',
            "SLOW_GATES is",
        ),
        Mutation(
            "a SLOW_GATES entry silently tightens a gate instead of loosening it",
            '    "mutation coverage": 900,',
            '    "mutation coverage": 30,',
            "silently TIGHTENS a gate",
        ),
    ),
)
