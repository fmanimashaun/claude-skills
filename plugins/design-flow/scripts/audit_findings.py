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
    page by `scripts/derive_architecture_rules.py`). **The registry path is not an option**: a forged
    registry could mark every rule a standard, so the CLI reads only the committed file, and
    `load_registry` refuses an entry whose `authority` disagrees with its basis.
  * A finding has exactly the keys `rule screen instances evidence message proposal`. It may NOT
    carry `authority`, `rank` or `severity`: authority comes from the registry (`claim` -> standard,
    anything else -> house rule) and rank is computed here.
  * `evidence` is a screenshot that resolves to a file UNDER `--root`, or a measured value.
  * EVERY string of a house-rule finding is scanned, by a structural walk of the whole object (not a
    list of fields), for words that claim a standard (WCAG, Success Criterion, Level A/AA/AAA, ADA,
    EN 301 549, Section 508, ARIA spec, a11y requirement, "violates", "non-compliant", "standard").
    The `screen` must be a path or URL with no spaces and is scanned with its separators read as
    spaces; the document's `audit` title and `unverified` list are scanned when house-rule findings
    sit beside them; unknown document keys are refused.
  * The document says which rules it audited and over how many screens each, and the report prints
    every other rule under **Not audited**, with what blocks it. A clean report names the rules it
    measured; it never says the interface is good.
  * Routes a judge could not verify are carried as `unverified`, never counted as clean.

WHAT IT DOES NOT PROVE: that the evidence shows the defect. It proves the finding is addressed to a
real rule, is not overclaimed, and carries something a reader can open.

Exit: 0 every finding is well-formed · 1 a finding is refused · 2 the file is unusable.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "reference" / "architecture-rules.json"
FINDING_KEYS = ("rule", "screen", "instances", "evidence", "message", "proposal")
EVIDENCE_KEYS = ("kind", "ref")
EVIDENCE_KINDS = ("screenshot", "measured")
# Words that claim a standard. A house-rule finding may not use them about itself, anywhere.
CLAIM_WORDS = (r"WCAG|WAI-ARIA|success\s+criteri(?:on|a)|level\s+AAA?|level\s+A|ADA|EN\s*301[\s.]?549|section\s+508|"
               r"ARIA\s+spec\w*|a11y\s+requirement\w*")
PROSE_WORDS = r"violat\w*|non-?complian\w*|standards?"
STANDARD_WORDS = re.compile(rf"\b({CLAIM_WORDS}|{PROSE_WORDS})\b", re.I)
# A screen is a path or a URL with no spaces, so it cannot carry a sentence; its separators are read as spaces
# before it is scanned, so "/WCAG-2.4.1-failure" is caught while a plain route name passes.
SCREEN_SHAPE = re.compile(r"^(/\S*|https?://\S+)$")
CLAIM_ONLY = re.compile(rf"\b({CLAIM_WORDS})\b", re.I)
DOC_KEYS = ("audit", "audited", "unverified", "skipped_non_2xx", "findings")
# A qa-flow judge's findings become findings against one framework rule each.
JUDGE_RULES = {"layout_fit": "A23", "text_resize": "A24", "theme_parity": "A25", "link_audit": "A26"}
# What blocks a rule from being audited today. A rule with no entry falls back on its basis.
BLOCKED = {
    "A3": "needs the mock-up record (#2211)",
    "A5": "needs the mock-up record's `Nav:` line (#2226)",
    "A8": "needs a way to drive a list's controls (#2229)",
    "A9": "needs a client-routed stack's crawl (#2222)",
    "A10": "needs `--screens` (the list linking each URL to its mock-up record, #2251)",
    "A19": "axe runs in the a11y-auditor agent; no judge with JSON output yet",
    "A20": "axe runs in the a11y-auditor agent; no judge with JSON output yet",
    "A21": "no focus check yet (#2228)",
    "A22": "axe runs in the a11y-auditor agent; no judge with JSON output yet",
    "A27": "no Core Web Vitals check yet (#2230)",
    "A59": "no forced-state check yet (#2229)",
    "A60": "no forced-state check yet (#2229)",
}
# The template rules (A29 to A58) this audit does not measure, each with the reason. The seven it does measure
# (A31, A34, A53 to A57) are judged only with `--screens`, and say so when it is absent.
_NEEDS_JOURNEY = "needs a declared flow or a judgement: no check yet (#2251)"
NOT_MEASURED_TEMPLATE = {
    **{r: _NEEDS_JOURNEY for r in ("A29", "A30", "A33")},
    "A32": "needs a driven journey: the back link's state depends on the step before (#2229)",
    **{f"A{n}": "a check-answers or confirmation page is declared (`multi-step: check-answers|confirmation`, #2310), but its rows are not built yet (#2327)" for n in range(35, 43)},
    **{f"A{n}": "a task-list page is declared (`multi-step: task-list`, #2310), but its rows are not built yet (#2327)" for n in range(43, 53)},
    "A58": "needs a driver for a partial update (#2229)",
}
NEEDS_SCREENS = {r: "judged only for a screen whose record declares its template, via `--screens` (#2251); none did in this run"
                 for r in ("A31", "A34", "A53", "A54", "A55", "A56", "A57")}
BLOCKED.update(NEEDS_SCREENS)
BLOCKED.update(NOT_MEASURED_TEMPLATE)
JUDGEMENT = ("density matches the surface, content hierarchy, interaction feedback, whether a screen is the right "
             "template: no verdict channel yet (#2225, rows tracked in #2309)")


class Unusable(Exception):
    pass


def load_registry(path: Path = REGISTRY) -> dict[str, dict]:
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError) as exc:
        raise Unusable(f"cannot read the rule registry {path}: {exc}") from exc
    if not rules:
        raise Unusable(f"the rule registry {path} holds no rules")
    for r in rules:
        want = "standard" if r.get("basis") == "claim" else "house"
        if r.get("authority") != want:
            raise Unusable(f"the rule registry {path}: {r.get('id')} says authority {r.get('authority')!r} but its "
                           f"basis {r.get('basis')!r} derives {want!r}; the registry is forged or stale")
    return {r["id"]: r for r in rules}


def every_string(obj: object, skip: tuple[str, ...] = ()):
    """EVERY string inside obj, however deep, dict keys included: the structural walk. Fields are not
    listed one at a time, because each listed field is a field someone forgets (#2253: evidence.ref,
    then screen, then the audit title)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            if k not in skip:
                yield from every_string(v, skip)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from every_string(v, skip)


def claim_in(strings, *, screen: str = "") -> str | None:
    """The first standard-claiming word in the strings; the screen is scanned for the high-signal
    claims only, with its separators read as spaces."""
    for t in strings:
        m = STANDARD_WORDS.search(t)
        if m:
            return m.group(0)
    if screen:
        m = CLAIM_ONLY.search(re.sub(r"[-_/.]+", " ", screen))
        if m:
            return m.group(0)
    return None


def _under(root: Path, ref: str) -> bool:
    try:
        target = (root / ref).resolve()
        return target.is_file() and target.is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def validate(doc: object, registry: dict[str, dict], root: Path) -> list[str]:
    if not isinstance(doc, dict) or not isinstance(doc.get("findings"), list):
        raise Unusable("the file is not an object with a `findings` list")
    problems: list[str] = []
    audited = doc.get("audited")
    if not isinstance(audited, dict) or not audited:
        problems.append("`audited` must map each rule the audit measured to the screens it examined: a report that "
                        "audited no rule says nothing")
        audited = {}
    for rid, n in audited.items():
        if rid not in registry:
            problems.append(f"audited rule {rid!r} is not in the framework's rules table")
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            problems.append(f"audited rule {rid!r}: the screen count must be an integer above zero")
    for k in doc:
        if k not in DOC_KEYS:
            problems.append(f"unknown document key `{k}` (allowed: {', '.join(DOC_KEYS)})")
    unv = doc.get("unverified", [])
    if not isinstance(unv, list) or not all(isinstance(u, str) and SCREEN_SHAPE.match(u) for u in unv):
        problems.append("`unverified` must be a list of screens, each a path or URL with no spaces")
    has_house = any(isinstance(f, dict) and (registry.get(f.get("rule")) or {}).get("authority") == "house"
                    for f in doc["findings"])
    if has_house:
        claim = claim_in(list(every_string({"audit": doc.get("audit", ""), "unverified": unv})))
        if claim:
            problems.append(f"the document's title or unverified list claims a standard ({claim!r}) next to house-rule "
                            "findings; the report prints them side by side")
    for n, f in enumerate(doc["findings"], 1):
        who = f"finding {n}"
        if not isinstance(f, dict):
            problems.append(f"{who}: not an object")
            continue
        rule = registry.get(f.get("rule"))
        if rule is None:
            problems.append(f"{who}: rule {f.get('rule')!r} is not in the framework's rules table")
        elif f["rule"] not in audited:
            problems.append(f"{who}: rule {f['rule']} is not among the rules this document says it audited")
        for k in f:
            if k in ("authority", "rank", "severity", "basis"):
                problems.append(f"{who}: carries `{k}`, which is derived from the rule and may not be written")
            elif k not in FINDING_KEYS:
                problems.append(f"{who}: unknown key `{k}` (allowed: {', '.join(FINDING_KEYS)}); free text hides there")
        if not isinstance(f.get("screen"), str) or not SCREEN_SHAPE.match(f["screen"]):
            problems.append(f"{who}: `screen` must be a path or URL with no spaces, not {f.get('screen')!r}")
        inst = f.get("instances")
        if not isinstance(inst, int) or isinstance(inst, bool) or inst < 1:
            problems.append(f"{who}: `instances` must be an integer of at least 1")
        ev = f.get("evidence")
        if not isinstance(ev, dict) or ev.get("kind") not in EVIDENCE_KINDS or not str(ev.get("ref", "")).strip():
            problems.append(f"{who}: `evidence` must be {{kind: screenshot|measured, ref: ...}}")
        else:
            for k in ev:
                if k not in EVIDENCE_KEYS:
                    problems.append(f"{who}: unknown evidence key `{k}`")
            if ev["kind"] == "screenshot" and not _under(root, str(ev["ref"])):
                problems.append(f"{who}: screenshot {ev['ref']!r} is not a file under {root}")
        if rule is not None and rule["authority"] == "house":
            claim = claim_in(every_string({k: v for k, v in f.items() if k not in ("rule", "screen")}),
                             screen=str(f.get("screen", "")))
            if claim:
                problems.append(f"{who}: rule {rule['id']} is a house rule ({rule['basis']}: {rule['ref']}) but its text "
                                f"claims a standard ({claim!r})")
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


def not_audited(doc: dict, registry: dict[str, dict]) -> dict[str, list[str]]:
    """Every rule this run did not measure, grouped by what blocks it."""
    groups: dict[str, list[str]] = {}
    for rid, r in sorted(registry.items(), key=lambda kv: int(kv[0][1:])):
        if rid in doc["audited"]:
            continue
        why = BLOCKED.get(rid) or (f"enforced by `{r['ref']}`; run that check separately" if r["basis"] == "check"
                                   else "no mechanical check in this audit yet (no later slice is filed for it)")
        groups.setdefault(why, []).append(rid)
    return groups


def report_md(doc: dict, registry: dict[str, dict]) -> str:
    rows = decorate(doc, registry)
    audited = ", ".join(f"{rid} ({n} screen{'s' if n != 1 else ''})" for rid, n in sorted(doc["audited"].items(), key=lambda kv: int(kv[0][1:])))
    lines = [f"# {doc.get('audit', 'Interface audit')}", "",
             f"Rules audited: {audited}. Findings: {len(rows)}. "
             "Authority is derived from the framework's rules table; a house rule is never a standards failure.", ""]
    if not rows:
        lines += [f"No findings against the rules audited ({', '.join(sorted(doc['audited'], key=lambda r: int(r[1:])))}). "
                  "That says nothing about the rules under Not audited.", ""]
    else:
        lines += ["| rank | rule | authority | screen | instances | evidence | what |", "|---|---|---|---|---|---|---|"]
        for d in rows:
            what = (d.get("message") or d["rule_text"]).replace("|", "\\|")
            lines.append(f"| {d['rank']} | {d['rule']} | {d['authority_label']} | {d['screen']} | {d['instances']} "
                         f"| {d['evidence']['kind']}: {d['evidence']['ref']} | {what} |")
        props = [d for d in rows if d.get("proposal")]
        if props:
            lines += ["", "## Proposed improvements (as a mock-up first, never as code)", ""]
            lines += [f"{d['rank']}. **{d['rule']}** on {d['screen']}: {d['proposal']}" for d in props]
        lines.append("")
    if doc.get("unverified"):
        lines += ["## Unverified: not judged, and not a pass", ""] + [f"- {u}" for u in doc["unverified"]] + [""]
    lines += ["## Not audited", ""]
    lines += [f"- {', '.join(ids)}: {why}" for why, ids in not_audited(doc, registry).items()]
    lines.append(f"- Judgement rules, not in the table above: {JUDGEMENT}")
    return "\n".join(lines) + "\n"


def from_judge(name: str, data: object, screens: int) -> dict:
    """A qa-flow judge's `--json` output as a findings document against one framework rule.

    One finding per example route (so reach counts the routes listed, a floor of the judge's own
    count, which the message states); routes the judge could not verify or that redirected are
    carried as `unverified`, never as clean."""
    rule = JUDGE_RULES.get(name)
    if rule is None:
        raise Unusable(f"unknown judge {name!r}; known: {', '.join(JUDGE_RULES)}")
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise Unusable(f"{name}: the output has no findings list")
    findings, unverified = [], []
    if isinstance(data, dict):
        for k in ("unverified", "redirected"):
            extra = data.get(k) or []
            if not isinstance(extra, list):
                raise Unusable(f"{name}: `{k}` is not a list")
            unverified += [str(x) for x in extra]
    for it in items:
        if not isinstance(it, dict):
            raise Unusable(f"{name}: a finding is not an object ({it!r})")
        total = max(int(it.get("count") or 1), 1)
        examples = [str(e) for e in (it.get("examples") or [it.get("ref") or it.get("target") or "/unknown"])]
        for screen in examples:
            findings.append({"rule": rule, "screen": screen or "/unknown", "instances": 1,
                             "evidence": {"kind": "measured", "ref": f"{name}: {it.get('rule', '')} {it.get('detail', '')}".strip()},
                             "message": f"{it.get('detail', '')} (the judge counts {total} route(s) affected; {len(examples)} listed)".strip()})
    return {"audit": f"{name} findings against {rule}", "audited": {rule: screens}, "unverified": unverified,
            "findings": findings}


def merge(docs: list[dict]) -> dict:
    """One findings document from several: every finding kept; each rule keeps the screens it was audited over."""
    if not docs:
        raise Unusable("nothing to merge")
    audited: dict[str, int] = {}
    for d in docs:
        for rid, n in (d.get("audited") or {}).items():
            audited[rid] = max(audited.get(rid, 0), n)
    return {"audit": "; ".join(str(d.get("audit", "")) for d in docs if d.get("audit")) or "merged audit",
            "audited": audited, "unverified": sorted({u for d in docs for u in d.get("unverified", [])}),
            "findings": [f for d in docs for f in d.get("findings", [])]}


def selftest() -> int:
    registry = {
        "A1": {"id": "A1", "authority": "standard", "basis": "claim", "ref": "C2", "source": "HTML spec", "rule": "one main"},
        "A2": {"id": "A2", "authority": "house", "basis": "decision", "ref": "D7", "source": "ours", "rule": "skip link"},
        "A9": {"id": "A9", "authority": "house", "basis": "decision", "ref": "D7", "source": "ours", "rule": "x"},
        "A11": {"id": "A11", "authority": "house", "basis": "check", "ref": "scripts/t.py", "source": "ours", "rule": "tables"},
        "A21": {"id": "A21", "authority": "standard", "basis": "claim", "ref": "C20", "source": "WCAG", "rule": "focus"},
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "run"
        root.mkdir()
        (root / "shot.png").write_text("x")
        (Path(td) / "outside.png").write_text("x")

        def doc(**over):
            f = {"rule": "A1", "screen": "/orders", "instances": 2, "evidence": {"kind": "measured", "ref": "main count 2"}}
            f.update(over)
            return {"audit": "t", "audited": {"A1": 3, "A2": 3, "A9": 3}, "findings": [f]}

        def problems(d):
            return validate(d, registry, root)

        base = doc()
        house = lambda **o: problems(doc(rule="A2", **o))
        cases = [
            ("a well-formed finding passes", problems(base) == []),
            ("a screenshot that exists under the root passes", problems(doc(evidence={"kind": "screenshot", "ref": "shot.png"})) == []),
            ("a screenshot that is not a file is refused", any("not a file" in p for p in problems(doc(evidence={"kind": "screenshot", "ref": "nope.png"})))),
            ("an absolute screenshot path is refused", any("not a file" in p for p in problems(doc(evidence={"kind": "screenshot", "ref": "/etc/hosts"})))),
            ("a screenshot that climbs out of the root is refused", any("not a file" in p for p in problems(doc(evidence={"kind": "screenshot", "ref": "../outside.png"})))),
            ("an unknown rule is refused", any("not in the framework" in p for p in problems(doc(rule="A99")))),
            ("a rule the document did not say it audited is refused", any("did not say" in p or "not among the rules" in p for p in problems(doc(rule="A11")))),
            ("a written authority is refused", any("may not be written" in p for p in problems(doc(authority="standard")))),
            ("a written rank is refused", any("may not be written" in p for p in problems(doc(rank=1)))),
            ("an unknown key is refused", any("unknown key" in p for p in problems(doc(note="WCAG 2.4.1")))),
            ("an unknown evidence key is refused", any("unknown evidence key" in p for p in problems(doc(evidence={"kind": "measured", "ref": "x", "why": "y"})))),
            ("a finding with no evidence is refused", any("evidence" in p for p in problems(doc(evidence={})))),
            ("an evidence kind that is neither is refused", any("evidence" in p for p in problems(doc(evidence={"kind": "opinion", "ref": "x"})))),
            ("a zero instance count is refused", any("instances" in p for p in problems(doc(instances=0)))),
            ("a missing screen is refused", any("`screen`" in p for p in problems(doc(screen="")))),
            ("a house rule that claims WCAG in its message is refused", any("claims a standard" in p for p in house(message="violates WCAG 2.4.1"))),
            ("a house rule that claims a standard in its proposal is refused", any("claims a standard" in p for p in house(proposal="this is non-compliant"))),
            ("a house rule that claims a standard in its evidence is refused", any("claims a standard" in p for p in house(evidence={"kind": "measured", "ref": "WCAG 2.4.1 failure, Level A"}))),
            ("'Success Criterion' in a house rule's text is refused", any("claims a standard" in p for p in house(message="fails Success Criterion 2.4.1"))),
            ("'EN 301 549' in a house rule's text is refused", any("claims a standard" in p for p in house(message="breaks EN 301 549"))),
            ("'ADA' in a house rule's text is refused", any("claims a standard" in p for p in house(message="an ADA problem"))),
            ("'Section 508' in a house rule's text is refused", any("claims a standard" in p for p in house(message="Section 508 requires it"))),
            ("'ARIA spec' in a house rule's text is refused", any("claims a standard" in p for p in house(message="the ARIA spec says so"))),
            ("'a11y requirement' in a house rule's text is refused", any("claims a standard" in p for p in house(message="an a11y requirement"))),
            ("'Level AA' in a house rule's text is refused", any("claims a standard" in p for p in house(message="Level AA"))),
            ("a screen that carries a sentence is refused", any("no spaces" in p for p in problems(doc(screen="/ WCAG 2.4.1 Level A failure")))),
            ("a screen that is not a path or URL is refused, whatever the rule", any("no spaces" in p for p in problems(doc(screen="orders page")))),
            ("a screen that hides a claim behind separators is refused on a house rule", any("claims a standard" in p for p in house(screen="/WCAG-2.4.1-Level-A"))),
            ("a screen that joins the claim with underscores is refused on a house rule", any("claims a standard" in p for p in house(screen="/fail_WCAG_2.4.1"))),
            ("a plain route named /standards passes on a house rule (prose words are not read in a screen)", house(screen="/standards/list") == []),
            ("the document's title claiming a standard beside a house finding is refused", any("title or unverified" in p for p in problems({**doc(rule="A2"), "audit": "WCAG 2.4.1 failure on A2"}))),
            ("a title naming WCAG is fine when only standard findings sit beside it", problems({**base, "audit": "WCAG audit"}) == []),
            ("an unverified entry that carries a sentence is refused", any("no spaces" in p for p in problems({**base, "unverified": ["/x violates WCAG"]}))),
            ("an unverified entry claiming a standard beside a house finding is refused", any("title or unverified" in p for p in problems({**doc(rule="A2"), "unverified": ["/WCAG-2.4.1-failure"]}))),
            ("an unknown document key is refused", any("unknown document key" in p for p in problems({**base, "note": "WCAG"}))),
            ("a claim nested inside a list in evidence.ref is refused", any("claims a standard" in p for p in house(evidence={"kind": "measured", "ref": ["WCAG 2.4.1 failure"]}))),
            ("plain prose about a house rule passes", house(message="the first focusable element is not a skip link") == []),
            ("a standard rule may say WCAG", problems(doc(rule="A1", message="WCAG says one main")) == []),
            ("a document that audited no rule is refused", any("audited no rule" in p for p in problems({**base, "audited": {}}))),
            ("an audited screen count of zero is refused", any("above zero" in p for p in problems({**base, "audited": {"A1": 0}}))),
            ("a boolean is not a screen count", any("above zero" in p for p in problems({**base, "audited": {"A1": True}}))),
            ("an audited rule that is not in the table is refused", any("not in the framework" in p for p in problems({**base, "audited": {"A1": 1, "A77": 1}}))),
            ("a document that is not a findings list is unusable", _raises(lambda: validate({"findings": 3}, registry, root))),
        ]
        d1 = {"audit": "t", "audited": {"A1": 3, "A2": 3}, "findings": [
            {"rule": "A2", "screen": "/a", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A2", "screen": "/b", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A2", "screen": "/c", "instances": 9, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A1", "screen": "/a", "instances": 1, "evidence": {"kind": "measured", "ref": "m"}},
            {"rule": "A1", "screen": "/b", "instances": 1, "evidence": {"kind": "measured", "ref": "m"}}]}
        ranked = decorate(d1, registry)
        rep = report_md(d1, registry)
        clean = report_md({"audit": "t", "audited": {"A1": 3}, "findings": []}, registry)
        cases += [
            ("a standard outranks a house rule whatever its reach and instance count", ranked[0]["rule"] == "A1" and ranked[-1]["rule"] == "A2"),
            ("authority is derived from the registry", ranked[0]["authority"] == "standard" and ranked[-1]["authority"] == "house"),
            ("reach counts distinct screens", ranked[0]["reach"] == 2 and ranked[-1]["reach"] == 3),
            ("ranks are 1..n", [d["rank"] for d in ranked] == [1, 2, 3, 4, 5]),
            ("the report labels a house rule as one", "house rule (decision: D7)" in rep),
            ("the report labels a standard with its source", "standard: HTML spec" in rep),
            ("the report prints a Not audited section", "## Not audited" in rep),
            ("Not audited names a rule this run did not cover, with its blocker", "A21" in rep and "#2228" in rep),
            ("Not audited does not list a rule the run audited", not {"A1", "A2"} & {r for ln in rep.partition("## Not audited")[2].splitlines()
                                                                                  if ln.startswith("- A") for r in ln[2:].split(":")[0].split(", ")}),
            ("Not audited names the judgement rules and #2225", "#2225" in rep),
            ("a rule enforced by a script says to run it separately", "scripts/t.py" in rep),
            ("a clean report names the rules it measured", "No findings against the rules audited (A1)" in clean),
            ("a clean report still prints Not audited", "## Not audited" in clean),
            ("the report says how many screens each rule covered", "A1 (3 screens)" in rep),
            ("unverified screens are printed and not counted clean", "Unverified" in report_md({**d1, "unverified": ["/x"]}, registry)),
        ]
        m = merge([{"audit": "a", "audited": {"A23": 2}, "unverified": ["/u"], "findings": [1, 2]},
                   {"audit": "b", "audited": {"A24": 5, "A23": 1}, "unverified": ["/u", "/v"], "findings": [3]}])
        cases += [
            ("a merge keeps every finding", m["findings"] == [1, 2, 3]),
            ("a merge keeps each rule's own screen count, not one overall number", m["audited"] == {"A23": 2, "A24": 5}),
            ("a merge unions the unverified screens", m["unverified"] == ["/u", "/v"]),
            ("a merge of nothing is unusable", _raises(lambda: merge([]))),
        ]
        fj = from_judge("layout_fit", {"findings": [{"rule": "clipped", "ref": "x", "detail": "hidden", "count": 4, "examples": ["/p", "/q"]}],
                                       "unverified": ["/u"], "redirected": ["/r"]}, 5)
        cases += [
            ("a judge's finding maps to its framework rule", fj["findings"][0]["rule"] == "A23" and fj["audited"] == {"A23": 5}),
            ("each example route becomes its own finding, so reach is the routes listed", [f["screen"] for f in fj["findings"]] == ["/p", "/q"]),
            ("the judge's own count is kept in the message", "counts 4 route(s)" in fj["findings"][0]["message"]),
            ("a judge's unverified and redirected routes are carried, never clean", fj["unverified"] == ["/u", "/r"]),
            ("an unknown judge is unusable", _raises(lambda: from_judge("nope", [], 1))),
            ("a judge finding that is not an object is unusable, not a crash", _raises(lambda: from_judge("layout_fit", {"findings": ["x"]}, 1))),
            ("a theme_parity list maps to A25", from_judge("theme_parity", [{"ref": "/r", "rule": "r", "detail": "d"}], 2)["findings"][0]["rule"] == "A25"),
        ]
        # A forged registry is refused whole, and the CLI has no way to point at one.
        forged = Path(td) / "forged.json"
        forged.write_text(json.dumps({"rules": [{"id": "A2", "authority": "standard", "basis": "decision", "ref": "D7",
                                                 "source": "WCAG 2.4.1", "rule": "skip link"}]}))
        cases.append(("a registry whose authority disagrees with its basis is refused", _raises(lambda: load_registry(forged))))
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # argparse prints its refusal; the test wants only the exit
                main(["check", str(forged), "--registry", str(forged)])
            cli_has_registry_option = True
        except SystemExit:
            cli_has_registry_option = False
        cases.append(("the CLI offers no --registry option", not cli_has_registry_option))
    real = load_registry()
    cases.append(("the real registry loads and holds rules", len(real) > 0))
    cases.append(("every judge maps to a rule that exists", all(r in real for r in JUDGE_RULES.values())))
    cases.append(("every blocker names a rule that exists", all(r in real for r in BLOCKED)))
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
            registry = load_registry()
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
                print(f"{len(doc['findings'])} finding(s) over {len(doc['audited'])} audited rule(s): all well-formed")
            return 0
        ap.print_help()
        return 2
    except (Unusable, OSError, ValueError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
