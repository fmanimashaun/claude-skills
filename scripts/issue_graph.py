#!/usr/bin/env python3
"""Compute the work queue from declared issue dependencies, instead of reasoning it out by hand.

Run:  python3 scripts/issue_graph.py                     # fetch the tracker via gh, report
      python3 scripts/issue_graph.py --json              # same, machine-readable
      python3 scripts/issue_graph.py --ready 109 110     # GATE: may this work start now?
      python3 scripts/issue_graph.py --from issues.json  # from a saved `gh issue list --json` dump
      python3 scripts/issue_graph.py --selftest          # prove the rules fire AND stay silent

WHY THIS EXISTS (#133). The tracker carries real dependencies — #93 → #104 → #94/#90, #125 → #127
— but every one of them lives as prose inside an issue body. Answering "what should I work on
next?" therefore means re-reading many issues and re-deriving the ordering, which produces a
different answer each time as the tracker grows. A queue asserted in prose is not a queue.

WHAT MAKES IT A GATE, NOT A REPORT. The reports below are advisory. The *graph* is not: a cycle,
an edge to an issue that does not exist, a typo'd key, a declaration outside its fence — each is a
filing error and each exits non-zero. And when the graph is broken the queue is **not printed at
all**, only the errors. A ranked queue computed from a graph we already know is wrong is worse
than no queue, because it reads exactly like a correct one. That split — fail closed for gates,
fail open for advisories — is the general rule now recorded in `docs/doctrine/harness-doctrine.md` §5
(which also gives the scoping this tool relies on: fail closed for what the gate guards, exit 0
otherwise), restated here as this tool's own contract.

AND THE QUEUE ITSELF IS A GATE, AT THE POINT OF USE (`--ready`). Reporting an order changes
nothing on its own: `/maintainer-work` said "take the head of the triaged queue" while nothing
checked that it had, which is the same prose-not-a-queue problem one level up. `--ready 109 110`
answers one question — may this be started now, as one branch? — and **exits non-zero when the
answer is no**: an issue waiting on open work, an issue already closed, an issue absent from the
tracker, or a graph too broken to answer from. Edges *between* the requested issues are satisfied
by the branch itself, because grouping related issues onto one branch is this repo's default shape
(CLAUDE.md, *Grouping related issues on one branch*); edges leaving the set are not.

WHY IT STILL SAYS WHAT IT DOES NOT KNOW. A READY verdict on an issue that declares no edges means
the tracker names no blocker, not that nothing blocks it. With the backfill incomplete that is the
common case, so every such verdict carries the caveat — reporting "no declared blocker" as "no
blocker" is the unverified-negative class, and it would be a green light nobody could calibrate.

THE DECLARATION FORMAT. One fenced block in the issue body, tagged `deps`:

    ```deps
    depends-on: #93, #104
    blocks: #94, #90
    part-of: #89
    ```

`depends-on: #A` means A must finish first; `blocks: #B` is the same edge stated from the other
end; `part-of: #E` is epic membership and carries no ordering. Prose still explains *why* — this
block only makes the edge machine-readable. Full documentation: docs/doctrine/issue-dependency-graph.md.

WHY THE TAG IS REQUIRED, when #133 sketched a bare fence. An untagged fence cannot be told from a
code sample, and `depends_on: :account` is an ordinary Rails idiom that would be read as an edge.
Requiring the tag makes extraction unambiguous — but strictness that silently drops a
near-miss is the `gate-that-cannot-fail` class, so the two near-misses are *detected and
reported*, never ignored: a fence that is nothing but declarations under the wrong tag, and a
declaration line loose in prose. Being strict is only safe because missing the tag is an error
rather than a silence. (Maintainer decision, recorded on #133 — this is our own format, so it has
no upstream to cite.)

Stdlib only, no network beyond `gh`.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# `gh issue list` defaults to --limit 30, so an unbounded call reports a page as the total —
# the unverified-negative class that told a maintainer "30 open issues" when there were 42
# (#211). Bounding alone is not enough: a bound silently *reached* is the same lie with a
# bigger number, so `fetch_issues` treats a full page as an error rather than a total.
GH_LIMIT = 500

KEYS = ("depends-on", "blocks", "part-of")

# A fence tagged exactly `deps`. Non-greedy body, closing fence at line start.
_DEPS_FENCE = re.compile(r"^[ \t]*```[ \t]*deps[ \t]*\r?$\n(.*?)^[ \t]*```", re.M | re.S)
# Any fence at all, with its info string — used to find mistagged blocks and to blank out
# code samples before scanning prose.
_ANY_FENCE = re.compile(r"^[ \t]*```([^\n]*)\r?$\n(.*?)^[ \t]*```", re.M | re.S)
# A line inside a deps block: `key: value`. Deliberately accepts ANY key so a typo becomes a
# reported error rather than a line that vanishes.
_LINE = re.compile(r"^[ \t]*(?P<key>[A-Za-z][A-Za-z_ -]*?)[ \t]*:[ \t]*(?P<refs>.*?)[ \t]*$")
# A declaration in its canonical form and nothing else. Used for the two near-miss detectors,
# where the whole point is to catch only what is unmistakably a declaration: prose that merely
# mentions an issue ("Blocks #94 and #90, see above") must stay silent or the checks get
# switched off.
_STRICT = re.compile(
    r"^[ \t]*(?:depends-on|blocks|part-of)[ \t]*:[ \t]*#\d+(?:[ \t]*,[ \t]*#\d+)*[ \t]*$",
    re.I,
)
_REF = re.compile(r"^#(\d+)$")

PRIORITIES = ("prio:P1", "prio:P2", "prio:P3")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    state: str                       # "OPEN" / "CLOSED", as `gh --json state` reports it
    labels: tuple[str, ...] = ()
    body: str = ""

    @property
    def is_open(self) -> bool:
        return self.state.upper() == "OPEN"

    @property
    def priority(self) -> str | None:
        for label in PRIORITIES:
            if label in self.labels:
                return label
        return None


@dataclass
class Graph:
    issues: dict[int, Issue]
    # (before, after): `before` must finish first. A set, so #10 saying `blocks: #11` and #11
    # saying `depends-on: #10` — the same edge from both ends — is one edge, not a 2-cycle.
    edges: set[tuple[int, int]] = field(default_factory=set)
    part_of: dict[int, set[int]] = field(default_factory=dict)
    declared: set[int] = field(default_factory=set)   # issues carrying at least one declaration
    problems: list[str] = field(default_factory=list)

    def successors(self, number: int) -> list[int]:
        return sorted(after for before, after in self.edges if before == number)

    def predecessors(self, number: int) -> list[int]:
        return sorted(before for before, after in self.edges if after == number)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _blank_fences(body: str) -> str:
    """Replace every fenced block with blank lines, preserving line numbering."""
    def blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return _ANY_FENCE.sub(blank, body)


def parse_body(number: int, body: str) -> tuple[list[tuple[str, int]], list[str]]:
    """Declarations `(key, target)` and problems for one issue body."""
    declarations: list[tuple[str, int]] = []
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()

    for match in _DEPS_FENCE.finditer(body):
        for raw in match.group(1).splitlines():
            if not raw.strip():
                continue
            line = _LINE.match(raw)
            if not line:
                problems.append(
                    f"#{number}: malformed line in ```deps block: {raw.strip()!r} — expected "
                    f"`<key>: #n, #n` with key one of {', '.join(KEYS)}"
                )
                continue
            key = line.group("key").strip().lower()
            if key not in KEYS:
                problems.append(
                    f"#{number}: unknown key {line.group('key').strip()!r} in ```deps block — "
                    f"expected one of {', '.join(KEYS)}. A typo'd key declares no edge, and "
                    "silently declaring nothing is the failure this check exists to prevent"
                )
                continue
            refs = line.group("refs")
            if not refs:
                problems.append(f"#{number}: `{key}:` declares no issue")
                continue
            for token in refs.split(","):
                token = token.strip()
                ref = _REF.match(token)
                if not ref:
                    problems.append(
                        f"#{number}: {key!r} references {token!r}, which is not a `#n` issue"
                    )
                    continue
                target = int(ref.group(1))
                if target == number:
                    problems.append(f"#{number}: `{key}: #{number}` references itself")
                    continue
                if (key, target) in seen:      # a repeated ref is sloppy, not wrong
                    continue
                seen.add((key, target))
                declarations.append((key, target))

    # -- near miss 1: declarations under the wrong fence tag ---------------------------
    # Only when the block is nothing BUT declarations. A block that also carries prose is a
    # sample being quoted, and firing on it would make the check noisy enough to be disabled.
    for match in _ANY_FENCE.finditer(body):
        if match.group(1).strip().lower() == "deps":
            continue
        lines = [line for line in match.group(2).splitlines() if line.strip()]
        if lines and all(_STRICT.match(line) for line in lines):
            tag = match.group(1).strip() or "(untagged)"
            problems.append(
                f"#{number}: a fence tagged {tag!r} contains only dependency declarations — "
                "tag it ```deps or it declares nothing"
            )

    # -- near miss 2: a declaration loose in prose -------------------------------------
    for lineno, line in enumerate(_blank_fences(body).splitlines(), start=1):
        if _STRICT.match(line):
            problems.append(
                f"#{number}: line {lineno} is a dependency declaration outside a ```deps "
                f"block: {line.strip()!r} — it declares nothing where it stands"
            )

    return declarations, problems


def build(issues: list[Issue]) -> Graph:
    graph = Graph(issues={issue.number: issue for issue in issues})
    for issue in sorted(issues, key=lambda i: i.number):
        declarations, problems = parse_body(issue.number, issue.body)
        graph.problems.extend(problems)
        if declarations:
            graph.declared.add(issue.number)
        for key, target in declarations:
            if target not in graph.issues:
                graph.problems.append(
                    f"#{issue.number}: `{key}: #{target}` references an issue that is not in the "
                    "tracker — a dangling edge silently drops out of every ordering"
                )
                continue
            if key == "depends-on":
                graph.edges.add((target, issue.number))
            elif key == "blocks":
                graph.edges.add((issue.number, target))
            else:
                graph.part_of.setdefault(issue.number, set()).add(target)
    graph.problems.extend(_find_cycles(graph))
    return graph


def _cycle_in(adjacency: dict[int, list[int]]) -> list[int] | None:
    """One cycle as a node list, or None. Iterative DFS — a deep chain must not blow the stack."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[int, int] = {}
    for start in sorted(adjacency):
        if colour.get(start, WHITE) != WHITE:
            continue
        stack: list[tuple[int, int]] = [(start, 0)]
        path: list[int] = []
        colour[start] = GREY
        path.append(start)
        while stack:
            node, index = stack[-1]
            children = adjacency.get(node, [])
            if index < len(children):
                stack[-1] = (node, index + 1)
                child = children[index]
                state = colour.get(child, WHITE)
                if state == GREY:
                    return path[path.index(child):] + [child]
                if state == WHITE:
                    colour[child] = GREY
                    path.append(child)
                    stack.append((child, 0))
            else:
                colour[node] = BLACK
                path.pop()
                stack.pop()
    return None


def _find_cycles(graph: Graph) -> list[str]:
    problems: list[str] = []
    dependency: dict[int, list[int]] = {}
    for before, after in sorted(graph.edges):
        dependency.setdefault(before, []).append(after)
    cycle = _cycle_in(dependency)
    if cycle:
        problems.append(
            "dependency cycle: " + " → ".join(f"#{n}" for n in cycle)
            + " — nothing in it can ever be ready, so it is a filing error"
        )
    parents: dict[int, list[int]] = {n: sorted(p) for n, p in graph.part_of.items()}
    cycle = _cycle_in(parents)
    if cycle:
        problems.append(
            "part-of cycle: " + " → ".join(f"#{n}" for n in cycle) + " — an epic cannot contain itself"
        )
    return problems


# ---------------------------------------------------------------------------
# Reports (only ever computed on a graph that validated)
# ---------------------------------------------------------------------------


def _open_predecessors(graph: Graph, number: int) -> list[int]:
    return [p for p in graph.predecessors(number) if graph.issues[p].is_open]


def chain_lengths(graph: Graph) -> dict[int, int]:
    """Longest chain of OPEN work starting at each open issue, itself included.

    Closed issues are done, so they are not on anybody's remaining path.

    Iterative post-order, for the same reason `_cycle_in` is: chain depth is bounded by the
    tracker, not by us, and Python's stack is ~1000 frames. The first version of this function
    recursed while the cycle detector three functions up did not — an inconsistency inside one
    module, which is how the deep-chain case ends up untested in exactly one of the two places
    it matters. Pinned by a 1500-issue fixture that raises RecursionError on the old code.
    """
    lengths: dict[int, int] = {}
    visiting: set[int] = set()
    for start in sorted(number for number, issue in graph.issues.items() if issue.is_open):
        if start in lengths:
            continue
        stack: list[tuple[int, bool]] = [(start, False)]
        while stack:
            number, expanded = stack.pop()
            if expanded:
                visiting.discard(number)
                best = 1
                for after in graph.successors(number):
                    if graph.issues[after].is_open:
                        best = max(best, 1 + lengths.get(after, 1))
                lengths[number] = best
                continue
            # `visiting` is what stops a CYCLE from looping forever. The recursive version got
            # this free by writing a provisional length before recursing; dropping that on the
            # rewrite turned a cycle into an infinite loop, which `mutation_check` found by
            # disabling cycle detection and watching this hang. Callers are not required to have
            # validated first — main() has, but analyse() is importable — and a hang is a far
            # worse failure than a wrong number on a graph that is already a filing error.
            if number in lengths or number in visiting:
                continue
            visiting.add(number)
            stack.append((number, True))         # revisit once the successors below resolve
            for after in graph.successors(number):
                if graph.issues[after].is_open and after not in lengths and after not in visiting:
                    stack.append((after, False))
    return lengths


def _rank(graph: Graph, number: int, lengths: dict[int, int]) -> tuple[int, int, int]:
    """Sort key for "which successor is the real critical one".

    Chain length first — that is what critical path means. Ties broken toward the HIGHER
    priority, because a tie reported as the lower-priority branch sends the reader to the
    wrong place while being equally true. Issue number last, only so the output is stable.
    """
    priority = graph.issues[number].priority
    return (lengths.get(number, 1), -PRIORITIES.index(priority) if priority else -len(PRIORITIES), -number)


def longest_chain_from(graph: Graph, number: int, lengths: dict[int, int]) -> list[int]:
    chain = [number]
    while True:
        nxt = [s for s in graph.successors(chain[-1]) if graph.issues[s].is_open]
        if not nxt:
            return chain
        chain.append(max(nxt, key=lambda n: _rank(graph, n, lengths)))


def epic_members(graph: Graph) -> dict[int, set[int]]:
    """Epic → every issue whose part-of chain reaches it (transitively)."""
    members: dict[int, set[int]] = {}
    for number in graph.part_of:
        seen: set[int] = set()
        frontier = set(graph.part_of.get(number, set()))
        while frontier:
            epic = frontier.pop()
            if epic in seen:
                continue
            seen.add(epic)
            members.setdefault(epic, set()).add(number)
            frontier |= graph.part_of.get(epic, set())
    return members


def _downstream(graph: Graph, number: int) -> set[int]:
    out: set[int] = set()
    frontier = [number]
    while frontier:
        for after in graph.successors(frontier.pop()):
            if after not in out:
                out.add(after)
                frontier.append(after)
    return out


def analyse(graph: Graph) -> dict:
    lengths = chain_lengths(graph)
    open_issues = sorted(n for n, i in graph.issues.items() if i.is_open)

    ready, blocked = [], []
    for number in open_issues:
        waiting = _open_predecessors(graph, number)
        (blocked if waiting else ready).append(
            {"number": number, "blocked_by": waiting, "chain": lengths.get(number, 1)}
        )

    epics = []
    for epic, members in sorted(epic_members(graph).items()):
        open_members = sorted(m for m in members if graph.issues[m].is_open)
        if not open_members:
            epics.append({"epic": epic, "open_members": [], "critical_path": []})
            continue
        head = max(open_members, key=lambda n: _rank(graph, n, lengths))
        epics.append({
            "epic": epic,
            "open_members": open_members,
            "critical_path": longest_chain_from(graph, head, lengths),
        })

    # Priority vs reachability, both directions. The second is the costlier mistake: a P3 that
    # three P1s wait on is the real head of the queue no matter what its label says.
    contradictions = []
    for number in open_issues:
        issue = graph.issues[number]
        waiting = _open_predecessors(graph, number)
        if issue.priority == "prio:P1" and waiting:
            contradictions.append({
                "number": number, "kind": "P1-but-blocked", "detail": waiting,
            })
        if issue.priority in ("prio:P2", "prio:P3"):
            higher = sorted(
                d for d in _downstream(graph, number)
                if graph.issues[d].is_open and graph.issues[d].priority == "prio:P1"
            )
            if higher:
                contradictions.append({
                    "number": number, "kind": "low-priority-blocking-P1", "detail": higher,
                })

    undeclared = sorted(n for n in open_issues if n not in graph.declared)
    return {
        "ready": sorted(ready, key=lambda r: (-r["chain"], r["number"])),
        "blocked": sorted(blocked, key=lambda r: (-r["chain"], r["number"])),
        "epics": epics,
        "contradictions": contradictions,
        "coverage": {
            "open": len(open_issues),
            "declaring": len(open_issues) - len(undeclared),
            "undeclared": undeclared,
        },
        "edges": sorted(graph.edges),
    }


# ---------------------------------------------------------------------------
# The gate at the point of use
# ---------------------------------------------------------------------------


def readiness(graph: Graph, requested: list[int]) -> tuple[list[str], list[str]]:
    """May `requested` be started now, as ONE unit of work? Returns `(problems, notes)`.

    Everything above reports; this is the half that can fail. That matters because an order
    nobody consults is an order asserted in prose — the exact defect #133 was filed about,
    reappearing one level up in a command that said "take the head of the triaged queue" with
    nothing checking that it had.

    Grouping related issues onto one branch is this repo's default shape (CLAUDE.md, *Grouping
    related issues on one branch*), so an edge BETWEEN two requested issues is satisfied by the
    branch itself and only fixes their order along it. An edge leaving the set is not satisfied.
    That asymmetry is the whole verdict: #110 alone waits on #109, while #109 and #110 together
    are ready. Gating against the shape the doctrine prefers would get this switched off.

    `notes` carry what the verdict does NOT know. A READY on an issue declaring no edges means
    the tracker names no blocker, not that none exists.
    """
    wanted = sorted(set(requested))
    inside = set(wanted)
    problems: list[str] = []
    notes: list[str] = []
    for number in wanted:
        issue = graph.issues.get(number)
        if issue is None:
            problems.append(
                f"#{number} is not in the tracker, so nothing is known about what it waits on"
            )
            continue
        if not issue.is_open:
            problems.append(f"#{number} is already closed — it is not work to start")
            continue
        waiting = _open_predecessors(graph, number)
        outside = [p for p in waiting if p not in inside]
        if outside:
            problems.append(
                f"#{number} waits on open work: " + ", ".join(f"#{p}" for p in outside)
                + " — starting it now works the queue out of order"
            )
        for predecessor in (p for p in waiting if p in inside):
            notes.append(
                f"#{number} waits on #{predecessor}, which is in this group — do #{predecessor} "
                "first on the branch"
            )
        if number not in graph.declared:
            notes.append(
                f"#{number} declares no edges of its own, so this says the tracker names no "
                "blocker for it — not that none exists"
            )
    return problems, notes


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def to_issues(payload: list[dict]) -> list[Issue]:
    issues = []
    for row in payload:
        labels = tuple(
            sorted(lbl["name"] if isinstance(lbl, dict) else str(lbl) for lbl in row.get("labels") or [])
        )
        issues.append(Issue(
            number=int(row["number"]),
            title=row.get("title") or "",
            state=row.get("state") or "OPEN",
            labels=labels,
            body=row.get("body") or "",
        ))
    return issues


def _run_gh(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "gh failed")
    return result.stdout


def fetch_issues(limit: int = GH_LIMIT, runner=_run_gh) -> list[Issue]:
    """Every issue, open and closed — a dependency on a closed issue is still an edge.

    A page that comes back FULL is treated as an error, not as the total. `--limit` bounds the
    query but proves nothing about whether it truncated, and a truncated tracker silently
    turns real edges into "references an issue that is not in the tracker" (#211).
    """
    payload = json.loads(runner([
        "gh", "issue", "list", "--state", "all", "--limit", str(limit),
        "--json", "number,title,state,labels,body",
    ]) or "[]")
    if len(payload) >= limit:
        raise RuntimeError(
            f"gh returned {len(payload)} issues for --limit {limit}: the page is full, so this "
            "is a truncated view being reported as the whole tracker — re-run with a larger "
            "--limit"
        )
    return to_issues(payload)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _line(graph: Graph, number: int) -> str:
    issue = graph.issues[number]
    prio = issue.priority.replace("prio:", "") if issue.priority else "--"
    title = issue.title if len(issue.title) <= 62 else issue.title[:59] + "..."
    return f"#{number:<5} {prio:<3} {title}"


def render(graph: Graph, report: dict) -> str:
    out: list[str] = []
    coverage = report["coverage"]

    out.append(f"READY NOW ({len(report['ready'])})  — open, every dependency closed")
    for row in report["ready"] or []:
        tail = f"   [unblocks a chain of {row['chain']}]" if row["chain"] > 1 else ""
        out.append("  " + _line(graph, row["number"]) + tail)
    if not report["ready"]:
        out.append("  (none)")

    out.append("")
    out.append(f"BLOCKED ({len(report['blocked'])})")
    for row in report["blocked"] or []:
        waiting = ", ".join(f"#{n}" for n in row["blocked_by"])
        out.append("  " + _line(graph, row["number"]) + f"   <- {waiting}")
    if not report["blocked"]:
        out.append("  (none)")

    if report["epics"]:
        out.append("")
        out.append("CRITICAL PATH PER EPIC")
        for row in report["epics"]:
            path = " -> ".join(f"#{n}" for n in row["critical_path"]) or "(complete)"
            out.append(f"  #{row['epic']}: {path}   [{len(row['open_members'])} open member(s)]")

    out.append("")
    out.append(f"PRIORITY vs GRAPH ({len(report['contradictions'])})")
    for row in report["contradictions"]:
        detail = ", ".join(f"#{n}" for n in row["detail"])
        if row["kind"] == "P1-but-blocked":
            out.append(f"  #{row['number']} is P1 but waits on {detail} — reconsider those first")
        else:
            out.append(f"  #{row['number']} is low priority but blocks P1 {detail} — under-ranked")
    if not report["contradictions"]:
        out.append("  (none)")

    out.append("")
    out.append(
        f"COVERAGE: {coverage['declaring']}/{coverage['open']} open issue(s) declare edges. "
        f"{len(coverage['undeclared'])} declare none, so this ordering is what the tracker "
        "SAYS, not everything that is true."
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="source", metavar="FILE",
                        help="read a `gh issue list --json ...` dump instead of calling gh ('-' for stdin)")
    parser.add_argument("--limit", type=int, default=GH_LIMIT,
                        help=f"page bound for the gh query (default {GH_LIMIT})")
    parser.add_argument("--ready", nargs="+", type=int, metavar="N",
                        help="gate: exit non-zero unless every named issue can be started now, "
                             "as one branch (edges between them are satisfied by the branch)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--selftest", action="store_true",
                        help="prove each rule fires on a real error and stays silent on its near miss")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        if args.source:
            text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
            issues = to_issues(json.loads(text))
        else:
            issues = fetch_issues(args.limit)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"could not read the tracker: {exc}", file=sys.stderr)
        return 2

    graph = build(issues)
    if graph.problems:
        print(f"ISSUE GRAPH INVALID — {len(graph.problems)} problem(s):", file=sys.stderr)
        for problem in graph.problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nNothing computed from it is printed — no queue, and no READY verdict. A ranked "
            "queue, or a green light to start work, derived from a graph already known to be "
            "wrong reads exactly like a correct one.",
            file=sys.stderr,
        )
        return 1

    if args.ready:
        problems, notes = readiness(graph, args.ready)
        requested = sorted(set(args.ready))
        if args.json:
            print(json.dumps({
                "requested": requested,
                "ready": not problems,
                "problems": problems,
                "notes": notes,
            }, indent=2, sort_keys=True))
            return 1 if problems else 0
        heading = ", ".join(f"#{n}" for n in requested)
        # A refusal must not put a verdict on stdout: a caller reading stdout alone would
        # otherwise see the word READY on the run that was telling it not to start.
        stream = sys.stderr if problems else sys.stdout
        if problems:
            print(f"NOT READY — {heading}:", file=stream)
            for problem in problems:
                print(f"  - {problem}", file=stream)
        else:
            print(f"READY — {heading} can be started now.", file=stream)
        for note in notes:
            print(f"  note: {note}", file=stream)
        if problems:
            print(
                "\nDo not start these until the refusal above is answered — clear the blocker, "
                "fix the filing, or record in the PR that you are going out of the computed "
                "order deliberately.",
                file=stream,
            )
        return 1 if problems else 0

    report = analyse(graph)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render(graph, report))
    return 0


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def selftest() -> int:
    """Every rule in both directions, plus the reports.

    The silent direction is the one that decides whether this survives. `depends_on: :account`
    is a Rails association, not an edge; "Blocks #94 and #90" is a sentence. A checker that
    fires on those gets switched off after the third false positive and then catches nothing.
    """
    failures: list[str] = []
    checks = 0

    # -- the selftest itself must not write into the repo ----------------------------
    # Snapshotted FIRST, so every scenario below is inside the window, and closed at the very
    # end. The gate runs inside `maintainer_doctor.py`, where a diagnostic that mutates the
    # working tree is a defect in its own right. Asserted rather than assumed, because the first
    # version of this selftest did exactly that.
    checks += 1
    before = {p.name for p in Path(__file__).resolve().parent.iterdir()}

    def issue(number: int, body: str = "", state: str = "OPEN", labels=()) -> Issue:
        return Issue(number=number, title=f"issue {number}", state=state,
                     labels=tuple(labels), body=body)

    def run_main(payload: str, *extra: str) -> tuple[int, str, str]:
        """`main()` end to end against a tracker dump, from a SYSTEM temp dir — never the repo.

        The first version of this selftest wrote `scripts/.issue_graph_selftest.json` and
        unlinked it in a `finally` — which mutates the working tree of whoever runs the gate,
        fails on a read-only checkout, and races two concurrent runs on one fixed filename.
        `mutation_check.py` already records this exact lesson ("one interrupted process away from
        leaving a mutated repo"), and `maintainer_doctor.py` runs this selftest as a gate.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory(prefix="issue-graph-selftest-") as workdir:
            fixture = Path(workdir) / "tracker.json"
            fixture.write_text(payload, encoding="utf-8")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--from", str(fixture), *extra])
        return code, stdout.getvalue(), stderr.getvalue()

    def scenario(label: str, issues: list[Issue], *, expect: str | None) -> Graph:
        """`expect` is a substring required in the problems, or None to require silence."""
        nonlocal checks
        checks += 1
        graph = build(issues)
        joined = " | ".join(graph.problems)
        if expect is None:
            if graph.problems:
                failures.append(f"{label}: expected silence, got {joined}")
        elif expect.lower() not in joined.lower():
            failures.append(f"{label}: expected a problem mentioning {expect!r}, got {joined or '(none)'}")
        return graph

    def deps(*lines: str) -> str:
        return "prose above\n\n```deps\n" + "\n".join(lines) + "\n```\n\nprose below\n"

    # -- edges are read at all -------------------------------------------------------
    graph = scenario(
        "a deps block declares edges",
        [issue(1, deps("blocks: #2")), issue(2, deps("depends-on: #1", "part-of: #3")), issue(3)],
        expect=None,
    )
    checks += 1
    if graph.edges != {(1, 2)}:
        failures.append(f"a deps block declares edges: expected {{(1, 2)}}, got {graph.edges}")
    checks += 1
    if graph.part_of != {2: {3}}:
        failures.append(f"part-of linkage: expected {{2: {{3}}}}, got {graph.part_of}")

    # The same edge stated from both ends is ONE edge. Were it two, this pair would look like a
    # 2-cycle and the format's own example would be a filing error.
    scenario(
        "reciprocal declarations are one edge, not a cycle",
        [issue(1, deps("blocks: #2")), issue(2, deps("depends-on: #1"))],
        expect=None,
    )

    # -- cycles ----------------------------------------------------------------------
    scenario(
        "dependency cycle",
        [issue(1, deps("depends-on: #2")), issue(2, deps("depends-on: #1"))],
        expect="dependency cycle",
    )
    scenario(
        "a three-hop cycle",
        [issue(1, deps("blocks: #2")), issue(2, deps("blocks: #3")), issue(3, deps("blocks: #1"))],
        expect="dependency cycle",
    )
    # Near miss: a diamond re-converges without ever cycling. Naive "already visited" cycle
    # detection reports this, and it is a perfectly ordinary shape.
    scenario(
        "a diamond is not a cycle",
        [issue(1, deps("blocks: #2, #3")), issue(2, deps("blocks: #4")),
         issue(3, deps("blocks: #4")), issue(4)],
        expect=None,
    )
    scenario(
        "self reference",
        [issue(1, deps("depends-on: #1"))],
        expect="references itself",
    )
    scenario(
        "part-of cycle",
        [issue(1, deps("part-of: #2")), issue(2, deps("part-of: #1"))],
        expect="part-of cycle",
    )
    # part-of carries no ordering, so an epic may sit inside another epic and also block work.
    scenario(
        "nested epics are not a cycle",
        [issue(1, deps("part-of: #2")), issue(2, deps("part-of: #3")), issue(3)],
        expect=None,
    )

    # -- dangling edges --------------------------------------------------------------
    scenario(
        "edge to an issue not in the tracker",
        [issue(1, deps("depends-on: #999"))],
        expect="not in the tracker",
    )
    scenario(
        "an edge to a CLOSED issue is fine",
        [issue(1, deps("depends-on: #2")), issue(2, state="CLOSED")],
        expect=None,
    )

    # -- malformed declarations ------------------------------------------------------
    scenario(
        "typo'd key",
        [issue(1, deps("depends_on: #2")), issue(2)],
        expect="unknown key",
    )
    scenario(
        "a prose line inside the deps block",
        [issue(1, deps("because the schema lands first")), issue(2)],
        expect="malformed line",
    )
    scenario(
        "a non-issue reference",
        [issue(1, deps("depends-on: the auth epic")), issue(2)],
        expect="not a `#n` issue",
    )
    scenario(
        "an empty declaration",
        [issue(1, deps("blocks:"))],
        expect="declares no issue",
    )
    # A repeated ref is sloppy, not wrong — deduped in silence.
    graph = scenario(
        "a repeated reference is deduped, not flagged",
        [issue(1, deps("blocks: #2, #2")), issue(2)],
        expect=None,
    )
    checks += 1
    if graph.edges != {(1, 2)}:
        failures.append(f"a repeated reference is deduped: expected one edge, got {graph.edges}")

    # -- near miss: the wrong fence tag ----------------------------------------------
    scenario(
        "declarations under an untagged fence",
        [issue(1, "```\ndepends-on: #2\n```\n"), issue(2)],
        expect="tag it ```deps",
    )
    scenario(
        "declarations under a `text` fence",
        [issue(1, "```text\nblocks: #2\n```\n"), issue(2)],
        expect="tag it ```deps",
    )
    # THE false positive that would kill this check: `depends_on:` is a Rails association, and
    # ruby fences full of them are ordinary content in this repo's own issues.
    scenario(
        "a ruby fence using depends_on is not a deps block",
        [issue(1, "```ruby\nclass Account < ApplicationRecord\n  depends_on: :owner\nend\n```\n")],
        expect=None,
    )
    scenario(
        "a fence mixing prose with a declaration is a sample, not a mistag",
        [issue(1, "```text\nExample of the format:\ndepends-on: #2\n```\n"), issue(2)],
        expect=None,
    )
    scenario(
        "a fence whose keys are not ours",
        [issue(1, "```yaml\nrequires: #2\n```\n"), issue(2)],
        expect=None,
    )

    # -- near miss: a declaration loose in prose -------------------------------------
    scenario(
        "a declaration outside any fence",
        [issue(1, "Some context.\n\ndepends-on: #2\n\nMore.\n"), issue(2)],
        expect="outside a ```deps",
    )
    # Prose that merely mentions the edge. If this fires, every issue body that discusses its
    # own ordering becomes an error and the check is deleted within a week.
    scenario(
        "prose naming a blocker is not a declaration",
        [issue(1, "Blocks: #2 and #3, but only once the schema lands.\n"), issue(2), issue(3)],
        expect=None,
    )
    scenario(
        "prose in the shape of a sentence",
        [issue(1, "This depends on #2 landing first.\n"), issue(2)],
        expect=None,
    )
    # The declaration is legitimately inside a deps fence — the prose scanner must not see it
    # again through the fence it already handled.
    scenario(
        "a real deps block is not also reported as loose prose",
        [issue(1, deps("blocks: #2")), issue(2)],
        expect=None,
    )

    # -- reports ---------------------------------------------------------------------
    tracker = [
        issue(1, deps("blocks: #2"), state="CLOSED"),
        issue(2, deps("depends-on: #1", "blocks: #3", "part-of: #10"), labels=["prio:P3"]),
        issue(3, deps("part-of: #10"), labels=["prio:P1"]),
        issue(4, labels=["prio:P2"]),
        issue(10, labels=["prio:P2"]),
    ]
    graph = scenario("the report tracker validates", tracker, expect=None)
    report = analyse(graph)

    checks += 1
    ready = [row["number"] for row in report["ready"]]
    if ready != [2, 4, 10]:
        failures.append(f"ready-now: expected [2, 4, 10] (#1 is closed, #3 waits on #2), got {ready}")

    checks += 1
    blocked = {row["number"]: row["blocked_by"] for row in report["blocked"]}
    if blocked != {3: [2]}:
        failures.append(f"blocked-by-what: expected {{3: [2]}}, got {blocked}")

    checks += 1
    epic = next((e for e in report["epics"] if e["epic"] == 10), None)
    if not epic or epic["critical_path"] != [2, 3]:
        failures.append(f"critical path: expected #2 -> #3 for epic #10, got {epic}")

    # A tie on chain length must resolve toward the P1, not toward whichever number sorts first.
    # #20 blocks a P3 and a P1, both terminal: the reported path has to name the P1.
    checks += 1
    tie = build([
        issue(20, deps("blocks: #21, #22", "part-of: #23"), labels=["prio:P2"]),
        issue(21, deps("part-of: #23"), labels=["prio:P3"]),
        issue(22, deps("part-of: #23"), labels=["prio:P1"]),
        issue(23),
    ])
    tie_path = next(e["critical_path"] for e in analyse(tie)["epics"] if e["epic"] == 23)
    if tie_path != [20, 22]:
        failures.append(
            f"critical-path tiebreak: expected the P1 branch #20 -> #22, got {tie_path}"
        )

    checks += 1
    kinds = {(row["number"], row["kind"]) for row in report["contradictions"]}
    if (3, "P1-but-blocked") not in kinds:
        failures.append(f"P1-but-blocked not flagged for #3: {kinds}")
    checks += 1
    if (2, "low-priority-blocking-P1") not in kinds:
        failures.append(f"low-priority-blocking-P1 not flagged for #2: {kinds}")

    # #4 is unrelated to everything: neither contradiction may fire on it, or the flags become
    # noise attached to the whole tracker.
    checks += 1
    if any(row["number"] == 4 for row in report["contradictions"]):
        failures.append("an unconnected P2 was flagged as a priority contradiction")

    checks += 1
    coverage = report["coverage"]
    if (coverage["open"], coverage["declaring"], coverage["undeclared"]) != (4, 2, [4, 10]):
        failures.append(f"coverage: expected 2 of 4 open declaring, #4/#10 silent, got {coverage}")

    # -- a chain deeper than the call stack ------------------------------------------
    # 1500 issues in one line, which is past CPython's ~1000-frame default. The recursive
    # version of chain_lengths raised RecursionError here; the graph is perfectly valid, so
    # /maintainer-triage would have died on a tracker that had done nothing wrong.
    checks += 1
    deep = [issue(n, deps(f"blocks: #{n + 1}")) for n in range(1, 1500)] + [issue(1500)]
    try:
        deep_graph = build(deep)
        if deep_graph.problems:
            failures.append(f"deep chain: expected a valid graph, got {deep_graph.problems[:2]}")
        elif chain_lengths(deep_graph)[1] != 1500:
            failures.append(
                f"deep chain: expected a chain of 1500, got {chain_lengths(deep_graph)[1]}"
            )
    except RecursionError:
        failures.append("deep chain: chain_lengths blew the stack on a valid 1500-issue chain")

    # A cyclic graph is a hard error, so chain_lengths should never SEE one — but it is an
    # importable function and "should never" is not a guarantee. It must terminate rather than
    # hang; the value it returns for a cycle is meaningless and deliberately unasserted.
    checks += 1
    cyclic = build([issue(1, deps("blocks: #2")), issue(2, deps("blocks: #3")),
                    issue(3, deps("blocks: #1"))])
    try:
        chain_lengths(cyclic)
    except RecursionError:
        failures.append("chain_lengths on a cyclic graph: blew the stack instead of terminating")

    # -- the truncation guard --------------------------------------------------------
    # #211's whole story. Exercised with an injected runner because `gh` is not present on
    # every machine that runs this selftest, and a check skipped for want of a binary is the
    # skip-is-not-a-pass failure.
    checks += 1
    full_page = json.dumps([{"number": n, "title": "t", "state": "OPEN", "labels": [], "body": ""}
                            for n in range(1, 6)])
    try:
        fetch_issues(limit=5, runner=lambda argv: full_page)
    except RuntimeError as exc:
        if "truncated" not in str(exc):
            failures.append(f"truncation guard: wrong message — {exc}")
    else:
        failures.append("truncation guard: a full page was accepted as the whole tracker")

    checks += 1
    short_page = json.dumps([{"number": 1, "title": "t", "state": "OPEN", "labels": [], "body": ""}])
    try:
        got = fetch_issues(limit=5, runner=lambda argv: short_page)
    except RuntimeError as exc:
        failures.append(f"truncation guard fired on a partial page: {exc}")
    else:
        if len(got) != 1:
            failures.append(f"partial page: expected 1 issue, got {len(got)}")

    # The query must be bounded AND cover closed issues, or every edge into a finished issue
    # becomes a dangling-edge error.
    checks += 1
    seen: list[list[str]] = []

    def capture(argv: list[str]) -> str:
        seen.append(argv)
        return "[]"

    fetch_issues(limit=7, runner=capture)
    argv = seen[0] if seen else []
    if "--limit" not in argv or "7" not in argv:
        failures.append(f"the gh query is unbounded: {argv}")
    if "--state" not in argv or "all" not in argv:
        failures.append(f"the gh query omits closed issues: {argv}")

    # -- a broken graph prints no queue ----------------------------------------------
    # The property that makes this a gate. If `main` ever renders a report alongside the
    # errors, a wrong ordering ships looking exactly like a right one.
    checks += 1
    broken = json.dumps([
        {"number": 1, "title": "a", "state": "OPEN", "labels": [],
         "body": "```deps\ndepends-on: #2\n```\n"},
        {"number": 2, "title": "b", "state": "OPEN", "labels": [],
         "body": "```deps\ndepends-on: #1\n```\n"},
    ])
    code, out, err = run_main(broken)
    if code != 1:
        failures.append(f"a cyclic graph exited {code}, expected 1")
    if "READY NOW" in out:
        failures.append("a queue was printed for a graph known to be cyclic")
    if "cycle" not in err:
        failures.append("the cycle was not reported on stderr")

    # -- the gate at the point of use: --ready ----------------------------------------
    # Everything above reports; this decides. The near miss is what keeps it alive: a group
    # carrying its own internal dependency must come back READY, because grouping related issues
    # onto one branch is the doctrine's preferred shape — a gate that refuses it would be
    # switched off inside a week, and then nothing checks the order at all.
    ready_tracker = [
        issue(30, deps("blocks: #31"), state="CLOSED"),
        issue(31, deps("depends-on: #30", "blocks: #32")),
        issue(32, deps("depends-on: #31")),
        issue(40),
    ]
    ready_graph = scenario("the --ready tracker validates", ready_tracker, expect=None)

    def gate(label: str, on: Graph, requested: list[int], *, expect: str | None,
             note: str | None = None) -> None:
        """`expect` is a substring required in the refusal, or None to require READY."""
        nonlocal checks
        checks += 1
        problems, notes = readiness(on, requested)
        joined = " | ".join(problems)
        if expect is None:
            if problems:
                failures.append(f"{label}: expected READY, got {joined}")
        elif expect.lower() not in joined.lower():
            failures.append(
                f"{label}: expected NOT READY mentioning {expect!r}, got {joined or '(READY)'}"
            )
        if note is not None:
            checks += 1
            if not any(note.lower() in n.lower() for n in notes):
                failures.append(
                    f"{label}: expected a note mentioning {note!r}, got {notes or '(none)'}"
                )

    gate("an issue waiting on open work is not ready", ready_graph, [32],
         expect="waits on open work: #31")
    # The satisfied dependency. #31 waits only on #30, which is CLOSED — that is what a met
    # prerequisite looks like, and refusing it would make every finished edge a permanent block.
    gate("an issue whose only blocker is closed is ready", ready_graph, [31], expect=None)
    gate("a group takes its own internal dependency with it", ready_graph, [31, 32],
         expect=None, note="in this group")
    # …but only its OWN. Adding an unrelated issue to the set must not launder #31 out of #32's
    # way, or "group it with anything" becomes a way to silence the gate.
    gate("a group is still blocked from outside itself", ready_graph, [32, 40],
         expect="waits on open work: #31")
    gate("an issue absent from the tracker", ready_graph, [999], expect="not in the tracker")
    gate("an already-closed issue is not work to start", ready_graph, [30],
         expect="already closed")
    # The honesty half: a green light on an issue that declared nothing must say so.
    gate("an issue declaring no edges gets the coverage caveat", ready_graph, [40],
         expect=None, note="declares no edges")
    # …and an issue that DID declare must not get it. A caveat attached to every verdict is a
    # caveat nobody reads, which is the same signal-destroying end as no caveat at all.
    checks += 1
    _, declared_notes = readiness(ready_graph, [31])
    if any("declares no edges" in note for note in declared_notes):
        failures.append(
            f"the coverage caveat fired on #31, which declares edges: {declared_notes}"
        )

    checks += 1
    _, duplicate_notes = readiness(ready_graph, [40, 40])
    if len(duplicate_notes) != 1:
        failures.append(
            f"a repeated request should be deduped, got {len(duplicate_notes)} notes: "
            f"{duplicate_notes}"
        )

    # The flag has to be WIRED, not merely implemented — a flag parsed and ignored is the
    # dead-declaration class, and calling `readiness` directly would never notice.
    ready_json = json.dumps([
        {"number": 31, "title": "schema", "state": "OPEN", "labels": [], "body": ""},
        {"number": 32, "title": "consumer", "state": "OPEN", "labels": [],
         "body": "```deps\ndepends-on: #31\n```\n"},
    ])
    checks += 1
    code, out, err = run_main(ready_json, "--ready", "32")
    if code != 1:
        failures.append(f"--ready on a blocked issue exited {code}, expected 1")
    if out.strip():
        # Not merely "no READY": stdout must be EMPTY, because a caller reading stdout alone is
        # the case the refusal has to survive. `--json` is the deliberate exception below.
        failures.append(f"--ready wrote to stdout while refusing to start work: {out!r}")
    if "#31" not in err:
        failures.append(f"--ready refused without naming the blocker: {err!r}")

    checks += 1
    code, out, err = run_main(ready_json, "--ready", "31", "32")
    if code != 0:
        failures.append(f"--ready on a whole group exited {code}, expected 0: {err}")
    if "READY" not in out:
        failures.append(f"--ready cleared the group but printed no verdict on stdout: {out!r}")

    checks += 1
    code, out, _ = run_main(ready_json, "--ready", "32", "--json")
    verdict = json.loads(out or "{}")
    if verdict.get("ready") is not False or verdict.get("requested") != [32] \
            or not verdict.get("problems"):
        failures.append(f"--ready --json reported the wrong verdict: {verdict}")

    # Fail closed, same as the queue. A green light derived from a graph already known to be
    # wrong is worse than a wrong ordering, because it authorises work rather than describing it.
    checks += 1
    code, out, err = run_main(broken, "--ready", "1")
    if code != 1:
        failures.append(f"--ready on an invalid graph exited {code}, expected 1")
    if "READY" in out:
        failures.append("--ready cleared work from a graph known to be cyclic")
    if "cycle" not in err:
        failures.append("--ready on an invalid graph did not report the cycle")

    # Closes the no-repo-writes check opened at the top, after every scenario that touches disk.
    stray = {p.name for p in Path(__file__).resolve().parent.iterdir()} - before
    if stray:
        failures.append(
            f"the selftest left files in scripts/: {sorted(stray)} — a gate the doctor runs "
            "must not mutate the working tree"
        )

    for failure in failures:
        print(f"  FAIL {failure}")
    if failures:
        print(f"\nissue_graph selftest: {len(failures)} of {checks} checks failed")
        return 1
    print(f"issue_graph selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
