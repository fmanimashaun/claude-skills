#!/usr/bin/env python3
"""Say, on the server, when a new issue is missing one of the labels this repo declares.

Run:  GITHUB_REPOSITORY=owner/name python3 label_new_issue.py --issue 12            # after an issue is opened or labelled (CI does this)
      GITHUB_REPOSITORY=owner/name python3 label_new_issue.py --issue 12 --dry-run  # print what it would do
      python3 label_new_issue.py --selftest

Run it from the repository root: it reads `.rails-flow/issue-labels.json` there (`ISSUE_LABELS_CONFIG` overrides the path). GitHub
Actions sets `GITHUB_REPOSITORY`; a downstream project copies this file and `scaffold/label-new-issues.yml` (see setup-flow).

WHY (owner's decision, #1793). The label check used to live in a PreToolUse hook that parsed the text of a
`gh issue create` command. A shell gives that text its meaning only when it expands it, so the check could never be
complete (#1675, #1696, #1711-#1716). The server sees the issue itself, however it was filed: a template, `gh`, the
API, the web form. This is the server half; the hook's check is not removed here.

WHAT IT DOES. It reads the same declaration the hook reads, `.rails-flow/issue-labels.json` (`groups`: each with
`one_of` label patterns and an optional `when`). For an issue missing a group it adds the label `needs-labels` and
posts ONE comment naming what is missing and the labels that exist for it; the comment is edited in place when it
changes, never repeated. When the issue is later complete it removes `needs-labels` and says so in the same comment.

WHAT IT DELIBERATELY DOES NOT DO: guess a label. A wrong `comp:*` label sends the issue to the wrong queue and looks
labelled; a missing one is visible and is what `/maintainer-triage` exists to fix. The workflow runs on `opened` and
`labeled`. It cannot loop: a label added with the workflow's own token starts no further run.

THE SELFTEST DRIVES THE ENTRY POINT against a stubbed `gh`, the way `close_on_dev_merge.py` does, so a wrong flag or a
crash fails a named check.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

REPO = os.environ.get("GITHUB_REPOSITORY", "")
LABEL = "needs-labels"
LABEL_COLOR = "d93f0b"
LABEL_TEXT = "A new issue is missing a declared label group (comp, type or prio): see the comment"
MARK = "<!-- label-new-issue -->"
CONFIG = Path(os.environ.get("ISSUE_LABELS_CONFIG", ".rails-flow/issue-labels.json"))

Gh = Callable[..., str]


def real_gh(*args: str) -> str:
    out = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {out.stderr.strip() or 'failed'}")
    return out.stdout


def matches(label: str, pattern: str) -> bool:
    """The hook's rule: a trailing `*` is a prefix, anything else is exact."""
    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern


def missing_groups(labels: list[str], groups: list[dict]) -> list[dict]:
    """The declared groups the issue's labels do not satisfy. A group with a `when` applies only if one of the labels matches it."""
    out = []
    for g in groups:
        when = g.get("when")
        if when and not any(matches(x, when) for x in labels):
            continue
        if not any(matches(x, p) for x in labels for p in g.get("one_of", [])):
            out.append(g)
    return out


def describe(group: dict, existing: list[str]) -> str:
    """`one_of: [comp:*]` -> `comp:*` (one of: comp:rails-8, comp:hotwire, ...)."""
    patterns = group.get("one_of", [])
    have = sorted({x for x in existing for p in patterns if matches(x, p)})
    shown = ", ".join(have[:12]) + (", ..." if len(have) > 12 else "")
    return f"`{'` or `'.join(patterns)}`" + (f" ({shown})" if shown else "")


def comment_body(missing: list[dict], existing: list[str]) -> str:
    if not missing:
        return f"{MARK}\nAll declared label groups are present now; `{LABEL}` removed."
    lines = "\n".join(f"- {describe(g, existing)}" for g in missing)
    return (f"{MARK}\nThis issue is missing a declared label group, so it is not queued yet. Add one label from each:\n\n{lines}\n\n"
            f"`/maintainer-triage` can do it. `{LABEL}` is removed when the groups are complete.")


def load_groups(path: Path = CONFIG) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ValueError(f"{path}: no `groups` list")
    return groups


def ensure_label(gh: Gh) -> None:
    names = {x["name"] for x in json.loads(gh("label", "list", "-R", REPO, "--limit", "200", "--json", "name"))}
    if LABEL not in names:
        gh("label", "create", LABEL, "-R", REPO, "--color", LABEL_COLOR, "--description", LABEL_TEXT)


def run(issue: int, dry_run: bool, gh: Gh = real_gh, groups: list[dict] | None = None) -> int:
    api = json.loads(gh("api", f"repos/{REPO}/issues/{issue}"))
    if "pull_request" in api:
        print(f"#{issue}: is a pull request; left alone")
        return 0
    if api.get("state") != "open":
        print(f"#{issue}: {api.get('state')}, left alone")
        return 0
    groups = load_groups() if groups is None else groups
    labels = [x["name"] for x in api.get("labels", [])]
    existing = [x["name"] for x in json.loads(gh("label", "list", "-R", REPO, "--limit", "200", "--json", "name"))]
    missing = missing_groups(labels, groups)
    flagged = LABEL in labels
    if not missing and not flagged:
        print(f"#{issue}: complete, nothing to do")
        return 0
    comments = json.loads(gh("api", f"repos/{REPO}/issues/{issue}/comments", "--paginate", "--slurp"))
    mine = next((c for page in comments for c in page if MARK in (c.get("body") or "")), None)
    body = comment_body(missing, existing)
    if dry_run:
        print(f"#{issue}: would {'flag' if missing else 'unflag'} and {'edit' if mine else 'post'} the comment:\n{body}")
        return 0
    if missing:
        ensure_label(gh)
        if not flagged:
            gh("issue", "edit", str(issue), "-R", REPO, "--add-label", LABEL)
    elif flagged:
        gh("issue", "edit", str(issue), "-R", REPO, "--remove-label", LABEL)
    if mine:
        if mine.get("body") != body:
            gh("api", f"repos/{REPO}/issues/comments/{mine['id']}", "-X", "PATCH", "-f", f"body={body}")
    elif missing:
        gh("issue", "comment", str(issue), "-R", REPO, "--body", body)
    print(f"#{issue}: {'missing ' + str(len(missing)) + ' group(s)' if missing else 'complete, unflagged'}")
    return 0


class StubGh:
    """A `gh` that answers from a table and records every mutating call."""

    def __init__(self, issues: dict, comments: dict | None = None, labels: tuple = ("comp:a", "comp:b", "type:bug", "prio:P1", LABEL)):
        self.issues, self.comments, self.labels, self.calls = issues, comments or {}, list(labels), []

    def __call__(self, *args: str) -> str:
        if args[0] == "label" and args[1] == "list":
            return json.dumps([{"name": x} for x in self.labels])
        if args[0] == "api" and "--slurp" in args:
            return json.dumps([self.comments.get(int(args[1].split("/")[-2]), [])])
        if args[0] == "api" and "PATCH" in args:
            self.calls.append(("patch", args[1].rsplit("/", 1)[1], next(a for a in args if a.startswith("body="))))
            return ""
        if args[0] == "api":
            n = int(args[1].rsplit("/", 1)[1])
            return json.dumps(self.issues[n])
        self.calls.append(args[:2] + tuple(a for a in args[2:] if a in ("--add-label", "--remove-label", LABEL, "--body")))
        return ""


GROUPS = [{"one_of": ["comp:*"]}, {"one_of": ["type:*"]}, {"one_of": ["prio:*"]}]


def selftest() -> int:
    failures: list[str] = []
    total = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal total
        total += 1
        if not ok:
            failures.append(f"{label}{(' -- ' + str(detail)) if detail != '' else ''}")

    def attempt(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:          # noqa: BLE001 -- recorded, not swallowed
            return exc

    for name, labels, want in (
        ("no labels at all", [], 3), ("only a type", ["type:bug"], 2), ("comp and type", ["comp:a", "type:bug"], 1),
        ("all three", ["comp:a", "type:bug", "prio:P1"], 0), ("a prefix is not a substring", ["xcomp:a", "type:bug", "prio:P1"], 1),
        ("the flag label alone", [LABEL], 3),
    ):
        got = len(missing_groups(labels, GROUPS))
        check(f"missing_groups: {name}", got == want, f"expected {want}, got {got}")
    when = [{"when": "type:bug", "one_of": ["prio:*"]}]
    check("a `when` group does not apply to another type", missing_groups(["type:feature"], when) == [])
    check("a `when` group applies when its label is present", len(missing_groups(["type:bug"], when)) == 1)
    check("an exact pattern needs the exact label", len(missing_groups(["comp:ab"], [{"one_of": ["comp:a"]}])) == 1)

    def issue(labels, state="open", pr=False):
        return {"state": state, "labels": [{"name": x} for x in labels], **({"pull_request": {}} if pr else {})}

    gh = StubGh({1: issue([]), 2: issue(["comp:a", "type:bug", "prio:P1"]), 3: issue(["comp:a", "type:bug", "prio:P1", LABEL]),
                 4: issue([], state="closed"), 5: issue([], pr=True), 6: issue(["type:bug", LABEL])},
                comments={3: [{"id": 33, "body": f"{MARK}\nold"}], 6: [{"id": 66, "body": comment_body(missing_groups(["type:bug"], GROUPS), gh_labels := ["comp:a", "comp:b", "type:bug", "prio:P1", LABEL])}]})
    rc = attempt(run, 1, False, gh, GROUPS)
    check("an empty issue exits 0", rc == 0, rc)
    check("an empty issue gets the flag", any("--add-label" in c and LABEL in c for c in gh.calls), gh.calls)
    check("an empty issue gets one comment", sum(1 for c in gh.calls if c[:2] == ("issue", "comment")) == 1, gh.calls)
    gh.calls.clear()
    attempt(run, 2, False, gh, GROUPS)
    check("a complete issue is left alone", gh.calls == [], gh.calls)
    gh.calls.clear()
    attempt(run, 3, False, gh, GROUPS)
    check("a complete issue that was flagged is unflagged", any("--remove-label" in c for c in gh.calls), gh.calls)
    check("the old comment is edited, not repeated", any(c[0] == "patch" and c[1] == "33" for c in gh.calls) and not any(c[:2] == ("issue", "comment") for c in gh.calls), gh.calls)
    gh.calls.clear()
    attempt(run, 4, False, gh, GROUPS)
    check("a closed issue is left alone", gh.calls == [], gh.calls)
    attempt(run, 5, False, gh, GROUPS)
    check("a pull request is left alone", gh.calls == [], gh.calls)
    attempt(run, 6, False, gh, GROUPS)
    check("a still-incomplete flagged issue is not flagged or commented again", gh.calls == [], gh.calls)
    attempt(run, 1, True, gh, GROUPS)
    check("--dry-run changes nothing", gh.calls == [], gh.calls)
    body = comment_body(missing_groups([], GROUPS), ["comp:a", "type:bug", "prio:P1"])
    check("the comment carries the marker, so it can be found again", body.startswith(MARK), body)
    check("the comment names each missing group", all(p in body for p in ("comp:*", "type:*", "prio:*")), body)
    check("the comment lists the labels that exist", "comp:a" in body, body)
    with tempfile.TemporaryDirectory() as td:
        sample = Path(td) / "issue-labels.json"
        sample.write_text(json.dumps({"groups": GROUPS}), encoding="utf-8")
        check("a declaration parses into its groups", load_groups(sample) == GROUPS)
        sample.write_text("{}", encoding="utf-8")
        check("a declaration with no `groups` is an error, not an empty rule", isinstance(attempt(load_groups, sample), ValueError))
    if failures:
        print(f"label_new_issue selftest: {len(failures)} failure(s) of {total}")
        for f in failures:
            print(f"  FAIL {f}")
        return 1
    print(f"label_new_issue selftest: {total} checks passed")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--issue", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.issue:
        ap.error("--issue N is required")
    if not REPO:
        ap.error("GITHUB_REPOSITORY (owner/name) is required")
    try:
        return run(a.issue, a.dry_run)
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"::error::{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
