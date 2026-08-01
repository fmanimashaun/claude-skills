#!/usr/bin/env python3
"""Circuit breakers for an unattended pipeline run -- the pipeline half of #128.

Run:  python3 breaker.py start  --stages verify,certify,release
      python3 breaker.py check  certify
      python3 breaker.py record certify --outcome fail --signature "rspec: 3F in billing_spec"
      python3 breaker.py stop   certify --breaker no-progress --diagnosis "..."
      python3 breaker.py report
      python3 breaker.py --selftest

WHY (#128, the `comp:pipeline` half). rails-flow's half shipped stop conditions inside the work
order `/rails-flow:handoff` writes, enforced by `check_handoff.py`. Pipeline has no work order: it
runs a **gated chain of stages**, sometimes unattended ("run the whole pipeline"), and its most
autonomous agent -- `kamal-configurator`, whose blast radius is a production environment -- was
told to *"troubleshoot autonomously"* and *"re-run idempotently"* with no bound of any kind. Each
plugin resolves its own `${CLAUDE_PLUGIN_ROOT}`, so pipeline cannot borrow rails-flow's checker; it
needs its own, and the shape is different because the failure is different.

An agent that cannot make progress does not idle -- it digs. In this plugin the digging is
expensive: re-pushing an image, re-running `kamal deploy` against a live host, or reaching for
`RAILS_FLOW_ALLOW_DEPLOY=1` because the gate is "obviously" wrong. Every one of those looks like
activity in a log, and two of them look like success.

WHAT THIS GUARANTEES (all of it decidable from the ledger, none of it from the agent's word)
    * A run declares its stages and its limits ONCE, at `start`. `check` reads the limits from the
      ledger and takes no threshold flags at all, so an agent under pressure cannot widen its own
      cap mid-run, and a second `start` over an open run is refused rather than silently resetting
      the counters.
    * `check` refuses a stage that is not in the plan, a stage whose predecessors have not passed
      (the gate-skipping escape, made mechanical), a stage past its attempt cap, a stage whose last
      N failures carry an identical signature, and any stage once the wall-clock budget is spent.
    * A `fail` cannot be recorded without a failure SIGNATURE -- without one the no-progress
      detector can never fire, which is an unfalsifiable breaker wearing a breaker's clothes.
    * A `stop` cannot be recorded without a DIAGNOSIS.
    * `report` derives complete / partial / stopped from the ledger and exits 0 ONLY for complete,
      so "partial completion reported as success" is not available to a caller that reads the exit
      code. Over-running a cap makes the run `stopped` even if every stage later passed.

WHAT IT DOES NOT
    It is a discipline, not a sandbox. It cannot stop an agent that never calls it, deletes the
    ledger, or lies to `--now`; the ledger is plain JSONL in the repo precisely so those show up in
    a diff. It cannot see file edits, so the blast-radius cap and the "weakening a test" escape
    stay doctrine (`reference/stop-conditions.md`) rather than becoming checks here -- and this
    module's selftest asserts that doctrine still enumerates all four escapes and still states
    these numbers, so the two cannot drift apart.

    It is deliberately NOT registered in a `checks.json` for `project_gates.py`. Those gates judge
    a repo's standing quality; this judges one run in flight, so a ledger sitting mid-run would
    fail a project gate for the ordinary state of doing the work. Pipeline ships no `checks.json`
    for that reason, not by oversight.

    It also does NOT implement escalate-and-continue, and that is a decision rather than an
    omission. rails-flow's criteria are independent, so a stop there moves to unrelated work. A
    pipeline is a gated chain: nothing downstream of a stopped stage is independent of it, and
    "continuing" past a stop is the gate-skipping escape under a friendlier name. So a stop ends
    the run here, and `report` says so.

DEFAULTS AND WHERE THEY COME FROM
    3 attempts, 2 identical signatures, 120 minutes -- the same numbers rails-flow's work order
    doctrine settled on, deliberately reused rather than re-derived. They are OURS (an architecture
    decision, no upstream to cite), overridable at `start` within a bounded range: an override that
    can be set to infinity is not a breaker, so the range is enforced and the refusal names what to
    do instead.

Exit codes:  0 proceed / recorded / complete
             1 STOP -- a breaker is open, or the run is partial or stopped
             2 unusable input -- unreadable ledger, undeclared stage, a fail with no signature
             (1 and 2 are never collapsed: "do not proceed" and "I could not tell" are different
             answers, and only one of them is a verdict.)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER = Path("pipeline/run-ledger.jsonl")

# Ours, not anyone's API. Same numbers as the rails-flow work order, on purpose: two halves of one
# issue disagreeing about what "3 attempts" means would be worse than either number being wrong.
DEFAULTS: dict[str, int] = {"attempts": 3, "no_progress": 2, "budget_minutes": 120}

# An override that can be set to infinity is not a breaker. `no_progress` starts at 2 because 1
# would stop on the first failure and make the attempt cap unreachable -- a breaker that fires
# before the mechanism it guards can run is not a stricter setting, it is a broken one.
BOUNDS: dict[str, tuple[int, int]] = {
    "attempts": (1, 10),
    "no_progress": (2, 10),
    "budget_minutes": (1, 480),
}

# The reasons `check` can refuse. Printed as the first token after STOP so a caller can branch on
# it without parsing prose, and asserted present in the shipped doctrine by the selftest.
STOP_REASONS: tuple[str, ...] = (
    "already-passed",
    "out-of-order",
    "attempt-cap",
    "no-progress",
    "budget",
)

VERDICTS: tuple[str, ...] = ("complete", "partial", "stopped")

# #128's four escapes, translated to what they look like in a gated deployment chain. Same
# taxonomy, not a new one: (1) destroying the external proof, (2) trading proven work for
# unproven, (3) going outside the declared boundary, (4) switching off the thing that made
# unattended work allowable. The doctrine file names the mapping; the selftest asserts it lists
# all four.
FORBIDDEN_ESCAPES: tuple[str, ...] = (
    "weakening, skipping or deleting a failing test to get a stage green",
    "reverting a stage that already passed in order to unblock this one",
    "running a stage out of order, or past a gate that has not passed",
    "disabling a guardrail, hook, or gate -- including reaching for an audited override",
)

OUTCOMES = ("pass", "fail")
_WS = re.compile(r"\s+")


class Unusable(Exception):
    """The input cannot be judged -- never report PROCEED or `complete` for it."""


def _now(text: str | None) -> datetime:
    """Wall clock, or a pinned instant.

    `--now` is a testing seam, and an honest one: the budget breaker is the only rule that depends
    on time, so without it the rule would be unreachable by any fixture -- and an untested breaker
    is the one that is wrong when it finally fires.
    """
    if text is None:
        return datetime.now(timezone.utc)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Unusable(f"--now {text!r} is not an ISO-8601 instant") from exc
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _signature(text: str) -> str:
    """Normalise a failure signature for comparison.

    Whitespace and case only. Digits are deliberately KEPT: "3 failures" becoming "2 failures" is
    progress, and a normaliser that erased it would report a run as stuck while it was converging.
    """
    return _WS.sub(" ", text).strip().lower()


# ---------------------------------------------------------------------------------------------
# The ledger: append-only JSONL, in the repo, so a run is diffable rather than remembered.
# ---------------------------------------------------------------------------------------------

def read_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        raise Unusable(
            f"no ledger at {path} -- an unattended run starts with "
            "`breaker.py start --stages …`; without it there is no plan to measure against and "
            "no limit anyone agreed to"
        )
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Unusable(f"{path} line {number} is not JSON ({exc}) -- refusing to guess") from exc
        if not isinstance(record, dict) or "kind" not in record:
            raise Unusable(f"{path} line {number} carries no `kind` -- not a ledger record")
        records.append(record)
    if not records:
        raise Unusable(f"{path} is empty -- an empty ledger would report every breaker closed")
    if records[0].get("kind") != "run":
        raise Unusable(
            f"{path} does not open with a `run` record -- the plan and the limits live there, and "
            "reading attempts without them would apply defaults nobody declared"
        )
    return records


def _run_record(records: list[dict]) -> dict:
    run = records[0]
    stages = run.get("stages")
    if not isinstance(stages, list) or not stages or not all(isinstance(s, str) for s in stages):
        raise Unusable("the `run` record declares no stages -- there is nothing to gate")
    limits = run.get("limits")
    if not isinstance(limits, dict) or any(k not in limits for k in DEFAULTS):
        raise Unusable(
            f"the `run` record is missing one of the limits {sorted(DEFAULTS)} -- a run whose "
            "limits are implicit is a run whose limits can be reinterpreted later"
        )
    return run


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _attempts(records: list[dict], stage: str) -> list[dict]:
    return [r for r in records if r.get("kind") == "attempt" and r.get("stage") == stage]


def _passed(records: list[dict], stage: str) -> bool:
    return any(r.get("outcome") == "pass" for r in _attempts(records, stage))


def _stops(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("kind") == "stop"]


def _elapsed(run: dict, now: datetime) -> float:
    """Minutes since the run opened. Shared by `check` and `report` deliberately: two
    implementations of "is the budget spent" would eventually disagree, and the one that drifted
    would be whichever is not the gate.

    A missing or unparseable `started` is UNUSABLE, never "no budget". `start` always writes one, so
    nothing legitimate lacks it -- and returning None here would have disabled the budget breaker
    silently on exactly the hand-edited ledger where you would most want it.
    """
    started = run.get("started")
    if not isinstance(started, str):
        raise Unusable(
            "the `run` record carries no `started` timestamp, so the budget cannot be measured. "
            "That is unusable input, not an unlimited budget."
        )
    try:
        begin = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Unusable(f"the `run` record's `started` is not ISO-8601: {started!r}") from exc
    if begin.tzinfo is None:
        begin = begin.replace(tzinfo=timezone.utc)
    return (now - begin).total_seconds() / 60


# ---------------------------------------------------------------------------------------------
# check: read-only. It never writes into what it inspects -- the diagnosis is a separate,
# deliberate act (`stop`), so a verdict can never be produced by the same call that records it.
# ---------------------------------------------------------------------------------------------

def evaluate(records: list[dict], stage: str, now: datetime) -> tuple[str, str]:
    """(reason, explanation). `reason` is "" when the stage may be attempted."""
    run = _run_record(records)
    stages: list[str] = run["stages"]
    limits: dict = run["limits"]
    if stage not in stages:
        raise Unusable(
            f"stage {stage!r} is not in this run's plan ({', '.join(stages)}) -- a stage nobody "
            "planned has no cap, no budget and no predecessor, so nothing here can bound it. "
            "Close this run and start one whose plan says what you are doing."
        )

    if _passed(records, stage):
        return "already-passed", (
            f"{stage} already has a pass in this run. Re-running a stage that passed spends real "
            "money to replace proven work with unproven work."
        )

    for earlier in stages[: stages.index(stage)]:
        if not _passed(records, earlier):
            return "out-of-order", (
                f"{earlier} has not passed, and it comes before {stage} in this run's plan. "
                "Reaching past a gate that has not passed is the escape this chain exists to "
                "prevent -- it is how uncertified code gets an image built for it."
            )

    spent = _elapsed(run, now)
    budget = limits["budget_minutes"]
    if spent >= budget:
        return "budget", (
            f"{spent:.0f} of {budget} budgeted minutes are spent. An unattended run with no "
            "budget is discovered by its bill; report the remainder and hand back."
        )

    failures = [r for r in _attempts(records, stage) if r.get("outcome") == "fail"]
    cap = limits["attempts"]
    if len(failures) >= cap:
        return "attempt-cap", (
            f"{stage} has failed {len(failures)} time(s) against a cap of {cap}. The next attempt "
            "on an unchanged failure has never been the one that works."
        )

    window = limits["no_progress"]
    if len(failures) >= window:
        recent = [_signature(str(r.get("signature", ""))) for r in failures[-window:]]
        if len(set(recent)) == 1:
            return "no-progress", (
                f"the last {window} failures of {stage} carry an identical signature "
                f"({recent[0][:80]!r}). Repetition without a changing error is the signal; a "
                "changing error would have been progress."
            )
    return "", f"{stage} may be attempted ({len(failures)} of {cap} attempts spent)."


# ---------------------------------------------------------------------------------------------
# report: the honest final verdict, derived rather than asserted.
# ---------------------------------------------------------------------------------------------

def verdict(records: list[dict], now: datetime) -> tuple[str, list[str]]:
    """(complete|partial|stopped, the lines that justify it)."""
    run = _run_record(records)
    stages: list[str] = run["stages"]
    limits: dict = run["limits"]
    lines: list[str] = []
    overrun: list[str] = []
    unfinished: list[str] = []

    for stage in stages:
        attempts = _attempts(records, stage)
        failures = [r for r in attempts if r.get("outcome") == "fail"]
        if _passed(records, stage):
            state = "pass"
        elif attempts:
            state = "unfinished"
            unfinished.append(stage)
        else:
            state = "not attempted"
            unfinished.append(stage)
        lines.append(f"  {stage}: {state} ({len(failures)} failure(s) of {limits['attempts']})")
        if len(failures) > limits["attempts"]:
            overrun.append(
                f"{stage} was attempted {len(failures)} times against a cap of "
                f"{limits['attempts']} -- the cap was exceeded, so this run is not clean however "
                "it ended"
            )

    stops = _stops(records)
    for stop in stops:
        lines.append(
            f"  STOPPED at {stop.get('stage')}: {stop.get('breaker')} -- "
            f"{stop.get('diagnosis', '')}"
        )
    # A tripped breaker with no recorded diagnosis is the failure this whole module is about: the
    # run stopped and nobody can say why. It cannot change the VERDICT -- any stop already makes a
    # run `stopped`, and writing `stops or undiagnosed` would be a condition whose second term can
    # never decide anything, which is a branch no fixture can hold to account. It changes the
    # REPORT, and a fixture asserts the line is there.
    for stop in stops:
        if not str(stop.get("diagnosis", "")).strip():
            lines.append(
                f"  {stop.get('stage')} stopped with no diagnosis -- a stop without one leaves "
                "the next session to rediscover the failure from scratch"
            )

    # A run whose budget ran out with stages still open is `stopped`, not `partial`: a breaker is
    # open, whether or not anyone asked it. `partial` is for a run that simply ended.
    spent = _elapsed(run, now)
    exhausted = bool(unfinished) and spent >= limits["budget_minutes"]
    if exhausted:
        lines.append(
            f"  the budget of {limits['budget_minutes']} minute(s) is spent with "
            f"{len(unfinished)} stage(s) still open -- {spent:.0f} minutes used"
        )

    if stops or overrun or exhausted:
        lines.extend(f"  {o}" for o in overrun)
        return "stopped", lines
    if unfinished:
        lines.append(
            "  not attempted / unfinished: " + ", ".join(unfinished)
            + " -- name these in the report; partial completion presented as success spends the "
              "reviewer's trust and is how a green log ships a broken release"
        )
        return "partial", lines
    return "complete", lines


# ---------------------------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------------------------

def cmd_start(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if not stages:
        raise Unusable("--stages is empty -- a run with no plan cannot be judged complete")
    if len(set(stages)) != len(stages):
        raise Unusable(
            f"--stages repeats a name ({', '.join(stages)}) -- the ordering rule and the "
            "per-stage counters both key on the name, so a duplicate makes both ambiguous"
        )

    limits: dict[str, int] = {}
    for key, fallback in DEFAULTS.items():
        value = getattr(args, key)
        value = fallback if value is None else value
        low, high = BOUNDS[key]
        if not low <= value <= high:
            raise Unusable(
                f"--{key.replace('_', '-')} {value} is outside {low}..{high}. A cap that can be "
                "set to anything is not a cap. If the work genuinely needs more, it is more than "
                "one run: split it, or hand back to a human with the diagnosis."
            )
        limits[key] = value

    if ledger.is_file():
        try:
            existing = read_ledger(ledger)
        except Unusable:
            existing = []
        if existing:
            state, _ = verdict(existing, _now(args.now))
            if state != "complete":
                raise Unusable(
                    f"{ledger} already holds a run that ended `{state}`. Starting over would reset "
                    "every attempt counter, which is the loosest escape available -- archive or "
                    "delete the ledger deliberately (it is committed, so the deletion is "
                    "reviewable) rather than restarting past a breaker."
                )
            ledger.write_text("", encoding="utf-8")

    _append(ledger, {
        "kind": "run",
        "started": _now(args.now).isoformat(),
        "stages": stages,
        "limits": limits,
    })
    print(f"run opened in {ledger}: {' -> '.join(stages)}; limits {limits}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    records = read_ledger(Path(args.ledger))
    reason, explanation = evaluate(records, args.stage, _now(args.now))
    if reason:
        print(f"STOP {reason}: {explanation}", file=sys.stderr)
        print(
            f"Record it: breaker.py stop {args.stage} --breaker {reason} --diagnosis '<what was "
            "attempted, the exact failure signature, the suspected cause>'",
            file=sys.stderr,
        )
        return 1
    print(f"PROCEED {args.stage}: {explanation}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    records = read_ledger(ledger)
    run = _run_record(records)
    if args.stage not in run["stages"]:
        raise Unusable(
            f"stage {args.stage!r} is not in this run's plan ({', '.join(run['stages'])})"
        )
    if args.outcome == "fail" and not (args.signature or "").strip():
        raise Unusable(
            "a failure needs --signature. The no-progress breaker compares consecutive failure "
            "signatures, so a fail recorded without one can never trip it -- an unfalsifiable "
            "breaker is worse than none, because it reads as protection."
        )
    _append(ledger, {
        "kind": "attempt",
        "at": _now(args.now).isoformat(),
        "stage": args.stage,
        "outcome": args.outcome,
        "signature": (args.signature or "").strip(),
    })
    print(f"recorded: {args.stage} {args.outcome}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    records = read_ledger(ledger)
    run = _run_record(records)
    if args.stage not in run["stages"]:
        raise Unusable(
            f"stage {args.stage!r} is not in this run's plan ({', '.join(run['stages'])})"
        )
    if args.breaker not in STOP_REASONS:
        raise Unusable(
            f"--breaker {args.breaker!r} is not one of {', '.join(STOP_REASONS)} -- name the one "
            "`check` reported, so the ledger says which rule ended the run"
        )
    if not args.diagnosis.strip():
        raise Unusable(
            "a stop needs --diagnosis: what was attempted, the exact failure signature, and the "
            "suspected cause. Without it the next session rediscovers the failure from scratch, "
            "which is the cost this record exists to avoid."
        )
    _append(ledger, {
        "kind": "stop",
        "at": _now(args.now).isoformat(),
        "stage": args.stage,
        "breaker": args.breaker,
        "diagnosis": args.diagnosis.strip(),
    })
    print(f"stop recorded: {args.stage} ({args.breaker})")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    records = read_ledger(Path(args.ledger))
    state, lines = verdict(records, _now(args.now))
    stream = sys.stdout if state == "complete" else sys.stderr
    print(f"run: {state}", file=stream)
    for line in lines:
        print(line, file=stream)
    if state == "complete":
        return 0
    print(
        f"\nReport this run as `{state}`, in those words, and name every stage that was not "
        "attempted. A partial run presented as a success is the worst available outcome.",
        file=sys.stderr,
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Circuit breakers and stop conditions for an unattended pipeline run."
    )
    parser.add_argument("--selftest", action="store_true",
                        help="prove every breaker fires AND stays silent on a healthy run")
    subparsers = parser.add_subparsers(dest="command")

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--ledger", default=str(DEFAULT_LEDGER),
                         help=f"append-only JSONL run ledger (default {DEFAULT_LEDGER})")
        sub.add_argument("--now", help="pin the instant (ISO-8601); the budget rule's test seam")

    start = subparsers.add_parser("start", help="declare the stages and the limits, once")
    start.add_argument("--stages", required=True, help="comma-separated, in gate order")
    for key, fallback in DEFAULTS.items():
        low, high = BOUNDS[key]
        start.add_argument(f"--{key.replace('_', '-')}", type=int, default=None,
                           help=f"default {fallback}, allowed {low}..{high}")
    common(start)
    start.set_defaults(func=cmd_start)

    check = subparsers.add_parser("check", help="may this stage be attempted now?")
    check.add_argument("stage")
    common(check)
    check.set_defaults(func=cmd_check)

    record = subparsers.add_parser("record", help="append a stage attempt's outcome")
    record.add_argument("stage")
    record.add_argument("--outcome", required=True, choices=OUTCOMES)
    record.add_argument("--signature", help="the failure signature; required for a fail")
    common(record)
    record.set_defaults(func=cmd_record)

    stop = subparsers.add_parser("stop", help="record a stop, with its mandatory diagnosis")
    stop.add_argument("stage")
    stop.add_argument("--breaker", required=True, help=", ".join(STOP_REASONS))
    stop.add_argument("--diagnosis", required=True)
    common(stop)
    stop.set_defaults(func=cmd_stop)

    report = subparsers.add_parser("report", help="complete / partial / stopped, from the ledger")
    common(report)
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import breaker_selftest as st

        return st.run()

    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        return args.func(args)
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
