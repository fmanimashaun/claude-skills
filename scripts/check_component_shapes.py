#!/usr/bin/env python3
"""Reconcile `component-shapes.json` against `components.md` — so the catalogue is whole (#609).

WHY THIS EXISTS. `design_prompt.py` builds the component catalog a Claude Design canvas may compose
from by reading this file's top-level keys (`catalog()`), so a sidecar that drifts from the prose it
accompanies is silent in the worst direction: a component added to the catalogue and not to the
shapes file simply **is not offered to the canvas**, and the canvas invents one instead — which is
the exact failure `/design-flow:canvas` exists to prevent. Without this check, "the canvas composes
from the real catalogue" is a claim nothing makes true — the claims-vs-enforcement defect this repo
is built around.

It was written for `pen_library.py`, which mirrored the same file into a pen.dev library and was
retired in #766. The consumer changed; the reconciliation did not, because the file is still a
sidecar to `components.md` and can still drift from it.

WHAT IT ASSERTS, and each half matters:

  1. **Every catalogue row has an entry.** Drawn, or `drawable: false` WITH a reason. Silence is not
     an option, because silence is indistinguishable from an oversight.
  2. **Every entry names a real row.** A shape for a component that no longer exists is a component
     offered in pen that `rails-ui-composer` cannot build — the exact drift the mirror prevents.
  3. **Every part is one the generator draws**, and every role it names is one `theme.css` declares.
     A shape referencing an undeclared role would be reported at generation time and silently absent
     from the library; catching it here makes it a build failure instead of a quiet gap.

It is a GATE, not a diagnostic: it is a claim about repository content, so it holds identically on a
runner and on a laptop.

Exit codes:  0 reconciled · 1 findings · 2 unreadable input
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Two files, one catalogue (#871): the commerce entries moved to components-commerce.md, and a shape
# check reading only components.md would report every commerce shape as "not a components.md row".
CATALOGUE_FILES = tuple(ROOT / "plugins" / "rails-stack" / "skills" / "design-system" / "references" / n
                        for n in ("components.md", "components-commerce.md"))
CATALOGUE = CATALOGUE_FILES[0]  # kept for messages that name the primary file
SHAPES = ROOT / "plugins" / "design-flow" / "catalog" / "component-shapes.json"   # the neutral design home (#2272); it sat in rails-stack's skill
THEME = ROOT / "plugins" / "design-flow" / "brands" / "fidara" / "theme.css"

# The declared vocabulary for a shape entry. These began as the kinds `pen_library.part_node` could
# draw; with pen retired (#766) nothing generates from them, but they stay enforced as a schema so a
# typo in the sidecar is refused rather than silently carried. There is no longer a second list to
# reconcile against, so the selftest no longer asserts one — see the note where that check was.
PART_KINDS = {"box", "pill", "text", "field", "line", "avatar", "icon-slot", "column"}
SHAPE_KINDS = {"control", "pill", "banner", "surface", "panel", "bar", "bare"}


AXES_MARK = "<!-- axes -->"
AXES = ("variants", "sizes")


def axes_line(entry: dict) -> str | None:
    """The `Catalog axes` line a components.md section carries for `entry`, or None when it states no list. Generated, never hand-edited (#2272)."""
    parts = [f"{axis} " + " · ".join(f"`{n}`" for n in entry[axis]) for axis in AXES if isinstance(entry.get(axis), list)]
    if not parts:
        return None
    return f"- **Catalog axes** (generated from the catalog's `component-shapes.json`, do not edit): {'; '.join(parts)}. {AXES_MARK}"


def sections(md: str) -> dict[str, str]:
    """Each `## ` section's text, keyed by its heading (the row name)."""
    return {block.split("\n", 1)[0].strip(): block for block in re.split(r"^## ", md, flags=re.M)[1:]}


def axis_problems(name: str, entry: dict, section: str | None) -> list[str]:
    """What is wrong with one drawable entry's `variants` and `sizes`, and with its generated line in the prose (#2272)."""
    found: list[str] = []
    for axis in AXES:
        value = entry.get(axis)
        if axis not in entry:
            found.append(f"`{name}` declares no `{axis}`: a list of names, or {{\"none\": \"reason\"}}. Silence is not an answer, because it is indistinguishable from an oversight.")
        elif isinstance(value, list):
            if not value or not all(isinstance(n, str) and n.strip() for n in value) or len(set(value)) != len(value):
                found.append(f"`{name}` `{axis}` must be a non-empty list of distinct non-empty names, got {value!r}")
        elif not (isinstance(value, dict) and set(value) == {"none"} and isinstance(value["none"], str) and value["none"].strip()):
            found.append(f"`{name}` `{axis}` must be a list of names or {{\"none\": \"reason\"}}, got {value!r}")
    if found or section is None:
        return found
    marked = [line for line in section.split("\n") if line.rstrip().endswith(AXES_MARK)]
    want = axes_line(entry)
    if want is None and marked:
        found.append(f"`{name}` states no list but its components.md section carries a generated `Catalog axes` line: regenerate (`python3 scripts/build_component_axes.py`)")
    elif want is not None and marked != [want]:
        found.append(f"`{name}`'s generated `Catalog axes` line in components.md is missing, duplicated or differs from the catalog: regenerate (`python3 scripts/build_component_axes.py`), never edit it by hand")
    prose = "\n".join(line for line in section.split("\n") if not line.rstrip().endswith(AXES_MARK))
    for axis in AXES:
        for word in entry.get(axis) if isinstance(entry.get(axis), list) else []:
            if not re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", prose, re.I):
                found.append(f"`{name}` declares {axis[:-1]} `{word}`, which its components.md section never mentions: a name in the catalog the prose cannot explain")
    return found


def catalogue_rows(md: str) -> list[str]:
    """Every `## ` row that is a component, not a doctrine section."""
    rows = [block.split("\n", 1)[0].strip() for block in re.split(r"^## ", md, flags=re.M)[1:]]
    return [r for r in rows if not r.startswith("The ")]


def declared_roles(css: str) -> set[str]:
    body = re.search(r"^:root\s*\{(.*?)^\}", css, re.S | re.M)
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", body.group(1))) if body else set()


def check(md: str, shapes: dict, roles: set[str]) -> list[str]:
    rows = catalogue_rows(md)
    entries = {k: v for k, v in shapes.items() if not k.startswith("_")}
    problems: list[str] = []

    # ONE CAUSE, ONE FINDING. If *nothing* is covered the sidecar is empty or unwritten — reporting
    # that as 51 identical "no shape entry" lines buries the diagnosis under its own consequences,
    # and anything reading the tail of the output learns the least useful of them. Same defect the
    # mutation harness had: N findings where there is one, with the real one first.
    missing = [row for row in rows if row not in entries]
    if rows and len(missing) == len(rows):
        problems.append(
            f"the shapes file covers none of the {len(rows)} catalogue rows — it is empty, "
            f"unwritten, or keyed differently. Fix that before reading anything below; every row "
            f"would otherwise be reported separately for the same single reason.")
    else:
        for row in missing:
            problems.append(
                f"`{row}` is in components.md with no shape entry. Every row must be drawn or "
                f"marked `drawable: false` with a reason — a component missing from the pen library "
                f"is one an agent composing a screen will never reach for, and never miss.")
    # THE SAME RULE IN THE OTHER DIRECTION. A sidecar keyed differently — slugs instead of row
    # names, say — makes every entry an orphan AND every row uncovered, which is one mistake
    # reported 102 times. The test is whether ONE action fixes all of them: it does here, so it is
    # one finding. Where each item needs its own fix (a row missing its `why`), N findings is right.
    orphans = [name for name in entries if name not in rows]
    if entries and len(orphans) == len(entries):
        problems.append(
            f"none of the {len(entries)} shape entries names a catalogue row — the file is keyed "
            f"differently from components.md (its keys must be the `## ` headings verbatim). One "
            f"mistake; everything else here follows from it.")
    else:
        for name in orphans:
            problems.append(
                f"`{name}` has a shape but is not a components.md row. A component offered in pen "
                f"that `rails-ui-composer` cannot build is the drift this mirror exists to prevent.")

    by_heading = sections(md)
    for name, entry in entries.items():
        if entry.get("drawable") is False:
            if not str(entry.get("why", "")).strip():
                problems.append(f"`{name}` is marked non-drawable with no `why`. The reason is the "
                                f"whole value: without it nobody can tell a decision from a gap.")
            continue
        problems += axis_problems(name, entry, by_heading.get(name))
        shape = entry.get("shape")
        if shape not in SHAPE_KINDS:
            problems.append(f"`{name}` declares shape {shape!r}, which is not one of "
                            f"{', '.join(sorted(SHAPE_KINDS))}")
        parts = entry.get("parts") or []
        if not parts:
            problems.append(f"`{name}` is drawable but declares no parts — it would render as an "
                            f"empty box, which is a placeholder wearing a component's name.")
        for part in walk_parts(parts):
            if part.get("kind") not in PART_KINDS:
                problems.append(f"`{name}` uses part kind {part.get('kind')!r}, which the generator "
                                f"does not draw")
            for key in ("fill", "color", "stroke"):
                role = part.get(key)
                if role and f"--{role}" not in roles:
                    problems.append(f"`{name}` names role `--{role}` for its {key}, which the "
                                    f"reference pack does not declare — it would be silently left "
                                    f"out of the library")
    return problems


def walk_parts(parts: list) -> list[dict]:
    out = []
    for part in parts:
        out.append(part)
        out.extend(walk_parts(part.get("of") or []))
    return out


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    try:
        md = "\n".join(p.read_text(encoding="utf-8") for p in CATALOGUE_FILES)
        shapes = json.loads(SHAPES.read_text(encoding="utf-8"))
        roles = declared_roles(THEME.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read the inputs: {exc}", file=sys.stderr)
        return 2
    problems = check(md, shapes, roles)
    for p in problems:
        print(f"- {p}")
    rows = len(catalogue_rows(md))
    print(f"\n{rows} catalogue row(s) reconciled against "
          f"{len([k for k in shapes if not k.startswith('_')])} shape(s)."
          if not problems else f"\n{len(problems)} finding(s).")
    return 1 if problems else 0


def selftest() -> int:
    checks, failures = 0, []

    def expect(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    ROLES = {"--primary", "--foreground", "--card", "--border"}
    MD = "## Button\n- stuff\n\n## Card\n- stuff\n\n## The focus ring\n- doctrine\n"
    NONE = {"none": "a slot layout, not a variant enum"}
    OK = {"Button": {"variants": NONE, "sizes": NONE, "shape": "control", "parts": [{"kind": "text", "color": "foreground"}]},
          "Card": {"variants": NONE, "sizes": NONE, "shape": "surface", "parts": [{"kind": "box", "fill": "card"}]}}
    expect("a reconciled pair has no findings", check(MD, OK, ROLES) == [])
    expect("...and doctrine sections are not treated as components",
           "The focus ring" not in str(check(MD, OK, ROLES)))

    # THE FAILURE THAT MATTERS MOST: a row with no shape simply vanishes from pen.
    expect("a row with no shape is reported",
           any("no shape entry" in p for p in check(MD, {"Button": OK["Button"]}, ROLES)))
    # ONE CAUSE, ONE FINDING. An empty sidecar is a single problem; reporting it once per row buries
    # the diagnosis under its own consequences, and a reader inspecting the tail learns the least
    # useful of them.
    empty = check(MD, {}, ROLES)
    expect(f"an empty sidecar is ONE finding, not one per row (got {len(empty)})", len(empty) == 1)
    expect("...and it names the systemic cause",
           bool(empty) and "covers none of the" in empty[0] and "before reading anything below" in empty[0])
    # ...while a PARTIAL gap is genuinely per-row, because each row is then a separate decision.
    partial = check(MD, {"Button": OK["Button"]}, ROLES)
    expect("a partial gap stays per-row", len(partial) == 1 and "`Card`" in partial[0])
    expect("a shape with no row is reported",
           any("not a components.md row" in p
               for p in check(MD, {**OK, "Ghost": OK["Card"]}, ROLES)))
    # THE SAME RULE, OTHER DIRECTION: a wrongly-keyed file is ONE mistake, not 2N.
    wrong = {"button": OK["Button"], "card": OK["Card"]}
    miskeyed = check(MD, wrong, ROLES)
    expect(f"a wrongly-keyed file is 2 findings, not 2N (got {len(miskeyed)})", len(miskeyed) == 2)
    expect("...and one of them names the keying itself",
           any("keyed differently" in p for p in miskeyed))
    # `drawable: false` is a DECISION; without a reason it is indistinguishable from an oversight.
    expect("non-drawable without a reason is reported",
           any("no `why`" in p for p in check(MD, {**OK, "Card": {"drawable": False}}, ROLES)))
    expect("...and with one is accepted",
           check(MD, {**OK, "Card": {"drawable": False, "why": "a chapter"}}, ROLES) == [])
    expect("an unknown shape kind is reported",
           any("not one of" in p
               for p in check(MD, {**OK, "Card": {"variants": NONE, "sizes": NONE, "shape": "blob", "parts": [{"kind": "box"}]}},
                              ROLES)))
    expect("an unknown part kind is reported",
           any("does not draw" in p
               for p in check(MD, {**OK, "Card": {"variants": NONE, "sizes": NONE, "shape": "surface",
                                                  "parts": [{"kind": "hologram"}]}}, ROLES)))
    # A role the pack does not declare would be silently dropped at generation time.
    expect("an undeclared role is reported",
           any("does not declare" in p
               for p in check(MD, {**OK, "Card": {"variants": NONE, "sizes": NONE, "shape": "surface",
                                                  "parts": [{"kind": "box", "fill": "nope"}]}},
                              ROLES)))
    expect("a drawable entry with no parts is reported",
           any("no parts" in p for p in check(MD, {**OK, "Card": {"variants": NONE, "sizes": NONE, "shape": "surface"}}, ROLES)))
    # Nested parts are checked too — a column's children are as capable of naming a bad role.
    expect("a nested part is checked",
           any("does not declare" in p
               for p in check(MD, {**OK, "Card": {"variants": NONE, "sizes": NONE, "shape": "surface", "parts": [
                   {"kind": "column", "of": [{"kind": "box", "fill": "nope"}]}]}}, ROLES)))

    # THE DUPLICATED KIND LISTS used to be reconciled against `pen_library.py`, the generator that
    # owned them. That generator is gone (#766) and the lists are now a schema with a single owner --
    # this file -- so there is nothing left to disagree with. Deleted rather than pointed at a new
    # file: a reconciliation with one side is not a check, and leaving it would be a gate that
    # cannot fail. The kinds are still enforced against the sidecar itself, above.

    # VARIANTS AND SIZES (#2272): one structured source, declared for every drawable entry, and the prose line derived from it.
    BTN = {**OK["Button"], "variants": ["primary", "ghost"], "sizes": ["sm", "md"]}
    LINE = axes_line(BTN)
    AMD = "## Button\n" + LINE + "\n- Variants are `primary` and `ghost`; sizes sm and md.\n\n## Card\n- stuff\n"
    expect("a list-bearing entry with its generated line and its names in the prose is clean", check(AMD, {"Button": BTN, "Card": OK["Card"]}, ROLES) == [])
    def axes_findings(entry, md=AMD):
        return " ".join(check(md, {"Button": entry, "Card": OK["Card"]}, ROLES))
    expect("an entry with no `variants` is reported", "declares no `variants`" in axes_findings({k: v for k, v in BTN.items() if k != "variants"}))
    expect("an entry with no `sizes` is reported", "declares no `sizes`" in axes_findings({k: v for k, v in BTN.items() if k != "sizes"}))
    expect("the old `\"enum\"` placeholder is reported", "must be a list of names or" in axes_findings({**BTN, "variants": "enum"}))
    expect("an empty list is reported", "non-empty list" in axes_findings({**BTN, "variants": []}))
    expect("a duplicated name is reported", "distinct" in axes_findings({**BTN, "sizes": ["sm", "sm"]}))
    expect("a `none` with no reason is reported", "must be a list of names or" in axes_findings({**BTN, "sizes": {"none": " "}}))
    expect("a `none` with another key is reported", "must be a list of names or" in axes_findings({**BTN, "sizes": {"none": "r", "extra": 1}}))
    expect("a non-drawable entry needs no variants or sizes", check(MD, {**OK, "Card": {"drawable": False, "why": "a rule"}}, ROLES) == [])
    expect("a missing generated line is reported", "missing, duplicated or differs" in axes_findings(BTN, AMD.replace(LINE + "\n", "")))
    expect("a hand-edited generated line is reported", "missing, duplicated or differs" in axes_findings(BTN, AMD.replace("`ghost`", "`GHOST`")))
    expect("a duplicated generated line is reported", "missing, duplicated or differs" in axes_findings(BTN, AMD.replace(LINE + "\n", LINE + "\n" + LINE + "\n")))
    expect("a generated line for an entry that states no list is reported", "carries a generated" in axes_findings(OK["Button"]))
    expect("a name the prose never mentions is reported (the generated line does not count)", "never mentions" in axes_findings({**BTN, "variants": ["primary", "ghost", "outline"], "sizes": ["sm", "md"]},
                                                                                                                              AMD.replace(LINE, axes_line({**BTN, "variants": ["primary", "ghost", "outline"]}))))
    expect("`axes_line` states lists only", axes_line(OK["Button"]) is None and "sizes `sm` · `md`" in LINE)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} shape-reconciliation assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
