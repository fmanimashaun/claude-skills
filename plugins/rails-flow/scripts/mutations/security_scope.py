"""Mutation guard: security_scope (#2117). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="security_scope",
    subject="scripts/security_scope.py",
    selftest="scripts/security_scope.py",
    selftest_args=("--selftest",),
    # security_scope imports its sibling detect_stack (#2117: stack patterns come from the descriptor), so stage it too.
    needs=("scripts/detect_stack.py",),
    mutations=(
        Mutation(
            "the upload spelling stops matching, so an upload plan owes no threat model",
            'r"\\b(?:uploads?|csv|',
            'r"\\b(?:uplo4ds?|csv|',
            "an upload is a boundary",
        ),
        Mutation(
            # #2117: a stack's path rows (its descriptor's boundary_paths) stop being read, so a planned route file owes nothing.
            "a stack's boundary paths are never matched",
            '            if kind == "path" and name not in seen and (rx.search(path) or rx.search(path.rstrip("/") + "/")):',
            '            if False:',
            "a stack's boundary_paths loads and fires",
        ),
        Mutation(
            "a stack's boundary text is never matched, so a stack-only spelling owes nothing",
            '        if kind == "text" and name not in seen and (m := rx.search(text)):',
            '        if False and (m := rx.search(text)):',
            "a stack's boundary_text loads and fires",
        ),
        Mutation(
            "the trailing word boundary goes, so a word that merely starts with `role` fires",
            '|remember[- ]me|api (?:key|token))\\b", re.I)),',
            '|remember[- ]me|api (?:key|token))", re.I)),',
            "a word inside another word is not a match",
        ),
        Mutation(
            "no input at all stops being exit 2, so an unknown plan reads as no boundary",
            "    if not text.strip() and not args.path:",
            "    if False:",
            "no input at all is exit 2",
        ),
        Mutation(
            "import goes back to a bare word, so a plan that imports a helper module owes a model",
            "(?:bulk |data )import|imports? (?:an? |the |their |that |this )?(?:files?|csv|spreadsheets?|data|records?|rows?))",
            "(?:bulk |data )import|imports?)",
            "importing a helper module is not a boundary",
        ),
        Mutation(
            "the auth words stop needing a change verb, so a login page tweak owes a model",
            'r"\\b(?:add|adds|adding|new|change|',
            'r"\\b(?:|add|adds|adding|new|change|',
            "a login page css tweak is not a boundary",
        ),
        Mutation(
            "secrets stop being a boundary",
            '("secrets", re.compile(r"\\b(?:secrets?|credentials|',
            '("secrets", re.compile(r"(?!)\\b(?:secrets?|credentials|',
            "a secret is a boundary",
        ),
        Mutation(
            "input parsing stops being a boundary",
            '("input-parsing", re.compile(r"\\bparse[sd]?',
            '("input-parsing", re.compile(r"\\bparsx[sd]?',
            "parsing partner xml is a boundary",
        ),
        Mutation(
            "a privacy filter stops being a boundary",
            '|\\b(?:hide|restrict|mask|redact|limit)\\b',
            '|\\b(?:hidx|restrict|mask|redact|limit)\\b',
            "hiding a field from everyone else is a boundary",
        ),
        Mutation(
            "raw html stops being a boundary",
            '    ("raw-html", re.compile(r"\\braw\\b[^.\\n]{0,40}\\bhtml\\b|\\bhtml\\b[^.\\n]{0,40}\\braw\\b|\\b(?:skip|disable|turn off|without)\\s+sanitiz\\w*|\\bsanitiz\\w*\\s+(?:off|disabled)\\b|\\brender\\w*\\s+(?:the |a |an )?(?:partner|user|customer|external|supplied|uploaded|third[- ]party)(?:\'s|s\')?\\s+(?:raw )?html\\b", re.I)),',
            '    ("raw-html", re.compile(r"(?!)", re.I)),',
            "raw as a word beside html is a boundary",
        ),
        Mutation(
            "a redirect to a supplied url stops being a boundary",
            '    ("redirect-param", re.compile(r"\\breturn[_ ]url\\b|\\b(?:return_to|redirect_url|redirect_uri|back_url|next_url|return_path)\\b|\\b(?:next|return|redirect|back)\\s+param(?:eter)?s?\\b|\\bredirect\\w*[^.\\n]{0,40}\\bparams?\\b|\\bsend (?:them|the user|the person) back to (?:the |a )?(?:url|link|page) (?:in|from|they|the user)|\\bredirects? (?:back )?to (?:a |the )?(?:param|url the user|url (?:in|from) the)", re.I)),',
            '    ("redirect-param", re.compile(r"(?!)", re.I)),',
            "a return_to param is a boundary",
        ),
        Mutation(
            # #2117 adversary: `./app/...`, `b/app/...` and `app\\...` slipped past every stack path pattern.
            "planned paths are matched verbatim again",
            '    p = path.strip().replace("\\\\", "/")',
            '    return path',
            "a ./ path is matched",
        ),
        Mutation(
            "the diff prefixes stop being dropped",
            '            for prefix in ("./", "../", "a/", "b/"):',
            '            for prefix in ("./", "../"):',
            "a diff b/ path is matched",
        ),
        Mutation(
            "the newer auth verbs stop counting, so skipping authentication owes nothing",
            "|switch|migrate|skip|extend|generate|make)",
            "|switch|migrate)",
            "skipping authentication is a boundary",
        ),
        Mutation(
            "impersonation stops being an auth noun",
            "|impersonat\\w*|",
            "|",
            "impersonation is a boundary",
        ),
        Mutation(
            "the stderr note stops naming the stack rows used",
            '        notes.append(f"stack rows: {len(rows)} from {\', \'.join(labels)}" if rows else',
            '        notes.append("" if rows else',
            "the note names the rows used",
        ),
        Mutation(
            "a leading ../ is kept again",
            '            for prefix in ("./", "../", "a/", "b/"):',
            '            for prefix in ("./", "a/", "b/"):',
            "a ../ path is matched",
        ),
        Mutation(
            "a drive letter is kept again",
            '    p = re.sub(r"^[A-Za-z]:/", "", p)',
            '    pass',
            "a drive-letter path is matched",
        ),
        Mutation(
            "an absolute path is compared unresolved again, so a symlinked project root misses",
            '        for cand in (p, real):',
            '        for cand in (p,):',
            "an unresolved absolute path (a symlinked temp root) is matched",
        ),
        Mutation(
            "a stack's own cases run with case-sensitive paths again",
            '            rows = [(e["boundary"], kind, re.compile(e["pattern"], re.I), label)',
            '            rows = [(e["boundary"], kind, re.compile(e["pattern"], re.I if kind == "text" else 0), label)',
            "a stack's own cases run case-insensitively",
        ),
        Mutation(
            "stack rows load case-sensitive paths again",
            '                rows.append((entry["boundary"], kind, re.compile(entry["pattern"], re.I), label))',
            '                rows.append((entry["boundary"], kind, re.compile(entry["pattern"], re.I if kind == "text" else 0), label))',
            "a path in another case is matched",
        ),
        Mutation(
            "sign in with a provider stops being a boundary",
            "|sign(?:s|ing)?[- ]?in with|without (?:logging|signing) in)",
            ")",
            "sign in with a provider is a boundary",
        ),
        Mutation(
            "a dot-dot inside a path stops being collapsed",
            '        p = posixpath.normpath(p).lstrip("/") if p else p',
            '        p = p',
            "a dot-dot inside a path is collapsed",
        ),
        Mutation(
            "a directory named without its slash stops matching a directory row",
            '(rx.search(path) or rx.search(path.rstrip("/") + "/"))',
            'rx.search(path)',
            "a directory without its slash is matched",
        ),
        Mutation(
            "a bare `tokens` counts as an auth noun again, so design tokens owe a model",
            "|(?:access|auth|bearer|refresh|reset|session|login|api|magic[- ]link) tokens?|",
            "|(?:(?:access|auth|bearer|refresh|reset|session|login|api|magic[- ]link) )?tokens?|",
            "design tokens are not a boundary",
        ),
        Mutation(
            'a cases file with an extra key passes the shape check',
            '        if set(case) != set(CASE_KEYS):',
            '        if not set(CASE_KEYS) <= set(case):',
            'a case with an extra key is refused',
        ),
        Mutation(
            'types are not enforced, so a string boundary passes',
            '        wrong = [k for k, t in CASE_KEYS.items() if type(case[k]) is not t]',
            '        wrong = []',
            'a string boundary is refused',
        ),
        Mutation(
            'an empty path passes',
            'p.strip() for p in case["paths"])',
            'p for p in case["paths"])',
            'an empty path is refused',
        ),
        Mutation(
            'a repeated case name passes',
            '        if case["name"] in seen:',
            '        if False:',
            'a repeated name is refused',
        ),
        Mutation(
            'an empty cases list passes',
            '    if not isinstance(cases, list) or not cases:',
            '    if not isinstance(cases, list):',
            'an empty cases list is refused',
        ),
        Mutation(
            'a misshapen cases file is still run',
            '                continue\n            for case in cases:',
            '                pass\n            for case in cases:',
            'a stack whose cases break the shape fails without running them',
        ),
    ),
)
