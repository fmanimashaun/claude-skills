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
            "                elif not target.is_file():",
            "                elif False:",
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
            r'RECOVERY_CODE = re.compile(r"\b(?=[a-z0-9-]*[a-z])(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)',
            r'RECOVERY_CODE = re.compile(r"\b(?=[a-z0-9-]*[a-z])[a-z0-9]{4,6}-[a-z0-9]{4,6}\b", re.I)',
            "secrets: screenshot names beside the word recovery are not codes",
        ),
        Mutation(
            "the recovery-code pattern loses its letter requirement, so request references read as codes",
            r'RECOVERY_CODE = re.compile(r"\b(?=[a-z0-9-]*[a-z])(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)',
            r'RECOVERY_CODE = re.compile(r"\b(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)',
            "secrets: numeric request references are not recovery codes",
        ),
        Mutation(
            "codes listed one per line are not counted",
            "        if len(RECOVERY_CODE.findall(line)) >= 3 or listed >= 3:",
            "        if len(RECOVERY_CODE.findall(line)) >= 3:",
            "secrets: recovery codes one per line fail",
        ),
        Mutation(
            "a key printed in groups of four is not recognised",
            r'                           r"((?:[A-Z2-7]{4}[ -]?){3}[A-Z2-7]{4,}|[A-Z2-7]{16,})\b")',
            r'                           r"([A-Z2-7]{16,})\b")',
            "secrets: a grouped base32 key fails",
        ),
        Mutation(
            "the secret itself becomes case-insensitive, so prose after key: reads as a secret",
            'BASE32_SECRET = re.compile(r"(?i:\\b(?:secret|key|seed|totp)\\b)[^A-Za-z0-9\\n]{0,4}"',
            'BASE32_SECRET = re.compile(r"(?i)\\b(?:secret|key|seed|totp)\\b[^A-Za-z0-9\\n]{0,4}"',
            "secrets: lower-case prose after key: is not a secret",
        ),
        Mutation(
            "zTXt chunks are not read",
            '        elif kind == b"zTXt":',
            '        elif kind == b"__none__":',
            "secrets: a zTXt chunk is read",
        ),
        # #1437 review blocker: evidence outside qa/manual-tests/ let a stamp carry code.
        Mutation(
            "evidence paths are not confined to qa/manual-tests/",
            "        if not evidence_path_ok(value):",
            "        if False:",
            "outside the evidence root is refused",
        ),
        Mutation(
            "uncommitted evidence is accepted",
            "        if not tracked(base, rel):",
            "        if False:",
            "stamp: uncommitted evidence is refused",
        ),
        Mutation(
            "a malformed schema is grandfathered like an old stamp",
            '    if "schema" in data:',
            '    if False:',
            "is refused, not grandfathered",
        ),
        Mutation(
            "a screenshot outside the folder counts as evidence",
            "                if Path(name).is_absolute() or folder.resolve() not in target.parents:",
            "                if False:",
            "first-boot: a screenshot outside the folder is not evidence",
        ),
        Mutation(
            "a target merely containing the root role counts as root",
            '    if not any(root_word.search(row.get("target_role", "")) for row in rows):',
            '    if not any(root_role.lower() in row.get("target_role", "").lower() for row in rows):',
            "authz: a target merely containing 'root' is not root",
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
            '    if not any(root_word.search(row.get("target_role", "")) for row in rows):',
            "    if False:",
            "authz: no row targeting root fails",
        ),
        # The stamp: a schema-2 stamp must name its evidence, and the window must be able to close.
        # The realistic slip: a new stamp with no evidence is waved through as if it were old.
        Mutation(
            "a schema-2 stamp naming no evidence is grandfathered as if it were old",
            "    elif grandfather:",
            '    if not data.get("first_boot") and grandfather:',
            "stamp: a schema-2 stamp naming no evidence is refused",
        ),
        Mutation(
            "the grandfather window can never close",
            "    elif grandfather:",
            "    elif True:",
            "stamp: an old stamp is refused once grandfathering is off",
        ),
        Mutation(
            "a boolean schema reads as schema 2",
            "        if not (isinstance(schema, int) and not isinstance(schema, bool) and schema >= STAMP_SCHEMA):",
            "        if not (isinstance(schema, int) and schema >= 1):",
            "stamp: schema True is refused",
        ),
        Mutation(
            "the evidence paths are printed to stderr, so the release gate reads none",
            '                    print("\\n".join(paths))        # the release gate reads these',
            '                    print("\\n".join(paths), file=sys.stderr)',
            "stamp: both layers passing -> 0 and the evidence paths on stdout",
        ),
    ),
)
