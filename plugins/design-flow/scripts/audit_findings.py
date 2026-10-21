#!/usr/bin/env python3
"""The findings contract of the interface audit: every finding names a framework rule, and its
authority is COMPUTED from that rule's basis, never written by whoever found it (#2221).

Run:  python3 audit_findings.py check   findings.json [--root DIR]
      python3 audit_findings.py report  findings.json [--root DIR] [--out report.md]
      python3 audit_findings.py from-judge NAME judge.json --screens N      # reuse a qa-flow judge's output
      python3 audit_findings.py merge a.json b.json ...                     # one document, every finding kept
      python3 audit_findings.py --selftest

WHY THIS EXISTS. The owner's rule is that a rule not enforced is useless, and the framework's rules
table (`design-system/references/architecture.md`) gives every rule a basis: a `claim:` (a published
standard or design-system pattern, confirmed against its source), a `decision:` (ours) or a `check:`
(a script that exists). An audit that lets an agent write "violates WCAG" over a house rule would
undo that, and an agent under time pressure does exactly that: it reaches for the more persuasive
word. So the contract refuses the freedom.

  * `rule` must be an id in the registry (`../reference/architecture-rules.json`, derived from the
    page by `scripts/derive_architecture_rules.py`; a plugin reaches only its own files).
  * The finding may NOT carry `authority`, `rank` or `severity`. Authority comes from the registry
    (`claim` -> standard, anything else -> house rule); rank is computed here.
  * `evidence` is a screenshot that exists under `--root`, or a measured value. A finding with no
    evidence is an opinion.
  * A house-rule finding's free text may not say it breaks a standard (WCAG, "violates", "standard").
  * The document must say how many screens it examined, and the number must be above zero: a clean
    report over nothing is not a clean report.

WHAT IT DOES NOT PROVE: that the evidence shows the defect. It proves the finding is addressed to a
real rule, is not overclaimed, and carries something a reader can open.

Exit: 0 every finding is well-formed · 1 a finding is refused · 2 the file is unusable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "reference" / "architecture-rules.json"
FORBIDDEN_KEYS = ("authority", "rank", "severity", "basis")
EVIDENCE_KINDS = ("screenshot", "measured")
# Words that claim a standard. A house-rule finding may not use them about itself.
STANDARD_WORDS = re.compile(r"\b(WCAG|violat\w*|non-?complian\w*|standards?)\b", re.I)
# A qa-flow judge's findings become findings against one framework rule each.
JUDGE_RULES = {"layout_fit": "A23", "text_resize": "A24", "theme_parity": "A25", "link_audit": "A26"}


class Unusable(Exception):
    pass


def load_registry(path: Path = REGISTRY) -> dict[str, dict]:
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError) as exc:
        raise Unusable(f"cannot read the rule registry {path}: {exc}") from exc
    if not rules:
        raise Unusable(f"the rule registry {path} holds no rules")
    return {r["id"]: r for r in rules}


def validate(doc: object, registry: dict[str, dict], root: Path) -> list[str]:
    if not isinstance(doc, dict) or not isinstance(doc.get("findings"), list):
        raise Unusable("the file is not an object with a `findings` list")
    problems: list[str] = []
    examined = doc.get("screens_examined")
    if not isinstance(examined, int) or isinstance(examined, bool) or examined < 1:
        problems.append("`screens_examined` must be an integer above zero: a report over no screens says nothing")
    for n, f in enumerate(doc["findings"], 1):
        who = f"finding {n}"
        if not isinstance(f, dict):
            problems.append(f"{who}: not an object")
            continue
        rule = registry.get(f.get("rule"))
        if rule is None:
            problems.append(f"{who}: rule {f.get('rule')!r} is not in the framework's rules table")
        for k in FORBIDDEN_KEYS:
            if k in f:
                problems.append(f"{who}: carries `{k}`, which is derived from the rule and may not be written")
        if not isinstance(f.get("screen"), str) or not f["screen"].strip():
            problems.append(f"{who}: no `screen`")
        inst = f.get("instances")
        if not isinstance(inst, int) or isinstance(inst, bool) or inst < 1:
            problems.append(f"{who}: `instances` must be an integer of at least 1")
        ev = f.get("evidence")
        if not isinstance(ev, dict) or ev.get("kind") not in EVIDENCE_KINDS or not str(ev.get("ref", "")).strip():
            problems.append(f"{who}: `evidence` must be {{kind: screenshot|measured, ref: ...}}")
        elif ev["kind"] == "screenshot" and not (root / ev["ref"]).is_file():
            problems.append(f"{who}: screenshot {ev['ref']!r} is not a file under {root}")
        text = " ".join(str(f.get(k, "")) for k in ("message", "proposal"))
        if rule is not None and rule["authority"] == "house" and STANDARD_WORDS.search(text):
            problems.append(f"{who}: rule {rule['id']} is a house rule ({rule['basis']}: {rule['ref']}) but the text "
                            f"claims a standard ({STANDARD_WORDS.search(text).group(0)!r})")
    return problems


def decorate(doc: dict, registry: dict[str, dict]) -> list[dict]:
    """Findings with the derived authority and a rank, standards first, then by reach."""
    screens_by_rule: dict[str, set[str]] = {}
    for f in doc["findings"]:
        screens_by_rule.setdefault(f["rule"], set()).add(f["screen"])
    out = []
    for f in doc["findings"]:
        r = registry[f["rule"]]
        label = (f"standard: {r['source']}" if r["authority"] == "standard"
                 else f"house rule ({r['basis']}: {r['ref']})")
        out.append({**f, "authority": r["authority"], "authority_label": label, "rule_text": r["rule"],
                    "reach": len(screens_by_rule[f["rule"]])})
    out.sort(key=lambda d: (d["authority"] != "standard", -d["reach"], -d["instances"],
                            int(d["rule"][1:]), d["screen"]))
    for i, d in enumerate(out, 1):
        d["rank"] = i
    return out


def report_md(doc: dict, registry: dict[str, dict]) -> str:
    rows = decorate(doc, registry)
    lines = [f"# {doc.get('audit', 'Interface audit')}", "",
             f"Screens examined: {doc['screens_examined']}. Findings: {len(rows)}. "
             "Authority is derived from the framework's rules table; a house rule is never a standards failure.", ""]
    if not rows:
        lines.append("No findings against the rules this audit can measure.")
        return "\n".join(lines) + "\n"
    lines += ["| rank | rule | authority | screen | instances | evidence | what |", "|---|---|---|---|---|---|---|"]
    for d in rows:
        what = (d.get("message") or d["rule_text"]).replace("|", "\\|")
        lines.append(f"| {d['rank']} | {d['rule']} | {d['authority_label']} | {d['screen']} | {d['instances']} "
                     f"| {d['evidence']['kind']}: {d['evidence']['ref']} | {what} |")
    props = [d for d in rows if d.get("proposal")]
    if props:
        lines += ["", "## Proposed improvements (as a mock-up first, never as code)", ""]
        lines += [f"{d['rank']}. **{d['rule']}** on {d['screen']}: {d['proposal']}" for d in props]
    return "\n".join(lines) + "\n"


def from_judge(name: str, data: object, screens: int) -> dict:
    """A qa-flow judge's `--json` output as a findings document against one framework rule."""
    rule = JUDGE_RULES.get(name)
    if rule is None:
        raise Unusable(f"unknown judge {name!r}; known: {', '.join(JUDGE_RULES)}")
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise Unusable(f"{name}: the output has no findings list")
    findings = []
    for it in items:
        screen = (it.get("examples") or [it.get("ref") or it.get("target") or ""])[0]
        findings.append({"rule": rule, "screen": str(screen) or "(unknown)", "instances": max(int(it.get("count") or 1), 1),
                         "evidence": {"kind": "measured", "ref": f"{name}: {it.get('rule', '')} {it.get('detail', '')}".strip()},
                         "message": str(it.get("detail", ""))})
    return {"audit": f"{name} findings against {rule}", "screens_examined": screens, "findings": findings}


def merge(docs: list[dict]) -> dict:
    """One findings document from several: every finding kept, the larger screen count."""
    if not docs:
        raise Unusable("nothing to merge")
    return {"audit": "; ".join(str(d.get("audit", "")) for d in docs if d.get("audit")) or "merged audit",
            "screens_examined": max(int(d.get("screens_examined") or 0) for d in docs),
            "findings": [f for d in docs for f in d.get("findings", [])]}


def selftest() -> int:
    registry = {
        "A1": {"id": "A1", "authority": "standard", "basis": "claim", "ref": "C2", "source": "HTML spec", "rule": "one main"},
        "A2": {"id": "A2", "authority": "house", "basis": "decision", "ref": "D7", "source": "ours", "rule": "skip link"},
        "A9": {"id": "A9", "authority": "house", "basis": "decision", "ref": "D7", "source": "ours", "rule": "x"},
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "shot.png").write_text("x")

        def doc(**over):
            f = {"rule": "A1", "screen": "/orders", "instances": 2, "evidence": {"kind": "measured", "ref": "main count 2"}}
            f.update(over)
            return {"audit": "t", "screens_examined": 3, "findings": [f]}

        def problems(d):
            return validate(d, registry, root)

        base = doc()
        cases = [
            ("a well-formed finding passes", problems(base) == []),
            ("a screenshot that exists passes", problems(doc(evidence={"kind": "screenshot", "ref": "shot.png"})) == []),
            ("a screenshot that is not a file is refused", any("not a file" in p for p in problems(doc(evidence={"kind": "screenshot", "ref": "nope.png"})))),
            ("an unknown rule is refused", any("not in the framework" in p for p in problems(doc(rule="A99")))),
            ("a written authority is refused", any("`authority`" in p for p in problems(doc(authority="standard")))),
            ("a written rank is refused", any("`rank`" in p for p in problems(doc(rank=1)))),
            ("a finding with no evidence is refused", any("evidence" in p for p in problems(doc(evidence={})))),
            ("an evidence kind that is neither is refused", any("evidence" in p for p in problems(doc(evidence={"kind": "opinion", "ref": "x"})))),
            ("a zero instance count is refused", any("instances" in p for p in problems(doc(instances=0)))),
            ("a missing screen is refused", any("`screen`" in p for p in problems(doc(screen="")))),
            ("a house rule that claims WCAG is refused", any("claims a standard" in p for p in problems(doc(rule="A2", message="violates WCAG 2.4.1")))),
            ("a house rule that says it breaks a standard is refused", any("claims a standard" in p for p in problems(doc(rule="A9", proposal="this is non-compliant")))),
            ("a standard rule may say WCAG", problems(doc(rule="A1", message="WCAG says one main")) == []),
            ("zero screens examined is refused", any("screens_examined" in p for p in problems({**base, "screens_examined": 0}))),
            ("a boolean is not a screen count", any("screens_examined" in p for p in problems({**base, "screens_examined": True}))),
            ("a document that is not a findings list is unusable", _raises(lambda: validate({"findings": 3}, registry, root))),
        ]
        d1 = {"audit": "t", "screens_examined": 3, "findings": [
            {"rule": "A2", "screen": "/a", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A2", "screen": "/b", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A2", "screen": "/c", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A1", "screen": "/a", "instances": 1, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A1", "screen": "/b", "instances": 1, "evidence": {"kind": "measured", "ref": "m"}}]}
        ranked = decorate(d1, registry)
        cases += [
            ("a standard outranks a house rule whatever its reach and instance count", ranked[0]["rule"] == "A1" and ranked[-1]["rule"] == "A2"),
            ("authority is derived from the registry", ranked[0]["authority"] == "standard" and ranked[-1]["authority"] == "house"),
            ("reach counts distinct screens", ranked[0]["reach"] == 2 and ranked[-1]["reach"] == 3),
            ("ranks are 1..n", [d["rank"] for d in ranked] == [1, 2, 3, 4, 5]),
            ("the report labels a house rule as one", "house rule (decision: D7)" in report_md(d1, registry)),
            ("the report labels a standard with its source", "standard: HTML spec" in report_md(d1, registry)),
            ("a clean report still says how many screens it examined", "Screens examined: 3" in report_md({"audit": "t", "screens_examined": 3, "findings": []}, registry)),
        ]
        m = merge([{"audit": "a", "screens_examined": 2, "findings": [1, 2]}, {"audit": "b", "screens_examined": 5, "findings": [3]}])
        cases += [
            ("a merge keeps every finding", m["findings"] == [1, 2, 3]),
            ("a merge takes the larger screen count", m["screens_examined"] == 5),
            ("a merge of nothing is unusable", _raises(lambda: merge([]))),
        ]
        fj = from_judge("layout_fit", {"findings": [{"rule": "clipped", "ref": "x", "detail": "hidden", "count": 4, "examples": ["/p"]}]}, 5)
        cases += [
            ("a judge's finding maps to its framework rule", fj["findings"][0]["rule"] == "A23" and fj["findings"][0]["screen"] == "/p"),
            ("a judge's count becomes the instance count", fj["findings"][0]["instances"] == 4),
            ("an unknown judge is unusable", _raises(lambda: from_judge("nope", [], 1))),
            ("a theme_parity list maps to A25", from_judge("theme_parity", [{"ref": "/r", "rule": "r", "detail": "d"}], 2)["findings"][0]["rule"] == "A25"),
        ]
    real = load_registry()
    cases.append(("the real registry loads and holds rules", len(real) > 0 and all(r["authority"] in ("standard", "house") for r in real.values())))
    cases.append(("every judge maps to a rule that exists", all(r in real for r in JUDGE_RULES.values())))
    bad = 0
    for label, ok in cases:
        bad += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"audit_findings selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


def _raises(fn) -> bool:
    try:
        fn()
    except Unusable:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("check", "report"):
        p = sub.add_parser(name)
        p.add_argument("findings")
        p.add_argument("--root", default=".")
        p.add_argument("--registry", default=str(REGISTRY))
        if name == "report":
            p.add_argument("--out")
    p = sub.add_parser("merge")
    p.add_argument("docs", nargs="+")
    p = sub.add_parser("from-judge")
    p.add_argument("name")
    p.add_argument("judge_json")
    p.add_argument("--screens", type=int, required=True, help="how many screens the judge examined")
    a = ap.parse_args(argv)
    try:
        if a.selftest:
            return selftest()
        if a.cmd == "merge":
            print(json.dumps(merge([json.loads(Path(d).read_text(encoding="utf-8")) for d in a.docs]), indent=1))
            return 0
        if a.cmd == "from-judge":
            print(json.dumps(from_judge(a.name, json.loads(Path(a.judge_json).read_text()), a.screens), indent=1))
            return 0
        if a.cmd in ("check", "report"):
            registry = load_registry(Path(a.registry))
            doc = json.loads(Path(a.findings).read_text(encoding="utf-8"))
            problems = validate(doc, registry, Path(a.root))
            for p in problems:
                print(f"REFUSED: {p}")
            if problems:
                return 1
            if a.cmd == "report":
                text = report_md(doc, registry)
                Path(a.out).write_text(text, encoding="utf-8") if a.out else print(text, end="")
            else:
                print(f"{len(doc['findings'])} finding(s) over {doc['screens_examined']} screen(s): all well-formed")
            return 0
        ap.print_help()
        return 2
    except (Unusable, OSError, ValueError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
