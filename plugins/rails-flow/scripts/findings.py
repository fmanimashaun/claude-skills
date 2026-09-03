#!/usr/bin/env python3
"""Typed findings records — validate, dedupe, order, render (#138).

`/rails-flow:review` fans out seven parallel passes and each returns findings as a **text line**.
Synthesis is then a model reading seven prose blobs and merging them by judgement. Three things
follow, and all three have already gone wrong in this toolchain:

  * **Dedupe is judgement, not mechanics** (#118). Two passes seeing the same defect produce two
    findings, and whether they collapse depends on whether one reader thought they looked alike.
  * **"Report everything" is unverifiable** (#77). The rule says no pass may drop a finding and
    synthesis may only reorder — but nothing compares the input set to the output set, so a dropped
    finding leaves no trace at all.
  * **Relations are lost.** Passes cross-examine, yet nothing records "A is caused by B", so fix
    order is a guess and the fix for a symptom can land before the fix for its cause.

This makes those three mechanical. It is deliberately **plain JSONL in git** — no graph database,
no orchestration runtime (#138 criterion 8, and `docs/doctrine/harness-doctrine.md` §9: prefer inspectable
state). A record you can `git diff`, `grep`, and read without a running service.

THE DIVISION OF LABOUR, which is the same one this toolchain uses everywhere. The agent decides
**what is a finding** and **what its signature is** — both are judgement. This script decides
everything downstream: whether the record is well-formed, which records collapse, whether any went
missing, and what order the fixes go in. Neither half pretends to be the other.

WHY `signature` IS THE AGENT'S JOB AND NOT INFERRED HERE. A signature is a stable identity for the
*defect*, not the occurrence — `missing-tenant-scope:InvoicesController#show`. Deriving one from
file+line would be wrong in both directions: the same defect moves when a line is inserted, and two
genuinely different defects share a line. So the agent writes it and this script trusts it, which
means a bad signature produces a bad dedupe. That is a real limit, stated rather than hidden.

Exit codes:  0 clean · 1 findings (invalid record, dropped id, cycle) · 2 unusable (bad input)

Stdlib only, no network.

Usage:
    python3 findings.py validate     FINDINGS.jsonl
    python3 findings.py dedupe       FINDINGS.jsonl
    python3 findings.py completeness --input IN.jsonl --output OUT.jsonl
    python3 findings.py order        FINDINGS.jsonl
    python3 findings.py report       FINDINGS.jsonl
    python3 findings.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# The canonical record shape. `plugins/qa-flow/agents/qa-reporter.md` documents the SAME list so a
# QA defect and a review defect are one kind of thing (#138 criterion 7), and `undeclared-topology`'s
# neighbour rule `findings-schema-drift` fails the build if the two ever disagree.
REQUIRED = ("id", "pass", "severity", "category", "file", "signature", "issue")
OPTIONAL = ("line", "repro", "fix_options", "caused_by", "blocks", "duplicate_of")
FIELDS = REQUIRED + OPTIONAL

SEVERITIES = ("P1", "P2", "P3")
# Sort rank, so P1 leads a phase. Kept explicit rather than derived from the tuple index, because
# reading `SEVERITIES.index(...)` at three call sites is how an off-by-one gets in.
SEVERITY_RANK = {"P1": 0, "P2": 1, "P3": 2}


class Unusable(Exception):
    """Input this tool cannot read — exit 2, never 1.

    The split is load-bearing and the same one `setup_doctrine_crosscheck.py` makes: 1 means "your
    findings have a problem", 2 means "this check could not run". Collapsing them sends someone
    hunting a defect that does not exist.
    """


def load(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Unusable(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise Unusable(f"{path} is not valid UTF-8: {exc}") from exc
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Unusable(f"{path}:{number} is not valid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise Unusable(f"{path}:{number} is a {type(record).__name__}, not an object")
        record["_line"] = number
        records.append(record)
    return records


def validate(records: list[dict]) -> list[str]:
    problems: list[str] = []
    seen: dict[str, int] = {}
    for record in records:
        where = f"line {record.get('_line', '?')}"
        for field in REQUIRED:
            if not record.get(field):
                problems.append(f"{where}: missing required field `{field}`")
        severity = record.get("severity")
        if severity and severity not in SEVERITIES:
            problems.append(f"{where}: severity {severity!r} is not one of {'/'.join(SEVERITIES)}")
        unknown = set(record) - set(FIELDS) - {"_line"}
        if unknown:
            # An unknown field is a finding, not a shrug. It is usually a typo in a field name,
            # which silently drops the value the author meant to set — `blocked_by` for `blocks`
            # loses an edge and the fix order goes wrong with nothing to show for it.
            problems.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        identifier = record.get("id")
        if identifier:
            if identifier in seen:
                problems.append(f"{where}: duplicate id {identifier!r} (first at line {seen[identifier]})")
            seen[identifier] = record.get("_line", 0)
        for edge in ("blocks",):
            value = record.get(edge)
            if value is not None and not isinstance(value, list):
                problems.append(f"{where}: `{edge}` must be a list, got {type(value).__name__}")
    # Edges must point at records that exist, or the fix order silently drops them.
    ids = {r.get("id") for r in records if r.get("id")}
    for record in records:
        where = f"line {record.get('_line', '?')}"
        for target in _edges_from(record):
            if target not in ids:
                problems.append(f"{where}: edge points at unknown id {target!r}")
        parent = record.get("duplicate_of")
        if parent and parent not in ids:
            problems.append(f"{where}: duplicate_of points at unknown id {parent!r}")
    return problems


def _edges_from(record: dict) -> list[str]:
    out = []
    if record.get("caused_by"):
        out.append(record["caused_by"])
    out.extend(record.get("blocks") or [])
    return out


def dedupe(records: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group by `signature`. Returns (signature, instances) ordered by severity then signature."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record.get("signature", "")].append(record)
    def rank(item):
        signature, instances = item
        best = min(SEVERITY_RANK.get(i.get("severity", "P3"), 3) for i in instances)
        return (best, signature)
    return sorted(groups.items(), key=rank)


def completeness(inputs: list[dict], outputs: list[dict]) -> list[str]:
    """Every input id must appear in the output, reported or marked `duplicate_of` (#77).

    This is the half that makes "report everything" checkable rather than contractual. Synthesis may
    reorder and may collapse duplicates; it may not make a finding vanish.
    """
    out_ids = {r.get("id") for r in outputs if r.get("id")}
    collapsed = {r.get("duplicate_of") for r in outputs if r.get("duplicate_of")}
    problems = []
    for record in inputs:
        identifier = record.get("id")
        if not identifier:
            continue
        if identifier not in out_ids and identifier not in collapsed:
            problems.append(
                f"id {identifier!r} ({record.get('pass', '?')}, {record.get('severity', '?')}) "
                f"is in the input and absent from the output — synthesis may reorder and collapse, "
                f"never drop")
    return problems


def order(records: list[dict]) -> tuple[list[dict], list[list[str]]]:
    """Topological order on caused_by/blocks, severity as tiebreak. Returns (ordered, cycles).

    Both edge kinds mean the same thing in opposite directions: `A caused_by B` and `B blocks A`
    both say **B is fixed before A**. Recording both is redundancy the agents wanted, so the two are
    normalised here rather than one being declared canonical and the other quietly ignored.

    A cycle is REPORTED, not raised. Fix order with a cycle in it is still more useful than no
    order, so cycle members fall back to severity order at the end — and the caller is told, because
    a mutual `caused_by` is usually a genuine modelling error worth a human look.
    """
    by_id = {r["id"]: r for r in records if r.get("id")}
    successors: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = {i: 0 for i in by_id}
    for record in records:
        identifier = record.get("id")
        if not identifier:
            continue
        if record.get("caused_by") in by_id:                 # cause -> this
            _add(successors, indegree, record["caused_by"], identifier)
        for blocked in record.get("blocks") or []:           # this -> blocked
            if blocked in by_id:
                _add(successors, indegree, identifier, blocked)

    ready = sorted((i for i, d in indegree.items() if d == 0), key=lambda i: _rank(by_id[i]))
    ordered: list[dict] = []
    while ready:
        current = ready.pop(0)
        ordered.append(by_id[current])
        for nxt in sorted(successors[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=lambda i: _rank(by_id[i]))

    remaining = [i for i in by_id if i not in {r["id"] for r in ordered}]
    cycles = [sorted(remaining)] if remaining else []
    ordered.extend(sorted((by_id[i] for i in remaining), key=_rank))
    return ordered, cycles


def _add(successors: dict, indegree: dict, before: str, after: str) -> None:
    if after not in successors[before]:
        successors[before].add(after)
        indegree[after] += 1


def _rank(record: dict) -> tuple[int, str]:
    return (SEVERITY_RANK.get(record.get("severity", "P3"), 3), record.get("id", ""))


def render(records: list[dict]) -> str:
    """The human report is GENERATED, never authored (#138 criterion 6).

    The moment someone edits the markdown by hand, the data and the report disagree and the data
    silently stops being the source of truth — the #56 shape, where a prose rule and its copyable
    example drifted apart and nothing compared them.
    """
    live = [r for r in records if not r.get("duplicate_of")]
    ordered, cycles = order(live)
    groups = dict(dedupe(live))
    lines = ["<!-- GENERATED by findings.py — edit findings.jsonl, not this file. -->",
             "# Review findings", ""]
    counts = {s: sum(1 for r in live if r.get("severity") == s) for s in SEVERITIES}
    lines.append("| severity | distinct | instances |")
    lines.append("|---|---|---|")
    for severity in SEVERITIES:
        distinct = sum(1 for sig, items in groups.items()
                       if min(SEVERITY_RANK.get(i.get("severity", "P3"), 3) for i in items)
                       == SEVERITY_RANK[severity])
        lines.append(f"| {severity} | {distinct} | {counts[severity]} |")
    lines.append("")
    if cycles:
        lines.append(f"> **Cycle in the fix graph:** {', '.join(cycles[0])}. Ordered by severity "
                     f"instead; a mutual `caused_by` is usually a modelling error.")
        lines.append("")
    lines.append("## Fix order")
    lines.append("")
    for position, record in enumerate(ordered, 1):
        instances = groups.get(record.get("signature", ""), [record])
        suffix = (f" _(also seen by {len(instances) - 1} other pass(es))_" if len(instances) > 1
                  else "")
        where = f"{record.get('file')}:{record['line']}" if record.get("line") else record.get("file")
        lines.append(f"{position}. **[{record.get('severity')}]** `{where}` — "
                     f"{record.get('issue')}{suffix}")
        if record.get("caused_by"):
            lines.append(f"   - caused by `{record['caused_by']}`, so that one is fixed first")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Typed findings records: validate/dedupe/order.")
    parser.add_argument("command", nargs="?",
                        choices=("validate", "dedupe", "completeness", "order", "report"))
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.command:
        parser.error("a command is required (or --selftest)")

    try:
        if args.command == "completeness":
            if not (args.input and args.output):
                parser.error("completeness needs --input and --output")
            problems = completeness(load(args.input), load(args.output))
            for problem in problems:
                print(f"  DROPPED: {problem}")
            print(f"\n{len(problems)} dropped finding(s).")
            return 1 if problems else 0

        if not args.path:
            parser.error(f"{args.command} needs a findings file")
        records = load(args.path)

        if args.command == "validate":
            problems = validate(records)
            for problem in problems:
                print(f"  INVALID: {problem}")
            print(f"\n{len(records)} record(s), {len(problems)} problem(s).")
            return 1 if problems else 0

        if args.command == "dedupe":
            groups = dedupe(records)
            for signature, instances in groups:
                where = ", ".join(sorted({i.get("file", "?") for i in instances}))
                print(f"  {instances[0].get('severity')}  {signature}  "
                      f"— {len(instances)} instance(s) across {where}")
            print(f"\n{len(groups)} distinct defect(s) from {len(records)} record(s).")
            return 0

        if args.command == "order":
            ordered, cycles = order(records)
            for position, record in enumerate(ordered, 1):
                print(f"  {position:3}. [{record.get('severity')}] {record.get('id')} "
                      f"{record.get('signature')}")
            if cycles:
                print(f"\nCYCLE: {', '.join(cycles[0])} — ordered by severity instead.")
                return 1
            return 0

        print(render(records))
        return 0
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def rec(identifier, **kw):
        base = {"id": identifier, "pass": "p", "severity": "P2", "category": "c",
                "file": "a.rb", "signature": f"sig-{identifier}", "issue": "i"}
        base.update(kw)
        return base

    # ---- validate FIRES ----------------------------------------------------------------------
    check("missing required field", validate([{"id": "a", "_line": 1}]))
    check("bad severity", any("severity" in p for p in validate([rec("a", severity="CRITICAL")])))
    check("duplicate id", any("duplicate id" in p for p in validate([rec("a"), rec("a")])))
    check("edge to unknown id", any("unknown id" in p for p in validate([rec("a", blocks=["ghost"])])))
    check("duplicate_of to unknown id",
          any("duplicate_of" in p for p in validate([rec("a", duplicate_of="ghost")])))
    check("blocks must be a list", any("must be a list" in p for p in validate([rec("a", blocks="b")])))
    # A typo'd field name silently drops the value the author meant to set. `blocked_by` instead of
    # `blocks` loses an edge, and the fix order is then wrong with nothing to show for it.
    check("unknown field", any("unknown field" in p for p in validate([rec("a", blocked_by=["b"])])))

    # ---- validate STAYS SILENT ---------------------------------------------------------------
    check("a well-formed pair is clean",
          validate([rec("a", blocks=["b"]), rec("b")]) == [],
          f"{validate([rec('a', blocks=['b']), rec('b')])}")
    check("optional fields may be absent", validate([rec("a")]) == [])

    # ---- dedupe --------------------------------------------------------------------------------
    groups = dedupe([rec("a", signature="s1"), rec("b", signature="s1"), rec("c", signature="s2")])
    check("same signature collapses", len(groups) == 2, f"{len(groups)}")
    check("instances are kept, not discarded",
          sum(len(i) for _, i in groups) == 3, "the count is what #118 needs")
    # P1 must lead even when its signature sorts later alphabetically.
    groups = dedupe([rec("a", signature="zzz", severity="P1"), rec("b", signature="aaa", severity="P3")])
    check("severity outranks alphabetical order", groups[0][0] == "zzz", f"{groups[0][0]}")

    # ---- completeness (#77) ---------------------------------------------------------------------
    check("a dropped id is caught", completeness([rec("a"), rec("b")], [rec("a")]))
    check("collapsing is allowed, dropping is not",
          completeness([rec("a"), rec("b")], [rec("a"), rec("b", duplicate_of="a")]) == [])
    check("reordering is allowed", completeness([rec("a"), rec("b")], [rec("b"), rec("a")]) == [])

    # ---- order ----------------------------------------------------------------------------------
    ordered, cycles = order([rec("sym", caused_by="root"), rec("root")])
    check("a cause is fixed before its symptom", [r["id"] for r in ordered] == ["root", "sym"],
          f"{[r['id'] for r in ordered]}")
    check("no false cycle", cycles == [], f"{cycles}")
    # `blocks` is the same statement pointing the other way, so it must produce the same order.
    ordered, _ = order([rec("sym"), rec("root", blocks=["sym"])])
    check("blocks and caused_by agree", [r["id"] for r in ordered] == ["root", "sym"],
          f"{[r['id'] for r in ordered]}")
    # Severity is the TIEBREAK, so it must not override a real edge. This is the fixture that
    # matters: a P1 symptom must still wait for its P3 cause, or the graph is decoration.
    ordered, _ = order([rec("sym", severity="P1", caused_by="root"), rec("root", severity="P3")])
    check("an edge outranks severity", [r["id"] for r in ordered] == ["root", "sym"],
          f"{[r['id'] for r in ordered]} — severity must not reorder across an edge")
    ordered, _ = order([rec("b", severity="P3"), rec("a", severity="P1")])
    check("severity decides when there is no edge", [r["id"] for r in ordered] == ["a", "b"],
          f"{[r['id'] for r in ordered]}")
    ordered, cycles = order([rec("a", caused_by="b"), rec("b", caused_by="a")])
    check("a cycle is reported", cycles == [["a", "b"]], f"{cycles}")
    check("a cycle still yields an order", len(ordered) == 2, "some order beats none")

    # ---- render ----------------------------------------------------------------------------------
    text = render([rec("a", severity="P1"), rec("b", severity="P1", signature="sig-a")])
    check("the report says it is generated", "GENERATED" in text)
    check("duplicates are counted, not repeated", "also seen by 1 other pass" in text, text[:200])
    check("a duplicate_of record is excluded from the report",
          "dup" not in render([rec("a"), rec("dup", duplicate_of="a")]))
    check("a cycle is surfaced in the report",
          "Cycle in the fix graph" in render([rec("a", caused_by="b"), rec("b", caused_by="a")]))

    # ---- unusable is 2, never 1 --------------------------------------------------------------
    import contextlib
    import io
    import tempfile
    # The exit-2 paths print to stderr by design; captured here so a passing gate does not look
    # like a crashing one. The exit CODE is what is asserted.
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()), \
            contextlib.redirect_stdout(io.StringIO()):
        bad = Path(tmp) / "bad.jsonl"
        bad.write_text('{"id": "a"\n', encoding="utf-8")
        check("malformed JSON is UNUSABLE (2), not a finding (1)",
              main(["validate", str(bad)]) == 2, f"{main(['validate', str(bad)])}")
        missing = Path(tmp) / "nope.jsonl"
        check("a missing file is UNUSABLE (2)", main(["validate", str(missing)]) == 2)
        empty = Path(tmp) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        check("an empty file is clean, not unusable", main(["validate", str(empty)]) == 0)

    if failures:
        print(f"SELFTEST FAILED — {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"findings selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
