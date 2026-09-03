#!/usr/bin/env python3
"""GATE: may work on these issues start now? Refuses when a named issue waits on open work.

    python3 check_issue_ready.py 42 57      # GATE: READY on stdout (exit 0), or refusal on stderr (exit 1)
    python3 check_issue_ready.py --queue    # REPORT: the whole open tracker as a computed, ranked queue
    python3 check_issue_ready.py --selftest

`--queue` is the triage half (#849 part 1): ready-now issues first, ordered by priority label
(`prio:P1` > `P2` > `P3` > unranked), bugs before features, oldest first; then blocked issues under
what blocks them; `needs-info` skipped and said so; and a coverage line -- `N/M open issues
declare edges` -- because an order computed from three declared edges out of forty issues is worth
having and dishonest to report without saying so. It exits non-zero and prints NO queue when the
graph is wrong (a cycle, an edge to an issue that does not exist): those are filing errors to fix,
not something to hand-wave past by ranking on priority, which is the habit the tool replaces.

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
                                    "--json", "number,title,labels,createdAt,body"))


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


PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
BUG_LABELS = {"bug", "type:bug", "security", "type:security", "type:incorrect-doctrine"}
SKIP_LABELS = {"needs-info", "duplicate", "wontfix"}


def _labels(issue: dict) -> set[str]:
    return {(lab["name"] if isinstance(lab, dict) else str(lab)).strip() for lab in issue.get("labels", [])}


def _priority(labels: set[str]) -> str | None:
    """`prio:P1`, `P1`, `priority:P1` and `p1` all rank as P1; anything else is unranked."""
    for lab in labels:
        tail = lab.rsplit(":", 1)[-1].upper()
        if tail in PRIORITY_RANK:
            return tail
    return None


def queue(gh: Gh) -> tuple[list[str], list[str]]:
    """`(report_lines, graph_errors)`. Errors mean NO queue: a wrong graph is a filing error, not noise."""
    issues = gh.open_issues()
    by_number = {i["number"]: i for i in issues}
    open_numbers = set(by_number)
    edges: dict[int, set[int]] = {n: set() for n in open_numbers}       # n waits on …
    declared = 0
    for issue in issues:
        e = parse_edges(issue.get("body", ""))
        if e["depends-on"] or e["blocks"]:
            declared += 1
        edges[issue["number"]] |= e["depends-on"]
        for target in e["blocks"]:
            edges.setdefault(target, set()).add(issue["number"])
    errors: list[str] = []
    # An edge to an issue that is neither open nor closed is a typo, and a typo'd dependency is
    # silently satisfied forever. Ask the tracker once per unknown number.
    for n, waits in sorted(edges.items()):
        for w in sorted(waits):
            if w not in open_numbers and gh.view(w) is None:
                errors.append(f"#{n} depends on #{w}, which is not in this tracker")
    # A cycle among open issues means nothing in it can ever be ready.
    colour: dict[int, int] = {}

    def visit(n: int, path: list[int]) -> None:
        colour[n] = 1
        for w in sorted(edges.get(n, ())):
            if w not in open_numbers:
                continue
            if colour.get(w) == 1:
                cycle = path[path.index(w):] + [w]
                errors.append("cycle: " + " -> ".join(f"#{x}" for x in cycle))
            elif colour.get(w) is None:
                visit(w, path + [w])
        colour[n] = 2
    for n in sorted(open_numbers):
        if colour.get(n) is None:
            visit(n, [n])
    if errors:
        return [], sorted(set(errors))

    def key(issue: dict) -> tuple:
        labels = _labels(issue)
        prio = _priority(labels)
        return (PRIORITY_RANK.get(prio, 9), 0 if labels & BUG_LABELS else 1, issue.get("createdAt", ""), issue["number"])

    ready, blocked, skipped = [], [], []
    for issue in sorted(issues, key=key):
        n = issue["number"]
        labels = _labels(issue)
        if labels & SKIP_LABELS:
            skipped.append(issue)
            continue
        open_waits = sorted(w for w in edges.get(n, ()) if w in open_numbers)
        (blocked if open_waits else ready).append((issue, open_waits))

    def row(issue: dict, tail: str = "") -> str:
        labels = _labels(issue)
        prio = _priority(labels) or "--"
        kind = "bug" if labels & BUG_LABELS else ("feature" if labels & {"feature", "type:feature", "enhancement"} else "----")
        return f"  #{issue['number']:<5} {prio:<3} {kind:<8} {issue.get('createdAt', '')[:10]}  {issue.get('title', '')[:70]}{tail}"

    out = [f"READY ({len(ready)}) — P1 > P2 > P3 > unranked, bugs before features, oldest first"]
    out += [row(i) for i, _ in ready] or ["  (none)"]
    out.append(f"BLOCKED ({len(blocked)}) — never rank a blocked issue above its own blocker")
    out += [row(i, "  waits on " + ", ".join(f"#{w}" for w in ws)) for i, ws in blocked] or ["  (none)"]
    out.append(f"SKIPPED ({len(skipped)}) — labelled " + "/".join(sorted(SKIP_LABELS)))
    out += [row(i) for i in skipped] or ["  (none)"]
    out.append(f"coverage: {declared}/{len(issues)} open issues declare edges — the order rests on those; "
               "the rest is priority and age, which is a guess the tracker has not confirmed")
    return out, []


def selftest() -> int:
    checks = 0
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    class FakeGh(Gh):
        def __init__(self, issues: dict[int, tuple], meta: dict[int, dict] | None = None):
            self.issues = issues  # number -> (state, body)
            self.meta = meta or {}  # number -> {"title", "labels", "createdAt"}

        def available(self) -> bool:
            return True

        def view(self, number: int) -> dict | None:
            if number not in self.issues:
                return None
            state, body = self.issues[number]
            return {"number": number, "state": state, "body": body}

        def open_issues(self) -> list[dict]:
            return [{"number": n, "body": b, **self.meta.get(n, {})}
                    for n, (s, b) in self.issues.items() if s == "OPEN"]

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

    # ---- --queue (#849 part 1): computed, not reasoned -----------------------------------------
    def meta(title, *labels, created="2026-08-01"):
        return {"title": title, "labels": [{"name": lab} for lab in labels], "createdAt": created + "T00:00:00Z"}
    gq = FakeGh(
        {20: ("OPEN", ""), 21: ("OPEN", ""), 22: ("OPEN", ""), 23: ("OPEN", "depends-on: #20"),
         24: ("OPEN", ""), 25: ("OPEN", ""), 26: ("OPEN", "depends-on: #12"), 12: ("CLOSED", "")},
        {20: meta("p2 bug, older", "prio:P2", "bug", created="2026-07-01"),
         21: meta("p1 feature", "prio:P1", "feature"),
         22: meta("p2 feature", "P2", "enhancement"),
         23: meta("blocked p1 bug", "prio:P1", "type:bug"),
         24: meta("unranked", created="2026-06-01"),
         25: meta("no repro yet", "needs-info", "bug"),
         26: meta("waits on a CLOSED issue", "prio:P3")})
    lines_, errs = queue(gq)
    text = "\n".join(lines_)
    check("a sound graph yields a queue and no errors", lines_ and not errs, f"{errs}")
    def section(name: str) -> list[int]:
        rows, on = [], False
        for l in lines_:
            if not l.startswith("  "):
                on = l.startswith(name)
            elif on and l.startswith("  #"):
                rows.append(int(l.split()[0][1:]))
        return rows
    ready_rows = section("READY")
    pos = lambda n: ready_rows.index(n) if n in ready_rows else 10**6  # noqa: E731 -- absent sorts last, never raises
    check("READY is ordered P1 before P2 before unranked", pos(21) < pos(20) < pos(24) < 10**6, f"{ready_rows}")
    check("...and within a priority, bugs before features", pos(20) < pos(22) < 10**6, f"{ready_rows}")
    check("a P1 that is BLOCKED is not ranked as ready", 23 not in ready_rows and 23 in section("BLOCKED"), f"ready={ready_rows} blocked={section('BLOCKED')}")
    check("...and is listed under what blocks it", "#23" in text and "waits on #20" in text, f"{text}")
    check("an issue waiting only on a CLOSED issue is ready", 26 in ready_rows, f"{ready_rows}")
    check("needs-info is skipped and said so", text.index("SKIPPED") < text.index("#25"), f"{text}")
    check("the coverage line counts issues that declare edges", "coverage: 2/7 open issues declare edges" in text, f"{text}")
    check("a bare `P2` label ranks like `prio:P2`", pos(22) < pos(24) < 10**6, f"{ready_rows}")
    _, errs = queue(FakeGh({30: ("OPEN", "depends-on: #31"), 31: ("OPEN", "depends-on: #30")}))
    check("a cycle is a graph error, and there is NO queue", errs and any("cycle" in e for e in errs), f"{errs}")
    _, errs = queue(FakeGh({40: ("OPEN", "depends-on: #999")}))
    check("an edge to an issue not in the tracker is a graph error", errs and "not in this tracker" in errs[0], f"{errs}")
    lines_, errs = queue(FakeGh({}))
    check("an empty tracker is an empty queue, not a crash", not errs and "READY (0)" in lines_[0], f"{lines_} {errs}")

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
    ap.add_argument("--queue", action="store_true", help="report the whole open tracker as a ranked queue")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.issues and not args.queue:
        ap.print_usage(sys.stderr)
        return 2
    gh = Gh()
    if not gh.available():
        print("check_issue_ready: `gh` is not on PATH — the tracker cannot be read, so this is not a READY",
              file=sys.stderr)
        return 2
    try:
        if args.queue:
            report, errors = queue(gh)
            if errors:
                print("GRAPH ERROR — fix the issue bodies, then re-run; no queue is printed from a wrong graph:",
                      file=sys.stderr)
                for line in errors:
                    print(f"  {line}", file=sys.stderr)
                return 1
            print("\n".join(report))
            return 0
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
