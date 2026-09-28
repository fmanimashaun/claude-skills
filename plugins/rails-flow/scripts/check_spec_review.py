#!/usr/bin/env python3
"""Check what the spec review claims against the acceptance file and the diff it reviewed (#1370).

Run:  python3 check_spec_review.py --acceptance docs/product/acceptance/<slug>.md \\
          --findings docs/evidence/reviews/prs/<branch-slug>/spec-reviewer-findings.jsonl --base <base> [--verdict CLEAN|BLOCKED]
      python3 check_spec_review.py --selftest

WHY. `check_criteria.py --specs` proves every `AC-n` is cited by a spec, and feature.md's mutation
step proves a citing spec can fail. Neither reads the diff against the criterion's TEXT, so two
defects pass every mechanical gate: behaviour nobody asked for, and a criterion that is cited,
tested and green but built against a misreading of it. `spec-reviewer` is the judgement pass that
looks for those. This script is the mechanical half of it: it cannot judge the reading, but it can
refuse a review whose citations do not exist.

WHAT THIS GUARANTEES, for every record whose `pass` is `spec-reviewer`:
    * its `category` is one of CATEGORIES;
    * a criterion finding (missing, partial, misread) names its criterion in the signature,
      `<category>:AC-n`, and that `AC-n` is defined in the acceptance file -- a reviewer that
      invents a criterion is caught here, not by the person reading the report;
    * an unasked-for finding names a `file` the diff really changed, INCLUDING untracked new files
      (a reviewer reading only `git diff` misses those, #1341);
    * with --verdict CLEAN, no blocking (P1/P2) spec finding exists -- CLEAN beside a blocking
      finding is the verdict contradicting its own list.

WHAT IT DOES NOT: judge whether a finding is right, or whether a criterion with no finding was
really met. That is the reviewer's judgement, and a count cannot stand in for it.

Exit codes: 0 clean · 1 findings · 2 unusable (no acceptance criteria, no findings file, bad base).
Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_criteria  # noqa: E402  -- one criteria parser, never a second
import findings as findings_mod  # noqa: E402  -- one record shape, never a second

PASS = "spec-reviewer"
CRITERION_BOUND = ("spec-missing", "spec-partial", "spec-misread")
UNASKED = "spec-unasked"
CATEGORIES = CRITERION_BOUND + (UNASKED,)
BLOCKING = ("P1", "P2")
SIGNATURE_AC = re.compile(r"^(?P<cat>[a-z-]+):AC-(?P<num>\d+)\b")


class Unusable(Exception):
    """This check could not run -- exit 2, never 1 (the split `findings.py` makes too)."""


def changed_files(root: Path, base: str) -> set[str]:
    """Everything the review was given: committed on the branch, uncommitted, and untracked."""
    def git(*args: str) -> str:
        out = subprocess.run(("git",) + args, cwd=root, capture_output=True, text=True)
        if out.returncode != 0:
            raise Unusable(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return out.stdout
    git("rev-parse", "--verify", "-q", f"{base}^{{commit}}")
    files = set(git("diff", "--name-only", f"{base}...HEAD").split("\n"))
    files |= set(git("diff", "--name-only", "HEAD").split("\n"))
    files |= set(git("ls-files", "--others", "--exclude-standard").split("\n"))
    return {f for f in files if f}


def run(acceptance: Path, findings_path: Path, changed: set[str], verdict: str | None) -> list[str]:
    """The whole decision. main() and the selftest both come through here."""
    try:
        criteria = check_criteria.parse(acceptance)
    except check_criteria.Unusable as exc:
        raise Unusable(str(exc)) from exc
    if not criteria:
        raise Unusable(f"{acceptance} defines no criteria, so there is nothing to review against")
    defined = {c.cid for c in criteria}

    if not findings_path.is_file():
        raise Unusable(f"no findings file at {findings_path}: the spec pass writes it even when "
                       f"it finds nothing, so its absence means the pass did not run")
    try:
        loaded = findings_mod.load(findings_path)
    except findings_mod.Unusable as exc:
        raise Unusable(str(exc)) from exc
    records = [r for r in loaded if r.get("pass") == PASS]
    # The file is the spec pass's OWN (#1393 review). Records from another pass and none from this one
    # means it is the wrong file, or another pass wrote here and this one never ran: exit 2, never a
    # clean exit 0. An EMPTY file is a spec pass that ran and found nothing.
    if loaded and not records:
        raise Unusable(f"{findings_path} holds {len(loaded)} record(s) and none from {PASS}: this is "
                       f"another pass's file, or the spec pass never ran")

    problems = [f"schema: {p}" for p in findings_mod.validate(records)]
    for r in records:
        where = f"{r.get('id', '?')} (line {r.get('_line', '?')})"
        category = r.get("category")
        if category not in CATEGORIES:
            problems.append(f"{where}: category {category!r} is not one of {', '.join(CATEGORIES)}")
            continue
        if category in CRITERION_BOUND:
            m = SIGNATURE_AC.match(str(r.get("signature", "")))
            cited = f"AC-{m.group('num')}" if m and m.group("cat") == category else None
            if cited is None:
                problems.append(f"{where}: a {category} finding must be signed `{category}:AC-n`, "
                                f"got {r.get('signature')!r}")
            elif cited not in defined:
                problems.append(f"{where}: cites {cited}, which {acceptance.name} does not "
                                f"define (it defines {', '.join(sorted(defined, key=lambda c: int(c[3:])))})")
        elif r.get("file") not in changed:
            problems.append(f"{where}: flags unasked-for behaviour in {r.get('file')!r}, which this "
                            f"diff does not change")
    if verdict == "CLEAN":
        blocking = [r.get("id", "?") for r in records if r.get("severity") in BLOCKING]
        if blocking:
            problems.append(f"verdict CLEAN contradicts {len(blocking)} blocking spec finding(s): "
                            f"{', '.join(blocking)}")
    return problems


# --------------------------------------------------------------------------- selftest

ACCEPTANCE = """# Acceptance — invoices

## Totals

- **AC-1** Given an invoice with two line items, when it is saved, then its total is their sum.
- **AC-2** Given an invoice with no line items, when it is submitted, then it is rejected with an error. [error]
"""


def _rec(i: int, category: str, signature: str, file: str = "app/models/invoice.rb",
         severity: str = "P2", pass_: str = PASS) -> str:
    import json
    return json.dumps({"id": f"spec-{i:03d}", "pass": pass_, "severity": severity,
                       "category": category, "file": file, "signature": signature,
                       "issue": "..."})


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        def git(*a: str) -> None:
            subprocess.run(("git",) + a, cwd=root, check=True, capture_output=True)
        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.com"); git("config", "user.name", "t")
        (root / "app/models").mkdir(parents=True)
        (root / "app/models/invoice.rb").write_text("class Invoice; end\n")
        (root / "app/models/untouched.rb").write_text("class Untouched; end\n")
        git("add", "."); git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "feature")
        (root / "app/models/invoice.rb").write_text("class Invoice; def total; end; end\n")
        git("commit", "-qam", "change")
        (root / "app/models/brand_new.rb").write_text("class BrandNew; end\n")   # untracked

        changed = changed_files(root, "main")
        check_that("the committed change is in the diff", "app/models/invoice.rb" in changed, changed)
        check_that("an UNTRACKED new file is in the diff (#1341)", "app/models/brand_new.rb" in changed, changed)
        check_that("CONTROL: an untouched file is not in the diff", "app/models/untouched.rb" not in changed)
        try:
            changed_files(root, "no-such-base")
            check_that("a base that does not resolve is unusable", False)
        except Unusable:
            pass

        acc = root / "acceptance.md"
        acc.write_text(ACCEPTANCE)
        fj = root / "findings.jsonl"

        def verdict_of(lines: list[str], verdict: str | None = None) -> list[str]:
            fj.write_text("\n".join(lines) + "\n")
            return run(acc, fj, changed, verdict)

        p = verdict_of([_rec(1, "spec-misread", "spec-misread:AC-1 total ignores discounts")])
        check_that("CONTROL: a finding citing a defined criterion passes", p == [], p)
        p = verdict_of([_rec(1, "spec-missing", "spec-missing:AC-9")])
        check_that("a finding citing an undefined criterion is refused", any("AC-9" in x for x in p), p)
        p = verdict_of([_rec(1, "spec-missing", "total-is-wrong")])
        check_that("a criterion finding with no AC in its signature is refused", any("signed" in x for x in p), p)
        p = verdict_of([_rec(1, "spec-partial", "spec-missing:AC-1")])
        check_that("a signature whose category disagrees with the record is refused", any("signed" in x for x in p), p)
        p = verdict_of([_rec(1, "scope", "scope:x")])
        check_that("an unknown category is refused", any("category" in x for x in p), p)

        p = verdict_of([_rec(1, UNASKED, "spec-unasked:csv-export", file="app/models/invoice.rb")])
        check_that("CONTROL: unasked-for behaviour in a changed file passes", p == [], p)
        p = verdict_of([_rec(1, UNASKED, "spec-unasked:new-model", file="app/models/brand_new.rb")])
        check_that("CONTROL: unasked-for behaviour in an untracked new file passes", p == [], p)
        p = verdict_of([_rec(1, UNASKED, "spec-unasked:elsewhere", file="app/models/untouched.rb")])
        check_that("unasked-for behaviour in a file the diff does not change is refused",
                   any("does not change" in x for x in p), p)

        p = verdict_of([_rec(1, "spec-missing", "spec-missing:AC-2", severity="P2")], "CLEAN")
        check_that("CLEAN beside a blocking spec finding is refused", any("contradicts" in x for x in p), p)
        p = verdict_of([_rec(1, "spec-missing", "spec-missing:AC-2", severity="P3")], "CLEAN")
        check_that("CONTROL: CLEAN beside an advisory (P3) finding passes", p == [], p)
        p = verdict_of([_rec(1, "spec-missing", "spec-missing:AC-2", severity="P2")], "BLOCKED")
        check_that("CONTROL: BLOCKED beside a blocking finding passes", p == [], p)

        p = verdict_of([_rec(1, "authz", "missing-scope:X", pass_="code-reviewer"),
                        _rec(2, "spec-misread", "spec-misread:AC-1")])
        check_that("CONTROL: another pass's records beside spec records are not judged here", p == [], p)
        try:
            verdict_of([_rec(1, "authz", "missing-scope:X", pass_="code-reviewer")], "CLEAN")
            check_that("a file holding only another pass's records is unusable, not a clean spec review", False)
        except Unusable:
            pass
        check_that("CONTROL: an empty file is a spec pass that ran and found nothing",
                   verdict_of([""], "CLEAN") == [])
        p = verdict_of([_rec(1, "spec-misread", "spec-misread:AC-1"), _rec(1, "spec-misread", "spec-misread:AC-2")])
        check_that("the shared record schema still applies (duplicate id)", any("duplicate id" in x for x in p), p)

        try:
            run(acc, root / "missing.jsonl", changed, None)
            check_that("a missing findings file is unusable, not clean", False)
        except Unusable:
            pass
        empty = root / "empty.md"
        empty.write_text("# nothing here\n")
        try:
            run(empty, fj, changed, None)
            check_that("an acceptance file with no criteria is unusable", False)
        except Unusable:
            pass

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_spec_review selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--acceptance", type=Path)
    ap.add_argument("--findings", type=Path)
    ap.add_argument("--base", help="the ref the branch merges into")
    ap.add_argument("--verdict", choices=("CLEAN", "BLOCKED"))
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.acceptance and args.findings and args.base):
        ap.error("--acceptance, --findings and --base are required")
    try:
        problems = run(args.acceptance, args.findings, changed_files(Path.cwd(), args.base), args.verdict)
    except Unusable as exc:
        print(f"check_spec_review: UNUSABLE — {exc}")
        return 2
    if problems:
        print(f"{len(problems)} spec-review finding(s):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("spec review: every citation resolves and the verdict agrees with the findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
