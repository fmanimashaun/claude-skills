#!/usr/bin/env python3
"""Every rule on the interface-architecture page names a basis that exists (#2220).

Run:  python3 scripts/check_architecture_rules.py
      python3 scripts/check_architecture_rules.py --selftest

WHY THIS EXISTS. The owner's ruling: "everything must be enforced, a claim or rule not enforced is
useless", and later "advice is not bad but must be tested against best practices or standards".
`references/architecture.md` therefore ships only rules that carry one of three bases, and this
refuses a row that carries none:

  check: <path>   a script that exists in this repository (the path must be a real file)
  claim: C#       an external claim whose latest verdict in the claims file is CONFIRMED
  decision: D#    a maintainer decision recorded in the claims file's decisions table

A rule cited to an INCONCLUSIVE or REFUTED claim is refused, so a citation cannot outlive its
verification. The seven layers must each carry at least one rule, so a layer cannot be emptied
quietly. WHAT IT DOES NOT PROVE: that a `check:` script is correct, or that a claim row's wording
matches the rule's wording. The first is that script's own selftest; the second is the reviewer's.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = "plugins/rails-stack/skills/design-system/references/architecture.md"
EVIDENCE = "docs/design/frontend-architecture-claims.md"
LAYERS = ("shell", "navigation", "template", "regions", "state", "cross-cutting")
ROW = re.compile(r"^\|\s*(A\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
BASIS = re.compile(r"^(check|claim|decision):\s*(\S+)$")
VERDICT_ROW = re.compile(r"^\|\s*(C\d+'?)\s*\|\s*([^|]+?)\s*\|")
DECISION_ROW = re.compile(r"^\|\s*(D\d+)\s*\|")


def claim_verdicts(text: str) -> dict[str, str]:
    """`{claim id: verdict}` from the tables after `## Verdicts`; a later row for an id wins."""
    head, sep, tail = text.partition("## Verdicts")
    if not sep:
        return {}
    out: dict[str, str] = {}
    for line in tail.splitlines():
        m = VERDICT_ROW.match(line)
        if m:
            out[m.group(1)] = "CONFIRMED" if re.match(r"(C|CONFIRMED)\b", m.group(2)) else m.group(2)
    return out


def decisions(text: str) -> set[str]:
    head, sep, tail = text.partition("## Maintainer decisions")
    return {m.group(1) for line in tail.splitlines() if (m := DECISION_ROW.match(line))} if sep else set()


def judge(page: str, evidence: str, root: Path) -> tuple[list[str], int]:
    findings: list[str] = []
    verdicts, decided = claim_verdicts(evidence), decisions(evidence)
    seen_ids: set[str] = set()
    layers_seen: set[str] = set()
    rows = 0
    for line in page.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        rows += 1
        rid, layer, rule, basis, _source = m.groups()
        if rid in seen_ids:
            findings.append(f"{rid}: duplicate rule id")
        seen_ids.add(rid)
        layers_seen.add(layer)
        if layer not in LAYERS:
            findings.append(f"{rid}: layer {layer!r} is not one of {', '.join(LAYERS)}")
        b = BASIS.match(basis)
        if not b:
            findings.append(f"{rid}: basis {basis!r} is not `check: <path>`, `claim: C#` or `decision: D#` -- a rule with no basis is not shipped")
            continue
        kind, ref = b.groups()
        if kind == "check" and not (root / ref).is_file():
            findings.append(f"{rid}: check {ref} is not a file in this repository")
        elif kind == "claim":
            verdict = verdicts.get(ref)
            if verdict is None:
                findings.append(f"{rid}: claim {ref} has no verdict in {EVIDENCE}")
            elif verdict != "CONFIRMED":
                findings.append(f"{rid}: claim {ref} is {verdict}, not CONFIRMED; reword the rule or drop it")
        elif kind == "decision" and ref not in decided:
            findings.append(f"{rid}: decision {ref} is not recorded in {EVIDENCE}")
    if not rows:
        findings.append(f"{PAGE}: no rule rows were read (a check that reads nothing is not a pass)")
    for layer in LAYERS:
        if rows and layer not in layers_seen:
            findings.append(f"layer {layer!r} carries no rule")
    return findings, rows


def selftest() -> int:
    ok_evidence = (
        "## Verdicts\n| C1 | C | x |\n| C2 | I | x |\n| C3 | R, reword | x |\n| C4 | I | x |\n| C4 | C | x |\n"
        "## Maintainer decisions\n| id | Decision |\n|---|---|\n| D1 | a |\n"
    )
    layers = "".join(
        f"| A{i} | {layer} | rule | decision: D1 | ours |\n" for i, layer in enumerate(LAYERS, 1))

    def run(page_rows: str, evidence: str = ok_evidence, files: tuple[str, ...] = ("s.py",)) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            for f in files:
                (Path(td) / f).write_text("x\n")
            return judge(layers + page_rows, evidence, Path(td))[0]

    cases = [
        ("a clean page passes", run(""), lambda f: f == []),
        ("a confirmed claim passes", run("| A9 | shell | r | claim: C1 | s |\n"), lambda f: f == []),
        ("a later verdict wins over an earlier one", run("| A9 | shell | r | claim: C4 | s |\n"), lambda f: f == []),
        ("an existing check path passes", run("| A9 | shell | r | check: s.py | s |\n"), lambda f: f == []),
        ("a missing check path is refused", run("| A9 | shell | r | check: nope.py | s |\n"), lambda f: any("not a file" in x for x in f)),
        ("an INCONCLUSIVE claim is refused", run("| A9 | shell | r | claim: C2 | s |\n"), lambda f: any("not CONFIRMED" in x for x in f)),
        ("a REFUTED claim is refused", run("| A9 | shell | r | claim: C3 | s |\n"), lambda f: any("not CONFIRMED" in x for x in f)),
        ("an unknown claim is refused", run("| A9 | shell | r | claim: C99 | s |\n"), lambda f: any("no verdict" in x for x in f)),
        ("an unrecorded decision is refused", run("| A9 | shell | r | decision: D9 | s |\n"), lambda f: any("not recorded" in x for x in f)),
        ("a row with no basis is refused", run("| A9 | shell | r | advice | s |\n"), lambda f: any("not shipped" in x for x in f)),
        ("a duplicate id is refused", run("| A1 | shell | r | decision: D1 | s |\n"), lambda f: any("duplicate" in x for x in f)),
        ("an unknown layer is refused", run("| A9 | colour | r | decision: D1 | s |\n"), lambda f: any("not one of" in x for x in f)),
        ("a page with no rows is refused", judge("no table here\n", ok_evidence, ROOT)[0], lambda f: any("no rule rows" in x for x in f)),
        ("a layer left empty is refused", judge("".join(f"| A{i} | {l} | r | decision: D1 | s |\n" for i, l in enumerate(LAYERS[:-1], 1)),
                                                ok_evidence, ROOT)[0], lambda f: any("carries no rule" in x for x in f)),
    ]
    bad = 0
    for label, findings, pred in cases:
        passed = pred(findings)
        bad += not passed
        print(f"  [{'ok' if passed else 'FAIL'}] {label}" + ("" if passed else f": {findings}"))
    print(f"check_architecture_rules selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    page, evidence = ROOT / PAGE, ROOT / EVIDENCE
    for p in (page, evidence):
        if not p.is_file():
            print(f"FAIL: {p.relative_to(ROOT)} does not exist")
            return 1
    findings, rows = judge(page.read_text(encoding="utf-8"), evidence.read_text(encoding="utf-8"), ROOT)
    for f in findings:
        print(f"FAIL: {f}")
    print(f"architecture rules: {rows} rule(s) read, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
