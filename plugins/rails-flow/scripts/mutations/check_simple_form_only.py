"""Mutation guard: check_simple_form_only. Declared here, run by scripts/mutation_check.py (#1383).

Each mutation lets a hand-built form or field through where simple_form is mandated, or refuses a
correct simple_form idiom, which is how a gate gets switched off.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_simple_form_only",
    subject="scripts/check_simple_form_only.py",
    selftest="scripts/check_simple_form_only.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "form_with passes",
            '    ("form-with", re.compile(r"(?<![\\w.])(form_with|form_for)\\b")),',
            '    ("form-with", re.compile(r"(?<![\\w.])(NEVER)\\b")),',
            "a planted form-with is refused",
        ),
        # Its control: the word boundary is what keeps every correct form silent.
        Mutation(
            "the boundary goes, so simple_form_for reads as form_for",
            '    ("form-with", re.compile(r"(?<![\\w.])(form_with|form_for)\\b")),',
            '    ("form-with", re.compile(r"(form_with|form_for)\\b")),',
            "CONTROL: simple_form_for is not form_for (word boundary)",
        ),
        Mutation(
            "a literal <form> passes",
            '    ("raw-form", re.compile(r"<form\\b", re.I)),',
            '    ("raw-form", re.compile(r"<NEVER\\b", re.I)),',
            "a planted raw-form is refused",
        ),
        Mutation(
            "a hidden input is refused like a visible one",
            r'''<input\b(?![^>]*\btype\s*=\s*[\"']?hidden\b)''',
            r'''<input\b''',
            "CONTROL: a hidden input is not a raw field",
        ),
        Mutation(
            "select_tag, the most common loose helper, passes",
            'r"(?<![\\w.])(text_field|select|check_box|',
            'r"(?<![\\w.])(text_field|check_box|',
            "a planted field-tag-helper is refused",
        ),
        Mutation(
            "tag.input passes",
            '    ("tag-builder-field", re.compile(r"\\btag\\.(input|select|textarea|form)\\b")),',
            '    ("tag-builder-field", re.compile(r"\\btag\\.(NEVER)\\b")),',
            "a planted tag-builder-field is refused",
        ),
        Mutation(
            "raw calls on a simple_form builder pass",
            "    for var in set(BUILDER.findall(text)):",
            "    for var in set():",
            "a planted raw-builder-call is refused",
        ),
        # Its control: the receiver must be the builder, not any variable.
        Mutation(
            "any receiver counts as the builder, so `items.select` is a raw call",
            '        for m in re.finditer(rf"(?<![\\w.]){re.escape(var)}\\.({RAW_FIELD_METHODS})\\b", text):',
            '        for m in re.finditer(rf"\\b\\w+\\.({RAW_FIELD_METHODS})\\b", text):',
            "CONTROL: `.select` on an array is not a builder call",
        ),
        Mutation(
            "comments are scanned, so an explanation of a past fix is a finding",
            '    text = re.sub(r"<%#.*?%>", keep, text, flags=re.S)',
            "    pass",
            "CONTROL: an ERB comment naming a raw helper is not a finding",
        ),
        Mutation(
            "components are not read, which was the old grep's blind spot",
            'for d in ("app/views", "app/components")',
            'for d in ("app/views",)',
            "a component template is scanned (the old grep read app/views only)",
        ),
        Mutation(
            "a project without simple_form reads as a pass",
            '        return 3, ["not applicable — simple_form is not in Gemfile.lock (NOT a pass)"]',
            '        return 0, ["not applicable — simple_form is not in Gemfile.lock (NOT a pass)"]',
            "no Gemfile.lock is not applicable (exit 3), never a pass",
        ),
        Mutation(
            "a stale exemption is silent",
            "        if not used[i]:",
            "        if False:",
            "a stale exemption is a finding",
        ),
        Mutation(
            "an exemption needs no reason",
            ' and str(row.get("reason", "")).strip()):',
            "):",
            "an exemption with no reason is unusable",
        ),
        # Pre-release review of #1388.
        Mutation(
            "a readonly display input is refused like a field again",
            "                if DISPLAY_INPUT.search(tag) and not NAMED.search(tag):\n                    continue\n",
            "",
            "CONTROL: a readonly, unnamed input is a display, not a field",
        ),
        Mutation(
            "a readonly input that POSTS slips through the display carve-out",
            "                if DISPLAY_INPUT.search(tag) and not NAMED.search(tag):",
            "                if DISPLAY_INPUT.search(tag):",
            "...but a readonly input that posts (named) is still a raw field",
        ),
        Mutation(
            "a multi-line simple_form_for call hides its builder again",
            'BUILDER = re.compile(r"\\bsimple_(?:form_for|fields_for)\\b[^%]*?\\bdo\\s*\\|\\s*(\\w+)", re.S)',
            'BUILDER = re.compile(r"\\bsimple_(?:form_for|fields_for)\\b[^\\n]*?\\bdo\\s*\\|\\s*(\\w+)")',
            "a raw call on a builder opened by a MULTI-LINE simple_form_for is refused",
        ),
        Mutation(
            "an exemption's `match` is ignored, so it exempts every violation of its rule in the file",
            '                     and (not e.get("match") or e["match"] in what)]',
            "                     ]",
            "...and does not exempt a different violation of the same rule in the same file",
        ),
        Mutation(
            "`exemptions: null` crashes instead of being unusable",
            "        if not isinstance(rows, list):\n            raise TypeError(",
            "        if False:\n            raise TypeError(",
            "`\"exemptions\": null` is unusable, not a crash",
        ),
        Mutation(
            "the tag is cut at an ERB %>, so a readonly after an ERB value is missed",
            'WHOLE_TAG = re.compile(r"<input\\b(?:<%.*?%>|[^<>])*>", re.I | re.S)',
            'WHOLE_TAG = re.compile(r"<input\\b[^>]*>", re.I | re.S)',
            "CONTROL: an ERB value inside the tag does not hide its readonly",
        ),
        # #1443: the tag stops at a bare `<`, and an unclosed tag is judged on its own line.
        Mutation(
            "the tag runs on into the NEXT tag again",
            'WHOLE_TAG = re.compile(r"<input\\b(?:<%.*?%>|[^<>])*>", re.I | re.S)',
            'WHOLE_TAG = re.compile(r"<input\\b(?:<%.*?%>|[^>])*>", re.I | re.S)',
            "an <input> is not closed by the NEXT tag's `>`",
        ),
        Mutation(
            "an unclosed tag falls back to the rest of the file again",
            "                tag = end.group(0) if end else text[m.start(): eol if eol != -1 else len(text)]",
            "                tag = end.group(0) if end else text[m.start():]",
            "an <input> with no `>` anywhere is judged on its own line only",
        ),
        Mutation(
            "readonly matches inside other attribute names and values again",
            'DISPLAY_INPUT = re.compile(r"(?:(?<=\\s)readonly(?=[\\s=/>]|$)|(?<![\\w-])readonly:\\s*true\\b)", re.I)',
            'DISPLAY_INPUT = re.compile(r"\\breadonly\\b", re.I)',
            "data-readonly is not readonly",
        ),
        Mutation(
            "a name set through ERB is no longer seen",
            'NAMED = re.compile(r"(?:(?<=\\s)name\\s*=|(?<![\\w-])name:)", re.I)',
            'NAMED = re.compile(r"\\bname\\s*=", re.I)',
            "a name set through ERB makes a readonly input a posting field",
        ),
    ),
)
