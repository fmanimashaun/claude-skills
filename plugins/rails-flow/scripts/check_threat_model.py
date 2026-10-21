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
`Threats` holds one table, columns `ID | Threat | STRIDE | Component | Decision | Reason`; ID is `TM-n`, unique, and is what a `[security]` criterion cites (#2118). STRIDE is S, T, R, I, D or E (a word starting with
one of those counts: `Spoofing`, `Tampering`...). Decision is exactly one of mitigate, transfer, accept, eliminate. Reason may not be
empty for `accept` (the one decision that leaves the risk in place); it is expected for the rest and a model that leaves it blank on
`mitigate` gets no finding, because the control is named in Security requirements.

HOLLOW IS REFUSED (review of #2131). The unedited template, an empty section, `TBD`/`TODO`/`n/a` as content and an `accept` with a stock reason are all
the boilerplate D1 exists to prevent, and the first thing a user does is copy the template. So: every section needs body text, `Trust boundaries` and
`Security requirements` each need a `-` bullet, any `<placeholder>` left outside backticks is a finding, and a Threat, Component, bullet or Reason that is
only a filler word is a finding.

LIMITS. A row that says `mitigate` and does nothing passes, and so does a sentence that is long and says nothing. The check reads the document, not the code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SECTIONS = ("What we are building", "Trust boundaries", "Threats", "Security requirements")
DECISIONS = ("mitigate", "transfer", "accept", "eliminate")
STRIDE = "STRIDE"
ID_RE = re.compile(r"TM-\d+", re.I)
FILLERS = {"tbd", "tba", "todo", "fixme", "n/a", "na", "none", "nil", "-", "--", "x", "xx", "?", "??", "...", "…", "etc", "later", "see above"}
PLACEHOLDER = re.compile(r"<[^<>\n`]{1,80}>")
BULLET_SECTIONS = ("Trust boundaries", "Security requirements")


CELL_PLACEHOLDER = re.compile(r"<(?!%)[^<>`\n]{1,120}>")
_FILLER_WORDS = {w for f in FILLERS for w in re.sub(r"[^\w\s]", " ", f).split()} | {
    "fill", "in", "yet", "wip", "to", "be", "decided", "determined", "pending", "placeholder", "here", "out", "up", "the", "a"}


def _is_filler(cell: str) -> bool:
    """Fewer than two letters, or every word a filler or a stop word (`TBD!`, `TODO: fill in`, `none yet`; #2117 adversary)."""
    if len(re.findall(r"[^\W\d_]", cell)) < 2:
        return True
    return all(w in _FILLER_WORDS for w in re.sub(r"[^\w\s]", " ", cell).lower().split())


def _uncommented(text: str) -> str:
    """Comments removed; an unclosed `<!--` runs to the end of the file, as it does when rendered."""
    return re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.S)


def _section_body(text: str, name: str) -> str | None:
    m = re.search(rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def threat_rows(text: str) -> list[tuple[int, str, str]]:
    """(TM number, threat, decision) per row of `## Threats`, the number read from the row's own ID cell (#2118). Empty when the table cannot be read."""
    m = re.search(r"^##\s+Threats\s*$(.*?)(?=^##\s|\Z)", _uncommented(text), re.M | re.S)
    lines = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("|")] if m else []
    if not lines or [h.lower() for h in _cells(lines[0])[:6]] != ["id", "threat", "stride", "component", "decision", "reason"]:
        return []
    out: list[tuple[int, str, str]] = []
    for ln in lines[1:]:
        cells = _cells(ln) + [""] * 6
        if all(set(c) <= set("-: ") for c in cells[:6]):
            continue
        if ID_RE.fullmatch(cells[0]):
            out.append((int(cells[0][3:]), cells[1], cells[4].lower()))
    return out


def check(text: str) -> tuple[list[str], int]:
    """(findings, threat rows read). Zero rows read means the model is unusable, not clean."""
    findings: list[str] = []
    heads = {m.group(1).strip().lower() for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}
    for s in SECTIONS:
        if s.lower() not in heads:
            findings.append(f"missing section `## {s}`")
    prose = re.sub(r"`[^`\n]*`", "", _uncommented(text))
    for ph in sorted({m_.group(0) for m_ in PLACEHOLDER.finditer(prose)}):
        findings.append(f"template placeholder `{ph}` left in the model")
    for s in SECTIONS:
        body = _section_body(text, s)
        if body is None:
            continue
        lines = [ln.strip() for ln in _uncommented(body).splitlines() if ln.strip()]
        if s != "Threats" and not [ln for ln in lines if not _is_filler(ln.lstrip("-* "))]:
            findings.append(f"section `## {s}` is empty or only a filler word")
        if s in BULLET_SECTIONS:
            bullets = [ln.lstrip("-* ").strip() for ln in lines if ln[:1] in "-*" and len(ln) > 1]
            if not [b for b in bullets if not _is_filler(b)]:
                findings.append(f"section `## {s}` needs at least one `-` bullet with content")
    m = re.search(r"^##\s+Threats\s*$(.*?)(?=^##\s|\Z)", _uncommented(text), re.M | re.S)
    rows = 0
    if m:
        lines = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("|")]
        header = _cells(lines[0]) if lines else []
        want = ["id", "threat", "stride", "component", "decision", "reason"]
        if [h.lower() for h in header[:6]] != want:
            findings.append("`## Threats` table needs the columns ID | Threat | STRIDE | Component | Decision | Reason")
        else:
            ids: set[str] = set()
            for ln in lines[1:]:
                cells = _cells(ln)
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                rows += 1
                cells += [""] * (6 - len(cells))
                rid, threat, stride, component, decision, reason = cells[:6]
                label = f"threat row `{threat[:50] or '(blank)'}`"
                for ph in sorted({p_.group(0) for c in cells[:6] for p_ in CELL_PLACEHOLDER.finditer(c.replace("`", ""))}):
                    findings.append(f"{label}: template placeholder `{ph}` left in a cell")
                if not ID_RE.fullmatch(rid):
                    findings.append(f"{label}: the ID must look like TM-1, got `{rid}`")
                elif rid.upper() in ids:
                    findings.append(f"{label}: the ID {rid} is already used by another row")
                else:
                    ids.add(rid.upper())
                if not threat or _is_filler(threat):
                    findings.append(f"{label}: no threat named")
                if not component or _is_filler(component):
                    findings.append(f"{label}: no component named")
                if reason and _is_filler(reason):
                    findings.append(f"{label}: the reason is only a filler word")
                if not stride or stride[0].upper() not in STRIDE:
                    findings.append(f"{label}: STRIDE must be S, T, R, I, D or E, got `{stride}`")
                if decision.lower() not in DECISIONS:
                    findings.append(f"{label}: decision must be one of {', '.join(DECISIONS)}, got `{decision}`")
                elif decision.lower() == "accept" and (not reason or _is_filler(reason)):
                    findings.append(f"{label}: an `accept` needs a reason")
    return findings, rows


def selftest() -> int:
    ok = """# T
## What we are building
A webhook.
## Trust boundaries
- Zoho -> app: the callback body
## Threats
| ID | Threat | STRIDE | Component | Decision | Reason |
|---|---|---|---|---|---|
| TM-1 | Forged callback | Spoofing | webhook | mitigate | signature checked |
| TM-4 | Replay | R | webhook | accept | idempotent, harmless |
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
        ("the unedited shipped template is refused", Path(__file__).resolve().parent.parent.joinpath("templates", "threat-model.md").read_text(encoding="utf-8") if Path(__file__).resolve().parent.parent.joinpath("templates", "threat-model.md").exists() else ok.replace("A webhook.", "<what we build>"), 1, "template placeholder"),
        ("a placeholder left in a filled model is found", ok.replace("A webhook.", "A webhook for <feature>."), 1, "template placeholder"),
        ("a placeholder inside backticks is prose, not a placeholder", ok.replace("A webhook.", "A webhook reading `<body>`."), 0, ""),
        ("an empty section is found", ok.replace("A webhook.\n", ""), 1, "is empty or only a filler word"),
        ("a section of TBD is found", ok.replace("A webhook.", "TBD"), 1, "is empty or only a filler word"),
        ("a boundaries section with no bullet is found", ok.replace("- Zoho -> app: the callback body", "Zoho to app."), 1, "needs at least one `-` bullet"),
        ("a requirements section with no bullet is found", ok.replace("- verify the signature", "verify the signature"), 1, "needs at least one `-` bullet"),
        ("a filler threat is found", ok.replace("| Forged callback |", "| TBD |"), 1, "no threat named"),
        ("a filler component is found", ok.replace("| webhook | mitigate |", "| n/a | mitigate |"), 1, "no component named"),
        ("an accept whose reason is a filler is found", ok.replace("| accept | idempotent, harmless |", "| accept | TBD |"), 1, "an `accept` needs a reason"),
        ("a filler reason on a mitigate is found", ok.replace("signature checked", "todo"), 1, "only a filler word"),
        ("a punctuated filler is found", ok.replace("signature checked", "TBD!"), 1, "only a filler word"),
        ("a reason with no letter is found", ok.replace("| accept | idempotent, harmless |", "| accept | 42 |"), 1, "an `accept` needs a reason"),
        ("a backticked placeholder in a threat cell is found", ok.replace("| Forged callback |", "| `<threat>` |"), 1, "left in a cell"),
        ("backticked code in a cell is not a placeholder", ok.replace("signature checked", "`<%= h(x) %>` escapes"), 0, ""),
        ("a commented-out table is no rows", ok.replace("| ID |", "<!--\n| ID |").replace("| idempotent, harmless |\n", "| idempotent, harmless |\n-->\n"), 2, ""),
        ("a stop-word filler is found", ok.replace("signature checked", "TODO: fill in"), 1, "only a filler word"),
        ("a filler with a stop word is found", ok.replace("| accept | idempotent, harmless |", "| accept | none yet |"), 1, "an `accept` needs a reason"),
        ("one letter is filler", ok.replace("| webhook | mitigate |", "| q1 | mitigate |"), 1, "no component named"),
        ("the template's own placeholder in a cell is found", ok.replace("signature checked", "<control, or why the risk stays>"), 1, "left in a cell"),
        ("an unclosed comment hides the rest", ok.replace("## Threats", "<!-- draft\n## Threats"), 2, ""),
        ("a table with no rows is unusable, not clean", ok.split("|---|---|---|---|---|")[0] + "|---|---|---|---|---|---|\n## Security requirements\n- x\n", 2, ""),
    ]
    bad = 0
    for name, text, want, needle in cases:
        findings, rows = check(text)
        got = 2 if rows == 0 else (1 if findings else 0)
        if got != want or (needle and not any(needle in f for f in findings)):
            bad += 1
            print(f"FAIL {name}: expected exit {want} naming `{needle}`, got {got} {findings}")
    # main() reads a FILE: an unusable one is exit 2, a finding is exit 1, a clean one is exit 0.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        good, broken, empty = Path(d, "good.md"), Path(d, "broken.md"), Path(d, "empty.md")
        good.write_text(ok)
        broken.write_text(ok.replace("| mitigate |", "|  |"))
        empty.write_text("# nothing here\n")
        for name, argv, want in (("a clean file is exit 0", [str(good)], 0), ("a file with a finding is exit 1", [str(broken)], 1),
                                 ("a file with no threat rows is exit 2", [str(empty)], 2), ("a missing file is exit 2", [str(Path(d, "no.md"))], 2)):
            got = main(argv)
            if got != want:
                bad += 1
                print(f"FAIL {name}: expected exit {want}, got {got}")
    got_rows = threat_rows(ok)
    if got_rows != [(1, "Forged callback", "mitigate"), (4, "Replay", "accept")]:
        bad += 1
        print(f"FAIL threat_rows reads each row's own ID, not its position: got {got_rows}")
    for name, body, needle in (("a row without an ID is found", ok.replace("| TM-4 |", "|  |"), "the ID must look like TM-1"),
                               ("a repeated ID is found", ok.replace("| TM-4 |", "| TM-1 |"), "already used")):
        findings, _ = check(body)
        if not any(needle in f for f in findings):
            bad += 1
            print(f"FAIL {name}: {findings}")
    if bad == 0:
        print(f"check_threat_model selftest: {len(cases)} cases and the exit codes pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
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
