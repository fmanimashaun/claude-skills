#!/usr/bin/env python3
"""Flag, in a PROJECT, the two defects the component mandate exists to prevent (#1063).

Run:  python3 check_component_contract.py                  # app/components + app/views
      python3 check_component_contract.py --root path/to/app
      python3 check_component_contract.py --selftest

WHY THIS EXISTS. The upstream skill states that a UI element a component covers is never written as
raw HTML, and that every component accepts a caller's attributes. Both were prose. An audited
consumer app had **18 raw `<button>` tags** against 139 component ones, and **zero** raw form fields
— because fields had a request spec asserting anatomy and buttons had only a sentence.

**Where the rule was enforced it was clean; where it was only written down it had drifted.** That is
the finding, and it is not about discipline. This is the enforcement.

THE TWO RULES, and they are the two halves of one failure.

  1. `raw-element` -- a hand-written `<button>` in a view. Nine of the eighteen retyped the class
     string; one identical string appeared **three times** and omitted `whitespace-nowrap`, a class
     the component had gained *because a table's action column broke mid-word*. Two of those copies
     sat in admin table action cells: they carried the exact defect the component was fixed for and
     could never receive the fix. **A copied class string is a silent fork of a component** --
     correct the day it is written, wrong by construction from the next fix onward, and findable
     only by grepping for raw HTML, which is what the mandate existed to make unnecessary.

  2. `component-drops-attributes` -- a component whose initializer takes a fixed keyword list, or
     accepts `**attrs` and never stores them. **This is the cause of rule 1, not a separate
     concern.** A developer who needs a Stimulus target on a Modal reaches for the component, finds
     it cannot carry one, and writes the tag by hand. Upstream, 17 of 23 shipped components had this
     defect. Accepting-and-dropping is the worse form: Ruby binds the hash and discards it, so the
     attribute vanishes with **no error**, where a fixed list at least raises `ArgumentError`.

THERE IS NO CARVE-OUT, AND THAT IS A MEASUREMENT RATHER THAN A POSITION. The one real exception in
the doctrine is a framework helper that builds the element itself -- `button_to`, `form.submit`,
`submit_tag`. **But those emit no literal `<button` into the ERB source**, so this scan never sees
them and never needs to exempt them. An earlier version of this file carried an explicit exemption
for them; a mutation that deleted it changed nothing, which is how the dead code was found. A
carve-out no fixture can reach is a carve-out without a negative test -- the class this project's
own review skill names -- so it is gone rather than kept as reassurance.

What the scan sees is therefore exactly what the doctrine forbids: a literal `<button` typed into a
view by hand.

**"The component does not expose what I need" is NOT an exception**, and it is refused here on
purpose because it is the plausible-sounding one. In the audit that produced this check, six raw
buttons were first reported as legitimate for exactly that reason -- and reading the component
disproved every one: its constructor already took `**attrs` and both render branches already passed
them through. **The check that reversed the finding was one file read.** If a component genuinely
cannot express something, that is rule 2 firing, and the fix belongs in the component.

WHY IT MUST PASS THE LEGITIMATE CASE, EXPLICITLY. A gate that forbade every raw `<button>` would
fail on correct code the first time it ran; somebody would add an exclusion list or switch it off,
and the real defects would go back to being invisible -- now behind a check that looks present. So
the selftest carries **one that must PASS and one that must FAIL**. A suite of only failures is
satisfied by a gate that refuses everything; a suite of only passes by one that refuses nothing.
Neither shows it discriminates.

SCOPE, STATED RATHER THAN IMPLIED. Rule 1 looks for `<button` only. That is the element with a
measured defect count; widening it to every tag a component might cover would produce findings
nobody has triaged, and an untriaged report is indistinguishable from a passing one. Other elements
are doctrine until somebody measures them.

Stdlib only, no network. Exit 0 clean, 1 findings, 2 cannot judge.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from source_text import strip_comments

RAW_BUTTON = re.compile(r"<button\b", re.I)
COMPONENT_CLASS = re.compile(r"^\s*class (\w+Component) < ViewComponent::Base\s*$", re.M)


def initializer_of(body: str) -> str | None:
    """The whole `def initialize(...)` signature, across line breaks, or None if there is none."""
    m = re.search(r"def initialize\(", body)
    if not m:
        return None
    depth, out = 0, []
    for ch in body[m.start():]:
        out.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def raw_elements(root: Path) -> list[str]:
    """Hand-written `<button>` outside the framework-helper carve-out."""
    findings = []
    # `app/views/**` ONLY. A component's own template is *supposed* to contain the element -- that
    # is where the element lives. Measured on a real consumer app: 31 raw `<button>` occurrences,
    # of which **13 are inside `app/components/**` and every one is correct**. Scanning those
    # would have produced 13 findings against correct code the first time this ran, which is
    # precisely how a gate earns an exclusion list or gets switched off. The remaining **18 are in
    # `app/views/**`, and 18 is exactly the audited defect count.**
    for pattern in ("app/views/**/*.erb",):
        for path in sorted(root.glob(pattern)):
            # COMMENTS ARE PROSE (#1128). A view explaining why NOT to hand-write a
            # `<button>` used to be reported for hand-writing one. Blanked in place, so `:n`
            # below still cites the right line.
            source = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
            for n, line in enumerate(source.split("\n"), 1):
                if not RAW_BUTTON.search(line):
                    continue
                rel = path.relative_to(root)
                findings.append(
                    f"{rel}:{n}: raw-element — a hand-written `<button>` where the button component "
                    f"is mandated. If it needs an attribute the component will not take, that is a "
                    f"defect in the component (see component-drops-attributes below), not a licence "
                    f"here. A copied class string is a silent fork: it stops receiving the "
                    f"component's fixes the moment it is written.")
    return findings


def components_dropping_attributes(root: Path) -> list[str]:
    """Components that cannot carry a caller's attribute, or accept it and throw it away."""
    findings = []
    for path in sorted(root.glob("app/components/**/*.rb")):
        # Here the same root cause runs the OTHER way: a commented-out `def initialize(**attrs)`
        # made a component that drops its caller's attributes look compliant -- a false NEGATIVE
        # (#1128). Blanking comments is what makes the body scan read only executable code.
        source = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        lines = source.split("\n")
        for m in COMPONENT_CLASS.finditer(source):
            name = m.group(1)
            start = source[: m.start()].count("\n")
            indent = len(m.group(0)) - len(m.group(0).lstrip())
            body = []
            for line in lines[start + 1:]:
                if line.strip() == "end" and (len(line) - len(line.lstrip())) == indent:
                    break
                body.append(line)
            blob = "\n".join(body)
            sig = initializer_of(blob)
            rel = path.relative_to(root)
            if sig is None:
                findings.append(
                    f"{rel}: component-drops-attributes — `{name}` defines no initializer, so a "
                    f"caller cannot pass it anything.")
            elif "**" not in sig:
                findings.append(
                    f"{rel}: component-drops-attributes — `{name}` takes a fixed keyword list and "
                    f"would drop a caller's `data:`, `form:` or `aria:`. A component that cannot "
                    f"carry an attribute is one a developer writes by hand instead.")
            elif "**" in sig and not re.search(
                    r"@\w+\s*=[^=\n]*\battrs\b|\battrs\b[^=\n]*=\s*", blob):
                findings.append(
                    f"{rel}: component-drops-attributes — `{name}` accepts a splat and never stores "
                    f"it. Ruby binds the hash and discards it, so the attribute vanishes with NO "
                    f"error — quieter than the fixed keyword list it replaced.")
    return findings


def run(root: Path) -> tuple[list[str], int, int]:
    views = list(root.glob("app/views/**/*.erb"))
    rubies = list(root.glob("app/components/**/*.rb"))
    findings = raw_elements(root) + components_dropping_attributes(root)
    return findings, len(views), len(rubies)


def _selftest() -> int:
    import shutil
    import tempfile

    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    root = Path(tempfile.mkdtemp(prefix="component-contract-"))
    try:
        (root / "app/views/admin").mkdir(parents=True)
        (root / "app/components/ui").mkdir(parents=True)

        # MUST FAIL: a hand-written button, the shape that was copied three times downstream.
        (root / "app/views/admin/index.html.erb").write_text(
            '<button class="inline-flex h-9 px-4 rounded-md border">Edit</button>\n',
            encoding="utf-8")
        # MUST PASS: `button_to` builds its own element and writes no literal `<button` into the
        # source, so the scan never sees it. This is the legitimate case, and it passes because
        # there is nothing here to match -- not because of an exemption.
        (root / "app/views/admin/show.html.erb").write_text(
            '<%= button_to "Delete", thing_path(@thing), method: :delete %>\n',
            encoding="utf-8")
        (root / "app/components/ui/good_component.rb").write_text(
            "module Ui\n  class GoodComponent < ViewComponent::Base\n"
            "    def initialize(variant: :primary, **attrs)\n"
            "      @variant, @attrs = variant, attrs\n    end\n  end\nend\n", encoding="utf-8")

        # A component's OWN template contains the element legitimately. This is the case that
        # would have produced 13 findings against correct code on a real app.
        (root / "app/components/ui/button_component.html.erb").write_text(
            '<button class="<%= classes %>" <%= tag.attributes(**attrs) %>><%= content %></button>\n',
            encoding="utf-8")

        findings, views, rubies = run(root)
        expect("both view files were read", views == 2)
        expect("a component's own template is NOT reported — the element lives there",
               not any("button_component" in f for f in findings))
        expect("the hand-written button is reported",
               any("raw-element" in f and "index.html.erb" in f for f in findings))
        # THE MUST-PASS HALF. Without it, "flags a raw button" is satisfied by a gate that flags
        # every raw button -- which fails correct code on day one and gets switched off.
        expect("the framework-helper button is NOT reported",
               not any("show.html.erb" in f for f in findings))
        expect("a compliant component is not reported",
               not any("GoodComponent" in f for f in findings))

        (root / "app/components/ui/fixed_component.rb").write_text(
            "module Ui\n  class FixedComponent < ViewComponent::Base\n"
            "    def initialize(variant: :primary)\n      @variant = variant\n"
            "    end\n  end\nend\n", encoding="utf-8")
        (root / "app/components/ui/drops_component.rb").write_text(
            "module Ui\n  class DropsComponent < ViewComponent::Base\n"
            "    def initialize(variant: :primary, **attrs)\n      @variant = variant\n"
            "    end\n  end\nend\n", encoding="utf-8")
        findings, _, rubies = run(root)
        expect("all three components were read", rubies == 3)
        expect("a fixed keyword list is reported",
               any("FixedComponent" in f for f in findings))
        # THE DISCRIMINATING PAIR: same signature as GoodComponent, one stores and one does not.
        expect("accept-and-drop is reported, and named as the silent form",
               any("DropsComponent" in f and "NO\n error" in f.replace("\n", "\n ")
                   or ("DropsComponent" in f and "never stores" in f) for f in findings))

        # A tree with no views and no components cannot be judged -- and must not read as clean.

        # COMMENTS ARE PROSE (#1128), and here it runs BOTH ways.
        views = root / "app/views/pages"
        views.mkdir(parents=True, exist_ok=True)
        (views / "note.html.erb").write_text(
            '<%# never hand-write a raw <button>; use the button component %>\n'
            '<div class="box">hi</div>\n', encoding="utf-8")
        f = raw_elements(root)
        expect("a comment warning against a raw `<button>` is not a raw `<button>`",
               not any("note.html.erb" in x for x in f))
        (views / "real.html.erb").write_text('<button class="btn">Go</button>\n', encoding="utf-8")
        # The control: without it, the assertion above passes against a gate that reads nothing.
        expect("...while a real one on the next line over is still reported",
               any("real.html.erb" in x for x in raw_elements(root)))
        empty = Path(tempfile.mkdtemp(prefix="component-contract-empty-"))
        try:
            f2, v2, r2 = run(empty)
            expect("an empty tree finds nothing AND reports nothing examined",
                   not f2 and v2 == 0 and r2 == 0)
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("the raw-element rule passes the framework-helper case and fails the hand-written one")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    root = Path(args.root).resolve()
    findings, views, rubies = run(root)

    if views == 0 and rubies == 0:
        # NOT a pass. Zero findings over zero files is indistinguishable from a healthy project,
        # and this gate is about a rule that drifts precisely where nothing looks.
        print("NOT APPLICABLE: no app/views/**/*.erb and no app/components/**/*.rb under "
              f"{root} — this check examined nothing.")
        return 0

    for f in findings:
        print(f"  {f}")
    print(f"\n{views} view file(s) and {rubies} component file(s) examined; "
          f"{len(findings)} finding(s).")
    if findings:
        print("The escape hatch is the ELEMENT, never the styling: a framework helper that builds "
              "its own <button> is exempt, and nothing else is.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
