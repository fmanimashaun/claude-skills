"""Mutation guard: check_component_contract. Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_component_contract",
    subject="scripts/check_component_contract.py",
    selftest="scripts/check_component_contract.py",
    # It now imports the shared ratchet (#1187). Undeclared, the mutant dies on
    # ModuleNotFoundError and an environmental death reads as a caught mutation.
    deps=("scripts/content_floors.py",),
    needs=("scripts/source_text.py",),   # comments are blanked here (#1128)
    mutations=(
        # The splat's name is hard-coded again, so `**input_html` stored as `@input_html` reads as dropped.
        Mutation(
            "the splat must be named attrs again",
            '    name = re.escape(m.group(1))',
            '    name = "attrs"',
            "a stored splat not named attrs is not reported",
        ),
        Mutation(
            # The must-FAIL half. A gate that stops reporting hand-written elements is the prose
            # mandate again, now wearing a check that looks present.
            "a hand-written element stops being reported",
            "                if not RAW_BUTTON.search(line):",
            "                if True:",
            "the hand-written button is reported",
        ),
        Mutation(
            # THE MUST-PASS HALF, and it is a scope rule rather than an exemption. Matching any
            # `button` word instead of the literal tag would flag `<%= button_to ... %>` -- correct
            # code -- the first time this ran, and a gate wrong about correct code on day one gets
            # an exclusion list or gets switched off.
            "the match widens from the literal tag to any mention of a button",
            r'RAW_BUTTON = re.compile(r"<button\b", re.I)',
            r'RAW_BUTTON = re.compile(r"button", re.I)',
            "the framework-helper button is NOT reported",
        ),
        Mutation(
            # Measured on a real consumer app: 31 raw `<button>` occurrences, 13 of them inside
            # `app/components/**` and every one correct -- the component's own template is where
            # the element belongs. Widening the scan there is 13 findings against correct code.
            "the scan widens to component templates, flagging the element where it belongs",
            '    for pattern in ("app/views/**/*.erb",):',
            '    for pattern in ("app/views/**/*.erb", "app/components/**/*.erb"):',
            "a component's own template is NOT reported",
        ),
        Mutation(
            "a component that cannot carry an attribute stops being reported",
            '            elif "**" not in sig:',
            "            elif False:",
            "a fixed keyword list is reported",
        ),
    Mutation(
        # Comments are prose (#1128). Without this call the gate reports a file for DESCRIBING the
        # anti-pattern -- and the file that describes it is usually the one that fixed it.
        "comments are matched as if they were code",
        '            source = strip_comments(path.read_text(encoding="utf-8", errors="replace"))',
        '            source = path.read_text(encoding="utf-8", errors="replace")',
        'a comment warning against a raw `<button>` is not a raw `<button>`',
    ),
        # #1434: the first `def initialize(` in the body, a nested class's included, is judged again.
        Mutation(
            "nested class bodies are read as the component's own",
            '            blob = "\\n".join(own_lines(body))',
            '            blob = "\\n".join(body)',
            "a nested class's initializer declared first is not the component's",
        ),
        Mutation(
            "a nested body never ends, so the component's own initializer after it vanishes",
            '            if _code(line).strip() == closer and len(line) - len(line.lstrip()) == skip_indent:\n                skip_indent = None',
            '            if _code(line).strip() == closer and len(line) - len(line.lstrip()) == skip_indent:\n                pass',
            "a nested class's initializer declared first is not the component's",
        ),
        Mutation(
            'any line starting `class` or `module` opens a nested body, `class:` included',
            'NESTED = re.compile(r"^([ \\t]*)(?:class[ \\t]+(?:[A-Z]|<<)|module[ \\t]+[A-Z]"\n                    r"|(?:[A-Z]\\w*[ \\t]*=[ \\t]*)?(?:Struct\\.new|Data\\.define|Class\\.new)\\b.*(?:\\bdo\\b|\\{)[ \\t]*(?:\\|[^|]*\\|)?[ \\t]*$)")',
            'NESTED = re.compile(r"^([ \\t]*)(?:class|module)\\b")',
            'a `class:` keyword line is not a nested class',
        ),
        Mutation(
            'the class regex spans blank lines above the class again',
            'COMPONENT_CLASS = re.compile(r"^[ \\t]*class (\\w+Component) < ViewComponent::Base[ \\t]*$", re.M)',
            'COMPONENT_CLASS = re.compile(r"^\\s*class (\\w+Component) < ViewComponent::Base[ \\t]*$", re.M)',
            'a nested COMPONENT after a blank line',
        ),
        # #1487 review: trailing comments, heredocs and block-defined classes.
        Mutation(
            "a trailing comment hides a one-liner's `end`",
            '        if m and not ONE_LINER.search(_code(line)):',
            '        if m and not ONE_LINER.search(line):',
            'a one-line nested class with a trailing comment opens no body',
        ),
        Mutation(
            '`end # Section` no longer closes a nested body',
            '            if _code(line).strip() == closer and len(line) - len(line.lstrip()) == skip_indent:',
            '            if line.strip() == closer and len(line) - len(line.lstrip()) == skip_indent:',
            'a nested body closed by `end # Section` ends there',
        ),
        Mutation(
            "a heredoc's lines are read as code",
            '        if h:\n            heredoc = h.group(2)\n        out.append(line)',
            '        out.append(line)',
            'a heredoc line starting `class` opens nothing',
        ),
        Mutation(
            'a Struct.new / Data.define / Class.new block is not a nested body',
            '                    r"|(?:[A-Z]\\w*[ \\t]*=[ \\t]*)?(?:Struct\\.new|Data\\.define|Class\\.new)\\b.*(?:\\bdo\\b|\\{)[ \\t]*(?:\\|[^|]*\\|)?[ \\t]*$)")',
            '                    r")")',
            'a Struct.new block above the initializer is not the component',
        ),
        Mutation(
            'an opener is judged with its trailing comment again',
            '        m = NESTED.match(_code(line))',
            '        m = NESTED.match(line)',
            "a `do` inside an opener's trailing comment opens nothing",
        ),
        Mutation(
            'a brace block closes only on `end`, so it swallows the component',
            '            closer = "}" if',
            '            closer = "end" if False and',
            'a Struct.new brace block above the initializer is not the component',
        ),
    ),
)
