#!/usr/bin/env python3
"""Turbo Frames and form-response flow: three static rules (#2278).

Run:  python3 check_turbo_flow.py [--project DIR]
      python3 check_turbo_flow.py --selftest

WHY. Three mistakes in a Hotwire app look fine in code review and fail in the browser, and each has a plain source signature (verified against Turbo v8.0.23
by `doctrine-verifier`; see rails-stack's `skills/hotwire/references/frames-and-modals.md`):

  1. MODAL TEMPLATES. A link with `data-turbo-frame="modal"` loads the response's matching `<turbo-frame id="modal">` into the shared frame. The template that
     link reaches (`new`, `edit`, a confirmation view) must render inside `turbo_frame_tag "modal"` (or `<turbo-frame id="modal">`); without it the frame shows
     "Content missing" and nothing opens. The link's path helper (`new_invoice_path`, `edit_invoice_path(i)`, `delete_confirmation_invoice_path(i)`) is mapped to
     `app/views/<plural>/<action>.html.*`; a helper that maps to no template is counted as "not located", never as clean.
  2. 422 ON A FAILED FORM. A `render :new` or `render :edit` in the `else` of a save, without a `status:`, answers 200. A Turbo Drive form submission that gets
     a 200 with no redirect is not rendered at all ("Form responses must redirect to another location"): the form seems to do nothing. A `render :new` / `:edit`
     (or the string forms) with no `status:` in the same statement is a finding; `status: :unprocessable_entity`, `:unprocessable_content` or `422` all pass.
  3. TURBO STREAM WITHOUT HTML. A `respond_to` block with `format.turbo_stream` and neither `format.html` nor `format.any` leaves a client without Turbo, or one
     whose stream request fails, with no usable answer: keep an HTML branch (usually a redirect).

WHAT IT IS HONESTLY NOT. It reads source and never runs it. It cannot tell whether a `render :new` is inside a failed-save branch (every `render :new` or
`render :edit` without a status is reported, including one a controller reaches only on a GET, where a 200 is right: give that one an explicit `status: :ok`).
A modal link built at run time (a `url_for` with variables, a link in a helper) is not seen. The rendered-page half (a crawl judge for `turbo:frame-missing`
and `.turbo-frame-error`) is not here: it needs a stack-specific judge seam in qa-flow, which stays neutral.

Every run prints how many modal links, renders and `respond_to` blocks it read, so a project with none shows 0 and not a bare pass.

Exit codes: 0 clean, 1 findings. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

VIEW_SUFFIXES = (".erb", ".haml", ".slim")
LINK_TO = re.compile(r"\blink_to\b|\bbutton_to\b")
MODAL_DATA = re.compile(r"""turbo_frame:\s*(?::modal\b|["']modal["'])|["']turbo_frame["']\s*=>\s*["']modal["']|data-turbo-frame\s*=\s*["']modal["']""")
PATH_HELPER = re.compile(r"\b([a-z][a-z0-9_]*)_path\b")
MODAL_FRAME = re.compile(r"""turbo_frame_tag\s*\(?\s*(?::modal\b|["']modal["'])|<turbo-frame\b[^>]*\bid\s*=\s*["']modal["']""")
RENDER_FORM = re.compile(r"""\brender\s*\(?\s*(?::(?:new|edit)\b|["'](?:new|edit)["'])([^\n]*)""")
RESPOND_TO = re.compile(r"^([ \t]*)respond_to\b[^\n]*\bdo\b[^\n]*\n", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def files(project: Path, roots: tuple[str, ...], suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(p for root in roots for p in (project / root).rglob("*") if p.is_file() and p.suffix in suffixes)


def template_candidates(project: Path, helper: str) -> list[Path]:
    """`new_invoice` -> app/views/invoices/new.*; `delete_confirmation_invoice` -> app/views/invoices/delete_confirmation.*. Every split of the helper's
    words into action + resource is tried; a plain `s` pluralises."""
    words = helper.split("_")
    found: list[Path] = []
    for i in range(1, len(words)):
        action, resource = "_".join(words[:i]), "_".join(words[i:])
        directory = project / "app" / "views" / f"{resource}s"
        if directory.is_dir():
            found.extend(sorted(directory.glob(f"{action}.*")))
    return found


def modal_links(text: str) -> list[tuple[int, str]]:
    """`(line, path helper)` for each `link_to`/`button_to` whose statement carries a modal turbo-frame target."""
    out = []
    for m in LINK_TO.finditer(text):
        statement = text[m.start(): m.start() + 400].split("\n\n")[0]
        if MODAL_DATA.search(statement):
            helper = PATH_HELPER.search(statement)
            if helper:
                out.append((line_of(text, m.start()), helper.group(1)))
    return out


def respond_blocks(text: str) -> list[tuple[int, str]]:
    """`(line, body)` for each `respond_to ... do` block, the body running to the `end` at the same indent."""
    out = []
    for m in RESPOND_TO.finditer(text):
        rest = text[m.end():]
        end = re.search(rf"^{re.escape(m.group(1))}end\b", rest, re.M)
        out.append((line_of(text, m.start()), rest[: end.start()] if end else rest))
    return out


def run(project: Path) -> tuple[int, list[str]]:
    findings: list[str] = []
    links = unlocated = renders = blocks = 0
    judged: set[Path] = set()
    for path in files(project, ("app/views", "app/components", "app/helpers"), VIEW_SUFFIXES + (".rb",)):
        text = read(path)
        for number, helper in modal_links(text):
            links += 1
            templates = template_candidates(project, helper)
            if not templates:
                unlocated += 1
                continue
            for template in templates:
                if template in judged:
                    continue
                judged.add(template)
                if not MODAL_FRAME.search(read(template)):
                    findings.append(f"{template.relative_to(project)}: reached by a data-turbo-frame=\"modal\" link ({path.relative_to(project)}:{number}, {helper}_path) but "
                                    f"does not render inside turbo_frame_tag \"modal\": the modal frame shows \"Content missing\" and nothing opens")
    for path in files(project, ("app/controllers",), (".rb",)):
        text = read(path)
        for m in RENDER_FORM.finditer(text):
            renders += 1
            statement = m.group(1)
            if not re.search(r"\bstatus:\s*(?::unprocessable_entity|:unprocessable_content|:ok|422|200)\b|\bstatus\s*=>", statement):
                findings.append(f"{path.relative_to(project)}:{line_of(text, m.start())}: `{m.group(0).strip()[:60]}` has no status:, so it answers 200 and a Turbo form "
                                f"submission is not rendered; a failed form needs `status: :unprocessable_entity` (or :unprocessable_content), a GET needs an explicit `status: :ok`")
        for number, body in respond_blocks(text):
            blocks += 1
            if re.search(r"\bformat\.turbo_stream\b", body) and not re.search(r"\bformat\.(?:html|any)\b", body):
                findings.append(f"{path.relative_to(project)}:{number}: respond_to has format.turbo_stream and no format.html (or format.any): a client without Turbo, or a failed "
                                f"stream request, gets no usable answer: keep an HTML branch, usually a redirect")
    summary = f"{links} modal link(s) read ({unlocated} not located), {renders} render :new/:edit, {blocks} respond_to block(s)"
    if findings:
        return 1, [*findings, summary, f"{len(findings)} finding(s)"]
    return 0, [f"turbo flow: {summary}, 0 findings"]


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    def project(files_: dict[str, str]) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files_.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            try:
                return run(root)
            except Exception as exc:  # noqa: BLE001  a crash fails ITS row, with the label, not the whole selftest
                return -1, [f"raised {exc!r}"]

    link = {"app/views/invoices/index.html.erb": '<%= link_to "New", new_invoice_path, data: { turbo_frame: "modal" } %>\n'}
    good_new = {"app/views/invoices/new.html.erb": '<%= turbo_frame_tag "modal" do %>form<% end %>\n'}
    code, out = project({**link, **good_new})
    check("a modal link whose template renders in the modal frame is clean, and the run counts it", code == 0 and "1 modal link(s) read (0 not located)" in out[0])
    code, out = project({**link, "app/views/invoices/new.html.erb": "<h1>New</h1>\n"})
    check("a modal link whose template has no modal frame is a finding with both paths", code == 1 and any("invoices/new.html.erb" in ln and "index.html.erb:1" in ln for ln in out))
    code, out = project({**link, "app/views/invoices/new.html.erb": '<turbo-frame id="modal"><p>x</p></turbo-frame>\n'})
    check("a literal <turbo-frame id=\"modal\"> counts as the modal frame", code == 0)
    code, out = project({"app/views/invoices/index.html.erb": '<%= link_to "Edit", edit_invoice_path(i), data: { turbo_frame: "modal" } %>\n', "app/views/invoices/edit.html.erb": "<h1>Edit</h1>\n"})
    check("an edit_ path helper is mapped to the edit template", code == 1 and any("invoices/edit.html.erb" in ln for ln in out))
    code, out = project({"app/views/invoices/index.html.erb": '<%= link_to "Delete", delete_confirmation_invoice_path(i), data: { turbo_frame: "modal" } %>\n',
                         "app/views/invoices/delete_confirmation.html.erb": "<p>sure?</p>\n"})
    check("a member-action helper (delete_confirmation_invoice_path) is mapped to its template", code == 1 and any("delete_confirmation.html.erb" in ln for ln in out))
    code, out = project({"app/views/invoices/index.html.erb": '<%= link_to "Show", invoice_path(i) %>\n', "app/views/invoices/show.html.erb": "<h1>x</h1>\n"})
    check("a link with no modal target is not judged", code == 0)
    code, out = project({"app/views/invoices/index.html.erb": '<%= link_to "Go", elsewhere_path, data: { turbo_frame: "modal" } %>\n'})
    check("a modal link whose template cannot be located is reported, not passed in silence", code == 0 and "(1 not located)" in out[0])
    ctrl = lambda body: {"app/controllers/invoices_controller.rb": f"class InvoicesController < ApplicationController\n  def create\n    if @invoice.save\n      redirect_to invoices_path\n    else\n{body}\n    end\n  end\nend\n"}  # noqa: E731
    code, out = project(ctrl("      render :new"))
    check("render :new with no status is a finding with its file:line", code == 1 and any("invoices_controller.rb:6" in ln and "no status:" in ln for ln in out))
    code, out = project(ctrl("      render :edit"))
    check("render :edit with no status is a finding", code == 1)
    code, out = project(ctrl('      render "new"'))
    check("the string form render \"new\" with no status is a finding", code == 1)
    code, out = project(ctrl("      render :new, status: :unprocessable_entity"))
    check("render :new with status: :unprocessable_entity is clean", code == 0 and "1 render :new/:edit" in out[0])
    code, out = project(ctrl("      render :new, status: :unprocessable_content"))
    check("render :new with status: :unprocessable_content is clean", code == 0)
    code, out = project(ctrl("      render :edit, status: 422"))
    check("render :edit with status: 422 is clean", code == 0)
    code, out = project(ctrl("      render :new, status: :ok"))
    check("an explicit status: :ok (a GET) is clean", code == 0)
    code, out = project(ctrl("      render partial: \"form\""))
    check("a render of something else is not judged", code == 0)
    resp = lambda body: {"app/controllers/notes_controller.rb": f"class NotesController < ApplicationController\n  def create\n    respond_to do |format|\n{body}    end\n  end\nend\n"}  # noqa: E731
    code, out = project(resp("      format.turbo_stream\n"))
    check("respond_to with format.turbo_stream and no format.html is a finding", code == 1 and any("notes_controller.rb:3" in ln for ln in out))
    code, out = project(resp("      format.turbo_stream\n      format.html { redirect_to notes_path }\n"))
    check("respond_to with both format.turbo_stream and format.html is clean", code == 0 and "1 respond_to block(s)" in out[0])
    code, out = project(resp("      format.turbo_stream\n      format.any { head :ok }\n"))
    check("format.any also counts as the fallback", code == 0)
    code, out = project(resp("      format.json { render json: {} }\n"))
    check("respond_to without a turbo_stream branch is not judged", code == 0)
    code, out = project({"config/application.rb": "module App; end\n"})
    check("a project with none of this reads zero and says so", code == 0 and out[0].startswith("turbo flow: 0 modal link(s) read (0 not located), 0 render :new/:edit, 0 respond_to block(s)"))
    print(f"check_turbo_flow selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_turbo_flow.py", description=__doc__.splitlines()[0])
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="the Rails project (default: the current directory)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    code, lines = run(args.project.resolve())
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
