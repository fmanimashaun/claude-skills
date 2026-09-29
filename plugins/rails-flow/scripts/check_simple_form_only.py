#!/usr/bin/env python3
"""Refuse a form, or a form element, built any way but simple_form (#1383).

Run:  check_simple_form_only.py [--root DIR]
      check_simple_form_only.py --selftest

Exit: 0 clean · 1 findings · 2 unreadable exemption file · 3 not applicable (no simple_form in
Gemfile.lock; reported as n/a by project_gates.py, never as a pass).

WHY. `skills/rails-8/references/ecosystem-gems.md` says "simple_form is mandatory in this stack --
no form, and no form element, is built any other way", and the doctrine map listed that as a
GUARANTEE enforced by `check_mandated_gems.py`. That script proves the gem is INSTALLED, not that
anything USES it, so a project with the gem and every form hand-built read green. The only other
check was design-auditor's review-time grep, `\\b(form_with|form_for)\\b` over app/views, with
three blind spots: other patterns, app/components unread, and advice instead of a gate.

WHAT IT REFUSES, in app/views/**/*.erb and app/components/**/*.erb (ERB and HTML comments blanked,
so line numbers hold and a comment explaining a past fix is not a finding):
  form-with          form_with / form_for (a word boundary keeps simple_form_for out)
  form-tag           form_tag
  raw-form           a literal <form> in markup (button_to's generated form is not markup)
  raw-field          a literal <input>, <select> or <textarea>, except <input type="hidden">
  field-tag-helper   text_field_tag, select_tag, check_box_tag, … (hidden_field_tag is allowed:
                     it carries state, and a user never fills it)
  tag-builder-field  tag.input / tag.select / tag.textarea / tag.form
  raw-builder-call   a Rails field method called ON a simple_form builder -- `f.text_field`,
                     `f.select`, `f.label`, … -- which renders a bare element with no wrapper,
                     label or error inside a form that looks compliant. The builder variable is
                     read from `simple_form_for … do |f|`, never assumed. `f.input`,
                     `f.input_field`, `f.association`, `f.button`, `f.submit`, `f.hidden_field`,
                     `f.error` and `f.simple_fields_for` are simple_form's own.

DECLARED EXCEPTIONS. A deliberate one, such as a one-time-code input that must carry a boolean
attribute, is declared in `.rails-flow/raw-form-exemptions.json`:
    {"exemptions": [{"file": "app/views/sessions/code.html.erb", "rule": "tag-builder-field",
                     "reason": "…"}]}
Every exemption needs a reason, and one that no longer matches anything is itself a finding: an
exemption outliving its code would quietly exempt the next violation in that file.

WHAT IT DOES NOT: see whether a simple_form field RENDERS styled. A stock, unstyled wrapper passes
this check; design-auditor's "the wrapper exists and is styled" check and the browser pass own that.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

RAW_FIELD_METHODS = ("text_field|email_field|password_field|number_field|telephone_field|phone_field|"
                     "url_field|search_field|date_field|datetime_field|datetime_local_field|time_field|"
                     "month_field|week_field|color_field|range_field|file_field|text_area|textarea|"
                     "select|collection_select|grouped_collection_select|time_zone_select|date_select|"
                     "datetime_select|time_select|check_box|checkbox|collection_check_boxes|"
                     "radio_button|collection_radio_buttons|label|fields_for|rich_textarea|rich_text_area")
RULES = (
    ("form-with", re.compile(r"(?<![\w.])(form_with|form_for)\b")),
    ("form-tag", re.compile(r"(?<![\w.])form_tag\b")),
    ("raw-form", re.compile(r"<form\b", re.I)),
    ("raw-field", re.compile(r"<(?:select|textarea)\b|<input\b(?![^>]*\btype\s*=\s*[\"']?hidden\b)", re.I)),
    ("field-tag-helper", re.compile(
        r"(?<![\w.])(text_field|select|check_box|radio_button|text_area|number_field|email_field|"
        r"password_field|date_field|datetime_field|time_field|file_field|search_field|telephone_field|"
        r"url_field|month_field|week_field|color_field|range_field|rich_textarea|rich_text_area)_tag\b")),
    ("tag-builder-field", re.compile(r"\btag\.(input|select|textarea|form)\b")),
)
# The block variable of a simple_form builder. The call may span lines (`simple_form_for @u,\n  url: x
# do |f|`), so match across newlines, but never past the ERB tag that opened it (pre-release review).
BUILDER = re.compile(r"\bsimple_(?:form_for|fields_for)\b[^%]*?\bdo\s*\|\s*(\w+)", re.S)
# A read-only input with no `name` is a DISPLAY (a copyable API key or invite URL), not a form field:
# nothing posts it, and simple_form has nothing to wrap (pre-release review: our own clipboard doctrine).
# ANCHORED TO A REAL ATTRIBUTE (#1443). `\breadonly\b` matched `data-readonly` and `placeholder="readonly"`,
# and `\bname\s*=` matched `data-name=` and missed a name set through ERB (`tag.attributes(name: "x")`),
# so an input that POSTS could be skipped as a display. An attribute follows whitespace; an ERB
# keyword follows neither a word character nor a hyphen.
DISPLAY_INPUT = re.compile(r"(?:(?<=\s)readonly(?=[\s=/>]|$)|(?<![\w-])readonly:\s*true\b)", re.I)
NAMED = re.compile(r"(?:(?<=\s)name\s*=(?!>)|(?<![\w-])name:|(?<![\w-])[:\"']?name[\"']?\s*=>)", re.I)
# A bare `<` cannot occur inside a tag outside ERB or a quoted value, so the match stops there (#1443):
# `[^>]` alone ran on into the NEXT tag and let its `readonly` excuse this input. Quoted values are read
# whole, because `value="a<b"` is legal and stopping at its `<` cut the tag before a later `name=`.
# NO BACKTRACKING (CodeQL py/redos on #1455). `<%.*?%>` could itself span `%><%` into the next ERB tag, so
# an input of many `%><%` split into ERB spans in exponentially many ways (measured: x4 per two repetitions).
# The ERB body is now `[^%]` or a `%` not closing the tag, so it cannot contain `%>` and ends in exactly one
# place; the other alternatives start on disjoint characters. One way to match, so linear time.
WHOLE_TAG = re.compile(r"<input\b(?:<%(?:[^%]|%(?!>))*%>|\"[^\"]*\"|'[^']*'|[^<>\"'])*>", re.I | re.S)
EXEMPTIONS = ".rails-flow/raw-form-exemptions.json"


class Unusable(Exception):
    pass


def blank_comments(text: str) -> str:
    """ERB and HTML comments become spaces, newlines kept, so a finding's line number is the real one."""
    keep = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    text = re.sub(r"<%#.*?%>", keep, text, flags=re.S)
    return re.sub(r"<!--.*?-->", keep, text, flags=re.S)


def scan(rel: str, text: str) -> list[tuple[str, int, str]]:
    text = blank_comments(text)
    hits: list[tuple[str, int, str]] = []
    def at(pos: int) -> int:
        return text.count("\n", 0, pos) + 1
    for rule, rx in RULES:
        for m in rx.finditer(text):
            if rule == "raw-field" and m.group(0).lower().startswith("<input"):
                # The tag ends at the first `>` that is not inside an ERB `<% … %>`, so
                # `value="<%= @url %>"` does not cut it short before `readonly`.
                end = WHOLE_TAG.match(text, m.start())
                # An `<input` with no closing `>` falls back to the rest of its LINE, never the rest
                # of the file, where an unrelated later `readonly` could excuse it (#1443).
                eol = text.find("\n", m.start())
                tag = end.group(0) if end else text[m.start(): eol if eol != -1 else len(text)]
                if DISPLAY_INPUT.search(tag) and not NAMED.search(tag):
                    continue
            hits.append((rule, at(m.start()), m.group(0).strip()))
    for var in set(BUILDER.findall(text)):
        for m in re.finditer(rf"(?<![\w.]){re.escape(var)}\.({RAW_FIELD_METHODS})\b", text):
            hits.append(("raw-builder-call", at(m.start()), m.group(0)))
    return hits


def load_exemptions(root: Path) -> list[dict]:
    path = root / EXEMPTIONS
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["exemptions"]
        if not isinstance(rows, list):
            raise TypeError(f"`exemptions` is {type(rows).__name__}, not a list")
    except (ValueError, KeyError, TypeError) as exc:
        raise Unusable(f"{EXEMPTIONS} is not {{\"exemptions\": [...]}}: {exc}") from exc
    for row in rows:
        if not (isinstance(row, dict) and row.get("file") and row.get("rule") and str(row.get("reason", "")).strip()):
            raise Unusable(f"{EXEMPTIONS}: every exemption needs a file, a rule and a reason, got {row!r}")
    return rows


def check(root: Path) -> tuple[int, list[str]]:
    lock = root / "Gemfile.lock"
    if not lock.is_file() or not re.search(r"^\s+simple_form\b", lock.read_text(encoding="utf-8"), re.M):
        return 3, ["not applicable — simple_form is not in Gemfile.lock (NOT a pass)"]
    try:
        exemptions = load_exemptions(root)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    used = [False] * len(exemptions)
    findings: list[str] = []
    files = sorted(p for d in ("app/views", "app/components") for p in (root / d).rglob("*.erb"))
    for path in files:
        rel = path.relative_to(root).as_posix()
        for rule, line, what in scan(rel, path.read_text(encoding="utf-8", errors="replace")):
            # An optional `match` narrows an exemption to hits whose text contains it, so a live
            # exemption for one control does not also exempt the next violation of that rule in the
            # same file (pre-release review).
            match = [i for i, e in enumerate(exemptions) if e["file"] == rel and e["rule"] == rule
                     and (not e.get("match") or e["match"] in what)]
            for i in match:
                used[i] = True
            if not match:
                findings.append(f"{rel}:{line} — {rule}: `{what}` where simple_form is mandated")
    for i, e in enumerate(exemptions):
        if not used[i]:
            findings.append(f"{EXEMPTIONS}: the exemption for {e['file']} ({e['rule']}) matches nothing "
                            f"any more — remove it, or it will exempt the next violation there")
    if findings:
        return 1, [f"{len(findings)} simple-form-only finding(s) across {len(files)} template(s):"] + \
                  [f"  {f}" for f in findings]
    return 0, [f"simple-form-only: {len(files)} template(s), every form and field built with simple_form"
               + (f" ({len(exemptions)} declared exemption(s))" if exemptions else "")]


# --------------------------------------------------------------------------- selftest

def selftest() -> int:
    fails: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            fails.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    def rules(src: str) -> list[str]:
        return sorted(r for r, _, _ in scan("x.html.erb", src))

    planted = {
        "form-with": '<%= form_with model: @user do |f| %><% end %>',
        "form-tag": '<%= form_tag "/search" do %><% end %>',
        "raw-form": '<form action="/x" method="post"></form>',
        "raw-field": '<input type="text" name="q">',
        "field-tag-helper": '<%= select_tag :status, options %>',
        "tag-builder-field": '<%= tag.input(type: "text", name: "code") %>',
        "raw-builder-call": '<%= simple_form_for @user do |form| %><%= form.text_field :name %><% end %>',
    }
    for rule, src in planted.items():
        check_that(f"a planted {rule} is refused", rule in rules(src), rules(src))
    check_that("a raw <select> is refused", "raw-field" in rules("<select name='a'></select>"))
    # #1443: the display exemption is judged on real attributes only.
    check_that("CONTROL: a readonly display input is still excused",
               "raw-field" not in rules('<input value="x" readonly>'))
    check_that("a name set through ERB makes a readonly input a posting field",
               "raw-field" in rules('<input <%= tag.attributes(name: "x") %> readonly>'))
    check_that("data-readonly is not readonly", "raw-field" in rules('<input data-readonly value="x">'))
    check_that("placeholder=\"readonly\" is not readonly", "raw-field" in rules('<input placeholder="readonly" value="x">'))
    check_that("data-name is not a name, so a readonly display with it is still excused",
               "raw-field" not in rules('<input data-name="x" readonly>'))
    check_that("an <input> is not closed by the NEXT tag's `>`, so that tag's readonly cannot excuse it",
               "raw-field" in rules('<input value="a"\n<p readonly>later</p>'))
    check_that("an <input> with no `>` anywhere is judged on its own line only",
               "raw-field" in rules('<input value="a"\nreadonly'))
    check_that("a `<` inside a quoted value does not end the tag before a later name=",
               "raw-field" in rules('<input value="a<b" readonly\n       name="q">'))
    check_that("CONTROL: a quoted `<` in a readonly display input is still excused",
               "raw-field" not in rules('<input value="a<b" readonly>'))
    check_that('a "name" => hash rocket makes a readonly input a posting field',
               "raw-field" in rules('<input readonly <%= tag.attributes("name" => "q") %>>'))
    check_that("a :name => hash rocket makes a readonly input a posting field",
               "raw-field" in rules('<input readonly <%= tag.attributes(:name => "q") %>>'))
    # LINEAR TIME. Run in a SUBPROCESS with a timeout: CPython's regex engine cannot be interrupted from
    # inside the process, so a backtracking pattern would hang the selftest instead of failing it.
    import subprocess, sys as _sys
    probe = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('m', sys.argv[1]); "
             "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
             "m.WHOLE_TAG.match('<input <%' + '%><%' * 50000); m.WHOLE_TAG.match('<input ' + '%><%' * 50000)")
    try:
        subprocess.run([_sys.executable, "-c", probe, str(Path(__file__).resolve())], timeout=2, check=True,
                       capture_output=True)
        linear = True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        linear = False
    check_that("WHOLE_TAG matches a pathological run of `%><%` in linear time (no ReDoS)", linear)
    check_that("CONTROL: ERB inside the tag still does not end it early",
               "raw-field" not in rules('<input value="<%= @url %>" readonly>'))
    check_that("a raw <textarea> is refused", "raw-field" in rules("<textarea></textarea>"))
    # #1439: Rails 8's name is rich_textarea (8.0+); rich_text_area is its kept alias. Both are raw.
    check_that("f.rich_textarea on a simple_form builder is refused",
               "raw-builder-call" in rules("<%= simple_form_for @a do |f| %><%= f.rich_textarea :content %><% end %>"))
    check_that("f.rich_text_area (the alias) on a simple_form builder is refused",
               "raw-builder-call" in rules("<%= simple_form_for @a do |f| %><%= f.rich_text_area :content %><% end %>"))
    check_that("CONTROL: simple_form's own rich-text input is not a raw call",
               rules("<%= simple_form_for @a do |f| %><%= f.input :content, as: :rich_text_area %><% end %>") == [])
    check_that("f.label on a simple_form builder is refused",
               "raw-builder-call" in rules("<%= simple_form_for @u do |f| %><%= f.label :name %><% end %>"))

    # CONTROLS: the idioms that must stay silent, each next to the rule it would trip.
    check_that("CONTROL: simple_form_for is not form_for (word boundary)",
               rules("<%= simple_form_for @user do |f| %><%= f.input :name %><%= f.button :submit %><% end %>") == [])
    check_that("CONTROL: simple_form's own builder methods are not raw calls",
               rules("<%= simple_form_for @u do |f| %><%= f.input_field :q %><%= f.association :team %>"
                     "<%= f.hidden_field :id %><%= f.error :name %><%= f.simple_fields_for :x do |g| %><% end %><% end %>") == [])
    check_that("CONTROL: a readonly, unnamed input is a display, not a field",
               rules('<input type="text" readonly value="<%= @key %>"\n  data-clipboard-target="source">') == [])
    check_that("CONTROL: an ERB value inside the tag does not hide its readonly",
               rules('<input data-clipboard-target="source" value="<%= @invite_url %>" readonly>') == [])
    check_that("...but a readonly input that posts (named) is still a raw field",
               "raw-field" in rules('<input type="text" readonly name="token" value="x">'))
    check_that("a raw call on a builder opened by a MULTI-LINE simple_form_for is refused",
               "raw-builder-call" in rules("<%= simple_form_for @u,\n      url: users_path do |f| %><%= f.text_field :a %><% end %>"))
    check_that("CONTROL: a hidden input is not a raw field",
               rules('<input type="hidden" name="t" value="1">') == [])
    # Rails 8's Action Text tag helper and its kept alias (#1456 review): both render a raw editor field.
    check_that("rich_textarea_tag is a raw field helper", "field-tag-helper" in rules('<%= rich_textarea_tag :body %>'))
    check_that("rich_text_area_tag (the alias) is a raw field helper",
               "field-tag-helper" in rules('<%= rich_text_area_tag :body %>'))
    check_that("CONTROL: hidden_field_tag carries state and is allowed",
               rules('<%= hidden_field_tag :sort, @sort %>') == [])
    check_that("CONTROL: button_to is a single-action button, not a form in markup",
               rules('<%= button_to "Delete", item_path(item), method: :delete %>') == [])
    check_that("CONTROL: an ERB comment naming a raw helper is not a finding",
               rules("<%# this used radio_button_tag and <form> once (#61) %>") == [])
    check_that("CONTROL: an HTML comment naming <input> is not a finding",
               rules("<!-- a bare <input> here broke the wrapper -->") == [])
    check_that("CONTROL: `.select` on an array is not a builder call",
               rules("<%= simple_form_for @u do |f| %><% items.select(&:ok) %><%= f.input :a %><% end %>") == [])
    check_that("CONTROL: a variable that is not the builder is not a builder call",
               rules("<% nav.label %>") == [])
    # Indexed defensively: a crash here would hide every fixture below it from the mutation harness.
    lines = [ln for _, ln, _ in scan("x.html.erb", "<%# one\ntwo %>\n\n<%= form_tag '/s' do %><% end %>")]
    check_that("a finding's line survives a blanked multi-line comment", lines == [4], lines)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, msg = check(root)
        check_that("no Gemfile.lock is not applicable (exit 3), never a pass", code == 3, msg)
        (root / "Gemfile.lock").write_text("GEM\n  specs:\n    rails (8.1.0)\n")
        code, msg = check(root)
        check_that("a project without simple_form is not applicable", code == 3, msg)
        (root / "Gemfile.lock").write_text("GEM\n  specs:\n    simple_form (5.3.1)\n")
        (root / "app/components/ui").mkdir(parents=True)
        (root / "app/views/users").mkdir(parents=True)
        (root / "app/views/users/edit.html.erb").write_text("<%= simple_form_for @u do |f| %><%= f.input :a %><% end %>\n")
        code, msg = check(root)
        check_that("CONTROL: a clean project passes", code == 0, msg)
        (root / "app/components/ui/search_component.html.erb").write_text("<div>\n<%= search_field_tag :q %>\n</div>\n")
        code, msg = check(root)
        check_that("a component template is scanned (the old grep read app/views only)",
                   code == 1 and any("search_component.html.erb:2" in m for m in msg), msg)
        (root / ".rails-flow").mkdir()
        (root / EXEMPTIONS).write_text(json.dumps({"exemptions": [
            {"file": "app/components/ui/search_component.html.erb", "rule": "field-tag-helper",
             "reason": "combobox query box; no model attribute"}]}))
        code, msg = check(root)
        check_that("a declared exemption with a reason is honoured", code == 0, msg)
        (root / EXEMPTIONS).write_text(json.dumps({"exemptions": [
            {"file": "app/components/ui/search_component.html.erb", "rule": "field-tag-helper",
             "reason": "combobox query box", "match": "search_field_tag"}]}))
        code, msg = check(root)
        check_that("CONTROL: an exemption narrowed by `match` covers its own control", code == 0, msg)
        (root / "app/components/ui/search_component.html.erb").write_text(
            "<div>\n<%= search_field_tag :q %>\n<%= text_field_tag :sneaky %>\n</div>\n")
        code, msg = check(root)
        check_that("...and does not exempt a different violation of the same rule in the same file",
                   code == 1 and any("text_field_tag" in m for m in msg), msg)
        (root / "app/components/ui/search_component.html.erb").write_text("<div>\n<%= search_field_tag :q %>\n</div>\n")
        (root / EXEMPTIONS).write_text(json.dumps({"exemptions": None}))
        try:  # a crash here must report as THIS fixture, not take every later fixture down with it
            code, msg = check(root)
        except Exception as exc:  # noqa: BLE001
            code, msg = -1, [repr(exc)]
        check_that("`\"exemptions\": null` is unusable, not a crash", code == 2, msg)
        (root / EXEMPTIONS).write_text(json.dumps({"exemptions": [
            {"file": "app/components/ui/search_component.html.erb", "rule": "field-tag-helper", "reason": " "}]}))
        code, msg = check(root)
        check_that("an exemption with no reason is unusable", code == 2, msg)
        (root / EXEMPTIONS).write_text(json.dumps({"exemptions": [
            {"file": "app/components/ui/search_component.html.erb", "rule": "field-tag-helper", "reason": "r"},
            {"file": "app/views/gone.html.erb", "rule": "raw-field", "reason": "r"}]}))
        code, msg = check(root)
        check_that("a stale exemption is a finding", code == 1 and any("matches nothing" in m for m in msg), msg)

    for f in fails:
        print(f"selftest FAIL: {f}")
    print(f"check_simple_form_only selftest: {'FAILED' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_simple_form_only.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = check(a.root.resolve())
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
