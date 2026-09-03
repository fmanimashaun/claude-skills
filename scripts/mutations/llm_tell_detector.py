"""Mutation guard: llm_tell_detector. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# design-flow #107. A conformance linter's whole risk is FALSE POSITIVES — one that fires on
# correct input is switched off, and then catches nothing — so roughly half of these break a
# CARVE-OUT rather than a rule, and are expected to be caught by a fixture whose job is to stay
# silent. Two of them exist because running the collector against a real page found the defect
# first: corners counted as elements, and an inline-link exemption wide enough to swallow every
# native <button>.
GUARD = Guard(
    name="llm_tell_detector",
    subject="plugins/design-flow/scripts/llm_tell_detector.py",
    selftest="plugins/design-flow/scripts/llm_tell_detector.py",
    # It IMPORTS `rendered_conformance` for the shared palette-step definition (#157 criterion
    # 7), so without this every mutant dies at import and each mutation reads as "caught" by a
    # traceback rather than by the fixture named below.
    needs=("plugins/design-flow/scripts/doctrine_path.py",
           "plugins/design-flow/scripts/rendered_conformance.py",
           "plugins/design-flow/scripts/conformance_collector.js"),
    mutations=(
        # #782. The rule fired on the exact form its own message tells you to use, on every
        # save via the PostToolUse hook. Four clauses: the value anchor, the shorthand branch,
        # the @font-face exemption, and that the block CLOSES.
        Mutation(
            "the pattern goes back to matching any font-family declaration",
            r'font(?:-family)?\s*:(?![^;}]*var\()',
            r"font-family\s*:",
            "the shorthand hides a literal too",
        ),
        Mutation(
            # Dropping `(?:-family)?` leaves `font:` unchecked -- a silent path for a genuine
            # literal, which is what it was before this fix.
            "the shorthand branch is dropped, so `font:` hides a literal again",
            r'font(?:-family)?\s*:(?![^;}]*var\()',
            r'font-family\s*:(?![^;}]*var\()',
            "the shorthand hides a literal too",
        ),
        Mutation(
            # A self-hosted @font-face MUST name a literal family; without the exemption this
            # rule and `cdn-font-link` demand opposite things.
            "the @font-face exemption goes, so self-hosting trips the rule",
            "        if in_font_face and rule.name in FONT_FACE_RULES:",
            "        if False:",
            "...and so does the multi-line form, declaration not first",
        ),
        Mutation(
            # The widest possible false negative: everything after the first @font-face would
            # be exempt for the rest of the file. The multi-line fixture alone did not see it.
            "the @font-face block never closes",
            '        return "}" not in line.split("@font-face", 1)[1], True',
            "        return True, True",
            "...and after a ONE-LINE @font-face too",
        ),
        # #758. The rule and its carve-out are separate clauses; each needs its own fixture.
        Mutation(
            # Two alternations, two mutations: emptying one leaves the other matching, so
            # a single mutation would be caught by whichever fixture it happened to kill.
            "the var() shape stops being caught",
            '                       r"|var\\(\\s*--color-fm-[a-z0-9-]+\\s*\\)"),',
            '                       r""),',
            "through var() in an inline style",
        ),
        Mutation(
            "the utility shape stops being caught",
            '            re.compile(r"\\b(?:" + "|".join(COLOUR_UTILITIES) + r")-fm-[a-z0-9-]+\\b"',
            '            re.compile(r"(?!x)x"',
            "a brand primitive as a text utility",
        ),
        Mutation(
            # Without the carve-out it fires on a pack BINDING a role -- correct work.
            "the declaration carve-out is dropped, so binding a role reads as misuse",
            "    return before.endswith(\"--\") or bool(TOKEN_DEFINITION.search(before))",
            "    return False",
            "silent when a role BINDS the primitive",
        ),

        # #738. A CDN font link is preview scaffolding from a design export. Both real Claude
        # Design artboards carry one, and nothing detected it.
        Mutation(
            "a CDN font link stops being a tell, so a design export ships one",
            '            re.compile(r"fonts\\.googleapis\\.com|fonts\\.gstatic\\.com"),',
            '            re.compile(r"(?!x)x"),',
            "a Google Fonts stylesheet link",
        ),
        Mutation(
            # Matching only the stylesheet host would miss the preconnect and the font files.
            "only the stylesheet host matches, so the font-file host slips through",
            'r"fonts\\.googleapis\\.com|fonts\\.gstatic\\.com"',
            'r"fonts\\.googleapis\\.com"',
            "a preconnect to the font FILE host",
        ),
        Mutation(
            # The gap that let this rule land unfixtured in the first place.
            "a rule with no fixture stops being reported, so the suite reads green over it",
            "    return sorted(set(names if names is not None else BY_NAME) - exercised)",
            "    return []",
            "unfixtured_rules must name a rule with no fixture",
        ),
        # Three of these four are bugs I actually shipped into the first draft, kept as
        # mutations because a bug that happened once is the best evidence a fixture is load-
        # bearing rather than decorative.
        Mutation(
            "the shared palette step loses its hyphen (`gray500`, matching nothing)",
            'STEP_ALTERNATION = _STEP[:-len(r"\\Z")]',
            'STEP_ALTERNATION = _STEP[1:-len(r"\\Z")]',
            "stock palette",
        ),
        Mutation(
            "the ease lookahead returns, excusing `ease-in-out` (it starts with `ease-in`)",
            're.compile(r"\\bease-(?:in-out|linear|initial)\\b")',
            're.compile(r"\\bease-(?!(?:out|in)\\b)(?:in-out|linear|initial)\\b")',
            "ease-in-out",
        ),
        Mutation(
            "the duration rule flags the documented FIX, `duration-(--duration-fast)`",
            'r"(?<![-\\w])duration-(?:"',
            'r"\\bduration-(?:"',
            "custom-property duration",
        ),
        Mutation(
            "the token-definition carve-out widens to every hex",
            'return before.endswith("--") or bool(TOKEN_DEFINITION.search(before))',
            "return True",
            "a plain declaration is NOT a token definition",
        ),
        Mutation(
            "a disable stops suppressing, so the escape hatch is decorative",
            "        if rule.name in allowed:\n            report.suppressed += 1\n            continue",
            "        if False:\n            report.suppressed += 1\n            continue",
            "a disable with a reason suppresses",
        ),
    ),
)
