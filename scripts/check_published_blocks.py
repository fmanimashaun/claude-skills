#!/usr/bin/env python3
"""A published release block must still say what it said at its tag (#1096).

Run:  python3 scripts/check_published_blocks.py
      python3 scripts/check_published_blocks.py --update   # re-baseline additions, deliberately
      python3 scripts/check_published_blocks.py --selftest

WHY THIS EXISTS. `feature/1085-context-budget` was rebased onto `dev` minutes after the v1.134.0
promotion merged. The rebase applied **cleanly, with no conflict**, and placed its CHANGELOG bullets
INSIDE the `### 2026-09-21 (release v1.134.0)` block that had just published. Resolving the
resulting duplicate by hand then deleted the WRONG bullet -- a real v1.133.0 note, published weeks
earlier, vanished from the file. Nothing noticed.

THE MECHANISM IS ORDINARY, WHICH IS WHY IT WILL RECUR. Before an arm, a branch's notes sit under
`### Unreleased`. The arm RENAMES that heading to `### <date> (release vX.Y.Z)`. A branch cut before
the arm still carries `### Unreleased`; rebased onto the armed `dev` it finds no such heading and
git places the bullets at the nearest matching context -- the top of the renamed block. **Every
branch in flight across a promotion is exposed, and the cleaner the rebase the less likely anyone
looks.**

WHY THE EXISTING GATE CANNOT SEE IT. `extract_release_notes.py --check` validates that a heading
names a real tag, has the publishing shape and is ordered. All true here. It has no way to know
whether a bullet UNDERNEATH a shipped heading was present when that tag was cut. The full sweep
passed -- 111 gates, 0 failed -- because no gate asked.

TWO RULES, AND THEY ARE DELIBERATELY DIFFERENT INSTRUMENTS.

  1. **A LOSS IS ABSOLUTE.** A bullet that was in the block at its tag and is gone now is
     destruction of published history, and there is no legitimate reason for it. Measured when this
     was written: **0** across 176 tagged blocks, once the v1.133.0 note was restored. So this rule
     is green today and stays green, which is exactly what makes it worth gating.

  2. **AN ADDITION IS RATCHETED.** 22 blocks already carry bullets their tag did not, from long
     before anyone was watching. An absolute rule would be red on day one and switched off within a
     week -- this repository's own lesson about thresholds. The baseline records those 22; a new one
     is a finding.

The asymmetry is the point. Losing a note destroys what a reader relied on; gaining one misattributes
work but destroys nothing, and the history is already full of them.

WHITESPACE IS NOT CONTENT. Bullets are compared by their first line, normalised -- a reflow, a
re-wrap or an indent change must not fire this, or it becomes noise and gets removed.

Stdlib + git. Exit 0 clean, 1 findings, 2 cannot judge.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "docs/evidence/published-block-baseline.json"
HEADING = re.compile(r"^### ")
TAGGED = re.compile(r"\(release (v\d+\.\d+\.\d+)\)")


def blocks_for(text: str, tag: str) -> list[list[str]]:
    """Body lines of every `### … (release <tag>)` block. Mirrors extract_release_notes."""
    needle = f"(release {tag})"
    out, current = [], None
    for line in text.split("\n"):
        if HEADING.match(line):
            if current is not None:
                out.append(current)
            current = [] if needle in line else None
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        out.append(current)
    return out


# A bullet's IDENTITY is its bolded lead, not its whole first line.
TITLE = re.compile(r"^- \*\*(.+?)\*\*", re.S)


def bullets(text: str, tag: str) -> list[str]:
    """One identity per bullet: the bolded lead, whitespace collapsed.

    NOT the whole first line, and the difference is the whole usability of this check. Files get
    reorganised, and the historical notes that point at them are updated to match -- `docs/
    coverage.html` became `docs/evidence/coverage.html`, `docs/harness-doctrine.md` became
    `docs/doctrine/harness-doctrine.md`. A first draft keyed on the first line and read four such
    path corrections as DESTROYED NOTES across v1.44.0, v1.92.0 and v1.112.0. The note is still
    there, still saying the same thing, now pointing somewhere that exists -- calling that a loss
    would make the rule refuse the maintenance it should welcome, and it would be red on day one.

    The bolded lead is what a reader remembers a note BY. If that disappears, the note is gone.
    """
    found = []
    for body in blocks_for(text, tag):
        for line in body:
            s = line.strip()
            m = TITLE.match(s)
            if m:
                # Backticked spans are dropped from the identity: a note's identity is its PROSE,
                # not the paths it cites. v1.112.0's lead carried the path INSIDE the bold --
                # "the reasoning moved to `docs/maintainer-history.md`" -- so when that file moved
                # to `docs/brain/history/`, correcting the note changed its identity and read as a
                # destroyed note. Same legitimate maintenance as the other three, one level in.
                title = re.sub(r"`[^`]*`", "", m.group(1))
                found.append(re.sub(r"\s+", " ", title).strip(" ,.—-"))
    return found


def _git(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def tagged_blocks(root: Path, text: str) -> list[str]:
    code, out = _git(root, "tag")
    if code != 0:
        return []
    tags = set(out.split())
    return sorted(t for t in set(TAGGED.findall(text)) if t in tags)


def compare(root: Path, text: str) -> tuple[list[str], list[str], int]:
    """(losses, additions, blocks examined) — losses and additions as `tag` strings."""
    losses, additions, examined = [], [], 0
    for tag in tagged_blocks(root, text):
        code, at_tag = _git(root, "show", f"{tag}:CHANGELOG.md")
        if code != 0:
            continue                     # no CHANGELOG at that tag; nothing to compare against
        examined += 1
        then, now = bullets(at_tag, tag), bullets(text, tag)
        if [b for b in then if b not in now]:
            losses.append(tag)
        if [b for b in now if b not in then]:
            additions.append(tag)
    return losses, additions, examined


def check(root: Path = REPO, baseline: list[str] | None = None) -> tuple[list[str], int]:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if baseline is None:
        baseline = []
        if BASELINE.is_file():
            baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("additions", [])
    losses, additions, examined = compare(root, text)
    findings = []
    for tag in losses:
        findings.append(
            f"CHANGELOG.md: the `{tag}` block has LOST a bullet it carried at that tag — a "
            f"published note a reader relied on has been destroyed. Restore it verbatim from "
            f"`git show {tag}:CHANGELOG.md`. There is no legitimate reason for a loss.")
    for tag in additions:
        if tag not in baseline:
            findings.append(
                f"CHANGELOG.md: the `{tag}` block has GAINED a bullet that was not there when the "
                f"tag was cut — unshipped work filed under a shipped release. A rebase across a "
                f"promotion does this cleanly and silently: `### Unreleased` was renamed by the "
                f"arm, so the bullets land at the top of the renamed block. Move it to a fresh "
                f"`### Unreleased`.")
    return findings, examined


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    AT_TAG = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n- **one** body\n- **two** body\n")
    SAME = AT_TAG
    LOST = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n- **one** body\n")
    GAINED = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n- **one** body\n- **two** body\n"
              "- **three** body\n")
    # A re-wrap is the SAME note. Without this the check fires on every reflow and gets deleted.
    REWRAPPED = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n- **one**    body\n- **two** body\n")
    # THE CASE THAT REALLY HAPPENS, four times in this repo's history: a file moved and the
    # historical note was corrected to point at its new home. `docs/coverage.html` became
    # `docs/evidence/coverage.html`; `docs/harness-doctrine.md` became `docs/doctrine/...`. The
    # note is still there, still saying the same thing, now pointing somewhere that exists.
    PATH_AT_TAG = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n"
                   "- **the map lives at `docs/map.html`** body\n")
    PATH_MOVED = ("## C\n\n### 2026-01-01 (release v1.0.0)\n\n"
                  "- **the map lives at `docs/architecture/map.html`** body\n")

    expect("a bullet present at the tag and gone now is a loss",
           [b for b in bullets(AT_TAG, "v1.0.0") if b not in bullets(LOST, "v1.0.0")])
    expect("a bullet added after the tag is an addition",
           [b for b in bullets(GAINED, "v1.0.0") if b not in bullets(AT_TAG, "v1.0.0")])
    expect("an unchanged block is neither",
           bullets(SAME, "v1.0.0") == bullets(AT_TAG, "v1.0.0"))
    # THE MUST-PASS CASE, and the reason the comparison is normalised.
    expect("a re-wrapped bullet is NOT a change",
           bullets(REWRAPPED, "v1.0.0") == bullets(AT_TAG, "v1.0.0"))
    expect("a block for a different tag is not read",
           bullets(AT_TAG, "v9.9.9") == [])
    # MUST PASS. Keying on the whole first line read four of these as destroyed notes, which
    # would make the rule refuse the maintenance it should welcome -- red on day one.
    expect("a note whose cited path was corrected is the SAME note",
           bullets(PATH_MOVED, "v1.0.0") == bullets(PATH_AT_TAG, "v1.0.0"))

    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="published-blocks-"))
    try:
        env = ["-c", "user.email=f@e", "-c", "user.name=f"]
        (root / "CHANGELOG.md").write_text(AT_TAG, encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, capture_output=True)
        subprocess.run(["git", *env, "add", "-A"], cwd=root, capture_output=True)
        subprocess.run(["git", *env, "commit", "-qm", "r"], cwd=root, capture_output=True)
        subprocess.run(["git", "tag", "v1.0.0"], cwd=root, capture_output=True)

        f, n = check(root, baseline=[])
        expect("a block identical to its tag is clean, and the tag was examined", not f and n == 1)

        (root / "CHANGELOG.md").write_text(LOST, encoding="utf-8")
        f, _ = check(root, baseline=[])
        expect("a LOST bullet is reported, and named as destroyed history",
               len(f) == 1 and "LOST" in f[0] and "v1.0.0" in f[0])

        (root / "CHANGELOG.md").write_text(GAINED, encoding="utf-8")
        f, _ = check(root, baseline=[])
        expect("a GAINED bullet is reported", len(f) == 1 and "GAINED" in f[0])
        # THE RATCHET. 22 blocks already differ from before anyone watched; an absolute rule would
        # be red on day one and switched off. A baselined tag is silent.
        f, _ = check(root, baseline=["v1.0.0"])
        expect("a baselined addition is silent", not f)
        # ...but a LOSS is never baselined away. Destruction has no legitimate case.
        (root / "CHANGELOG.md").write_text(LOST, encoding="utf-8")
        f, _ = check(root, baseline=["v1.0.0"])
        expect("a LOSS is reported even for a baselined tag — the ratchet never excuses destruction",
               len(f) == 1 and "LOST" in f[0])

        (root / "CHANGELOG.md").write_text(REWRAPPED, encoding="utf-8")
        f, _ = check(root, baseline=[])
        expect("a re-wrapped published block is clean", not f)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a loss is absolute, an addition is ratcheted, and a re-wrap is neither")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="re-record which tags already carry post-tag additions")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    losses, additions, examined = compare(REPO, text)
    if examined == 0:
        # NOT a pass. Zero findings over zero blocks reads exactly like a clean history.
        print("NOT APPLICABLE: no tagged release block could be compared — this check examined "
              "nothing.")
        return 2

    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({"additions": additions}, indent=2) + "\n", encoding="utf-8")
        print(f"baseline recorded: {len(additions)} block(s) carry post-tag additions.")
        if losses:
            print(f"REFUSED to baseline {len(losses)} LOSS(es) — restore them instead: "
                  f"{', '.join(losses)}")
            return 1
        return 0

    findings, _ = check()
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} tagged release block(s) compared against their tags; "
          f"{len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
