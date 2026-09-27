"""Mutation guard: check_table_layout. Run by scripts/mutation_check.py (#1391)."""
from mutation_types import Guard, Mutation  # noqa: F401

# Each rule has a way of going quiet, and each quiet shape is a real app's shape: the scroller
# judged by order instead of nesting fires on every tablist; the style parsed by its quoted value
# misses the interpolated `min-width` the app behind #1391 shipped; the directory lookup narrowed to
# the file reports every index whose row link lives in a partial.
GUARD = Guard(
    name="check_table_layout",
    subject="scripts/check_table_layout.py",
    selftest="scripts/check_table_layout.py",   # --selftest lives in the module
    deps=("scripts/content_floors.py", "scripts/source_text.py"),
    mutations=(
        Mutation(
            "a table inside a scroller stops being a finding",
            "        if scrolled:\n",
            "        if False:\n",
            "a table inside overflow-x-auto is caught",
        ),
        Mutation(
            "nesting is forgotten: a closed scroller still counts for a later table",
            "                    del stack[i:]\n",
            "                    pass\n",
            "a table AFTER a closed scroller is silent",
        ),
        Mutation(
            "min-width is read from a parsed quoted style value again, missing interpolation",
            "    if MIN_WIDTH_STYLE.search(attrs):\n",
            "    if MIN_WIDTH_STYLE.search(attrs.split('<%', 1)[0]):\n",
            "a min-width interpolated into the table's own style is caught",
        ),
        Mutation(
            "a wrapped render call is read one line at a time again",
            'RENDER_TAG = re.compile(r"<%=?\\s*render\\b(.*?)%>", re.S)',
            'RENDER_TAG = re.compile(r"<%=?\\s*render\\b([^\\n]*?)%>")',
            "a min_width: on the LAST line of a wrapped render call is caught",
        ),
        Mutation(
            "a table with no details target stops being a finding",
            "    if tables and not directory_has_target and not DECLARES.search(raw):",
            "    if False:",
            "a table with no details target in its directory is caught",
        ),
        Mutation(
            "the details target is looked up per FILE, so a partial's link no longer counts",
            "            targets[p.parent] = True",
            "            targets[p] = True",
            "run(): the partial's link satisfies its index",
        ),
        Mutation(
            "a declaration no longer needs a reason",
            'DECLARES = re.compile(r"table-without-details:[ \\t]*\\w")',
            'DECLARES = re.compile(r"table-without-details:")',
            "a declaration with no reason is not a declaration",
        ),
        Mutation(
            "mailer views are judged again, and email layout tables fail",
            "        if MAILER.search(p.relative_to(root).as_posix()):\n            continue\n",
            "",
            "run(): mailer views and layouts are not judged",
        ),
    ),
)
