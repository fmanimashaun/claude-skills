#!/usr/bin/env python3
"""Measure a user journey as a FLOW, against a budget the journey itself declares. (#2250, slice 2 of #2221)

Run:  python3 flow_report.py docs/evidence/qa/<date>-walkthrough/flow.json --root .
      python3 flow_report.py flow.json --root . --json
      python3 flow_report.py --schema      # what `journey-walker` must emit
      python3 flow_report.py --selftest

WHY. `journey-walker` already records pages, hand-offs and notifications, and judges each page against the spec. Nothing measures a journey as a
flow: how many actions it takes, how many times the person is moved to another part of the product, how long they wait, where they are left
with nothing to do, where they go back, what they type twice, and where a permission wall appears after they have already put in the work. Those
are bottlenecks, and each is a number a script can state, so each is measured here and not left to a reviewer's impression.

BROWSER MEASURES, PYTHON JUDGES (the split `layout_fit.py` uses). `journey-walker` drives the app and writes `flow.json`, one row per action. This
file reads it and judges it, so it runs anywhere, with no browser.

THE SEVEN MEASUREMENTS. Each is a number in the report; the ones with a finding condition say so.
  steps              the actions to complete the journey. A finding when it exceeds the declared budget, or when the journey never completed.
  context switches   a change of top-level navigation section, or a modal or tab opened. A finding only when the budget declares `switches`.
  waits              the time from an action to the page settling, and whether a spinner showed. A finding for each over the declared `wait`.
  dead ends          a page that is not the journey's declared end and offers no forward action. A finding for each.
  back-tracks        a landing on a URL the journey already visited (a landing the app caused, a redirect or a reload, is not one). A finding for each.
  forms re-entered   a form (its URL and field names) submitted again after it came back. A finding for each.
  late walls         a permission wall at step 2 or later: the person has already spent the steps before it. A finding for each.

THRESHOLDS ARE DECLARATIONS, NEVER DEFAULTS. A journey's own document says `Budget: steps=8 wait=3s` (and optionally `switches=3`) inside the
journey's section, and this refuses a journey with no budget (exit 2): a made-up limit would be reported as if the product had broken a rule it never
had. Where a limit comes from a source, it belongs in the project's budget with its citation, not here.

THE LATE WALL IS DEFINED BY WHAT A BROWSER CAN SEE. The plan said "a wall at step k when the first step already needed the permission", which a
browser cannot observe. What it can observe is that the wall came at step k >= 2, after k-1 steps were spent: that is measured, and the finding says
how many were wasted. A wall at step 1 is not late; it is the cheapest place for one.

RANKED, DETERMINISTICALLY. Findings are ordered by class (late wall, dead end, steps over budget, form re-entered, back-track, wait over budget,
switches over budget), then by how much, then by step; the script computes it and the agent does not. Every finding names the step that causes it.

`rule` IS NULL, ON PURPOSE. A finding cites a framework rule id (#2220) where one applies; none of the seven measurements is the violation of any of
the framework's 60 rules (checked: the closest, A18, is about what a denied page SAYS, which a flow row does not carry). The field exists so a later
mapping lands without a schema change; it is never filled by guesswork.

Exit codes:  0 clean · 1 a finding, or a wait that was not measured · 2 unusable (a document that is malformed, or a journey with no budget)

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "qa-flow/flow/1"
# A step is something the PERSON does. What the app does next (a redirect after a submit, a reload) is recorded on the row of the action that caused it, in
# `then`, and is never a row of its own: otherwise a submit that redirects counts as two steps, and a journey is over its budget by the app's own plumbing.
ACTIONS = frozenset({"navigate", "click", "submit", "back", "modal-open", "tab-open"})
THEN = (None, "redirect", "reload")
SWITCHES = frozenset({"modal-open", "tab-open"})
# Class order of a ranked report: the walls and dead ends stop a person; the rest slow them.
RANK = ("late-wall", "dead-end", "steps-over-budget", "journey-incomplete", "form-re-entered", "back-track", "wait-over-budget", "switches-over-budget")

SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "journeys": [{
        "journey": "applicant submits a request",
        "persona": "applicant",
        "document": "docs/roles/applicant.md",
        "heading": "Submit a request",
        "complete": True,
        "rows": [
            {"step": 1, "url": "/requests", "action": "navigate", "section": "requests", "settled_ms": 380, "spinner": False, "status": 200,
             "forward_actions": 3, "terminal": False, "denied": False, "form": None, "then": None},
            {"step": 2, "url": "/requests/new", "action": "click", "section": "requests", "settled_ms": 410, "spinner": False, "status": 200,
             "forward_actions": 1, "terminal": False, "denied": False,
             "form": {"url": "/requests/new", "fields": ["title", "details"], "outcome": "advanced"}, "then": None},
            {"step": 3, "url": "/requests/42", "action": "submit", "section": "requests", "settled_ms": 1900, "spinner": True, "status": 200,
             "forward_actions": 0, "terminal": True, "denied": False, "form": None, "then": "redirect"},
        ],
    }],
}


class Unusable(RuntimeError):
    """The document cannot be judged -- reported, never treated as a clean run."""


@dataclass
class Finding:
    measurement: str
    journey: str
    step: int | None
    url: str | None
    detail: str
    evidence: dict
    rule: str | None = None        # a #2220 rule id where one applies; none of the seven does (see the module docstring)


@dataclass
class Budget:
    steps: int
    wait_ms: int
    switches: int | None = None


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# Reading the budget a journey declares
# ---------------------------------------------------------------------------------------------

_BUDGET_LINE = re.compile(r"^\s*(?:[-*>]\s*)?\**\s*budget\s*:?\s*\**\s*:?\s*(.*)$", re.I)
_NUMBER = r"[0-9]+(?:\.[0-9]+)?"
# A number is digits, optionally a point and more digits: `.` alone, `3.` and `.5` are not numbers. The unit is attached to it (`4 steps` is not `4 s`).
_PAIR = re.compile(rf"([a-z]+)\s*=\s*({_NUMBER})(ms|s)?(?![a-z0-9.])", re.I)
_HEADING = re.compile(r"^(#+)\s+(.*?)\s*#*\s*$")


def _headings(lines: list[str], heading: str) -> list[int]:
    return [i for i, line in enumerate(lines) if (m := _HEADING.match(line)) and m.group(2) == heading]


def _section(text: str, heading: str) -> list[str] | None:
    """The lines under `heading` (an exact heading line) up to the next heading of the same or a higher level; None when no such heading."""
    lines = text.splitlines()
    found = _headings(lines, heading)
    if not found:
        return None
    level = len(_HEADING.match(lines[found[0]]).group(1))
    out = []
    for nxt in lines[found[0] + 1:]:
        n = re.match(r"^(#+)\s", nxt)
        if n and len(n.group(1)) <= level:
            break
        out.append(nxt)
    return out


def parse_budget(text: str, heading: str) -> tuple[Budget | None, str | None]:
    """`(budget, None)` or `(None, why)`. `Budget: steps=8 wait=3s [switches=3]` inside the journey's section, exactly one, nothing undeclared."""
    from decimal import Decimal

    count = len(_headings(text.splitlines(), heading))
    if count > 1:
        return None, f"has its heading `{heading}` {count} times in the journey document: a journey heading is unique, or the second one's budget is never read"
    section = _section(text, heading)
    if section is None:
        return None, f"no heading `{heading}` in the journey document, so the journey is declared nowhere"
    lines = [m for m in (_BUDGET_LINE.match(line) for line in section) if m and "=" in m.group(1)]
    marked = [line for line in section if re.match(r"^\s*(?:[-*>]\s*)?\**\s*budget\b", line, re.I)]
    if not marked:
        return None, "declares no `Budget:` line (steps and wait): a journey with no declared limit is not judged against an invented one"
    if len(marked) > 1:
        return None, f"declares {len(marked)} `Budget:` lines: one journey, one budget"
    if not lines:
        return None, f"`{marked[0].strip()}` has no `steps=` and `wait=` values"
    rest = lines[0].group(1)
    leftover = _PAIR.sub(" ", rest).strip(" ,;\t")
    if leftover:
        return None, f"its `Budget:` line has text this budget does not understand: `{leftover}` (limits are `steps=8`, `wait=3s`, `switches=3`)"
    seen: dict[str, int] = {}
    for key, value, unit in _PAIR.findall(rest):
        key = key.lower()
        if key in seen:
            return None, f"declares `{key}` twice in its budget"
        if key == "wait":
            if not unit:
                return None, "`wait=` needs a unit, `s` or `ms` (for example `wait=3s`)"
            ms = Decimal(value) * (1 if unit.lower() == "ms" else 1000)
            if ms != ms.to_integral_value():
                return None, f"`wait={value}{unit}` is not a whole number of milliseconds ({ms} ms)"
            if ms < 1:
                return None, f"`wait={value}{unit}` is less than 1 ms, which is not a budget"
            seen[key] = int(ms)
        elif key in ("steps", "switches"):
            if unit or "." in value:
                return None, f"`{key}` must be a whole number, got `{value}{unit or ''}`"
            seen[key] = int(value)
        else:
            return None, f"declares `{key}`, which is not a budget limit (steps, wait, switches)"
    if "steps" not in seen or "wait" not in seen:
        return None, "its budget needs both `steps=` and `wait=` (for example `Budget: steps=8 wait=3s`)"
    if seen["steps"] < 1:
        return None, "a budget of zero steps is not a budget"
    return Budget(seen["steps"], seen["wait"], seen.get("switches")), None


# ---------------------------------------------------------------------------------------------
# Loading and validating the document
# ---------------------------------------------------------------------------------------------

def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def load(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unusable(f"{path} does not exist: `journey-walker` writes flow.json beside its other evidence")
    except json.JSONDecodeError as err:
        raise Unusable(f"{path} is not valid JSON ({err}): a truncated walk is not a clean walk")
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise Unusable(f"{path} does not declare schema {SCHEMA!r}: run `--schema` to see what `journey-walker` emits")
    if not isinstance(doc.get("journeys"), list) or not doc["journeys"]:
        raise Unusable(f"{path} has no journeys: nothing was measured, which is not a pass")
    return doc


def validate(doc: dict) -> list[str]:
    """Every way the document is malformed, named (a row that cannot be read is never skipped)."""
    problems: list[str] = []
    names: set[str] = set()
    for j, journey in enumerate(doc["journeys"]):
        where = f"journeys[{j}]"
        if not isinstance(journey, dict):
            problems.append(f"{where} is not an object")
            continue
        for key, kind in (("journey", str), ("persona", str), ("document", str), ("heading", str)):
            if not isinstance(journey.get(key), kind) or not journey[key].strip():
                problems.append(f"{where}.{key} must be a non-empty string")
        if not isinstance(journey.get("complete"), bool):
            problems.append(f"{where}.complete must be true or false")
        name = journey.get("journey") if isinstance(journey.get("journey"), str) else where
        if name in names:
            problems.append(f"{where}: the journey `{name}` appears twice")
        names.add(name)
        rows = journey.get("rows")
        if not isinstance(rows, list) or not rows:
            problems.append(f"{where}.rows must be a non-empty list: a journey with no actions was not walked")
            continue
        for i, row in enumerate(rows):
            at = f"{where}.rows[{i}]"
            if not isinstance(row, dict):
                problems.append(f"{at} is not an object")
                continue
            if row.get("step") != i + 1 or not _is_int(row.get("step")):
                problems.append(f"{at}.step must be {i + 1}: steps are the actions in order, with none missing")
            if not isinstance(row.get("url"), str) or not row["url"].strip():
                problems.append(f"{at}.url must be a non-empty string")
            if row.get("action") not in ACTIONS:
                hint = (": a redirect or a reload is recorded as `then` on the row of the action that caused it, never as a row of its own"
                        if row.get("action") in ("redirect", "reload") else "")
                problems.append(f"{at}.action must be one of {', '.join(sorted(ACTIONS))}, got {row.get('action')!r}{hint}")
            if "then" not in row or row["then"] not in THEN:
                problems.append(f"{at}.then must be null, \"redirect\" or \"reload\": what the app did after the action, never a step")
            sm = row.get("settled_ms")
            if sm is not None and (not _is_int(sm) or sm < 0):
                problems.append(f"{at}.settled_ms must be a whole number of milliseconds, or null when it was not measured")
            if not _is_int(row.get("status")):
                problems.append(f"{at}.status must be the HTTP status as a whole number")
            if not _is_int(row.get("forward_actions")) or row["forward_actions"] < 0:
                problems.append(f"{at}.forward_actions must be a whole number, 0 or more")
            for flag in ("spinner", "terminal", "denied"):
                if not isinstance(row.get(flag), bool):
                    problems.append(f"{at}.{flag} must be true or false")
            if row.get("section") is not None and not isinstance(row.get("section"), str):
                problems.append(f"{at}.section must be a string, or null")
            form = row.get("form")
            if form is not None:
                if not (isinstance(form, dict) and isinstance(form.get("url"), str) and isinstance(form.get("fields"), list)
                        and form["fields"] and all(isinstance(f, str) and f for f in form["fields"])
                        and form.get("outcome") in ("advanced", "returned")):
                    problems.append(f"{at}.form must be null, or {{url, fields (non-empty names), outcome: advanced|returned}}")
        if isinstance(rows[-1], dict) and journey.get("complete") is True and rows[-1].get("terminal") is not True:
            problems.append(f"{where}: marked complete but its last row is not the declared end (terminal)")
    return problems


# ---------------------------------------------------------------------------------------------
# The seven measurements
# ---------------------------------------------------------------------------------------------

def _norm(url: str) -> str:
    """A URL as the journey compares it: no fragment, a trailing slash ignored, the query kept (a different query is a different page)."""
    url = url.split("#", 1)[0]
    path, _, query = url.partition("?")
    path = path.rstrip("/") or "/"
    return path + ("?" + query if query else "")


def _signature(form: dict) -> tuple[str, tuple[str, ...]]:
    return (_norm(form["url"]).split("?", 1)[0], tuple(sorted(form["fields"])))


def judge_journey(journey: dict, budget: Budget) -> tuple[list[Finding], dict, list[str]]:
    rows = journey["rows"]
    name = journey["journey"]
    findings: list[Finding] = []
    unverified: list[str] = []

    def add(measurement: str, row: dict | None, detail: str, **evidence) -> None:
        findings.append(Finding(measurement, name, row["step"] if row else None, row["url"] if row else None, detail, evidence))

    # 1. steps
    steps = len(rows)
    if not journey["complete"]:
        add("journey-incomplete", rows[-1], f"the journey never reached its declared end: {steps} step(s) were taken and the last page is not the end",
            steps=steps)
    elif steps > budget.steps:
        add("steps-over-budget", rows[-1], f"{steps} steps to complete, budget {budget.steps} ({steps - budget.steps} over)", steps=steps,
            budget=budget.steps, over=steps - budget.steps)

    # 2. context switches
    switches = 0
    previous = None
    switch_steps: list[int] = []
    for row in rows:
        moved = row.get("section") is not None and previous is not None and row["section"] != previous
        if moved or row["action"] in SWITCHES:
            switches += 1
            switch_steps.append(row["step"])
        if row.get("section") is not None:
            previous = row["section"]
    limit = budget.switches
    if limit is not None and switches > limit:
        add("switches-over-budget", next(r for r in rows if r["step"] == switch_steps[limit]),
            f"{switches} context switches, budget {limit} ({switches - limit} over): at steps {switch_steps}",
            switches=switches, budget=limit, steps=switch_steps)

    # 3. waits
    longest = 0
    spinner_seen = False
    for row in rows:
        ms = row["settled_ms"]
        spinner_seen = spinner_seen or row["spinner"]
        if ms is None:
            unverified.append(f"{name}: step {row['step']} ({row['url']}): settled time not measured")
            continue
        longest = max(longest, ms)
        if ms > budget.wait_ms:
            add("wait-over-budget", row, f"{ms} ms to settle, budget {budget.wait_ms} ms ({ms - budget.wait_ms} ms over)"
                + (" (a spinner showed)" if row["spinner"] else " (no spinner showed)"), settled_ms=ms, budget_ms=budget.wait_ms,
                over_ms=ms - budget.wait_ms, spinner=row["spinner"])

    # 7 first, because a wall is reported once: a late wall with no forward action is a late wall, not also a dead end.
    walls = [r for r in rows if r["denied"]]
    late = [r for r in walls if r["step"] >= 2]
    late_steps = {r["step"] for r in late}

    # 4. dead ends
    dead = [r for r in rows if not r["terminal"] and r["forward_actions"] == 0 and r["step"] not in late_steps]
    for row in dead:
        add("dead-end", row, "a page that is not the journey's end and offers no forward action", forward_actions=0)

    # 5. back-tracks
    visited: dict[str, int] = {}
    backs: list[int] = []
    for row in rows:
        key = _norm(row["url"])
        if key in visited and row["then"] is None:
            backs.append(row["step"])
            add("back-track", row, f"returns to {key}, first visited at step {visited[key]}", first_step=visited[key])
        visited.setdefault(key, row["step"])

    # 6. forms re-entered
    forms: dict[tuple, dict] = {}
    reentered: list[int] = []
    for row in rows:
        form = row.get("form")
        if not form:
            continue
        sig = _signature(form)
        earlier = forms.get(sig)
        if earlier is not None and earlier["form"]["outcome"] == "returned":
            reentered.append(row["step"])
            add("form-re-entered", row, f"the form {sig[0]} ({', '.join(sig[1])}) is submitted again after it came back at step {earlier['step']}",
                first_step=earlier["step"], fields=list(sig[1]))
        forms[sig] = row

    # 7. late permission walls
    for row in late:
        add("late-wall", row, f"a permission wall at step {row['step']}, after {row['step'] - 1} step(s) were spent", wasted_steps=row["step"] - 1)

    metrics = {"journey": name, "persona": journey["persona"], "steps": steps, "steps_budget": budget.steps, "complete": journey["complete"],
               "switches": switches, "switches_budget": budget.switches, "longest_wait_ms": longest, "wait_budget_ms": budget.wait_ms,
               "spinner_seen": spinner_seen, "dead_ends": len(dead), "back_tracks": len(backs), "forms_re_entered": len(reentered),
               "late_walls": len(late), "walls": len(walls)}
    return findings, metrics, unverified


def rank(findings: list[Finding]) -> list[Finding]:
    """Deterministic order: class, then how much (the larger overrun first), then step."""
    def amount(f: Finding) -> int:
        return -int(f.evidence.get("over_ms") or f.evidence.get("over") or f.evidence.get("wasted_steps") or 0)
    return sorted(findings, key=lambda f: (RANK.index(f.measurement), amount(f), f.step or 0, f.journey))


def judge(doc: dict, root: Path) -> Result:
    problems = validate(doc)
    budgets: dict[str, Budget] = {}
    for journey in doc["journeys"]:
        if not isinstance(journey, dict) or not isinstance(journey.get("document"), str) or not isinstance(journey.get("heading"), str):
            continue
        name = journey.get("journey", "?")
        path = (root / journey["document"]).resolve()
        if not path.is_relative_to(root.resolve()):
            problems.append(f"{name}: the document `{journey['document']}` is outside the project root")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as err:
            problems.append(f"{name}: cannot read its journey document `{journey['document']}` ({err.strerror})")
            continue
        budget, why = parse_budget(text, journey["heading"])
        if budget is None:
            problems.append(f"{name}: `{journey['document']}` section `{journey['heading']}` {why}")
        else:
            budgets[name] = budget
    if problems:
        raise Unusable("\n  - " + "\n  - ".join(problems))
    result = Result()
    for journey in doc["journeys"]:
        findings, metrics, unverified = judge_journey(journey, budgets[journey["journey"]])
        result.findings += findings
        result.metrics.append(metrics)
        result.unverified += unverified
    result.findings = rank(result.findings)
    return result


# ---------------------------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------------------------

def render(result: Result) -> str:
    out = ["## Flow bottlenecks (measured; each journey against its own declared Budget)", ""]
    out.append("| journey | steps | switches | longest wait | dead ends | back-tracks | forms re-entered | late walls |")
    out.append("|---|---|---|---|---|---|---|---|")
    for m in result.metrics:
        sw = f"{m['switches']}" + (f" / {m['switches_budget']}" if m["switches_budget"] is not None else " (no budget)")
        out.append(f"| {m['journey']} | {m['steps']} / {m['steps_budget']}{'' if m['complete'] else ' (not completed)'} | {sw} | "
                   f"{m['longest_wait_ms']} ms / {m['wait_budget_ms']} ms | {m['dead_ends']} | {m['back_tracks']} | {m['forms_re_entered']} | "
                   f"{m['late_walls']} |")
    out.append("")
    if not result.findings and not result.unverified:
        out.append("No bottleneck: every journey is within its budget, with no dead end, back-track, re-entered form or late wall.")
    for n, f in enumerate(result.findings, 1):
        out.append(f"{n}. **{f.measurement}** — {f.journey}" + (f", step {f.step} (`{f.url}`)" if f.step else "") + f": {f.detail}")
    if result.unverified:
        out.append("")
        out.append("Not measured (a wait with no settled time is not a wait that passed):")
        out.extend(f"- {u}" for u in result.unverified)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure a journey as a flow, against its own declared budget.")
    ap.add_argument("document", nargs="?", type=Path, help="flow.json from `journey-walker`")
    ap.add_argument("--root", type=Path, default=Path("."), help="the project root the journey documents are relative to (default: .)")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--schema", action="store_true", help="print what `journey-walker` must emit")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if a.document is None:
        ap.error("a flow document is required (or --schema / --selftest)")
    try:
        result = judge(load(a.document), a.root)
    except Unusable as err:
        print(f"UNUSABLE: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001 -- exit 1 means "findings"; a crash that exits 1 would read as a finding, so it exits 2 and says what it was
        print(f"UNUSABLE: unexpected {type(err).__name__}: {err}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"metrics": result.metrics, "unverified": result.unverified, "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        print(render(result))
    return 1 if (result.findings or result.unverified) else 0


# ---------------------------------------------------------------------------------------------
# Selftest: every measurement fires on its defect and stays silent on its near-miss
# ---------------------------------------------------------------------------------------------

def selftest() -> int:
    import copy
    import tempfile

    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def row(step: int, url: str = "/a", **over) -> dict:
        base = {"step": step, "url": url, "action": "click", "section": "s", "settled_ms": 300, "spinner": False, "status": 200, "forward_actions": 2,
                "terminal": False, "denied": False, "form": None, "then": None}
        base.update(over)
        return base

    def journey(rows: list[dict], complete: bool = True, name: str = "j") -> dict:
        if complete and rows:
            rows[-1]["terminal"] = True
        return {"journey": name, "persona": "p", "document": "docs/j.md", "heading": "Journey", "complete": complete, "rows": rows}

    BUDGET = Budget(steps=5, wait_ms=2000)

    def kinds(j: dict, budget: Budget = BUDGET) -> list[str]:
        return [f.measurement for f in judge_journey(j, budget)[0]]

    clean = journey([row(1, "/a"), row(2, "/b"), row(3, "/c")])
    check("a journey within budget with nothing wrong is clean", kinds(clean) == [], kinds(clean))

    # 1. steps
    over = journey([row(i, f"/p{i}") for i in range(1, 8)])
    check("steps over budget is a finding naming the overrun", kinds(over) == ["steps-over-budget"]
          and judge_journey(over, BUDGET)[0][0].evidence["over"] == 2, kinds(over))
    check("steps AT the budget is not over", kinds(journey([row(i, f"/p{i}") for i in range(1, 6)])) == [], "")
    check("a journey that never completed is a finding, not a step count", kinds(journey([row(1), row(2, "/b")], complete=False)) == ["journey-incomplete"],
          kinds(journey([row(1), row(2, "/b")], complete=False)))

    # 2. context switches
    sw = journey([row(1, "/a", section="x"), row(2, "/b", section="y"), row(3, "/c", section="x"), row(4, "/d", section="x", action="modal-open")])
    check("switches are counted (two section changes and a modal)", judge_journey(sw, BUDGET)[1]["switches"] == 3, judge_journey(sw, BUDGET)[1])
    check("switches with no declared limit are measured, not a finding", kinds(sw) == [], kinds(sw))
    check("switches over a declared limit are a finding", kinds(sw, Budget(5, 2000, switches=2)) == ["switches-over-budget"], kinds(sw, Budget(5, 2000, switches=2)))
    check("switches AT a declared limit are not over", kinds(sw, Budget(5, 2000, switches=3)) == [], "")
    check("a null section never counts as a move", judge_journey(journey([row(1, "/a", section=None), row(2, "/b", section="x")]), BUDGET)[1]["switches"] == 0, "")

    # 3. waits
    slow = journey([row(1, "/a"), row(2, "/b", settled_ms=2500, spinner=True), row(3, "/c", settled_ms=2500)])
    wf = [f for f in judge_journey(slow, BUDGET)[0] if f.measurement == "wait-over-budget"]
    check("every wait over the budget is a finding, with and without a spinner", len(wf) == 2 and "spinner showed" in wf[0].detail + wf[1].detail
          and "no spinner" in wf[0].detail + wf[1].detail, [f.detail for f in wf])
    check("a wait AT the budget is not over", kinds(journey([row(1, "/a", settled_ms=2000)])) == [], "")
    unmeasured = judge_journey(journey([row(1, "/a", settled_ms=None)]), BUDGET)
    check("a wait that was not measured is unverified, never a pass", len(unmeasured[2]) == 1 and unmeasured[0] == [], unmeasured[2])

    # 4. dead ends
    check("a page with no forward action that is not the end is a dead end",
          kinds(journey([row(1, "/a"), row(2, "/b", forward_actions=0), row(3, "/c")])) == ["dead-end"], "")
    check("the declared end with no forward action is not a dead end", kinds(journey([row(1, "/a"), row(2, "/b", forward_actions=0)])) == [], "")

    # 5. back-tracks
    bt = journey([row(1, "/a"), row(2, "/b"), row(3, "/a", action="back"), row(4, "/c")])
    check("a landing on an earlier URL is a back-track naming the first visit",
          kinds(bt) == ["back-track"] and judge_journey(bt, BUDGET)[0][0].evidence["first_step"] == 1, kinds(bt))
    check("a reload the app caused is not a back-track", kinds(journey([row(1, "/a"), row(2, "/a", action="submit", then="reload")])) == [], "")
    check("a redirect the app caused is not a back-track", kinds(journey([row(1, "/a"), row(2, "/b", action="submit", then="redirect")])) == [], "")
    check("a redirect that lands on an EARLIER page is still the app's doing, not a back-track",
          kinds(journey([row(1, "/list"), row(2, "/new"), row(3, "/list", action="submit", then="redirect")])) == [], "")
    # A step is something the person does: a submit that redirects is ONE step, not two.
    sub = journey([row(1, "/a"), row(2, "/new", action="submit", then="redirect"), row(3, "/done")])
    check("a submit followed by a redirect counts as 1 step (3 rows, 3 steps, never 4)", judge_journey(sub, Budget(3, 2000))[1]["steps"] == 3
          and kinds(sub, Budget(3, 2000)) == [], judge_journey(sub, Budget(3, 2000))[1])
    check("a journey is not over budget by the app's own redirects", kinds(journey([row(i, f"/p{i}", action="submit", then="redirect") for i in range(1, 4)]),
                                                                          Budget(3, 2000)) == [], "")
    check("a trailing slash and a fragment do not make a new page", kinds(journey([row(1, "/a"), row(2, "/b"), row(3, "/a/#top")])) == ["back-track"], "")
    check("a different query is a different page", kinds(journey([row(1, "/a?x=1"), row(2, "/a?x=2")])) == [], "")

    # 6. forms re-entered
    f1 = {"url": "/new", "fields": ["title", "details"], "outcome": "returned"}
    re_ = journey([row(1, "/new", form=f1), row(2, "/new", form={**f1, "outcome": "advanced"}, action="submit"), row(3, "/done")])
    check("the same form submitted again after it came back is a finding", "form-re-entered" in kinds(re_), kinds(re_))
    check("the same form submitted twice but never returned is not re-entry",
          "form-re-entered" not in kinds(journey([row(1, "/new", form={**f1, "outcome": "advanced"}), row(2, "/x"), row(3, "/new", form={**f1, "outcome": "advanced"}, action="submit")])), "")
    check("a different field set is a different form", "form-re-entered" not in kinds(
        journey([row(1, "/new", form=f1), row(2, "/new", form={**f1, "fields": ["other"]}, action="submit")])), "")
    check("field order does not make a different form", "form-re-entered" in kinds(
        journey([row(1, "/new", form=f1), row(2, "/x"), row(3, "/new", form={**f1, "fields": ["details", "title"]}, action="submit")])), "")

    # 7. late walls
    late = journey([row(1, "/a"), row(2, "/b"), row(3, "/admin", denied=True, status=403, forward_actions=1)])
    lf = [f for f in judge_journey(late, BUDGET)[0] if f.measurement == "late-wall"]
    check("a wall at step 3 is a late wall naming the steps spent", len(lf) == 1 and lf[0].evidence["wasted_steps"] == 2, [f.detail for f in lf])
    walled = journey([row(1, "/a"), row(2, "/admin", denied=True, status=403, forward_actions=0), row(3, "/c")])
    check("a late wall with no forward action is reported ONCE, as a late wall, not also as a dead end", kinds(walled) == ["late-wall"], kinds(walled))
    check("a wall at step 1 with no forward action is a dead end, reported once",
          kinds(journey([row(1, "/admin", denied=True, status=403, forward_actions=0), row(2, "/b")])) == ["dead-end"],
          kinds(journey([row(1, "/admin", denied=True, status=403, forward_actions=0), row(2, "/b")])))
    check("a wall at step 1 is not late", "late-wall" not in kinds(journey([row(1, "/admin", denied=True, status=403, forward_actions=1), row(2, "/b")])), "")

    # ranking
    mixed = journey([row(1, "/a"), row(2, "/b", forward_actions=0), row(3, "/a", action="back", settled_ms=9000), row(4, "/z", denied=True, forward_actions=1)])
    order = [f.measurement for f in rank(judge_journey(mixed, BUDGET)[0])]
    check("findings rank walls, then dead ends, then back-tracks, then waits", order == ["late-wall", "dead-end", "back-track", "wait-over-budget"], order)
    check("ranking is deterministic", [f.__dict__ for f in rank(judge_journey(mixed, BUDGET)[0])] == [f.__dict__ for f in rank(list(reversed(judge_journey(mixed, BUDGET)[0])))], "")
    check("the rule field is null (no framework rule applies to any of the seven)", all(f.rule is None for f in judge_journey(mixed, BUDGET)[0]), "")

    # the budget declaration
    good = "# Doc\n\n## Journey\n\nBudget: steps=8 wait=3s\n\ntext\n\n## Other\n\nBudget: steps=1 wait=1s\n"
    b, why = parse_budget(good, "Journey")
    check("a budget is read from its own section only", b == Budget(8, 3000) and why is None, (b, why))
    check("a budget in milliseconds and with switches is read", parse_budget("## J\nBudget: steps=4 wait=500ms switches=2\n", "J")[0] == Budget(4, 500, 2), "")
    check("a wait of exactly 1 ms is a budget", parse_budget("## J\nBudget: steps=1 wait=1ms\n", "J")[0] == Budget(1, 1), "")
    check("a fractional second that is whole milliseconds is a budget", parse_budget("## J\nBudget: steps=1 wait=0.5s\n", "J")[0] == Budget(1, 500), "")
    check("separators between limits are accepted", parse_budget("## J\nBudget: steps=4, wait=2s; switches=1\n", "J")[0] == Budget(4, 2000, 1), "")
    check("a bulleted, bold Budget line is read", parse_budget("## J\n- **Budget:** steps=4 wait=2s\n", "J")[0] == Budget(4, 2000), "")
    for label, text, needle in (
            ("no Budget line", "## J\ntext\n", "declares no `Budget:`"),
            ("a Budget line with no values", "## J\nBudget: tbd\n", "no `steps=`"),
            ("steps only", "## J\nBudget: steps=4\n", "needs both"),
            ("wait only", "## J\nBudget: wait=2s\n", "needs both"),
            ("wait with no unit", "## J\nBudget: steps=4 wait=2\n", "needs a unit"),
            ("zero steps", "## J\nBudget: steps=0 wait=2s\n", "not a budget"),
            ("a fractional step count", "## J\nBudget: steps=4.5 wait=2s\n", "whole number"),
            ("an unknown limit", "## J\nBudget: steps=4 wait=2s bounce=3\n", "not a budget limit"),
            ("a repeated limit", "## J\nBudget: steps=4 steps=5 wait=2s\n", "twice"),
            ("two Budget lines", "## J\nBudget: steps=4 wait=2s\nBudget: steps=5 wait=2s\n", "one journey, one budget"),
            ("the budget of ANOTHER journey", "## J\ntext\n\n## K\nBudget: steps=4 wait=2s\n", "declares no `Budget:`"),
            ("a heading that is not in the document", "## K\nBudget: steps=4 wait=2s\n", "declared nowhere"),
            ("a lone point as the wait number", "## J\nBudget: steps=8 wait=.s\n", "does not understand"),
            ("a point with no digits after it", "## J\nBudget: steps=8 wait=3.s\n", "does not understand"),
            ("a wait of a tenth of a millisecond", "## J\nBudget: steps=8 wait=0.0001s\n", "whole number of milliseconds"),
            ("a wait of half a millisecond", "## J\nBudget: steps=8 wait=0.5ms\n", "whole number of milliseconds"),
            ("a wait of zero", "## J\nBudget: steps=8 wait=0s\n", "less than 1 ms"),
            ("leftover text on the line", "## J\nBudget: steps=8 wait=3s junk=zz\n", "does not understand"),
            ("leftover words on the line", "## J\nBudget: steps=8 wait=3s approximately\n", "does not understand"),
            ("a duplicated journey heading", "## J\nBudget: steps=4 wait=2s\n\n## J\nBudget: steps=9 wait=9s\n", "2 times")):
        try:
            got = parse_budget(text, "J")
        except Exception as exc:  # noqa: BLE001 -- a crash in the parser is a failed check, not an aborted selftest
            got = (None, f"raised {exc!r}")
        check(f"{label} is refused", got[0] is None and needle in (got[1] or ""), got)

    # the document and the refusals
    doc = {"schema": SCHEMA, "journeys": [journey([row(1, "/a"), row(2, "/b")])]}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs/j.md").write_text(good, encoding="utf-8")
        try:
            result = judge(doc, root)
            check("a valid document is judged end to end", result.findings == [] and result.metrics[0]["steps"] == 2, result.metrics)
        except Unusable as err:
            check("a valid document is judged end to end", False, str(err))
        (root / "docs/j.md").write_text("## Journey\ntext\n", encoding="utf-8")
        try:
            judge(doc, root)
            check("a journey with no budget is refused (exit 2), never judged against a default", False, "judged")
        except Unusable as err:
            check("a journey with no budget is refused (exit 2), never judged against a default", "declares no `Budget:`" in str(err), str(err))
        try:
            judge(doc, Path(tmp) / "nowhere")
            check("a missing journey document is refused", False, "judged")
        except Unusable as err:
            check("a missing journey document is refused", "cannot read its journey document" in str(err), str(err))
        outside = copy.deepcopy(doc)
        outside["journeys"][0]["document"] = "../escape.md"
        try:
            judge(outside, root)
            check("a document outside the project root is refused", False, "judged")
        except Unusable as err:
            check("a document outside the project root is refused", "outside the project root" in str(err), str(err))
    # A sibling whose name merely STARTS with the root's name is outside it (a string prefix test says it is inside).
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "repo").mkdir()
        (base / "repo-evil").mkdir()
        (base / "repo-evil" / "j.md").write_text(good, encoding="utf-8")
        sib = copy.deepcopy(doc)
        sib["journeys"][0]["document"] = "../repo-evil/j.md"
        try:
            judge(sib, base / "repo")
            check("a sibling directory that shares the root's name as a prefix is refused", False, "judged")
        except Unusable as err:
            check("a sibling directory that shares the root's name as a prefix is refused", "outside the project root" in str(err), str(err))

    def refused(label: str, mutate, needle: str) -> None:
        bad = copy.deepcopy(doc)
        mutate(bad)
        problems = validate(bad)
        check(label, any(needle in p for p in problems), problems)

    refused("a step out of order is refused", lambda d: d["journeys"][0]["rows"][1].update(step=5), "steps are the actions in order")
    refused("`redirect` as an action is refused, with where it belongs", lambda d: d["journeys"][0]["rows"][0].update(action="redirect"), "recorded as `then`")
    refused("`reload` as an action is refused", lambda d: d["journeys"][0]["rows"][0].update(action="reload"), "recorded as `then`")
    refused("an unknown `then` is refused", lambda d: d["journeys"][0]["rows"][0].update(then="teleport"), "then must be null")
    refused("a row with no `then` is refused", lambda d: d["journeys"][0]["rows"][0].pop("then"), "then must be null")
    refused("an unknown action is refused", lambda d: d["journeys"][0]["rows"][0].update(action="teleport"), "action must be one of")
    refused("a negative settled time is refused", lambda d: d["journeys"][0]["rows"][0].update(settled_ms=-1), "settled_ms")
    refused("a string settled time is refused", lambda d: d["journeys"][0]["rows"][0].update(settled_ms="fast"), "settled_ms")
    refused("a non-boolean flag is refused", lambda d: d["journeys"][0]["rows"][0].update(terminal="yes"), "terminal must be true or false")
    refused("a form with no fields is refused", lambda d: d["journeys"][0]["rows"][0].update(form={"url": "/x", "fields": [], "outcome": "advanced"}), "form must be null")
    refused("a form with an unknown outcome is refused", lambda d: d["journeys"][0]["rows"][0].update(form={"url": "/x", "fields": ["a"], "outcome": "maybe"}), "form must be null")
    refused("a journey with no rows is refused", lambda d: d["journeys"][0].update(rows=[]), "was not walked")
    refused("a complete journey whose last row is not the end is refused", lambda d: d["journeys"][0]["rows"][-1].update(terminal=False), "not the declared end")
    refused("a duplicated journey name is refused", lambda d: d["journeys"].append(copy.deepcopy(d["journeys"][0])), "appears twice")
    refused("a missing field is refused", lambda d: d["journeys"][0]["rows"][0].pop("url"), "url must be")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "f.json"
        for label, text in (("not JSON", "{ nope"), ("a wrong schema", json.dumps({"schema": "other", "journeys": []})),
                            ("no journeys", json.dumps({"schema": SCHEMA, "journeys": []}))):
            p.write_text(text, encoding="utf-8")
            try:
                load(p)
                check(f"a document that is {label} is refused", False, "loaded")
            except Unusable:
                check(f"a document that is {label} is refused", True)
        try:
            load(Path(tmp) / "missing.json")
            check("a missing document is refused", False, "loaded")
        except Unusable:
            check("a missing document is refused", True)

    # THE COMMAND LINE: the exit codes are the contract a gate or an agent reads.
    import contextlib
    import io

    def run_main(flow: dict, document: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs/j.md").write_text(document, encoding="utf-8")
            (root / "flow.json").write_text(json.dumps(flow), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main([str(root / "flow.json"), "--root", str(root)])

    check("a clean flow exits 0", run_main(doc, good) == 0, run_main(doc, good))
    check("a flow with a finding exits 1", run_main({"schema": SCHEMA, "journeys": [journey([row(i, f"/p{i}") for i in range(1, 12)])]}, good) == 1, "")
    check("an unmeasured wait fails the run (exit 1), never passes it",
          run_main({"schema": SCHEMA, "journeys": [journey([row(1, "/a", settled_ms=None), row(2, "/b")])]}, good) == 1, "")
    check("a journey with no budget exits 2", run_main(doc, "## Journey\ntext\n") == 2, "")
    check("`wait=.s` exits 2, never as a crash that reads as a finding", run_main(doc, "## Journey\nBudget: steps=8 wait=.s\n") == 2, "")
    original = globals()["judge"]

    def exploding(*args, **kwargs):
        raise ValueError("unexpected")

    globals()["judge"] = exploding
    try:
        crashed = run_main(doc, good)
    except Exception as exc:  # noqa: BLE001 -- the selftest reports a crash as a failed check, it does not abort
        crashed = f"raised {exc!r}"
    finally:
        globals()["judge"] = original
    check("an unexpected exception exits 2, never 1 (which means findings)", crashed == 2, crashed)
    check("a malformed document exits 2", run_main({"schema": SCHEMA, "journeys": [{"journey": "x"}]}, good) == 2, "")

    check("the schema example is itself a valid document", validate(copy.deepcopy(SCHEMA_EXAMPLE)) == [], validate(copy.deepcopy(SCHEMA_EXAMPLE)))
    text = render(judge_journey_result(doc))
    check("the report names the journey and its budget", "| j | 2 / 8 |" in text, text)

    for f in failures:
        print(f"FAIL {f}")
    print(f"flow_report selftest: {n - len(failures)} of {n} checks passed")
    return 1 if failures else 0


def judge_journey_result(doc: dict) -> Result:
    """The judged result for a document whose budget is `steps=8 wait=3s`, for the report's selftest (no file needed)."""
    result = Result()
    for j in doc["journeys"]:
        findings, metrics, unverified = judge_journey(j, Budget(8, 3000))
        result.findings += findings
        result.metrics.append(metrics)
        result.unverified += unverified
    return result


if __name__ == "__main__":
    sys.exit(main())
