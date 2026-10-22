#!/usr/bin/env python3
"""Reject acceptance criteria that cannot fail, and specs that do not prove them.

Run:  python3 check_criteria.py docs/product/acceptance/<unit-slug>.md
      python3 check_criteria.py docs/product/acceptance/<slug>.md --specs spec
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

SECURITY (#2118). A unit whose threat model (docs/security/threat-models/<slug>.md, each row has an `ID` cell, `TM-n`) has `mitigate`
    rows must carry a `[security]` criterion citing each such row in the criterion's citation slot, `(TM-n)` or `covers: TM-n` at its end
    (a tag or id inside an HTML comment or a code span, or a mention elsewhere in the sentence, does not count); a `[security]` criterion citing no row, or a row that is not
    a `mitigate` row of the model, is a finding. Without a model nothing changes: the step fires only when security_scope.py does (#2117).

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

# RUBY'S OWN FAILURE VOCABULARY (#1189). Raising is the commonest way a Ruby unit expresses an error
# path, and none of the words above covered it: a criterion stating "raises ArgumentError on fewer
# than two segments" -- a real, tested, mutation-proved error path -- was reported as having none,
# which pressures the author into inventing a criterion that satisfies the detector and asserts
# nothing.
#
# "raise" CANNOT BE A PLAIN HINT, because in a domain app it is ordinary vocabulary: a requester
# RAISES a request, and a request shows "raised 8 Sep". A bare `raise` would make those count as
# error paths, and a unit with no real one would pass. So the verb counts only with WHAT is raised --
# an exception class (capitalised, case-sensitive) or the words error/exception. `rescue` and
# `exception` have no domain sense and count alone.
#
# CRITERIA ARE MARKDOWN (#1209), so the class usually arrives quoted -- "raises `ArgumentError`",
# "raises **ArgumentError**" -- or in the passive, "`ArgumentError` is raised". Delimiters may sit
# between the verb and the class, the passive counts with a capitalised subject, and a class named
# `...Error` / `...Exception` counts wherever it appears: that suffix is Ruby vocabulary, not domain.
RUBY_FAILURE = re.compile(
    r"\b(?i:raise[sd]?)\s+(?:(?i:an?)\s+)?[`*_]*(?:[A-Z][\w:]*|(?i:error|exception)\b)"
    r"|\b[A-Z][\w:]*[`*_]*\s+(?:is|are|gets?|be|being)\s+raised\b"
    r"|\b[A-Z][\w:]*(?:Error|Exception)\b"
    r"|\b(?i:rescue[sd]?)\b|\b(?i:exception)\b"
)


SECURITY_TAG = "[security]"
# A citation counts only in the criterion's own slot: `(TM-1)`, `(TM-1, TM-3)` or `covers: TM-1` at the END of the line. `[security] (unlike TM-1 ...)`,
# a TM-n inside a comment or a code span, or one mentioned mid-sentence is not a citation (review of #2133).
_TM_LIST = r"TM-\d+(?:\s*,\s*TM-\d+)*"
SLOT_RE = re.compile(rf"(?:\(\s*({_TM_LIST})\s*\)|\bcovers:\s*({_TM_LIST}))\s*[.;]?\s*$", re.I)
HIDDEN_RE = re.compile(r"<!--.*?-->|`[^`\n]*`", re.S)


def _visible(text: str) -> str:
    return HIDDEN_RE.sub(" ", text)


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


NO_COMMENTS = "no HTML comments in security tables or criteria; delete the row or criterion instead"


def _strict_lines(text: str, path: Path) -> str:
    """The criteria file in the one shape we read, or Unusable (#2213 adversary: hand-parsed Markdown always has another edge, so a shape
    outside this one is refused, never interpreted). No `<!--` anywhere; a fence closes on a line holding only its marker, and is closed
    before the end; no criterion indented as code. Lines inside a closed fence are blanked: a renderer shows them as code, not criteria."""
    if "<!--" in text:
        raise Unusable(f"{path}: {NO_COMMENTS}")
    out, fence, opened_at = [], "", 0
    for n, line in enumerate(text.split("\n"), start=1):
        # A fence anywhere but column 0 (indented, or after `>` or a list marker) means something different in each container, so it is
        # refused, never interpreted (#2213 adversary: a fence inside a blockquote hid a live-looking criterion from a renderer).
        inner = re.sub(r"^(?:[ \t]*>|[ \t]*(?:[-*+]|\d+[.)])(?=[ \t]))+[ \t]*", "", line)
        if re.match(r"\s+(?:`{3,}|~{3,})", line) or (inner != line and re.match(r"`{3,}|~{3,}", inner)):
            raise Unusable(f"{path}:{n} write a fence at the start of its line: an indented, quoted or listed one means different things in different containers")
        mark = re.match(r"(`{3,}|~{3,})(.*)$", line)
        if not fence and mark and mark.group(1)[0] == "`" and "`" in mark.group(2):
            raise Unusable(f"{path}:{n} a backtick in a backtick fence's info string makes it no fence to a renderer: remove it")
        if fence:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence):
                if mark.group(2).strip():
                    raise Unusable(f"{path}:{n} a fence closes on a line holding only its marker, got `{line.strip()[:40]}`")
                fence = ""
            out.append("")
        elif mark:
            fence, opened_at = mark.group(1), n
            out.append("")
        else:
            # Any indentation or container: a list item's continuation can open an HTML block at four spaces or a tab (security review).
            if re.match(r"[ \t]*<(?:[A-Za-z][\w-]*|/[A-Za-z]|[!?])", inner):
                raise Unusable(f"{path}:{n} no raw HTML blocks in a criteria file (`{line.strip()[:30]}`): a renderer and this check read them differently")
            if re.match(r"(?: {4}|\t)", line) and (BOLD_ID_RE.search(line) or DEF_RE.match(line.strip())):
                raise Unusable(f"{path}:{n} a criterion indented four spaces is a code block to a renderer: write it at the start of the line")
            out.append(line)
    if fence:
        raise Unusable(f"{path}:{opened_at} a fence opened here never closes, so everything after it is code")
    return "\n".join(out)


def parse(path: Path) -> list[Criterion]:
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    unit = ""
    out: list[Criterion] = []
    for line_no, raw in enumerate(_strict_lines(path.read_text(encoding="utf-8"), path).splitlines(), start=1):
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
    return any(h in low for h in ERROR_HINTS) or bool(RUBY_FAILURE.search(text))


def check_security(criteria: list[Criterion], rows: list[tuple[int, str, str]]) -> list[str]:
    """Map `[security]` criteria to the `mitigate` rows of the unit's threat model, both ways."""
    findings: list[str] = []
    mitigate = {n: threat for n, threat, decision in rows if decision == "mitigate"}
    known = {n for n, _, _ in rows}
    tagged = [c for c in criteria if SECURITY_TAG in _visible(c.text).lower()]
    cited: set[int] = set()
    for c in tagged:
        slot = SLOT_RE.search(_visible(c.text))
        refs = {int(n) for n in re.findall(r"TM-(\d+)", slot.group(1) or slot.group(2), re.I)} if slot else set()
        if not refs:
            findings.append(f"{where_of(c)}: a {SECURITY_TAG} criterion cites no threat-model row -- end it with `(TM-n)` or `covers: TM-n`")
        for n in sorted(refs):
            if n not in known:
                findings.append(f"{where_of(c)}: cites TM-{n}, which is not a row of the threat model ({len(known)} row(s))")
            elif n not in mitigate:
                findings.append(f"{where_of(c)}: cites TM-{n}, which is not a `mitigate` row -- only a mitigation is proven by a criterion")
        cited |= refs
    for n, threat in sorted(mitigate.items()):
        if n not in cited:
            findings.append(
                f"threat model row TM-{n} (`{threat[:50]}`) is `mitigate` and no {SECURITY_TAG} criterion cites it -- "
                "a requirement nobody turned into a criterion is not proven by the spec"
            )
    return findings


def check(criteria: list[Criterion], spec_root: Path | None = None,
          threat_rows: list[tuple[int, str, str]] | None = None) -> list[str]:
    findings: list[str] = []
    if threat_rows:
        findings.extend(check_security(criteria, threat_rows))

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


def default_threat_model(criteria_path: Path) -> tuple[Path | None, str]:
    """`docs/security/threat-models/<slug>.md` at the repository root above the criteria file (the first directory holding `.git`),
    wherever under the tree the criteria sit; `(None, why)` when there is no repository root."""
    start = criteria_path.resolve().parent
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d / "docs" / "security" / "threat-models" / criteria_path.name, ""
    return None, f"no repository root (a directory holding .git) above {criteria_path}, so no default threat model"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate acceptance criteria, and that specs cite them."
    )
    parser.add_argument("criteria_path", nargs="?", help="docs/product/acceptance/<unit-slug>.md")
    parser.add_argument(
        "--specs", metavar="DIR",
        help="also require every AC-n to be cited by a spec under DIR (usually `spec`)",
    )
    parser.add_argument(
        "--threat-model", metavar="FILE",
        help="the unit's threat model; default docs/security/threat-models/<slug>.md at the repository root above the criteria file; a missing default is reported as a skipped check",
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

    if args.threat_model:
        model, why = Path(args.threat_model), ""
    else:
        model, why = default_threat_model(Path(args.criteria_path))
    rows: list[tuple[int, str, str]] = []
    if model is not None and model.is_file():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_threat_model as tm

        model_text = model.read_text(encoding="utf-8")
        rows = tm.threat_rows(model_text)
        # threat_rows skips a row it cannot read, and a skipped row would drop its requirement silently: a model check_threat_model
        # does not pass is refused whole (#2213 adversary).
        table_findings = tm.check(model_text)[0]
        if table_findings:
            print(f"UNUSABLE: {model} has threat rows this check cannot trust -- fix them first:", file=sys.stderr)
            for f in table_findings:
                print(f"  - {f}", file=sys.stderr)
            return 2
        if not rows:
            print(f"UNUSABLE: {model} exists but has no readable `## Threats` table (ID | Threat | STRIDE | Component | Decision | Reason) -- "
                  "an unreadable model is not a clean one", file=sys.stderr)
            return 2
    elif args.threat_model:
        print(f"UNUSABLE: no such threat model: {model}", file=sys.stderr)
        return 2
    else:
        # Said out loud (#2213 review): a silent skip reads as "no security criteria owed" when the model was simply not found.
        others = sorted(p.name for p in model.parent.glob("*.md")) if model is not None and model.parent.is_dir() else []
        hint = f" ({len(others)} other model(s) there: {', '.join(others[:5])}; is one this unit's?)" if others else ""
        print(f"security check skipped: {why or f'no threat model at {model}'}{hint}; pass --threat-model FILE if the unit has one", file=sys.stderr)
    findings = check(criteria, Path(args.specs) if args.specs else None, rows)

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
