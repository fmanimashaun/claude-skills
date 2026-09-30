#!/usr/bin/env python3
"""A change a user can see is built only after the owner approved a clickable mock-up (#1376).

Run:  check_mockup_gate.py --base dev [--root DIR]            # the branch's diff, before merge
      check_mockup_gate.py --paths app/views/a.html.erb ...   # the plan's files, at Phase 1
      check_mockup_gate.py --selftest
      optional on either: --record docs/product/mockups/<slug>.md

Exit: 0 no user-visible change, or an approved mock-up is recorded, or the project declared the
gate off · 1 user-visible change with no approved mock-up recorded · 2 cannot classify.

WHY. On a downstream app's first production day the owner reported about 14 screens built unlike
what had been agreed in conversation: tables for cards, page forms for modals, a link for a
dropdown. Each cost a PR, specs, screenshots and a redeploy. The one screen whose clickable mock-up
was approved FIRST was right in one round, because the build had a target. So the owner's rule: a
user-visible change waits for an approved mock-up, whatever the issue's label says.

UI SCOPE IS A PATH RULE, not a judgement. A change touches what a user sees when it touches
UI_PATHS: views (not JSON/XML templates, which API clients read), components, JavaScript,
stylesheets, helpers, and locale files (visible copy). Everything else is backend. A mixed change is
UI scope.

THE RECORD is `docs/product/mockups/<slug>.md`, carrying one `Key: value` line for each of RECORD_KEYS.
It must name the mock-up (a URL, or a repo file that exists), the issue, who approved it, the
approval itself as a link to the comment where they said so, and the widths (a phone width ≤ 480
and a desktop width ≥ 1024) and states it covers. The branch must add or change the record, or name
it with --record. An approval with no link is a sentence anyone can type.

WHAT IT DOES NOT: prove the linked comment says "approved", or that the build matches the mock-up.
The first is the reviewer's click; the second is the screenshot comparison before merge.

OPT-OUT. A project without a design reviewer declares `mockup-gate: off` on its own line in
GUARDRAILS.md (setup-flow asks). Undeclared means ON: the owner set the default.

Stdlib only; git is read like classify_door.py reads it, through the same helper.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_door import Unusable, diff  # noqa: E402  -- one diff reader, never a second

UI_PATHS = (re.compile(r"^app/views/"), re.compile(r"^app/components/"), re.compile(r"^app/javascript/"),
            re.compile(r"^app/assets/(stylesheets|tailwind|images)/"), re.compile(r"^app/helpers/"),
            re.compile(r"^config/locales/"),
            # What Rails 8 generates for a user to see outside app/views: the error pages, the icon,
            # the favicon (pre-release review of #1381).
            re.compile(r"^public/[^/]+\.(html|png|svg|ico|webmanifest)$"))
# An API template is read by a client, not seen by a person -- except the PWA manifest, which holds
# the installed app's name and icons.
NOT_UI = re.compile(r"\.(json|xml)(\.[a-z]+)?$")
SEEN_ANYWAY = re.compile(r"^app/views/pwa/")
RECORD_DIR = "docs/product/mockups/"
RECORD_KEYS = ("Mock-up", "Issue", "Approved-by", "Approval", "Widths", "States")
APPROVAL_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/(issues|pull)/\d+"
                          r"#(issuecomment-\d+|discussion_r\d+|pullrequestreview-\d+)$")
MOCK_FILE = re.compile(r"\.(html?|png|jpe?g|webp|pdf|svg)$", re.I)
ISSUE_REF = re.compile(r"^(#\d+|https://github\.com/[^/\s]+/[^/\s]+/issues/\d+)\b")
# Space and tab only: CommonMark counts no other character as indentation (spec 0.31.2 §2.1), so a
# line opening with a non-breaking space is paragraph text, not an indented declaration (#1490).
OPT_OUT = re.compile(r"^[ \t]*(?:[-*+][ \t]*)?`?mockup-gate:[ \t]*off`?[ \t]*$", re.M | re.I)


def ui_paths(paths: list[str]) -> list[str]:
    return sorted(p for p in paths if any(r.match(p) for r in UI_PATHS)
                  and (SEEN_ANYWAY.match(p) or not NOT_UI.search(p)))


def declared_off(root: Path) -> bool:
    g = root / "GUARDRAILS.md"
    if not g.is_file():
        return False
    # A fenced example of the line documents the opt-out; it does not declare it (review of #1381).
    # An UNTERMINATED fence runs to the end of the file (#1430) -- stricter than a renderer, which
    # ends one at the close of its list item; list-scoped fences are not modelled here. The
    # regex this replaces removed only closed fences, so an opt-out after a stray ``` still counted.
    # ...and an INDENTED code block is an example too (#1490).
    return bool(OPT_OUT.search(outside_indented_code(unfenced(g.read_text(encoding="utf-8")))))



HTML_COMMENT = re.compile(r" {0,3}<!--")
HTML_RAW = re.compile(r" {0,3}<(pre|script|style|textarea)(?:[ \t>]|$)", re.I)
HTML_TAG_LINE = re.compile(r" {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:[ \t][^<>]*)?/?>[ \t]*$")
HTML_BLOCK = re.compile(r" {0,3}</?(?:address|article|aside|blockquote|body|details|dialog|dd|div|dl|dt|"
                        r"fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|section|"
                        r"summary|table|tbody|td|tfoot|th|thead|tr|ul)(?:[ \t/>]|$)", re.I)


def unfenced(text: str) -> str:
    """The lines outside fenced code blocks and HTML blocks, each block left as one blank line.

    A fence closes on the same character, at least as long, and -- conservatively -- no more indented
    than it opened: CommonMark closes only within 3 columns of the container, and a closer indented
    further is content, so closing on it let the opt-out after it count (#1496 review, R5). An HTML
    comment hides its lines, and an HTML block's lines are markup, not a declaration (R6).
    """
    out, fence, fence_col, html_end = [], "", 0, None
    in_para = False                # a lone-tag HTML block (type 7) cannot interrupt a paragraph
    for line in text.splitlines():
        # Any indentation: in GUARDRAILS.md a fence usually sits inside a list item (review of PR #1478).
        # A BACKTICK opener may not contain another backtick (CommonMark), so "```x``` inline" is a
        # code span, not a fence -- read as one it swallowed a real opt-out below it (final review).
        m = re.match(r"^\s*(`{3,})(?=[^`]*$)|^\s*(~{3,})", line)
        run = (m.group(1) or m.group(2)) if m else ""
        if fence:
            if (run and run[0] == fence[0] and len(run) >= len(fence) and not line.strip()[len(run):].strip()
                    and _columns(line)[0] <= fence_col):
                fence = ""
            continue
        if html_end is not None:
            if (html_end == "" and not line.strip()) or (html_end and html_end in line.lower()):
                html_end = None
            continue
        if run:
            fence, fence_col = run, _columns(line)[0]
            out.append("")          # the block ends any open paragraph (outside_indented_code)
            continue
        raw = HTML_RAW.match(line)
        if HTML_COMMENT.match(line) or raw or HTML_BLOCK.match(line) or (not in_para and HTML_TAG_LINE.match(line)):
            end = "-->" if HTML_COMMENT.match(line) else (f"</{raw.group(1).lower()}>" if raw else "")
            if not (end and end in line.lower()[4:]):
                html_end = end
            out.append("")
            in_para = False
            continue
        in_para = bool(line.strip())
        out.append(line)
    return "\n".join(out)


LIST_MARKER = re.compile(r"(?:[-*+]|\d{1,9}[.)])(?=[ \t]|$)")
# A heading or thematic break is a block of its own, not a paragraph: an indented line after it is code.
NOT_PARAGRAPH = re.compile(r"#{1,6}(?:[ \t]|$)|(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
SETEXT = re.compile(r"(?:=+|-+)[ \t]*$")


def _columns(line: str, start: int = 0, col: int = 0) -> tuple[int, int]:
    """(column reached, index reached) after the spaces and tabs from `start`. A tab advances to the
    next multiple of 4, counted from the line's start (CommonMark 0.31.2 §2.2, Ex 1-11)."""
    i = start
    while i < len(line) and line[i] in " \t":
        col = col + 1 if line[i] == " " else col + 4 - col % 4
        i += 1
    return col, i


def outside_indented_code(text: str) -> str:
    """`text` without its INDENTED code blocks (#1490), by CommonMark 0.31.2's block rules:

    - a line indented 4+ columns past its container is code (§4.4), but NOT when it would interrupt
      a paragraph (Ex 113) -- then it is the paragraph's continuation;
    - a list item's content column is its marker's indentation + marker width + 1-4 following
      columns, or +1 when 5+ follow or the item is blank (§5.2 rules 1-3, Ex 270-288); an item that
      starts blank and meets a blank line is empty and closes (§5.2);
    - a nested marker sits 0-3 columns past that content column (Ex 294), so under `- Gates:`
      four spaces is a nested item and six, after a blank line, is code (Ex 270);
    - a line indented less than an open item's content column ends the item, unless it lazily
      continues that item's paragraph (Ex 290) -- and only paragraph TEXT continues lazily: a
      heading, break or quote there ends the list (#1496 review, R1);
    - headings (ATX, and setext underlines `===` / `---` after a paragraph), breaks and an empty
      quote are not paragraphs (R2, R4).
    Only space and tab indent (§2.1). Fenced and HTML blocks are gone already (`unfenced`).
    """
    kept: list[str] = []
    items: list[list] = []         # [content column, still empty] per open list item, outermost first
    prev = "blank"                 # the kind of the last non-removed line: blank | para | code
    for line in text.split("\n"):
        if not line.strip(" \t"):
            if items and items[-1][1]:
                items.pop()        # a blank-started item meeting a blank line is empty (§5.2)
            kept.append(line)
            prev = "blank"
            continue
        col, i = _columns(line)
        marker = LIST_MARKER.match(line, i)
        # A block can start here only within 3 columns of the container the line would land in.
        land = max((c for c, _ in items if c <= col), default=0)
        own_block = col - land <= 3 and (NOT_PARAGRAPH.match(line, i) or line.startswith(">", i))
        if items and col < items[-1][0] and prev == "para" and not marker and not own_block:
            kept.append(line)      # lazy continuation of the open paragraph: text, not code
            continue
        while items and col < items[-1][0]:
            items.pop()
        if items:
            items[-1][1] = False
        base = items[-1][0] if items else 0
        if col - base >= 4:
            if prev == "para":
                kept.append(line)  # an indented code block cannot interrupt a paragraph
            else:
                prev = "code"      # an example: dropped
            continue
        if prev == "para" and SETEXT.match(line, i):
            prev = "blank"         # a setext underline: the paragraph above was a heading
            kept.append(line)
            continue
        if NOT_PARAGRAPH.match(line, i):
            prev = "blank"
            kept.append(line)
            continue
        if line.startswith(">", i):
            prev = "para" if line[i + 1:].strip(" \t") else "blank"
            kept.append(line)
            continue
        if marker:
            width = col + (marker.end() - i)
            after, j = _columns(line, marker.end(), width)
            blank_item = j >= len(line)
            items.append([width + 1 if blank_item or after - width >= 5 else after, blank_item])
            starts_block = not blank_item and (NOT_PARAGRAPH.match(line, j) or line.startswith(">", j))
            # 5+ columns after the marker: the item's content OPENS with an indented code block (§5.2 rule 2)
            opens_code = not blank_item and after - width >= 5
            prev = "code" if opens_code else ("blank" if blank_item or starts_block else "para")
        else:
            prev = "para"
        kept.append(line)
    return "\n".join(kept)


def record_problems(root: Path, rel: str) -> list[str]:
    path = root / rel
    if not path.is_file():
        return [f"{rel}: no such mock-up record"]
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**([A-Za-z-]+)\**:\s*(.*?)\s*$", line)
        if m and m.group(1) in RECORD_KEYS:
            fields[m.group(1)] = m.group(2)
    out = [f"{rel}: no `{k}:` line" for k in RECORD_KEYS if not fields.get(k)]
    mock = fields.get("Mock-up", "")
    if mock.startswith("https://"):
        if not re.match(r"^https://[^/\s]+\.[^/\s]+", mock):
            out.append(f"{rel}: Mock-up {mock!r} is not a link to anything")
    elif mock and ((root / mock).resolve() == path.resolve()
                   or ((root / mock).exists() and (root / mock).samefile(path))):
        # `samefile` too: a hard link is the record under another name, and resolve() keeps names (#1479).
        # A record naming itself satisfied "a file under docs/product/mockups/" (#1430).
        out.append(f"{rel}: Mock-up names this record itself; name the mock-up it records")
    elif mock and (root / mock).resolve().suffix.lower() == ".md":
        # ...and so did naming another record. A record is not a mock-up, whatever a symlink calls it
        # -- the RESOLVED target is judged. Any other committed file under the folder is still a
        # mock-up (.gif, .avif, .html.erb): an allow-list refused real ones (review of PR #1478).
        out.append(f"{rel}: Mock-up {mock!r} is a Markdown record, not a mock-up file")
    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):
        out.append(f"{rel}: Mock-up {mock!r} is neither an https link nor a mock-up file in the repo "
                   f"(under {RECORD_DIR}, or an .html/.png/.jpg/.webp/.pdf/.svg)")
    issue = fields.get("Issue", "")
    if issue and not ISSUE_REF.match(issue):
        out.append(f"{rel}: Issue {issue!r} must name the issue this mock-up answers (#n, or its URL)")
    approval = fields.get("Approval", "")
    if approval and not APPROVAL_URL.match(approval):
        out.append(f"{rel}: Approval must link the comment where the owner approved "
                   f"(…/issues/N#issuecomment-M), got {approval!r}")
    widths = [int(w) for w in re.findall(r"\d+", fields.get("Widths", ""))]
    if fields.get("Widths") and not (any(w <= 480 for w in widths) and any(w >= 1024 for w in widths)):
        out.append(f"{rel}: Widths {fields['Widths']!r} must include a phone width (≤ 480) and a desktop width (≥ 1024)")
    return out


def run(root: Path, changed: list[str], record: str | None) -> tuple[int, list[str]]:
    """The whole decision. main() and the selftest both come through here."""
    ui = ui_paths(changed)
    if not ui:
        return 0, ["no user-visible change: no mock-up needed"]
    if declared_off(root):
        return 0, [f"{len(ui)} user-visible file(s), and GUARDRAILS.md declares `mockup-gate: off`"]
    records = [record] if record else sorted(p for p in changed if p.startswith(RECORD_DIR) and p.endswith(".md")
                                             and Path(p).name.lower() != "readme.md")
    if not records:
        return 1, [f"{len(ui)} user-visible file(s) ({', '.join(ui[:5])}{' …' if len(ui) > 5 else ''}) and no "
                   f"approved mock-up: publish one, stop for the owner's approval, then record it in "
                   f"{RECORD_DIR}<slug>.md"]
    problems = [p for r in records for p in record_problems(root, r)]
    if problems:
        return 1, problems
    return 0, [f"{len(ui)} user-visible file(s); approved mock-up recorded in {', '.join(records)}"]


# --------------------------------------------------------------------------- selftest

GOOD = """# Mock-up — invoice bell
Mock-up: https://example.com/mockups/bell
Issue: #12
Approved-by: @owner
Approval: https://github.com/acme/app/issues/12#issuecomment-99
Widths: 1280, 390
States: default, empty, error
"""


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    check_that("a view is UI scope", ui_paths(["app/views/invoices/index.html.erb"]) != [])
    check_that("a component is UI scope", ui_paths(["app/components/bell_component.rb"]) != [])
    check_that("a Stimulus controller is UI scope", ui_paths(["app/javascript/controllers/bell_controller.js"]) != [])
    check_that("a locale file (visible copy) is UI scope", ui_paths(["config/locales/en.yml"]) != [])
    check_that("CONTROL: a model, migration, job and spec are not UI scope",
               ui_paths(["app/models/invoice.rb", "db/migrate/1_x.rb", "app/jobs/sync_job.rb",
                         "spec/models/invoice_spec.rb"]) == [])
    check_that("CONTROL: a JSON template is read by a client, not seen",
               ui_paths(["app/views/api/invoices/show.json.jbuilder"]) == [])
    # Pre-release review of #1381: what Rails 8 generates for a user to see outside app/views.
    check_that("a public error page is UI scope", ui_paths(["public/404.html"]) == ["public/404.html"])
    check_that("the app icon is UI scope", ui_paths(["public/icon.png"]) == ["public/icon.png"])
    check_that("an image asset is UI scope", ui_paths(["app/assets/images/logo.svg"]) != [])
    check_that("the PWA manifest is UI scope although it is JSON",
               ui_paths(["app/views/pwa/manifest.json.erb"]) == ["app/views/pwa/manifest.json.erb"])
    check_that("CONTROL: robots.txt and a public subdirectory file are not UI scope",
               ui_paths(["public/robots.txt", "public/assets/app-1.css"]) == [])
    check_that("a mixed change is UI scope",
               ui_paths(["app/models/invoice.rb", "app/views/invoices/_row.html.erb"]) == ["app/views/invoices/_row.html.erb"])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rec = root / "docs/product/mockups"
        rec.mkdir(parents=True)
        view = ["app/views/invoices/index.html.erb"]

        code, _ = run(root, ["app/models/invoice.rb"], None)
        check_that("CONTROL: a backend-only change passes with no record", code == 0)
        code, msg = run(root, view, None)
        check_that("a UI change with no mock-up record is held", code == 1, msg)

        (rec / "bell.md").write_text(GOOD)
        code, msg = run(root, view + ["docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a UI change with a complete, approved record passes", code == 0, msg)
        code, msg = run(root, view, "docs/product/mockups/bell.md")
        check_that("CONTROL: --record names a record the branch did not touch", code == 0, msg)

        def with_record(text: str) -> tuple[int, list[str]]:
            (rec / "r.md").write_text(text)
            return run(root, view + ["docs/product/mockups/r.md"], None)

        code, msg = with_record(GOOD.replace("Approval: https://github.com/acme/app/issues/12#issuecomment-99\n", ""))
        check_that("a record with no approval line is held", code == 1 and any("Approval" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://github.com/acme/app/issues/12#issuecomment-99", "approved in chat"))
        check_that("an approval that is not a comment link is held", code == 1 and any("link the comment" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 1280"))
        check_that("a mock-up with no phone width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 390"))
        check_that("a mock-up with no desktop width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/missing.html"))
        check_that("a mock-up file that does not exist is held", code == 1 and any("neither" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.html").write_text("<html></html>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.html"))
        check_that("CONTROL: a committed mock-up file passes", code == 0, msg)

        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "https://"))
        check_that("a bare https:// is not a mock-up", code == 1 and any("not a link" in m for m in msg), msg)
        (root / "GUARDRAILS.md").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "GUARDRAILS.md"))
        check_that("an arbitrary repo file is not a mock-up", code == 1 and any("mock-up file" in m for m in msg), msg)
        (root / "notes.txt").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "notes.txt"))
        check_that("an arbitrary NON-Markdown repo file outside the folder is not a mock-up",
                   code == 1 and any("neither" in m for m in msg), msg)
        (root / "GUARDRAILS.md").unlink()
        code, msg = with_record(GOOD.replace("Issue: #12", "Issue: the bell one"))
        check_that("a record that names no issue is held", code == 1 and any("Issue" in m for m in msg), msg)
        (rec / "README.md").write_text("# How mock-up records work\n")
        code, msg = run(root, view + ["docs/product/mockups/README.md", "docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a README in the records folder is not a record", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nTo opt out, add:\n\n```markdown\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("a fenced example of the opt-out line is not a declaration", code == 1, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("a project that declared the gate off is not held", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nWe might set mockup-gate: off one day.\n")
        code, msg = run(root, view, None)
        check_that("CONTROL: prose mentioning the key is not a declaration", code == 1, msg)
        # #1430: an opt-out inside an UNTERMINATED fence is still inside a fence.
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nExample:\n\n```\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430: an opt-out inside an unterminated fence is not a declaration", code == 1, msg)
        # #1490: an INDENTED code block is an example too, by CommonMark 0.31.2's rules (verified by
        # doctrine-verifier against spec.txt at tag 0.31.2). Each shape is run through run(), the
        # entry point, so a scanner the gate does not call cannot pass these. (declared, expected).
        O = "mockup-gate: off"
        for label, text, declared in (
            ("an indented code block after a blank line is an example (§4.4)", f"Example:\n\n    - {O}\n", False),
            ("a tab indents to column 4 (§2.2)", f"Example:\n\n\t- {O}\n", False),
            ("a space then a tab is 4 columns, not 5 (§2.2)", f"Example:\n\n \t- {O}\n", False),
            ("CONTROL: 4 spaces directly under a paragraph continue it (Ex 113)", f"Example:\n    {O}\n", True),
            ("CONTROL: 4 spaces under `- Gates:` is a nested item (Ex 294)", f"- Gates:\n    - {O}\n", True),
            ("CONTROL: a nested item after a continuation line stays in the list", f"- Gates:\n  more text\n    - {O}\n", True),
            ("six spaces after a blank line inside an item is code (Ex 270)", f"- Gates:\n\n      {O}\n", False),
            ("CONTROL: an ordered item's content column is 3", f"1. Gates:\n   - {O}\n", True),
            ("CONTROL: a `+` bullet declares", f"+ {O}\n", True),
            ("an indented line after a heading is code (a heading is no paragraph)", f"# Gates\n    - {O}\n", False),
            ("an indented line after a fenced block is code", f"Text\n```\nx\n```\n    - {O}\n", False),
            ("a list ends at a top-level paragraph, and code after it is code", f"- a\n\nPara\n\n    - {O}\n", False),
            ("a non-breaking space is not indentation (§2.1)", f"Example:\n\n\u00a0\u00a0\u00a0\u00a0- {O}\n", False),
            ("CONTROL: three spaces before a top-level marker is still an item (Ex 286)", f"   - {O}\n", True),
            # Discriminating shapes: each is decided by one rule, after a blank line where the paragraph
            # exemption cannot rescue a wrong column.
            ("CONTROL: two spaces then a tab inside an item reach column 4, item text (§2.2)", f"- Gates:\n\n  \t{O}\n", True),
            ("CONTROL: a nested item after a blank line sits at the item's content column", f"- Gates:\n\n    - {O}\n", True),
            ("CONTROL: a lazy line keeps the item open for a nested item below it (Ex 290)", f"- Gates\nlazy text\n\n    - {O}\n", True),
            ("CONTROL: `1.` opens an item whose content column is 3", f"1. Gates:\n\n    - {O}\n", True),
            # PR #1496's review, measured against markdown-it-py (commonmark) over 200k variants:
            ("R1: a heading under an item's text ends the list; the code after it is code",
             f"- Keep specs green\n## Opting out\n\n    - {O}\n", False),
            ("R2: a setext `===` underline makes the paragraph a heading; the line after is code",
             f"Opting out\n==========\n    - {O}\n", False),
            ("R2: a setext `-` underline is a heading, not an empty item", f"Text\n-\n    - {O}\n", False),
            ("R3: an item that starts blank and meets a blank line is empty and closes",
             f"-\n\n    - {O}\n", False),
            ("R4: a heading as an item's content is no paragraph", f"- # H\n      {O}\n", False),
            ("R5: a closing fence indented further than it opened does not close it",
             f"```\nx\n     ```\n- {O}\n", False),
            ("R6: an opt-out inside an HTML comment is hidden", f"<!--\n- {O}\n-->\n", False),
            ("R6: an opt-out inside an HTML block is markup", f"<div>\n- {O}\n</div>\n", False),
            ("R6: a lone tag line opens an HTML block to the blank line", f"</pre>\n- {O}\n", False),
            ("CONTROL: after an HTML block and a blank line the opt-out counts", f"<div>\nx\n</div>\n\n- {O}\n", True),
            ("an empty quote is no paragraph; the indented line after it is code", f">\n    - {O}\n", False),
            ("an item opening with 5+ columns opens with code, so the next line is code too",
             f"-     five\n      {O}\n", False),
            ("CONTROL: `1)` opens an item whose content column is 3", f"1) Gates:\n\n    - {O}\n", True),
        ):
            (root / "GUARDRAILS.md").write_text(f"# Guardrails\n\n{text}", encoding="utf-8")
            code, msg = run(root, view, None)
            check_that(f"#1490: {label}", (code == 0) == declared, (code, msg))
        # R8: the line `/rails-flow:setup-flow` scaffolds must still declare -- read from the shipped
        # command itself, not retyped, so a doc edit that breaks it fails here.
        setup = Path(__file__).resolve().parents[1] / "commands" / "setup-flow.md"
        if setup.is_file():
            block = re.search(r"```markdown\n(- mockup-gate: off\n)```", setup.read_text(encoding="utf-8"))
            check_that("the scaffolded opt-out block is present in setup-flow.md", bool(block), setup)
            if block:
                (root / "GUARDRAILS.md").write_text("# Guardrails\n\n" + block.group(1), encoding="utf-8")
                code, msg = run(root, view, None)
                check_that("CONTROL: the opt-out setup-flow scaffolds still declares", code == 0, (code, msg))
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n```\nexample\n```\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430 CONTROL: an opt-out AFTER a closed fence still declares", code == 0, msg)
        (root / "GUARDRAILS.md").unlink()
        # #1430: a record may not name itself, or another record, as its mock-up.
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r.md"))
        check_that("#1430: a record naming itself is held", code == 1 and any("itself" in m for m in msg), msg)
        # #1479: a HARD LINK is the record under another name; resolve() keeps the name, samefile
        # does not. Named .html so the Markdown-record rule cannot be what holds it. Portable to Linux.
        (rec / "r.md").write_text(GOOD)
        alias = rec / "r-alias.html"
        alias.unlink(missing_ok=True)
        os.link(rec / "r.md", alias)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r-alias.html"))
        check_that("#1479: a record naming itself by another name is held",
                   code == 1 and any("itself" in m for m in msg), msg)
        alias.unlink()
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.md"))
        check_that("#1430: a record naming another record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.svg"))
        check_that("#1430 CONTROL: a committed .svg mock-up passes", code == 0, msg)
        (root / "design").mkdir(exist_ok=True)
        (root / "design/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "design/bell.svg"))
        check_that("#1430: an .svg mock-up OUTSIDE the records folder is a mock-up file", code == 0, msg)
        # Review of PR #1478: an allow-list refused real mock-ups committed under the folder.
        for name in ("bell.gif", "bell.avif", "bell.html.erb"):
            (root / "docs/product/mockups" / name).write_text("x")
            code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", f"docs/product/mockups/{name}"))
            check_that(f"PR #1478 review: a committed {name} under the folder is a mock-up", code == 0, msg)
        # ...and a symlink is judged by its TARGET: o.html -> bell.md is a record, not a mock-up.
        (root / "docs/product/mockups/o.html").symlink_to("bell.md")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/o.html"))
        check_that("PR #1478 review: a symlink onto a record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        # An example opt-out in an INDENTED fence (inside a list item) is still an example.
        (root / "GUARDRAILS.md").write_text("# G\n\n- Example:\n\n    ```\n    - mockup-gate: off\n    ```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 review: an opt-out in an indented fence is not a declaration", code == 1, msg)
        # Final review: a line OPENING with an inline code span is not a fence.
        (root / "GUARDRAILS.md").write_text("# G\n\n```x``` inline\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review: a code span at line start does not fence the opt-out", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# G\n\n```sh\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review CONTROL: an info-string fence still fences", code == 1, msg)
        (root / "GUARDRAILS.md").unlink()

    # The git path main() takes: a new, untracked view must count (the #1341 blind spot). A FRESH
    # directory: the one above holds untracked records, which would rightly count as on the branch.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        def git(*a: str) -> None:
            subprocess.run(("git",) + a, cwd=root, check=True, capture_output=True)
        git("init", "-q", "-b", "dev"); git("config", "user.email", "t@example.com"); git("config", "user.name", "t")
        (root / "README.md").write_text("x\n"); git("add", "README.md"); git("commit", "-qm", "base")
        git("checkout", "-q", "-b", "feature")
        (root / "app/views/invoices").mkdir(parents=True)
        (root / "app/views/invoices/index.html.erb").write_text("<table></table>\n")   # untracked
        code, msg = run(root, list(diff(root, "dev")), None)
        check_that("an untracked new view, read through the diff, is held", code == 1, msg)
        try:
            diff(root, "no-such-base")
            check_that("an unresolvable base is unusable", False)
        except Unusable:
            pass

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_mockup_gate selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_mockup_gate.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="dev")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--paths", nargs="+", help="the plan's files, instead of the branch's diff")
    ap.add_argument("--record", help=f"the mock-up record, when the branch does not touch one ({RECORD_DIR}<slug>.md)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        changed = a.paths if a.paths else list(diff(a.root, a.base))
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified change is not exempt; ask the owner", file=sys.stderr)
        return 2
    code, lines = run(a.root, changed, a.record)
    print(("MOCK-UP GATE: HOLD -- " if code else "MOCK-UP GATE: ok -- ") + lines[0])
    for line in lines[1:]:
        print(f"  {line}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
