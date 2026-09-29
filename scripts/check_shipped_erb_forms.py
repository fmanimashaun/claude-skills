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

THE ONE EXCEPTION IS DECLARED IN THE BLOCK. A design-system primitive that implements a control (the
Checkbox, the Combobox) is the one place a raw element is built; its block carries the ERB comment
`<%# simple-form-only: primitive %>`, and its prose tells the project to declare the matching row in
`.rails-flow/raw-form-exemptions.json`. Every other hit is a finding: fix the doctrine, not the gate.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/rails-flow/scripts"))
from check_simple_form_only import scan  # noqa: E402 -- the project gate's own scanner

BLOCK = re.compile(r"^```erb[^\n]*\n(.*?)^```", re.S | re.M)
PRIMITIVE = "simple-form-only: primitive"


def findings(files: list[Path], root: Path) -> list[str]:
    out = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in BLOCK.finditer(text):
            if PRIMITIVE in m.group(1):
                continue
            start = text.count("\n", 0, m.start()) + 1
            for rule, line, what in scan(str(f), m.group(1)):
                out.append(f"{f.relative_to(root)}:{start + line} — {rule}: `{what[:50]}` in a shipped ERB block")
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
        f = run("```erb\n<%# simple-form-only: primitive %>\n<%= check_box_tag :a %>\n```\n")
        check_that("CONTROL: a block declared a primitive is excused", f == [], f)
        f = run("```erb\n<%= simple_form_for @u do |f| %><%= f.input :a %><% end %>\n```\n")
        check_that("CONTROL: a simple_form block is clean", f == [], f)
        f = run("```ruby\ncheck_box_tag :a\n```\n")
        check_that("CONTROL: a non-ERB fence is not read", f == [], f)
        f = run("```erb\n<%# simple-form-only: primitive %>\n```\n\n```erb\n<%= check_box_tag :b %>\n```\n")
        check_that("the marker excuses its own block only", len(f) == 1, f)

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
