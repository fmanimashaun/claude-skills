"""Mutation guard: check_threat_model (#2117). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_threat_model",
    subject="scripts/check_threat_model.py",
    selftest="scripts/check_threat_model.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "a missing section stops being reported",
            "        if s.lower() not in heads:",
            "        if False:",
            "a missing section is found",
        ),
        Mutation(
            "a decision outside the four stops being reported",
            "                if decision.lower() not in DECISIONS:",
            "                if False:",
            "a row without a decision is found",
        ),
        Mutation(
            "an accept with no reason stops being reported",
            '                elif decision.lower() == "accept" and (not reason or _is_filler(reason)):',
            '                elif decision.lower() == "accept" and False:',
            "an accept without a reason is found",
        ),
        Mutation(
            "a STRIDE letter outside S T R I D E stops being reported",
            "                if not stride or stride[0].upper() not in STRIDE:",
            "                if False:",
            "a bad STRIDE letter is found",
        ),
        Mutation(
            "a file with no threat rows stops being unusable (exit 2) and reads as clean",
            "        if rows == 0:\n            print(f\"UNUSABLE",
            "        if False:\n            print(f\"UNUSABLE",
            "a file with no threat rows is exit 2",
        ),
        Mutation(
            "a placeholder left from the template stops being reported, so the unedited template passes",
            "    for ph in sorted({m_.group(0) for m_ in PLACEHOLDER.finditer(prose)}):",
            "    for ph in []:",
            "the unedited shipped template is refused",
        ),
        Mutation(
            "an empty section stops being reported",
            "        if s != \"Threats\" and not [ln for ln in lines if not _is_filler(ln.lstrip(\"-* \"))]:",
            "        if False:",
            "an empty section is found",
        ),
        Mutation(
            "a section with no bullet stops being reported",
            "            if not [b for b in bullets if not _is_filler(b)]:",
            "            if False:",
            "a boundaries section with no bullet is found",
        ),
        Mutation(
            "a filler word stops counting as filler",
            "    return cell.strip().strip(\".\").lower() in FILLERS",
            "    return False",
            "a filler threat is found",
        ),
    ),
)
