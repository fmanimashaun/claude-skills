#!/usr/bin/env python3
"""Reject acceptance criteria that cannot fail, and specs that do not prove them.

Run:  python3 check_criteria.py docs/acceptance/<branch-slug>.md
      python3 check_criteria.py docs/acceptance/<slug>.md --specs spec
      python3 check_criteria.py --selftest

WHY (rails-flow #125). The Stop gate enforces "no behavioural change without a proving spec",
but it fires AFTER code exists. Nothing defined what would prove the task correct BEFORE work
started, so the agent decided post-hoc what "done" meant -- and a post-hoc spec asserts what
the code happens to do rather than what was required. Karpathy's form of it: if you cannot
evaluate it, you cannot auto-research it. A task without a pre-agreed observable is not a
task, it is a hope, and an unattended loop cannot grade itself honestly against a hope.

This is the other half of qa-flow #106. That fix made *evidence* trustworthy -- a screenshot
must prove it shows the page under test. This makes the *expectation* trustworthy. An
"Expected vs Actual" authored after seeing the result is unfalsifiable: the same defect class
as `--check || echo`, relocated from the gate to the goal.

WHAT THIS GUARANTEES
    Every criterion has Given/When/Then, names a non-trivial action and a non-trivial
    observable, and avoids the rubber-stamp phrasings that pass review while asserting
    nothing ("works", "handles errors gracefully"). Every unit carries at least one
    error-path criterion. And with --specs, every criterion id appears in some spec file --
    a real 1:1 mapping, which is what makes "the spec proves the criteria" checkable.

WHAT IT DOES NOT
    It cannot tell whether a spec citing `AC-3` actually ASSERTS AC-3's observable; only that
    the claim is traceable. It also cannot know whether the criteria were written before the
    code -- that is what the Stop gate's ordering enforces, not this parser. It closes the
    "unfalsifiable goal" hole, not the "lying spec" one, and the doctrine says so in the same
    words.

Exit codes:  0 clean · 1 findings · 2 unusable input (no file / no criteria parsed)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# A criterion line looks like:
#   - **AC-1** Given a wrong password, when the user submits the form, then ... [error]
ID_RE = re.compile(r"\bAC-(\d+)\b")
GIVEN_RE = re.compile(r"\bgiven\b", re.I)
WHEN_RE = re.compile(r"\bwhen\b", re.I)
THEN_RE = re.compile(r"\bthen\b", re.I)
UNIT_RE = re.compile(r"^\s{0,3}#{2,4}\s+(.*\S)\s*$")

# #707. `ID_RE` matches an `AC-n` token ANYWHERE, including running prose, and `parse()` used to
# treat every matching line as a criterion definition. So an explanatory note under `## Notes` --
# "so AC-6/AC-7 passing also proves the pipeline is wired" -- was read as a malformed criterion and
# the whole file was rejected as UNUSABLE. Reported from a real acceptance doc whose nine criteria
# were all well-formed; the only thing "wrong" was a true, useful sentence. Because this also runs
# from the Stop gate, one such sentence blocked every turn-stop, and the documented remedy ("fix the
# criteria, do not soften") was unactionable: the criteria were already correct.
#
# A DEFINITION is a list item whose id LEADS it. Prose that references criteria is the normal way to
# write a note and is not a definition.
DEF_RE = re.compile(r"^\s*[-*+]\s*(?:\*\*\s*)?AC-(\d+)\b")
# Bolded ids -- the shape the docstring documents. Two of them on one line is two criteria crammed
# together, which is what the one-per-line rule is actually for.
BOLD_ID_RE = re.compile(r"\*\*\s*AC-(\d+)\s*\*\*")

# Phrasings that read as criteria but assert nothing -- the issue's own "bad" list plus the
# neighbours that travel with it. Matched on the THEN clause, where the observable belongs.
RUBBER_STAMP = (
    "works", "work correctly", "works correctly", "works as expected", "behaves correctly",
    "handles errors", "handled gracefully", "handles it gracefully", "gracefully",
    "no errors", "without error", "is correct", "looks right", "as expected",
    "handles invalid input", "is successful", "succeeds properly", "properly",
)

# An error-path criterion has to be recognisable. A tag is explicit and greppable; the
# keyword list is the fallback so an author who forgets the tag is not blocked by pedantry.
ERROR_TAG = "[error]"
ERROR_HINTS = (
    "invalid", "wrong", "missing", "denied", "forbidden", "unauthori", "reject",
    "fails", "failure", "empty", "duplicate", "expired", "not found", "422", "403",
    "401", "404", "409", "500", "blank", "too long", "too short", "conflict",
)


class Unusable(Exception):
    """The input cannot be checked -- never report clean for it."""


@dataclass
class Criterion:
    num: int
    unit: str
    line_no: int
    text: str

    @property
    def cid(self) -> str:
        return f"AC-{self.num}"

    def clause(self, start: re.Pattern[str], end: re.Pattern[str] | None) -> str:
        """The text between two clause keywords -- used to judge action and observable."""
        m = start.search(self.text)
        if not m:
            return ""
        rest = self.text[m.end():]
        if end:
            m2 = end.search(rest)
            if m2:
                rest = rest[: m2.start()]
        return rest.strip(" ,.;:`*")


def parse(path: Path) -> list[Criterion]:
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    unit = ""
    out: list[Criterion] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        heading = UNIT_RE.match(raw)
        if heading:
            unit = heading.group(1)
            continue
        bold = BOLD_ID_RE.findall(raw)
        lead = DEF_RE.match(raw)
        if bold:
            # The documented shape. Only the BOLDED ids count as definitions, so a criterion may
            # reference another one in its own text -- `- **AC-7** Given AC-6 has passed, …` -- which
            # the old rule rejected.
            ids = bold
        elif lead:
            # A leading id without the bold markers is accepted, but keeps the strict one-per-line
            # rule: with no marker there is nothing to tell a definition from a reference, so
            # `- AC-1 and AC-2 Given …` must still fail. Bold the id to get in-text references.
            ids = ID_RE.findall(raw)
        else:
            # PROSE. It mentions criteria; it does not define one. Not silently dropped, though: a
            # line carrying a full Given/When/Then *is* trying to be a criterion, and skipping it
            # would lose a real one -- worse than the false positive this fixes.
            if (ID_RE.search(raw) and GIVEN_RE.search(raw)
                    and WHEN_RE.search(raw) and THEN_RE.search(raw)):
                raise Unusable(
                    f"{path}:{line_no} reads like a criterion -- it has Given/When/Then and an "
                    f"`AC-n` id -- but the id does not lead the line, so it is not a definition and "
                    f"the mapping check would never see it. Write it as `- **AC-n** Given …`."
                )
            continue
        if len(ids) > 1:
            raise Unusable(
                f"{path}:{line_no} names {len(ids)} criterion ids on one definition line ({ids}); "
                "one criterion per line, or the mapping check cannot attribute a spec to a "
                "criterion. A criterion that merely REFERENCES another is fine -- bold only the id "
                "being defined."
            )
        out.append(Criterion(num=int(ids[0]), unit=unit, line_no=line_no, text=raw))

    if not out:
        raise Unusable(
            f"{path} contains no `AC-n` criteria -- refusing to bless a criteria file with no "
            "criteria in it (a task without an observable is a hope, not a task)"
        )
    return out


def _is_error_path(text: str) -> bool:
    low = text.lower()
    if ERROR_TAG in low:
        return True
    return any(h in low for h in ERROR_HINTS)


def check(criteria: list[Criterion], spec_root: Path | None = None) -> list[str]:
    findings: list[str] = []

    # ---- duplicate ids would silently merge two criteria into one traceable claim --------
    seen: dict[int, Criterion] = {}
    for c in criteria:
        if c.num in seen:
            findings.append(
                f"{c.cid} (line {c.line_no}) reuses an id already used on line "
                f"{seen[c.num].line_no} -- ids must be unique or the spec mapping is ambiguous"
            )
        else:
            seen[c.num] = c

    for c in criteria:
        where = f"{c.cid} (line {c.line_no})"

        missing = [
            name for name, rx in (("Given", GIVEN_RE), ("when", WHEN_RE), ("then", THEN_RE))
            if not rx.search(c.text)
        ]
        if missing:
            findings.append(
                f"{where}: missing {', '.join(missing)} -- the shape is "
                "\"Given <state>, when <action>, then <observable>\""
            )
            continue  # the clause checks below are meaningless without the keywords

        action = c.clause(WHEN_RE, THEN_RE)
        observable = c.clause(THEN_RE, None)

        if len(action.split()) < 3:
            findings.append(
                f"{where}: the `when` clause names no real action ({action!r}) -- say the "
                "command or user action, not a restatement of the state"
            )
        if len(observable.split()) < 3:
            findings.append(
                f"{where}: the `then` clause names no real observable ({observable!r}) -- say "
                "what can be seen or asserted"
            )

        low = observable.lower()
        for phrase in RUBBER_STAMP:
            # Word-boundary match so "properly" does not fire inside "property".
            if re.search(rf"\b{re.escape(phrase)}\b", low):
                findings.append(
                    f"{where}: the observable is rubber-stamp phrasing ({phrase!r}) -- it will "
                    "be marked done without proving anything. Name the visible result."
                )
                break

    # ---- every unit needs at least one error-path criterion -----------------------------
    units: dict[str, list[Criterion]] = {}
    for c in criteria:
        units.setdefault(c.unit, []).append(c)
    for unit, group in units.items():
        if not any(_is_error_path(c.text) for c in group):
            label = unit or "<untitled unit>"
            findings.append(
                f"unit {label!r} has no error-path criterion ({', '.join(c.cid for c in group)})"
                " -- happy-path-only criteria are rejected, because most real defects live on "
                f"the error path. Tag one {ERROR_TAG} or state a failure case."
            )

    # ---- the 1:1 mapping: every criterion must be cited by some spec --------------------
    if spec_root is not None:
        if not spec_root.is_dir():
            findings.append(
                f"spec root {spec_root} does not exist -- cannot verify that specs prove the "
                "criteria, and an unverifiable mapping must not read as a pass"
            )
        else:
            cited: set[int] = set()
            for spec in spec_root.rglob("*_spec.rb"):
                for num in ID_RE.findall(spec.read_text(encoding="utf-8", errors="replace")):
                    cited.add(int(num))
            for c in criteria:
                if c.num not in cited:
                    findings.append(
                        f"{where_of(c)}: no spec under {spec_root} cites {c.cid} -- the proving "
                        "spec must map to the criterion, or the criterion is unproven"
                    )

    return findings


def where_of(c: Criterion) -> str:
    return f"{c.cid} (line {c.line_no})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate acceptance criteria, and that specs cite them."
    )
    parser.add_argument("criteria_path", nargs="?", help="docs/acceptance/<branch-slug>.md")
    parser.add_argument(
        "--specs", metavar="DIR",
        help="also require every AC-n to be cited by a spec under DIR (usually `spec`)",
    )
    parser.add_argument("--selftest", action="store_true", help="prove the rules fire AND stay silent")
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_criteria_selftest as st

        return st.run()

    if not args.criteria_path:
        parser.error("criteria_path is required (or pass --selftest)")

    try:
        criteria = parse(Path(args.criteria_path))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    findings = check(criteria, Path(args.specs) if args.specs else None)

    if findings:
        print(
            f"{len(findings)} acceptance-criteria finding(s) in {args.criteria_path} -- "
            "these criteria cannot grade the work:",
            file=sys.stderr,
        )
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nRewrite the criterion, do not soften the check. Every criterion names an action "
            "and an observable; every unit carries an error path.",
            file=sys.stderr,
        )
        return 1

    scope = f", all cited under {args.specs}" if args.specs else ""
    print(f"{len(criteria)} criteria validated{scope}: {args.criteria_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
