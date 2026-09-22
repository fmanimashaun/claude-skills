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

Those four figures are an AUDIT of one app on 2026-09-21, not something this script computes -- they
are here with their date because a figure with no provenance goes stale silently (`frozen-figure`,
#1124). Re-take them by grepping that app's `app/views` for the component's call sites; nothing in
this repo can refresh them for you.

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

from source_text import strip_comments

# The layout recipes a surface must not wrap its content in.
RECIPES = ("stack", "cluster", "grid-auto", "switcher", "sidebar", "reel", "center", "cover")

# A component declares itself a composition, in the file, with a reason after the colon.
DECLARES = re.compile(r"(?:#|<%#)\s*composition:\s*\S")

# SLOT RENDERING, not the word. `<%= content %>` / `<%= header %>` in a template, or a bare
# `content` as an argument in a `call` -- `concat content`, `safe_join([..., content])`.
# A SLOT IS WHAT THE COMPONENT DECLARED, not any bare identifier (#1141). The first version was
# `<%= content %>` OR `<%= <any identifier> %>`, which reported a table whose only matches were
# `<%= caption %>` -- a constructor keyword exposed by `attr_reader` -- and `<%= caption_classes %>`,
# a private method returning a CSS class string. Neither is content the component cannot see, and
# that component declares no slots at all.
#
# This is the same failure as the `content`-as-a-word one this check was born fixing: matching the
# WORD rather than the construct. It was closed for `content` and left open for every other single
# identifier, one variant along.
SLOT_DECLARATION = re.compile(r"^\s*renders_(?:one|many)\s+[:'\"]([a-z_]+)", re.M)
SLOT_RUBY = re.compile(r"(?:concat|safe_join\(\[?|,)\s*content\b")


def declared_slots(source: str, sibling: str = "") -> set[str]:
    """`content`, plus every slot the component declares. `sibling` is the paired .rb or .erb.

    Read from the DECLARATION rather than guessed from the template, because a template cannot tell
    a slot from an attribute reader: both are `<%= name %>`. The component says which is which.
    """
    return {"content"} | set(SLOT_DECLARATION.findall(source)) | set(SLOT_DECLARATION.findall(sibling))


def renders_a_slot(source: str, slots: set[str]) -> bool:
    """Does this template output a DECLARED slot, or a bare `content` in a `call`?"""
    if SLOT_RUBY.search(source):
        return True
    return any(re.search(r"<%=\s*" + re.escape(name) + r"\s*%>", source) for name in slots)

CLASS_ATTR = re.compile(r'class(?:\s*[:=]\s*)["\']([^"\']*)["\']')


# HTML elements that never nest and never close, so they can carry no content and must not be
# pushed onto the element stack.
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                 "param", "source", "track", "wbr"}
TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:[^<>]|<%[^%]*%>)*?)(/?)>")


def recipe_containing_a_slot(source: str, slots: set[str]) -> str | None:
    """The recipe on an element that CONTAINS a slot render, or None (#1152).

    CONTAINMENT, NOT CO-OCCURRENCE, and the difference is the whole finding. The previous version
    asked "does this file hold a slot anywhere" and "does it hold a recipe anywhere" and reported
    when both were true -- while its NAME claimed the recipe wrapped the slot. A reviewer supplied
    the input that tells the two apart: a declared slot rendered OUTSIDE every recipe, with a
    recipe on an unrelated element. Co-occurrence reports it; containment does not; and every
    fixture written before that one satisfied BOTH mechanisms, so none could see the difference.

    That is the general trap worth naming: **a test whose passing is compatible with two different
    mechanisms proves neither.** A positive control has to be an input on which they disagree.
    """
    stack: list[tuple[str, str | None, int]] = []
    for m in TAG.finditer(source):
        closing, name, attrs, self_closing = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            while stack:
                tag, recipe, content_start = stack.pop()
                if tag != name:
                    continue          # unbalanced markup: discard until the tags line up again
                if recipe and renders_a_slot(source[content_start:m.start()], slots):
                    return recipe
                break
            continue
        if self_closing or name in VOID_ELEMENTS:
            continue                  # carries no content
        found = None
        for classes in CLASS_ATTR.findall(attrs):
            for candidate in RECIPES:
                if candidate in classes.split():
                    found = candidate
                    break
        stack.append((name, found, m.end()))
    return None


def any_element_carries_a_recipe(source: str) -> bool:
    """Is there markup here at all that a containment scan could reason about?"""
    for m in TAG.finditer(source):
        if m.group(1):
            continue
        for classes in CLASS_ATTR.findall(m.group(3)):
            if any(r in classes.split() for r in RECIPES):
                return True
    return False


def co_occurring_recipe(source: str) -> str | None:
    """The weaker instrument, for markup built in RUBY rather than written as tags.

    A `call` method composing with `tag.div(class: "cluster") { … content … }` has no HTML tags for a
    containment scan to walk, and that is precisely the surface case this gate exists for -- so
    dropping it in the name of precision would trade a false positive for a hole. Recipe and slot in
    the same Ruby source is strong evidence and NOT proof of nesting, and saying which instrument
    produced a finding is the honest half.
    """
    for classes in CLASS_ATTR.findall(source):
        for recipe in RECIPES:
            if recipe in classes.split():
                return recipe
    return None


def wraps_slot_in_recipe(source: str, sibling: str = "") -> str | None:
    """The recipe a slot is wrapped in, or None. Returns the recipe so the finding can name it."""
    # COMMENTS ARE PROSE (#1128). A file explaining why the wrapper was removed used to re-trip the
    # gate its own fix satisfies. `run()` still tests the RAW source for the `# composition:`
    # declaration, which lives in a comment on purpose.
    source = strip_comments(source)
    slots = declared_slots(source, strip_comments(sibling))
    if not renders_a_slot(source, slots):
        return None                      # renders no slot; nothing arbitrary to arrange
    # MARKUP GETS CONTAINMENT; RUBY-BUILT MARKUP GETS CO-OCCURRENCE. When no element here carries a
    # recipe, the recipes are in `tag.div(class: …)` calls a tag scan cannot walk -- and that is the
    # surface case this gate exists for, so falling back keeps the coverage rather than trading a
    # false positive for a hole. Where markup DOES carry a recipe, containment decides, and the
    # co-occurrence answer is never consulted.
    if any_element_carries_a_recipe(source):
        return recipe_containing_a_slot(source, slots)
    return co_occurring_recipe(source)


def _sibling_source(path: Path) -> str:
    """The other half of a ViewComponent pair: `x.rb` <-> `x.html.erb`. Empty when there is none."""
    stem = path.name.split(".", 1)[0]
    for candidate in (path.with_name(f"{stem}.rb"), path.with_name(f"{stem}.html.erb")):
        if candidate != path and candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def run(root: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    files = sorted(root.glob("app/components/**/*.rb")) + \
        sorted(root.glob("app/components/**/*.erb"))
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        # The DECLARATION lives in the `.rb`; the rendering lives in the `.html.erb`. Reading one
        # without the other is why a template's attribute readers looked like slots.
        sibling = _sibling_source(path)
        recipe = wraps_slot_in_recipe(source, sibling)
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
        # The utility is INSIDE the recipe element, so containment is satisfied and only "match
        # the construct, not the word" can keep it silent -- the shape that made this rule exist.
        ("Tailwind's own before:content-[''] utility",
         '<div class="stack"><span class="before:content-[\'\']">a</span></div>\n'),
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


        # COMMENTS ARE PROSE (#1128). The file that describes REMOVING the wrapper used to be
        # reported for having it -- the false positive lands on the remediated file, and the
        # natural response is to delete the explanation to satisfy the detector.
        (root / "app/components/note_component.rb").write_text(
            "class NoteComponent < ViewComponent::Base\nend\n", encoding="utf-8")
        (root / "app/components/note_component.html.erb").write_text(
            '<%# it used to be <div class="stack"> around the slot; removed because it\n'
            '    flattened every grid it was handed %>\n'
            '<!-- and never `class: "cluster"` here either -->\n'
            # INSIDE the recipe on purpose: with the comment unstripped this element would hold a
            # slot-shaped match and fire, so only `strip_comments` can keep it silent. Outside a
            # recipe, containment alone would save it and the fixture would stop discriminating --
            # which is exactly what happened when containment landed, and two mutations SURVIVED.
            '<div class="stack">\n  <%# the removed wrapper held <%= content %> once %>\n'
            '  <p>text</p>\n</div>\n', encoding="utf-8")
        f, _ = run(root)
        expect("a comment describing the wrapper is not the wrapper",
               not any("note_component" in x for x in f))
        # The CONTROL on the same run: the real one is still reported, or the fixture above
        # would pass just as well against a gate that had stopped looking at anything.
        expect("...while the component that really wraps its slot is still reported",
               any("card_component" in x for x in f))
        # A SLOT IS WHAT THE COMPONENT DECLARED (#1141). A real table reported a finding whose
        # only "slots" were `<%= caption %>` -- a constructor keyword exposed by `attr_reader` --
        # and `<%= caption_classes %>`, a private method returning a CSS class string. It declares
        # `renders_one`/`renders_many` nowhere, so there is no content it cannot see.
        (root / "app/components/table_component.rb").write_text(
            "class TableComponent < ViewComponent::Base\n"
            "  def initialize(caption:)\n    @caption = caption\n  end\n"
            "  attr_reader :caption\n"
            "  private def caption_classes = \"sr-only\"\n"
            "end\n", encoding="utf-8")
        (root / "app/components/table_component.html.erb").write_text(
            # The readers sit INSIDE the `cluster`, so only "a slot is what the component
            # DECLARED" can keep this silent -- containment is satisfied here.
            '<div class="scroll-x">\n'
            '  <a class="cluster" href="#">\n'
            '    <span class="<%= caption_classes %>"><%= caption %></span>\n'
            '  </a>\n'
            "</div>\n", encoding="utf-8")
        f, _ = run(root)
        expect("an attribute reader is not a slot, so a recipe elsewhere is not a finding",
               not any("table_component" in x for x in f))

        # THE CONTROL, on the same tree: a component that DECLARES a slot and wraps it is still
        # reported -- or narrowing what counts as a slot has simply switched the check off.
        (root / "app/components/panel_component.rb").write_text(
            "class PanelComponent < ViewComponent::Base\n  renders_one :header\nend\n",
            encoding="utf-8")
        (root / "app/components/panel_component.html.erb").write_text(
            '<div class="stack">\n  <%= header %>\n</div>\n', encoding="utf-8")
        f, _ = run(root)
        expect("...while a DECLARED slot wrapped in a recipe is still reported",
               any("panel_component" in x for x in f))
        # ...and `content` needs no declaration: every ViewComponent has it.
        (root / "app/components/shell_component.html.erb").write_text(
            '<div class="cluster">\n  <%= content %>\n</div>\n', encoding="utf-8")
        f, _ = run(root)
        expect("...and bare `content` still counts with no declaration at all",
               any("shell_component" in x for x in f))

        # THE `no slot` GUARD IS LOAD-BEARING ON THE RUBY PATH, and only there. With markup,
        # containment already answers "a recipe with nothing inside it"; with Ruby-built markup the
        # fallback is pure co-occurrence, so the early return is the only thing keeping a component
        # that merely MENTIONS a recipe silent. The markup fixture stopped discriminating the moment
        # containment landed, and the mutation SURVIVED until this one existed.
        (root / "app/components/ruby_only_component.rb").write_text(
            "class RubyOnlyComponent < ViewComponent::Base\n"
            "  def call = tag.div(class: \"stack\") { \"static\" }\n"
            "end\n", encoding="utf-8")
        f, _ = run(root)
        expect("a Ruby-built recipe rendering NO slot is not a finding",
               not any("ruby_only_component" in x for x in f))

        # CONTAINMENT, NOT CO-OCCURRENCE (#1152). THE DISCRIMINATING INPUT, supplied by a
        # reviewer: a DECLARED slot rendered OUTSIDE every recipe, with a recipe on an unrelated
        # element. Co-occurrence reports it; containment does not. Every fixture written before
        # this one satisfied BOTH mechanisms, so none could tell them apart -- a test whose passing
        # is compatible with two different mechanisms proves neither.
        (root / "app/components/apart_component.rb").write_text(
            "class ApartComponent < ViewComponent::Base\n  renders_one :toolbar\nend\n",
            encoding="utf-8")
        (root / "app/components/apart_component.html.erb").write_text(
            '<div class="box">\n  <%= toolbar %>\n</div>\n'
            '<a class="cluster" href="#">Sort</a>\n', encoding="utf-8")
        f, _ = run(root)
        expect("a slot OUTSIDE every recipe is not a finding",
               not any("apart_component" in x for x in f))

        # THE CONTROL, and it must be an input where the two mechanisms AGREE is not enough --
        # this one is contained, so it separates "still fires" from "fires for the wrong reason"
        # only when read together with the case above.
        (root / "app/components/inside_component.rb").write_text(
            "class InsideComponent < ViewComponent::Base\n  renders_one :toolbar\nend\n",
            encoding="utf-8")
        (root / "app/components/inside_component.html.erb").write_text(
            '<div class="stack">\n  <section>\n    <%= toolbar %>\n  </section>\n</div>\n',
            encoding="utf-8")
        f, _ = run(root)
        expect("...while a slot nested inside the recipe still is",
               any("inside_component" in x for x in f))

        # A recipe INSIDE the slot's element is the inverse and must stay silent: the surface is
        # not arranging the content, the content sits beside something that arranges itself.
        (root / "app/components/inverse_component.rb").write_text(
            "class InverseComponent < ViewComponent::Base\n  renders_one :toolbar\nend\n",
            encoding="utf-8")
        (root / "app/components/inverse_component.html.erb").write_text(
            '<div class="box">\n  <%= toolbar %>\n  <a class="cluster">Sort</a>\n</div>\n',
            encoding="utf-8")
        f, _ = run(root)
        expect("a recipe INSIDE the slot's element is not wrapping it",
               not any("inverse_component" in x for x in f))

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
