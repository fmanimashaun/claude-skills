#!/usr/bin/env python3
"""A surface must not impose layout on the content it is handed (#1117).

Run:  python3 check_surface_layout.py                 # app/components
      python3 check_surface_layout.py --root path/to/app
      python3 check_surface_layout.py --selftest

WHY THIS EXISTS, and the visible half is the lesser half. A card component -- a padded, bordered
surface taking arbitrary content -- wrapped what it was handed in a layout recipe with a hardcoded
spacing value. Measured on the app where it was found, before anything changed:

    call sites                                        112 in 63 files
    already pass `class="stack"` on the outer element  77
    use the header slot                                 1
    use the footer slot                                 0

**It flattens**: a grid cannot survive being wrapped in a flex column, so four grid layouts
collapsed to one column. Visible, eventually, on the right screen.

**And it silently overrides**, which is the defect that escaped review for months: 77 of 112 call
sites already declared `stack` with their OWN `--space`, and the component's hardcoded inner value
won on the children that mattered. A caller asked for one spacing step and rendered another. No
error, no glitch on most screens, and no way to notice except by reading the component. **Every
individual template reads correctly**, which is exactly why review does not catch it.

THE DISTINCTION THAT MAKES IT CHECKABLE.

  * A SURFACE takes arbitrary content and gives it a background, a border, padding. It cannot know
    what it will hold, so it must not arrange it.
  * A COMPOSITION is a named thing with a defined internal arrangement -- a shell with a rail and a
    main, a dialog with a title and actions. Its layout IS the component.

A surface must not impose layout. A composition may, and must DECLARE itself one, in the file, with
a reason. On the app above that yields three legitimate entries -- a page shell, a dialog, an empty
state -- and fails the card.

MATCH SLOT RENDERING, NOT THE WORD, and this is learned rather than designed. A first version keyed
on the source containing `content` and produced four false positives in one run: `"main content"` in
a prose comment, a `--content-cols` custom property, `"hidden-content"` in another comment, and
**Tailwind's own `before:content-['']` utility**. Any shipped version of this gate meets the same
four shapes. So the two ways ViewComponent actually emits a slot are matched: `<%= content %>` in a
template, and a bare `content` as an argument inside a `call`.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The layout recipes a surface must not wrap its content in.
RECIPES = ("stack", "cluster", "grid-auto", "switcher", "sidebar", "reel", "center", "cover")

# A component declares itself a composition, in the file, with a reason after the colon.
DECLARES = re.compile(r"(?:#|<%#)\s*composition:\s*\S")

# SLOT RENDERING, not the word. `<%= content %>` / `<%= header %>` in a template, or a bare
# `content` as an argument in a `call` -- `concat content`, `safe_join([..., content])`.
SLOT_ERB = re.compile(r"<%=\s*(?:content|[a-z_]+)\s*%>")
SLOT_RUBY = re.compile(r"(?:concat|safe_join\(\[?|,)\s*content\b")

CLASS_ATTR = re.compile(r'class(?:\s*[:=]\s*)["\']([^"\']*)["\']')


def wraps_slot_in_recipe(source: str) -> str | None:
    """The recipe a slot is wrapped in, or None. Returns the recipe so the finding can name it."""
    if not (SLOT_ERB.search(source) or SLOT_RUBY.search(source)):
        return None                      # renders no slot; nothing arbitrary to arrange
    for classes in CLASS_ATTR.findall(source):
        for recipe in RECIPES:
            if recipe in classes.split():
                return recipe
    return None


def run(root: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    files = sorted(root.glob("app/components/**/*.rb")) + \
        sorted(root.glob("app/components/**/*.erb"))
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        recipe = wraps_slot_in_recipe(source)
        if not recipe:
            continue
        if DECLARES.search(source):
            continue                     # a composition, declared with a reason
        findings.append(
            f"{path.relative_to(root)}: wraps the content it is handed in `{recipe}` — a SURFACE "
            f"takes arbitrary content and cannot know what it will hold, so it must not arrange "
            f"it. Two things go wrong and the second is the one review misses: a grid cannot "
            f"survive being wrapped in a flex column, and a caller that already declared its own "
            f"spacing is silently overridden — no error, no glitch, every template still reading "
            f"correctly. If this component's layout IS the component, say so: "
            f"`# composition: <why>`")
    return findings, len(files)


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # THE DEFECT, in the exact shape found: a surface wrapping arbitrary content in a recipe.
    CARD = ('content_tag(:div, class: "stack", style: "--space: var(--space-xs)") do\n'
            '  concat content\n'
            'end\n')
    expect("a surface wrapping its slot in a recipe is caught",
           wraps_slot_in_recipe(CARD) == "stack")

    # MUST PASS: a declared composition. Without this the gate fails a page shell and a dialog on
    # day one, and gets an exclusion list or gets switched off.
    SHELL = "# composition: a rail beside a main region; the arrangement IS this component\n" + CARD
    expect("a DECLARED composition is accepted", DECLARES.search(SHELL) is not None)

    # MUST PASS: a surface that renders a slot and arranges nothing.
    PLAIN = 'content_tag(:div, class: "rounded-md border p-4") { content }\n'
    expect("a surface that arranges nothing is silent", wraps_slot_in_recipe(PLAIN) is None)

    # MUST PASS: a recipe with no slot. A component laying out its OWN fixed parts is composing,
    # not imposing on somebody else's content.
    OWN = '<div class="cluster"><span>a</span><span>b</span></div>\n'
    expect("a recipe with no slot rendered is not this rule's business",
           wraps_slot_in_recipe(OWN) is None)

    # THE FOUR FALSE POSITIVES, all met in one real run by a version that matched the WORD.
    for label, src in (
        ("a prose comment saying 'main content'",
         '# the main content sits here\n<div class="stack"><span>a</span></div>\n'),
        ("a --content-cols custom property",
         '<div class="stack" style="--content-cols: 3"><span>a</span></div>\n'),
        ("a 'hidden-content' class in a comment",
         '# hidden-content is toggled elsewhere\n<div class="stack"><span>a</span></div>\n'),
        ("Tailwind's own before:content-[''] utility",
         '<div class="stack before:content-[\'\']"><span>a</span></div>\n'),
    ):
        expect(f"NOT a finding: {label}", wraps_slot_in_recipe(src) is None)

    # Both slot spellings must be seen, or half the components are invisible to the gate.
    expect("the ERB spelling of a slot is seen",
           wraps_slot_in_recipe('<div class="stack"><%= content %></div>\n') == "stack")
    expect("the safe_join spelling is seen",
           wraps_slot_in_recipe('safe_join([tag.span, content])\ntag.div(class: "cluster")\n')
           == "cluster")

    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="surface-layout-"))
    try:
        d = root / "app/components/ui"
        d.mkdir(parents=True)
        (d / "card_component.rb").write_text(CARD, encoding="utf-8")
        (d / "shell_component.rb").write_text(SHELL, encoding="utf-8")
        (d / "panel_component.rb").write_text(PLAIN, encoding="utf-8")
        findings, examined = run(root)
        expect("all three components were read", examined == 3)
        expect("the card is reported, and the recipe named",
               len(findings) == 1 and "card_component" in findings[0] and "`stack`" in findings[0])
        expect("the declared composition is not reported",
               not any("shell_component" in f for f in findings))
        expect("the plain surface is not reported",
               not any("panel_component" in f for f in findings))

        empty = Path(tempfile.mkdtemp(prefix="surface-empty-"))
        try:
            f2, e2 = run(empty)
            expect("a tree with no components reports nothing AND says it examined nothing",
                   not f2 and e2 == 0)
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
    print("a surface wrapping its slot is caught; a declared composition and the four "
          "false-positive shapes are not")
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
    findings, examined = run(root)
    if examined == 0:
        # NOT a pass. Zero findings over zero components reads exactly like a clean app.
        print(f"NOT APPLICABLE: no app/components under {root} — this check examined nothing.")
        return 0
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} component file(s) examined; {len(findings)} finding(s).")
    if findings:
        print("A COMPOSITION may impose layout — declare it with `# composition: <why>` and the "
              "check stands aside. A SURFACE may not, because it cannot know what it holds.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
