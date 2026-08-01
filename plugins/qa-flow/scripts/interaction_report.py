#!/usr/bin/env python3
"""Judge an interaction sweep: which controls do nothing when you use them.

Run:  python3 interaction_report.py qa/manual-tests/interactions.json
      python3 interaction_report.py --schema
      python3 interaction_report.py --selftest

WHY (#105, criterion 4 — "inventories interactive elements, exercises each distinct type, and flags
dead controls"). Everything nearby judges a control by how it **looks**: `icon-only-unnamed` wants a
name, `focus-ring-missing` wants a focus style, `aria-controls-no-expanded` wants the state
attribute. A control can satisfy all three and **still do nothing when clicked** — a button whose
handler never bound because its Stimulus controller failed to register, or whose target selector no
longer matches. It is named, focusable, correctly marked up, and inert.

That defect is only visible by *using* the control and observing whether anything changed. So the
browser activates each one and records what happened; every verdict about what counts as "something
happened" is here.

THE EXCLUSIONS ARE THE DESIGN. A rule that flags every control without a DOM change is unusable in a
real app, so a control is judged dead only when it was genuinely exercised and genuinely inert:

  * `disabled` / `aria-disabled` — doing nothing is the correct behaviour, not a defect.
  * a link with an `href` — navigation IS its effect; a crawl that stays on the page cannot observe
    it, and calling that dead would flag every link on the site.
  * anything the collector marks `exercised: false` — reported as NOT EXERCISED, never as passing.
    A control nobody could click was not verified, and that is a third state, not a clean one.

WHAT COUNTS AS AN EFFECT is deliberately broad — DOM mutation, navigation, a network request, a
focus move, an `aria-expanded`/`aria-selected`/`aria-pressed` flip, or a dialog opening. Broad
because a false "dead control" on a working button is the finding that gets this switched off.

WHAT IT DOES NOT DO. It does not judge naming, focus styling or ARIA correctness — those have owners
already, and a second opinion here would drift from them. It does not crawl or click.

Exit codes:  0 clean · 1 findings · 2 the sweep file is unusable

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "qa-flow/interaction-sweep/1"

# Any one of these means the control did something. Kept broad on purpose: see the docstring.
EFFECT_KEYS = ("domChanged", "navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")


class Unusable(RuntimeError):
    """The sweep cannot be judged -- reported, never treated as a clean sweep."""


@dataclass
class Finding:
    ref: str
    rule: str
    detail: str


@dataclass
class Judged:
    findings: list[Finding] = field(default_factory=list)
    exercised: int = 0
    not_exercised: list[str] = field(default_factory=list)
    excluded: int = 0


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Unusable(f"{path}: not a {SCHEMA} document — run `--schema` to see what is expected")
    controls = data.get("controls")
    if not isinstance(controls, list) or not controls:
        raise Unusable(
            f"{path}: no controls. An empty sweep reporting zero dead controls is indistinguishable "
            "from a page whose every control works, which is the outcome this must never produce.")
    return controls


def excluded_reason(control: dict) -> str | None:
    """Why this control is not a candidate for `dead-control`, or None if it is."""
    if control.get("disabled"):
        return "disabled — doing nothing is correct"
    if control.get("tag") == "a" and control.get("href"):
        # Navigation is the effect. A sweep that stays on the page cannot observe it, and flagging
        # it would put every link on the site in the report.
        return "link with href — navigation is its effect and is not observed here"
    return None


def judge(controls: list[dict]) -> Judged:
    result = Judged()
    for control in controls:
        ref = str(control.get("ref", "<unknown>"))
        if not control.get("exercised", False):
            result.not_exercised.append(f"{ref}: {control.get('reason') or 'not activated'}")
            continue
        if excluded_reason(control):
            result.excluded += 1
            continue
        result.exercised += 1
        effects = control.get("effects") or {}
        if not any(effects.get(k) for k in EFFECT_KEYS):
            result.findings.append(Finding(
                ref, "dead-control",
                f"{control.get('tag', '?')}"
                f"{'[' + control['role'] + ']' if control.get('role') else ''} "
                f"named {control.get('name') or '(unnamed)'!r} — activated, nothing changed"))
        for message in control.get("consoleAfter", []) or []:
            if str(message.get("level", "")).lower() == "error":
                result.findings.append(Finding(
                    ref, "error-on-activate", str(message.get("text", ""))[:120]))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge an interaction sweep.")
    ap.add_argument("sweep", nargs="?", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps({
            "schema": SCHEMA,
            "controls": [{
                "ref": "main > button.filter", "tag": "button", "role": "", "name": "Filter",
                "disabled": False, "href": None, "exercised": True, "reason": None,
                "effects": {k: False for k in EFFECT_KEYS},
                "consoleAfter": [{"level": "error", "text": "..."}],
            }],
        }, indent=2))
        return 0
    if not args.sweep:
        ap.error("a sweep file is required (or --schema / --selftest)")
    try:
        result = judge(load(args.sweep))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"exercised": result.exercised, "excluded": result.excluded,
                          "notExercised": result.not_exercised,
                          "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        for f in result.findings:
            print(f"  [{f.rule}] {f.ref}\n      {f.detail}")
        for s in result.not_exercised:
            print(f"  [not exercised] {s}")
        print(f"\n{result.exercised} control(s) exercised, {len(result.findings)} finding(s), "
              f"{result.excluded} excluded by rule, {len(result.not_exercised)} not exercised.")
        if result.not_exercised:
            print("A control that was never activated is NOT a working control.")
    return 1 if result.findings else 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def ctl(**kw):
        base = {"ref": "r", "tag": "button", "name": "Go", "disabled": False, "href": None,
                "exercised": True, "effects": {k: False for k in EFFECT_KEYS}}
        base.update(kw)
        return base

    def rules(*controls) -> list[str]:
        return [f.rule for f in judge(list(controls)).findings]

    check("an inert button fires dead-control", rules(ctl()) == ["dead-control"], f"{rules(ctl())}")

    # Every effect kind must count. If one is dropped, a working control gets reported dead -- the
    # false positive that would get this switched off.
    #
    # The list is LITERAL, not `EFFECT_KEYS`. Deriving it from the constant under test made the
    # assertion vanish along with the key: removing `domChanged` from EFFECT_KEYS also removed the
    # fixture that would have named it, and the mutation was caught by an unrelated check instead.
    # A fixture derived from its subject cannot witness that subject shrinking.
    for key in ("domChanged", "navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened"):
        check(f"{key} is a known effect kind", key in EFFECT_KEYS,
              f"EFFECT_KEYS lost {key}; a control whose only effect is {key} would report dead")
        c = ctl(effects={**{k: False for k in EFFECT_KEYS}, key: True})
        check(f"{key} counts as an effect", rules(c) == [], f"still fired with {key}=True")

    # THE EXCLUSIONS.
    check("a disabled control is not dead", rules(ctl(disabled=True)) == [])
    check("a link with href is not dead", rules(ctl(tag="a", href="/next")) == [])
    check("a link WITHOUT href is still judged",
          rules(ctl(tag="a", href=None)) == ["dead-control"],
          "an anchor with no href navigates nowhere; it is exactly the dead control to catch")

    # NOT EXERCISED is a third state, never a pass.
    r = judge([ctl(exercised=False, reason="covered by an overlay")])
    check("an unexercised control is not judged clean", not r.findings and r.not_exercised, f"{r}")
    # Guarded, not indexed blindly: when the exercised-check is broken this list is EMPTY, and an
    # IndexError here would abort the run before any labelled assertion reported. A crash is not a
    # verdict -- the mutation checker refused this as a coincidental catch until it was fixed.
    check("and it is named with its reason",
          bool(r.not_exercised) and "overlay" in r.not_exercised[0], f"{r.not_exercised}")
    check("an unexercised control is not counted as exercised", r.exercised == 0, f"{r.exercised}")

    check("a console error on activate fires",
          "error-on-activate" in rules(ctl(effects={**{k: False for k in EFFECT_KEYS},
                                                    "domChanged": True},
                                           consoleAfter=[{"level": "error", "text": "boom"}])))
    check("a console warning on activate stays silent",
          rules(ctl(effects={**{k: False for k in EFFECT_KEYS}, "domChanged": True},
                    consoleAfter=[{"level": "warning", "text": "meh"}])) == [])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for label, body in (("not json", "{["),
                            ("wrong schema", '{"schema": "x/1", "controls": [{}]}'),
                            ("no controls", f'{{"schema": "{SCHEMA}", "controls": []}}')):
            p = Path(tmp) / "s.json"
            p.write_text(body, encoding="utf-8")
            n += 1
            try:
                load(p)
                failures.append(f"{label}: expected UNUSABLE")
            except Unusable:
                pass

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"interaction_report selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
