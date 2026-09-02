#!/usr/bin/env python3
"""Judge an interaction sweep: which controls do nothing when you use them, and which overlays
never hand focus back.

Run:  python3 interaction_report.py qa/manual-tests/interactions.json
      python3 interaction_report.py --schema
      python3 interaction_report.py --check-collector
      python3 interaction_report.py --selftest

WHY (#105, criterion 4 — "inventories interactive elements, exercises each distinct type, and flags
dead controls + missing focus restore"). Everything nearby judges a control by how it **looks**:
`icon-only-unnamed` wants a name, `focus-ring-missing` wants a focus style,
`aria-controls-no-expanded` wants the state attribute. A control can satisfy all three and **still
do nothing when clicked** — a button whose handler never bound because its Stimulus controller
failed to register, or whose target selector no longer matches. It is named, focusable, correctly
marked up, and inert.

THE SECOND HALF OF THAT CRITERION IS FOCUS RESTORE, and it had no mechanical owner. `a11y-auditor`
walks overlays and reports `Restore Failures` in a CSV, and `validate_evidence.py`'s keyboard
profile gates that CSV's arithmetic — but the number in the column is the agent's own claim, and
nothing compares it to the browser. This is the measurement: the collector opens the layer, presses
Escape, and asks the DOM whether `document.activeElement` is the trigger element itself.

WHICH OVERLAYS THAT RULE MAY FIRE ON IS THE WHOLE DESIGN, and it is narrower than the issue asked
for. Verified against the live WAI-ARIA APG (2026-08-01):

  * Dialog (Modal) — REQUIRED. "Escape: Closes the dialog." and "When a dialog closes, focus returns
    to the element that invoked the dialog."
  * Menu / Menu Button — REQUIRED. "Escape: Close the menu that contains focus and return focus to
    the element or context, e.g., menu button or parent menuitem, from which the menu was opened."
  * Combobox popups — REQUIRED. "Escape: Closes the popup and returns focus to the combobox."
  * **Disclosure (the base pattern) — NOT required. Its Keyboard Interaction table has no Escape row
    at all.** A standalone Listbox does not mention Escape either.

So a rule keyed on `aria-expanded` — which is what the issue text implies — would fire on every
ordinary FAQ accordion and every listbox on the internet, against APG's own spec. Those are
measured, reported OUT OF SCOPE by name, and never counted as findings. The narrow set is the
reason this rule is usable at all.

Exclusions differ from `dead-control` on purpose: a link with an `href` is exempt there because
navigation cannot be observed from a sweep that stays on the page, but its focus restore *can* be —
so the dismissal is judged even for controls `dead-control` skips.

THE THIRD HALF IS FOCUS CONTAINMENT, and it had the same problem one layer along. #114's overlay
criterion is three assertions — *"(a) Tab cycles within the layer, (b) Escape closes it, (c) focus
returns to the trigger"* — and (b) and (c) became mechanical above while (a) stayed a number an
agent types into the `Trap Failures` column of a CSV. `validate_evidence.py` checks that number's
arithmetic; nothing has ever compared it to a browser. So the collector now walks Tab and Shift+Tab
from inside the layer and records whether focus ever lands on a real element outside it.

WHERE THAT RULE MAY FIRE IS NARROWER THAN THE COLUMN, and the scope note has to be worded carefully,
because the obvious wording is false. Verified against the live APG (2026-08-02):

  * **Dialog (Modal) — REQUIRED, and it is the only formal mandate.** "Tab: ... If focus is on the
    last tabbable element inside the dialog, moves focus to the first tabbable element inside the
    dialog", and the mirror-image row for Shift + Tab.
  * **Menu / Menu Button — NOT containment.** The opposite, in fact: "Tab: ... move focus out of the
    `menu` or `menubar`, and close all menus and submenus", and "Tab and Shift + Tab do not move
    focus among the items in the menu."
  * **Combobox — NOT containment.** "DOM Focus is maintained on the combobox and the assistive
    technology focus is moved within the listbox using `aria-activedescendant`", and the popup and
    its descendants are "excluded from the page Tab sequence". (A combobox whose popup is itself a
    dialog is APG's own stated exception; it is not special-cased here because the dialog it opens
    is judged on its own merits.)
  * **Disclosure — nothing.** Its Keyboard Interaction table is Enter and Space and no more.

That matters beyond this file: `Overlays` in the keyboard CSV is the denominator for `Escape
Failures` and `Restore Failures` — which APG *does* mandate for all three patterns — but it is the
wrong denominator for `Trap Failures`, which only the dialog owes. a11y-auditor.md said all three
applied to all three patterns, and that was wrong in the direction that files S1s against behaviour
APG explicitly describes the other way.

**WHAT AN OUT-OF-SCOPE VERDICT HERE MEANS IS "NOT CHECKED", NOT "EXEMPT"** — the distinction is the
verification's most useful output. It is tempting to write "APG exempts non-modal dialogs from
containment"; APG says the reverse, in the Dialog (Modal) pattern's own About section: *"Like
non-modal dialogs, modal dialogs contain their tab sequence."* There is simply no APG pattern page
for a non-modal dialog and no platform state that marks one, so there is nothing to check it
against. Scoping to runtime modality is a statement about what is **measurable**, not a claim that
the rest is permitted.

MODALITY IS READ FROM THE RUNTIME, NEVER FROM THE MARKUP'S INTENT: `:modal` (true only for a
`<dialog>` opened with `showModal()` — the HTML Standard's "is modal" flag, which `show()` never
sets) or `aria-modal="true"`. And APG mandates the *behaviour*, not the mechanism — it never
mentions traps, `showModal`, or JS at all — so pressing Tab and watching where focus lands is a
valid test whichever way containment was implemented. A native modal usually passes for free,
because the HTML Standard makes everything outside the top dialog `inert`.

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
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "qa-flow/interaction-sweep/1"

# Any one of these means the control did something. Kept broad on purpose: see the docstring.
EFFECT_KEYS = ("domChanged", "navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")

# The overlay kinds APG actually mandates Escape-closes-and-returns-focus for. Anything else the
# collector measured is reported out of scope, never as a finding: see the docstring for the quoted
# APG text, and for why `aria-expanded` alone is the wrong discriminator.
RESTORE_REQUIRED = ("dialog", "menu", "combobox")

# The document a collector must produce. ONE definition, printed by `--schema` and cross-checked
# against the shipped collector by the selftest: separate files in separate languages drift, and a
# collector that quietly stops emitting a field makes the rule reading it go silent rather than fail.
SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "controls": [{
        "ref": "main > button.filter", "tag": "button", "role": "", "name": "Filter",
        "disabled": False, "href": None, "exercised": True, "reason": None,
        "constraintBlocked": False,
        "effects": {k: False for k in EFFECT_KEYS},
        # null unless activating this control opened a layer. RAW attributes, never a
        # classification: which kind of popup this is decides whether APG mandates anything, and
        # that decision belongs here, where a fixture can reach it.
        "dismiss": {
            "dialogOpened": True, "haspopup": None, "triggerRole": "", "popupRole": None,
            "closedOnEscape": True, "focusRestored": False,
        },
        # null unless a layer opened. RAW again: `ariaModal` is the attribute STRING and
        # `nativeModal` the `:modal` match, because "is this modal" is the judged question.
        "containment": {
            "containerFound": True, "containerRole": "dialog", "ariaModal": "true",
            "nativeModal": False, "tabbables": 4, "tabsPressed": 5,
            "forwardEscaped": True, "backwardEscaped": False,
        },
        "consoleAfter": [{"level": "error", "text": "..."}],
    }],
}
# Sub-fields of `dismiss`, cross-checked against the collector separately: the top-level check only
# proves the key exists, and an empty `dismiss` object would satisfy it while the rule went quiet.
DISMISS_KEYS = ("dialogOpened", "haspopup", "triggerRole", "popupRole",
                "closedOnEscape", "focusRestored")
# Same argument, same reason, for the containment probe.
CONTAINMENT_KEYS = ("containerFound", "containerRole", "ariaModal", "nativeModal",
                    "tabbables", "tabsPressed", "forwardEscaped", "backwardEscaped")
COLLECTOR = "crawl_collector.js"


class Unusable(RuntimeError):
    """The sweep cannot be judged -- reported, never treated as a clean sweep."""


MAX_EXAMPLES = 3


def _grouped(findings):
    """[( (rule, detail), [ref, ...] ), ...] in first-seen order, refs de-duplicated.

    #108 item J. A defect in a SHARED LAYOUT is found once per page, so one line per finding
    reports a single broken control 72 times. `ref` here is `"<route> <selector>"`, so the
    refs differ even when the defect does not — grouping is on `(rule, detail)`, which is the
    part that is genuinely the same. Details carrying per-instance counts therefore do not
    group, and that is correct: it never merges two defects to make a shorter report.

    Deliberately duplicated across the judges rather than extracted. They are standalone by
    design — an agent runs one file — and a shared module would trade that for ten lines.
    """
    out: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        refs = out.setdefault((f.rule, f.detail), [])
        if f.ref not in refs:
            refs.append(f.ref)
    return list(out.items())


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
    # Layers opened but not judged, each for a DIFFERENT reason, kept apart on purpose. One is
    # "APG asks nothing here"; the other is "the probe did not run". Folding them together would
    # let a browser that never answered look like a pattern with no requirement.
    dismiss_out_of_scope: list[str] = field(default_factory=list)
    dismiss_unjudged: list[str] = field(default_factory=list)
    dismiss_judged: int = 0
    # The same three-way split for containment, and for the same reason. `containment_judged` is
    # the DENOMINATOR: "0 findings" over 0 walked layers is the vacuous pass, and without a counter
    # printed beside it there is nothing to tell the two apart.
    containment_out_of_scope: list[str] = field(default_factory=list)
    containment_unjudged: list[str] = field(default_factory=list)
    containment_judged: int = 0


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
    if control.get("constraintBlocked"):
        # #357. A submit inside a form with an unfilled `required` field fires no request because
        # the browser blocked it -- doing nothing is CORRECT, exactly like a disabled control.
        # Reported from a real app: every sign-in, sign-up and validated form false-positived, and
        # the buttons all worked. A rule that fires on the most common form on the internet is a
        # rule switched off within a day, which would have cost every genuine dead control too.
        return "submit blocked by native constraint validation — the form is invalid, so no action is correct"
    if control.get("tag") == "a" and control.get("href"):
        # Navigation is the effect. A sweep that stays on the page cannot observe it, and flagging
        # it would put every link on the site in the report.
        return "link with href — navigation is its effect and is not observed here"
    return None


def layer_kind(dismiss: dict) -> str:
    """Which APG pattern the opened layer is, from the collector's RAW attributes.

    Returns one of `RESTORE_REQUIRED`, or `"disclosure"` for everything APG mandates nothing for.
    That last bucket is deliberately the default: an unrecognised widget must fall into "no
    requirement" rather than into "must restore focus", because the failure direction that matters
    is the false positive. A standalone listbox lands here too -- APG's Listbox pattern does not
    mention Escape at all, so a button that opens one owes nothing on dismissal.
    """
    if dismiss.get("dialogOpened"):
        return "dialog"
    haspopup = str(dismiss.get("haspopup") or "").strip().lower()
    popup_role = str(dismiss.get("popupRole") or "").strip().lower()
    trigger_role = str(dismiss.get("triggerRole") or "").strip().lower()
    if haspopup == "menu" or popup_role == "menu":
        return "menu"
    # The TRIGGER must be the combobox. A plain button that controls a listbox is a standalone
    # listbox, which APG exempts -- keying off the popup's role alone would pull it back in.
    if trigger_role == "combobox":
        return "combobox"
    return "disclosure"


def judge_dismissal(result: Judged, ref: str, control: dict) -> None:
    """Judge the Escape probe for one control. Silent when no layer opened."""
    dismiss = control.get("dismiss")
    if not isinstance(dismiss, dict) or not dismiss:
        return
    kind = layer_kind(dismiss)
    if kind not in RESTORE_REQUIRED:
        result.dismiss_out_of_scope.append(
            f"{ref}: {kind} — APG states no Escape/focus-return requirement for this pattern")
        return
    closed, restored = dismiss.get("closedOnEscape"), dismiss.get("focusRestored")
    if closed is None or restored is None:
        # The probe threw. Named, never silent, and never a pass: an overlay whose dismissal could
        # not be observed is exactly as unverified as a control that was never clicked.
        result.dismiss_unjudged.append(f"{ref}: {kind} — the dismissal probe did not complete")
        return
    result.dismiss_judged += 1
    if not closed:
        result.findings.append(Finding(
            ref, "focus-restore-missing",
            f"{kind} stayed open on Escape, so focus never returned to the trigger"))
    elif not restored:
        result.findings.append(Finding(
            ref, "focus-restore-missing",
            f"{kind} closed on Escape but focus did not return to the trigger"))


def is_modal(containment: dict) -> bool:
    """Is this layer modal AT RUNTIME? The only two facts the platform actually exposes.

    `:modal` is true only for a `<dialog>` opened with `showModal()`; `show()` never sets the HTML
    Standard's "is modal" flag, so a `show()`-opened dialog is correctly not modal here. Anything
    else is read from `aria-modal`, whose DEFAULT IS FALSE -- so absent, `""` and `"false"` are all
    not-modal, exactly as with `aria-invalid` elsewhere in this plugin. A check that merely found
    the attribute would call every dialog modal.
    """
    if containment.get("nativeModal") is True:
        return True
    return str(containment.get("ariaModal") or "").strip().lower() == "true"


def judge_containment(result: Judged, ref: str, control: dict) -> None:
    """Judge the Tab walk for one control. Silent when no layer opened."""
    containment = control.get("containment")
    if not isinstance(containment, dict) or not containment:
        return
    if not containment.get("containerFound"):
        # Two very different causes, kept apart. A disclosure genuinely has no dialog; a dialog
        # that opened without moving focus into itself is a DIFFERENT defect (initial focus
        # placement, which has no rule here yet) and calling it a containment pass would be a lie.
        if (control.get("dismiss") or {}).get("dialogOpened"):
            result.containment_unjudged.append(
                f"{ref}: a dialog opened but focus was not inside it, so the walk had nowhere to "
                "start -- unmeasured, and NOT a contained layer")
        else:
            result.containment_out_of_scope.append(
                f"{ref}: no dialog container -- APG specifies Tab containment for its Dialog "
                "pattern, and states the opposite for menus and comboboxes")
        return

    kind = containment.get("containerRole") or "(no role)"
    if not is_modal(containment):
        result.containment_out_of_scope.append(
            f"{ref}: {kind} is not modal at runtime (aria-modal="
            f"{containment.get('ariaModal')!r}, :modal={containment.get('nativeModal')!r}) -- "
            "NOT CHECKED rather than exempt: APG has no non-modal dialog pattern to check against")
        return
    if not containment.get("tabbables"):
        # There is no cycle to walk. Tab from a modal holding no tabbable element leaves by
        # definition, and firing here would report the emptiest overlays as the most broken.
        result.containment_unjudged.append(
            f"{ref}: modal {kind} has no tabbable element inside it, so there is no tab sequence "
            "to contain")
        return

    forward, backward = containment.get("forwardEscaped"), containment.get("backwardEscaped")
    if forward is None or backward is None:
        result.containment_unjudged.append(f"{ref}: modal {kind} -- the containment walk did not "
                                           "complete")
        return
    result.containment_judged += 1
    leaked = [name for name, escaped in (("Tab", forward), ("Shift+Tab", backward)) if escaped]
    if leaked:
        # ONE finding per layer however many directions leaked: an overlay cannot fail the same
        # assertion twice, which is the rule `validate_evidence.py` applies to the same column.
        result.findings.append(Finding(
            ref, "focus-not-contained",
            f"modal {kind}: {' and '.join(leaked)} moved focus to an element outside the layer "
            f"({containment.get('tabsPressed')} press(es) over "
            f"{containment.get('tabbables')} tabbable element(s) inside)"))


def judge(controls: list[dict]) -> Judged:
    result = Judged()
    for control in controls:
        ref = str(control.get("ref", "<unknown>"))
        if not control.get("exercised", False):
            result.not_exercised.append(f"{ref}: {control.get('reason') or 'not activated'}")
            continue
        # BEFORE the exclusions, deliberately. They exempt a control from `dead-control` because its
        # effect is unobservable here -- a link's navigation. A link that opens a dialog has an
        # entirely observable dismissal, and exempting it would lose the overlays most worth
        # checking.
        judge_dismissal(result, ref, control)
        judge_containment(result, ref, control)
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


def node_check_module(node_bin: str, source: bytes) -> tuple[int, str]:
    """`node --check` in MODULE mode, which is the only mode that can fail on this collector.

    `node --check <path>` on a file containing `import` exits **0 even when the file has a blatant
    syntax error** (verified on Node 24: `import x from "y"; const = ;` passes). It is detected as
    ESM and the check silently does nothing. A gate written the obvious way would therefore be a
    gate that cannot fail — so the source goes in on **stdin** with `--input-type=module`, which is
    the only combination Node accepts for an explicit module-mode check.

    Returns (returncode, stderr) so the selftest can drive this exact path with broken input.
    """
    import subprocess
    proc = subprocess.run([node_bin, "--input-type=module", "--check"],
                          input=source, capture_output=True, timeout=60)
    return proc.returncode, proc.stderr.decode("utf-8", "replace")


def check_collector(node_bin: str = "node") -> int:
    """Syntax-check the shipped collector — the one file here no other gate reads.

    `lint_markdown_code.py` only sees JS inside markdown fences, and this is a real `.js` file we
    hand to a user's `node`. Mirrors design-flow's `rendered_conformance.py --check-collector`,
    except that this collector is ESM and therefore needs the module-mode path above.

    A missing `node` prints a SKIP and exits 0: a gate that fails for want of a binary teaches
    people to ignore gates. The skip is printed, never silent.
    """
    import shutil
    collector = Path(__file__).with_name(COLLECTOR)
    if not collector.is_file():
        print(f"interaction_report: collector missing at {collector} — /qa-flow:crawl points at "
              f"it, so this is a packaging fault, not a syntax verdict.", file=sys.stderr)
        return 2
    if shutil.which(node_bin) is None:
        print(f"  skip:  collector syntax ({COLLECTOR}) — `{node_bin}` is not on PATH, so the "
              f"check did NOT run. That is not a pass.")
        # Exit 3, not 0 (#829): the doctor maps 0 to PASS; 3 renders as SKIP with this reason.
        return 3
    rc, err = node_check_module(node_bin, collector.read_bytes())
    if rc != 0:
        print(f"{COLLECTOR} does not parse as an ES module:\n{err}", file=sys.stderr)
        return 1
    print(f"  ok:    collector syntax ({COLLECTOR}) parses as an ES module")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge an interaction sweep.")
    ap.add_argument("sweep", nargs="?", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--check-collector", action="store_true",
                    help="syntax-check the shipped browser collector (module mode) and exit")
    ap.add_argument("--node-bin", default="node", metavar="BIN",
                    help="node executable for --check-collector (the selftest points this at a "
                         "nonexistent binary to prove the skip path is a skip)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.check_collector:
        return check_collector(args.node_bin)
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if not args.sweep:
        ap.error("a sweep file is required (or --schema / --check-collector / --selftest)")
    try:
        result = judge(load(args.sweep))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"exercised": result.exercised, "excluded": result.excluded,
                          "notExercised": result.not_exercised,
                          "dismissJudged": result.dismiss_judged,
                          "dismissOutOfScope": result.dismiss_out_of_scope,
                          "dismissUnjudged": result.dismiss_unjudged,
                          "containmentJudged": result.containment_judged,
                          "containmentOutOfScope": result.containment_out_of_scope,
                          "containmentUnjudged": result.containment_unjudged,
                          "findings": [f.__dict__ for f in result.findings]}, indent=2))
    else:
        for (rule, detail), refs in _grouped(result.findings):
            if len(refs) == 1:
                print(f"  [{rule}] {refs[0]}\n      {detail}")
            else:
                print(f"  [{rule}] {len(refs)} occurrence(s), e.g. "
                      f"{', '.join(refs[:MAX_EXAMPLES])}\n      {detail}")
        for s in result.not_exercised:
            print(f"  [not exercised] {s}")
        for s in result.dismiss_out_of_scope:
            print(f"  [dismissal out of scope] {s}")
        for s in result.dismiss_unjudged:
            print(f"  [dismissal not judged] {s}")
        for s in result.containment_out_of_scope:
            print(f"  [containment out of scope] {s}")
        for s in result.containment_unjudged:
            print(f"  [containment not judged] {s}")
        print(f"\n{result.exercised} control(s) exercised, {len(result.findings)} finding(s), "
              f"{result.excluded} excluded by rule, {len(result.not_exercised)} not exercised.")
        print(f"{result.dismiss_judged} overlay dismissal(s) judged, "
              f"{len(result.dismiss_out_of_scope)} out of scope, "
              f"{len(result.dismiss_unjudged)} not judged.")
        # Printed unconditionally, at zero as loudly as at fifty: a containment rule reporting no
        # findings over no walked layers reads exactly like a clean app unless the denominator is
        # on the page next to it.
        print(f"{result.containment_judged} modal layer(s) walked for focus containment, "
              f"{len(result.containment_out_of_scope)} out of scope, "
              f"{len(result.containment_unjudged)} not judged.")
        if result.not_exercised:
            print("A control that was never activated is NOT a working control.")
        if result.dismiss_unjudged:
            print("An overlay whose dismissal could not be observed is NOT a passing overlay.")
        if result.containment_unjudged:
            print("A layer whose tab sequence could not be walked is NOT a contained layer.")
        if result.containment_judged == 0:
            print("NO modal layer was walked. Zero containment findings here is a statement about "
                  "the sweep, not about the app.")
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
    # #357, reported from a real app: a submit inside a form with an unfilled `required` field.
    check("a submit blocked by constraint validation is not dead",
          rules(ctl(constraintBlocked=True)) == [], f"{rules(ctl(constraintBlocked=True))}")
    # NEAR MISS: the exclusion must need the FORM to be invalid. A submit in a VALID form that does
    # nothing is a genuine dead control, and excluding every submit would gut the rule.
    check("a submit in a VALID form is still judged",
          rules(ctl(constraintBlocked=False)) == ["dead-control"],
          "constraintBlocked=False must not exempt anything")

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

    # ---- FOCUS RESTORE (#105, criterion 4, second half) ---------------------------------------
    #
    # The scope fixtures below are the ones that matter. Every APG pattern this rule may fire on
    # was verified against the live spec; the two it may NOT fire on are fixtured just as hard,
    # because a rule that flags every accordion is a rule switched off in a day.
    def dis(**kw):
        base = {"dialogOpened": False, "haspopup": None, "triggerRole": "", "popupRole": None,
                "closedOnEscape": True, "focusRestored": True}
        base.update(kw)
        return base

    def working(**kw):
        """A control that DID something, so only the dismissal is under test."""
        return ctl(effects={**{k: False for k in EFFECT_KEYS}, "domChanged": True}, **kw)

    check("no layer opened means nothing to judge",
          rules(working()) == [], "a control that opened nothing must not be judged on dismissal")

    # IN SCOPE — the three APG mandates focus-return for.
    for kind, attrs in (("dialog", {"dialogOpened": True}),
                        ("menu", {"haspopup": "menu"}),
                        ("menu via the popup's role", {"popupRole": "menu"}),
                        ("combobox", {"triggerRole": "combobox"})):
        c = working(dismiss=dis(focusRestored=False, **attrs))
        check(f"a {kind} that keeps focus fires focus-restore-missing",
              rules(c) == ["focus-restore-missing"], f"{rules(c)}")
        ok = working(dismiss=dis(**attrs))
        check(f"a {kind} that restores focus is silent", rules(ok) == [], f"{rules(ok)}")

    # A layer that never closed cannot have restored focus. Same rule, different cause named.
    c = working(dismiss=dis(dialogOpened=True, closedOnEscape=False, focusRestored=False))
    check("a dialog that ignores Escape fires focus-restore-missing",
          rules(c) == ["focus-restore-missing"], f"{rules(c)}")
    check("and the detail names Escape as the cause",
          "stayed open on Escape" in judge([c]).findings[0].detail if judge([c]).findings else False)

    # OUT OF SCOPE — the negative half, and the reason this rule is usable. APG's base Disclosure
    # pattern has NO Escape row, and its Listbox pattern never mentions Escape.
    acc = working(dismiss=dis(focusRestored=False))
    check("an ordinary disclosure that keeps focus is NOT a finding",
          rules(acc) == [],
          "APG's Disclosure pattern mandates no Escape behaviour; firing here flags every accordion")
    check("and it is reported out of scope rather than silently dropped",
          len(judge([acc]).dismiss_out_of_scope) == 1, f"{judge([acc]).dismiss_out_of_scope}")
    lb = working(dismiss=dis(popupRole="listbox", focusRestored=False))
    check("a standalone listbox that keeps focus is NOT a finding",
          rules(lb) == [], "APG's Listbox pattern does not mention Escape at all")
    # NEAR MISS: the SAME popup role, but the trigger is a combobox. That one IS in scope.
    cb = working(dismiss=dis(popupRole="listbox", triggerRole="combobox", focusRestored=False))
    check("the same listbox popup under a combobox trigger IS judged",
          rules(cb) == ["focus-restore-missing"],
          "the trigger's role is the discriminator; without it the combobox case is lost")

    # AN UNRUN PROBE IS NOT A PASS.
    for label, attrs in (("focusRestored", {"focusRestored": None}),
                         ("closedOnEscape", {"closedOnEscape": None})):
        r = judge([working(dismiss=dis(dialogOpened=True, **attrs))])
        check(f"a probe with {label}=null is not judged clean",
              not r.findings and len(r.dismiss_unjudged) == 1, f"{r}")
        check(f"and a null {label} is not counted as judged", r.dismiss_judged == 0,
              f"{r.dismiss_judged}")

    # The exclusions must NOT reach the dismissal. A link's navigation is unobservable here; the
    # dialog it opened is entirely observable.
    link = ctl(tag="a", href="/next", effects={**{k: False for k in EFFECT_KEYS}, "domChanged": True},
               dismiss=dis(dialogOpened=True, focusRestored=False))
    check("a link with href is still judged on focus restore",
          rules(link) == ["focus-restore-missing"],
          "the href exclusion is about dead-control only; exempting it here loses real overlays")

    # An unexercised control never opened anything, so its dismissal must not be invented.
    r = judge([ctl(exercised=False, reason="obscured",
                   dismiss=dis(dialogOpened=True, focusRestored=False))])
    check("an unexercised control is not judged on dismissal",
          not r.findings and not r.dismiss_out_of_scope and not r.dismiss_unjudged, f"{r}")

    check("RESTORE_REQUIRED holds exactly the patterns APG mandates",
          tuple(RESTORE_REQUIRED) == ("dialog", "menu", "combobox"),
          f"{RESTORE_REQUIRED} — adding a pattern here needs a citation, not a guess")

    # ---- FOCUS CONTAINMENT (#114, overlay criterion (a)) --------------------------------------
    #
    # Every value in the IN-SCOPE and OUT-OF-SCOPE fixtures below was MEASURED by running the
    # shipped collector against a six-case page in headless Chromium, not reasoned about. Two of
    # them are the reason the collector looks the way it does, and both would have shipped as
    # false positives on the commonest correct implementations:
    #
    #   * a `showModal()` dialog with two buttons cycles `one -> two -> BODY -> one` in Chromium,
    #     so `document.body` had to stop counting as an escape;
    #   * a `role="dialog"` div that lives in the DOM and is revealed by toggling `hidden` never
    #     changed the collector's dialog count, so the probe never ran on the shape every component
    #     library ships.
    def con(**kw):
        base = {"containerFound": True, "containerRole": "dialog", "ariaModal": "true",
                "nativeModal": False, "tabbables": 3, "tabsPressed": 4,
                "forwardEscaped": False, "backwardEscaped": False}
        base.update(kw)
        return base

    check("no layer opened means no containment verdict",
          rules(working()) == [] and judge([working()]).containment_judged == 0,
          "a control that opened nothing must not be walked")

    # IN SCOPE — the one pattern APG mandates containment for, reached both ways.
    for label, attrs in (("aria-modal=\"true\"", {"ariaModal": "true", "nativeModal": False}),
                         ("a native showModal() dialog", {"ariaModal": None, "nativeModal": True})):
        leaky = working(containment=con(forwardEscaped=True, **attrs))
        check(f"a modal declared by {label} that leaks Tab fires focus-not-contained",
              rules(leaky) == ["focus-not-contained"], f"{rules(leaky)}")
        tight = working(containment=con(**attrs))
        check(f"a modal declared by {label} that contains Tab is silent",
              rules(tight) == [], f"{rules(tight)}")
        check(f"and the contained {label} counts toward the denominator",
              judge([tight]).containment_judged == 1, f"{judge([tight]).containment_judged}")

    back_only = working(containment=con(backwardEscaped=True))
    check("Shift+Tab alone leaking is still a finding",
          rules(back_only) == ["focus-not-contained"],
          "APG mandates the wrap in BOTH directions; checking Tab only halves the rule")
    # Guarded, never indexed blindly. When the direction pair is broken this list is EMPTY, and an
    # IndexError aborts the run before any labelled assertion reports -- which the mutation checker
    # refuses to count as a catch, correctly. The same footgun the not-exercised fixture hit above.
    back_detail = next((f.detail for f in judge([back_only]).findings), "")
    check("and the detail names the direction that leaked",
          "Shift+Tab" in back_detail and "Tab and" not in back_detail, f"{back_detail!r}")
    both = working(containment=con(forwardEscaped=True, backwardEscaped=True))
    check("a layer leaking BOTH ways is ONE finding, not two",
          rules(both) == ["focus-not-contained"],
          "an overlay cannot fail the same assertion twice — the rule validate_evidence applies "
          "to this very column")

    # OUT OF SCOPE — the half that decides whether this rule is usable at all. Menus and comboboxes
    # are not merely unmentioned by APG: it specifies the OPPOSITE behaviour for both.
    for label, attrs in (("a non-modal role=dialog (aria-modal absent)", {"ariaModal": None}),
                         ('aria-modal=""', {"ariaModal": ""}),
                         ('aria-modal="false"', {"ariaModal": "false"}),
                         ("a native dialog opened with show(), not showModal()",
                          {"ariaModal": None, "nativeModal": False})):
        c = working(containment=con(forwardEscaped=True, backwardEscaped=True, **attrs))
        check(f"{label} that leaks Tab is NOT a finding", rules(c) == [], f"{rules(c)}")
        check(f"and {label} is reported out of scope rather than silently dropped",
              len(judge([c]).containment_out_of_scope) == 1,
              f"{judge([c]).containment_out_of_scope}")
        check(f"and {label} is NOT counted as judged",
              judge([c]).containment_judged == 0, f"{judge([c]).containment_judged}")
    # The out-of-scope wording is load-bearing: APG's Dialog (Modal) About section says non-modal
    # dialogs contain their tab sequence TOO, so "exempt" would be a false claim about the spec.
    nm = next(iter(judge([working(containment=con(ariaModal=None, forwardEscaped=True))])
                   .containment_out_of_scope), "")
    check("an out-of-scope layer says NOT CHECKED, never that APG exempts it",
          "NOT CHECKED" in nm and "exempt" not in nm.replace("rather than exempt", ""),
          f"{nm!r}")

    # No container at all: a disclosure owes nothing, and it must not read as a walked layer.
    disc = working(containment=con(containerFound=False, containerRole=None, ariaModal=None,
                                   nativeModal=None, tabbables=None, tabsPressed=0,
                                   forwardEscaped=None, backwardEscaped=None))
    check("a disclosure with no dialog container is not a finding", rules(disc) == [], f"{rules(disc)}")
    check("and it is out of scope, not unjudged",
          len(judge([disc]).containment_out_of_scope) == 1
          and not judge([disc]).containment_unjudged, f"{judge([disc])}")

    # A DIALOG THAT OPENED BUT NEVER TOOK FOCUS is a different defect, and must not be laundered
    # into either verdict. It is unmeasured, and it is named.
    nofocus = working(
        dismiss=dis(dialogOpened=True),
        containment=con(containerFound=False, containerRole=None, ariaModal=None, nativeModal=None,
                        tabbables=None, tabsPressed=0, forwardEscaped=None, backwardEscaped=None))
    r = judge([nofocus])
    check("a dialog that opened without taking focus is not judged contained",
          not [f for f in r.findings if f.rule == "focus-not-contained"]
          and len(r.containment_unjudged) == 1, f"{r.containment_unjudged}")
    check("and it is not counted as judged", r.containment_judged == 0, f"{r.containment_judged}")

    # AN UNRUN WALK IS NOT A PASS — same contract as the dismissal probe.
    for label, attrs in (("forwardEscaped", {"forwardEscaped": None}),
                         ("backwardEscaped", {"backwardEscaped": None})):
        r = judge([working(containment=con(**attrs))])
        check(f"a walk with {label}=null is not judged clean",
              not r.findings and len(r.containment_unjudged) == 1, f"{r}")
        check(f"and a null {label} is not counted as judged",
              r.containment_judged == 0, f"{r.containment_judged}")

    # A modal holding nothing tabbable has no cycle to walk, and Tab leaves it by definition.
    # Firing here would report the emptiest overlays as the most broken.
    r = judge([working(containment=con(tabbables=0, forwardEscaped=True, backwardEscaped=True))])
    check("a modal with no tabbable element inside is not a containment finding",
          not r.findings and len(r.containment_unjudged) == 1, f"{r}")

    # An unexercised control opened nothing, so its walk must not be invented.
    r = judge([ctl(exercised=False, reason="obscured", containment=con(forwardEscaped=True))])
    check("an unexercised control is not walked",
          not r.findings and not r.containment_out_of_scope and not r.containment_unjudged, f"{r}")

    # The exclusions must not reach the walk either, for the reason they do not reach the
    # dismissal: a link that opens a modal is one of the overlays most worth checking.
    link = ctl(tag="a", href="/next", effects={**{k: False for k in EFFECT_KEYS}, "domChanged": True},
               containment=con(forwardEscaped=True))
    check("a link with href is still walked for containment",
          rules(link) == ["focus-not-contained"], f"{rules(link)}")

    check("is_modal reads aria-modal by VALUE, not by presence",
          is_modal({"ariaModal": "true"}) and not is_modal({"ariaModal": "false"})
          and not is_modal({"ariaModal": ""}) and not is_modal({"ariaModal": None}),
          "aria-modal defaults to false; a presence check would call every dialog modal")
    check("is_modal treats :modal as authoritative on its own",
          is_modal({"nativeModal": True, "ariaModal": None})
          and not is_modal({"nativeModal": False, "ariaModal": None}),
          "showModal() sets the HTML Standard's `is modal` flag; show() never does")

    check("a console error on activate fires",
          "error-on-activate" in rules(ctl(effects={**{k: False for k in EFFECT_KEYS},
                                                    "domChanged": True},
                                           consoleAfter=[{"level": "error", "text": "boom"}])))
    check("a console warning on activate stays silent",
          rules(ctl(effects={**{k: False for k in EFFECT_KEYS}, "domChanged": True},
                    consoleAfter=[{"level": "warning", "text": "meh"}])) == [])

    # THE COLLECTOR MUST EMIT EVERY FIELD THIS SCHEMA DECLARES. Object shorthand counts.
    collector = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", collector.is_file(), f"{collector} is missing")
    if collector.is_file():
        js = collector.read_text(encoding="utf-8")
        missing = [f for f in SCHEMA_EXAMPLE["controls"][0]
                   if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing,
              f"{COLLECTOR} never emits {missing} — the rule reading it would go quiet")
        for key in EFFECT_KEYS:
            # `[,:]`, matching the field check above: `{ requested }` is shorthand for
            # `requested: requested`, and requiring a colon reported a false positive on it.
            check(f"the collector measures {key}", re.search(rf"(?m)^\s*{key}\s*[,:]", js) is not None,
                  f"{COLLECTOR} never sets {key}, so that effect can never be observed")
        # The `dismiss` sub-fields need their own check: the top-level one above only proves the
        # key exists, and a collector emitting `dismiss: {}` would satisfy it while every overlay
        # silently fell out of scope -- the rule going quiet rather than failing.
        for key in DISMISS_KEYS:
            check(f"the collector measures dismiss.{key}",
                  re.search(rf"(?m)^\s*{key}\s*[,:]", js) is not None,
                  f"{COLLECTOR} never sets {key}; without it the focus-restore rule cannot fire")
        for key in CONTAINMENT_KEYS:
            check(f"the collector measures containment.{key}",
                  re.search(rf"(?m)^\s*{key}\s*[,:]", js) is not None,
                  f"{COLLECTOR} never sets {key}; without it the containment rule cannot fire")
        # THE TRIGGER-CONDITION REGRESSION, pinned. Counting dialogs by PRESENCE instead of
        # visibility is what kept the whole overlay probe off the shape every component library
        # ships -- a `role="dialog"` div toggled by `hidden`. It reads as a harmless selector and
        # silently empties both rules, so the fix is asserted here rather than trusted to memory.
        check("the collector counts open overlays by VISIBILITY, not by presence",
              "checkVisibility" in js,
              f"{COLLECTOR} is back to counting dialogs that merely exist, so a hidden-toggled "
              "modal never registers as opened and no overlay rule ever runs on it")
        check("and the overlay selector includes alertdialog",
              'role="alertdialog"' in js,
              "every confirm-before-delete overlay is an alertdialog; omitting it exempts them")
        check("the containment walk does not treat document.body as an escape",
              "document.body" in js and "documentElement" in js,
              "Chromium parks focus on BODY at a native modal's wrap point, so without this every "
              "correct showModal() dialog reports a containment failure")

    # ---- THE COLLECTOR SYNTAX GATE MUST BE ABLE TO FAIL ----------------------------------------
    #
    # This is the negative test for `--check-collector`, and it is not ceremony: the obvious
    # implementation (`node --check <path>`) exits 0 on a broken ESM file, so the gate would have
    # passed on anything at all. The fixture drives the real code path with real broken input.
    import shutil as _shutil
    if _shutil.which("node") is None:
        # NOT counted as passed (#829): a skipped fixture that increments the pass tally is the
        # "35 checks passed on a machine with no corpora" shape. The skip is printed and that is all.
        print("  skip:  node is absent, so the collector syntax fixtures did NOT run — not a pass.",
              file=sys.stderr)
    else:
        rc_bad, _ = node_check_module("node", b'import x from "y";\nawait 1;\nconst = ;\n')
        check("the module-mode check FAILS on a broken ES module", rc_bad != 0,
              "node --input-type=module --check accepted invalid syntax; the gate cannot fail")
        rc_ok, err_ok = node_check_module("node", b'import x from "y";\nawait 1;\nconst a = 1;\n')
        check("and stays silent on a valid ES module", rc_ok == 0, err_ok)
        check("the shipped collector passes it", check_collector("node") == 0)
    # == 3, not == 0 (#829). This fixture used to assert 0 -- pinning the very defect: the doctor maps
    # 0 to PASS, so "skip, not a pass" printed and a pass was recorded. 3 is the protocol's SKIP.
    check("a missing node is a SKIP, not a failure",
          check_collector("node-that-does-not-exist") == 3,
          "a gate that fails for want of a binary teaches people to ignore gates")

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

    # ---- #108 item J: collapse a shared-layout defect, never merge two distinct ones -------
    G = Finding
    shared = [G("/a nav>a", "RULE", "DETAIL"), G("/b nav>a", "RULE", "DETAIL"),
              G("/c nav>a", "RULE", "DETAIL")]
    check("one defect across three pages collapses to one group", len(_grouped(shared)) == 1,
          f"{_grouped(shared)}")
    check("the group keeps every ref",
          _grouped(shared)[0][1] == ["/a nav>a", "/b nav>a", "/c nav>a"], f"{_grouped(shared)}")
    # THE FAILURE THAT WOULD MATTER: a shorter report that hid a defect.
    two = [G("/a x", "RULE", "DETAIL"), G("/b x", "RULE", "OTHER DETAIL")]
    check("same rule, different detail stays two groups", len(_grouped(two)) == 2, f"{_grouped(two)}")
    two_rules = [G("/a x", "RULE", "DETAIL"), G("/a x", "OTHER RULE", "DETAIL")]
    check("same detail, different rule stays two groups", len(_grouped(two_rules)) == 2,
          f"{_grouped(two_rules)}")
    dup = [G("/a x", "RULE", "DETAIL"), G("/a x", "RULE", "DETAIL")]
    check("a repeated ref is counted once", _grouped(dup)[0][1] == ["/a x"], f"{_grouped(dup)}")
    check("no findings groups to nothing", _grouped([]) == [], f"{_grouped([])}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"interaction_report selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
