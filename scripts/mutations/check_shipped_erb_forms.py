"""Mutation guard: check_shipped_erb_forms. Declared here, run by scripts/mutation_check.py (#1383, #1443).

Each mutation lets our own doctrine ship an ERB block the simple-form-only gate we ship would refuse.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_shipped_erb_forms",
    subject="scripts/check_shipped_erb_forms.py",
    selftest="scripts/check_shipped_erb_forms.py",
    needs=("plugins/rails-flow/scripts/check_simple_form_only.py",),
    mutations=(
        Mutation(
            "shipped blocks are never scanned",
            "            for rule, line, what in scan(str(f), body):",
            "            for rule, line, what in []:",
            "a raw <form> in a shipped ERB block is a finding",
        ),
        # #1443 / #1455 review: the marker excuses exactly what it NAMES, and only with a reason.
        Mutation(
            "the primitive marker excuses its whole block again",
            '                if named.get(key, 0) > 0:\n                    named[key] -= 1\n',
            '                if named:\n',
            "the marker excuses only what it names: a later raw <select> is a finding",
        ),
        Mutation(
            "a named primitive construct is refused like any other",
            '                if named.get(key, 0) > 0:\n                    named[key] -= 1\n                    continue\n',
            '',
            "CONTROL: the construct a primitive marker names is excused",
        ),
        Mutation(
            "the marker matches as a PREFIX again, so `primitive <` excuses every raw tag",
            '                if named.get(key, 0) > 0:\n                    named[key] -= 1\n',
            '                if any(key.startswith(n) for n in named):\n',
            "`primitive <` is not a prefix that excuses every raw tag",
        ),
        Mutation(
            "an invalid marker is silently accepted",
            '                    out.append(f"{where} — primitive-marker-invalid: a marker must name one construct and give a "',
            '                    pass; (f"{where} — primitive-marker-invalid: a marker must name one construct and give a "',
            "a marker that names nothing excuses nothing",
        ),
        Mutation(
            "a marker no longer needs a reason",
            'VALID_MARKER = re.compile(r"^[ \\t]*(\\S+)[ \\t]+--[ \\t]*\\w")',
            'VALID_MARKER = re.compile(r"^[ \\t]*(\\S+)")',
            "a marker with no reason excuses nothing",
        ),
        Mutation(
            "only the first marker in a block counts",
            "            for marker in PRIMITIVE.finditer(body):",
            "            for marker in list(PRIMITIVE.finditer(body))[:1]:",
            "every marker in a block counts, not only the first",
        ),
        # #1443: every fence, indented or not.
        Mutation(
            "indented fences are skipped again",
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^()(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            "an INDENTED fence is read",
        ),
        Mutation(
            "an indented fence closes at any later fence",
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^[ \\t]*\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            "a fence line at ANOTHER indent does not close an indented block",
        ),
        Mutation(
            "the finding's line is the block's, not the doc's",
            "                out.append(f\"{f.relative_to(root)}:{start + line}",
            "                out.append(f\"{f.relative_to(root)}:{line}",
            "...with the doc's own line number",
        ),
        # #1458/#1460
        Mutation(
            'a marker may excuse a form builder',
            '                elif valid.group(1).lower() in FORM_BUILDERS:',
            '                elif False:',
            '#1460: a marker naming form_with is invalid',
        ),
        Mutation(
            'one marker excuses every instance',
            '                    named[key] -= 1\n',
            '',
            '#1460: one marker excuses ONE instance',
        ),
        Mutation(
            '~~~erb blocks are not read',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})NEVER(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            '#1460: a ~~~erb block is read',
        ),
        Mutation(
            'only three-backtick fences are read',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(```)(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            '#1460: a four-backtick erb block is read',
        ),
        Mutation(
            'any fence line closes a block',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2[`~]*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            '#1521 R2: a mixed ```~~~ line does not close a backtick block',
        ),
        # #1521 review
        Mutation(
            'a marker may excuse a raw <form>',
            'FORM_BUILDERS = {"form_with", "form_for", "form_tag", "<form", "tag.form"}',
            'FORM_BUILDERS = {"form_with", "form_for", "form_tag", "tag.form"}',
            '#1521 R1: a marker naming <form is invalid',
        ),
        Mutation(
            'a marker may excuse tag.form',
            'FORM_BUILDERS = {"form_with", "form_for", "form_tag", "<form", "tag.form"}',
            'FORM_BUILDERS = {"form_with", "form_for", "form_tag", "<form"}',
            '#1521 R1: a marker naming tag.form is invalid',
        ),
        Mutation(
            'a spare marker stays silent',
            '                if spare > 0:',
            '                if False:',
            '#1521 R3: a marker that excuses nothing is reported',
        ),
        Mutation(
            'only lowercase erb fences are read',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M | re.I)',
            'BLOCK = re.compile(r"^([ \\t]*)(?:(`{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\2`*"\n                   r"|(~{3,})(?:html\\+)?erb\\b[^\\n]*\\n(.*?)^\\1\\4~*)[ \\t]*$", re.S | re.M)',
            '#1521 R6: a ```ERB block is read',
        ),
    ),
)
