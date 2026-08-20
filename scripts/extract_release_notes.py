#!/usr/bin/env python3
"""Extract the release notes for a tag from CHANGELOG.md — EVERY block, not just the first.

Run:  python3 scripts/extract_release_notes.py                      # notes for marketplace.json's version
      python3 scripts/extract_release_notes.py --tag v1.92.0         # for a specific tag
      python3 scripts/extract_release_notes.py --check                # gate: notes exist and are complete
      python3 scripts/extract_release_notes.py --selftest             # prove the parser, both directions

WHY THIS EXISTS (#699). `release.yml` and `release_local.sh` each carried this awk:

    /^### / && index($0, needle) { grab=1; next }
    grab && /^### / { exit }
    grab { print }

`exit` — not "stop grabbing". So it published the FIRST `### … (release vX.Y.Z)` block and stopped.
But this CHANGELOG has **one block per component**, because CLAUDE.md requires components to version
independently, so any promotion bumping two components has two blocks carrying the same tag and the
second one's notes were silently discarded.

It had already shipped four times when it was found — v1.87.0, v1.88.0, v1.89.0, v1.91.2. Measured
against what GitHub actually published, v1.91.2's release body contains only the rails-flow block;
the pipeline block (#682, a deploy briefing that booted local dev config in production) never
appeared. v1.92.0, armed and waiting, would have dropped 130 of its 206 note lines — five of nine
bullets, including a fix for five shipped ERB examples building HTML attributes by string
interpolation, one through `.html_safe`.

It went unseen because **the release succeeds either way.** The body is just shorter, and nobody
diffs a release body against the CHANGELOG. That is claims-vs-enforcement inside our own release
machinery, against a rule CLAUDE.md states outright and nothing checked.

WHY ONE SCRIPT AND NOT TWO FIXED AWKS. The awk was duplicated verbatim in a workflow and a shell
script, and CLAUDE.md had to *ask* maintainers to keep them in step — the same unenforced claim as
the bug. One implementation, called by both, plus a `lint_self_consistency` rule that fails if either
call site grows its own extractor again. Fixing the duplication is part of fixing the bug, not tidying
afterwards.

WHAT IS PRESERVED FROM THE AWK, deliberately:

  * **The `/^### /` anchor.** The needle must match a HEADING, never a line that merely mentions the
    tag. Prose referencing "(release vX.Y.Z)" would otherwise start the grab early and leak the
    preceding section's bullets into this release's notes. That was a real failure, not a
    hypothesis, and there is a selftest fixture for it.
  * **The bare-pointer fallback** when no block matches, so a release never publishes an empty body.

WHAT CHANGED BESIDES "all blocks": each block's heading is now printed, minus the `(release …)`
bookkeeping. A multi-component release has to say which component version a note belongs to, and the
old output — headings stripped, bullets concatenated — could not. Single-block releases gain one
heading line, which is strictly more informative and needs no special case.

Exit codes:  0 = ok · 1 = --check found a problem · 2 = not this repo

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHANGELOG = "CHANGELOG.md"
MANIFEST = ".claude-plugin/marketplace.json"

# A heading is `### ` at column 0. Anything else mentioning the needle is prose.
HEADING = re.compile(r"^### ")


def current_tag(root: Path = REPO) -> str:
    """The tag the release workflow will build: `v` + `metadata.version`."""
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    return "v" + data["metadata"]["version"]


def blocks_for(text: str, tag: str) -> list[tuple[str, list[str]]]:
    """Every (heading, body-lines) whose HEADING contains `(release <tag>)`.

    A block runs to the next `### ` heading, matching or not. The old awk `exit`ed there instead,
    which is the entire bug: it ended the whole extraction rather than that one block.
    """
    needle = f"(release {tag})"
    lines = text.split("\n")
    out: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    heading = ""
    for line in lines:
        if HEADING.match(line):
            if current is not None:
                out.append((heading, current))
                current = None
            if needle in line:
                # Strip the bookkeeping suffix; keep the component/version/date prefix.
                heading = line[:line.index(needle)].rstrip().rstrip("—-").rstrip()
                current = []
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        out.append((heading, current))
    return out


def render(text: str, tag: str) -> tuple[str, int]:
    """(notes, block-count). Falls back to a bare pointer so a release is never published empty."""
    found = blocks_for(text, tag)
    if not found:
        return f"Marketplace {tag}. See CHANGELOG.md for details.\n", 0
    parts = []
    for heading, body in found:
        parts.append(heading)
        parts.append("\n".join(body).strip("\n"))
    return "\n".join(parts).strip("\n") + "\n", len(found)


def _check(text: str, tag: str) -> list[str]:
    """Findings. The gate's real question: would this release publish everything written for it?

    It runs the REAL extractor and compares the set of blocks it emitted against an independent scan
    of the file — not a count against a count. Counting would catch the #699 instance and miss the
    next extractor bug: two blocks extracted could be the wrong two. Same reasoning as
    `check_asset_layout.py` running the real `scaffold()` instead of asserting a path string.
    """
    findings: list[str] = []
    needle = f"(release {tag})"

    # Independent scan: every heading that declares itself part of this release.
    declared = [line.rstrip() for line in text.split("\n")
                if HEADING.match(line) and needle in line]
    # What the extractor actually produced, keyed the same way.
    produced = render(text, tag)[0]
    extracted = blocks_for(text, tag)

    if not declared:
        findings.append(
            f"no `### … (release {tag})` heading in {CHANGELOG} — the release would publish a bare "
            f"pointer saying nothing about what shipped")
        return findings

    for line in declared:
        stem = line[:line.index(needle)].rstrip().rstrip("—-").rstrip()
        if stem not in produced:
            findings.append(
                f"block {line.strip()!r} is written for {tag} but would NOT publish — its notes are "
                f"lost, which is the #699 defect recurring")
    for heading, _body in extracted:
        if not any(heading in line for line in declared):
            findings.append(
                f"the extractor emitted {heading!r}, which no `{needle}` heading declares — it is "
                f"publishing something this release did not write")
    for heading, body in extracted:
        if not "\n".join(body).strip():
            findings.append(f"empty release block: {heading!r} for {tag}")
    return findings


# ---------------------------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------------------------

def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    one = """# CHANGELOG

## rails-flow

### 1.23.0 — 2026-08-20 (release v1.92.0)

- only bullet

### 1.22.3 — 2026-08-16 (release v1.91.2)

- older
"""
    notes, n = render(one, "v1.92.0")
    check("one block extracts", n == 1 and "only bullet" in notes)
    check("one block stops at the next heading", "older" not in notes)
    check("the heading is kept", "### 1.23.0 — 2026-08-20" in notes)
    check("the (release …) bookkeeping is stripped", "(release v1.92.0)" not in notes)
    check("one block is clean", _check(one, "v1.92.0") == [])

    # THE BUG. Two components, same tag, a non-matching heading between them.
    two = """# CHANGELOG

## rails-flow

### 1.23.0 — 2026-08-20 (release v1.92.0)

- first component

### 1.22.3 — 2026-08-16 (release v1.91.2)

- unrelated older release

## rails-stack

### 1.49.0 — 2026-08-20 (release v1.92.0)

- second component
"""
    notes, n = render(two, "v1.92.0")
    check("BOTH blocks extract", n == 2)
    check("first component's notes present", "first component" in notes)
    check("second component's notes present — the bug", "second component" in notes)
    check("the intervening older release is excluded", "unrelated older" not in notes)
    check("both headings present", notes.count("###") == 2)
    check("two blocks are clean", _check(two, "v1.92.0") == [])

    # The preserved anchor: prose mentioning the tag must NOT start a grab.
    prose = """# CHANGELOG

## Repository hygiene

### 2026-08-20 (v1.92.0)

- We warned about leaving a stray `(release v1.92.0)` heading around. Prose, not a heading.
- leaked bullet

### 1.23.0 — 2026-08-20 (release v1.92.0)

- the real notes
"""
    notes, n = render(prose, "v1.92.0")
    check("prose mentioning the tag does not start a grab", n == 1 and "leaked bullet" not in notes)
    check("the real block is still found after prose", "the real notes" in notes)

    missing = "# CHANGELOG\n\n## rails-flow\n\n### 1.0.0 — 2020-01-01 (release v1.0.0)\n\n- x\n"
    notes, n = render(missing, "v9.9.9")
    check("no block falls back to a pointer", n == 0 and "See CHANGELOG.md" in notes)
    check("no block is a CHECK finding", any("bare pointer" in f for f in _check(missing, "v9.9.9")))

    empty = "# CHANGELOG\n\n### 1.0.0 — 2020-01-01 (release v1.0.0)\n\n### 0.9.0 — 2019 (release v0.9.0)\n\n- y\n"
    check("an empty block is a finding", any("empty release block" in f
                                             for f in _check(empty, "v1.0.0")))

    # THE GATE'S TEETH. Simulate the old awk -- first block only -- and prove the check REFUSES it.
    # Without this the gate is the parser agreeing with itself, and would have passed the broken
    # version it exists to refuse.
    import builtins
    real_render = render
    def first_only(text, tag):
        found = blocks_for(text, tag)[:1]
        if not found:
            return f"Marketplace {tag}. See CHANGELOG.md for details.\n", 0
        h, b = found[0]
        return h + "\n" + "\n".join(b).strip("\n") + "\n", 1
    g = globals()
    g["render"] = first_only
    try:
        broken = _check(two, "v1.92.0")
    finally:
        g["render"] = real_render
    check("the check REFUSES the old first-block-only behaviour",
          any("would NOT publish" in f for f in broken))
    check("...and names the block that would be lost",
          any("1.49.0" in f for f in broken))
    check("the check passes again once the extractor is whole", _check(two, "v1.92.0") == [])

    # The needle carries the CLOSING PAREN, which is the only thing making the tag match exact
    # rather than prefix. A heading whose tag merely starts with ours must not be collected -- the
    # first version of this fixture tested v1.9.0 against v1.92.0 and proved nothing, because
    # `(release v1.9.0` does not occur in `(release v1.92.0)` either way. The property is
    # SUFFIXED tags, and it only fails when the paren is gone.
    pfx = """### 1.0.0 — d (release v1.92.0)

- the exact tag

### 0.9.9 — d (release v1.92.0-rc1)

- a tag that merely starts with ours
"""
    notes, n = render(pfx, "v1.92.0")
    check("a prefix tag does not match the longer one",
          n == 1 and "the exact tag" in notes and "merely starts with ours" not in notes)

    # Against the REAL repo: a selftest that only ever sees fixtures is the bug maintainer_doctor
    # was written about.
    text = (REPO / CHANGELOG).read_text(encoding="utf-8")
    tag = current_tag()
    real = _check(text, tag)
    check(f"the committed CHANGELOG publishes completely for {tag}", real == [])
    _, rn = render(text, tag)
    check("the real release has at least one block", rn >= 1)

    # And the call sites must actually USE this script -- the gate half lives in
    # lint_self_consistency, but assert the wiring here too so a stale call site fails fast.
    for rel in (".github/workflows/release.yml", "scripts/release_local.sh"):
        body = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel} calls extract_release_notes.py", "extract_release_notes.py" in body)
        check(f"{rel} has no inline extractor", "grab && /^### /" not in body)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", help="tag to extract (default: v + marketplace.json metadata.version)")
    ap.add_argument("--check", action="store_true",
                    help="gate: every block written for the tag would publish")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if not (REPO / MANIFEST).is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    if a.selftest:
        return _selftest()

    text = (REPO / CHANGELOG).read_text(encoding="utf-8")
    tag = a.tag or current_tag()

    if a.check:
        findings = _check(text, tag)
        if findings:
            print(f"{len(findings)} finding(s) for {tag}:", file=sys.stderr)
            for f in findings:
                print(f"  {f}", file=sys.stderr)
            return 1
        _, n = render(text, tag)
        print(f"clean — {n} block(s) for {tag} would publish")
        return 0

    notes, _ = render(text, tag)
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
