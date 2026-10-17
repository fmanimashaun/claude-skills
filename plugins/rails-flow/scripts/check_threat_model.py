#!/usr/bin/env python3
"""Check a threat model written by /rails-flow:secure-design is COMPLETE, not that it is right (#2117).

Run:  check_threat_model.py docs/security/threat-models/<slug>.md [...]
      check_threat_model.py --selftest
Exit: 0 every file is well formed
      1 a finding: a missing section, a threat row without a valid decision, or an `accept` without a reason
      2 unusable: no file, unreadable, or no threats table to read (an empty model is not a clean one)

WHY (#2117, decisions D1-D2 on #2115). The step exists so each decision is written down and revisited. A model whose rows carry no
decision, or accept a risk with no reason, is the boilerplate D1 was written to avoid. This is the part of "is it done" a script can
answer; whether the threats are the RIGHT ones is for `security-auditor` and a human.

THE SHAPE (templates/threat-model.md): four `##` sections, `What we are building`, `Trust boundaries`, `Threats`, `Security requirements`.
`Threats` holds one table, columns `Threat | STRIDE | Component | Decision | Reason`. STRIDE is S, T, R, I, D or E (a word starting with
one of those counts: `Spoofing`, `Tampering`...). Decision is exactly one of mitigate, transfer, accept, eliminate. Reason may not be
empty for `accept` (the one decision that leaves the risk in place); it is expected for the rest and a model that leaves it blank on
`mitigate` gets no finding, because the control is named in Security requirements.

LIMITS. A row that says `mitigate` and does nothing passes. The check reads the document, not the code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SECTIONS = ("What we are building", "Trust boundaries", "Threats", "Security requirements")
DECISIONS = ("mitigate", "transfer", "accept", "eliminate")
STRIDE = "STRIDE"


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check(text: str) -> tuple[list[str], int]:
    """(findings, threat rows read). Zero rows read means the model is unusable, not clean."""
    findings: list[str] = []
    heads = {m.group(1).strip().lower() for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}
    for s in SECTIONS:
        if s.lower() not in heads:
            findings.append(f"missing section `## {s}`")
    m = re.search(r"^##\s+Threats\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    rows = 0
    if m:
        lines = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("|")]
        header = _cells(lines[0]) if lines else []
        want = ["threat", "stride", "component", "decision", "reason"]
        if [h.lower() for h in header[:5]] != want:
            findings.append("`## Threats` table needs the columns Threat | STRIDE | Component | Decision | Reason")
        else:
            for ln in lines[1:]:
                cells = _cells(ln)
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                rows += 1
                cells += [""] * (5 - len(cells))
                threat, stride, _component, decision, reason = cells[:5]
                label = f"threat row `{threat[:50] or '(blank)'}`"
                if not threat:
                    findings.append(f"{label}: no threat named")
                if not stride or stride[0].upper() not in STRIDE:
                    findings.append(f"{label}: STRIDE must be S, T, R, I, D or E, got `{stride}`")
                if decision.lower() not in DECISIONS:
                    findings.append(f"{label}: decision must be one of {', '.join(DECISIONS)}, got `{decision}`")
                elif decision.lower() == "accept" and not reason:
                    findings.append(f"{label}: an `accept` needs a reason")
    return findings, rows


def selftest() -> int:
    ok = """# T
## What we are building
A webhook.
## Trust boundaries
Zoho -> app.
## Threats
| Threat | STRIDE | Component | Decision | Reason |
|---|---|---|---|---|
| Forged callback | Spoofing | webhook | mitigate | signature checked |
| Replay | R | webhook | accept | idempotent, harmless |
## Security requirements
- verify the signature
"""
    cases: list[tuple[str, str, int, str]] = [
        ("a complete model passes", ok, 0, ""),
        ("a missing section is found", ok.replace("## Security requirements", "## Notes"), 1, "missing section `## Security requirements`"),
        ("a row without a decision is found", ok.replace("| mitigate |", "|  |"), 1, "decision must be one of"),
        ("an unknown decision is found", ok.replace("| mitigate |", "| ignore |"), 1, "decision must be one of"),
        ("an accept without a reason is found", ok.replace("| accept | idempotent, harmless |", "| accept |  |"), 1, "an `accept` needs a reason"),
        ("a bad STRIDE letter is found", ok.replace("| Spoofing |", "| X |"), 1, "STRIDE must be"),
        ("wrong columns are unusable, not clean", ok.replace("| Reason |", "| Why |"), 2, "needs the columns"),
        ("a table with no rows is unusable, not clean", ok.split("|---|---|---|---|---|")[0] + "|---|---|---|---|---|\n## Security requirements\n- x\n", 2, ""),
    ]
    bad = 0
    for name, text, want, needle in cases:
        findings, rows = check(text)
        got = 2 if rows == 0 else (1 if findings else 0)
        if got != want or (needle and not any(needle in f for f in findings)):
            bad += 1
            print(f"FAIL {name}: expected exit {want} naming `{needle}`, got {got} {findings}")
    if bad == 0:
        print(f"check_threat_model selftest: {len(cases)} cases pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if not argv:
        print("usage: check_threat_model.py FILE [FILE...]", file=sys.stderr)
        return 2
    worst = 0
    for name in argv:
        try:
            text = Path(name).read_text(encoding="utf-8")
        except OSError as e:
            print(f"UNUSABLE {name}: {e}", file=sys.stderr)
            worst = max(worst, 2)
            continue
        findings, rows = check(text)
        if rows == 0:
            print(f"UNUSABLE {name}: no threat rows read" + (f" ({'; '.join(findings)})" if findings else ""), file=sys.stderr)
            worst = max(worst, 2)
        elif findings:
            for f in findings:
                print(f"{name}: {f}")
            worst = max(worst, 1) if worst != 2 else 2
        else:
            print(f"{name}: ok, {rows} threat row(s)")
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
