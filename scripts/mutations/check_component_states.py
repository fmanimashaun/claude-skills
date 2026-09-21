"""Mutation guard: check_component_states. Declared here, run by scripts/mutation_check.py (#1068).

The check asserts that every catalogue row DECLARES its six states. These prove it can fail -- and
the first four matter more than usual, because the natural way to write this check is a grep for six
words, which passes on prose that makes no claim at all. A guard that only proved "the script runs"
would certify exactly that implementation.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_component_states",
    subject="scripts/check_component_states.py",
    selftest="scripts/check_component_states.py",
    # The selftest READS the real catalogue -- on purpose: fixtures prove the parser, and only the
    # real file proves the rule. Without this the staged mutant has no catalogue, the unmutated
    # selftest dies of FileNotFoundError, and every mutation below reads as "caught" whether or not
    # it broke anything. The runner refused the guard as INERT on the first run, which is the
    # harness catching exactly the defect this guard exists to catch.
    needs=("skills/design-system/references/components.md",),
    mutations=(
        # The completeness half. Without it a row may name one state and stop.
        Mutation(
            "a missing slot stops being a finding, so a row naming one state passes",
            '            out.append(f"does not name {slot!r}")',
            "            pass",
            "a declaration missing 'loading' fails",
        ),
        # The escape hatch's lock. A bare `n/a` is how 43 rows would be 'fixed' in an afternoon.
        Mutation(
            "a bare n/a is accepted, turning the escape hatch into a loophole",
            '            out.append(f"{slot!r} is \'n/a\' with no reason")',
            "            pass",
            "a bare n/a is refused",
        ),
        # The reason this is not a line-based reader. The one row that already declared its states
        # wrapped across two lines; a reader that stops at the newline drops `loading` from it.
        Mutation(
            "the declaration is truncated at the first line break again",
            "            if i and (raw.startswith((\"- \", \"#\", \"```\")) or not raw.strip()):",
            "            if i:",
            "'Button' declaration was truncated at the line break",
        ),
        # Both halves of the ratchet. Neither alone is one.
        Mutation(
            "the floor stops refusing a drop, so a declaration can be deleted unnoticed",
            "    if declared < floor:",
            "    if False:",
            "a drop below the floor fails",
        ),
        Mutation(
            "unrecorded growth stops being refused, so the floor goes stale and protects nothing",
            "    elif declared > floor:",
            "    elif False:",
            "unrecorded growth fails",
        ),
        # The exemption must come from the FILE, not from the script deciding what looks like prose.
        Mutation(
            "every section becomes exempt, so the whole catalogue passes vacuously",
            "        if row.exempt:",
            "        if True:",
            "a complete declaration passes",
        ),
        # A section cannot be both. Without this, marking a row not-a-component while it declares
        # states leaves two contradictory claims and the check reads only one of them.
        Mutation(
            "a section may be exempt AND declare states at the same time",
            "            if MARKER in row.body:",
            "            if False:",
            "may not be exempt and declare states at once",
        ),
    ),
)
