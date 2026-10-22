#!/usr/bin/env python3
"""Refuse a PR that closes an issue carrying an owner ruling no decision record cites (#2297).

Run:  python3 check_owner_rulings.py [--root DIR] [--pr N] [--decisions docs/brain/DECISIONS.md]
      python3 check_owner_rulings.py --selftest

WHY THIS EXISTS. Seven owner rulings (2026-10-21 and 22) were recorded as issue comments and in one session's
private memory, and docs/brain/DECISIONS.md did not hear of them. An issue is a place a ruling is made, not a
place it is kept: it closes. The brain is where the next session looks. So closing an issue that carries an owner
ruling needs a decision record that names it.

THE RULE. For each issue the PR closes (a line that is exactly `Fixes #n`, `Closes #n` or `Resolves #n`, the
repository's own closing convention), read the issue body and every comment. If any of them says `owner rule`,
`owner ruling`, `owner decision`, `owner decided`, `owner direction` or `owner, <date>`, then some `## D-NNN`
block in docs/brain/DECISIONS.md, as it is at HEAD (so a record added in this very PR counts, and so does one
already on dev), must mention `#n`. Otherwise the PR is refused, naming the issue, the ruling's date and its
first words. "Owner request" is not a ruling and is not matched.

SCOPE. It reads GitHub through `gh`. Exit 3 ("not applicable", never a pass) only where that is genuinely
impossible and says so: `gh` is not installed, or this branch has no PR yet (nothing closes anything). With `gh`
present, an error reading the PR or an issue is a REFUSAL (exit 1, named): a check that passes because the read
failed is the defect this repository warns about most.

Exit: 0 every closed issue's ruling (if any) is recorded · 1 a ruling is unrecorded, or a read failed · 3 gh
is absent or there is no PR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

CLOSING = re.compile(r"^\s*(?:fixes|closes|resolves)\s+#(\d+)\s*$", re.I | re.M)
RULING = re.compile(r"\bowner\s+(?:rule|ruling|decision|decided|direction)\b|\bowner,\s*\d{4}-\d{2}-\d{2}\b", re.I)
DECISION_BLOCK = re.compile(r"^##\s+D-\d+\b", re.M)


def gh(root: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True)
    return r.returncode, (r.stdout if r.returncode == 0 else r.stderr or r.stdout).strip()


def decision_blocks(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    starts = [m.start() for m in DECISION_BLOCK.finditer(text)]
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def recorded(blocks: list[str], issue: int) -> bool:
    return any(re.search(rf"#{issue}\b", b) for b in blocks)


def rulings(issue: dict) -> list[tuple[str, str]]:
    """`[(date, first words)]` for each body or comment that states an owner ruling."""
    found = []
    for date, text in [(issue.get("createdAt", "")[:10], issue.get("body") or "")] + \
                      [((c.get("createdAt") or "")[:10], c.get("body") or "") for c in issue.get("comments", [])]:
        m = RULING.search(text)
        if m:
            found.append((date, " ".join(text[m.start():m.start() + 90].split())))
    return found


def judge(root: Path, pr: str | None, decisions: Path) -> tuple[int, list[str]]:
    if shutil.which("gh") is None:
        return 3, ["gh is not installed: the issues this PR closes cannot be read, so their owner rulings cannot be checked (not a pass)"]
    args = ["pr", "view"] + ([pr] if pr else []) + ["--json", "number,body"]
    rc, out = gh(root, *args)
    if rc != 0:
        if "no pull requests found" in out.lower() or "no pull request" in out.lower():
            return 3, ["no pull request for this branch yet: nothing closes anything, so there is no ruling to check (not a pass)"]
        return 1, [f"could not read the pull request: {out[:200]}"]
    try:
        body = json.loads(out).get("body") or ""
    except ValueError:
        return 1, ["`gh pr view` did not return JSON"]
    issues = sorted({int(n) for n in CLOSING.findall(body)})
    blocks = decision_blocks(decisions)
    problems, ruled = [], 0
    for n in issues:
        rc, out = gh(root, "issue", "view", str(n), "--json", "body,comments,createdAt")
        if rc != 0:
            problems.append(f"could not read #{n}: {out[:200]}; its owner rulings cannot be checked, so the PR is refused")
            continue
        try:
            issue = json.loads(out)
        except ValueError:
            problems.append(f"`gh issue view {n}` did not return JSON")
            continue
        for date, words in rulings(issue):
            ruled += 1
            if not recorded(blocks, n):
                problems.append(f"#{n} carries an owner ruling ({date}: \"{words}...\") and no `## D-NNN` block in {decisions.as_posix()} mentions #{n}: "
                                f"record the decision (the choice, why, and `Refs #{n}`) in this PR, or the ruling lives only in the issue")
                break
    if problems:
        return 1, problems
    return 0, [f"{len(issues)} closing issue(s), {ruled} owner ruling(s), every one recorded in a decision"]


def selftest() -> int:
    n, bad = 0, []

    def check(label: str, ok: bool, detail=""):
        nonlocal n
        n += 1
        if not ok:
            bad.append(f"{label}{(' — ' + str(detail)) if detail else ''}")

    tmp = Path(tempfile.mkdtemp(prefix="owner-rulings-"))
    root = tmp / "repo"
    (root / "docs/brain").mkdir(parents=True)
    state = tmp / "state.json"
    fake = tmp / "bin"
    fake.mkdir()
    # A stand-in `gh`: answers from state.json, so no live GitHub is touched (a probe once ran three real mutations).
    (fake / "gh").write_text("#!" + sys.executable + """
import json, sys
s = json.load(open(%r))
a = sys.argv[1:]
if a[:2] == ["pr", "view"]:
    if s.get("no_pr"):
        print("no pull requests found for branch", file=sys.stderr); sys.exit(1)
    if s.get("pr_error"):
        print("HTTP 502", file=sys.stderr); sys.exit(1)
    print(json.dumps({"number": 1, "body": s["pr_body"]}))
elif a[:2] == ["issue", "view"]:
    n = a[2]
    if n in s.get("issue_error", []):
        print("HTTP 500", file=sys.stderr); sys.exit(1)
    print(json.dumps(s["issues"][n]))
""" % str(state))
    (fake / "gh").chmod((fake / "gh").stat().st_mode | stat.S_IXUSR)
    decisions = root / "docs/brain/DECISIONS.md"

    def run(pr_body="Fixes #5\n", issues=None, dec="# DECISIONS\n", no_pr=False, pr_error=False, issue_error=(), path=None, status="") -> tuple[int, str]:
        state.write_text(json.dumps({"pr_body": pr_body, "issues": issues or {}, "no_pr": no_pr, "pr_error": pr_error,
                                     "issue_error": list(issue_error)}), encoding="utf-8")
        decisions.write_text(dec, encoding="utf-8")
        (root / "docs/brain/STATUS.md").write_text(status, encoding="utf-8")
        r = subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True,
                           env={**os.environ, "PATH": path or f"{fake}{os.pathsep}{os.environ['PATH']}"})
        return r.returncode, r.stdout + r.stderr

    ruling = {"5": {"createdAt": "2026-10-20T00:00:00Z", "body": "a bug", "comments": [{"createdAt": "2026-10-21T10:00:00Z", "body": "**Owner ruling, 2026-10-21:** keep it."}]}}
    plain = {"5": {"createdAt": "2026-10-20T00:00:00Z", "body": "Owner request, 2026-10-20 (verbatim): please look", "comments": [{"createdAt": "2026-10-21T10:00:00Z", "body": "fixed"}]}}
    cited = "# DECISIONS\n\n## D-012 — keep it (2026-10-21) `[decided]`\n**Choice:** keep. Refs #5.\n"

    rc, out = run(issues=ruling)
    check("a closed issue with an owner ruling and no decision citing it is refused, naming the issue and the ruling",
          rc == 1 and "#5" in out and "2026-10-21" in out and "Owner ruling" in out, (rc, out))
    rc, out = run(issues=ruling, dec=cited)
    check("...and passes once a D-NNN block mentions #5", rc == 0 and "recorded" in out, (rc, out))
    rc, out = run(issues=ruling, dec="# DECISIONS\n\n## D-012 — other (2026-10-21)\n**Choice:** x. Refs #50.\n")
    check("a block that mentions #50 does not record #5", rc == 1, (rc, out))
    rc, out = run(issues=ruling, status="Refs #5 — decided in chat\n")
    check("a mention outside DECISIONS.md does not record it", rc == 1, (rc, out))
    rc, out = run(issues=plain)
    check("an owner REQUEST is not a ruling: nothing to record", rc == 0, (rc, out))
    rc, out = run(issues={"5": {"createdAt": "2026-10-20T00:00:00Z", "body": "Owner, 2026-10-20: do X", "comments": []}})
    check("`owner, <date>` in the issue body counts as a ruling", rc == 1, (rc, out))
    rc, out = run(pr_body="Refs #5\n", issues=ruling)
    check("`Refs #n` closes nothing, so it owes no record", rc == 0, (rc, out))
    rc, out = run(pr_body="This Fixes #5 in passing\n", issues=ruling)
    check("a closing keyword mid-sentence closes nothing (the repository's own convention)", rc == 0, (rc, out))
    rc, out = run(pr_body="Fixes #5\nFixes #6\n", issues={**ruling, "6": plain["5"]}, dec=cited)
    check("two closing issues: the recorded ruling and the plain one pass together", rc == 0, (rc, out))
    rc, out = run(issues=ruling, issue_error=("5",))
    check("with gh present, an issue that cannot be read REFUSES the PR (exit 1), never passes", rc == 1 and "could not read #5" in out, (rc, out))
    rc, out = run(issues=ruling, pr_error=True)
    check("with gh present, a PR that cannot be read refuses", rc == 1 and "could not read the pull request" in out, (rc, out))
    rc, out = run(issues=ruling, no_pr=True)
    check("no PR yet is not applicable (exit 3) and says so", rc == 3 and "no pull request" in out, (rc, out))
    bare = tmp / "nogh"
    bare.mkdir()
    rc, out = run(issues=ruling, path=str(bare))
    check("no gh at all is not applicable (exit 3) and says so", rc == 3 and "gh is not installed" in out, (rc, out))

    for f in bad:
        print(f"FAIL {f}")
    print(f"check_owner_rulings selftest: {n} checks, {len(bad)} failure(s)")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--pr")
    ap.add_argument("--decisions", default="docs/brain/DECISIONS.md")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    rc, lines = judge(root, a.pr, root / a.decisions)
    label = {0: "ok", 1: "REFUSED", 3: "not applicable"}[rc]
    for line in lines:
        print(f"{label}: {line}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
