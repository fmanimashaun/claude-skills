#!/usr/bin/env python3
"""Compose the system-carrying half of a Claude Design prompt, from this project's own sources.

Run:  python3 design_prompt.py --surface dashboard
      python3 design_prompt.py --surface dashboard --theme app/assets/tailwind/application.css
      python3 design_prompt.py --selftest

WHY THIS EXISTS (#745). The inbound half of the loop shipped first: `design-handoff.md` and the
`design-porter` agent turn a Claude Design canvas into Rails + Hotwire. But the cost of that port is
decided BEFORE it starts, by the prompt.

Measured on a real artboard: `Ledger auth.dc.html` declares **50 of its own `:root` tokens** and makes
**755 `var(--…)`** references. Those names happened to align with the project's. Nothing made them
align -- the prompt was hand-written and the alignment was luck. When it is not luck, the port becomes
a translation between two invented vocabularies, and that is where a whole-app audit found **20
alignable divergences** (#739).

So the prompt carries the system: the project's OWN role tokens, the real component catalog, and the
band sequence for the surface. If the returned canvas declares `:root` with our names, then
`design-handoff.md` §2's "drop the `:root` block" is safe by construction rather than by careful
reading.

WHAT IS DERIVED AND WHAT IS AUTHORED. This script emits only the part that would rot if retyped --
tokens, catalog, bands. What the surface is *for*, its tone, and which states it must show are
judgement, and belong to `/design-flow:canvas` and the human. Generating prose about intent would be
inventing a brief, not carrying a system.

THREE SOURCES, ALL REUSED RATHER THAN RE-PARSED:

  * the project's `@theme` block, via `palette_candidates` -- which already carries the
    `(?!\\s+inline)` carve-out that stops Tailwind's `--color-*` alias re-export shadowing the role it
    aliases. A second parser here would drift from that.
  * `component-shapes.json` -- the catalog, 52 entries. Derived so that adding a component changes the
    prompt with no edit; a hand-written list is stale the day one lands.
  * the marked band block in `page-anatomies.md`, via `compose_brief.read_bands`, for the same reason
    `check_page_pacing` imports it rather than keeping its own.

IT DEGRADES LOUDLY. A missing `@theme`, or a surface with no anatomy, is REPORTED in the output and on
stderr -- never silently dropped. A prompt that quietly omits the token list still looks like a prompt,
and the canvas it produces is the one nobody can port.

Exit codes:  0 = composed · 1 = a required source was unusable · 2 = not a design-flow context

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

CATALOG = "component-shapes.json"
ANATOMY = "page-anatomies.md"
DEFAULT_THEME = Path("app/assets/tailwind/application.css")

# Roles a canvas must be told about by name. Anything else in `:root` is a primitive the design system
# keeps private, and naming it in a prompt would invite the canvas to bind to it.
ROLE_PREFIXES = ("--background", "--foreground", "--card", "--primary", "--secondary", "--muted",
                 "--accent", "--destructive", "--border", "--input", "--ring", "--radius",
                 "--space-", "--text-step", "--font-")


def project_roles(theme_css: Path) -> tuple[dict[str, str], str | None]:
    """`({token: value}, problem)`. The problem is text, never an exception: a prompt without tokens
    is still worth emitting *with the gap named*, which is what makes the gap actionable."""
    if not theme_css.is_file():
        return {}, (f"no {theme_css} — the prompt cannot carry this project's tokens, so the canvas "
                    f"will invent its own and the port becomes a translation between two systems")
    try:
        import palette_candidates as pc
        src = pc.bpl.strip_css_comments(theme_css.read_text(encoding="utf-8"))
        roles = pc._declarations(pc.bpl.selector_block(src, ":root"))
    except Exception as exc:                                              # noqa: BLE001
        return {}, f"could not read {theme_css}: {type(exc).__name__}: {exc}"
    kept = {k: v for k, v in roles.items() if k.startswith(ROLE_PREFIXES)}
    if not kept:
        return {}, f"{theme_css} declares no role tokens in `:root` — only primitives, or nothing"
    return kept, None


def catalog(refs: Path) -> tuple[list[str], str | None]:
    """The component names a canvas may compose from. Derived from the shapes file."""
    doc = refs / CATALOG
    if not doc.is_file():
        return [], f"no {doc} — without the catalog the canvas will invent components"
    try:
        data = json.loads(doc.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [], f"{doc} is not readable JSON: {exc}"
    # `_comment` and any other underscore key is metadata, not a component.
    return sorted(k for k in data if not k.startswith("_")), None


def bands_for(refs: Path, surface: str) -> tuple[list[str], str | None]:
    doc = refs / ANATOMY
    try:
        import compose_brief as cb
        rows = cb.read_bands(doc)
    except Exception as exc:                                              # noqa: BLE001
        return [], f"could not read {doc}: {exc}"
    names = [b.name for b in rows] if rows else []
    if not names:
        return [], f"{doc} declares no bands"
    return names, None


def compose(surface: str, roles: dict[str, str], components: list[str],
            bands: list[str], problems: list[str]) -> str:
    out = [f"# Claude Design brief — {surface}", ""]
    if problems:
        # First, and loudly. A gap buried under 60 lines of tokens is a gap nobody acts on.
        out += ["> **This prompt is incomplete.** Fix these before sending it, or the canvas will "
                "invent what is missing and the port will pay for it:", ""]
        out += [f"> - {p}" for p in problems] + [""]

    out += ["## Use these exact token names", "",
            "Declare `:root` with **these names and no others**. Do not invent token names, and do "
            "not inline literal values where a name exists — the returned canvas is ported into an "
            "app that already defines every one of these, and a name that matches is a substitution "
            "rather than a judgement call.", ""]
    if roles:
        out += ["```css", ":root{"]
        out += [f"  {k}: {v};" for k, v in sorted(roles.items())]
        out += ["}", "```", ""]
    else:
        out += ["_No tokens available — see the gap above._", ""]

    out += ["## Compose from this catalog", "",
            "These components exist. Compose the surface from them; **do not invent a component** "
            "that is not on this list. If the design genuinely needs one that is missing, say so "
            "explicitly in the output rather than drawing it.", ""]
    out += [f"- {c}" for c in components] if components else ["_No catalog available._"]
    out += [""]

    if bands:
        out += ["## Band sequence", "",
                "The surface is paced as these bands, in order. Keep the order; a band may be "
                "omitted, but say which and why.", ""]
        out += [f"{i}. {b}" for i, b in enumerate(bands, 1)] + [""]

    out += ["## Constraints", "",
            "- Semantic HTML. Every interactive control reachable by keyboard, with a visible focus "
            "ring.",
            "- One `h1`. Heading levels descend without skipping.",
            "- Show **every state** the surface has — empty, loading, error, success — not only the "
            "populated one.",
            "- No client-side framework, no build step, no external script.", ""]
    return "\n".join(out)


def _selftest() -> int:
    import tempfile
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        css = root / "application.css"
        # Multi-line, closing brace on its own line -- the shape `selector_block` requires and the
        # shape a formatter produces. A single-line fixture passed nothing to the reader and made
        # this look like a reader bug; it was the fixture being unrealistic.
        css.write_text(
            "@theme {\n  --brand-x: #111;\n}\n"
            ":root {\n"
            "  --background: #FAF7F2;\n"
            "  --primary: #0077CC;\n"
            "  --brand-x: #111;\n"
            "  --space-s: 1rem;\n"
            "  --text-step-0: 1rem;\n"
            "}\n"
            ".dark {\n  --background: #000;\n}\n", encoding="utf-8")
        roles, problem = project_roles(css)
        check("reads the project's roles", problem is None and roles.get("--primary") == "#0077CC")
        # PRIMITIVES ARE PRIVATE. Naming one in a prompt invites the canvas to bind to it.
        check("...and omits a private primitive", "--brand-x" not in roles)
        check("...keeping the scale tokens", "--space-s" in roles and "--text-step-0" in roles)

        # DEGRADES LOUDLY, in both directions.
        _, problem = project_roles(root / "absent.css")
        # Assert the SPECIFIC message, not a substring any error happens to contain. `"no " in
        # problem` passed on the generic exception path too -- an OS error text matched it -- so the
        # mutation removing the early return survived while the fixture looked like it covered it.
        check("a missing theme is reported, not silent",
              problem is not None and "cannot carry this project's tokens" in problem)
        empty = root / "empty.css"
        empty.write_text(":root {\n  --brand-only: #111;\n}\n", encoding="utf-8")
        _, problem = project_roles(empty)
        check("a theme with only primitives is reported",
              problem is not None and "no role tokens" in problem)

        refs = root / "references"; refs.mkdir()
        (refs / CATALOG).write_text(json.dumps({"_comment": "x", "Button": {}, "Card": {}}),
                                    encoding="utf-8")
        names, problem = catalog(refs)
        check("catalog is derived from the shapes file", names == ["Button", "Card"])
        check("...and metadata keys are not components", "_comment" not in names)
        _, problem = catalog(root)
        check("a missing catalog is reported", problem is not None)

        # The gap must lead the document, not trail it.
        body = compose("dashboard", {}, [], [], ["no tokens"])
        # `find`, not `index`: under the mutation that drops the warning entirely, `index` RAISES and
        # a crash is not a verdict -- the harness rejects a fixture that dies instead of failing.
        check("a gap is stated before anything else",
              0 <= body.find("This prompt is incomplete") < body.find("Use these exact token names"))
        body = compose("dashboard", roles or {"--primary": "#0077CC"}, ["Button"], ["Hero"], [])
        check("a complete prompt carries no warning", "incomplete" not in body)
        check("...names the surface", body.startswith("# Claude Design brief — dashboard"))
        check("...emits the tokens as CSS", "--primary: #0077CC;" in body)
        check("...and forbids inventing a component", "do not invent a component" in body)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--surface", default="surface")
    ap.add_argument("--theme", type=Path, default=DEFAULT_THEME)
    ap.add_argument("--refs", type=Path,
                    help="fidara-design references dir (default: resolve from the plugin root)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()

    refs = a.refs or (HERE.parents[3] / "skills" / "fidara-design" / "references")
    problems: list[str] = []
    roles, p = project_roles(a.theme)
    if p:
        problems.append(p)
    components, p = catalog(refs)
    if p:
        problems.append(p)
    bands, p = bands_for(refs, a.surface)
    if p:
        problems.append(p)

    print(compose(a.surface, roles, components, bands, problems))
    for p in problems:
        print(f"incomplete: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
