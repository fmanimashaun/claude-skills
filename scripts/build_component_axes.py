#!/usr/bin/env python3
"""Write each component's `Catalog axes` line into components.md from `component-shapes.json`, and check it (#2272).

Run:  python3 scripts/build_component_axes.py            # rewrite the generated lines in the two catalogue files
      python3 scripts/build_component_axes.py --check    # fail when the committed (HEAD) files differ from a clean build
      python3 scripts/build_component_axes.py --selftest

WHY. The variants and sizes of a component used to exist only as prose, so nothing could ask which a component takes, and a prose line could say one thing
while the code or the next reader assumed another. `plugins/design-flow/catalog/component-shapes.json` is now the ONE source (a list of names, or an
explicit `{"none": reason}`); the line in each components.md section that states the lists is DERIVED from it, never hand-edited, the `derived-artifacts`
pattern: go to the structured source, never regex-parse the prose. A line is marked `<!-- axes -->`, sits right under its section's heading, and exists
only for an entry that states at least one list. `scripts/check_component_shapes.py` refuses a missing, duplicated or edited line.

`--check` compares the blob at HEAD, never the file on disk, so a rebuild that was never committed fails honestly (the rule every generated surface here follows).

Exit codes:  0 built or clean · 1 stale · 2 unreadable input
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_component_shapes as ccs  # noqa: E402  (the one place the line's text is defined)
import rails_assumptions as ra  # noqa: E402  (committed_blob: the blob at HEAD)

ROOT = ccs.ROOT


def build(md: str, shapes: dict) -> str:
    """`md` with every section's `Catalog axes` line made to match its entry: removed where the entry states no list, written right under the heading
    where it does. Everything else is carried through byte for byte."""
    chunks = re.split(r"(?m)^(?=## )", md)
    out: list[str] = []
    for chunk in chunks:
        if not chunk.startswith("## "):
            out.append(chunk)
            continue
        lines = chunk.split("\n")
        heading = lines[0][3:].strip()
        entry = shapes.get(heading)
        if isinstance(entry, dict) and entry.get("drawable") is not False:
            lines = [lines[0]] + [ln for ln in lines[1:] if not ln.rstrip().endswith(ccs.AXES_MARK)]
            want = ccs.axes_line(entry)
            if want:
                lines.insert(1, want)
        out.append("\n".join(lines))
    return "".join(out)


def files(root: Path) -> list[Path]:
    return [root / p.relative_to(ccs.ROOT) for p in ccs.CATALOGUE_FILES]


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    try:
        shapes = json.loads(ccs.SHAPES.read_text(encoding="utf-8"))
        texts = {p: p.read_text(encoding="utf-8") for p in ccs.CATALOGUE_FILES}
    except (OSError, ValueError) as exc:
        print(f"cannot read the inputs: {exc}", file=sys.stderr)
        return 2
    built = {p: build(t, shapes) for p, t in texts.items()}
    if "--check" in argv:
        stale = []
        for p, text in built.items():
            rel = p.relative_to(ROOT).as_posix()
            blob = ra.committed_blob(rel, ROOT)
            if blob is None:
                stale.append(f"{rel} is not committed: rebuild, `git add` and COMMIT")
            elif blob != text:
                stale.append(f"{rel} does not match a clean build of its `Catalog axes` lines: run `python3 scripts/build_component_axes.py`, `git add` and COMMIT "
                             "(this check reads the blob at HEAD, so staging alone leaves it red)")
        for line in stale:
            print(line, file=sys.stderr)
        if not stale:
            print("clean: the Catalog axes lines match the catalog")
        return 1 if stale else 0
    changed = [p for p, text in built.items() if text != texts[p]]
    for p in changed:
        p.write_text(built[p], encoding="utf-8")
    print(f"wrote the Catalog axes lines: {len(changed)} file(s) changed. `git add` them AND COMMIT; the drift gate compares the blob at HEAD.")
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def expect(label: str, ok: bool) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(label)

    md = "# Catalog\n\nintro\n\n## Button\n- **Variants:** `a` · `b`. hand prose stays.\n\n## Card\n- slot layout\n\n## Note\n- no entry\n"
    shapes = {"Button": {"variants": ["primary", "ghost"], "sizes": {"none": "x"}}, "Card": {"variants": {"none": "r"}, "sizes": {"none": "r"}}}
    once = build(md, shapes)
    line = ccs.axes_line(shapes["Button"])
    expect("a section with a stated list gets its line right under the heading", "## Button\n" + line + "\n- **Variants:**" in once)
    expect("the line names the list and ends with the marker", "variants `primary` · `ghost`" in line and line.endswith(ccs.AXES_MARK))
    expect("a section whose entry states no list gets no line", once.count(ccs.AXES_MARK) == 1)
    expect("everything else is carried through byte for byte", once.replace(line + "\n", "") == md)
    expect("building twice changes nothing", build(once, shapes) == once)
    shapes["Button"]["variants"] = ["primary", "ghost", "link"]
    twice = build(once, shapes)
    expect("a changed list replaces its line, never adds a second", twice.count(ccs.AXES_MARK) == 1 and "`link`" in twice)
    shapes["Button"]["variants"] = {"none": "now none"}
    expect("an entry that no longer states a list loses its line", ccs.AXES_MARK not in build(twice, shapes))
    hand = once.replace(line, line.replace("primary", "PRIMARY"))
    expect("a hand-edited line is overwritten by a rebuild", build(hand, {"Button": {"variants": ["primary", "ghost"], "sizes": {"none": "x"}}}) == once)
    expect("a non-drawable entry is left alone", build(md, {"Button": {"drawable": False, "why": "w"}}) == md)
    expect("an empty catalogue builds the file unchanged", build(md, {}) == md)
    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} axes-line assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
