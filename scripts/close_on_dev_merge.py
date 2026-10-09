#!/usr/bin/env python3
"""Close an issue when the PR that fixes it merges into `dev`; say so again when it ships.

Run:  python3 scripts/close_on_dev_merge.py --pr 1478            # after a merge into dev (CI does this)
      python3 scripts/close_on_dev_merge.py --pr 1478 --dry-run  # print what it would do
      python3 scripts/close_on_dev_merge.py --shipped v1.153.0 --notes notes.md
      python3 scripts/close_on_dev_merge.py --selftest

WHY (owner's decision, #1483). Issues used to close only at the `dev -> main` promotion, so a fix
merged on Monday sat open until the release, and "open" stopped meaning "not done". GitHub cannot
do this itself: a closing keyword fires only on a merge into the DEFAULT branch, which here is
`main`. So `.github/workflows/close-on-dev-merge.yml` runs this on every merge into `dev`.

THE CONSEQUENCE IT HAS TO CARRY. `main` is what users install, so "closed" no longer means
"installable". Every issue closed here gets the `fixed-on-dev` label and a comment naming the PR and
saying the fix ships in the next release; `--shipped` (run by release.yml after it publishes)
comments the version and removes the label. A downstream reporter can always tell which one they
are looking at.

WHICH ISSUES. Only a `Fixes #n` alone on its line in the PR body -- the complete fix. `Refs #n`
stays open (an EPIC's increment, a partial fix), and a keyword mid-sentence or quoted is prose, not
an instruction: "this fixes #12 only partly" must not close #12. A number that is a PULL REQUEST is
never touched: GitHub numbers issues and PRs in one sequence, and `gh issue view` answers for both.

THE SELFTEST DRIVES THE ENTRY POINTS against a stubbed `gh`, not only the parsers. The first
version asked `gh pr view` for a `merged` field that does not exist, so every real run crashed
while twelve parser checks and four mutations stayed green (review of PR #1488).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Callable

REPO = "fmanimashaun/claude-skills"
LABEL = "fixed-on-dev"
LABEL_COLOR = "0e8a16"
LABEL_TEXT = "Fixed on dev, not yet released: ships in the next dev -> main promotion"
FIXES = re.compile(r"^\s*(?:[-*]\s+)?Fixes\s+#(\d+)\s*$", re.M | re.I)
# A CHANGELOG citation: a parenthesised group that STARTS with `#n`, or with `Fixes #n` / `Closes #n` -- `(#1410)`, `(#1461, #1462)`,
# `(#1483, the owner's decision)`, `(Fixes #1628; found by the security review of #1627)`, `(Closes #484)`. "(in PR #1470)" is a
# cross-reference and does not start with `#`. Only the run of `#n` that OPENS the group is read, so an annotation may hold anything,
# including a markdown link whose own parentheses ended the old `[^()]*` match early (v1.153.0 cited `(#1404, [maintainer decision](https://…))`,
# and #1404 never got its shipped note), and a second `#n` inside the annotation ("found by the review of #1627") is not a citation.
#
# `Fixes` AND `Closes` OPEN A CITATION (#1637): v1.154.0's notes cited #1628, #1626 and #1607 as `(Fixes #…; …)`, and the old pattern, which needed
# `#` straight after `(`, told none of them they had shipped. `Refs` STAYS OUT, deliberately: it marks a partial fix (an EPIC's increment), the issue
# stays open, and "shipped" must not be said of work that is not complete. (`mark_shipped` also skips any issue without the `fixed-on-dev` label,
# which only a merged `Fixes` PR sets, so a `Refs` bullet could never have been told in practice; this keeps the rule stated rather than incidental.)
CITATION = re.compile(r"\(\s*(?:(?:Fixes|Closes)\s+)?(#\d+(?:\s*[,/]\s*#\d+)*)", re.I)

Gh = Callable[..., str]


def real_gh(*args: str) -> str:
    out = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {out.stderr.strip() or 'failed'}")
    return out.stdout


def fixed_issues(body: str) -> list[int]:
    """Issue numbers a PR body declares complete, in order, without repeats."""
    seen: list[int] = []
    for m in FIXES.finditer(body or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def shipped_issues(notes: str) -> list[int]:
    """Every `#n` inside a citation group of the release notes."""
    return sorted({int(n) for run in CITATION.findall(notes) for n in re.findall(r"#(\d+)", run)})


def is_pull_request(gh: Gh, n: int) -> bool:
    return "pull_request" in json.loads(gh("api", f"repos/{REPO}/issues/{n}"))


def ensure_label(gh: Gh) -> None:
    names = {label["name"] for label in json.loads(
        gh("label", "list", "-R", REPO, "--limit", "200", "--json", "name"))}
    if LABEL not in names:
        gh("label", "create", LABEL, "-R", REPO, "--color", LABEL_COLOR, "--description", LABEL_TEXT)


def close_for_pr(pr: int, dry_run: bool, gh: Gh = real_gh) -> int:
    data = json.loads(gh("pr", "view", str(pr), "-R", REPO, "--json", "body,state,baseRefName"))
    if data.get("state") != "MERGED" or data.get("baseRefName") != "dev":
        print(f"PR #{pr} is not merged into dev; nothing to close")
        return 0
    issues = fixed_issues(data.get("body", ""))
    if not issues:
        print(f"PR #{pr} declares no `Fixes #n`; nothing to close")
        return 0
    if not dry_run:
        ensure_label(gh)
    errors = 0
    for n in issues:
        # One issue's failure must not leave the ones after it open: report it, carry on, exit 1.
        try:
            if is_pull_request(gh, n):
                print(f"#{n}: is a pull request, not an issue; left alone")
                continue
            state = json.loads(gh("issue", "view", str(n), "-R", REPO, "--json", "state"))["state"]
            if state != "OPEN":
                print(f"#{n}: already {state.lower()}, left alone")
                continue
            if dry_run:
                print(f"#{n}: would label {LABEL}, comment and close")
                continue
            note = (f"Fixed on `dev` by PR #{pr}. **Not installable yet:** it ships in the next release "
                    f"(`dev -> main`), when this issue gets a comment naming the version. "
                    f"Label `{LABEL}` means exactly that.")
            gh("issue", "edit", str(n), "-R", REPO, "--add-label", LABEL)
            gh("issue", "close", str(n), "-R", REPO, "--reason", "completed", "--comment", note)
            print(f"#{n}: closed ({LABEL})")
        except (RuntimeError, ValueError, KeyError) as exc:
            errors += 1
            print(f"::error::#{n}: {exc}")
    return 1 if errors else 0


def mark_shipped(tag: str, notes: str, dry_run: bool, gh: Gh = real_gh) -> int:
    """Always exit 0: this runs AFTER the publish, and a re-run skips once the release exists, so a
    red here would only hide the comments it failed to post. Each failure is a visible warning."""
    for n in shipped_issues(notes):
        try:
            labels = json.loads(gh("issue", "view", str(n), "-R", REPO, "--json", "labels"))["labels"]
            if LABEL not in {label["name"] for label in labels}:
                continue
            if dry_run:
                print(f"#{n}: would comment 'shipped in {tag}' and remove {LABEL}")
                continue
            gh("issue", "comment", str(n), "-R", REPO, "--body", f"Shipped in **{tag}**: installable now.")
            gh("issue", "edit", str(n), "-R", REPO, "--remove-label", LABEL)
            print(f"#{n}: shipped in {tag}")
        except (RuntimeError, ValueError, KeyError) as exc:
            print(f"::warning::#{n}: could not mark shipped: {exc}")
    return 0


class StubGh:
    """A `gh` that answers from a table and records every mutating call."""

    def __init__(self, prs: dict, issues: dict, labels: tuple = (LABEL,), fail: set = frozenset()):
        self.prs, self.issues, self.labels, self.fail, self.calls = prs, issues, list(labels), fail, []

    def __call__(self, *args: str) -> str:
        if args[0] == "pr" and args[1] == "view":
            requested = set(args[args.index("--json") + 1].split(","))
            if not requested <= {"body", "state", "baseRefName", "mergedAt", "number"}:
                raise RuntimeError(f"Unknown JSON field: {sorted(requested)}")   # what real gh does
            return json.dumps(self.prs[int(args[2])])
        if args[0] == "api":
            n = int(args[1].rsplit("/", 1)[1])
            return json.dumps({"number": n, **({"pull_request": {}} if n in self.prs else {})})
        if args[0] == "label" and args[1] == "list":
            return json.dumps([{"name": x} for x in self.labels])
        n = int(args[2]) if len(args) > 2 and args[2].isdigit() else None
        if n in self.fail:
            raise RuntimeError(f"gh: HTTP 502 on #{n}")
        if args[:2] == ("issue", "view"):
            # Real gh answers `issue view` for a PR number too, as OPEN -- the trap #1488's review found.
            i = self.issues.get(n) or {"state": self.prs[n].get("state", "OPEN"), "labels": []}
            return json.dumps({"state": i["state"], "labels": [{"name": x} for x in i["labels"]]})
        self.calls.append(args[:3])
        return ""


def selftest() -> int:
    failures: list[str] = []
    total = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal total
        total += 1
        if not ok:
            failures.append(f"{label}{(' -- ' + str(detail)) if detail != '' else ''}")

    def attempt(fn, *a, **kw):
        """An entry point's exit code, or the exception it raised -- so a crash fails the NAMED check
        instead of the whole selftest (a mutation caught only by a traceback proves no fixture)."""
        try:
            return fn(*a, **kw)
        except Exception as exc:          # noqa: BLE001 -- recorded, not swallowed
            return exc

    for body, want in {
        "Fixes #12": [12], "Fixes #12\nFixes #13\nFixes #12": [12, 13], "- Fixes #7": [7], "fixes #7": [7],
        "Refs #12": [], "This fixes #12 only partly.": [], "`Fixes #12`": [], "Fixes #12 and #13": [],
        "Fixes#12": [], "> Fixes #12": [], "": [],
    }.items():
        got = fixed_issues(body)
        check(f"fixed_issues({body!r})", got == want, f"expected {want}, got {got}")
    # THE SHAPES OF v1.154.0'S OWN NOTES (#1637): three were never told they shipped. `#1627` and `#1620` are cross-references inside the annotation.
    release = ("- **a** (Fixes #1628; found by the security review of #1627, older than it)\n"
               "- **b** (Fixes #1607, the timeout path)\n"
               "- **c** (Fixes #1626; found by the delta security review of #1620, and older than it)\n"
               "- **d** (Fixes #1617)\n- **e** (Closes #484). All five criteria verified\n- **f** (fixes #1700, #1701)\n- **g** (closes #1702)\n")
    got = shipped_issues(release)
    check("shipped_issues reads (Fixes #n; ...) and (Closes #n), not the #n cited inside the annotation",
          got == [484, 1607, 1617, 1626, 1628, 1700, 1701, 1702], got)
    check("shipped_issues leaves (Refs #n) out: a partial fix is not shipped",
          shipped_issues("- **x** (Refs #531)\n- **y** (Refs #487, #490)\n- z (Fixes #5) (Refs #6)") == [5])
    check("shipped_issues does not read a bare Fixes #n that is not in a citation group",
          shipped_issues("Fixes #77 is prose. See (the Fixes #78 note) and Fixes #79.") == [])
    notes = ("- **x** (#1410). See also (in PR #1470) and #99.\n- y (#1444) (#1410)\n"
             "- z (#1461, #1462)\n- w (#1483, the owner's decision)\n"
             "- v (#1404, [maintainer decision](https://github.com/o/r/issues/1404#issuecomment-1))\n"
             "- u (#1500, #1501, see [the log](https://x.test/a(b)))\n- t (#621/#624)")
    got = shipped_issues(notes)
    check("shipped_issues reads single, grouped and annotated citations, not cross-references",
          got == [621, 624, 1404, 1410, 1444, 1461, 1462, 1483, 1500, 1501], got)

    # THE ENTRY POINTS, against a stub that refuses unknown JSON fields the way real gh does.
    merged = {"body": "Fixes #20\nFixes #21\nFixes #30\nRefs #22\nFixes #23", "state": "MERGED",
              "baseRefName": "dev"}
    issues = {20: {"state": "OPEN", "labels": []}, 21: {"state": "CLOSED", "labels": []},
              22: {"state": "OPEN", "labels": []}, 23: {"state": "OPEN", "labels": []}}
    pr30 = {"state": "OPEN", "body": "", "baseRefName": "dev"}          # #30 is a PR, not an issue
    stub = StubGh({1: merged, 30: pr30}, issues)
    rc = attempt(close_for_pr, 1, dry_run=False, gh=stub)
    closed = [c[2] for c in stub.calls if c[:2] == ("issue", "close")]
    check("close_for_pr runs against gh's real field set, and closes each open Fixes issue",
          rc == 0 and closed == ["20", "23"], (rc, stub.calls))
    check("close_for_pr labels before it closes",
          ("issue", "edit", "20") in stub.calls and stub.calls.index(("issue", "edit", "20"))
          < stub.calls.index(("issue", "close", "20")), stub.calls)
    check("a Fixes line naming a PULL REQUEST never touches it", "30" not in {c[2] for c in stub.calls},
          stub.calls)
    check("a Refs issue stays open, and an already-closed one is left alone",
          not {"21", "22"} & {c[2] for c in stub.calls}, stub.calls)
    stub = StubGh({1: {**merged, "state": "OPEN"}, 30: pr30}, issues)
    check("an unmerged PR closes nothing", attempt(close_for_pr, 1, False, stub) == 0 and not stub.calls, stub.calls)
    stub = StubGh({1: {**merged, "baseRefName": "main"}, 30: pr30}, issues)
    check("a PR merged into main (not dev) closes nothing", attempt(close_for_pr, 1, False, stub) == 0 and not stub.calls,
          stub.calls)
    stub = StubGh({1: merged, 30: pr30}, issues, labels=())
    attempt(close_for_pr, 1, False, stub)
    check("a missing label is created before use", bool(stub.calls) and stub.calls[0][:2] == ("label", "create"),
          stub.calls[:2])
    stub = StubGh({1: merged, 30: pr30}, issues, fail={20})
    rc = attempt(close_for_pr, 1, False, stub)
    check("one issue's failure still closes the rest, and the run exits 1",
          rc == 1 and ("issue", "close", "23") in stub.calls, (rc, stub.calls))
    stub = StubGh({1: merged, 30: pr30}, issues)
    check("--dry-run changes nothing", attempt(close_for_pr, 1, True, stub) == 0 and not stub.calls, stub.calls)

    shipped = {1410: {"state": "CLOSED", "labels": [LABEL]}, 1444: {"state": "CLOSED", "labels": []},
               1461: {"state": "CLOSED", "labels": [LABEL]}, 1462: {"state": "CLOSED", "labels": [LABEL]},
               1483: {"state": "CLOSED", "labels": [LABEL]},
               # Cited by the notes too, never labelled: present so the stub answers instead of warning.
               **{n: {"state": "CLOSED", "labels": []} for n in (621, 624, 1404, 1500, 1501)}}
    stub = StubGh({}, shipped, fail={1461})
    rc = attempt(mark_shipped, "v9.9.9", notes, dry_run=False, gh=stub)
    touched = sorted({c[2] for c in stub.calls})
    check("mark_shipped comments only fixed-on-dev issues, survives one failure, and exits 0",
          rc == 0 and touched == ["1410", "1462", "1483"], (rc, touched))

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
        return mark_shipped(args.shipped, open(args.notes, encoding="utf-8").read(), args.dry_run)
    ap.error("give --pr, or --shipped with --notes, or --selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
