#!/usr/bin/env python3
"""Every change that closes an issue brings its QA case, and a fix brings the spec that proves it (#1858, slice 4 of #1853).

The owner's rule (#1853), in their words: "every fix or gap or bug must have a case to test it and help to prevent regression", and "u can't build something without a
way to test it in qa, there must be a test case for it to prove it worked as intended, if not, we are fooling ourself". The rule is unconditional: no feature, fix, gap
or bug closes without a manual catalogue case that proves its intent. Downstream, v1.3.1's five fixes shipped with no catalogue cases until a coordinator noticed.

    python3 check_case_in_diff.py --base origin/dev --closes 12,14 --kind fix          # the issues this PR closes
    python3 check_case_in_diff.py --base origin/dev --closes-from-body body.md --kind feature --body-file body.md
    python3 check_case_in_diff.py --selftest

WHAT IT CHECKS, over the diff `BASE...HEAD` (refs only: no working-tree file is hashed, fsmonitor and external diff are off, so no repository config runs a program):
  1. for EVERY issue the PR closes, at least one catalogue row (`qa/test-cases.csv`, or `--catalogue`) that the diff ADDS OR CHANGES names that issue in its `Source`
     column (`#12`, `defect:#12`, `issue #12`, any separator of space , ; |). A row that already existed at the base and is untouched does not count: the case is for THIS
     change. `#123` is not `#12`.
  2. for `--kind fix` (a fix, a gap or a bug), the diff also adds or changes a spec or test file (a `spec/`, `test/`, `tests/` or `e2e/` directory, or a `_spec`,
     `.spec.`, `.test.`, `_test` file name): the regression spec. With `--body-file`, the PR body must also carry a `Red/green` section saying the spec failed without the
     fix (red) and passes with it (green). Presence only: a script cannot run the spec against the pre-fix tree, so the flow command does that and records the result here.
  A PR that closes no issue has nothing to require (a docs change, a refactor): exit 0 and said.

THE PR BODY IS READ for its closing keywords by `check_registry_closed.closing_numbers` (every GitHub keyword, any case, `#N` and this repository's qualified forms).

Exit codes: 0 clean; 1 findings; 2 COULD NOT CHECK (the base cannot be read, git fails, a body file is missing): the gate runner grades 2 ERROR and 3 not applicable, which
never fails a run, so a check that could not look must not say 3; 3 only when the project has no catalogue (nothing to check against).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_registry_closed as crc  # noqa: E402

CATALOGUE = "qa/test-cases.csv"
SEPARATORS = re.compile(r"[\s,;|]+")
TEST_FILE = re.compile(r"(?:(?:^|/)(?:spec|test|tests|e2e)/|_spec\.|\.spec\.|\.test\.|_test\.)")
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([*GIT, "-C", str(root), *args], capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


def changed_rows(root: Path, base: str, catalogue: str) -> tuple[list[dict] | None, str | None]:
    """The catalogue rows that `base...HEAD` adds or changes, as {column: value}; (None, why) when git cannot say."""
    header_text = (root / catalogue).read_text(encoding="utf-8-sig").splitlines()[:1]
    if not header_text:
        return None, f"{catalogue} is empty"
    header = next(csv.reader(header_text))
    done = git(root, "diff", "--no-ext-diff", "--no-color", "--unified=0", f"{base}...HEAD", "--", catalogue)
    if done.returncode != 0:
        return None, f"git diff {base}...HEAD failed: {done.stderr.strip()[:160]}"
    rows = []
    for line in done.stdout.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        try:
            values = next(csv.reader(io.StringIO(line[1:])))
        except (StopIteration, csv.Error):
            continue
        if values == header:
            continue
        rows.append(dict(zip(header, values)))
    return rows, None


def names_issue(row: dict, number: int) -> bool:
    source = row.get("Source") or ""
    return any(re.fullmatch(rf"(?:[A-Za-z]+:)?#{number}", token.strip("()[]\"'`.")) for token in SEPARATORS.split(source) if token)


def test_files(root: Path, base: str) -> tuple[list[str] | None, str | None]:
    done = git(root, "diff", "--no-ext-diff", "--name-only", f"{base}...HEAD")
    if done.returncode != 0:
        return None, f"git diff --name-only {base}...HEAD failed: {done.stderr.strip()[:160]}"
    return [p for p in done.stdout.splitlines() if TEST_FILE.search(p)], None


def red_green(body: str) -> bool:
    """The body has a `Red/green` section with a line that says red and a line that says green."""
    sections = re.split(r"(?m)^#{1,6}\s+", body)
    for section in sections:
        title, _, rest = section.partition("\n")
        if re.search(r"red\s*/\s*green", title, re.I):
            return bool(re.search(r"\bred\b", rest, re.I)) and bool(re.search(r"\bgreen\b", rest, re.I))
    return False


def check(root: Path, base: str, closes: set[int], kind: str, catalogue: str, body: str | None) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes)."""
    if not (root / catalogue).is_file():
        return 3, [], [f"{catalogue}: no catalogue here, so there is no case to require"]
    if git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").returncode != 0:
        return 2, [], [f"the base {base} cannot be read: fetch it, or name another with --base"]
    if not closes:
        return 0, [], ["this change closes no issue, so no case is required"]
    rows, why = changed_rows(root, base, catalogue)
    if rows is None:
        return 2, [], [why or "could not read the diff"]
    findings = []
    for number in sorted(closes):
        if not any(names_issue(row, number) for row in rows):
            findings.append(f"#{number}: no catalogue case in this diff names it in its Source ({catalogue}): add or update the case that proves the behaviour, with `defect:#{number}` or `#{number}` in `Source`")
    if kind == "fix":
        specs, why = test_files(root, base)
        if specs is None:
            return 2, findings, [why or "could not list the changed files"]
        if not specs:
            findings.append("a fix needs the spec that fails without it: the diff adds or changes no spec or test file (a spec/, test/, tests/ or e2e/ directory, or a _spec, .spec., .test. or _test file)")
        if body is not None and not red_green(body):
            findings.append("the PR body has no `Red/green` section saying the spec failed without the fix (red) and passes with it (green)")
    return (1 if findings else 0), findings, []


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------


def selftest(match: str | None = None) -> int:
    """`match` runs only the rows whose label contains it (the mutation harness runs each mutant on the row it names)."""
    import fixture_git

    failures: list[str] = []
    HEADER = "Test ID,Title,Area,Type,Priority,Status,Source,Notes\n"

    def case(tid: str, source: str) -> str:
        return f'{tid},t,A,Functional,P1,Active,"{source}",\n'

    def row(label: str, base_files: dict[str, str], change: dict[str, str | None], want_code: int, want: str | None, closes: set[int] | None = None, kind: str = "fix",
            body: str | None = None, base_ref: str = "base") -> None:
        if match and match not in label:
            return
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            fixture_git.init(repo)
            for name, text in base_files.items():
                (repo / name).parent.mkdir(parents=True, exist_ok=True)
                (repo / name).write_text(text, encoding="utf-8")
            if base_files:
                fixture_git.run(repo, "add", ".")
            fixture_git.run(repo, "commit", "-q", "--allow-empty", "-m", "base")
            fixture_git.run(repo, "branch", "base")
            for name, text in change.items():
                if text is None:
                    (repo / name).unlink()
                else:
                    (repo / name).parent.mkdir(parents=True, exist_ok=True)
                    (repo / name).write_text(text, encoding="utf-8")
            fixture_git.run(repo, "add", "-A")
            fixture_git.run(repo, "commit", "-q", "--allow-empty", "-m", "change")
            code, found, notes = check(repo, base_ref, closes if closes is not None else {5}, kind, CATALOGUE, body)
        joined = "\n".join([*found, *notes])
        if code != want_code or (want is None and found) or (want is not None and want not in joined):
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:240]!r}")

    base = {CATALOGUE: HEADER + case("TC-1", "REQ-1"), "app.rb": "x\n"}
    SPEC = "spec/app_spec.rb"
    ok_change = {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#5"), SPEC: "it\n"}
    row("a fix with a new case naming the issue and a spec is clean", base, ok_change, 0, None)
    row("a fix whose diff adds no case is a finding", base, {SPEC: "it\n"}, 1, "#5: no catalogue case in this diff names it")
    row("a case naming another issue does not count", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#6"), SPEC: "it\n"}, 1, "#5: no catalogue case")
    row("#55 is not #5 (near miss)", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#55"), SPEC: "it\n"}, 1, "#5: no catalogue case")
    row("a plain #5 token in Source counts", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "#5"), SPEC: "it\n"}, 0, None)
    row("a Source with several tokens counts", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "REQ-2; defect:#5, REQ-3"), SPEC: "it\n"}, 0, None)
    row("a CHANGED existing row that now names the issue counts", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1; defect:#5"), SPEC: "it\n"}, 0, None)
    row("a row that already named the issue at the base and is untouched does not count", {CATALOGUE: HEADER + case("TC-1", "defect:#5"), "app.rb": "x\n"},
        {SPEC: "it\n"}, 1, "#5: no catalogue case")
    row("a deleted case does not count", {CATALOGUE: HEADER + case("TC-1", "defect:#5")}, {CATALOGUE: HEADER, SPEC: "it\n"}, 1, "#5: no catalogue case")
    row("every closed issue needs its own case", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#5"), SPEC: "it\n"}, 1, "#6: no catalogue case", closes={5, 6})
    row("a fix with no spec or test file is a finding", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#5")}, 1, "the spec that fails without it")
    row("a feature needs the case but not a spec file", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#5")}, 0, None, kind="feature")
    for label, path, want_code in (("a test/ directory file is a spec", "test/helper.rb", 0), ("an e2e/ directory file is a spec", "qa/e2e/login.rb", 0),
                                   ("a _spec file is a spec", "lib/thing_spec.rb", 0), ("a docs file named spec is not a spec", "docs/spec.md", 1)):
        row(label, base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + case("TC-2", "defect:#5"), path: "x\n"}, want_code, None if want_code == 0 else "the spec that fails without it")
    BODY_OK = "## Red/green proof\nred: the spec failed on the base (exit 1)\ngreen: it passes on the head\n"
    row("a fix body with a red/green section is clean", base, ok_change, 0, None, body="## What\nx\n\n" + BODY_OK)
    row("a fix body with no red/green section is a finding", base, ok_change, 1, "no `Red/green` section", body="## What\nx\n")
    row("a red/green section that never says green is a finding", base, ok_change, 1, "no `Red/green` section", body="## Red/green proof\nred only\n")
    row("a change that closes no issue needs no case", base, {"app.rb": "y\n"}, 0, None, closes=set())
    row("no catalogue is exit 3, nothing to check against", {"app.rb": "x\n"}, {SPEC: "it\n"}, 3, "no catalogue here")
    row("an unreadable base is exit 2, never a pass", base, ok_change, 2, "cannot be read", base_ref="no-such-base")
    row("a quoted Source with a comma is read as one field", base, {CATALOGUE: HEADER + case("TC-1", "REQ-1") + '"TC-2","a, b",A,F,P1,Active,"defect:#5, REQ-2",\n', SPEC: "it\n"}, 0, None)
    if not match or "closing keywords are read from a body" in match:
        for body, want in (("Fixes #5 and closes #6", {5, 6}), ("Refs #7", set()), ("RESOLVED #8", {8})):
            if crc.closing_numbers(body) != want:
                failures.append(f"closing keywords are read from a body: {body!r} wanted {sorted(want)}, got {sorted(crc.closing_numbers(body))}")
    if failures:
        print("check_case_in_diff selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_case_in_diff selftest: ok (0 failure(s))")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="A change that closes an issue brings its catalogue case, and a fix its spec (#1858).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--base", metavar="REF", help="the branch this change merges into (default: origin/$GITHUB_BASE_REF when set)")
    parser.add_argument("--closes", default="", metavar="N,M", help="the issues this change closes")
    parser.add_argument("--closes-from-body", metavar="FILE", help="read the issues from the PR body's closing keywords")
    parser.add_argument("--kind", choices=("fix", "feature"), default="feature", help="`fix` (a fix, gap or bug) also needs a spec and, with --body-file, a Red/green section")
    parser.add_argument("--catalogue", default=CATALOGUE, help=f"the catalogue (default {CATALOGUE})")
    parser.add_argument("--body-file", metavar="FILE", help="the PR body, for the Red/green section of a fix")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the rows whose label contains TEXT (the mutation harness)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match)
    root = Path(args.root).resolve()
    try:
        closes = {int(x) for x in re.split(r"[,\s]+", args.closes.strip()) if x}
        if args.closes_from_body:
            closes |= crc.closing_numbers(Path(args.closes_from_body).read_text(encoding="utf-8-sig"), crc.repo_slug(root))
        body = Path(args.body_file).read_text(encoding="utf-8-sig") if args.body_file else None
    except (ValueError, OSError) as exc:
        print(f"check_case_in_diff: {exc} (exit 2)", file=sys.stderr)
        return 2
    import os
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "")
    if not base:
        print("check_case_in_diff: no --base and no GITHUB_BASE_REF: name the branch this change merges into (exit 2, not a pass)", file=sys.stderr)
        return 2
    code, found, notes = check(root, base, closes, args.kind, args.catalogue, body)
    for line in found:
        print(line)
    for note in notes:
        print(f"note: {note}")
    print(f"check_case_in_diff: {'ok' if code == 0 else 'no catalogue (exit 3, nothing to check against)' if code == 3 else 'could not check (exit 2, not a pass)' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
