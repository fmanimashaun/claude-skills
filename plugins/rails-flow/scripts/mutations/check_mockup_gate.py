"""Mutation guard: check_mockup_gate. Declared here, run by scripts/mutation_check.py (#1376).

Each mutation lets a user-visible change through with no approved mock-up, or holds work it should not.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_mockup_gate",
    subject="scripts/check_mockup_gate.py",
    selftest="scripts/check_mockup_gate.py",   # --selftest lives in the module itself
    needs=("scripts/classify_door.py",),
    mutations=(
        Mutation(
            "a UI change with no record passes",
            "    if not records:\n        return 1, [",
            "    if not records:\n        return 0, [",
            "a UI change with no mock-up record is held",
        ),
        Mutation(
            "views stop counting as UI scope",
            're.compile(r"^app/views/"), ',
            're.compile(r"^app/NEVER/"), ',
            "a view is UI scope",
        ),
        Mutation(
            "locale copy stops counting as user-visible",
            ',\n            re.compile(r"^config/locales/"))',
            ")",
            "a locale file (visible copy) is UI scope",
        ),
        # Its control: a JSON template is an API contract, not a screen.
        Mutation(
            "API templates are held as if they were screens",
            "and not NOT_UI.search(p)",
            "and True",
            "CONTROL: a JSON template is read by a client, not seen",
        ),
        Mutation(
            "an approval needs no link",
            "    if approval and not APPROVAL_URL.match(approval):",
            "    if False:",
            "an approval that is not a comment link is held",
        ),
        Mutation(
            "a desktop-only mock-up passes",
            "any(w <= 480 for w in widths) and any(w >= 1024 for w in widths)",
            "any(w >= 1024 for w in widths)",
            "a mock-up with no phone width is held",
        ),
        Mutation(
            "a mock-up file that does not exist passes",
            "    if mock and not mock.startswith(\"https://\") and not (root / mock).is_file():",
            "    if False:",
            "a mock-up file that does not exist is held",
        ),
        Mutation(
            "a record missing its approval line passes",
            '    out = [f"{rel}: no `{k}:` line" for k in RECORD_KEYS if not fields.get(k)]',
            "    out = []",
            "a record with no approval line is held",
        ),
        Mutation(
            "the opt-out is ignored, so a project that declared it off is still held",
            "    if declared_off(root):",
            "    if False:",
            "a project that declared the gate off is not held",
        ),
        # Its control: prose that mentions the key is not a declaration.
        Mutation(
            "any mention of the key reads as an opt-out",
            r'OPT_OUT = re.compile(r"^\s*(?:[-*]\s*)?`?mockup-gate:\s*off`?\s*$", re.M | re.I)',
            r'OPT_OUT = re.compile(r"mockup-gate:\s*off", re.M | re.I)',
            "CONTROL: prose mentioning the key is not a declaration",
        ),
    ),
)
