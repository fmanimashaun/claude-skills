#!/usr/bin/env python3
"""Close an issue when the PR that fixes it merges into `dev`; say so again when it ships.

Run:  python3 scripts/close_on_dev_merge.py --pr 1478            # after a merge into dev (CI does this)
      python3 scripts/close_on_dev_merge.py --pr 1478 --dry-run  # print what it would do
      python3 scripts/close_on_dev_merge.py --shipped v1.153.0 --notes notes.md
      python3 scripts/close_on_dev_merge.py --selftest

WHY (owner's decision, 2026-09-29). Issues used to close only at the `dev -> main` promotion, so a
fix merged on Monday sat open until the release, and "open" stopped meaning "not done". GitHub
cannot do this itself: a closing keyword fires only on a merge into the DEFAULT branch, which here
is `main`. So `.github/workflows/close-on-dev-merge.yml` runs this on every merge into `dev`.

THE CONSEQUENCE IT HAS TO CARRY. `main` is what users install, so "closed" no longer means
"installable". Every issue closed here gets the `fixed-on-dev` label and a comment naming the PR and
saying the fix ships in the next release; `--shipped` (run by release.yml after it publishes)
comments the version and removes the label. A downstream reporter can always tell which one they
are looking at.

WHICH ISSUES. Only a `Fixes #n` alone on its line in the PR body -- the complete fix. `Refs #n`
stays open (an EPIC's increment, a partial fix), and a keyword mid-sentence or quoted is prose, not
an instruction: "this fixes #12 only partly" must not close #12.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

REPO = "fmanimashaun/claude-skills"
LABEL = "fixed-on-dev"
LABEL_COLOR = "0e8a16"
LABEL_TEXT = "Fixed on dev, not yet released: ships in the next dev -> main promotion"
FIXES = re.compile(r"^\s*(?:[-*]\s+)?Fixes\s+#(\d+)\s*$", re.M | re.I)


def fixed_issues(body: str) -> list[int]:
    """Issue numbers a PR body declares complete, in order, without repeats."""
    seen: list[int] = []
    for m in FIXES.finditer(body or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def shipped_issues(notes: str) -> list[int]:
    """Issue numbers a release's notes cite as `(#n)`, the CHANGELOG's convention for "ships n"."""
    return sorted({int(n) for n in re.findall(r"\(#(\d+)\)", notes)})


def gh(*args: str) -> str:
    out = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {out.stderr.strip() or 'failed'}")
    return out.stdout


def ensure_label() -> None:
    names = {label["name"] for label in json.loads(
        gh("label", "list", "-R", REPO, "--limit", "200", "--json", "name"))}
    if LABEL not in names:
        gh("label", "create", LABEL, "-R", REPO, "--color", LABEL_COLOR, "--description", LABEL_TEXT)


def close_for_pr(pr: int, dry_run: bool) -> int:
    data = json.loads(gh("pr", "view", str(pr), "-R", REPO, "--json", "body,merged,baseRefName"))
    if not data.get("merged") or data.get("baseRefName") != "dev":
        print(f"PR #{pr} is not merged into dev; nothing to close")
        return 0
    issues = fixed_issues(data.get("body", ""))
    if not issues:
        print(f"PR #{pr} declares no `Fixes #n`; nothing to close")
        return 0
    if not dry_run:
        ensure_label()
    for n in issues:
        state = json.loads(gh("issue", "view", str(n), "-R", REPO, "--json", "state"))["state"]
        if state != "OPEN":
            print(f"#{n}: already {state.lower()}, left alone")
            continue
        note = (f"Fixed on `dev` by PR #{pr}. **Not installable yet:** it ships in the next release "
                f"(`dev -> main`), when this issue gets a comment naming the version. "
                f"Label `{LABEL}` means exactly that.")
        if dry_run:
            print(f"#{n}: would label {LABEL}, comment and close")
            continue
        gh("issue", "edit", str(n), "-R", REPO, "--add-label", LABEL)
        gh("issue", "close", str(n), "-R", REPO, "--reason", "completed", "--comment", note)
        print(f"#{n}: closed ({LABEL})")
    return 0


def mark_shipped(tag: str, notes_path: str, dry_run: bool) -> int:
    notes = open(notes_path, encoding="utf-8").read()
    for n in shipped_issues(notes):
        labels = json.loads(gh("issue", "view", str(n), "-R", REPO, "--json", "labels"))["labels"]
        if LABEL not in {label["name"] for label in labels}:
            continue
        if dry_run:
            print(f"#{n}: would comment 'shipped in {tag}' and remove {LABEL}")
            continue
        gh("issue", "comment", str(n), "-R", REPO, "--body", f"Shipped in **{tag}**: installable now.")
        gh("issue", "edit", str(n), "-R", REPO, "--remove-label", LABEL)
        print(f"#{n}: shipped in {tag}")
    return 0


def selftest() -> int:
    failures: list[str] = []
    cases = {
        "Fixes #12": [12],
        "Fixes #12\nFixes #13\nFixes #12": [12, 13],
        "- Fixes #7": [7],
        "fixes #7": [7],
        "Refs #12": [],
        "This fixes #12 only partly.": [],
        "`Fixes #12`": [],
        "Fixes #12 and #13": [],
        "Fixes#12": [],
        "> Fixes #12": [],
        "": [],
    }
    for body, want in cases.items():
        got = fixed_issues(body)
        if got != want:
            failures.append(f"fixed_issues({body!r}): expected {want}, got {got}")
    got = shipped_issues("- **x** (#1410). See also (in PR #1470) and #99.\n- y (#1444) (#1410)")
    if got != [1410, 1444]:
        failures.append(f"shipped_issues: expected [1410, 1444], got {got}")
    total = len(cases) + 1
    if failures:
        print(f"close_on_dev_merge selftest FAILED -- {len(failures)} of {total}:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"close_on_dev_merge selftest: {total} checks passed")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr", type=int)
    ap.add_argument("--shipped", metavar="TAG")
    ap.add_argument("--notes", metavar="FILE")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    if args.pr:
        return close_for_pr(args.pr, args.dry_run)
    if args.shipped and args.notes:
        return mark_shipped(args.shipped, args.notes, args.dry_run)
    ap.error("give --pr, or --shipped with --notes, or --selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
