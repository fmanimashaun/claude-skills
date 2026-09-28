"""Mutation guard: release_evidence (#1428). Declared here, run by scripts/mutation_check.py.

Each mutation re-opens the gap the downstream release escaped through: an unwalked step with no
reason, a HOLE or UI-only protection read as passing, a sweep that never targets root, a
second-factor secret committed, or an old stamp let through after the grandfather window closes.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="release_evidence",
    subject="scripts/release_evidence.py",
    selftest="scripts/release_evidence.py",
    mutations=(
        # THE ESCAPED DEFECT: the root row was Blocked, with no reason, and never re-run.
        Mutation(
            "a Blocked or Not walked row passes with no documented reason",
            '        elif status in UNWALKED and not row.get("Notes"):',
            '        elif status in UNWALKED and False:',
            "first-boot: Blocked with no reason fails",
        ),
        Mutation(
            "a Fail row need not name its filed issue",
            '        elif status == "fail" and not row.get("Issue"):',
            '        elif False:',
            "first-boot: a Fail with no filed issue fails",
        ),
        Mutation(
            "the phone width is not required",
            "    if not any(w <= PHONE_MAX for w in widths):",
            "    if False:",
            "first-boot: no phone width fails",
        ),
        Mutation(
            "a missing screenshot is not noticed",
            "                if not (folder / name).is_file():",
            "                if False:",
            "first-boot: a named screenshot that is missing fails",
        ),
        Mutation(
            "PNG text chunks are not read, so a secret in image metadata passes",
            "            text = png_text(path.read_bytes())",
            '            text = ""',
            "secrets: an otpauth URI in a PNG tEXt chunk fails",
        ),
        Mutation(
            "the recovery-code pattern loses its digit requirement, so screenshot names read as codes",
            r'RECOVERY_CODE = re.compile(r"\b(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)',
            r'RECOVERY_CODE = re.compile(r"\b[a-z0-9]{4,6}-[a-z0-9]{4,6}\b", re.I)',
            "secrets: screenshot names beside the word recovery are not codes",
        ),
        # THE OTHER ESCAPED DEFECT: authorization tested by action, never by target.
        Mutation(
            "a HOLE is read as passing",
            '        elif verdict == "HOLE":\n            findings.append(',
            '        elif verdict == "HOLE":\n            (',
            "authz: a HOLE fails",
        ),
        Mutation(
            "a hidden-but-unenforced control counts as a guard",
            '        elif verdict == "UI-ONLY":\n            findings.append(',
            '        elif verdict == "UI-ONLY":\n            (',
            "authz: a UI-ONLY protection fails",
        ),
        Mutation(
            "the sweep need not target root",
            '    if not any(root_role.lower() in row.get("target_role", "").lower() for row in rows):',
            "    if False:",
            "authz: no row targeting root fails",
        ),
        # The stamp: a schema-2 stamp must name its evidence, and the window must be able to close.
        # The realistic slip: a new stamp with no evidence is waved through as if it were old.
        Mutation(
            "a schema-2 stamp naming no evidence is grandfathered as if it were old",
            "    if not current and grandfather:",
            '    if (not current or not data.get("first_boot")) and grandfather:',
            "stamp: a schema-2 stamp naming no evidence is refused",
        ),
        Mutation(
            "the grandfather window can never close",
            "    if not current and grandfather:",
            "    if not current:",
            "stamp: an old stamp is refused once grandfathering is off",
        ),
        Mutation(
            "a boolean schema reads as schema 2",
            "    current = isinstance(schema, int) and not isinstance(schema, bool) and schema >= STAMP_SCHEMA",
            "    current = isinstance(schema, int) and schema >= 1",
            "stamp: schema true is not schema 2",
        ),
        Mutation(
            "the evidence paths are printed to stderr, so the release gate reads none",
            '                    print("\\n".join(paths))        # the release gate reads these',
            '                    print("\\n".join(paths), file=sys.stderr)',
            "stamp: both layers passing -> 0 and the evidence paths on stdout",
        ),
    ),
)
