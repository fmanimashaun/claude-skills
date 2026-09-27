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

THREE RULES, each a construct and never a word:

  table-scroll-wrapper   a `<table>` inside an element whose class scrolls on the x axis
                         (`overflow-x-auto|scroll`, or `overflow-auto|scroll`, which include x).
                         `overflow-x-auto` on a TABLIST is the doctrine and is not a table, so the
                         table has to be INSIDE the scroller, by element nesting, not merely later
                         in the file.
  table-min-width        a `<table>` given a fixed minimum width -- a `min-w-*` class other than
                         `min-w-0`/`min-w-full`, an inline `min-width`, or a `min_width:` keyword
                         passed to a table component (the shape the app above used 25 times).
  table-no-details       a file with a `<table>` and no details target anywhere in its directory:
                         no link into the modal frame (`turbo_frame: "modal"` / `:modal`, or
                         `data-turbo-frame="modal"`). THE DIRECTORY, NOT THE FILE: a Rails index
                         renders its rows from a partial beside it (`<%= render @people %>` ->
                         `_person.html.erb`), and the row link lives in the partial.

A table that is not a record index -- a permissions matrix, a data-viz fallback, invoice lines --
declares itself, in the file, with a reason: `<%# table-without-details: <why> %>`. A declaration
with no reason is not a declaration.

COMMENTS ARE BLANKED before matching (`source_text.py`, #1128), so a file explaining the
anti-pattern is not reported as committing it. The declaration is read from the RAW source, since
it is itself a comment.

KNOWN LIMITS, stated so a clean run is not over-read: a wrapper built with `content_tag`/`tag.div`
rather than markup is not seen, and a table rendered by a component whose own template holds the
`<table>` is judged in that component's file.

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
DECLARES = re.compile(r"table-without-details:[ \t]*\w")
# EMAIL IS LAID OUT WITH TABLES, and has no modal to open. Found on the first run against the app
# behind #1391: both `table-no-details` findings were a mailer layout and a mailer view. Action Mailer
# looks views up under `app/views/<name>_mailer/`, and a mailer layout is `layouts/*mailer*`.
MAILER = re.compile(r"(?:^|/)(?:[\w]+_mailer/|layouts/[\w.]*mailer[\w.]*$)")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}


def _line(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def tables_in(source: str) -> list[tuple[int, str, bool]]:
    """(line, attrs, inside an x-scroller) for every `<table>`, by element nesting."""
    stack: list[tuple[str, bool]] = []
    out: list[tuple[int, str, bool]] = []
    for m in TAG.finditer(source):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
            continue
        cls = CLASS_VALUE.search(attrs)
        scrolls = bool(cls and X_SCROLLER.search(cls.group(2)))
        if name == "table":
            out.append((_line(source, m.start()), attrs, any(s for _, s in stack) or scrolls))
        if name not in VOID and not selfclose:
            stack.append((name, scrolls))
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


def check_file(rel: str, raw: str, directory_has_target: bool) -> list[str]:
    source = strip_comments(raw)
    findings: list[str] = []
    tables = tables_in(source)
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
    targets: dict[Path, bool] = {}
    for p in files:
        if DETAILS_TARGET.search(strip_comments(p.read_text(encoding="utf-8", errors="replace"))):
            targets[p.parent] = True
    findings: list[str] = []
    for p in files:
        if MAILER.search(p.relative_to(root).as_posix()):
            continue
        findings += check_file(str(p.relative_to(root)), p.read_text(encoding="utf-8", errors="replace"),
                               targets.get(p.parent, False))
    return findings, len(files)


# --------------------------------------------------------------------------- selftest

LINKED_ROW = '<td><%= link_to p.name, p, data: { turbo_frame: "modal" } %></td>'


def _selftest() -> int:
    failures: list[str] = []

    def expect(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    def rules(src: str, has_target: bool = True) -> list[str]:
        return [content_floors.rule_of(f) for f in check_file("x.html.erb", src, has_target)]

    # table-scroll-wrapper, and the controls that keep it from firing on everything.
    wrapped = f'<div class="overflow-x-auto">\n  <table class="w-full"><tr>{LINKED_ROW}</tr></table>\n</div>'
    expect("a table inside overflow-x-auto is caught", rules(wrapped) == ["table-scroll-wrapper"])
    expect("a table two levels inside the scroller is caught",
           "table-scroll-wrapper" in rules('<div class="overflow-auto"><section><table></table></section></div>'))
    expect("a scroller on the table itself is caught",
           "table-scroll-wrapper" in rules('<table class="overflow-x-scroll w-full"></table>'))
    expect("a tablist with overflow-x-auto and no table is silent",
           rules('<div role="tablist" class="cluster overflow-x-auto">…</div>') == [])
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
