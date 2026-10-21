"""Mutation guard: check_architecture_rules. Declared here, run by scripts/mutation_check.py (#2220).

The check refuses a rule row on the interface-architecture page that has no existing basis. A guard
that only proved "the script runs" would certify a check that reads nothing, so every mutation turns
one refusal off and names the fixture that must notice.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_architecture_rules",
    subject="scripts/check_architecture_rules.py",
    selftest="scripts/check_architecture_rules.py",
    selftest_args=("--selftest",),
    needs=(),
    mutations=(
        Mutation(
            "a check path that is not a file stops being a finding",
            '        if kind == "check" and not (root / ref).is_file():',
            '        if False:',
            "a missing check path is refused",
        ),
        Mutation(
            "a claim that is not CONFIRMED stops being a finding",
            '            elif verdict != "CONFIRMED":',
            '            elif False:',
            "an INCONCLUSIVE claim is refused",
        ),
        Mutation(
            "every claim verdict reads as CONFIRMED",
            '"CONFIRMED" if re.match(r"(C|CONFIRMED)\\b", m.group(2)) else m.group(2)',
            '"CONFIRMED"',
            "an INCONCLUSIVE claim is refused",
        ),
        Mutation(
            "a claim with no verdict row stops being a finding",
            '            if verdict is None:',
            '            if False:',
            "an unknown claim is refused",
        ),
        Mutation(
            "a decision that is not recorded stops being a finding",
            '        elif kind == "decision" and ref not in decided:',
            '        elif False:',
            "an unrecorded decision is refused",
        ),
        Mutation(
            "a duplicate rule id stops being a finding",
            '        if rid in seen_ids:',
            '        if False:',
            "a duplicate id is refused",
        ),
        Mutation(
            "an unknown layer stops being a finding",
            '        if layer not in LAYERS:',
            '        if False:',
            "an unknown layer is refused",
        ),
        Mutation(
            "a layer with no rule stops being a finding",
            '        if rows and layer not in layers_seen:',
            '        if False:',
            "a layer left empty is refused",
        ),
        Mutation(
            "a page that yields no rows stops being a finding",
            '    if not rows:',
            '    if False:',
            "a page with no rows is refused",
        ),
    ),
)
