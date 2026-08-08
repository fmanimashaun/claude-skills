#!/usr/bin/env python3
"""Choose ONE next action from repository state, and say whether the agent may take it alone.

Pillar 2 of the autonomous flow driver (EPIC #488) — the decision engine. Pillars 1 and 3 already
ship: `toolchain_version.py` gates the start, `escalation.py` asks the human asynchronously. This is
the part that decides what to do next, every tick, without being told.

WHAT THIS DELIBERATELY DOES NOT DO. It does not re-implement circuit breakers. `breaker.py` in the
pipeline plugin already owns attempt caps, the no-progress detector, the four forbidden escapes, the
elapsed/blast-radius limits and the complete/partial/stopped verdict — all of #128's doctrine, with
its own selftest and mutations. Duplicating that here would create a second set of stop conditions
which could disagree with the first, and the failure mode of two disagreeing safety systems is that
whichever is more permissive wins. So a run-level stop is `breaker.py`'s answer and this script
refuses to proceed when the ledger says the run has stopped.

WHAT IT ADDS, because nothing else has it:

  1. THE NEXT ACTION. One command per tick, chosen from state: open issues -> fix; a roadmap item
     with no branch -> feature; everything green and shippable -> the release path. One, not a menu
     — a driver that returns three options has moved the decision back to the human it exists to
     spare.

  2. THE DECISION-RIGHTS MATRIX, and it is CONFIGURABLE rather than a heuristic buried in an if.
     The EPIC names this as the hard part and it is right: over-asking kills autonomy, under-asking
     goes off-rails. The seed policy encodes the maintainer decision recorded on #488 —

       decide alone: which backlog item is next; implementation approach inside a frozen plan;
                     aesthetic and interface craft; filing bugs and upstream reports
       must escalate: product scope and user journeys; anything irreversible; the dev -> main
                     release; spend; a gate that cannot be satisfied without weakening it

     The test that makes this checkable rather than a vibe is "does it publish, or can it not be
     undone" — readable from the action itself, unlike "is this important".

  3. THE HONEST STOP. Four named stopping conditions, and the report distinguishes them. "Nothing to
     do" and "I was told to stop" and "I ran out of budget" are three different sentences, and a
     driver that prints the same one for all three has told the human nothing.

Exit codes:  0 an action was chosen (JSON on stdout) · 1 STOPPED, with the named condition
             2 unusable state or policy

Exit 1 is not a failure. A backlog that has been cleared is the goal, and a driver that exits
non-zero on success would be wired into CI as a permanent red. The `stop` field names which of the
four conditions fired; read that, not the code alone.

Stdlib only, no network. This script reads state and decides; it never runs the command it chooses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

POLICY_PATH = Path(".rails-flow/decision-rights.json")

# The seed matrix, recorded as the maintainer decision on #488. Config OVERRIDES this, but the
# default is not empty: an unconfigured driver that escalates nothing is more dangerous than one
# that escalates too much, so the shipped default is the cautious half.
DEFAULT_POLICY = {
    "decide": [
        "pick-next-backlog-item",
        "implementation-approach-within-frozen-plan",
        "aesthetic-and-interface-craft",
        "file-bug-or-upstream-report",
        "merge-feature-to-dev-on-green-gates",
    ],
    "escalate": [
        "product-scope-or-user-journey-change",
        "irreversible-or-destructive-action",
        "promote-dev-to-main",
        "increase-spend-or-budget",
        "requirement-the-brief-does-not-settle",
        "gate-unsatisfiable-without-weakening-it",
    ],
}

# Which right each action needs. Kept beside the actions rather than inferred from the name, because
# inferring it is exactly the "implicit heuristic" the EPIC rules out as a deliverable.
ACTION_RIGHTS = {
    "fix-issue": "pick-next-backlog-item",
    "build-feature": "product-scope-or-user-journey-change",
    "run-qa": "pick-next-backlog-item",
    "promote": "promote-dev-to-main",
}

STOP_CONDITIONS = ("backlog-empty", "needs-human", "budget-reached", "release-ready")


class Unusable(Exception):
    """The state cannot be judged — never report an action for it."""


def load_policy(root: Path) -> dict:
    path = root / POLICY_PATH
    if not path.is_file():
        return DEFAULT_POLICY
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Unusable(f"{path} is not valid JSON ({exc})")
    if not isinstance(loaded, dict) or not loaded.get("escalate"):
        raise Unusable(
            f"{path} declares no `escalate` list. A policy that escalates nothing is not a policy — "
            f"it is full autonomy with a config file in front of it. Delete the file to use the "
            f"shipped default, or state what must be asked.")
    return {"decide": loaded.get("decide", []),
            "escalate": loaded.get("escalate", [])}


def rights_for(action: str, policy: dict) -> str:
    """decide | escalate | unknown. An action in NEITHER list is `unknown`, and unknown escalates.

    Defaulting the unknown case to `decide` would mean every action nobody thought about is taken
    autonomously — the policy would grow permissive by omission, which is the failure mode a
    decision-rights matrix exists to prevent.
    """
    right = ACTION_RIGHTS.get(action)
    if right in policy.get("escalate", []):
        return "escalate"
    if right in policy.get("decide", []):
        return "decide"
    return "unknown"


def choose(state: dict, policy: dict) -> dict:
    """One action, or one named stop. Never a menu."""
    if state.get("run_stopped"):
        return {"stop": "needs-human",
                "why": "breaker.py reports the run has stopped; a stop is not something this "
                       "script may overrule — that is why it does not own the breaker."}
    if state.get("budget_exhausted"):
        return {"stop": "budget-reached",
                "why": "the run's token/turn budget is spent. Stopping here is the budget working."}
    if state.get("awaiting_human"):
        return {"stop": "needs-human",
                "why": f"parked on {state['awaiting_human']} awaiting a reply. Other independent "
                       f"work should have been taken first; if there is none, this is the stop."}

    open_issues = state.get("open_issues") or []
    if open_issues:
        return _action("fix-issue", policy, target=open_issues[0])
    if state.get("roadmap_items"):
        return _action("build-feature", policy, target=state["roadmap_items"][0])
    if state.get("unverified_work"):
        return _action("run-qa", policy, target="unverified work on dev")
    if state.get("shippable"):
        return _action("promote", policy, target="dev -> main")
    return {"stop": "backlog-empty",
            "why": "no open issues, no roadmap items, nothing unverified and nothing shippable."}


def _action(name: str, policy: dict, target: str) -> dict:
    right = rights_for(name, policy)
    out = {"action": name, "target": target, "rights": right}
    if right != "decide":
        out["escalate_because"] = (
            f"{name!r} needs the {ACTION_RIGHTS.get(name, 'unlisted')!r} right, which this policy "
            f"does not grant autonomously." if right == "escalate" else
            f"{name!r} is not classified by this policy. An unclassified action escalates — "
            f"defaulting it to 'decide' would let the policy grow permissive by omission.")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", help="path to a JSON state file, or - for stdin")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.state:
        print("nothing to decide: pass --state (or --selftest)", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args.state == "-" else Path(args.state).read_text(encoding="utf-8")
        state = json.loads(raw)
        policy = load_policy(Path.cwd())
    except (OSError, ValueError, Unusable) as exc:
        print(f"unusable: {exc}", file=sys.stderr)
        return 2

    decision = choose(state, policy)
    print(json.dumps(decision, indent=2))
    return 1 if "stop" in decision else 0


def selftest() -> int:
    checks, failures = 0, []

    def expect(label, state, key, want, policy=DEFAULT_POLICY):
        nonlocal checks
        checks += 1
        got = choose(state, policy).get(key)
        if got != want:
            failures.append(f"{label}: expected {key}={want!r}, got {got!r}")

    # THE ORDER MATTERS, and each earlier condition must win over the later ones. A driver that
    # picked up a new issue while the breaker said STOP would be overruling the safety system.
    expect("a stopped run stops, even with issues waiting",
           {"run_stopped": True, "open_issues": [1]}, "stop", "needs-human")
    expect("budget beats a full backlog",
           {"budget_exhausted": True, "open_issues": [1]}, "stop", "budget-reached")
    expect("a parked escalation beats a full backlog",
           {"awaiting_human": "#42", "open_issues": [1]}, "stop", "needs-human")

    # THE LADDER of work, cheapest signal first.
    expect("open issues -> fix", {"open_issues": [7]}, "action", "fix-issue")
    expect("...and it names the issue", {"open_issues": [7]}, "target", 7)
    expect("no issues, a roadmap -> feature",
           {"roadmap_items": ["search"]}, "action", "build-feature")
    expect("nothing to build, work unverified -> qa",
           {"unverified_work": True}, "action", "run-qa")
    expect("all green and shippable -> promote", {"shippable": True}, "action", "promote")
    expect("nothing at all", {}, "stop", "backlog-empty")

    # THE DECISION-RIGHTS MATRIX. The two that must never be autonomous.
    expect("fixing an issue is autonomous", {"open_issues": [7]}, "rights", "decide")
    expect("a feature is scope, so it escalates",
           {"roadmap_items": ["search"]}, "rights", "escalate")
    expect("promotion publishes, so it escalates", {"shippable": True}, "rights", "escalate")

    # UNKNOWN ESCALATES. Defaulting to `decide` would let the policy grow permissive by omission.
    checks += 1
    if rights_for("some-action-nobody-classified", DEFAULT_POLICY) != "unknown":
        failures.append("an unclassified action should be `unknown`, not silently decidable")
    checks += 1
    empty = {"decide": [], "escalate": ["promote-dev-to-main"]}
    if choose({"open_issues": [1]}, empty).get("rights") == "decide":
        failures.append("an action absent from BOTH lists must not be treated as decidable")

    # A POLICY THAT ESCALATES NOTHING IS REFUSED — it is full autonomy wearing a config file.
    import tempfile
    checks += 1
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".rails-flow").mkdir()
        (root / POLICY_PATH).write_text(json.dumps({"decide": ["everything"]}), encoding="utf-8")
        try:
            load_policy(root)
            failures.append("a policy with no `escalate` list should be refused")
        except Unusable:
            pass
    checks += 1
    with tempfile.TemporaryDirectory() as td:   # no file at all -> the cautious shipped default
        if load_policy(Path(td)) != DEFAULT_POLICY:
            failures.append("an absent policy file should fall back to the shipped default")

    # THE FOUR STOPS ARE DISTINCT. A driver printing one sentence for all of them says nothing.
    checks += 1
    seen = {choose(s, DEFAULT_POLICY).get("stop") for s in (
        {}, {"budget_exhausted": True}, {"awaiting_human": "#1"}, {"run_stopped": True})}
    if not {"backlog-empty", "budget-reached", "needs-human"} <= seen:
        failures.append(f"the stop conditions are not distinguishable: {seen}")
    checks += 1
    for cond in ("backlog-empty", "needs-human", "budget-reached"):
        if cond not in STOP_CONDITIONS:
            failures.append(f"{cond!r} is returned but not declared in STOP_CONDITIONS")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} next-action assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
