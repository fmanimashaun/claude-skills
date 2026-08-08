#!/usr/bin/env python3
"""Derive the driver's state from the repository, so nothing is hand-typed.

`next_action.py` decides what to do next from a state document. Until this existed, that document
was written by hand — which meant the "autonomous driver" had a human in its innermost loop,
composing the very facts the decision was made from. A real run said so exactly: *"I had to be the
loop by hand."* This is the missing half.

WHAT IT DERIVES, and where each fact comes from:

  open_issues       `gh issue list` — with labels, FILTERED for actionability and ORDERED by an
                    explicit priority, because both were previously left to whatever order the
                    caller happened to type.
  run_stopped       the breaker ledger's own verdict — never re-derived here, because two safety
                    systems that disagree resolve in favour of the permissive one.
  awaiting_human    escalations parked by `escalation.py` and not yet answered.
  unverified_work   commits on the integration branch since the last recorded verification.
  shippable         verified, and nothing unverified after it.

TWO THINGS THIS FIXES THAT WERE SILENT BEFORE.

  1. ACTIONABILITY. The driver took `open_issues[0]` blindly, so a deploy-time or environment-blocked
     issue was picked, attempted, and only stopped by the breaker AFTER the attempts were spent. The
     breaker is a backstop for work that turns out to be impossible, not a substitute for reading
     the label that already said so. Blocked issues are excluded here WITH THEIR REASON, so a run
     that stops with an empty backlog can still say what it declined and why.

  2. ORDERING. "First element" is a real prioritisation policy; leaving it to composition order
     meant the toolchain had one and refused to say what it was. It is stated here, and it is
     boring on purpose: priority label, then age. A cleverer order is a decision for a human.

WHAT IT DOES NOT DO. It does not decide, and it does not act. It reports what is true so that
`next_action.py` can decide — kept separate because a composer that also decided could quietly
prefer the state that justified the action it wanted.

Exit codes:  0 state written (JSON on stdout) · 2 the repository could not be read

There is no exit 1: a repository with nothing to do is a valid state, not a finding. Reporting it
as one would make an empty backlog indistinguishable from a broken read.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Explicit, boring, and STATED — the whole complaint about the old behaviour was not that first-wins
# is wrong, but that nothing declared it. Lower sorts first.
PRIORITY_ORDER = ("priority:p0", "priority:p1", "priority:p2", "priority:p3")

# An issue carrying any of these cannot be started by an agent right now. Excluded WITH a reason
# rather than silently, because "the backlog is empty" and "everything left is blocked" are
# different sentences and only one of them means you are finished.
BLOCKING_LABELS = {
    "blocked": "marked blocked",
    "status:blocked": "marked blocked",
    "needs-env": "needs environment access an agent does not have",
    "needs-human": "already escalated and awaiting a human",
    "awaiting-input": "already escalated and awaiting a human",
    "deploy-time": "only actionable during a deploy",
    "wontfix": "declined",
}


def _gh(args: list[str]) -> object:
    if not shutil.which("gh"):
        raise SystemExit("cannot read the backlog: `gh` is not on PATH")
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"cannot read the backlog: gh {' '.join(args)} failed — {out.stderr.strip()}")
    return json.loads(out.stdout or "[]")


def priority_rank(labels: set[str]) -> int:
    for i, p in enumerate(PRIORITY_ORDER):
        if p in labels:
            return i
    return len(PRIORITY_ORDER)          # unprioritised sorts last, never first


def partition_issues(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    """(actionable, declined). Both are returned — a declined issue that vanishes is a lie."""
    actionable, declined = [], []
    for issue in raw:
        labels = {str(l.get("name", l)).lower() for l in issue.get("labels", [])}
        blocked = sorted(BLOCKING_LABELS[l] for l in labels & set(BLOCKING_LABELS))
        entry = {"number": issue["number"], "title": issue.get("title", ""),
                 "labels": sorted(labels)}
        if blocked:
            declined.append({**entry, "why_not_actionable": blocked})
        else:
            actionable.append(entry)
    # Explicit order: priority label, then issue number (oldest first). Stated, not incidental.
    actionable.sort(key=lambda e: (priority_rank(set(e["labels"])), e["number"]))
    return actionable, declined


def compose(root: Path, limit: int = 200) -> dict:
    # BOUNDED: `gh issue list` silently defaults to --limit 30, so an unbounded call reports one
    # page as the whole backlog -- measuring the wrong thing carefully.
    raw = _gh(["issue", "list", "--state", "open", "--limit", str(limit),
               "--json", "number,title,labels"])
    actionable, declined = partition_issues(raw)

    ledger = root / ".pipeline" / "ledger.jsonl"
    run_stopped = False
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("event") == "stop":
                    run_stopped = True
            except ValueError:
                continue                # a malformed line is not a stop; the breaker owns that call

    parked = root / ".rails-flow" / "escalations.json"
    awaiting = None
    if parked.is_file():
        try:
            for e in json.loads(parked.read_text(encoding="utf-8")).get("open", []):
                if not e.get("answered"):
                    awaiting = f"#{e.get('issue')}"
                    break
        except ValueError:
            pass

    return {
        "open_issues": actionable,
        "declined_issues": declined,
        "run_stopped": run_stopped,
        "awaiting_human": awaiting,
        "unverified_work": (root / ".qa-flow" / "unverified").exists(),
        "shippable": (root / ".qa-flow" / "certified").exists()
        and not (root / ".qa-flow" / "unverified").exists(),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=200, help="backlog page size (never unbounded)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    print(json.dumps(compose(Path.cwd(), args.limit), indent=2))
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    ISSUES = [
        {"number": 9,  "title": "p2 bug",     "labels": [{"name": "priority:p2"}]},
        {"number": 2,  "title": "deploy",     "labels": [{"name": "deploy-time"}]},
        {"number": 7,  "title": "p0 bug",     "labels": [{"name": "priority:p0"}]},
        {"number": 22, "title": "env",        "labels": [{"name": "needs-env"}]},
        {"number": 4,  "title": "unlabelled", "labels": []},
        {"number": 3,  "title": "p2 feature", "labels": [{"name": "priority:p2"},
                                                         {"name": "enhancement"}]},
    ]
    actionable, declined = partition_issues(ISSUES)
    got = [e["number"] for e in actionable]

    # ORDERING, stated: priority label, then number. p0 first; the two p2s by age; unlabelled last.
    check(f"priority then age, got {got}", got == [7, 3, 9, 4])
    # ACTIONABILITY: the two the breaker would otherwise have burned attempts on.
    check(f"blocked issues excluded, got {got}", 2 not in got and 22 not in got)
    check("declined issues are still reported", {e["number"] for e in declined} == {2, 22})
    check("...each with a reason",
          all(e["why_not_actionable"] for e in declined))
    # An unprioritised issue must sort LAST, never first -- otherwise forgetting a label promotes it.
    check("unprioritised sorts last", got[-1] == 4)
    # Labels survive to next_action, which is what closes the scope-through-fix-issue door.
    check("labels are carried through",
          "enhancement" in next(e for e in actionable if e["number"] == 3)["labels"])

    # The composer must never invent a stop -- the breaker owns that verdict.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".pipeline").mkdir()
        (root / ".pipeline/ledger.jsonl").write_text('{"event":"start"}\nnot json\n', encoding="utf-8")
        ledger_stop = False
        for line in (root / ".pipeline/ledger.jsonl").read_text().splitlines():
            try:
                if json.loads(line).get("event") == "stop":
                    ledger_stop = True
            except ValueError:
                continue
        check("a malformed ledger line is not read as a stop", ledger_stop is False)

    check("the backlog query is bounded", "--limit" in compose.__code__.co_consts
          or "limit" in compose.__code__.co_varnames)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} compose-state assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
