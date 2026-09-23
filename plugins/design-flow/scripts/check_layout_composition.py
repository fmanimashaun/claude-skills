#!/usr/bin/env python3
"""Flag hand-rolled layout in a project's views where a declared primitive expresses it.

Run:  python3 check_layout_composition.py                 # app/views
      python3 check_layout_composition.py --root path/to/app
      python3 check_layout_composition.py --selftest

WHY THIS EXISTS. The design system's whole premise is that layout is COMPOSED from a small set of
primitives -- `cluster`, `grid-auto`, `switcher`, `band`, `center` -- rather than written per
surface with `flex`/`grid` utilities. That premise lives in prose: the audit checklist says to
prefer *"an intrinsic primitive (`grid-auto`, `Sidebar`/`Switcher`, `cluster`)"*, and **no script
has ever checked it.**

Measured on a consumer app that ships 20-odd primitives of its own: `grid-auto` is used **21
times**, so the idea took. And **34 elements across 22 view files** are `flex` + `items-*` + `gap-*`
written by hand -- which is precisely what `cluster` is. The primitive was available, declared, and
used elsewhere in the same app.

**That is the pattern this repository keeps finding: where a rule is gated it stays clean; where it
is prose it drifts.** Tokens are gated and clean. Component usage was prose until it was gated this
week, and had drifted to 18 raw buttons. Layout is still prose.

THE DOCTRINE IS A PRIORITY ORDER, not a preference: fluid, then intrinsic, then breakpoints as an
exception that must justify itself (`responsive.md` SS1-3). *"If you're writing breakpoint classes
to change layout, first check whether a primitive expresses it intrinsically."* So there are two
rules, and they are the same rule seen from two sides.

  `hand-rolled-cluster`      `flex` + an `items-*` + a `gap-*` on one element. That triple **is**
                             the definition of `cluster` -- a row of things, aligned, evenly
                             spaced. Measured: **34 across 22 view files** in one consumer app.

  `breakpoint-driven-layout` a breakpoint variant that changes the layout AXIS or TRACK COUNT --
                             `md:flex-row`, `sm:flex-col`, `lg:grid-cols-2`. Those are exactly
                             what `switcher`, `Layout::Sidebar` and `grid-auto` express with zero
                             media queries. Measured: **3** in the same app, out of 30 breakpoint
                             variants -- so intrinsic layout largely took there, and the three are
                             worth looking at rather than lost in noise.

**Sizing breakpoints are not flagged.** `md:w-auto` on a toolbar button is prescribed by the
doctrine itself (`responsive.md` SS146). Only the axis and the track count are intrinsic
mechanisms' business.

**SS3 permits a genuine structural swap** -- nav to rail to drawer is the doctrine's own example --
so that exception is DECLARED rather than assumed: put `layout-swap:` with a reason in an ERB
comment on the line or the line above, and the finding is suppressed. An exception nobody can see
is how a rule gets quietly abandoned; an exception you have to write down is one a reviewer can
argue with.

**Everything else is deliberately out of scope**, and the omissions are the design:

  * `flex` alone, or `flex-1`, or `flex min-w-0 flex-col` -- a flex CHILD, or a structural
    one-off. No primitive claims these and flagging them would be an opinion.
  * an UNPREFIXED `grid grid-cols-*` -- a deliberate fixed layout at every width. `grid-auto` is
    the intrinsic, content-sized one; they are different tools, not a right and a wrong one. It is
    the BREAKPOINT-prefixed form that reaches for a query where a primitive already adapts.
  * anything already using a primitive -- the point is composition, and an element that composes
    one is composing.

Widening past the triple is how this becomes a tool that reports things nobody triages, and an
untriaged report is indistinguishable from a passing one.

SCOPE IS `app/views/**` ONLY, for the same reason the component-contract gate is. A component's own
template is where layout is *implemented*; the primitives are built from flex and grid somewhere,
and that somewhere is a component. Scanning `app/components/**` would flag the implementation of
the very thing it is asking people to use.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import content_floors

from source_text import strip_comments

CLASS_ATTR = re.compile(r'class="([^"]*)"')

# A breakpoint variant that changes the layout AXIS or TRACK COUNT. `switcher`, `Layout::Sidebar`
# and `grid-auto` express all three with zero media queries. Sizing variants (`md:w-auto`) are
# prescribed by the doctrine and are deliberately absent.
AXIS_VARIANT = re.compile(r"^(?:sm|md|lg|xl|2xl):(?:flex-row|flex-col|grid-cols-\d+)$")

# The doctrine's own exception (responsive.md SS3): a genuine structural swap, nav -> rail ->
# drawer. DECLARED, never inferred -- an exception nobody can see is how a rule gets quietly
# abandoned, and one written down is one a reviewer can argue with.
SWAP_DECLARED = re.compile(r"layout-swap:\s*\S")

# A composed element is already doing the right thing. Read from the project when it declares them,
# so a project that names its primitives differently is not told it is wrong -- see `primitives()`.
FALLBACK_PRIMITIVES = frozenset({
    "cluster", "grid-auto", "switcher", "band", "center", "cover", "frame", "sidebar", "imposter",
    "reel", "stack", "box", "pad",
})


def primitives(root: Path) -> frozenset[str]:
    """The layout primitives this project actually declares, or a sane default.

    READ FROM THE PROJECT, not hardcoded. A project renames or extends its primitives, and a check
    that insisted on our names would report drift against a vocabulary the project never adopted --
    which is a gate wrong about correct code, and it gets switched off.
    """
    found = set()
    for css in root.glob("app/assets/**/*.css"):
        found |= set(re.findall(r"@utility\s+([a-z][a-z0-9-]*)", css.read_text(
            encoding="utf-8", errors="replace")))
    return frozenset(found) if found else FALLBACK_PRIMITIVES


def cluster_shaped(classes: list[str], declared: frozenset[str]) -> bool:
    """Is this element a hand-rolled `cluster` -- flex, aligned, with a gap?"""
    if any(c in declared for c in classes):
        return False                       # already composed
    if "flex" not in classes:
        return False
    return (any(c.startswith("items-") for c in classes)
            and any(c.startswith("gap-") for c in classes))


def run(root: Path) -> tuple[list[str], int]:
    declared = primitives(root)
    views = sorted(root.glob("app/views/**/*.erb"))
    findings = []
    for path in views:
        # COMMENTS ARE PROSE (#1128) -- but only for the MARKUP scan. A view describing the markup
        # it REPLACED used to be reported for still containing it, so classes are matched against
        # the blanked text; blanked in place, so `:n` stays true. The `layout-swap:` declaration
        # lives in a comment ON PURPOSE, so it is still read from the RAW line. Stripping both is
        # how the first attempt at this fix silently disabled the opt-out.
        raw = path.read_text(encoding="utf-8", errors="replace").split("\n")
        lines = strip_comments("\n".join(raw)).split("\n")
        for n, line in enumerate(lines, 1):
            # The swap declaration may sit on the line or the one above it, because the element
            # is often long enough that the comment goes on its own line.
            excused = bool(SWAP_DECLARED.search(raw[n - 1])
                           or (n > 1 and SWAP_DECLARED.search(raw[n - 2])))
            for m in CLASS_ATTR.finditer(line):
                classes = m.group(1).split()
                if cluster_shaped(classes, declared):
                    findings.append(
                        f"{path.relative_to(root)}:{n}: hand-rolled-cluster — `flex` with an "
                        f"alignment and a gap is what `cluster` expresses. Compose the primitive; "
                        f"a hand-written row stops receiving changes to the primitive the moment "
                        f"it is written.")
                axis = [c for c in classes if AXIS_VARIANT.match(c)]
                if axis and not excused:
                    findings.append(
                        f"{path.relative_to(root)}:{n}: breakpoint-driven-layout — {', '.join(axis)}"
                        f" changes the layout axis at a query, and `switcher`, `Layout::Sidebar` "
                        f"and `grid-auto` express that intrinsically. If this is a genuine "
                        f"structural swap (responsive.md §3), declare it: `layout-swap: <reason>` "
                        f"in an ERB comment on this line or the one above.")
    return findings, len(views)


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

    root = Path(tempfile.mkdtemp(prefix="layout-composition-"))
    try:
        (root / "app/views/admin").mkdir(parents=True)
        (root / "app/assets/tailwind").mkdir(parents=True)
        (root / "app/assets/tailwind/application.css").write_text(
            "@utility cluster { display: flex; }\n@utility grid-auto { display: grid; }\n",
            encoding="utf-8")

        expect("the project's own primitives are read from its CSS",
               {"cluster", "grid-auto"} <= primitives(root))

        # MUST FAIL: the measured shape — 34 of these in one real app.
        (root / "app/views/admin/index.html.erb").write_text(
            '<div class="flex items-center gap-2.5">\n  <span>a</span>\n</div>\n', encoding="utf-8")
        # MUST PASS: already composed. Without this the gate flags correct code on day one.
        (root / "app/views/admin/show.html.erb").write_text(
            '<div class="cluster flex items-center gap-2">\n  <span>a</span>\n</div>\n',
            encoding="utf-8")
        # MUST PASS: a flex CHILD, and a structural one-off. No primitive claims these.
        (root / "app/views/admin/edit.html.erb").write_text(
            '<div class="flex min-w-0 flex-col">\n  <p class="flex-1">x</p>\n</div>\n',
            encoding="utf-8")

        findings, views = run(root)
        expect("all three view files were read", views == 3)
        expect("the hand-rolled cluster is reported",
               any("index.html.erb" in f for f in findings))
        expect("an element already composing a primitive is NOT reported",
               not any("show.html.erb" in f for f in findings))
        expect("a flex child and a structural one-off are NOT reported",
               not any("edit.html.erb" in f for f in findings))
        expect("exactly one finding — the gate is narrow, not enthusiastic", len(findings) == 1)

        # A project whose CSS names its primitives differently must not be told it is wrong for
        # using its own vocabulary.
        (root / "app/assets/tailwind/application.css").write_text(
            "@utility row-group { display: flex; }\n", encoding="utf-8")
        (root / "app/views/admin/show.html.erb").write_text(
            '<div class="row-group flex items-center gap-2">x</div>\n', encoding="utf-8")
        findings, _ = run(root)
        expect("a project's OWN primitive name is honoured, not ours",
               not any("show.html.erb" in f for f in findings))

        # `grid grid-cols-3` is a deliberate fixed layout, not a failed `grid-auto`.
        (root / "app/views/admin/grid.html.erb").write_text(
            '<div class="grid grid-cols-3 gap-4 items-start">x</div>\n', encoding="utf-8")
        findings, _ = run(root)
        expect("an explicit grid is not reported — it is a different tool, not a wrong one",
               not any("grid.html.erb" in f for f in findings))

        # -- breakpoint-driven-layout, and its declared exception ---------------------------
        # MUST FAIL: a query that changes the axis, where `switcher` adapts with none.
        (root / "app/views/admin/bp.html.erb").write_text(
            '<div class="flex flex-col md:flex-row">x</div>\n', encoding="utf-8")
        findings, _ = run(root)
        expect("a breakpoint that changes the layout axis is reported",
               any("breakpoint-driven-layout" in f and "bp.html.erb" in f for f in findings))
        # MUST PASS: SIZING at a breakpoint is prescribed by the doctrine itself (responsive.md
        # §146, `w-full md:w-auto` on toolbar buttons). Flagging it would fail correct code.
        (root / "app/views/admin/sizing.html.erb").write_text(
            '<div class="w-full md:w-auto md:sticky md:top-0">x</div>\n', encoding="utf-8")
        findings, _ = run(root)
        expect("a SIZING breakpoint is not reported — the doctrine prescribes it",
               not any("sizing.html.erb" in f for f in findings))

        # THE DECLARED EXCEPTION. §3 permits a genuine structural swap; it must be written down.
        (root / "app/views/admin/swap.html.erb").write_text(
            '<%# layout-swap: nav → rail → drawer, three states, no primitive expresses it %>\n'
            '<div class="flex flex-col md:flex-row">x</div>\n', encoding="utf-8")
        # The SAME-LINE form. The code excuses a declaration on this line OR the one above, and
        # only the line-above case had a fixture -- so a mutation reading the declaration from the
        # comment-blanked text survived, because the line above is read raw either way (#1128).
        (root / "app/views/admin/swap_inline.html.erb").write_text(
            '<div class="flex flex-col md:flex-row">x</div> <%# layout-swap: same reason %>\n',
            encoding="utf-8")
        findings, _ = run(root)
        expect("a swap declared on the SAME line as the element is suppressed too",
               not any("swap_inline.html.erb" in f for f in findings))
        findings, _ = run(root)
        expect("a DECLARED structural swap is suppressed",
               not any("swap.html.erb" in f for f in findings))
        # ...and the control: the identical element WITHOUT the declaration is still reported, or
        # the exception would be indistinguishable from switching the rule off.
        (root / "app/views/admin/swap.html.erb").write_text(
            '<%# a comment that declares nothing %>\n'
            '<div class="flex flex-col md:flex-row">x</div>\n', encoding="utf-8")
        findings, _ = run(root)
        expect("the SAME element without a declaration is still reported",
               any("swap.html.erb" in f for f in findings))


        # COMMENTS ARE PROSE (#1128). A view that documents the markup it REPLACED used to be
        # reported for still containing it.
        (root / "app/views/admin/note.html.erb").write_text(
            '<%# the old markup was <div class="flex flex-col md:flex-row"> before\n'
            '    the switcher recipe replaced it %>\n'
            '<div class="stack"><p>hi</p></div>\n', encoding="utf-8")
        f, _ = run(root)
        expect("a comment quoting the old breakpoint markup is not that markup",
               not any("note.html.erb" in x for x in f))
        (root / "app/views/admin/real.html.erb").write_text(
            '<div class="flex flex-col md:flex-row"><p>hi</p></div>\n', encoding="utf-8")
        # The control on the same tree, so the assertion above cannot pass vacuously.
        expect("...while the same markup outside a comment is still reported",
               any("real.html.erb" in x for x in run(root)[0]))
        empty = Path(tempfile.mkdtemp(prefix="layout-empty-"))
        try:
            f2, v2 = run(empty)
            expect("a tree with no views reports nothing AND says it examined nothing",
                   not f2 and v2 == 0)
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
    print("a hand-rolled cluster is reported; a composed one, a flex child and an explicit grid "
          "are not")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    ap.add_argument("--set-floor", action="store_true",
                    help="record the CURRENT findings as this project's sanctioned floor (#1187)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    root = Path(args.root).resolve()
    findings, views = run(root)
    if views == 0:
        # NOT a pass. Zero findings over zero files reads exactly like a clean project.
        print(f"NOT APPLICABLE: no app/views/**/*.erb under {root} — this check examined nothing.")
        return 0
    for f in findings:
        print(f"  {f}")
    print(f"\n{views} view file(s) examined; {len(findings)} finding(s).")
    if args.set_floor:
        return content_floors.set_floor(root, "layout-composition", findings)
    if findings:
        print("Primitives this project declares: "
              f"{', '.join(sorted(primitives(root))[:12])}…")
    code, lines = content_floors.verdict(root, "layout-composition", findings)
    if lines:
        print(f"\nagainst {content_floors.FLOORS}:")
        for line in lines:
            print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
