"""Mutation guard: check_security_review (#2119). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_security_review",
    subject="scripts/check_security_review.py",
    selftest="scripts/check_security_review.py",
    selftest_args=("--selftest",),
    needs=("scripts/check_threat_model.py", "scripts/classify_door.py", "scripts/risky_diff.py"),
    mutations=(
        Mutation(
            "a record for an earlier commit stops being refused",
            '    if kind in ("missing", "no-head", "stale", "no-verdict"):',
            '    if kind in ("missing", "no-head", "no-verdict"):',
            "a record for another commit is stale",
        ),
        Mutation(
            "a mitigate row answered `not implemented` stops being BLOCKING",
            '            if verdict == "not implemented":',
            "            if False:",
            "a mitigate row not implemented is BLOCKING, exit 3",
        ),
        Mutation(
            "evidence past the end of the file is accepted",
            "> len(f.read_text(encoding=\"utf-8\", errors=\"replace\").splitlines()):",
            "> 10**9:",
            "evidence past the end of the file is incomplete",
        ),
        Mutation(
            "a stale accept row stops being a finding",
            '            if verdict == "stale":',
            "            if False:",
            "a stale accept row is a finding, exit 3",
        ),
        Mutation(
            "a row the record leaves out stops being incomplete",
            '        if got is None:\n            incomplete.append(f"{label}: no answer in the record")\n            continue',
            "        if got is None:\n            continue",
            "a mitigate row with no answer is incomplete",
        ),
        Mutation(
            "a record that answers a row the model lacks is accepted",
            "    for n in sorted(set(answers) - known):",
            "    for n in []:",
            "a row the model does not have is another model",
        ),
        Mutation(
            "a model with no readable table stops being exit 2",
            "    if not threat_rows(model_text):",
            "    if False:",
            "an unreadable model is exit 2",
        ),
    ),
)
