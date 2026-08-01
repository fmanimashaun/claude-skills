#!/usr/bin/env python3
"""Prove every pipeline breaker fires -- and, harder, that a healthy run is never refused.

Run:  python3 breaker.py --selftest   (or execute this file directly)

The silent direction is the one that decides whether this survives. A breaker that refuses a
run which was making progress does not get tuned; it gets bypassed, and then nothing is bounded at
all. So each firing fixture below is paired with the near miss that must stay quiet:

  * three failures with a CHANGING signature is progress, not a stall -- the digits stay in the
    normalised signature for exactly this reason;
  * the last attempt before the cap must proceed, or the cap is really cap-minus-one;
  * a run inside its budget must proceed, however long the wall clock has been running elsewhere;
  * a stage whose predecessor passed is in order, even though the ordering rule scans every
    earlier stage.

The last two checks run against the REAL shipped files, and a fixture cannot make them: that the
doctrine in `reference/stop-conditions.md` still enumerates the four escapes and the three numbers
this module declares, and that every pipeline command or agent describing an unattended re-run
actually names the breaker. Doctrine and code drifting apart is the defect #128 is about, one
level up.

Costs nothing: no network, no Docker, no Kamal.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import breaker as br  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STAGES = ["verify", "certify", "release"]
START = "2026-08-01T09:00:00+00:00"


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def ledger(records: list[dict], *, stages: list[str] | None = None,
           limits: dict | None = None, started: str = START) -> list[dict]:
    run = {
        "kind": "run",
        "started": started,
        "stages": list(stages if stages is not None else STAGES),
        "limits": dict(limits) if limits else dict(br.DEFAULTS),
    }
    return [run, *records]


def attempt(stage: str, outcome: str, signature: str = "") -> dict:
    return {"kind": "attempt", "at": START, "stage": stage, "outcome": outcome,
            "signature": signature}


def expect_stop(label: str, records: list[dict], reason: str, *, stage: str = "verify",
                now: str = "2026-08-01T09:30:00+00:00") -> None:
    """The firing direction: this stage must be refused, for THIS reason."""
    _tick()
    try:
        got, _ = br.evaluate(records, stage, br._now(now))
    except br.Unusable as exc:
        FAILURES.append(f"{label}: raised Unusable instead of refusing ({exc})")
        return
    if got != reason:
        FAILURES.append(
            f"{label}: expected STOP {reason!r}, got {got or 'PROCEED'} -- the breaker did not "
            "fire on the situation it exists for"
        )


def expect_proceed(label: str, records: list[dict], *, stage: str = "verify",
                   now: str = "2026-08-01T09:30:00+00:00") -> None:
    """The SILENT direction: a run that is progressing must not be refused."""
    _tick()
    try:
        got, _ = br.evaluate(records, stage, br._now(now))
    except br.Unusable as exc:
        FAILURES.append(f"{label}: raised Unusable instead of proceeding ({exc})")
        return
    if got:
        FAILURES.append(
            f"{label}: expected PROCEED, got STOP {got!r} -- a breaker that refuses a healthy run "
            "gets bypassed, and then nothing is bounded"
        )


def expect_verdict(label: str, records: list[dict], want: str,
                   now: str = "2026-08-01T09:30:00+00:00") -> None:
    _tick()
    got, _ = br.verdict(records, br._now(now))
    if got != want:
        FAILURES.append(f"{label}: expected the run to report {want!r}, got {got!r}")


def expect_report_line(label: str, records: list[dict], needle: str,
                       now: str = "2026-08-01T09:30:00+00:00") -> None:
    """Some facts belong in the report without changing the verdict. Asserting only the verdict
    would leave those lines with nothing holding them to account."""
    _tick()
    _, lines = br.verdict(records, br._now(now))
    if not any(needle in line for line in lines):
        FAILURES.append(
            f"{label}: the report never mentions {needle!r} -- the verdict alone does not tell a "
            f"reader what to fix. Got: {lines}"
        )


def cli(*argv: str) -> int:
    """`breaker.main` with both streams captured.

    The CLI fixtures deliberately drive the refusals, and every refusal prints. Left uncaptured
    they bury the one line that matters when a mutation trips a fixture.
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return br.main(list(argv))


def expect_unusable(label: str, call) -> None:
    _tick()
    try:
        call()
    except br.Unusable:
        return
    FAILURES.append(
        f"{label}: expected UNUSABLE (exit 2), got a verdict -- collapsing 'I cannot judge this' "
        "into 'proceed' is how an unbounded run reads as a bounded one"
    )


def run() -> int:  # noqa: PLR0915 -- a fixture list; splitting it would hide the pairing
    # ---- attempt cap ------------------------------------------------------------------
    three = [attempt("verify", "fail", f"rspec: {n} failures") for n in (5, 4, 3)]
    expect_stop("three failures against a cap of three", ledger(three), "attempt-cap")
    # The near miss that decides the cap's meaning: the THIRD attempt must be allowed to happen.
    expect_proceed("the last attempt before the cap still proceeds",
                   ledger(three[:2]))

    # ---- no progress ------------------------------------------------------------------
    same = [attempt("verify", "fail", "rspec: 3 failures in spec/billing_spec.rb")] * 2
    expect_stop("two identical failure signatures", ledger(same), "no-progress")
    # Whitespace and case are noise; the same failure formatted differently is still the same.
    expect_stop(
        "an identical signature reformatted is still identical",
        ledger([attempt("verify", "fail", "rspec:  3 FAILURES"),
                attempt("verify", "fail", "rspec: 3 failures")]),
        "no-progress",
    )
    # NEAR MISS, and the reason digits survive normalisation: a shrinking failure count is the
    # commonest form of real progress, and a normaliser that erased it would stop a converging run.
    # The two signatures differ in NOTHING but the digit, on purpose: a fixture whose strings also
    # differ in a word would still pass with the digits erased, and would prove nothing about the
    # carve-out it is named for.
    expect_proceed(
        "a changing failure count is progress, not a stall",
        ledger([attempt("verify", "fail", "kamal: 3 of 5 healthchecks failed"),
                attempt("verify", "fail", "kamal: 1 of 5 healthchecks failed")]),
    )
    # A pass between two identical failures still leaves two identical failures in the window --
    # but the stage has passed, so the ordering of the rules is what is under test here.
    expect_stop("a passed stage is not re-attempted",
                ledger([attempt("verify", "pass")]), "already-passed")

    # ---- out of order: the gate-skipping escape, made mechanical -----------------------
    expect_stop("release reached before certify passed", ledger([attempt("verify", "pass")]),
                "out-of-order", stage="release")
    expect_proceed("the next stage after a pass is in order",
                   ledger([attempt("verify", "pass")]), stage="certify")
    expect_proceed("the first stage has no predecessor to wait for", ledger([]))

    # ---- budget -----------------------------------------------------------------------
    expect_stop("the wall-clock budget is spent", ledger([]), "budget",
                now="2026-08-01T11:30:00+00:00")
    # NEAR MISS: one minute short of the budget is inside it.
    expect_proceed("one minute short of the budget still proceeds", ledger([]),
                   now="2026-08-01T10:59:00+00:00")

    # ---- unusable, never a verdict -----------------------------------------------------
    expect_unusable("a stage outside the declared plan",
                    lambda: br.evaluate(ledger([]), "deploy-to-prod", br._now(START)))
    expect_unusable("a run record with no stages",
                    lambda: br.evaluate([{"kind": "run", "stages": [], "limits": br.DEFAULTS}],
                                        "verify", br._now(START)))
    expect_unusable("a run record missing a limit",
                    lambda: br.evaluate([{"kind": "run", "stages": STAGES,
                                          "limits": {"attempts": 3}}], "verify", br._now(START)))
    # A missing `started` must be UNUSABLE, never "no budget". This path had exactly that fail-open
    # in its first draft: `_elapsed` returned None and the budget rule quietly skipped -- on the
    # hand-edited ledger where you would most want it to fire.
    expect_unusable("a run record with no started timestamp",
                    lambda: br.evaluate([{"kind": "run", "stages": STAGES,
                                          "limits": dict(br.DEFAULTS)}], "verify", br._now(START)))

    # ---- the report: complete / partial / stopped ---------------------------------------
    passes = [attempt(s, "pass") for s in STAGES]
    expect_verdict("every planned stage passed", ledger(passes), "complete")
    expect_verdict("a stage never attempted", ledger(passes[:2]), "partial")
    expect_verdict(
        "a recorded stop makes the run stopped",
        ledger([*passes[:1], {"kind": "stop", "at": START, "stage": "certify",
                              "breaker": "no-progress", "diagnosis": "same 3 failures twice"}]),
        "stopped",
    )
    # Exceeding the cap is `stopped` EVEN IF the stage later passed. A run that ignored its own
    # breaker did not follow the protocol, and crediting the outcome would make the cap advisory.
    expect_verdict(
        "a cap exceeded then passed is still stopped",
        ledger([*[attempt("verify", "fail", f"e{n}") for n in range(4)], *passes]),
        "stopped",
    )
    # A stop with an empty diagnosis is the failure this module is about: the run ended and nobody
    # can say why. Any stop already makes the verdict `stopped`, so the verdict cannot hold this
    # to account -- the REPORT LINE is what must call it out, and that is what is asserted.
    blank_stop = ledger([{"kind": "stop", "at": START, "stage": "verify", "breaker": "budget",
                          "diagnosis": "   "}])
    expect_verdict("a stop with no diagnosis", blank_stop, "stopped")
    expect_report_line("a stop with no diagnosis is named in the report", blank_stop,
                       "no diagnosis")
    # A run whose budget expired with stages still open is `stopped`, not `partial`: a breaker is
    # open whether or not anyone asked it.
    expect_verdict("the budget expired with stages still open", ledger([]), "stopped",
                   now="2026-08-01T11:30:00+00:00")
    # NEAR MISS: a run that finished inside its budget is complete, and the clock reading past the
    # budget must not retro-actively spoil a finished run.
    expect_verdict("a finished run is complete however late the clock is read",
                   ledger([attempt(s, "pass") for s in STAGES]), "complete",
                   now="2026-08-02T09:00:00+00:00")

    # ---- the ledger reader refuses rather than guesses ----------------------------------
    root = Path(tempfile.mkdtemp(prefix="breaker-selftest-"))
    expect_unusable("no ledger at all", lambda: br.read_ledger(root / "missing.jsonl"))
    empty = root / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    expect_unusable("an empty ledger", lambda: br.read_ledger(empty))
    broken = root / "broken.jsonl"
    broken.write_text('{"kind": "run"\n', encoding="utf-8")
    expect_unusable("a ledger line that is not JSON", lambda: br.read_ledger(broken))
    headless = root / "headless.jsonl"
    headless.write_text(json.dumps(attempt("verify", "pass")) + "\n", encoding="utf-8")
    expect_unusable("a ledger that does not open with a run record",
                    lambda: br.read_ledger(headless))

    # ---- the CLI contract: a fail with no signature, and an override past its bound ------
    # Driven through main() because these are argument-level refusals, and exit 2 -- not 1 -- is
    # the contract. A caller branching on 1 would treat "I could not record this" as "STOP".
    live = root / "cli.jsonl"
    _tick()
    if cli("start", "--stages", "verify,certify", "--ledger", str(live), "--now", START) != 0:
        FAILURES.append("opening a run: `start` did not exit 0 on a valid plan")
    _tick()
    if cli("record", "verify", "--outcome", "fail", "--ledger", str(live)) != 2:
        FAILURES.append(
            "a fail recorded with no signature: expected exit 2 -- the no-progress breaker "
            "compares signatures, so a fail without one is an unfalsifiable breaker"
        )
    _tick()
    if cli("record", "verify", "--outcome", "fail", "--signature", "boom",
           "--ledger", str(live)) != 0:
        FAILURES.append("a fail WITH a signature: expected exit 0, the record is legitimate")
    _tick()
    if cli("stop", "verify", "--breaker", "attempt-cap", "--diagnosis", "  ",
           "--ledger", str(live)) != 2:
        FAILURES.append(
            "a stop with a blank diagnosis: expected exit 2 -- a stop nobody can read leaves the "
            "next session to rediscover the failure from scratch"
        )
    _tick()
    if cli("stop", "verify", "--breaker", "invented-reason", "--diagnosis", "x",
           "--ledger", str(live)) != 2:
        FAILURES.append("a stop naming a breaker that does not exist: expected exit 2")
    _tick()
    if cli("report", "--ledger", str(live), "--now", START) != 1:
        FAILURES.append(
            "reporting an unfinished run: expected exit 1 -- exit 0 on a partial run is exactly "
            "the 'partial presented as complete' failure this module exists to prevent"
        )
    _tick()
    fresh = root / "fresh.jsonl"
    if cli("start", "--stages", "verify", "--attempts", "99", "--ledger", str(fresh),
           "--now", START) != 2:
        FAILURES.append(
            "an attempt cap of 99: expected exit 2 -- an override that can be set to infinity is "
            "not a breaker"
        )
    _tick()
    if cli("start", "--stages", "verify", "--no-progress", "1", "--ledger", str(fresh),
           "--now", START) != 2:
        FAILURES.append(
            "a no-progress window of 1: expected exit 2 -- it would fire before the attempt cap "
            "could ever run"
        )
    _tick()
    if cli("start", "--stages", "verify,verify", "--ledger", str(fresh),
           "--now", START) != 2:
        FAILURES.append("a plan repeating a stage name: expected exit 2, both rules key on it")
    # Restarting over a run that did not end `complete` would reset every counter: the loosest
    # escape available, and the one an agent at its cap reaches for first.
    _tick()
    if cli("start", "--stages", "verify,certify", "--ledger", str(live),
           "--now", START) != 2:
        FAILURES.append(
            "restarting over an unfinished run: expected exit 2 -- a second start would reset "
            "every attempt counter"
        )
    _tick()
    done = root / "done.jsonl"
    done.write_text("\n".join(json.dumps(r) for r in ledger([attempt("verify", "pass")],
                                                            stages=["verify"])) + "\n",
                    encoding="utf-8")
    if cli("start", "--stages", "verify", "--ledger", str(done), "--now", START) != 0:
        FAILURES.append(
            "starting over a run that ended complete: expected exit 0 -- refusing here would "
            "make the ledger a one-shot file and get it deleted instead"
        )

    # ---- the two checks a fixture cannot make: the REAL shipped doctrine and commands -----
    # A FAILURE, never a skip. A selftest reporting "all passed" while silently checking nothing
    # is the exact bug this repo's doctrine warns about.
    _tick()
    doctrine_path = PLUGIN_ROOT / "reference" / "stop-conditions.md"
    if not doctrine_path.is_file():
        FAILURES.append(
            f"the shipped doctrine ({doctrine_path}) is missing -- the breaker enforces four "
            "numbers and two of the four escapes; the other two exist only in that file"
        )
    else:
        doctrine = doctrine_path.read_text(encoding="utf-8")
        for escape in br.FORBIDDEN_ESCAPES:
            _tick()
            if escape not in doctrine:
                FAILURES.append(
                    f"the shipped doctrine does not enumerate the escape {escape!r} -- "
                    "#128 requires all four named, and two of them are enforced nowhere else"
                )
        for key, default in br.DEFAULTS.items():
            flag = "--" + key.replace("_", "-")
            _tick()
            low, high = br.BOUNDS[key]
            stated = [line for line in doctrine.splitlines() if flag in line]
            if not any(re.search(rf"\b{default}\b", line) for line in stated):
                FAILURES.append(
                    f"the shipped doctrine never states {flag}'s default of {default} on the same "
                    "line as the flag -- the doc and the code would drift silently, which is one "
                    "level up from the defect #128 reports"
                )
            if not any(f"{low}..{high}" in line for line in stated):
                FAILURES.append(
                    f"the shipped doctrine never states {flag}'s allowed range {low}..{high} -- "
                    "'overridable' with no stated bound reads as unbounded"
                )
        for token in (*br.STOP_REASONS, *br.VERDICTS):
            _tick()
            if token not in doctrine:
                FAILURES.append(
                    f"the shipped doctrine never names {token!r}, which the script prints -- an "
                    "operator reading the output would find nothing that explains it"
                )

    # Every pipeline surface that describes an unattended re-run must name the breaker. This is
    # the wiring assertion: doctrine nothing calls is doctrine nothing enforces.
    #
    # Matched against WHITESPACE-NORMALISED text, not per line. `pipeline.md` wraps "run the
    # whole pipeline" across two lines, so a line-based scan silently missed the command that
    # starts the unattended chain -- found by counting the subjects, not by reading.
    unattended = re.compile(
        r"re-?run idempotently|self-troubleshoot|troubleshoot autonomously|chain until|"
        r"run the whole pipeline", re.I)
    matched = 0
    for doc in sorted([*(PLUGIN_ROOT / "commands").glob("*.md"),
                       *(PLUGIN_ROOT / "agents").glob("*.md")]):
        body = doc.read_text(encoding="utf-8")
        if not unattended.search(re.sub(r"\s+", " ", body)):
            continue
        matched += 1
        _tick()
        if "breaker.py" not in body:
            FAILURES.append(
                f"{doc.name} describes an unattended re-run but never names `breaker.py` -- the "
                "one surface that needs a bound is the one that has none"
            )
    _tick()
    if matched < 4:
        FAILURES.append(
            f"only {matched} pipeline surface(s) matched the unattended-run vocabulary; four are "
            "known to (pipeline.md, deploy-cloud.md, pipeline-coordinator.md, "
            "kamal-configurator.md). A shrinking scan reports clean over work it never did"
        )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"breaker selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
