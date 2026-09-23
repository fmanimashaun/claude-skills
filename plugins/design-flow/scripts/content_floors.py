#!/usr/bin/env python3
"""A recorded floor for the design-flow content gates, so tracked debt is not a permanent FAIL (#1187).

`structure_ratchet` has had this since it was written; the three content gates never did. They
return `1 if findings else 0`, so a project with **tracked, triaged, deliberately-deferred** design
debt can never show a green sweep however well that debt is managed. The gate cannot distinguish

    debt that is known, filed, assigned and shrinking      from
    debt that appeared this morning and nobody has noticed

and both print FAIL. A verdict that carries no information for any project past its first week is
one people stop reading, which is how a gate dies. Measured on a live downstream project: 21 of 21
design-flow findings were already filed and owned, seven of them blocked on a recorded design
decision awaiting a human.

NO FLOOR FILE MEANS ZERO TOLERANCE, unchanged. A greenfield project is green on day one and stays
strict; this only exists for a project that has chosen to sanction a specific amount of debt and
written the number down.

THE RATCHET REFUSES BOTH DIRECTIONS. Above the floor fails, naming what is new. **Below the floor
also fails**, because a floor nobody lowers after doing the work leaves that much room to drift back
silently -- the gate would be green while the debt regrew to a number someone recorded months ago.

PER RULE, NOT PER GATE, and that is not tidiness. `component-contract` reports `raw-element` and
`component-drops-attributes` together; one floor of 9 is satisfied by 9 of either. So five sites
converted and four new ones of the other kind reads exactly like nothing happening -- a count that
cannot tell two causes apart, which is `signal-that-cannot-discriminate` sitting inside the fix for
it. A gate whose findings carry no rule token gets one floor under `*`, which is the honest
degradation rather than a guessed split.

Stdlib only, no network.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FLOORS = Path(".design-flow") / "content-floors.json"

# The rule token every finding leads with -- `path:12: raw-element — …`. `check_surface_layout`
# writes prose instead, and gets `*`; inventing a split for it would be a floor for a rule that
# does not exist.
RULE = re.compile(r"^[^\s]+?:(?:\d+:)?\s*([a-z][a-z0-9-]{2,})\s+[—-]")


def rule_of(finding: str) -> str:
    m = RULE.match(finding.strip())
    return m.group(1) if m else "*"


def tally(findings: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[rule_of(f)] = out.get(rule_of(f), 0) + 1
    return out


def load(root: Path, gate: str) -> dict[str, int] | None:
    """The floors recorded for this gate, or None when the project has recorded none."""
    path = root / FLOORS
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{FLOORS} is not valid JSON: {exc}")
    gates = data.get("floors")
    if not isinstance(gates, dict):
        raise SystemExit(f"{FLOORS} has no `floors` object — re-cut it with --set-floor")
    entry = gates.get(gate)
    if entry is None:
        return None                      # this gate is not sanctioned; zero tolerance stands
    if not isinstance(entry, dict):
        raise SystemExit(f"{FLOORS}: floors.{gate} must be an object of rule -> count")
    return {str(k): int(v) for k, v in entry.items()}


def _head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def set_floor(root: Path, gate: str, findings: list[str]) -> int:
    """Record the CURRENT counts as this gate's floor, leaving other gates untouched."""
    path = root / FLOORS
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{FLOORS} is not valid JSON: {exc}")
    floors = data.get("floors")
    if not isinstance(floors, dict):
        floors = {}
    counts = tally(findings)
    if counts:
        floors[gate] = dict(sorted(counts.items()))
    else:
        floors.pop(gate, None)           # nothing left to sanction: remove the row, restore strict
    data["measured_by"] = f"{gate} --set-floor"
    data["measured_at"] = _head(root)
    data["floors"] = dict(sorted(floors.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    total = sum(counts.values())
    print(f"wrote {FLOORS} — {gate}: {total} sanctioned finding(s) across {len(counts)} rule(s).")
    print("Commit it on its own, and say in the message WHY this debt is sanctioned and what "
          "issue tracks it. A floor with no reason is indistinguishable from giving up.")
    return 0


def verdict(root: Path, gate: str, findings: list[str]) -> tuple[int, list[str]]:
    """(exit code, lines to print). No floors recorded -> today's behaviour, unchanged."""
    floors = load(root, gate)
    if floors is None:
        return (1 if findings else 0), []

    counts = tally(findings)
    lines, failed = [], False
    # Every rule either side knows about -- a rule that has gone to zero must still be seen, or a
    # stale floor for it is invisible.
    for rule in sorted(set(counts) | set(floors)):
        now, floor = counts.get(rule, 0), floors.get(rule)
        if floor is None:
            failed = True
            lines.append(f"  {rule}: {now} finding(s) and NO recorded floor — this rule is not "
                         f"sanctioned. Fix them, or record the floor and say what tracks it.")
        elif now > floor:
            failed = True
            lines.append(f"  {rule}: {now} finding(s), floor {floor} — {now - floor} NEW. "
                         f"Sanctioned debt is not a budget to spend.")
        elif now < floor:
            failed = True
            lines.append(f"  {rule}: {now} finding(s) but the floor is still {floor} — STALE. The "
                         f"work was done and the floor was not lowered, so this rule may drift "
                         f"back {floor - now} finding(s) without failing. Re-cut it.")
        else:
            lines.append(f"  {rule}: {now} at the floor — sanctioned, still visible.")
    return (1 if failed else 0), lines


def _selftest() -> int:
    import tempfile
    failures: list[str] = []

    def expect(label: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    RAW = "app/views/x.html.erb:1: raw-element — a hand-written button"
    DROP = "app/components/y.rb: component-drops-attributes — never stores"
    PROSE = "app/components/z.html.erb: wraps the content it is handed in `stack`"

    # The rule token, and the honest degradation for a gate that does not write one.
    expect("a tagged finding yields its rule", rule_of(RAW) == "raw-element", rule_of(RAW))
    expect("a second rule is distinguished", rule_of(DROP) == "component-drops-attributes", rule_of(DROP))
    expect("an untagged finding is `*`, not a guess", rule_of(PROSE) == "*", rule_of(PROSE))
    # THE CONTROL FOR THAT: if rule_of returned "*" for everything, the three above still pass
    # except the first two -- so assert the tally SPLITS, which is the property per-rule exists for.
    expect("the tally splits by rule", tally([RAW, DROP, RAW]) == {"raw-element": 2, "component-drops-attributes": 1},
           str(tally([RAW, DROP, RAW])))

    root = Path(tempfile.mkdtemp(prefix="content-floors-"))

    # NO FLOOR FILE IS ZERO TOLERANCE, unchanged. This is the property that must not regress: the
    # whole change is worthless if it quietly relaxes a greenfield project.
    code, lines = verdict(root, "g", [RAW])
    expect("no floor file: findings still fail", code == 1 and lines == [], f"{code} {lines}")
    code, lines = verdict(root, "g", [])
    expect("no floor file: clean still passes", code == 0 and lines == [])

    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        set_floor(root, "g", [RAW, RAW, DROP])

    expect("at the floor: passes", verdict(root, "g", [RAW, RAW, DROP])[0] == 0)
    expect("above the floor: fails", verdict(root, "g", [RAW, RAW, RAW, DROP])[0] == 1)
    expect("below the floor: fails as STALE", verdict(root, "g", [RAW, DROP])[0] == 1)
    expect("...and says STALE, not NEW",
           any("STALE" in l for l in verdict(root, "g", [RAW, DROP])[1]))

    # A RULE THAT REACHES ZERO, which is a different case from one that merely fell. It is absent
    # from the tally entirely, so a verdict that iterates only what was FOUND cannot see that a
    # floor for it is still standing — the rule would be free to come all the way back in silence.
    # The mutation "only the rules still found are checked" SURVIVED until this case existed: the
    # STALE case above kept the rule present, so it exercised the comparison and not the iteration.
    code, lines = verdict(root, "g", [RAW, RAW])
    expect("a rule fixed to ZERO still reports its stale floor", code == 1, str(lines))
    expect("...naming the rule that is gone",
           any("component-drops-attributes" in l and "STALE" in l for l in lines), str(lines))

    # THE REASON THE FLOORS ARE PER RULE. One rule falling while the other rises keeps the TOTAL at
    # three, so a single per-gate count cannot tell it from nothing happening.
    swapped = [RAW, DROP, DROP]
    expect("a swap that keeps the total is still caught", verdict(root, "g", swapped)[0] == 1,
           str(verdict(root, "g", swapped)[1]))
    expect("...and it names the rule that GREW",
           any("component-drops-attributes" in l and "NEW" in l for l in verdict(root, "g", swapped)[1]))

    # A gate with no floors recorded is untouched by another gate's entry.
    expect("an unrecorded gate keeps zero tolerance", verdict(root, "other", [RAW])[0] == 1)

    # A rule appearing that was never sanctioned is not silently allowed by its gate's entry.
    NEWRULE = "app/views/q.html.erb:2: breakpoint-driven-layout — md: prefixes"
    code, lines = verdict(root, "g", [RAW, RAW, DROP, NEWRULE])
    expect("an unsanctioned rule fails even when the others are at their floor", code == 1)
    expect("...and says the rule is not sanctioned",
           any("breakpoint-driven-layout" in l and "NO recorded floor" in l for l in lines))

    with contextlib.redirect_stdout(io.StringIO()):
        set_floor(root, "g", [])
    expect("set-floor with nothing left removes the row, restoring strict",
           verdict(root, "g", [RAW])[0] == 1 and load(root, "g") is None)

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"content_floors selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_selftest())
