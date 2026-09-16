#!/usr/bin/env python3
"""Hold the structural tokens on the 8px grid (#976).

Run:  python3 scripts/check_structural_grid.py            # read the shipped block, fail on a finding
      python3 scripts/check_structural_grid.py --selftest  # prove every rule fires AND stays silent

WHY. #976 proposed anchoring every spatial figure to a strict 8px grid (it attributed the proposal
to a design manual that the maintainer confirmed does not exist; the proposal stands on its merits);
the shipped scale is fluid `clamp()` values that are on no grid by design. #976 settled it
by SPLITTING BY AXIS: structure (shell header, rails, sticky toolbar, table row heights, the
selection column, drawer bounds) is fixed and divisible by 8; rhythm (`--space-*`, type) stays
fluid. `foundations-tokens.md` -> *3b. Structure snaps to the 8px grid* states that, and a rule
stated in prose is the `claims-vs-enforcement` class the `code-review` skill exists for. This is
the enforcement half: the structural tokens live in ONE marked block, and this refuses a value
there that is not a whole multiple of 8px.

Downstream evidence that the rule is real: a consuming app's rail was 236px, which satisfies the
fluid doctrine and fails this check.

Same shape as `check_page_pacing.py` and `check_shared_shapes.py`: it refuses only a **value in
shipped doctrine disagreeing with the rule written beside it**. It is not a design gate -- nothing
here judges whether 288 is a good rail width; it judges whether the block obeys the rule the
section states, and whether every structural token the references reach for exists.

THE FIVE RULES, and each is a measurement:

  off-grid         a token in the block is not a whole multiple of 8px (rem x 16, or px)
  fluid-structure  a token in the block is not a fixed length -- clamp(), vw, %, calc() -- when
                   the section's whole point is that structure is fixed
  undeclared       a design-system reference uses a token carrying one of the block's prefixes
                   (`--shell-`, `--row-`, ...) that the block does not declare -- the #750 class,
                   a doctrine that names a step the file does not define
  empty-block      the markers are present and declare nothing (a fence moved out from between them)
  no-block         the markers are missing

Exit codes:  0 the block obeys the rule * 1 it does not * 2 a file could not be read or parsed

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFS = REPO / "skills" / "design-system" / "references"
TOKENS = REFS / "foundations-tokens.md"

BEGIN = "<!-- structural-grid:begin -->"
END = "<!-- structural-grid:end -->"
GRID_PX = 8

_DECL = re.compile(r"^\s*(--[a-z][a-z0-9-]*)\s*:\s*([^;]+);", re.M)
_LENGTH = re.compile(r"^\s*(\d+(?:\.\d+)?)(rem|px)\s*$")


class ParseError(Exception):
    pass


def block_of(text: str) -> str:
    """The text between the markers, or ParseError when either marker is missing."""
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ParseError(f"no-block: {BEGIN} … {END} not found, or out of order")
    return text[start + len(BEGIN):end]


def declarations(block: str) -> dict[str, str]:
    """`--name: value` pairs declared in the block, in order."""
    return {m.group(1): m.group(2).strip() for m in _DECL.finditer(block)}


def px_of(value: str) -> float | None:
    """A fixed length in px, or None when the value is not a fixed rem/px length."""
    m = _LENGTH.match(value)
    if not m:
        return None
    number, unit = float(m.group(1)), m.group(2)
    return number * 16 if unit == "rem" else number


def prefixes_of(names) -> set[str]:
    """`--shell-header` -> `--shell`. The first segment is the family; a use of any `--shell-…`
    token is checked against the block."""
    return {"--" + n[2:].split("-", 1)[0] for n in names}


def uses_in(text: str, prefixes: set[str]) -> set[str]:
    if not prefixes:
        return set()
    alt = "|".join(re.escape(p[2:]) for p in sorted(prefixes))
    return set(re.findall(rf"--(?:{alt})-[a-z0-9]+(?:-[a-z0-9]+)*", text))


def check(tokens_text: str, references: dict[str, str]) -> list[str]:
    """Findings for one tokens file and the references that may use its tokens.

    `references` maps a display path to its text and SHOULD include the tokens file itself, so a
    token named in that file's prose outside the block is checked too.
    """
    try:
        block = block_of(tokens_text)
    except ParseError as e:
        return [str(e)]
    tokens = declarations(block)
    findings: list[str] = []
    if not tokens:
        findings.append(f"empty-block: nothing is declared between {BEGIN} and {END}")
        return findings
    for name, value in tokens.items():
        px = px_of(value)
        if px is None:
            findings.append(
                f"fluid-structure: {name}: {value} — structure is a fixed rem or px length; a fluid "
                f"value belongs in --space-*, not in this block")
            continue
        if px % GRID_PX:
            nearest = sorted((round(px / GRID_PX) * GRID_PX, (round(px / GRID_PX) + 1) * GRID_PX))
            findings.append(
                f"off-grid: {name}: {value} = {px:g}px is not a multiple of {GRID_PX}px "
                f"(nearest {nearest[0]:g} or {nearest[1]:g})")
    prefixes = prefixes_of(tokens)
    for path, text in sorted(references.items()):
        outside = text.replace(block, "") if path.endswith("foundations-tokens.md") else text
        for name in sorted(uses_in(outside, prefixes) - set(tokens)):
            findings.append(
                f"undeclared: {path} uses {name}, which the structural block does not declare — the "
                f"#750 class: doctrine naming a token the file does not define")
    return findings


def load_references(refs_dir: Path) -> dict[str, str]:
    return {p.relative_to(refs_dir.parent.parent.parent).as_posix() if refs_dir.is_relative_to(REPO)
            else p.name: p.read_text(encoding="utf-8")
            for p in sorted(refs_dir.glob("*.md"))}


def run(tokens: Path = TOKENS, refs_dir: Path = REFS) -> int:
    try:
        text = tokens.read_text(encoding="utf-8")
        references = load_references(refs_dir)
    except OSError as e:
        print(f"check_structural_grid: cannot read: {e}", file=sys.stderr)
        return 2
    findings = check(text, references)
    if findings:
        print(f"check_structural_grid: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    declared = declarations(block_of(text))
    print(f"check_structural_grid: ok — {len(declared)} structural token(s), every one a multiple of "
          f"{GRID_PX}px; no undeclared use across {len(references)} reference file(s)")
    return 0


# ---------------------------------------------------------------------------------------------
# Selftest -- every rule fires on the input it exists for, and the clean case is silent.
# ---------------------------------------------------------------------------------------------

_CLEAN_BLOCK = f"""
## 3b. Structure

{BEGIN}
```css
@theme {{
  --shell-header: 4rem;      /* 64px */
  --shell-rail: 18rem;       /* 288px */
  --row-compact: 32px;
}}
```
{END}

Prose may name `--shell-rail` again; it is declared, so that is fine.
"""


def selftest() -> int:
    failures: list[str] = []

    def expect(label: str, findings: list[str], *, fires: str | None):
        if fires is None:
            if findings:
                failures.append(f"{label}: expected silence, got {findings}")
        elif not any(f.startswith(fires) for f in findings):
            failures.append(f"{label}: expected a `{fires}` finding, got {findings}")

    refs = {"foundations-tokens.md": _CLEAN_BLOCK, "components.md": "uses h-(--shell-header) here"}
    expect("clean block is silent", check(_CLEAN_BLOCK, refs), fires=None)

    off = _CLEAN_BLOCK.replace("--shell-rail: 18rem;", "--shell-rail: 14.75rem;")  # 236px
    expect("236px rail", check(off, {"foundations-tokens.md": off}), fires="off-grid")

    off_px = _CLEAN_BLOCK.replace("--row-compact: 32px;", "--row-compact: 36px;")
    expect("36px row in px", check(off_px, {"foundations-tokens.md": off_px}), fires="off-grid")

    fluid = _CLEAN_BLOCK.replace("--shell-rail: 18rem;", "--shell-rail: clamp(16rem, 15rem + 2vw, 18rem);")
    expect("clamp in the block", check(fluid, {"foundations-tokens.md": fluid}), fires="fluid-structure")

    undeclared = dict(refs)
    undeclared["page-anatomies.md"] = "the bar is top-(--shell-toolbar) tall"
    expect("undeclared --shell-toolbar", check(_CLEAN_BLOCK, undeclared), fires="undeclared")

    # A token from a family the block does not own is not this check's business.
    foreign = dict(refs)
    foreign["motion.md"] = "duration-(--duration-fast) and var(--space-s)"
    expect("foreign families are ignored", check(_CLEAN_BLOCK, foreign), fires=None)

    # A wildcard mention (`--shell-*`) is prose, not a use.
    wildcard = dict(refs)
    wildcard["responsive.md"] = "reach for a `--shell-*` token"
    expect("wildcard mention is not a use", check(_CLEAN_BLOCK, wildcard), fires=None)

    empty = f"{BEGIN}\n```css\n@theme {{\n}}\n```\n{END}\n"
    expect("empty block", check(empty, {"foundations-tokens.md": empty}), fires="empty-block")

    expect("missing markers", check("## no markers here\n", {}), fires="no-block")

    # The file-system path: a staged tempdir with a clean pair returns 0 and a broken one returns 1.
    with tempfile.TemporaryDirectory() as d:
        refs_dir = Path(d) / "skills" / "design-system" / "references"
        refs_dir.mkdir(parents=True)
        tokens = refs_dir / "foundations-tokens.md"
        tokens.write_text(_CLEAN_BLOCK, encoding="utf-8")
        if run(tokens, refs_dir) != 0:
            failures.append("run(): clean tempdir did not exit 0")
        (refs_dir / "components.md").write_text("w-(--shell-nope)", encoding="utf-8")
        if run(tokens, refs_dir) != 1:
            failures.append("run(): undeclared use in tempdir did not exit 1")
        if run(Path(d) / "absent.md", refs_dir) != 2:
            failures.append("run(): unreadable tokens file did not exit 2")

    if failures:
        print("check_structural_grid selftest: FAIL")
        for f in failures:
            print(f"  {f}")
        return 1
    print("check_structural_grid selftest: ok — 5 rules fire on their input, 3 clean cases are silent, "
          "exit codes 0/1/2 proven")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = parser.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
