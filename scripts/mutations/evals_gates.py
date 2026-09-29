"""Mutation guard: the doctrine-effect benchmark's gates. Declared here, run by scripts/mutation_check.py.

The mutations that matter make a case VACUOUS: it passes before the agent writes anything, adds the
same PASS to every arm, and pulls the comparison toward "no difference" (#1374). Both preconditions
are guarded twice -- by their own rule fixtures and by the case-level untouched-scaffold invariant.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="evals_gates",
    subject="evals/gates.py",
    selftest="evals/selftest.py",
    deps=("evals/run.py", "evals/scaffold.py"),
    needs=("evals/suite.json", ".claude-plugin/marketplace.json"),
    mutations=(
        # Case 01's old precondition: any controller counts, and the scaffold ships one.
        Mutation(
            "scoped-index treats any controller as an attempt, so the scaffold's own passes",
            "    if not attempted:\n",
            "    if not files:\n",
            "only the scaffold's ApplicationController (#1374)",
        ),
        Mutation(
            "ui-component-present never fires, so case 03 passes on no work",
            '                    "so the task was not attempted")]\n\n\n',
            '                    "so the task was not attempted")][:0]\n\n\n',
            "case 03-role-tokens PASSES on the untouched scaffold",
        ),
        # The exempt component must not satisfy the precondition, or writing only Ui::Logo passes.
        Mutation(
            "Ui::Logo counts as the requested component",
            "        if rel(path, workspace).lower() in _LOGO_EXEMPT_PATHS:\n            continue\n"
            "        if any(_CLASS_DEF",
            "        if any(_CLASS_DEF",
            "only the exempt Ui::Logo",
        ),
        # One silencing break per remaining rule: each one leaves a gate that runs, prints PASS, and
        # measures nothing, so every arm scores the same on that case.
        Mutation(
            "simple-form-convention stops seeing form_with",
            "            if _FORM_WITH.search(line):\n",
            "            if False:\n",
            "one raw form_with beside simple_form_for",
        ),
        Mutation(
            "no-inline-dark never matches a dark: utility",
            "            for match in _DARK_UTILITY.finditer(line):\n",
            "            for match in ():\n",
            "inline dark: utility in a component",
        ),
        Mutation(
            "no-literal-color never matches a hex literal",
            "            for match in _HEX.finditer(line):\n",
            "            for match in ():\n",
            "literal hex in a component",
        ),
        Mutation(
            "job-idempotent accepts a job with no re-run guard",
            "        if not _IDEMPOTENCE_MARKER.search(body):\n",
            "        if False:\n",
            "unguarded create on every retry",
        ),
        Mutation(
            "spec-accompanies-behavior treats every concern as specced",
            "        if expected in spec_names:\n            continue\n",
            "        if True:\n            continue\n",
            "concern with no spec",
        ),
        Mutation(
            "stimulus-discipline stops seeing document queries",
            "            if _DOC_QUERY.search(code):\n",
            "            if False:\n",
            "document.querySelector instead of a target",
        ),
    ),
)
