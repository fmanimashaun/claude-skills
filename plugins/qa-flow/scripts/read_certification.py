#!/usr/bin/env python3
"""Read one field out of `qa/CERTIFICATION`, and say precisely what is wrong when it cannot.

Run:  python3 read_certification.py --field verdict      # value on stdout, exit 0 if usable
      python3 read_certification.py --field sha
      python3 read_certification.py --explain             # one human line about the stamp's state
      python3 read_certification.py --selftest

WHY THIS EXISTS (#721). A live project's promotion was permanently denied with:

    BLOCKED by qa-flow release gate: certification verdict is not PASS. Re-certify.

The stamp on disk was not JSON at all, so `json.load` raised, the shell's `|| true` swallowed it,
`verdict` came back empty, and the gate reported the wrong problem. **The reader re-certifies, the
same non-conforming file is produced again, and the loop closes.** A gate that misdiagnoses is worse
than one that merely blocks: it sends you to fix something that is not broken.

WHAT THE REPORT GOT WRONG, and it changes the fix. The issue said the text stamp was "what
qa-reporter historically wrote" and that "the writer contract was migrated to JSON", asking for a
text fallback. Checked against the history instead of taken on trust:

    $ git log --format=%H --all -- plugins/qa-flow/agents/qa-reporter.md   # every revision
    2026-07-22  CERTIFICATION` as JSON        <- the FIRST commit to introduce the stamp
    ... every later revision, same
    $ git log -S'Certified sha' --all         # the text shape it asked us to parse
    (empty)

**There was never a text format of ours.** No migration happened, so there is nothing to be
backward-compatible with, and adding a fallback would bless a shape we never specified -- making the
schema permanently ambiguous, which is how a format becomes unknowable. `/qa-flow:certify` writes
JSON; a hand-written stamp is not a certification. So: ONE schema, and an error message that says
exactly that.

WHY ONE READER. `release-gate.sh` parsed this file twice inline and `qa-status.sh` twice more -- four
copies of one `json.load`, kept in step by nothing. That is the shape #699 was: two copies of a
release-notes extractor, a comment asking maintainers to keep them aligned, and a bug that survived
its own discovery because only one copy got fixed.

FAIL-CLOSED IS PRESERVED. This script never decides anything. It reports; the hook denies. A missing
python3, a missing script or an unreadable file all yield no value, and `release-gate.sh` denies on an
empty value exactly as before -- scoped, as ever, to a command targeting `main`.

Exit codes:  0 = the field is present and non-empty · 1 = it is not (reason on stderr)

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STAMP = Path("qa/CERTIFICATION")
FIELDS = ("verdict", "sha", "date", "report")

# The states worth telling apart. The old code collapsed all of them into "verdict is not PASS",
# which is the one sentence that is wrong in every case except the last.
MISSING, NOT_JSON, NOT_OBJECT, NO_FIELD, EMPTY, OK = (
    "missing", "not-json", "not-object", "no-field", "empty", "ok")


def inspect(field: str, stamp: Path = STAMP) -> tuple[str, str]:
    """`(state, value)`. `value` is meaningful only when state is OK."""
    try:
        raw = stamp.read_text(encoding="utf-8")
    except OSError:
        return MISSING, ""
    try:
        data = json.loads(raw)
    except ValueError:
        return NOT_JSON, ""
    if not isinstance(data, dict):
        return NOT_OBJECT, ""
    if field not in data:
        return NO_FIELD, ""
    value = data[field]
    text = "" if value is None else str(value).strip()
    return (OK, text) if text else (EMPTY, "")


def explain(state: str, field: str, stamp: Path = STAMP) -> str:
    """One line a human can act on. Naming the ACTUAL state is the whole point of this file."""
    if state == MISSING:
        return f"no {stamp} found. Run /qa-flow:certify against staging first."
    if state == NOT_JSON:
        first = ""
        try:
            first = stamp.read_text(encoding="utf-8").splitlines()[0][:60]
        except (OSError, IndexError):
            pass
        return (f"{stamp} is not JSON — it starts {first!r}. A certification is written by "
                f"/qa-flow:certify as JSON {{\"sha\",\"date\",\"verdict\"}}; a hand-written or "
                f"free-text stamp is not a certification and cannot be read. Delete it and "
                f"re-certify. (Re-certifying without replacing this file will not help.)")
    if state == NOT_OBJECT:
        return (f"{stamp} is JSON but not an object, so it has no fields. Re-run /qa-flow:certify.")
    if state == NO_FIELD:
        return (f"{stamp} is JSON but has no {field!r} key. The stamp is incomplete — re-run "
                f"/qa-flow:certify rather than editing it by hand.")
    if state == EMPTY:
        return f"{stamp} has an empty {field!r}. The stamp is invalid; re-run /qa-flow:certify."
    return f"{stamp} is readable and {field!r} is set."


def _selftest() -> int:
    import tempfile
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "CERTIFICATION"

        check("a missing stamp is MISSING", inspect("verdict", p) == (MISSING, ""))
        check("...and says so", "no " in explain(MISSING, "verdict", p))

        # THE REPORTED BUG. A text stamp must be diagnosed as not-JSON, never as a failed verdict.
        p.write_text("FIDARA LEDGER — RELEASE CERTIFICATION\n=====================\nVerdict: PASS\n",
                     encoding="utf-8")
        state, value = inspect("verdict", p)
        check("a text stamp is NOT_JSON, not a failed verdict", state == NOT_JSON and value == "")
        msg = explain(state, "verdict", p)
        check("...and the message says it is not JSON", "is not JSON" in msg)
        # The old message sent people to re-certify, which is exactly what does not help here.
        check("...and warns that re-certifying alone will not help",
              "will not help" in msg and "Delete it" in msg)
        check("...and quotes the first line, so it is identifiable",
              "FIDARA LEDGER" in msg)
        # A text stamp CONTAINING the word PASS must still not yield PASS. This is the fixture that
        # matters: a lenient reader would happily grep it out and unlock the promotion.
        check("a text stamp containing 'PASS' does not yield PASS", value != "PASS")

        p.write_text('["a","b"]', encoding="utf-8")
        check("a JSON array is NOT_OBJECT", inspect("verdict", p)[0] == NOT_OBJECT)

        p.write_text('{"sha":"abc123"}', encoding="utf-8")
        check("a stamp with no verdict is NO_FIELD", inspect("verdict", p)[0] == NO_FIELD)
        check("...but its sha reads fine", inspect("sha", p) == (OK, "abc123"))

        p.write_text('{"verdict":"   ","sha":"abc"}', encoding="utf-8")
        check("a whitespace-only verdict is EMPTY", inspect("verdict", p)[0] == EMPTY)

        p.write_text('{"verdict":"PASS","sha":"deadbeefcafe","date":"2026-08-21"}', encoding="utf-8")
        check("a conforming stamp reads PASS", inspect("verdict", p) == (OK, "PASS"))
        check("...and its sha", inspect("sha", p) == (OK, "deadbeefcafe"))
        check("...and whitespace is stripped rather than passed through",
              inspect("date", p) == (OK, "2026-08-21"))

        p.write_text('{"verdict":"FAIL","sha":"abc"}', encoding="utf-8")
        check("a genuine FAIL is OK-with-value-FAIL, not an error state",
              inspect("verdict", p) == (OK, "FAIL"))

        # NO TEXT FALLBACK, asserted. We never prescribed one; adding it would make the schema
        # ambiguous forever. A negative test, because "it happens not to work" and "it must not
        # work" are different claims and only the second survives a refactor.
        p.write_text("Verdict: PASS\nCertified sha: abc123\n", encoding="utf-8")
        check("the text shape the issue asked us to parse is still refused",
              inspect("verdict", p)[0] == NOT_JSON)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--field", choices=FIELDS)
    ap.add_argument("--explain", action="store_true",
                    help="print why the field is unusable, for a gate's deny message")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    field = a.field or "verdict"
    state, value = inspect(field)
    if a.explain:
        print(explain(state, field))
        return 0 if state == OK else 1
    if state == OK:
        print(value)
        return 0
    print(explain(state, field), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
