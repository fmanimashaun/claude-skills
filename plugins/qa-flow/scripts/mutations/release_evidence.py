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
        # #1493: a fixture commit's detached `git maintenance` raced the temp-dir cleanup.
        Mutation(
            'the control detaches its maintenance run -- the race, reintroduced (review of PR #1511)',
            '                "-c", "maintenance.auto=true", "-c", "maintenance.autoDetach=false", "-c", "gc.autoDetach=false"]',
            '                "-c", "maintenance.auto=true"]',
            'cleanup CONTROL: with auto-maintenance on, a commit runs it -- in the foreground, never detached',
        ),
        Mutation(
            "the fixture's git starts background maintenance again -- the #1493 root cause",
            'FIXTURE_GIT = ("-c", "user.email=t@t", "-c", "user.name=t", "-c", "maintenance.auto=false", "-c", "gc.auto=0",',
            'FIXTURE_GIT = ("-c", "user.email=t@t", "-c", "user.name=t",',
            'cleanup: a fixture commit starts no background maintenance or gc',
        ),
        Mutation(
            'a cleanup error crashes the selftest again',
            '    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)',
            '    return tempfile.TemporaryDirectory(ignore_cleanup_errors=False)',
            'cleanup: a directory still being written at cleanup does not crash the selftest',
        ),
        # ROUND 3 (second pass) BLOCKER: last release's evidence, renamed, passed because the copy
        # check only saw evidence still at dev. main is the last published release.
        Mutation(
            "the published release is never consulted",
            "        if published:\n            for key, record in",
            "        if False:\n            for key, record in",
            "stamp: last release's evidence, git-mv'd to this release's name, is refused",
        ),
        Mutation(
            "a record already on main by PATH is accepted",
            "    if record in shipped:",
            "    if False:",
            "stamp: a new stamp re-declaring the published version is refused",
        ),
        Mutation(
            "a record byte-identical to a published one is accepted",
            "        if own and oid == own:",
            "        if False:",
            "stamp: last release's evidence, git-mv'd to this release's name, is refused",
        ),
        # ROUND 3 BLOCKER: a newline in an evidence path smuggled a second path into the gate's
        # line-by-line allowance.
        Mutation(
            "control characters are allowed in evidence paths",
            "    if CONTROL.search(value):\n        return False",
            "    if False:\n        return False",
            "evidence_path_ok refuses 'qa/manual-tests/x",
        ),
        Mutation(
            "only the stripped path is checked, so a control character strip() removes slips by",
            "        if not evidence_path_ok(value) or CONTROL.search(data[key]):",
            "        if not evidence_path_ok(value):",
            "first_boot='qa/manual-tests/first-boot-v1\\r' outside the evidence root is refused",
        ),
        Mutation(
            "evidence need not be named for the stamp's release",
            "        elif not same_release(key, value, version):",
            "        elif False:",
            "stamp: evidence named for another release is refused",
        ),
        Mutation(
            "a renamed copy of another release's evidence is accepted",
            "            twin = copied_from(base, rev, value, prefix)",
            "            twin = None",
            "stamp: last release's walkthrough, renamed, is refused as a copy",
        ),
        Mutation(
            "at --rev the stamp is read from the working tree",
            "        if rev:\n            # The STAMP is read as committed at `rev` too",
            "        if False:\n            # The STAMP is read as committed at `rev` too",
            "stamp: at --rev the committed stamp is judged, not the working-tree one",
        ),
        # ROUND 3 FOLD-IN 1: grandfathering must not be spoofable by omitting `schema`.
        Mutation(
            "any schema-less stamp is grandfathered, whenever it was committed",
            "        if when is not None and when < cutoff:",
            "        if True:",
            "stamp: a NEW stamp that merely omits schema is refused",
        ),
        Mutation(
            "the cutoff itself counts as before",
            "        if when is not None and when < cutoff:",
            "        if when is not None and when <= cutoff:",
            "stamp: a schema-less stamp committed AT the cutoff is refused",
        ),
        Mutation(
            "a working-tree edit of an old stamp keeps its commit date",
            "                if head.returncode != 0 or head.stdout != raw:",
            "                if head.returncode != 0:",
            "stamp: an old stamp edited in the working tree is not the committed one",
        ),
        # A finding is printed; one that quoted the matched secret would leak it again.
        Mutation(
            "a finding quotes the matched secret",
            '        found.append("an otpauth:// URI")',
            '        found.append("an otpauth:// URI " + text)',
            "secrets: no finding quotes the secret it found",
        ),
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
            r'r"((?:[A-Z2-7]{4}[ -]?){3}[A-Z2-7]{4,}|(?:[a-z2-7]{4}[ -]){3}',
            r'r"((?:[a-z2-7]{4}[ -]){3}',
            "secrets: a grouped base32 key fails",
        ),
        Mutation(
            "the secret itself becomes case-insensitive, so prose after key: reads as a secret",
            'BASE32_SECRET = re.compile(r"(?i:\\b(?:secret|key|seed|totp)\\b)[^A-Za-z0-9\\n]{0,8}',
            'BASE32_SECRET = re.compile(r"(?i)\\b(?:secret|key|seed|totp)\\b[^A-Za-z0-9\\n]{0,8}',
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
            "    return (value.startswith(EVIDENCE_ROOT) and not Path(value).is_absolute()",
            "    return (True and not Path(value).is_absolute()",
            "evidence_path_ok refuses 'docs/manual-tests",
        ),
        Mutation(
            "--rev is ignored, so the gate judges the working tree",
            "        if rev:\n            findings += committed_tree(",
            "        if False:\n            findings += committed_tree(",
            "stamp: uncommitted evidence is refused at --rev",
        ),
        Mutation(
            "a symlink in the committed evidence is followed",
            "    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:\n        for member in tar.getmembers():",
            '    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:\n        tar.extractall(dest, filter="fully_trusted")\n        for member in []:',
            "stamp: a committed symlink into code is not evidence",
        ),
        Mutation(
            "a printed finding quotes a cell that holds a secret",
            '    return "<redacted: looks like a second-factor secret>" if leak_reasons(text) else text',
            "    return text",
            "secrets: a secret in a quoted cell is redacted in the finding",
        ),
        Mutation(
            "a key need not carry a digit, so an upper-case legend reads as a key",
            '    if any(re.search(r"[2-7]", m.group(1)) for m in BASE32_SECRET.finditer(text)):',
            "    if BASE32_SECRET.search(text):",
            "secrets: an upper-case legend with no digit is not a key",
        ),
        Mutation(
            "a lower-case grouped key is not recognised",
            r'|(?:[a-z2-7]{4}[ -]){3}[a-z2-7]{4,}|',
            r'|',
            "secrets: a key lower-case grouped fails",
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
