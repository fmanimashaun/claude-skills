"""Mutation guard: check_layout_composition. Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_layout_composition",
    subject="scripts/check_layout_composition.py",
    selftest="scripts/check_layout_composition.py",
    needs=("scripts/source_text.py",),   # comments are blanked here (#1128)
    mutations=(
        Mutation(
            "hand-rolled clusters stop being reported",
            '    if "flex" not in classes:\n        return False',
            "    if True:\n        return False",
            "the hand-rolled cluster is reported",
        ),
        Mutation(
            # THE MUST-PASS HALF of rule 1. Ignore what the project already composes and the gate
            # flags correct code -- 20+ primitives' worth of it in one real app -- which is how a
            # gate earns an exclusion list on its first run.
            "an element already composing a primitive is flagged anyway",
            "    if any(c in declared for c in classes):\n        return False",
            "    if False:\n        return False",
            "an element already composing a primitive is NOT reported",
        ),
        Mutation(
            # Reading the project's OWN primitive names is what keeps this from imposing our
            # vocabulary. Hardcode ours and a project that renamed them is told it is wrong.
            "the project's declared primitives are ignored for our own list",
            "    return frozenset(found) if found else FALLBACK_PRIMITIVES",
            "    return FALLBACK_PRIMITIVES",
            "a project's OWN primitive name is honoured, not ours",
        ),
        Mutation(
            "breakpoint-driven layout stops being reported",
            "                if axis and not excused:",
            "                if False:",
            "a breakpoint that changes the layout axis is reported",
        ),
        Mutation(
            # THE OTHER SIDE of rule 2. Widen the variant to any breakpoint and `md:w-auto` --
            # which the doctrine PRESCRIBES for toolbar buttons -- becomes a finding.
            "the axis rule widens to any breakpoint, flagging prescribed sizing",
            r'AXIS_VARIANT = re.compile(r"^(?:sm|md|lg|xl|2xl):(?:flex-row|flex-col|grid-cols-\d+)$")',
            r'AXIS_VARIANT = re.compile(r"^(?:sm|md|lg|xl|2xl):")',
            "a SIZING breakpoint is not reported",
        ),
        Mutation(
            # The declared exception must be an exception, not a hole: with it always true, §3
            # stops being a justification anybody has to write down.
            "every element counts as a declared structural swap",
            "            excused = bool(SWAP_DECLARED.search(raw[n - 1])",
            "            excused = True or bool(SWAP_DECLARED.search(raw[n - 1])",
            "the SAME element without a declaration is still reported",
        ),
    Mutation(
        # The near-miss this fix actually hit: blanking comments for the MARKUP scan is right, and
        # blanking them for the DECLARATION is wrong, because `layout-swap:` lives in a comment on
        # purpose. Reading the stripped line here silently disables every opt-out.
        "the `layout-swap:` declaration is read from the blanked line, not the raw one",
        "            excused = bool(SWAP_DECLARED.search(raw[n - 1])",
        "            excused = bool(SWAP_DECLARED.search(line)",
        "a swap declared on the SAME line as the element is suppressed too",
    ),
    Mutation(
        # Comments are prose (#1128). Without this call the gate reports a file for DESCRIBING the
        # anti-pattern -- and the file that describes it is usually the one that fixed it.
        "comments are matched as if they were code",
        '        lines = strip_comments("\\n".join(raw)).split("\\n")',
        '        lines = list(raw)',
        'a comment quoting the old breakpoint markup is not that markup',
    ),
    ),
)
