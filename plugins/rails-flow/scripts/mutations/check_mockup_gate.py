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
            '            re.compile(r"^config/locales/"),\n',
            "",
            "a locale file (visible copy) is UI scope",
        ),
        # Its control: a JSON template is an API contract, not a screen.
        Mutation(
            "API templates are held as if they were screens",
            "or not NOT_UI.search(p)",
            "or True",
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
            '    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):',
            "    elif False:",
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
        # Pre-release review of #1381.
        Mutation(
            "public error pages and icons stop counting as UI scope",
            '            re.compile(r"^public/[^/]+\\.(html|png|svg|ico|webmanifest)$"))',
            '            re.compile(r"^NEVER/"))',
            "a public error page is UI scope",
        ),
        Mutation(
            "the PWA manifest is dropped as an API template",
            "                  and (SEEN_ANYWAY.match(p) or not NOT_UI.search(p)))",
            "                  and not NOT_UI.search(p))",
            "the PWA manifest is UI scope although it is JSON",
        ),
        Mutation(
            "a bare https:// counts as a mock-up",
            '        if not re.match(r"^https://[^/\\s]+\\.[^/\\s]+", mock):',
            "        if False:",
            "a bare https:// is not a mock-up",
        ),
        Mutation(
            "any repo file counts as a mock-up",
            '    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):',
            "    elif mock and not (root / mock).is_file():",
            'an arbitrary NON-Markdown repo file outside the folder is not a mock-up',
        ),
        Mutation(
            "a record need not name its issue",
            "    if issue and not ISSUE_REF.match(issue):",
            "    if False:",
            "a record that names no issue is held",
        ),
        Mutation(
            "a README in the records folder is judged as a record",
            '                                             and Path(p).name.lower() != "readme.md")',
            "                                             )",
            "CONTROL: a README in the records folder is not a record",
        ),
        Mutation(
            "a fenced example of the opt-out line turns the gate off",
            '    return bool(OPT_OUT.search(unfenced(g.read_text(encoding="utf-8"))))',
            '    return bool(OPT_OUT.search(g.read_text(encoding="utf-8")))',
            "a fenced example of the opt-out line is not a declaration",
        ),
        Mutation(
            # #1430
            'an unterminated fence no longer runs to the end of the file, so its opt-out counts',
            '        if run:\n            fence = run\n            continue',
            '        if run and False:\n            fence = run\n            continue',
            'an opt-out inside an unterminated fence is not a declaration',
        ),
        Mutation(
            # #1430
            'a record may name itself as its mock-up again',
            '    elif mock and ((root / mock).resolve() == path.resolve()\n                   or ((root / mock).exists() and (root / mock).samefile(path))):',
            '    elif False:',
            'a record naming itself is held',
        ),
        Mutation(
            # #1430
            'an .svg is not a mock-up file',
            'MOCK_FILE = re.compile(r"\\.(html?|png|jpe?g|webp|pdf|svg)$", re.I)',
            'MOCK_FILE = re.compile(r"\\.(html?|png|jpe?g|webp|pdf)$", re.I)',
            'an .svg mock-up OUTSIDE the records folder is a mock-up file',
        ),
        Mutation(
            # review of PR #1478
            'a record may name another record (or a symlink onto one) as its mock-up',
            '    elif mock and (root / mock).resolve().suffix.lower() == ".md":',
            '    elif False:',
            'a record naming another record is held',
        ),
        Mutation(
            # final review of PR #1478
            'a code span at line start opens a fence again, swallowing the opt-out below it',
            '        m = re.match(r"^\\s*(`{3,})(?=[^`]*$)|^\\s*(~{3,})", line)',
            '        m = re.match(r"^\\s*(`{3,})|^\\s*(~{3,})", line)',
            'a code span at line start does not fence the opt-out',
        ),
        # #1479 (after #1478): the remainder #1478 did not cover.
        Mutation(
            'a hard link to the record is not the record',
            '                   or ((root / mock).exists() and (root / mock).samefile(path))):',
            '                   or False):',
            'a record naming itself by another name is held',
        ),
    ),
)
