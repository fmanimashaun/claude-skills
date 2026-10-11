#!/usr/bin/env python3
"""No stale registry rows: a requirement that points at a CLOSED issue says so (#1857, slice 3 of #1853).

WHY. Downstream (Retask, #1853) the requirement registry was last edited the day the audit issue closed. The gap fixes landed afterwards, but 117 rows
still said partial, missing or deviates and pointed at the closed audit issue, so the status report showed fixed gaps as open. A registry is only
as true as the last PR that touched it: the PR that closes an issue must update the rows that point at it, in the same diff.

    python3 check_registry_closed.py                    # rows that point at a closed issue and have not been updated
    python3 check_registry_closed.py --closes 12,14     # a PR that will close #12 and #14: rows pointing at them must already be updated
    python3 check_registry_closed.py --selftest

THE REGISTRY is the project's `qa/requirements.yml` (or the `registry:` key under `requirements:` in qa/qa.config.yml, or `--registry PATH`), the file qa-flow's
`check_requirements.py` gates: one entry per requirement, every line `key: <JSON value>`, `- id:` opening an entry. This check reads one optional key,
`issue` (a JSON number: the issue that fixes the requirement, or tracks the question), plus `status` and `closed`. It has its OWN small reader because plugins
install alone and rails-flow cannot import qa-flow; the maintainer gate `registry reader parity` keeps the two readers answering the same.

A ROW IS STALE when its `issue` is closed (on GitHub, or named by `--closes`) and the row is not `status: "done"` with `closed: true`. The fix is to update the
row in the closing PR: flip the status and add `closed: true` once the requirement is proven, or point `issue` at the issue that now tracks the rest. A row that
says `closed: true` while its issue is still open is also a finding: the row claims what GitHub does not. One `gh issue view` per distinct issue, at most 200.

Exit codes: 0 clean (or no row carries an issue), 1 findings, 2 the registry is unreadable, 3 could not check (no registry, `gh` missing or failing, more than
200 distinct issues): said, and never a pass.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REGISTRY = "qa/requirements.yml"
LIMIT = 200


class Gh:
    """The one read this gate makes. Subclassed by the selftest, never mocked at the subprocess."""

    def available(self) -> bool:
        return shutil.which("gh") is not None

    def state(self, number: int) -> str | None:
        """OPEN, CLOSED, or None when the issue does not exist; RuntimeError when GitHub could not be read."""
        done = subprocess.run(["gh", "issue", "view", str(number), "--json", "state", "-q", ".state"], capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        if done.returncode != 0:
            if "Could not resolve" in done.stderr or "not found" in done.stderr.lower():
                return None
            raise RuntimeError(f"gh issue view {number} failed: {done.stderr.strip()[:160]}")
        return done.stdout.strip() or None


def registry_path(root: Path, flag: str | None) -> str:
    """`--registry`, else `registry:` under `requirements:` in qa/qa.config.yml, else qa/requirements.yml. Always a path inside the project."""
    chosen = flag
    config = root / "qa" / "qa.config.yml"
    if not chosen and config.is_file():
        inside = False
        for raw in config.read_text(encoding="utf-8-sig").splitlines():
            if re.match(r"^requirements:\s*(#.*)?$", raw):
                inside = True
            elif inside and re.match(r"^\S", raw):
                inside = False
            elif inside:
                found = re.match(r"^\s+registry:\s*[\"']?([^\"'#\s]+)", raw)
                if found:
                    chosen = found.group(1)
    chosen = chosen or REGISTRY
    if not (root / chosen).resolve().is_relative_to(root.resolve()):
        raise ValueError(f"the registry path {chosen!r} must be inside the project")
    return chosen


def load(root: Path, registry: str) -> tuple[list[dict], list[str]]:
    """The registry's entries and the problems found reading it (the same grammar check_requirements.py reads)."""
    path, problems, entries = root / registry, [], []
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.match(r"^(- |  )([a-z_]+): (.*)$", raw)
        if not match:
            problems.append(f"{registry}:{number}: not a `key: <JSON value>` line: {raw[:60]!r}")
            continue
        starts, key, text = match.groups()
        try:
            value = json.loads(text)
        except ValueError:
            problems.append(f"{registry}:{number}: the value of `{key}` is not JSON: {text[:40]!r}")
            continue
        if starts == "- ":
            entries.append({"_line": number})
        if not entries:
            problems.append(f"{registry}:{number}: a field before the first `- id:` entry")
            continue
        entries[-1][key] = value
    return entries, problems


def check(root: Path, registry: str, closes: set[int], gh: Gh) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes)."""
    path = root / registry
    if not path.is_file():
        return 3, [], [f"{registry}: no registry here, so nothing was checked"]
    entries, problems = load(root, registry)
    if problems:
        return 2, problems, []
    findings: list[str] = []
    rows = []
    for entry in entries:
        issue = entry.get("issue")
        if issue is None:
            continue
        if isinstance(issue, bool) or not isinstance(issue, int):
            findings.append(f"{registry}:{entry['_line']}: {entry.get('id')}: `issue` must be a number, got {issue!r}")
            continue
        rows.append((entry, issue))
    numbers = sorted({issue for _, issue in rows})
    if not numbers:
        return (1 if findings else 0), findings, []
    asked = [n for n in numbers if n not in closes]
    if len(asked) > LIMIT:
        return 3, findings, [f"{len(asked)} distinct issues, more than the {LIMIT} one `gh` read each is allowed"]
    if asked and not gh.available():
        return 3, findings, ["`gh` is not on PATH, so whether the issues the rows point at are closed could not be read"]
    state: dict[int, str | None] = {n: "CLOSED" for n in numbers if n in closes}
    try:
        for n in asked:
            state[n] = gh.state(n)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return 3, findings, [f"could not read an issue's state: {exc}"]
    for entry, issue in rows:
        rid, where = entry.get("id"), f"{registry}:{entry['_line']}"
        closed = state.get(issue) == "CLOSED"
        updated = entry.get("status") == "done" and entry.get("closed") is True
        if state.get(issue) is None:
            findings.append(f"{where}: {rid} points at #{issue}, which does not exist")
        elif closed and not updated:
            by = " (closed by this PR)" if issue in closes else ""
            findings.append(f"{where}: {rid} points at #{issue}, which is closed{by}, but the row says status {entry.get('status')!r}"
                            f"{'' if entry.get('closed') is True else ' without `closed: true`'}: update it in this PR (status `done` and `closed: true` once proven, or point `issue` at the issue that tracks the rest)")
        elif not closed and entry.get("closed") is True:
            findings.append(f"{where}: {rid} says `closed: true` but #{issue} is still open")
    return (1 if findings else 0), findings, []


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------


class FakeGh(Gh):
    def __init__(self, states: dict[int, str | None], broken: bool = False, absent: bool = False):
        self.states, self.broken, self.absent, self.asked = states, broken, absent, []

    def available(self) -> bool:
        return not self.absent

    def state(self, number: int) -> str | None:
        self.asked.append(number)
        if self.broken:
            raise RuntimeError("gh issue view failed: HTTP 502")
        return self.states.get(number)


def selftest(match: str | None = None) -> int:
    """`match` runs only the rows whose label contains it (the mutation harness runs each mutant on the row it names)."""
    failures: list[str] = []

    def entry(rid: str, status: str = "partial", extra: str = "") -> str:
        return f'- id: "{rid}"\n  area: "A"\n  requirement: "text"\n  status: "{status}"\n{extra}'

    def row(label: str, text: str, gh: FakeGh, want_code: int, want: str | None, closes: set[int] | None = None, files: dict[str, str] | None = None) -> None:
        if match and match not in label:
            return
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, body in {REGISTRY: "# rows: 1\n" + text, **(files or {})}.items():
                if body is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(body, encoding="utf-8")
            code, found, notes = check(root, registry_path(root, None), closes or set(), gh)
        joined = "\n".join([*found, *notes])
        if code != want_code or (want is None and found) or (want is not None and want not in joined):
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:220]!r}")

    gh = FakeGh({10: "CLOSED", 11: "OPEN"})
    row("a partial row pointing at a closed issue is stale", entry("R-1", "partial", "  issue: 10\n"), gh, 1, "R-1 points at #10, which is closed")
    row("a done row with closed: true is up to date", entry("R-1", "done", "  issue: 10\n  closed: true\n"), gh, 0, None)
    row("a done row WITHOUT closed: true is still stale", entry("R-1", "done", "  issue: 10\n"), gh, 1, "without `closed: true`")
    row("closed: true with a status that is not done is stale (near miss: the flag alone is not the update)", entry("R-1", "partial", "  issue: 10\n  closed: true\n"), gh, 1,
        "which is closed")
    row("a row pointing at an open issue is fine", entry("R-1", "partial", "  issue: 11\n"), gh, 0, None)
    row("closed: true on a row whose issue is open is a finding", entry("R-1", "done", "  issue: 11\n  closed: true\n"), gh, 1, "is still open")
    row("a row with no issue is not checked", entry("R-1", "missing"), FakeGh({}), 0, None)
    row("a row whose issue does not exist is a finding", entry("R-1", "partial", "  issue: 99\n"), gh, 1, "which does not exist")
    row("an issue that is not a number is a finding", entry("R-1", "partial", '  issue: "12"\n'), gh, 1, "`issue` must be a number")
    row("a boolean is not an issue number", entry("R-1", "partial", "  issue: true\n"), gh, 1, "`issue` must be a number")
    row("--closes: a row pointing at an issue this PR closes must already be updated", entry("R-1", "partial", "  issue: 11\n"), gh, 1, "closed by this PR", closes={11})
    row("--closes: an updated row is clean", entry("R-1", "done", "  issue: 11\n  closed: true\n"), gh, 0, None, closes={11})
    asked = FakeGh({11: "OPEN"})
    row("--closes issues are not asked of GitHub", entry("R-1", "done", "  issue: 11\n  closed: true\n") + entry("R-2", "done", "  issue: 12\n  closed: true\n"), asked, 0, None, closes={11, 12})
    if not match or "are not asked of GitHub" in match:
        if asked.asked:
            failures.append(f"--closes issues are not asked of GitHub: asked {asked.asked}")
    twice = FakeGh({10: "CLOSED"})
    row("one read per distinct issue", entry("R-1", "done", "  issue: 10\n  closed: true\n") + entry("R-2", "done", "  issue: 10\n  closed: true\n"), twice, 0, None)
    if not match or "one read per distinct issue" in match:
        if twice.asked != [10]:
            failures.append(f"one read per distinct issue: asked {twice.asked}")
    row("no registry is exit 3, never a pass", "", FakeGh({}), 3, "no registry here", files={REGISTRY: None})
    row("a broken registry line is exit 2", "- id: R-1\n", FakeGh({}), 2, "is not JSON")
    row("gh missing is exit 3, never a pass", entry("R-1", "partial", "  issue: 10\n"), FakeGh({}, absent=True), 3, "`gh` is not on PATH")
    row("gh failing is exit 3, never a pass", entry("R-1", "partial", "  issue: 10\n"), FakeGh({}, broken=True), 3, "could not read an issue's state")
    row("gh is not needed when --closes names every issue", entry("R-1", "partial", "  issue: 10\n"), FakeGh({}, absent=True), 1, "closed by this PR", closes={10})
    row("the registry path comes from qa.config.yml", entry("R-1", "partial", "  issue: 10\n"), gh, 1, "R-1 points at #10",
        files={REGISTRY: None, "qa/qa.config.yml": 'requirements:\n  registry: "docs/reqs.yml"   # mine\n', "docs/reqs.yml": "# rows: 1\n" + entry("R-1", "partial", "  issue: 10\n")})
    many = "".join(entry(f"R-{i}", "done", f"  issue: {1000 + i}\n  closed: true\n") for i in range(LIMIT + 1))
    row("more than the limit of distinct issues is exit 3", many, FakeGh({}), 3, "more than the 200")
    if not match or "the registry path must stay inside the project" in match:
        with tempfile.TemporaryDirectory() as td:
            try:
                registry_path(Path(td), "../elsewhere.yml")
                failures.append("the registry path must stay inside the project: ../elsewhere.yml was accepted")
            except ValueError:
                pass
    if failures:
        print("check_registry_closed selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_registry_closed selftest: ok (0 failure(s))")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="No registry row points at a closed issue without being updated (#1857).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--registry", metavar="PATH", help="the registry (default: `requirements: registry:` in qa/qa.config.yml, else qa/requirements.yml)")
    parser.add_argument("--closes", metavar="N,M", default="", help="the issues the PR will close (its `Fixes #n` lines): rows pointing at them must already be updated")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the rows whose label contains TEXT (the mutation harness)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match)
    try:
        closes = {int(x) for x in re.split(r"[,\s]+", args.closes.strip()) if x}
        root = Path(args.root).resolve()
        registry = registry_path(root, args.registry)
    except ValueError as exc:
        print(f"check_registry_closed: {exc} (exit 2)", file=sys.stderr)
        return 2
    code, found, notes = check(root, registry, closes, Gh())
    for line in found:
        print(line)
    for note in notes:
        print(f"note: {note}")
    print(f"check_registry_closed: {'ok' if code == 0 else 'could not check (exit 3, not a pass)' if code == 3 else 'could not read the registry' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
