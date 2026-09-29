#!/usr/bin/env python3
"""No modal card is ever larger than the viewport, or flush with its edge (#1391, #1419).

Run:  python3 check_modal_fit.py                 # app/components + app/views
      python3 check_modal_fit.py --root path/to/app
      python3 check_modal_fit.py --selftest

WHY THIS EXISTS. The maintainer's rule: "no modal card should be longer than the viewport vertically
and horizontally, and every modal card should have a margin away from the viewport edges." The
design-system doctrine carries it as two mechanisms (`components.md` -> Viewport inset, Modal /
Dialog): the fixed wrapper is `inset-viewport` and the panel is `max-h-full` inside it, so the
panel's maximum is the viewport minus the inset on every side at every size. The app behind #1391
capped its panel with `max-h-[calc(100vh-3rem)]`, had no inset wrapper, and pinned its drawer and
bottom sheet to the edge with `fixed inset-y-0 ... rounded-none` -- every one of which the doctrine
has since replaced.

WHAT COUNTS AS FITTING, and the doctrine's recipe is one shape of it, not the only one. The first run
against the app behind #1391 reported its centred modal and its privacy <dialog> as unbounded, because
the check knew only `inset-viewport` + `max-h-full`. Both already fit, by another route: a width of
`calc(100% - 2rem)` and the app's own `@utility modal-max-h` (`calc(100svh - 2rem - env(...))`). So:

  horizontal fit  `inset-viewport`, OR a width class of `calc(100% | 100vw - <gap>)`.
  vertical fit    `max-h-full` inside `inset-viewport`, OR a max height of `calc(100{s,d,l,}vh - <gap>)`,
                  as a class or as an `@utility` read from the app's own CSS.

(And that first run was taken on a checkout 308 commits behind the app's `dev`. The check now gets
driven against an EXPORT of the branch it judges; a number from a stale tree is a number about
something else.)

TWO RULES, judged per DIALOG COMPONENT -- a file that declares `role="dialog"` (markup or helper)
or a `<dialog>`, read together with its sibling (`x.rb` with `x.html.erb`), because a ViewComponent
computes the panel's classes in Ruby and renders them in the template:

  modal-exceeds-viewport   the component has no `inset-viewport` wrapper, or no `max-h-full` panel.
  modal-touches-edge       the component pins a panel to an edge: `fixed` with `inset-y-0` or
                           `inset-x-0`. A drawer or a bottom placement floats inside the inset. A
                           placement pinned ON PURPOSE declares it, with a reason, in the component:
                           `<%# modal-fit: edge-pinned -- why %>` (or `# modal-fit: edge-pinned -- why`
                           in the `.rb`). A declaration with no reason is not one.

COMMENTS ARE BLANKED before matching (`source_text.py`), so a component explaining the old shape is
not reported as having it.

KNOWN LIMITS: a dialog whose classes come from a helper outside its own two files is judged on the
files it has; a panel sized some other way that also fits (e.g. its own `calc()` against the inset
tokens) is reported and should record a floor rather than be exempted.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings; `--set-floor` ratchets an app
that already has findings (`content_floors.py`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import content_floors
from source_text import strip_comments

GATE = "modal-fit"

DIALOG = re.compile(r"""\brole\s*[=:]\s*["']dialog["']|<dialog\b""")
INSET = re.compile(r"(?<![\w-])inset-viewport(?![\w-])")
MAX_H = re.compile(r"(?<![\w-])max-h-full(?![\w-])")
WIDTH_GUTTER = re.compile(r"(?<![\w-])(?:max-)?w-\[calc\(100(?:%|vw)-[^\]]+\)\]")
VH_CALC_CLASS = re.compile(r"(?<![\w-])max-h-\[calc\(100[sdl]?vh-[^\]]+\)\]")
UTILITY = re.compile(r"@utility\s+([\w-]+)\s*\{([^{}]*)\}", re.S)
VH_CALC_DECL = re.compile(r"max-height\s*:\s*calc\(\s*100[sdl]?vh\s*-")
# The reason is on the SAME line: `\s` would cross the newline and read the next line as a reason.
EDGE_PINNED = re.compile(r"modal-fit:[ \t]*edge-pinned[ \t]*--[ \t]*\w")
PINNED = re.compile(r"(?<![\w-])fixed(?![\w-])[^\"'\n]*?(?<![\w-])inset-[xy]-0(?![\w-])")


def _line(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _sibling(path: Path) -> Path | None:
    name = path.name
    if name.endswith(".html.erb"):
        other = path.with_name(name[: -len(".html.erb")] + ".rb")
    elif name.endswith(".rb"):
        other = path.with_name(name[: -len(".rb")] + ".html.erb")
    else:
        return None
    return other if other.is_file() else None


def viewport_height_utilities(css: str) -> set[str]:
    """App `@utility` names whose max-height is the viewport minus a gap."""
    return {name for name, body in UTILITY.findall(css) if VH_CALC_DECL.search(body)}


def _has_class(text: str, names: set[str]) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text) for n in names)


def check_component(rel: str, source: str, sibling: str = "", vh_utilities: frozenset[str] = frozenset()) -> list[str]:
    """Judge one dialog component; `source` declares the dialog, `sibling` is its pair."""
    raw = source + "\n" + sibling
    source, sibling = strip_comments(source), strip_comments(sibling)
    m = DIALOG.search(source)
    if not m:
        return []
    both = source + "\n" + sibling
    line = _line(source, m.start())
    findings: list[str] = []
    inset = bool(INSET.search(both))
    fits_x = inset or bool(WIDTH_GUTTER.search(both))
    fits_y = (inset and bool(MAX_H.search(both))) or bool(VH_CALC_CLASS.search(both)) or _has_class(both, set(vh_utilities))
    missing = [what for what, ok in (("a width bounded by the viewport", fits_x),
                                     ("a height bounded by the viewport", fits_y)) if not ok]
    if missing:
        findings.append(
            f"{rel}:{line}: modal-exceeds-viewport — this dialog has no {' and no '.join(missing)}. "
            f"Its panel's maximum must be the viewport minus the inset on every side: the doctrine's "
            f"`inset-viewport` wrapper with a `max-h-full` panel, or a `calc(100% - gap)` width with a "
            f"`calc(100svh - gap)` max height (design-system components.md → Modal / Dialog, Viewport inset).")
    if EDGE_PINNED.search(raw):
        return findings
    for p in PINNED.finditer(both):
        findings.append(
            f"{rel}:{line}: modal-touches-edge — `{p.group(0)}` pins a panel to the viewport edge. A drawer "
            f"or a bottom placement floats inside the inset with all corners rounded (Viewport inset).")
        break
    return findings


def run(root: Path) -> tuple[list[str], int]:
    css = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted((root / "app").glob("**/*.css")))
    vh_utilities = frozenset(viewport_height_utilities(css))
    files = sorted(p for base in ("app/components", "app/views") for p in (root / base).glob("**/*")
                   if p.is_file() and p.suffix in {".erb", ".rb"})
    findings: list[str] = []
    for p in files:
        raw = p.read_text(encoding="utf-8", errors="replace")
        sib = _sibling(p)
        findings += check_component(str(p.relative_to(root)), raw,
                                    sib.read_text(encoding="utf-8", errors="replace") if sib else "", vh_utilities)
    return findings, len(files)


# --------------------------------------------------------------------------- selftest

GOOD_RB = 'PLACEMENT = { center: "relative m-auto", right: "relative ml-auto h-full" }\n' \
          'def panel = "rounded-lg w-full max-h-full flex flex-col"\n'
GOOD_ERB = '<div data-controller="modal" class="fixed inset-0 z-50 flex inset-viewport">\n' \
           '  <div class="<%= panel %>" role="dialog" aria-modal="true">…</div>\n</div>'


def _selftest() -> int:
    failures: list[str] = []

    def expect(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    def rules(erb: str, rb: str = "") -> list[str]:
        return [content_floors.rule_of(f) for f in check_component("x.html.erb", erb, rb)]

    expect("the doctrine's own modal is silent", rules(GOOD_ERB, GOOD_RB) == [])
    expect("a dialog capped with 100vh and no inset wrapper is caught",
           rules('<div class="fixed inset-0 z-50"><div class="max-h-[calc(100vh-3rem)]" role="dialog"></div></div>')
           == ["modal-exceeds-viewport"])
    expect("an inset wrapper with no max-h-full panel is caught",
           rules(GOOD_ERB.replace("<%= panel %>", "rounded-lg"), "") == ["modal-exceeds-viewport"])
    expect("the classes may live in the sibling .rb — read together",
           rules(GOOD_ERB, GOOD_RB) == [] and rules(GOOD_ERB, "") == ["modal-exceeds-viewport"])
    expect("a panel pinned to an edge is caught",
           rules(GOOD_ERB, GOOD_RB + 'X = { right: "fixed inset-y-0 right-0 h-full rounded-none" }\n') == ["modal-touches-edge"])
    expect("the backdrop's fixed inset-0 is not a pinned panel",
           "modal-touches-edge" not in rules(GOOD_ERB, GOOD_RB))
    expect("a dialog helper keyword is recognised", rules('<%= tag.div role: "dialog", class: "rounded-lg" %>') == ["modal-exceeds-viewport"])
    expect("a native <dialog> is recognised", rules('<dialog class="rounded-lg">…</dialog>') == ["modal-exceeds-viewport"])

    # ANOTHER ROUTE TO FITTING — the shapes the app behind #1391 really ships, at its current dev.
    GUTTERED = '<dialog class="modal-max-h m-auto w-[calc(100%-2rem)] max-w-[40rem] rounded-lg">…</dialog>'
    expect("a calc(100%-gap) width with an app utility that is calc(100svh - gap) fits",
           [content_floors.rule_of(f) for f in check_component("x.html.erb", GUTTERED, "", frozenset({"modal-max-h"}))] == [])
    expect("...and the same markup WITHOUT that utility defined does not fit vertically",
           rules(GUTTERED) == ["modal-exceeds-viewport"])
    expect("a max-h-[calc(100dvh-3rem)] class fits vertically",
           rules('<div class="w-[calc(100%-2rem)] max-h-[calc(100dvh-3rem)]" role="dialog"></div>') == [])
    expect("max-h-screen is the whole viewport, not the viewport minus a gap",
           rules('<div class="w-[calc(100%-2rem)] max-h-screen" role="dialog"></div>') == ["modal-exceeds-viewport"])
    expect("max-h-full with NO inset wrapper is not bounded by the viewport",
           rules('<div class="w-[calc(100%-2rem)] max-h-full" role="dialog"></div>') == ["modal-exceeds-viewport"])
    expect("an @utility is read as a viewport height only when its max-height is calc(100vh - gap)",
           viewport_height_utilities("@utility modal-max-h {\n  max-height: calc(100svh - 2rem - env(safe-area-inset-top));\n}\n"
                                     "@utility tall { max-height: 100vh; }\n@utility card { padding: 1rem; }") == {"modal-max-h"})

    # A PLACEMENT PINNED ON PURPOSE, declared with a reason.
    PINNED_RB = GOOD_RB + 'X = { right: "fixed inset-y-0 right-0 h-full rounded-none" }\n'
    expect("a declared edge-pinned placement is not a finding",
           rules(GOOD_ERB, "# modal-fit: edge-pinned -- the drawer is a side panel, probed by modal_bounds\n" + PINNED_RB) == [])
    expect("a declaration with no reason is not a declaration",
           rules(GOOD_ERB, "# modal-fit: edge-pinned --\n" + PINNED_RB) == ["modal-touches-edge"])
    expect("an HTML comment's max-h class does not make a dialog fit",
           rules('<!-- max-h-[calc(100dvh-3rem)] w-[calc(100%-2rem)] -->\n<div class="rounded-lg" role="dialog"></div>') == ["modal-exceeds-viewport"])
    expect("a file with no dialog is not judged", rules('<div class="fixed inset-y-0 left-0">nav</div>') == [])
    expect("the old shape described in a comment is silent",
           rules('<%# was: fixed inset-y-0 right-0 %>\n' + GOOD_ERB, GOOD_RB) == [])

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app/components/ui").mkdir(parents=True)
        (root / "app/components/ui/modal_component.html.erb").write_text(GOOD_ERB)
        (root / "app/components/ui/modal_component.rb").write_text(GOOD_RB)
        (root / "app/components/ui/sheet_component.html.erb").write_text('<div class="fixed inset-x-0 bottom-0" role="dialog"></div>')
        found, examined = run(root)
        got = sorted(content_floors.rule_of(f) for f in found)
        expect("run(): the doctrine modal passes through its sibling .rb", not any("modal_component" in f for f in found))
        expect("run(): the edge sheet reports both rules", got == ["modal-exceeds-viewport", "modal-touches-edge"])
        expect("run(): every file was examined", examined == 3)

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_modal_fit selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    ap.add_argument("--set-floor", action="store_true",
                    help="record the CURRENT findings as this project's sanctioned floor (#1187)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    root = Path(args.root).resolve()
    findings, examined = run(root)
    if examined == 0:
        print(f"NOT APPLICABLE: no app/components or app/views under {root} — this check examined nothing.")
        return 0
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} view/component file(s) examined; {len(findings)} finding(s).")
    if args.set_floor:
        return content_floors.set_floor(root, GATE, findings)
    code, lines = content_floors.verdict(root, GATE, findings)
    if lines:
        print(f"\nagainst {content_floors.FLOORS}:")
        for line in lines:
            print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
