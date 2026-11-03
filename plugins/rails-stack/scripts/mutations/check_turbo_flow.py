"""Mutation guard: check_turbo_flow. Declared here, run by scripts/mutation_check.py (#2278).

Every mutation here lets a modal that cannot open, a failed form answered 200, or a stream with no HTML fallback read as clean.
"""
from mutation_types import Guard, Mutation  # noqa: F401

STATUS_OK = ":unprocessable_entity|:unprocessable_content|:ok|422|200"
STRING_FORM_OLD = '|["\'](?:new|edit)["\'])([^\\n]*)""")'
STRING_FORM_NEW = ')([^\\n]*)""")'

GUARD = Guard(
    name="check_turbo_flow",
    subject="scripts/check_turbo_flow.py",
    selftest="scripts/check_turbo_flow.py",
    mutations=(
        Mutation("a modal template with no modal frame is accepted", "                if not MODAL_FRAME.search(read(template)):", "                if False:",
                 "a modal link whose template has no modal frame is a finding with both paths"),
        Mutation("the modal link pattern never matches", 'MODAL_DATA = re.compile(r"""turbo_frame:', 'MODAL_DATA = re.compile(r"""zzturbo_frame:',
                 "a modal link whose template has no modal frame is a finding with both paths"),
        Mutation("a template that cannot be located is not reported", "                unlocated += 1", "                pass",
                 "a modal link whose template cannot be located is reported, not passed in silence"),
        Mutation("a member-action helper is cut to its first word", "    for i in range(1, len(words)):", "    for i in range(1, 2):",
                 "a member-action helper (delete_confirmation_invoice_path) is mapped to its template"),
        Mutation("render :new with no status is accepted", '            if not re.search(r"\\bstatus:\\s*(?::unprocessable_entity', '            if False and not re.search(r"\\bstatus:\\s*(?::unprocessable_entity',
                 "render :new with no status is a finding with its file:line"),
        Mutation("status: :unprocessable_content is not accepted", STATUS_OK, ":unprocessable_entity|:ok|422|200",
                 "render :new with status: :unprocessable_content is clean"),
        Mutation("an explicit status: :ok is not accepted", STATUS_OK, ":unprocessable_entity|:unprocessable_content|422|200",
                 "an explicit status: :ok (a GET) is clean"),
        Mutation("the string form render \"new\" is not read", STRING_FORM_OLD, STRING_FORM_NEW,
                 "the string form render \"new\" with no status is a finding"),
        Mutation("a stream with no HTML branch is accepted", '            if re.search(r"\\bformat\\.turbo_stream\\b", body) and not re.search(r"\\bformat\\.(?:html|any)\\b", body):', "            if False:",
                 "respond_to with format.turbo_stream and no format.html is a finding"),
        Mutation("format.any no longer counts as the fallback", '\\bformat\\.(?:html|any)\\b', '\\bformat\\.html\\b',
                 "format.any also counts as the fallback"),
    ),
)
