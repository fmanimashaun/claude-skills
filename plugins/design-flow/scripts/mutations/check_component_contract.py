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
    ),
)
