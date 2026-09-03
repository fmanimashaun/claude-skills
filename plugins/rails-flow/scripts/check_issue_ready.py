#!/usr/bin/env python3
"""GATE: may work on these issues start now? Refuses when a named issue waits on open work.

    python3 check_issue_ready.py 42 57      # READY on stdout (exit 0), or refusal on stderr (exit 1)
    python3 check_issue_ready.py --selftest

"Take the head of the queue" is a claim nothing checked (#849, after the marketplace's own #133).
An issue's body can declare what it waits on, in the same shape the marketplace's `issue_graph.py`
reads, so a project that adopts the convention gets the same gate:

    ```deps
    depends-on: #93, #104
    blocks: #120
    ```

or bare strict lines `depends-on: #93` outside any fence. `depends-on: #A` means A must be closed
first; `blocks: #B` is the same edge stated from the other end, so it is read from EVERY open
issue, not only the ones named. Anything else -- prose that happens to say "depends on", a Ruby
`depends_on: :account` inside a code sample -- is not an edge: the syntax is deliberately strict
so a sentence cannot be mistaken for a dependency.

Edges BETWEEN the issues you named are satisfied by the branch itself: a grouped branch declares
its whole set in one call and learns only which member goes first.

Exit 0: every named issue is open and waits on nothing open.  Exit 1: refused; stdout is left
empty and the reasons go to stderr, so `$(…)` in a script gets nothing to act on.  Exit 2: cannot
answer -- no `gh`, a failed call, no issue named. A tracker that cannot be read is not a READY.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys

KEYS = ("depends-on", "blocks")
_DEPS_FENCE = re.compile(r"^[ \t]*```[ \t]*deps[ \t]*\r?$\n(.*?)^[ \t]*```", re.M | re.S)
_ANY_FENCE = re.compile(r"^[ \t]*```([^\n]*)\r?$\n(.*?)^[ \t]*```", re.M | re.S)
_STRICT = re.compile(r"^[ \t]*(depends-on|blocks)[ \t]*:[ \t]*(#\d+(?:[ \t]*,[ \t]*#\d+)*)[ \t]*$", re.M)
_REF = re.compile(r"#(\d+)")


class Gh:
    """The two reads this gate makes. Subclassed by the selftest, never mocked at the subprocess."""

    def available(self) -> bool:
        return shutil.which("gh") is not None

    def _run(self, *args: str) -> str:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise RuntimeError(f"gh {' '.join(args[:3])} failed: {done.stderr.strip()[:200]}")
        return done.stdout

    def view(self, number: int) -> dict | None:
        try:
            return json.loads(self._run("issue", "view", str(number), "--json", "number,state,body"))
        except RuntimeError as exc:
            if "Could not resolve" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    def open_issues(self) -> list[dict]:
        # Bounded on purpose: `gh issue list` defaults to 30 and reports a page as the total.
        return json.loads(self._run("issue", "list", "--state", "open", "--limit", "200",
                                    "--json", "number,body"))


def parse_edges(body: str) -> dict[str, set[int]]:
    """`{"depends-on": {…}, "blocks": {…}}` from a body -- the `deps` fence first, else bare strict lines.

    Other fences are removed before the bare scan, so a code sample cannot contribute an edge.
    """
    edges: dict[str, set[int]] = {k: set() for k in KEYS}
    body = body or ""
    fences = _DEPS_FENCE.findall(body)
    if fences:
        text = "\n".join(fences)
    else:
        text = _ANY_FENCE.sub("", body)  # strip every other fence -- `depends_on: :account` lives there
    for key, refs in _STRICT.findall(text):
        edges[key].update(int(n) for n in _REF.findall(refs))
    return edges


def readiness(named: list[int], gh: Gh) -> tuple[list[str], list[str]]:
    """`(ready_lines, refusals)`. Refusals are complete: every reason, not the first."""
    refusals: list[str] = []
    ready: list[str] = []
    if not named:
        return [], ["no issue named"]
    open_list = gh.open_issues()
    open_numbers = {i["number"] for i in open_list}
    # `blocks: #B` on any open issue A is an edge B depends-on A. Read it from every open body.
    blocked_by: dict[int, set[int]] = {}
    for issue in open_list:
        for target in parse_edges(issue.get("body", "")).get("blocks", set()):
            blocked_by.setdefault(target, set()).add(issue["number"])
    named_set = set(named)
    for n in named:
        record = gh.view(n)
        if record is None:
            refusals.append(f"#{n}: not in this tracker")
            continue
        if record.get("state", "").upper() != "OPEN":
            refusals.append(f"#{n}: already {record.get('state', '?').lower()} — nothing to start")
            continue
        waits = parse_edges(record.get("body", "")).get("depends-on", set()) | blocked_by.get(n, set())
        waits -= named_set  # edges inside the named set are satisfied by the branch
        open_waits = sorted(w for w in waits if w in open_numbers)
        if open_waits:
            refusals.append(f"#{n}: waits on open work — {', '.join(f'#{w}' for w in open_waits)}")
            continue
        note = "" if waits else "  (declares no edges: the tracker names no blocker, not that none exists)"
        ready.append(f"READY #{n}{note}")
    return ready, refusals


def selftest() -> int:
    checks = 0
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    class FakeGh(Gh):
        def __init__(self, issues: dict[int, tuple[str, str]]):
            self.issues = issues  # number -> (state, body)

        def available(self) -> bool:
            return True

        def view(self, number: int) -> dict | None:
            if number not in self.issues:
                return None
            state, body = self.issues[number]
            return {"number": number, "state": state, "body": body}

        def open_issues(self) -> list[dict]:
            return [{"number": n, "body": b} for n, (s, b) in self.issues.items() if s == "OPEN"]

    e = parse_edges("```deps\ndepends-on: #93, #104\nblocks: #120\n```\n")
    check("a deps fence yields both edge kinds", e["depends-on"] == {93, 104} and e["blocks"] == {120}, f"{e}")
    e = parse_edges("Some prose.\n\ndepends-on: #7\n")
    check("a bare strict line is an edge", e["depends-on"] == {7}, f"{e}")
    e = parse_edges("This depends on #7 being done first, honestly.\n")
    check("prose saying 'depends on' is NOT an edge -- the syntax is strict", e["depends-on"] == set(), f"{e}")
    e = parse_edges("Use the syntax below:\n\n```md\ndepends-on: #99\n```\n\ndepends-on: #3\n")
    check("a fenced SAMPLE of the syntax is not an edge; the bare line beside it is",
          e["depends-on"] == {3}, f"{e}")
    e = parse_edges("```ruby\nclass Invoice\n  depends_on: :account\nend\n```\n")
    check("a Ruby idiom inside a code fence is not an edge", e["depends-on"] == set(), f"{e}")

    gh = FakeGh({10: ("OPEN", ""), 11: ("OPEN", "depends-on: #10"), 12: ("CLOSED", ""),
                 13: ("OPEN", "depends-on: #12"), 14: ("OPEN", "blocks: #15"), 15: ("OPEN", "")})
    r, f = readiness([10], gh)
    check("an open issue with no edges is READY", r and not f, f"{r} {f}")
    check("...and the note says the tracker names no blocker", "declares no edges" in r[0], f"{r}")
    r, f = readiness([11], gh)
    check("an issue whose depends-on is OPEN is refused", not r and f and "#11" in f[0] and "#10" in f[0], f"{r} {f}")
    r, f = readiness([13], gh)
    check("an issue whose depends-on is CLOSED is READY", r and not f, f"{r} {f}")
    r, f = readiness([15], gh)
    check("`blocks:` declared on ANOTHER open issue is read as a dependency", not r and "#14" in f[0], f"{r} {f}")
    r, f = readiness([10, 11], gh)
    check("edges between the named issues are satisfied by the branch (grouping)", len(r) == 2 and not f, f"{r} {f}")
    r, f = readiness([12], gh)
    check("a closed issue is refused, not started twice", not r and "already closed" in f[0], f"{r} {f}")
    r, f = readiness([99], gh)
    check("an issue absent from the tracker is refused", not r and "not in this tracker" in f[0], f"{r} {f}")
    r, f = readiness([], gh)
    check("naming no issue is a refusal, not a vacuous READY", not r and f, f"{r} {f}")
    r, f = readiness([11, 12], gh)
    check("refusals are complete -- every reason, not the first", len(f) == 2, f"{f}")

    if failures:
        print(f"check_issue_ready selftest: {len(failures)} of {checks} checks FAILED", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"check_issue_ready selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("issues", nargs="*", type=int, help="issue numbers the branch will carry")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.issues:
        ap.print_usage(sys.stderr)
        return 2
    gh = Gh()
    if not gh.available():
        print("check_issue_ready: `gh` is not on PATH — the tracker cannot be read, so this is not a READY",
              file=sys.stderr)
        return 2
    try:
        ready, refusals = readiness(args.issues, gh)
    except RuntimeError as exc:
        print(f"check_issue_ready: {exc}", file=sys.stderr)
        return 2
    if refusals:
        print("REFUSED — work the blocker first, or say in the PR body why you are going out of order:",
              file=sys.stderr)
        for line in refusals:
            print(f"  {line}", file=sys.stderr)
        return 1
    for line in ready:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
