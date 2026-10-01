#!/usr/bin/env python3
"""Our own shipped ERB must pass the simple-form-only gate we ship (#1383, pre-release review).

Run:  python3 scripts/check_shipped_erb_forms.py            # exit 0 clean, 1 findings
      python3 scripts/check_shipped_erb_forms.py --selftest

WHY. `plugins/rails-flow/scripts/check_simple_form_only.py` refuses a hand-built form or field in a
project. The independent pre-release review ran its scanner over our own doctrine and found nine
```erb blocks that fail it: a downstream app that copies our filter panel, billing radio group or
checkbox exactly as the design-system shows would go red with no exemption on file. The gate had been
measured against one downstream app and never against the text agents copy from us. This check runs
the SAME `scan()` (imported, never a second copy) over every ```erb block under skills/ and plugins/.

THE ONE EXCEPTION IS DECLARED IN THE BLOCK, AND NAMES WHAT IT EXCUSES (#1443). A design-system
primitive that implements a control (the Checkbox, the Combobox, the Tabs picker) is the one place a raw
element is built; its block carries `<%# simple-form-only: primitive <construct> -- why %>`, where
`<construct>` is the raw construct the scanner reports (`check_box_tag`, `tag.input`, `<select`), and its
prose tells the project to declare the matching row in `.rails-flow/raw-form-exemptions.json`. The
marker excuses ONLY that construct: any other raw construct in the same block is still a finding, and
a marker that names nothing excuses nothing. It used to excuse the whole block, so a later, unrelated
raw field in the Checkbox block would have passed unseen. Every other hit is a finding: fix the
doctrine, not the gate.

EVERY FENCE, INDENTED OR NOT. A fence may be indented (inside a list item); its closing fence carries
the same indent. Only column-0 fences were read before #1443, which skipped five blocks.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/rails-flow/scripts"))
from check_simple_form_only import scan  # noqa: E402 -- the project gate's own scanner

# A ```erb block, or ~~~erb, or a longer fence, closed by a run of the SAME character at least as long
# (#1460; a mixed run like ```~~~ closes nothing, #1521 review R2). The info string may be `erb`, `ERB`
# or `html+erb` (R6). The body is group 3 for a backtick fence and group 5 for a tilde fence.
BLOCK = re.compile(r"^([ \t]*)(?:(`{3,})(?:html\+)?erb\b[^\n]*\n(.*?)^\1\2`*"
                   r"|(~{3,})(?:html\+)?erb\b[^\n]*\n(.*?)^\1\4~*)[ \t]*$", re.S | re.M | re.I)
# A primitive builds ONE raw control. It must never excuse a FORM: that is what the mandate refuses.
# Every construct a form rule reports -- form-with, form-tag, raw-form (`<form`), and tag-builder-field's
# `tag.form` (#1460; the last two were missed, #1521 review R1).
FORM_BUILDERS = {"form_with", "form_for", "form_tag", "<form", "tag.form"}
# EVERY marker in a block counts, and each must name a construct AND give a reason (#1455 review).
PRIMITIVE = re.compile(r"<%#\s*simple-form-only:\s*primitive\b(.*?)%>", re.S)
VALID_MARKER = re.compile(r"^[ \t]*(\S+)[ \t]+--[ \t]*\w")


def findings(files: list[Path], root: Path) -> list[str]:
    out = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in BLOCK.finditer(text):
            body = m.group(3) if m.group(3) is not None else m.group(5)
            start = text.count("\n", 0, m.start()) + 1
            # ONE excused instance per marker (#1460): a second `check_box_tag` added to the Checkbox
            # block later needs its own marker, and its reason, or it is reported.
            named: dict[str, int] = {}
            for marker in PRIMITIVE.finditer(body):
                valid = VALID_MARKER.match(marker.group(1))
                where = f"{f.relative_to(root)}:{start + body.count(chr(10), 0, marker.start()) + 1}"
                if not valid or valid.group(1).startswith("--"):
                    out.append(f"{where} — primitive-marker-invalid: a marker must name one construct and give a "
                               f"reason (`primitive <construct> -- why`), so this one excuses nothing")
                elif valid.group(1).lower() in FORM_BUILDERS:
                    out.append(f"{where} — primitive-marker-invalid: `{valid.group(1)}` is a form builder, the thing "
                               f"simple-form-only refuses; a primitive builds one control, never a form")
                else:
                    named[valid.group(1).lower()] = named.get(valid.group(1).lower(), 0) + 1
            for rule, line, what in scan(str(f), body):
                # EQUALITY, never a prefix (#1455 review): `primitive <` would excuse every `<select`,
                # `<textarea`, `<input` and `<form`, and `primitive t` both tag.input and text_field_tag.
                key = what.strip().lower()
                if named.get(key, 0) > 0:
                    named[key] -= 1
                    continue
                out.append(f"{f.relative_to(root)}:{start + line} — {rule}: `{what[:50]}` in a shipped ERB block")
            # A marker that excuses nothing is a spare excuse for the next raw construct added to the
            # block -- the case #1460 exists to stop -- so it is reported, like an unused exemption (R3).
            for construct, spare in sorted(named.items()):
                if spare > 0:
                    out.append(f"{f.relative_to(root)}:{start} — primitive-marker-unused: {spare} `{construct}` "
                               f"marker(s) excuse nothing in this block; remove them")
    return out


def shipped(root: Path) -> list[Path]:
    return sorted(p for d in ("skills", "plugins") for p in (root / d).rglob("*.md") if p.is_file())


def selftest() -> int:
    fails: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            fails.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills/x").mkdir(parents=True)
        doc = root / "skills/x/SKILL.md"
        def run(body: str) -> list[str]:
            doc.write_text(body)
            return findings(shipped(root), root)
        f = run("Filter:\n\n```erb\n<form method=\"get\">\n</form>\n```\n")
        check_that("a raw <form> in a shipped ERB block is a finding", any("raw-form" in x for x in f), f)
        check_that("...with the doc's own line number", any("SKILL.md:4" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<%= check_box_tag :a %>\n```\n")
        check_that("CONTROL: the construct a primitive marker names is excused", f == [], f)
        # #1460: a marker never excuses a form builder, and each marker excuses ONE instance.
        for builder in ("form_with", "form_for", "form_tag"):
            src = {"form_with": "<%= form_with model: @u do |f| %><% end %>", "form_for": "<%= form_for @u do |f| %><% end %>",
                   "form_tag": "<%= form_tag \"/x\" do %><% end %>"}[builder]
            f = run(f"```erb\n<%# simple-form-only: primitive {builder} -- a primitive form %>\n{src}\n```\n")
            check_that(f"#1460: a marker naming {builder} is invalid and excuses nothing",
                       any("primitive-marker-invalid" in x and builder in x for x in f)
                       and any(x.split(" — ")[1].startswith("form-") for x in f if " — " in x and "primitive-marker" not in x), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<%= check_box_tag :a %>\n<%= check_box_tag :b %>\n```\n")
        check_that("#1460: one marker excuses ONE instance, so a second check_box_tag is reported",
                   len(f) == 1 and "field-tag-helper" in f[0] and "check_box_tag" in f[0], f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<%# simple-form-only: primitive check_box_tag -- the second one %>\n<%= check_box_tag :a %>\n<%= check_box_tag :b %>\n```\n")
        check_that("#1460 CONTROL: two markers excuse two instances", f == [], f)
        # #1521 review: every FORM construct is refused as a marker (R1), and a spare marker is reported (R3).
        for construct, src in (("<form", "<form action=\"/x\"></form>"), ("tag.form", "<%= tag.form(action: \"/x\") %>")):
            f = run(f"```erb\n<%# simple-form-only: primitive {construct} -- x %>\n{src}\n```\n")
            check_that(f"#1521 R1: a marker naming {construct} is invalid and the form is still reported",
                       any("primitive-marker-invalid" in x for x in f) and any("primitive-marker" not in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<p>nothing raw here</p>\n```\n")
        check_that("#1521 R3: a marker that excuses nothing is reported", any("primitive-marker-unused" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<%= check_box_tag :a %>\n```\n")
        check_that("#1521 R3 CONTROL: a used marker is not reported", f == [], f)
        f = run("```erb\n<%= check_box_tag :a %>\n```~~~\n<form method=\"get\"></form>\n```\n")
        check_that("#1521 R2: a mixed ```~~~ line does not close a backtick block", any("raw-form" in x for x in f), f)
        for label in ("ERB", "html+erb"):
            f = run(f"```{label}\n<form method=\"get\"></form>\n```\n")
            check_that(f"#1521 R6: a ```{label} block is read", any("raw-form" in x for x in f), f)
        # #1460 (latent): ~~~erb and longer fences are read too, and only the same fence closes one.
        f = run("~~~erb\n<form method=\"get\"></form>\n~~~\n")
        check_that("#1460: a ~~~erb block is read", any("raw-form" in x for x in f), f)
        f = run("````erb\n<form method=\"get\"></form>\n````\n")
        check_that("#1460: a four-backtick erb block is read", any("raw-form" in x for x in f), f)
        f = run("```erb\n<%= check_box_tag :a %>\n~~~\n<form method=\"get\"></form>\n```\n")
        check_that("#1460: a ~~~ line does not close a backtick block, so the form after it is read",
                   any("raw-form" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n<%= check_box_tag :a %>\n<select name=\"x\"></select>\n```\n")
        check_that("the marker excuses only what it names: a later raw <select> is a finding",
                   len(f) == 1 and "<select" in f[0], f)
        f = run("```erb\n<%# simple-form-only: primitive -- why %>\n<%= check_box_tag :a %>\n```\n")
        check_that("a marker that names nothing excuses nothing",
                   any("primitive-marker-invalid" in x for x in f) and any("check_box_tag" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive < -- why %>\n<select name=\"a\"></select>\n<textarea></textarea>\n```\n")
        check_that("`primitive <` is not a prefix that excuses every raw tag",
                   sum("raw-field" in x for x in f) == 2, f)
        f = run("```erb\n<%# simple-form-only: primitive t -- why %>\n<%= tag.input :a %>\n<%= text_field_tag :b %>\n```\n")
        check_that("`primitive t` excuses neither tag.input nor text_field_tag (and is itself unused)",
                   sum("primitive-marker-unused" not in x for x in f) == 2
                   and any("primitive-marker-unused" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag %>\n<%= check_box_tag :a %>\n```\n")
        check_that("a marker with no reason excuses nothing",
                   any("primitive-marker-invalid" in x for x in f) and any("check_box_tag" in x for x in f), f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- one %>\n<%= check_box_tag :a %>\n"
                "<%# simple-form-only: primitive tag.input -- two %>\n<%= tag.input :b %>\n```\n")
        check_that("every marker in a block counts, not only the first", f == [], f)
        f = run("- item:\n\n  ```erb\n  <form method=\"get\">\n  </form>\n  ```\n")
        check_that("an INDENTED fence is read", any("raw-form" in x for x in f), f)
        check_that("...with the doc's own line number", any("SKILL.md:4" in x for x in f), f)
        f = run("  ```erb\n  <%= simple_form_for @u do |f| %><%= f.input :a %><% end %>\n  ```\n\n```erb\n<form></form>\n```\n")
        check_that("an indented fence closes at its own indent, not a later column-0 fence",
                   len(f) == 1 and "SKILL.md:6" in f[0], f)
        f = run("  ```erb\n  <%= simple_form_for @u do |f| %><% end %>\n```\n  <form></form>\n  ```\n")
        check_that("a fence line at ANOTHER indent does not close an indented block",
                   any("raw-form" in x for x in f), f)
        f = run("```erb\n<%= simple_form_for @u do |f| %><%= f.input :a %><% end %>\n```\n")
        check_that("CONTROL: a simple_form block is clean", f == [], f)
        f = run("```ruby\ncheck_box_tag :a\n```\n")
        check_that("CONTROL: a non-ERB fence is not read", f == [], f)
        f = run("```erb\n<%# simple-form-only: primitive check_box_tag -- why %>\n```\n\n```erb\n<%= check_box_tag :b %>\n```\n")
        check_that("the marker excuses its own block only",
                   sum("field-tag-helper" in x for x in f) == 1 and any("primitive-marker-unused" in x for x in f), f)

    for x in fails:
        print(f"selftest FAIL: {x}")
    print(f"check_shipped_erb_forms selftest: {'FAILED' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    files = shipped(ROOT)
    found = findings(files, ROOT)
    if found:
        print(f"{len(found)} shipped ERB block finding(s) against simple-form-only:")
        print("\n".join(f"  {x}" for x in found))
        return 1
    print(f"shipped ERB: every block in {len(files)} doc(s) passes simple-form-only")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
