#!/usr/bin/env python3
"""Every table is master-detail and none scrolls sideways (#1391).

Run:  python3 check_table_layout.py                 # app/views + app/components
      python3 check_table_layout.py --root path/to/app
      python3 check_table_layout.py --selftest

WHY THIS EXISTS. The shipped design-system skill told agents to wrap a table in `overflow-x-auto`,
pin its identifier columns, link the id to a show page, and dump every column into a phone card. An
app built exactly that and the owner rejected it. Measured there: 25 tables forced a fixed
`min_width` of 36rem-60rem, so they scrolled sideways on tablets and laptops that had room to fit
them. The doctrine is now `design-system` `components.md` -> Table (CRUD); this checks the three
parts of it that are visible in source.

FOUR RULES, each a construct and never a word:

  table-scroll-wrapper   a `<table>` inside an element whose class scrolls on the x axis
                         (`overflow-x-auto|scroll`, or `overflow-auto|scroll`, which include x).
                         The table has to be INSIDE the scroller, by element nesting, not merely
                         later in the file.
  table-min-width        a `<table>`, `<th>`, `<td>` or `<col>` given a fixed minimum width -- a
                         `min-w-*` class other than `min-w-0`/`min-w-full`, an inline `min-width`,
                         or a `min_width:` keyword passed to a table component (the shape the app
                         above used 22 times).
  table-no-details       a file with a `<table>` and no details target anywhere in its directory:
                         no link into the modal frame (`turbo_frame: "modal"` / `:modal`, or
                         `data-turbo-frame="modal"`). THE DIRECTORY, NOT THE FILE: a Rails index
                         renders its rows from a partial beside it (`<%= render @people %>` ->
                         `_person.html.erb`), and the row link lives in the partial. A modal link
                         that is a CRUD ACTION -- `new_*`/`edit_*` helpers, `/new`, `/edit`, a
                         delete method -- is not a details target: a "New" button that opens the
                         modal says nothing about where the ROWS go.
  tablist-scroll         a tab strip that scrolls: a `role="tablist"` that scrolls or sits inside a
                         scroller (by nesting), or any scroller
                         in a file named for tabs (`*tab*`) -- apps build strips as link lists on
                         purpose, and the app behind #1391 does. A strip is one row of at most four
                         that never wraps or scrolls, and a picker below 768px (the maintainer's
                         scope addition on #1391). A scrolling `<pre>` elsewhere is not a strip.

A SCROLLER IS WHAT THE APP DEFINES, not only Tailwind's names. The first run against the app behind
#1391 reported its tables clean: it wraps them in `scroll-x`, its own `@utility` whose body is
`overflow-x: auto`. So every `@utility` under `app/` whose body sets `overflow-x`/`overflow` to
`auto`/`scroll` is read from the app's CSS and counted as a scroller alongside the Tailwind classes.

A table that is not a record index -- a permissions matrix, a data-viz fallback, invoice lines --
declares itself, in the file, with a reason: `<%# table-without-details: <why> %>`. A declaration
with no reason is not a declaration.

COMMENTS ARE BLANKED before matching (`source_text.py`, #1128), so a file explaining the
anti-pattern is not reported as committing it. The declaration is read from the RAW source, since
it is itself a comment.

KNOWN LIMITS, stated so a clean run is not over-read: a wrapper built with `content_tag`/`tag.div`
rather than markup is not seen; a table rendered by a component whose own template holds the
`<table>` is judged in that component's file, so its details target is judged by that component's
directory and not by each call site; the six-column budget, the five-field summary and the four-tab
cap are not counted; and a CRUD action is recognised by Rails' helper and path conventions only.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings. An app that already has
findings records them once with `--set-floor` and is then refused only on a regression
(`content_floors.py`, #1187).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import content_floors
from source_text import strip_comments

GATE = "table-layout"

TABLIST = re.compile(r"""\brole\s*=\s*["']tablist["']""")
# `tab`/`tabs` as a WORD in the file name. A substring test called `table_component` a tab strip on
# the first real run.
TAB_FILE = re.compile(r"(?:^|[_.-])tabs?(?=[_.-]|$)")
UTILITY = re.compile(r"@utility\s+([\w-]+)\s*\{([^{}]*)\}", re.S)
SCROLLS_X = re.compile(r"\boverflow(?:-x)?\s*:\s*(?:auto|scroll)\b")
TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)\b([^>]*?)(/?)>", re.S)
CLASS_VALUE = re.compile(r"""\bclass\s*=\s*(["'])(.*?)\1""", re.S)
X_SCROLLER = re.compile(r"(?<![\w-])overflow(?:-x)?-(?:auto|scroll)(?![\w-])")
MIN_WIDTH_CLASS = re.compile(r"(?<![\w-])min-w-(?!0(?![\w.])|full(?![\w-]))[\w\[\]().%-]+")
MIN_WIDTH_STYLE = re.compile(r"\bmin-width\s*:", re.I)
# A `render` ERB tag, WHOLE -- calls wrap over several lines, and the keyword is often on the last.
RENDER_TAG = re.compile(r"<%=?\s*render\b(.*?)%>", re.S)
TABLE_CALL_MIN_WIDTH = re.compile(r"Table\w*[\s\S]*?\bmin_width:")
DETAILS_TARGET = re.compile(
    r"""turbo_frame:\s*(?:["']modal["']|:modal)|data-turbo-frame\s*=\s*["']modal["']|["']turbo-frame["']\s*=>\s*["']modal["']""")
# A modal link that is a CRUD ACTION is not a details target. Found in review: a "New person" button
# opening the modal satisfied the rule while every row still linked to a show page.
CRUD_ACTION = re.compile(
    r"""\b(?:new|edit)_\w*(?:path|url)\b|/(?:new|edit)\b|\baction:\s*:(?:new|edit)\b"""
    r"""|(?:turbo_)?method:\s*:delete\b|data-turbo-method\s*=\s*["']delete""")
DECLARES = re.compile(r"table-without-details:[ \t]*\w")
# EMAIL IS LAID OUT WITH TABLES, and has no modal to open. Found on the first run against the app
# behind #1391: both `table-no-details` findings were a mailer layout and a mailer view. Action Mailer
# looks views up under `app/views/<name>_mailer/`, and a mailer layout is `layouts/*mailer*`.
MAILER = re.compile(r"(?:^|/)(?:[\w]+_mailer/|layouts/[\w.]*mailer[\w.]*$)")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}


def opens_a_record(source: str) -> bool:
    """Is any modal-frame link here a RECORD link, not new/edit/delete? Judged per enclosing tag."""
    for m in DETAILS_TARGET.finditer(source):
        start = source.rfind("<", 0, m.start())
        end = source.find(">", m.end())
        construct = source[start if start >= 0 else 0: end + 1 if end >= 0 else len(source)]
        if not CRUD_ACTION.search(construct):
            return True
    return False


def app_scrollers(css: str) -> set[str]:
    """Names of `@utility` blocks that scroll horizontally, from an app's own stylesheets."""
    return {name for name, body in UTILITY.findall(css) if SCROLLS_X.search(body)}


def _scrolls(classes: str, scrollers: frozenset[str]) -> bool:
    return bool(X_SCROLLER.search(classes)) or any(c in scrollers for c in classes.split())


def _line(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _close(stack: list[tuple[str, bool]], name: str) -> None:
    """Pop back to the nearest open element of this name -- ONE place, so both walkers nest alike."""
    for i in range(len(stack) - 1, -1, -1):
        if stack[i][0] == name:
            del stack[i:]
            break


def tables_in(source: str, scrollers: frozenset[str] = frozenset()) -> list[tuple[int, str, bool]]:
    """(line, attrs, inside an x-scroller) for every `<table>`, by element nesting."""
    stack: list[tuple[str, bool]] = []
    out: list[tuple[int, str, bool]] = []
    for m in TAG.finditer(source):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            _close(stack, name)
            continue
        cls = CLASS_VALUE.search(attrs)
        scrolls = bool(cls and _scrolls(cls.group(2), scrollers))
        if name == "table":
            out.append((_line(source, m.start()), attrs, any(s for _, s in stack) or scrolls))
        if name not in VOID and not selfclose:
            stack.append((name, scrolls))
    return out


def scrolling_strips(source: str, scrollers: frozenset[str], tab_file: bool) -> list[int]:
    """A strip that scrolls ITSELF, or sits inside a scroller -- by element nesting, as for tables."""
    stack: list[tuple[str, bool]] = []
    lines = []
    for m in TAG.finditer(source):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            _close(stack, name)
            continue
        cls = CLASS_VALUE.search(attrs)
        scrolls = bool(cls and _scrolls(cls.group(2), scrollers))
        if (scrolls and tab_file) or (TABLIST.search(attrs) and (scrolls or any(s for _, s in stack))):
            lines.append(_line(source, m.start()))
        if name not in VOID and not selfclose:
            stack.append((name, scrolls))
    return lines


def cell_min_widths(source: str) -> list[tuple[int, str]]:
    """A fixed minimum width on a column or cell forces the table wider exactly as one on the table."""
    out = []
    for m in TAG.finditer(source):
        if not m.group(1) and m.group(2).lower() in {"th", "td", "col"} and (w := fixed_min_width(m.group(3))):
            out.append((_line(source, m.start()), w))
    return out


def fixed_min_width(attrs: str) -> str | None:
    cls = CLASS_VALUE.search(attrs)
    if cls and (m := MIN_WIDTH_CLASS.search(cls.group(2))):
        return m.group(0)
    # The WHOLE attribute run, not a parsed `style` value: an app interpolates it,
    # `style="table-layout: fixed<%= "; min-width: #{w}" if w %>"`, and a quoted-value parse stops at
    # the inner quote and never reaches the declaration -- the shape of the app behind #1391.
    if MIN_WIDTH_STYLE.search(attrs):
        return "min-width (inline style)"
    return None


def check_file(rel: str, raw: str, directory_has_target: bool,
               scrollers: frozenset[str] = frozenset()) -> list[str]:
    source = strip_comments(raw)
    findings: list[str] = []
    tables = tables_in(source, scrollers)
    for line, attrs, scrolled in tables:
        if scrolled:
            findings.append(
                f"{rel}:{line}: table-scroll-wrapper — this table sits inside an element that "
                f"scrolls sideways. No table scrolls horizontally at any width: at 768px and wider "
                f"it fits its container and its cells wrap; below that it is a stack of summary "
                f"cards. Remove the wrapper (design-system components.md → Table (CRUD)).")
        if (width := fixed_min_width(attrs)):
            findings.append(
                f"{rel}:{line}: table-min-width — `{width}` forces this table wider than its "
                f"container, which is what makes it scroll on screens that could fit it. Let it "
                f"fit; a column that does not fit belongs in the Details card.")
    for line in scrolling_strips(source, scrollers, bool(TAB_FILE.search(Path(rel).name))):
        findings.append(
            f"{rel}:{line}: tablist-scroll — this tab strip scrolls sideways. A strip is one row of "
            f"at most four tabs that never wraps or scrolls; regroup a fifth, and below 768px render "
            f"a single labelled picker instead (design-system components.md → Tabs).")
    for line, width in cell_min_widths(source):
        findings.append(
            f"{rel}:{line}: table-min-width — `{width}` on a cell or column forces the table wider "
            f"than its container. Let it fit; a column that does not fit belongs in the Details card.")
    for m in RENDER_TAG.finditer(source):
        if not TABLE_CALL_MIN_WIDTH.search(m.group(1)):
            continue
        findings.append(
            f"{rel}:{_line(source, m.start())}: table-min-width — a `min_width:` passed to a table "
            f"component forces it wider than its container. Let it fit.")
    if tables and not directory_has_target and not DECLARES.search(raw):
        findings.append(
            f"{rel}:{tables[0][0]}: table-no-details — no row here or in this directory opens a "
            f"record into the modal frame. Every table is master-detail: the name links the row "
            f"to its Details card (`data: {{ turbo_frame: \"modal\" }}`), not a show page. A table "
            f"that is not a record index says so: `<%# table-without-details: <why> %>`.")
    return findings


def run(root: Path) -> tuple[list[str], int]:
    files = sorted(p for base in ("app/views", "app/components") for p in (root / base).glob("**/*")
                   if p.is_file() and p.suffix in {".erb", ".rb"})
    css = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted((root / "app").glob("**/*.css")))
    scrollers = frozenset(app_scrollers(css))
    targets: dict[Path, bool] = {}
    for p in files:
        if opens_a_record(strip_comments(p.read_text(encoding="utf-8", errors="replace"))):
            targets[p.parent] = True
    findings: list[str] = []
    for p in files:
        if MAILER.search(p.relative_to(root).as_posix()):
            continue
        findings += check_file(str(p.relative_to(root)), p.read_text(encoding="utf-8", errors="replace"),
                               targets.get(p.parent, False), scrollers)
    return findings, len(files)


# --------------------------------------------------------------------------- selftest

LINKED_ROW = '<td><%= link_to p.name, p, data: { turbo_frame: "modal" } %></td>'


def _selftest() -> int:
    failures: list[str] = []

    def expect(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    def rules(src: str, has_target: bool = True, scrollers: frozenset[str] = frozenset(),
              name: str = "x.html.erb") -> list[str]:
        return [content_floors.rule_of(f) for f in check_file(name, src, has_target, scrollers)]

    # table-scroll-wrapper, and the controls that keep it from firing on everything.
    wrapped = f'<div class="overflow-x-auto">\n  <table class="w-full"><tr>{LINKED_ROW}</tr></table>\n</div>'
    expect("a table inside overflow-x-auto is caught", rules(wrapped) == ["table-scroll-wrapper"])
    expect("a table two levels inside the scroller is caught",
           "table-scroll-wrapper" in rules('<div class="overflow-auto"><section><table></table></section></div>'))
    expect("a scroller on the table itself is caught",
           "table-scroll-wrapper" in rules('<table class="overflow-x-scroll w-full"></table>'))
    # An APP-DEFINED scroller, the shape that made the first real run read clean.
    expect("a table inside an app's own scroll utility is caught",
           rules('<div class="scroll-x relative"><table></table></div>', scrollers=frozenset({"scroll-x"})) == ["table-scroll-wrapper"])
    expect("...and the same markup with no such utility defined is silent",
           rules('<div class="scroll-x relative"><table></table></div>') == [])
    expect("an @utility that scrolls is discovered; one that does not is not",
           app_scrollers("@utility scroll-x {\n  overflow-x: auto;\n  background: none;\n}\n"
                         "@utility reel { display: flex; overflow-x: auto; }\n"
                         "@utility card { padding: 1rem; overflow: hidden; }") == {"scroll-x", "reel"})

    # tablist-scroll, and its controls.
    expect("a scrolling tablist is caught",
           rules('<div role="tablist" class="cluster overflow-x-auto">…</div>') == ["tablist-scroll"])
    expect("a scrolling link-list strip in a tabs file is caught",
           rules('<nav class="scroll-x" aria-label="Settings sections">…</nav>', scrollers=frozenset({"scroll-x"}),
                 name="app/components/ui/settings_tabs_component.html.erb") == ["tablist-scroll"])
    expect("a TABLE component's scroller is not a tab strip — `tab` is a word, not a substring",
           "tablist-scroll" not in rules('<div class="scroll-x"><table></table></div>', scrollers=frozenset({"scroll-x"}),
                                         name="app/components/ui/table_component.html.erb"))
    expect("a tablist inside a scrolling wrapper is caught",
           rules('<div class="overflow-x-auto"><div role="tablist" class="flex">…</div></div>') == ["tablist-scroll"])
    expect("min-w-* on a header cell is caught",
           rules('<table><tr><th class="min-w-[12rem]">Name</th></tr></table>') == ["table-min-width"])
    expect("min-w-0 on a cell is silent", rules('<table><tr><td class="min-w-0 truncate">x</td></tr></table>') == [])
    expect("a tablist that does not scroll is silent",
           rules('<div role="tablist" class="cluster border-b">…</div>') == [])
    expect("a scroller that is neither a table nor a strip is silent",
           rules('<pre class="overflow-x-auto"><code>long line</code></pre>') == [])
    expect("a table AFTER a closed scroller is silent — nesting, not order",
           rules('<div class="overflow-x-auto"><p>x</p></div>\n<table></table>') == [])
    expect("a vertical-only scroller is silent",
           rules('<div class="max-h-[70vh] overflow-y-auto"><table></table></div>') == [])
    expect("a scroller named only in a comment is silent",
           rules('<%# never <div class="overflow-x-auto"><table> %>\n<table></table>') == [])

    # table-min-width.
    expect("a min-w-[48rem] table is caught", rules('<table class="w-full min-w-[48rem]"></table>') == ["table-min-width"])
    expect("an inline min-width is caught", rules('<table style="min-width: 40rem"></table>') == ["table-min-width"])
    expect("min_width: on a table component is caught",
           rules('<%= render Ui::TableComponent.new(rows: @rows, min_width: "36rem") %>') == ["table-min-width"])
    expect("a min_width: on the LAST line of a wrapped render call is caught",
           rules('<%= render(Ui::TableComponent.new(rows: @rows,\n    caption: "x",\n    min_width: "36rem")) do |t| %>') == ["table-min-width"])
    expect("a min-width interpolated into the table's own style is caught",
           rules('<table class="w-full" style="table-layout: fixed<%= "; min-width: #{min_width}" if min_width %>"></table>') == ["table-min-width"])
    expect("a min_width: on a NON-table render is silent",
           rules('<%= render Ui::ChartComponent.new(min_width: "20rem") %>') == [])
    expect("min-w-0 and min-w-full are silent",
           rules('<table class="min-w-0"></table><table class="min-w-full"></table>') == [])

    # table-no-details.
    expect("a table with no details target in its directory is caught",
           rules("<table><tr><td>x</td></tr></table>", has_target=False) == ["table-no-details"])
    expect("a NEW button opening the modal is not a details target",
           not opens_a_record('<%= link_to "New person", new_person_path, data: { turbo_frame: "modal" } %>\n'
                              '<td><%= link_to p.name, p %></td>'))
    expect("edit and delete links opening the modal are not details targets either",
           not opens_a_record('<%= link_to "Edit", edit_person_path(p), data: { turbo_frame: "modal" } %>'
                              '<%= button_to "Delete", p, method: :delete, data: { turbo_frame: "modal" } %>'))
    expect("a row link into the modal IS a details target, beside a New button",
           opens_a_record('<%= link_to "New", new_person_path, data: { turbo_frame: "modal" } %>' + LINKED_ROW))
    expect("a target in the same directory satisfies it",
           rules("<table><tbody><%= render @people %></tbody></table>", has_target=True) == [])
    expect("a declared non-index table with a reason is silent",
           rules("<%# table-without-details: permissions matrix, a form %>\n<table></table>", has_target=False) == [])
    expect("a declaration with no reason is not a declaration",
           rules("<%# table-without-details: %>\n<table></table>", has_target=False) == ["table-no-details"])

    # THE ENTRY POINT, on a tree: the partial holds the link, the index holds the table.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app/views/people").mkdir(parents=True)
        (root / "app/views/reports").mkdir(parents=True)
        (root / "app/views/people/index.html.erb").write_text("<table><tbody><%= render @people %></tbody></table>")
        (root / "app/views/people/_person.html.erb").write_text(f"<tr>{LINKED_ROW}</tr>")
        (root / "app/views/reports/index.html.erb").write_text('<div class="overflow-x-auto"><table></table></div>')
        (root / "app/views/notification_mailer").mkdir(parents=True)
        (root / "app/views/notification_mailer/notify.html.erb").write_text("<table><tr><td>hi</td></tr></table>")
        (root / "app/views/layouts").mkdir(parents=True)
        (root / "app/views/layouts/mailer.html.erb").write_text("<table><tr><td><%= yield %></td></tr></table>")
        # THE CONTROL: a view merely NAMED like mail, outside a mailer directory, is still judged.
        (root / "app/views/reports/mailer_stats.html.erb").write_text("<table><tr><td>x</td></tr></table>")
        found, examined = run(root)
        got = sorted(content_floors.rule_of(f) for f in found)
        expect("run(): the partial's link satisfies its index", not any("people/" in f for f in found))
        expect("run(): the other directory reports both its defects",
               got.count("table-scroll-wrapper") == 1 and got.count("table-no-details") == 2)
        expect("run(): mailer views and layouts are not judged — email is laid out with tables",
               not any("mailer/" in f or "layouts/mailer" in f for f in found))
        expect("run(): a non-mailer view named like mail is still judged",
               any(f.startswith("app/views/reports/mailer_stats.html.erb:") for f in found))
        expect("run(): every file was examined", examined == 6)
        expect("run(): a finding carries file and line", any(f.startswith("app/views/reports/index.html.erb:1: ") for f in found))
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app/assets/tailwind").mkdir(parents=True)
        (root / "app/assets/tailwind/application.css").write_text("@utility scroll-x {\n  overflow-x: auto;\n}\n")
        (root / "app/components/ui").mkdir(parents=True)
        (root / "app/components/ui/table_component.html.erb").write_text(
            '<div class="scroll-x"><table><tr><td><%= link_to "x", "/x", data: { turbo_frame: "modal" } %></td></tr></table></div>')
        found, _ = run(root)
        expect("run(): an app's own scroll utility is read from its CSS",
               [content_floors.rule_of(f) for f in found] == ["table-scroll-wrapper"])

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_table_layout selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    ap.add_argument("--set-floor", action="store_true",
                    help="record the CURRENT findings as this project's sanctioned floor (#1187)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    root = Path(args.root).resolve()
    findings, examined = run(root)
    if examined == 0:
        print(f"NOT APPLICABLE: no app/views or app/components under {root} — this check examined nothing.")
        return 0
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} view/component file(s) examined; {len(findings)} finding(s).")
    if args.set_floor:
        return content_floors.set_floor(root, GATE, findings)
    code, lines = content_floors.verdict(root, GATE, findings)
    if lines:
        print(f"\nagainst {content_floors.FLOORS}:")
        for line in lines:
            print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
