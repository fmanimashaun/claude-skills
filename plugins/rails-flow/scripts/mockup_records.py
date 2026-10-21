#!/usr/bin/env python3
"""Reading a mock-up record, and auditing which designs were never linked to a built screen (#2226).

ONE COPY, TWO HOMES. `check_mockup_gate.py` (rails-flow) judges a branch's records; qa-flow's `release_evidence.py` refuses the
certification stamp when a shipped design names no `Story:`. A plugin reaches only its own files, so qa-flow ships a byte-identical copy
of THIS file, and `scripts/lint_self_consistency.py` (`vendored-copy-drift`) fails when the two differ. Edit the rails-flow file, then cp.

A record is `docs/product/mockups/<slug>.md`: one `Key: value` line for each key. The keys and their meaning are in
`plugins/rails-flow/reference/mockup-record.md`. Stdlib only.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RECORD_DIR = "docs/product/mockups/"
RECORD_KEYS = ("Mock-up", "Issue", "Approved-by", "Approval", "Widths", "States")
# The shell (#2211): one record every other record points at.
SHELL_RECORD = RECORD_DIR + "shell.md"
SHELL_KEYS = ("Kind", "Shell", "Shell-sources", "Shell-keep", "Shell-signature")
# The design lines of a screen record (#2226); their allowed values are in reference/mockup-vocabulary.json, the one list.
DESIGN_KEYS = ("Template", "Screen", "Nav", "Story")
ISSUE_REF = re.compile(r"^(#\d+|https://github\.com/[^/\s]+/[^/\s]+/issues/\d+)\b")


def read_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**([A-Za-z-]+)\**:\s*(.*?)\s*$", line)
        if m and m.group(1) in RECORD_KEYS + SHELL_KEYS + DESIGN_KEYS:
            fields[m.group(1)] = m.group(2)
    return fields


def issue_state(root: Path, ref: str) -> str | None:
    """`OPEN` or `CLOSED` for an issue (`gh issue view`), or None when gh cannot say (offline, unauthenticated, no such issue)."""
    try:
        r = subprocess.run(["gh", "issue", "view", ref, "--json", "state", "--jq", ".state"], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and out in ("OPEN", "CLOSED") else None


def audit_results(root: Path, state=issue_state) -> tuple[list[str], list[str], list[str], int]:
    """(failing, unjudged, legacy, judged): see `audit`."""
    folder = root / RECORD_DIR
    failing: list[str] = []
    unjudged: list[str] = []
    legacy: list[str] = []
    judged = 0
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if rel == SHELL_RECORD or path.name.lower() == "readme.md":
            continue
        fields = read_fields(path)
        if fields.get("Story"):
            judged += 1
            continue
        if not fields.get("Template"):
            legacy.append(rel)
            continue
        issue = fields.get("Issue", "")
        ref = issue.lstrip("#") if re.match(r"^#\d+$", issue) else (issue if ISSUE_REF.match(issue) else "")
        verdict = state(root, ref) if ref else None
        if verdict is None:
            unjudged.append(f"{rel}: Issue {issue!r} could not be read, so whether it is closed is unknown")
        elif verdict == "CLOSED":
            failing.append(f"{rel}: Issue {issue} is closed and the record names no `Story:`: link the built screen")
            judged += 1
        else:
            judged += 1
    return failing, unjudged, legacy, judged


def audit(root: Path, state=issue_state) -> tuple[int, list[str]]:
    """Records whose issue is CLOSED but that name no `Story:` (#2226): designed, shipped, and never linked to the built screen.

    ONLINE, which is why it is not part of the offline gate: it asks GitHub whether each issue is closed. A new-format record (it has a
    `Template:` line) that lacks `Story:` and whose issue is closed fails. A legacy record is only listed: it predates the line. A record
    whose issue cannot be read is UNJUDGED, and an audit with an unjudged record is not a pass (exit 2, unless a failure already says 1)."""
    failing, unjudged, legacy, judged = audit_results(root, state)
    lines = [f"{len(failing)} closed-issue record(s) with no Story, {len(unjudged)} unjudged, {len(legacy)} legacy record(s) without one, "
             f"{judged} checked"] + failing + unjudged
    if legacy:
        lines.append("legacy records with no Story (listed, not failed): " + ", ".join(legacy[:10])
                     + (f" and {len(legacy) - 10} more" if len(legacy) > 10 else ""))
    return (1 if failing else 2 if unjudged else 0), lines
