"""Mutation guard: check_react_patterns. Declared here, run by scripts/mutation_check.py (#2222)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_react_patterns",
    subject="scripts/check_react_patterns.py",
    selftest="scripts/check_react_patterns.py",
    mutations=(
        Mutation(
            "a client route file is never reported",
            "    if in_app and client and stem in ROUTE_FILES and not CLIENT_ROUTE_DECLARED.search(raw):",
            "    if False:",
            "a client layout is reported",
        ),
        Mutation(
            "a declaration with no reason passes",
            r'CLIENT_ROUTE_DECLARED = re.compile(r"react-architecture:[ \t]*client-route[ \t]*(?:--|—|:)[ \t]*\S")',
            r'CLIENT_ROUTE_DECLARED = re.compile(r"react-architecture:[ \t]*client-route")',
            "a declaration with no reason does not pass",
        ),
        Mutation(
            "route files are judged anywhere, not only under app/",
            "        in_app = any(app in path.parents for app in apps)",
            "        in_app = True",
            "OUTSIDE app/ is not a route file",
        ),
        Mutation(
            "the directive is found anywhere in the file, comments included",
            "    client = has_client_directive(raw)",
            '    client = "use client" in raw',
            "the directive inside a comment is not a directive",
        ),
        Mutation(
            "fetch inside an effect is never reported",
            '            if re.search(r"\\bfetch\\s*\\(", body):',
            "            if False:",
            "a fetch in an effect with no cleanup is reported",
        ),
        Mutation(
            "a protocol-relative URL counts as internal",
            r'''INTERNAL_ANCHOR = re.compile(r"""<a\b[^>]*\bhref\s*=\s*\{?\s*(['"`])/(?!/)""")''',
            r'''INTERNAL_ANCHOR = re.compile(r"""<a\b[^>]*\bhref\s*=\s*\{?\s*(['"`])/""")''',
            "a protocol-relative anchor is not internal",
        ),
        Mutation(
            "a project with no app/ directory is judged clean",
            '        raise NotApplicable(f"{project}: no app/ or src/app/ directory -- not an App Router project")',
            "        return []",
            "NOT APPLICABLE",
        ),
        Mutation(
            "a not-applicable project exits 0, reading as a pass",
            '        print(f"check_react_patterns: not applicable -- {exc}")\n        return 3',
            '        print(f"check_react_patterns: not applicable -- {exc}")\n        return 0',
            "must exit 3, not applicable",
        ),
    ),
)
