#!/usr/bin/env python3
"""Every defect class a reviewer blocked on names a fixture that still exists (#1563).

Run:  python3 scripts/check_blocked_catalogue.py
      python3 scripts/check_blocked_catalogue.py --selftest

WHY THIS EXISTS. `docs/evidence/reviews/blocked-catalogue.md` lists what independent reviewers refused
and what now stops it. A list of defect classes with no trigger behind it changes nothing: the next
author repeats the class and the reviewer pays for it again. So the catalogue names, for each merged
class, a `path :: literal` fixture on `dev`, and this check refuses a row whose file is gone or whose
literal no longer appears in it -- the way a fixture quietly disappears in a refactor.

WHAT IT CHECKS, AND WHAT IT DOES NOT. It checks that the fixture the catalogue points at is still
there and still contains the named literal. It does NOT prove the fixture would catch the defect: that
is the job of the mutation guard for the script the fixture tests. A literal found in a comment would
satisfy this check, which is why each literal is a distinctive string a test asserts on, not a word.

THREE TABLES, THREE RULES.
  * "with a fixture on `dev`": state must be `merged`, and the fixture must resolve.
  * "fix is on an open PR": state must be `open` and an owner must be named; no fixture is claimed,
    because claiming one that is not on `dev` would be a statement nothing makes true.
  * "Advisory": a reason is required. An advisory row with no reason is a class that was dropped.

Stdlib only, no network (so it cannot know a PR's state; it checks the catalogue is self-consistent).
Exit 0 clean, 1 findings, 2 nothing examined.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = Path("docs/evidence/reviews/blocked-catalogue.md")

FIXTURE_HEAD = "classes with a fixture on `dev`"
OPEN_HEAD = "fix is on an open pr"
ADVISORY_HEAD = "advisory:"


def tables(text: str) -> dict[str, list[list[str]]]:
    """Map a section's heading (lower-cased) to its table rows, header and rule rows dropped."""
    out: dict[str, list[list[str]]] = {}
    heading = ""
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            out.setdefault(heading, [])
        elif line.startswith("|") and heading:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and not set("".join(cells)) <= set("-: "):
                out[heading].append(cells)
    for rows in out.values():
        if rows:
            rows.pop(0)          # the header row
    return out


def section(found: dict[str, list[list[str]]], key: str) -> list[list[str]]:
    for heading, rows in found.items():
        if key in heading:
            return rows
    return []


def check_fixture(root: Path, cell: str) -> str | None:
    """None when `path :: literal` resolves, else the reason it does not."""
    m = re.fullmatch(r"`([^`]+?) :: ([^`]+)`", cell)
    if not m:
        return f"fixture cell {cell!r} is not `path :: literal`"
    path, literal = m.group(1), m.group(2)
    target = root / path
    if not target.is_file():
        return f"{path} does not exist"
    if literal not in target.read_text(encoding="utf-8", errors="replace"):
        return f"{path} no longer contains {literal!r}"
    return None


def examine(root: Path) -> tuple[list[str], int]:
    """(findings, rows examined)."""
    path = root / CATALOGUE
    if not path.is_file():
        return [f"{CATALOGUE} does not exist"], 0
    found = tables(path.read_text(encoding="utf-8"))
    findings: list[str] = []
    examined = 0

    for row in section(found, FIXTURE_HEAD):
        examined += 1
        cls, pr, state, _defect, fixture = (row + [""] * 5)[:5]
        if state != "merged":
            findings.append(f"{cls} (#{pr}): in the fixture table but state is {state!r}, not merged")
        problem = check_fixture(root, fixture)
        if problem:
            findings.append(f"{cls} (#{pr}): {problem}")

    for row in section(found, OPEN_HEAD):
        examined += 1
        cls, pr, state, _defect, owner = (row + [""] * 5)[:5]
        if state != "open":
            findings.append(f"{cls} (#{pr}): in the open-PR table but state is {state!r}")
        if not owner:
            findings.append(f"{cls} (#{pr}): no owner named for a fix that is not on dev")

    for row in section(found, ADVISORY_HEAD):
        examined += 1
        cls, pr, _state, _defect, reason = (row + [""] * 5)[:5]
        if not reason:
            findings.append(f"{cls} (#{pr}): an advisory row must say why it has no fixture")

    return findings, examined


def run(root: Path) -> int:
    findings, examined = examine(root)
    if examined == 0:
        print("blocked catalogue: examined nothing (missing file or no table rows)", file=sys.stderr)
        return 2
    for f in findings:
        print(f"FAIL {f}")
    print(f"blocked catalogue: {examined} rows examined, {len(findings)} findings")
    return 1 if findings else 0


# --- selftest ---------------------------------------------------------------------------------------

def _catalogue(fixture_row: str = "| a | 1 | merged | d | `f.py :: needle` |",
               open_row: str = "| b | 2 | open | d | PR 2 |",
               adv_row: str = "| c | 3 | merged | d | judgement |") -> str:
    return "\n".join([
        "## Classes with a fixture on `dev`", "| c | pr | s | d | f |", "|---|---|---|---|---|", fixture_row, "",
        "## Classes whose fix is on an open PR", "| c | pr | s | d | o |", "|---|---|---|---|---|", open_row, "",
        "## Advisory: no fixture", "| c | pr | s | d | a |", "|---|---|---|---|---|", adv_row, ""])


def _outcome(text: str, files: dict[str, str]) -> tuple[list[str], int]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / CATALOGUE).parent.mkdir(parents=True)
        (root / CATALOGUE).write_text(text, encoding="utf-8")
        for name, body in files.items():
            (root / name).write_text(body, encoding="utf-8")
        return examine(root)


def selftest() -> int:
    failures: list[str] = []
    good = {"f.py": "assert needle\n"}

    def expect(label: str, text: str, files: dict[str, str], want: str | None) -> None:
        findings, _ = _outcome(text, files)
        hit = any(want in f for f in findings) if want else not findings
        if not hit:
            failures.append(f"{label}: wanted {want or 'no findings'}, got {findings}")

    expect("a resolving fixture is clean", _catalogue(), good, None)
    expect("a missing literal is reported", _catalogue(), {"f.py": "nothing here\n"}, "no longer contains")
    expect("a missing file is reported", _catalogue(), {}, "does not exist")
    expect("a malformed fixture cell is reported",
           _catalogue(fixture_row="| a | 1 | merged | d | f.py needle |"), good, "not `path :: literal`")
    expect("an open row in the fixture table is reported",
           _catalogue(fixture_row="| a | 1 | open | d | `f.py :: needle` |"), good, "not merged")
    expect("a merged row in the open table is reported",
           _catalogue(open_row="| b | 2 | merged | d | PR 2 |"), good, "in the open-PR table")
    expect("an open row with no owner is reported",
           _catalogue(open_row="| b | 2 | open | d |  |"), good, "no owner")
    expect("an advisory row with no reason is reported",
           _catalogue(adv_row="| c | 3 | merged | d |  |"), good, "must say why")
    # The near miss: an advisory row WITH a reason, and an open row WITH an owner, stay clean.
    expect("an advisory row with a reason is clean", _catalogue(adv_row="| c | 3 | merged | d | why |"),
           good, None)
    if _outcome("## Notes\nno tables\n", {})[1] != 0:
        failures.append("a catalogue with no table rows must examine nothing")
    with tempfile.TemporaryDirectory() as tmp:
        if run(Path(tmp)) != 2:
            failures.append("a missing catalogue must exit 2, not pass")

    for f in failures:
        print("SELFTEST FAIL", f)
    print(f"check_blocked_catalogue selftest: {'FAILED' if failures else 'ok'}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    return selftest() if args.selftest else run(args.root)


if __name__ == "__main__":
    sys.exit(main())
