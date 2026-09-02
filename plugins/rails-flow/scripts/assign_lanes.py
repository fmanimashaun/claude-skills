#!/usr/bin/env python3
"""Assign non-overlapping worktree lanes so several agent sessions can share one repository. #661

WHAT THIS IS. `skills/parallel-session-lane` has always described the protocol for being one of N
sessions -- confirm your worktree, take one coherent slice, stay in your subtree. Nothing in this
marketplace ever put a session INTO that mode: a human opened N terminals and assigned lanes by
hand. We wrote the coordination rules and skipped the assignment.

WHAT THIS IS NOT, stated first because the borrowed design gets this wrong for us. `swarm-forge`
runs tmux panes and a handoff daemon, because its roles cannot see each other's state. Ours can:
`compose_state.py` already derives the driver's state FROM THE REPOSITORY and `docs/handoff/<slug>.md`
is already a committed, validated work order. Git is our handoff medium and it survives a reboot,
which a tmux session does not. A daemon here would re-solve a solved problem worse.

It also does not spawn sessions. It prepares worktrees and prints the exact command per lane. That
boundary is honest: creating a worktree is mechanical, and deciding when an agent starts is not.

WHY IT REFUSES OVERLAP. Two lanes that contain each other are not lanes -- they are two sessions
editing one tree with a protocol that believes otherwise, which is worse than no protocol because
each session's own diff review looks clean.

Exit 0 assigned · 1 refused (overlap, dirty tree, missing guard) · 2 unusable input.

Stdlib only, no network.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "hooks" / "scripts" / "guard-lane.sh"


class Refusal(Exception):
    """A refusal is a normal outcome and carries a reason the caller prints verbatim."""


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def normalise(lane: str) -> str:
    """A lane as a clean repo-relative subtree path."""
    return str(Path(lane.strip().rstrip("/")))


def check_no_overlap(lanes: list[str]) -> None:
    """Two lanes must not contain each other.

    This is the whole safety property. Overlapping lanes are two sessions editing one tree while the
    protocol -- and #660's guard -- believe otherwise, so each session's own diff review looks clean
    and the collision only surfaces at merge.
    """
    for i, a in enumerate(lanes):
        for b in lanes[i + 1:]:
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                raise Refusal(
                    f"lanes {a!r} and {b!r} overlap. Two sessions would edit one tree while the "
                    f"lane guard believes each is alone, so both diffs review clean and the "
                    f"collision surfaces at merge. Split them at a real boundary or run fewer "
                    f"sessions.")


def check_guard_present() -> None:
    """#660 must be in place before this exists. An advisory protocol is survivable while nobody can
    enter the mode; it is not once a launcher can put four sessions in it."""
    if not GUARD.is_file():
        raise Refusal(
            f"the lane guard is missing at {GUARD}. Assigning lanes "
            f"without it puts N sessions into a mode whose only rule is advice -- which is the one "
            f"ordering that must not happen.")


def budget_note(lanes: list[str], total_usd: float | None) -> str:
    """N sessions is N times the spend, and nothing else here meters it.

    Reported rather than enforced: this script cannot see a provider balance, and a cap it could not
    honour would be a promise nothing keeps. Naming the arithmetic is what it can honestly do.
    """
    n = len(lanes)
    if total_usd is None:
        return (f"**Spend is unbounded across {n} sessions and nothing here meters it.** Pass "
                f"`--budget-usd` to see the per-lane share, and set each session's own ceiling.")
    return (f"**${total_usd:.2f} across {n} lanes is ${total_usd / n:.2f} each** if they spend "
            f"evenly, which they will not. Set the ceiling per session; this script cannot enforce "
            f"one it cannot observe.")


def plan(lanes: list[str], base: str, total_usd: float | None) -> dict:
    lanes = [normalise(l) for l in lanes]
    if len(lanes) < 2:
        raise Refusal("assign at least two lanes; one lane is an ordinary session and needs none of "
                      "this.")
    check_guard_present()
    check_no_overlap(lanes)
    if _git("status", "--porcelain"):
        raise Refusal("the working tree is dirty. A worktree branched from an uncommitted state "
                      "hands each session a different idea of the baseline, and the handoff medium "
                      "here is git.")
    head = _git("rev-parse", "--short=10", "HEAD")
    return {
        "base": base,
        "head": head,
        "lanes": [{"lane": l,
                   "worktree": f".worktrees/{Path(l).name}",
                   "branch": f"lane/{Path(l).name}",
                   "env": f"RAILS_FLOW_LANE={l}"} for l in lanes],
        "budget": budget_note(lanes, total_usd),
    }


def render(p: dict) -> str:
    out = [f"# Lane assignment — {len(p['lanes'])} sessions from `{p['head']}`\n",
           p["budget"], ""]
    out.append("Create the worktrees:\n")
    out.append("```bash")
    for l in p["lanes"]:
        out.append(f"git worktree add -b {l['branch']} {l['worktree']} {p['base']}")
    out.append("```\n")
    out.append("Then start one session per lane, each with its lane in the environment:\n")
    out.append("```bash")
    for l in p["lanes"]:
        out.append(f"( cd {l['worktree']} && {l['env']} claude )")
    out.append("```\n")
    out.append("**`RAILS_FLOW_LANE` is what makes the guard live.** Without it the lane hook is "
               "dormant and the protocol is advice again — which is the state this exists to end.\n")
    out.append("## The one contention to expect\n")
    out.append("Lanes are subtree-scoped, so two sessions do not touch the same code. **They do both "
               "append to `CHANGELOG.md`**, and that conflict is expected, is one hunk in a known "
               "place, and resolves by keeping both entries.\n")
    out.append("That is deliberate rather than unsolved. A per-lane changelog fragment merged at arm "
               "time would be a **second source of truth for release notes** — exactly what "
               "`derived-artifacts` warns about — traded for avoiding a conflict git already handles "
               "well. Take the conflict.\n")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lanes", nargs="*", help="repo-relative subtree per session, e.g. app/models")
    ap.add_argument("--base", default="dev", help="branch each worktree starts from (default: dev)")
    ap.add_argument("--budget-usd", type=float, default=None,
                    help="total spend across all sessions, to report the per-lane share")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.lanes:
        print("nothing to assign: pass two or more lanes (or --selftest)", file=sys.stderr)
        return 2
    try:
        print(render(plan(args.lanes, args.base, args.budget_usd)))
    except Refusal as why:
        print(f"refused: {why}", file=sys.stderr)
        return 1
    return 0


def selftest() -> int:
    failures: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    print("overlap is the whole safety property")
    for a, b in (("app", "app/models"), ("app/models", "app"), ("app/models", "app/models")):
        try:
            check_no_overlap([a, b])
            ok(f"{a!r} vs {b!r} refused", False)
        except Refusal as why:
            ok(f"{a!r} vs {b!r} refused", "overlap" in str(why))
    try:
        check_no_overlap(["app/models", "app/controllers", "spec"])
        ok("disjoint lanes are accepted", True)
    except Refusal:
        ok("disjoint lanes are accepted", False)
    # A PREFIX THAT IS NOT A PATH BOUNDARY is not an overlap: `app/models` and `app/modelsx` are
    # different directories, and a bare startswith would have called them the same.
    try:
        check_no_overlap(["app/models", "app/modelsx"])
        ok("a shared name prefix is not an overlap", True)
    except Refusal:
        ok("a shared name prefix is not an overlap", False)

    print("one lane is not a lane")
    try:
        plan(["app/models"], "dev", None)
        ok("a single lane is refused", False)
    except Refusal as why:
        ok("a single lane is refused", "one lane is an ordinary session" in str(why))

    print("the guard must exist first (#660 precedes #661)")
    real = globals()["GUARD"]
    try:
        globals()["GUARD"] = Path("/nonexistent/guard-lane.sh")
        plan(["a", "b"], "dev", None)
        ok("a missing lane guard refuses assignment", False)
    except Refusal as why:
        ok("a missing lane guard refuses assignment", "lane guard is missing" in str(why))
    finally:
        globals()["GUARD"] = real

    print("spend is named, never silently unbounded")
    ok("no budget says so plainly", "unbounded" in budget_note(["a", "b"], None))
    ok("a budget reports the per-lane share", "$5.00 each" in budget_note(["a", "b"], 10.0))
    ok("...and refuses to promise enforcement",
       "cannot enforce" in budget_note(["a", "b"], 10.0))

    print("the render says what a reader needs")
    view = render({"base": "dev", "head": "abc1234567",
                   "lanes": [{"lane": "app/models", "worktree": ".worktrees/models",
                              "branch": "lane/models", "env": "RAILS_FLOW_LANE=app/models"}],
                   "budget": "b"})
    ok("it emits the worktree command", "git worktree add -b lane/models" in view)
    ok("...and sets the lane in the environment", "RAILS_FLOW_LANE=app/models claude" in view)
    ok("...saying the guard is dormant without it", "dormant" in view)
    ok("...and naming the CHANGELOG contention", "CHANGELOG.md" in view)
    ok("...with the decision, not just the problem", "Take the conflict." in view)

    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
