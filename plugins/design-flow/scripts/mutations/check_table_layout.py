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
            "            del stack[i:]\n",
            "            pass\n",
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
        # THE FIRST REAL RUN READ CLEAN because the app's scroller was its own `@utility`.
        Mutation(
            "an app's own scroll utilities are no longer discovered from its CSS",
            "    return {name for name, body in UTILITY.findall(css) if SCROLLS_X.search(body)}",
            "    return set()",
            "an @utility that scrolls is discovered",
        ),
        Mutation(
            "a tab strip that scrolls stops being a finding",
            "        if (scrolls and tab_file) or (TABLIST.search(attrs) and (scrolls or any(s for _, s in stack))):",
            "        if False:",
            "a scrolling tablist is caught",
        ),
        Mutation(
            "a link-list strip in a tabs file is no longer recognised as a strip",
            "(scrolls and tab_file) or ",
            "",
            "a scrolling link-list strip in a tabs file is caught",
        ),
        Mutation(
            "`tab` is matched as a substring again, so a table component is called a tab strip",
            "bool(TAB_FILE.search(Path(rel).name)))",
            '"tab" in Path(rel).name)',
            "a TABLE component's scroller is not a tab strip",
        ),
        # REVIEW FINDING: a "New" button opening the modal satisfied table-no-details.
        Mutation(
            "a new/edit/delete modal link counts as a details target again",
            "        if not CRUD_ACTION.search(construct):",
            "        if True:",
            "a NEW button opening the modal is not a details target",
        ),
        Mutation(
            "our own doctrine's delete-confirmation link counts as a details target again",
            "(?:new|edit|delete)_\\w*(?:path|url)",
            "(?:new|edit)_\\w*(?:path|url)",
            "the doctrine's delete-confirmation link is not a details target",
        ),
        Mutation(
            "a tablist inside a scroller is no longer seen -- only one that scrolls itself",
            "(TABLIST.search(attrs) and (scrolls or any(s for _, s in stack)))",
            "(TABLIST.search(attrs) and scrolls)",
            "a tablist inside a scrolling wrapper is caught",
        ),
        Mutation(
            "a min-width on a cell or column is no longer a finding",
            '        if not m.group(1) and m.group(2).lower() in {"th", "td", "col"} and (w := fixed_min_width(m.group(3))):',
            '        if False and (w := fixed_min_width(m.group(3))):',
            "min-w-* on a header cell is caught",
        ),
        # #1419: rows per page, then the summary, bottom-left.
        Mutation(
            "a pager with the summary first stops being a finding",
            "    if per and summary and summary.start() < per.start():",
            "    if False:",
            "a pager with the summary before rows-per-page is caught",
        ),
        Mutation(
            "a pager with no rows-per-page control is judged anyway",
            "    if per and summary and summary.start() < per.start():",
            "    if summary and (not per or summary.start() < per.start()):",
            "a pager with no rows-per-page control is not judged",
        ),
        Mutation(
            "any file with Showing before a select is judged as a pager",
            "    if not (pager_file or PAGER_NAV.search(source)):\n        return None",
            "    pass",
            "a non-pager file with Showing before a select is silent",
        ),
        # #1451 review: comment stripping, and the pager shapes a real app writes.
        Mutation(
            "COMMENTS ARE NO LONGER STRIPPED, so a described anti-pattern counts as committed",
            "    source = strip_comments(raw)\n",
            "    source = raw\n",
            "a scroller named only in a comment is silent",
        ),
        Mutation(
            "a tag.nav helper's Pagination label is no longer seen",
            r"""|aria:\s*\{[^}]*\blabel:\s*["']Pagination["']""",
            "",
            "a tag.nav helper's Pagination label marks a pager",
        ),
        Mutation(
            "an i18n summary is no longer seen",
            """|\\bt\\(\\s*[\\"'][\\w.]*(?:showing|summary)[\\"']")""",
            """")""",
            "an i18n summary before rows-per-page is caught",
        ),
        Mutation(
            "Pagy's _pagy_nav is no longer a pager file",
            "(?:pagination|pager|pagy)",
            "(?:pagination|pager)",
            "Pagy's _pagy_nav partial is a pager file",
        ),
        Mutation(
            "mailer views are judged again, and email layout tables fail",
            "        if MAILER.search(p.relative_to(root).as_posix()):\n            continue\n",
            "",
            "run(): mailer views and layouts are not judged",
        ),
    ),
)
