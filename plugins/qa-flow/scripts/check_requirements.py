#!/usr/bin/env python3
"""The requirement-to-case gate: every requirement is named, by id, in an ACTIVE test case (#1855, slice 1 of #1853).

WHY. The owner's rule (#1853): "we should have 100% test case" and "u can't build something without a way to test it in qa". Downstream, 0 of 426
registry requirements were named by any of 923 catalogue cases, so coverage could not even be shown; the registry and the catalogue were two lists
with no link. Retask's `scripts/prd_requirements.py` (Retask #1578) is the reference implementation; this one is stack-neutral: no RSpec tags, the
link is the catalogue's own `Source` column, which `/qa-flow:cases` already fills.

    python3 check_requirements.py                    # the gate
    python3 check_requirements.py --uncased          # the requirement ids with no active case, one per line (what /qa-flow:cases should author)
    python3 check_requirements.py --base origin/dev  # the base to compare the baseline with (default: origin/dev, or `requirements: base:`)
    python3 check_requirements.py --selftest

THE FILES (paths may be set under a `requirements:` section of `qa/qa.config.yml` with keys `registry`, `cases`, `baseline`; there is no path flag, only `--root`):
  qa/requirements.yml                       the registry. One entry per requirement, every line `key: <JSON value>` (valid YAML, no YAML library needed):
                                              - id: "REQ-001"
                                                area: "Auth"
                                                requirement: "A visitor can sign in with an email and password"
                                                status: "done"        # done | partial | missing | deviates | owner-decision
  qa/test-cases.csv                         the catalogue (`Test ID,Title,Area,Type,Priority,Status,Source,Notes`); a requirement is cased when a case
                                            whose Status is Active has its id as a whole token of the Source cell (separators: space , ; | but NOT `/`: `REQ-001/REQ-002` names neither)
  qa/requirements-uncased-baseline.txt      a RATCHET, not a threshold: the requirements with no case today, one id per line, `# size: N` in its header

THE GATE FAILS WHEN
  1. the registry is missing or unreadable, an id is malformed or repeated, a status is unknown, or `id`, `requirement` or `status` is missing, or
     its `# rows: N` header is absent or not its entry count (a requirement cannot be deleted, with its baseline line, unseen);
  2. a requirement that is not an owner-decision is named by no ACTIVE case and is not on the baseline;
  3. a baseline line names a requirement that is now cased, is an owner-decision, or is not in the registry (the list only shrinks), or the baseline's
     `# size: N` is not its line count (a line cannot be added or dropped without a visible edit of that number);
  4. a baseline line is not in the base branch's baseline (it cannot grow against the branch it merges into). The base is `--base REF`, else `base:` under
     `requirements:` in qa/qa.config.yml, else the default origin/dev. A base set by flag or config that cannot be read is exit 2. The DEFAULT base missing
     (a project on `main`) is a printed note and exit 3, a skip, and only when nothing else is wrong. A base that holds neither a registry nor a baseline at
     the configured or the default path is the first adoption and skips this rule with a printed note; a base with a registry and no baseline is an EMPTY
     baseline, so every baseline line is growth. The base's baseline is the union of the two paths, so moving the file is not growth;
  5. an ACTIVE case's Source names an id that looks like one of the registry's (same prefix) but is not in it: a typo that would cover nothing.
An owner-decision requirement is exempt only by that status, never by absence. A deprecated or draft case covers nothing.

WHAT IT CANNOT DO. It reads text. It cannot tell that a case really proves the requirement it names; that is the review of the case (and the manual
run). It proves the link exists and that the list of uncovered requirements cannot quietly grow.

Files are read as UTF-8 with a BOM tolerated (an Excel save adds one). A `requirements:` path must stay inside the project.

Exit codes: 0 clean, 1 findings, 2 could not check (a missing catalogue, an unreadable base ref, a path outside the project).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REGISTRY = "qa/requirements.yml"
CASES = "qa/test-cases.csv"
BASELINE = "qa/requirements-uncased-baseline.txt"
DEFAULT_BASE = "origin/dev"
STATUSES = ("done", "partial", "missing", "deviates", "owner-decision")
ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+$")
SEPARATORS = re.compile(r"[\s,;|]+")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+~^/-]*$")


def requirements_section(root: Path) -> dict:
    """The `requirements:` section of qa/qa.config.yml (`registry`, `cases`, `baseline`, `base`), or {} when there is none."""
    config = root / "qa" / "qa.config.yml"
    if not config.is_file():
        return {}
    import qa_config
    section = qa_config.load_section(config, "requirements")
    return section


def paths(root: Path) -> tuple[str, str, str]:
    """Registry, catalogue and baseline paths: the `requirements:` section of qa/qa.config.yml, else the defaults."""
    section = requirements_section(root)
    def pick(key: str, default: str) -> str:
        value = str(section[key]) if section.get(key) else default
        if not (root / value).resolve().is_relative_to(root.resolve()):     # an absolute path, `..` and a symlink out all resolve outside
            raise ValueError(f"requirements.{key} {value!r} must be a path inside the project")
        return value
    return pick("registry", REGISTRY), pick("cases", CASES), pick("baseline", BASELINE)


def load(root: Path, registry: str) -> tuple[list[dict], list[str]]:
    """The registry's entries and the problems found reading it. One `key: <JSON>` per line; `- id:` starts an entry."""
    path, problems, entries = root / registry, [], []
    if not path.is_file():
        return [], [f"{registry}: missing"]
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
        if key in entries[-1]:
            problems.append(f"{registry}:{number}: `{key}` is repeated within the entry that starts at line {entries[-1]['_line']} (the last one would hide the first)")
            continue
        entries[-1][key] = value
    return entries, problems


def baseline_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def header_number(text: str, key: str) -> int | None:
    match = re.search(rf"^#\s*{key}:\s*(\d+)\s*$", text, re.M)
    return int(match.group(1)) if match else None


def active_sources(root: Path, cases: str) -> tuple[dict[str, list[str]] | None, list[str]]:
    """{token: [case ids that name it]} over ACTIVE cases, or None when the catalogue cannot be read."""
    path = root / cases
    if not path.is_file():
        return None, [f"{cases}: missing, so no requirement can be shown to have a case"]
    named: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"Test ID", "Status", "Source"} - set(reader.fieldnames or [])
        if missing:
            return None, [f"{cases}: no {', '.join(sorted(missing))} column"]
        for row in reader:
            if (row.get("Status") or "").strip().lower() != "active":
                continue
            for token in SEPARATORS.split(row.get("Source") or ""):
                token = token.strip("()[]\"'`.:")
                if token:
                    named.setdefault(token, []).append((row.get("Test ID") or "?").strip())
    return named, []


def check(root: Path, base: list[str] | None = None) -> tuple[int, list[str]]:
    """(exit code, findings)."""
    try:
        registry, cases, baseline = paths(root)
    except ValueError as exc:
        return 2, [str(exc)]
    entries, problems = load(root, registry)
    if (root / registry).is_file():
        rows = header_number((root / registry).read_text(encoding="utf-8-sig"), "rows")
        if rows is None:
            problems.append(f"{registry}: no `# rows: N` header, so a requirement could be deleted unseen; add `# rows: {len(entries)}`")
        elif rows != len(entries):
            problems.append(f"{registry}: the header says `# rows: {rows}` but it holds {len(entries)} entr(ies); edit the number on purpose, where a reviewer sees it")
    by_id: dict[str, dict] = {}
    for entry in entries:
        rid, where = entry.get("id"), f"{registry}:{entry['_line']}"
        if not isinstance(rid, str) or not ID.match(rid):
            problems.append(f"{where}: id {rid!r} is missing or malformed (e.g. REQ-001, PRD-15.1-landing)")
            continue
        if rid in by_id:
            problems.append(f"{where}: id {rid} is repeated (first at line {by_id[rid]['_line']})")
            continue
        by_id[rid] = entry
        if entry.get("status") not in STATUSES:
            problems.append(f"{where}: {rid} has status {entry.get('status')!r}, not one of {', '.join(STATUSES)}")
        if not isinstance(entry.get("requirement"), str) or not entry["requirement"].strip():
            problems.append(f"{where}: {rid} has no `requirement` text")
    named, case_problems = active_sources(root, cases)
    if named is None:
        return 2, problems + case_problems
    base_path = root / baseline
    base_text = base_path.read_text(encoding="utf-8-sig") if base_path.is_file() else ""
    listed = baseline_lines(base_text)
    seen: set[str] = set()
    for line in listed:
        if line in seen:
            problems.append(f"{baseline}: {line} is listed twice")
        seen.add(line)
    size = header_number(base_text, "size")
    if listed or size is not None:
        if size != len(listed):
            problems.append(f"{baseline}: the header says `# size: {size}` but it holds {len(listed)} line(s); edit the number on purpose, where a reviewer sees it")
    for line in listed:
        entry = by_id.get(line)
        if entry is None:
            problems.append(f"{baseline}: {line} is not in the registry (the list only shrinks: drop it)")
        elif entry.get("status") == "owner-decision":
            problems.append(f"{baseline}: {line} is an owner-decision and needs no case (drop it)")
        elif line in named:
            problems.append(f"{baseline}: {line} is now named by {named[line][0]}; drop it from the baseline (the list only shrinks)")
    for rid, entry in by_id.items():
        if entry.get("status") == "owner-decision" or rid in named or rid in listed:
            continue
        problems.append(f"{registry}:{entry['_line']}: {rid} is named by no ACTIVE case in {cases} and is not on {baseline}: add a case whose Source names it")
    prefixes = {rid.split("-")[0].split(".")[0] for rid in by_id}
    for token, case_ids in sorted(named.items()):
        if token not in by_id and ID.match(token) and token.split("-")[0].split(".")[0] in prefixes:
            problems.append(f"{cases}: {case_ids[0]} names {token}, which looks like a requirement id but is not in {registry} (a typo covers nothing)")
    if base is not None:
        for line in listed:
            if line not in base:
                problems.append(f"{baseline}: {line} is not in the base branch's baseline; a requirement without a case cannot be added to it (add the case)")
    return (1 if problems else 0), problems


def uncased(root: Path) -> list[str]:
    """Requirement ids, in registry order, that no ACTIVE case names and that are not owner decisions (whether or not baselined)."""
    registry, cases, _ = paths(root)     # a ValueError here is reported by main
    entries, _ = load(root, registry)
    named, _ = active_sources(root, cases)
    return [e["id"] for e in entries if isinstance(e.get("id"), str) and e.get("status") != "owner-decision" and e["id"] not in (named or {})]


def base_ref(root: Path, flag: str | None) -> tuple[str, bool]:
    """(ref, explicit): the `--base` flag, else `requirements: base:` in qa/qa.config.yml (both explicit), else the default `origin/dev`. A ref that starts with
    `-` is refused: it would be read by git as an option."""
    section = requirements_section(root)
    ref = flag or (str(section["base"]) if section.get("base") else "")
    # The ref comes from a file a pull request can change and reaches `git fetch`: a component git would read as an option
    # (`origin/--upload-pack=...`) is command execution, so only a plain ref is accepted (and `--` ends git's options below).
    if ref and (not REF.fullmatch(ref) or any(part.startswith("-") for part in ref.split("/"))):
        raise ValueError(f"the base ref {ref!r} must be a plain ref: letters, digits and . _ @ + ~ ^ /, no component starting with `-`")
    return (ref, True) if ref else (DEFAULT_BASE, False)


def base_baseline(ref: str, root: Path) -> tuple[str, list[str]]:
    """(state, lines). `ok`: the baseline lines at `ref` (the union of the configured path and the default path, so moving the file is not growth;
    fetched if the checkout lacks `ref`); a registry with no baseline anywhere at the base is `ok` with NO lines, so every baseline line is growth.
    `none`: `ref` holds neither a registry nor a baseline at either path, which is the first adoption (nothing to grow against; the caller prints a note).
    `unreadable`: `ref` itself cannot be read."""
    registry, _, baseline = paths(root)

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def at_ref(path: str) -> str | None:
        done = git("show", f"{ref}:{path}")
        return done.stdout if done.returncode == 0 else None

    if git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}").returncode != 0:
        remote, _, branch = ref.partition("/")
        # Only a configured remote is fetched from: `git fetch somedir main` would read `somedir` as a PATH to some other repository.
        if remote in git("remote").stdout.split():
            subprocess.run(["git", "-C", str(root), "fetch", "-q", "--", remote, branch], capture_output=True, timeout=120, stdin=subprocess.DEVNULL)
        if git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}").returncode != 0:
            return "unreadable", []
    baselines = [t for t in (at_ref(path) for path in dict.fromkeys((baseline, BASELINE))) if t is not None]
    registries = [t for t in (at_ref(path) for path in dict.fromkeys((registry, REGISTRY))) if t is not None]
    if not baselines and not registries:
        return "none", []
    lines: list[str] = []
    for text in baselines:
        lines += baseline_lines(text)
    return "ok", lines


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------


def selftest(match: str | None = None) -> int:
    """`match` runs only the scenario rows whose label contains it (the mutation harness runs each mutant on the one row it names, #1599); when no scenario row
    carries it, the whole real-ref and CLI part runs, because the row it names is one of those."""
    failures: list[str] = []
    matched: list[str] = []

    def report() -> int:
        if failures:
            print("check_requirements selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
            return 1
        print("check_requirements selftest: ok (0 failure(s))")
        return 0

    def entry(rid: str, status: str = "done", extra: str = "") -> str:
        return f'- id: "{rid}"\n  area: "A"\n  requirement: "text of {rid}"\n  status: "{status}"\n{extra}'

    def csv_text(*rows: tuple[str, str, str]) -> str:
        return "Test ID,Title,Area,Type,Priority,Status,Source,Notes\n" + "".join(f'{tid},t,A,Functional,P1,{st},"{src}",\n' for tid, st, src in rows)

    def scenario(label: str, files: dict[str, str], want_code: int, want: str | None, base: list[str] | None = None, raw: bool = False) -> None:
        if match and match not in label:
            return
        matched.append(label)
        files = dict(files)
        if REGISTRY in files and not raw and "# rows:" not in files[REGISTRY]:     # every fixture states its row count unless it is testing that header
            files[REGISTRY] = f"# rows: {files[REGISTRY].count('- id:')}\n" + files[REGISTRY]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            code, found = check(root, base)
        joined = "\n".join(found)
        ok = code == want_code and (want is None and not found if want_code == 0 else want is not None and want in joined)
        if not ok:
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:200]!r}")

    reg2 = entry("REQ-001") + entry("REQ-002", "missing")
    cases2 = csv_text(("TC-1", "Active", "REQ-001"), ("TC-2", "Active", "REQ-002; defect:#9"))
    base0 = "# size: 0\n"
    scenario("every requirement named by an active case is clean", {REGISTRY: reg2, CASES: cases2, BASELINE: base0}, 0, None)
    scenario("a registry with no baseline file is clean when every row is cased", {REGISTRY: reg2, CASES: cases2}, 0, None)
    scenario("an uncased requirement is a finding", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: base0}, 1, "REQ-002 is named by no ACTIVE case")
    scenario("a DEPRECATED case covers nothing (near miss: same id, wrong status)",
             {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001"), ("TC-2", "Deprecated", "REQ-002")), BASELINE: base0}, 1, "REQ-002 is named by no ACTIVE case")
    scenario("a DRAFT case covers nothing", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001"), ("TC-2", "Draft", "REQ-002")), BASELINE: base0}, 1,
             "REQ-002 is named by no ACTIVE case")
    scenario("an id inside a longer token does not count (REQ-0011 is not REQ-001)", {REGISTRY: entry("REQ-001"), CASES: csv_text(("TC-1", "Active", "REQ-0011")),
             BASELINE: base0}, 1, "REQ-001 is named by no ACTIVE case")
    scenario("the Source separators are space, comma, semicolon and pipe", {REGISTRY: entry("REQ-001") + entry("REQ-002") + entry("REQ-003"),
             CASES: csv_text(("TC-1", "Active", "REQ-001,REQ-002|REQ-003")), BASELINE: base0}, 0, None)
    scenario("an owner-decision needs no case", {REGISTRY: entry("REQ-001", "owner-decision"), CASES: csv_text(("TC-1", "Active", "x")), BASELINE: base0}, 0, None)
    scenario("a baselined uncased requirement is clean", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: "# size: 1\nREQ-002\n"}, 0, None)
    scenario("a baseline line that is now cased is a finding (the list only shrinks)", {REGISTRY: reg2, CASES: cases2, BASELINE: "# size: 1\nREQ-002\n"}, 1,
             "now named by TC-2")
    scenario("a baseline line for an unknown requirement is a finding", {REGISTRY: reg2, CASES: cases2, BASELINE: "# size: 1\nREQ-404\n"}, 1, "not in the registry")
    scenario("a baseline line for an owner-decision is a finding", {REGISTRY: entry("REQ-001", "owner-decision"), CASES: csv_text(("TC-1", "Active", "x")),
             BASELINE: "# size: 1\nREQ-001\n"}, 1, "owner-decision")
    scenario("a baseline whose size header is wrong is a finding", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: "# size: 5\nREQ-002\n"}, 1,
             "header says `# size: 5`")
    scenario("a baseline with lines and no size header is a finding", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: "REQ-002\n"}, 1,
             "header says `# size: None`")
    scenario("a duplicate baseline line is a finding", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: "# size: 2\nREQ-002\nREQ-002\n"}, 1,
             "listed twice")
    scenario("--base: a baseline line not in the base branch's baseline is refused", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")),
             BASELINE: "# size: 1\nREQ-002\n"}, 1, "not in the base branch's baseline", base=[])
    scenario("--base: a baseline line that was already there is clean", {REGISTRY: reg2, CASES: csv_text(("TC-1", "Active", "REQ-001")),
             BASELINE: "# size: 1\nREQ-002\n"}, 0, None, base=["REQ-002"])
    scenario("a case naming a mistyped requirement id is a finding (REQ-0O1 near REQ-001)", {REGISTRY: entry("REQ-001"), CASES: csv_text(("TC-1", "Active", "REQ-001"),
             ("TC-2", "Active", "REQ-999")), BASELINE: base0}, 1, "REQ-999, which looks like a requirement id but is not in")
    scenario("a Source that merely mentions an issue or a section is not an id", {REGISTRY: entry("REQ-001"), CASES: csv_text(("TC-1", "Active", "REQ-001 defect:#7 §15.1")),
             BASELINE: base0}, 0, None)
    scenario("a missing registry is a finding", {CASES: cases2}, 1, "qa/requirements.yml: missing")
    scenario("a missing catalogue is exit 2, never a pass", {REGISTRY: reg2}, 2, "qa/test-cases.csv: missing")
    scenario("a catalogue without a Source column is exit 2", {REGISTRY: reg2, CASES: "Test ID,Status\nTC-1,Active\n"}, 2, "no Source column")
    scenario("a repeated id is a finding", {REGISTRY: entry("REQ-001") + entry("REQ-001"), CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: base0}, 1, "is repeated")
    scenario("a malformed id is a finding", {REGISTRY: entry("req 1"), CASES: csv_text(("TC-1", "Active", "x")), BASELINE: base0}, 1, "malformed")
    scenario("an unknown status is a finding", {REGISTRY: entry("REQ-001", "wip"), CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: base0}, 1, "status 'wip'")
    scenario("a line that is not key: JSON is a finding", {REGISTRY: "- id: REQ-001\n", CASES: cases2, BASELINE: base0}, 1, "is not JSON")
    scenario("a key repeated within an entry is a finding (the last would hide the first)", {REGISTRY: entry("REQ-001") + '  status: "missing"\n', CASES: csv_text(("TC-1", "Active", "REQ-001")),
             BASELINE: base0}, 1, "`status` is repeated within the entry")
    scenario("a requirement with no text is a finding", {REGISTRY: '- id: "REQ-001"\n  status: "done"\n', CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: base0}, 1,
             "no `requirement` text")
    scenario("paths come from the requirements section of qa.config.yml", {"qa/qa.config.yml": 'requirements:\n  registry: "docs/reqs.yml"   # trailing comment\n  cases: "docs/cases.csv"\n',
             "docs/reqs.yml": "# rows: 1\n" + entry("REQ-001"), "docs/cases.csv": csv_text(("TC-1", "Active", "REQ-001"))}, 0, None)
    # the rows header (a requirement cannot be deleted, with its baseline line, unseen)
    scenario("a registry with no rows header is a finding", {REGISTRY: reg2, CASES: cases2, BASELINE: base0}, 1, "no `# rows: N` header", raw=True)
    scenario("a registry whose rows header is not its entry count is a finding", {REGISTRY: "# rows: 5\n" + reg2, CASES: cases2, BASELINE: base0}, 1, "header says `# rows: 5`")
    scenario("a requirement deleted from the registry together with its baseline line is a finding, not 100%",
             {REGISTRY: "# rows: 2\n" + entry("REQ-001"), CASES: csv_text(("TC-1", "Active", "REQ-001")), BASELINE: base0}, 1, "header says `# rows: 2` but it holds 1")
    # a catalogue saved from Excel starts with a BOM; paths stay inside the project; ids are not split on a slash
    scenario("a catalogue saved with a BOM is read", {REGISTRY: reg2, CASES: "\ufeff" + cases2, BASELINE: base0}, 0, None)
    scenario("a requirements path outside the project is exit 2 (..)", {"qa/qa.config.yml": 'requirements:\n  registry: "../elsewhere.yml"\n', CASES: cases2}, 2, "inside the project")
    scenario("a requirements path outside the project is exit 2 (absolute)", {"qa/qa.config.yml": 'requirements:\n  cases: "/etc/hosts"\n', REGISTRY: reg2}, 2, "inside the project")
    scenario("a slash-joined Source names neither id", {REGISTRY: entry("REQ-001") + entry("REQ-002"), CASES: csv_text(("TC-1", "Active", "REQ-001/REQ-002")), BASELINE: base0},
             1, "REQ-001 is named by no ACTIVE case")
    if match and matched:
        return report()
    # --base against real refs: a baseline at the ref, no baseline at the ref (first adoption), a ref that does not exist
    import fixture_git
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        fixture_git.init(repo)
        (repo / "qa").mkdir()
        fixture_git.run(repo, "commit", "-q", "--allow-empty", "-m", "no baseline yet")
        none_sha = fixture_git.run(repo, "rev-parse", "HEAD").stdout.strip()
        (repo / BASELINE).write_text("# size: 1\nREQ-002\n")
        fixture_git.run(repo, "add", "qa")
        fixture_git.run(repo, "commit", "-q", "-m", "baseline")
        with_sha = fixture_git.run(repo, "rev-parse", "HEAD").stdout.strip()
        got = base_baseline(with_sha, repo)
        if got != ("ok", ["REQ-002"]):
            failures.append(f"base_baseline reads the baseline at the ref: got {got!r}")
        got = base_baseline(none_sha, repo)
        if got != ("none", []):
            failures.append(f"a ref with no baseline file is `none`, not an empty baseline: got {got!r}")
        got = base_baseline("no-such-ref", repo)
        if got[0] != "unreadable":
            failures.append(f"a ref that does not exist is unreadable: got {got!r}")
        (repo / REGISTRY).write_text("# rows: 2\n" + reg2)
        (repo / CASES).write_text(csv_text(("TC-1", "Active", "REQ-001")))
        (repo / BASELINE).write_text("# size: 1\nREQ-002\n")
        done = subprocess.run([sys.executable, __file__, "--root", str(repo), "--base", none_sha], capture_output=True, text=True, timeout=120)
        if done.returncode != 0 or "holds no registry or baseline, so growth against it was not checked" not in done.stdout:
            failures.append(f"a base with no registry or baseline skips the growth check with a printed note and exits 0: got {done.returncode} {done.stdout[:160]!r}")
        done = subprocess.run([sys.executable, __file__, "--root", str(repo), "--base", with_sha], capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            failures.append(f"a baseline line already at the base is clean under --base: got {done.returncode} {done.stdout[:160]!r}")
        (repo / BASELINE).write_text("# size: 2\nREQ-002\nREQ-003\n")
        (repo / REGISTRY).write_text("# rows: 3\n" + reg2 + entry("REQ-003", "missing"))
        done = subprocess.run([sys.executable, __file__, "--root", str(repo), "--base", with_sha], capture_output=True, text=True, timeout=120)
        if done.returncode != 1 or "REQ-003 is not in the base branch's baseline" not in done.stdout:
            failures.append(f"an uncased requirement plus its baseline line plus a bumped size is refused under --base: got {done.returncode} {done.stdout[:200]!r}")
    # the base ratchet, against real refs
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        fixture_git.init(repo)
        (repo / "qa").mkdir()

        def put(name: str, text: str) -> None:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text, encoding="utf-8")

        def cli(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, __file__, "--root", str(repo), *args], capture_output=True, text=True, timeout=120)

        def commit(message: str) -> str:
            fixture_git.run(repo, "add", "qa")
            fixture_git.run(repo, "commit", "-q", "-m", message)
            return fixture_git.run(repo, "rev-parse", "HEAD").stdout.strip()

        put(REGISTRY, "# rows: 2\n" + reg2)
        put(CASES, csv_text(("TC-1", "Active", "REQ-001")))
        put(BASELINE, "# size: 1\nREQ-002\n")
        with_registry = commit("registry and a size-1 baseline")
        # the bypass: a base that HAS a registry, and a config that moves the baseline to a path the base lacks
        put("qa/qa.config.yml", 'requirements:\n  baseline: "qa/b2.txt"\n')
        put(REGISTRY, "# rows: 4\n" + reg2 + entry("REQ-003", "missing") + entry("REQ-004", "missing"))
        put("qa/b2.txt", "# size: 3\nREQ-002\nREQ-003\nREQ-004\n")
        done = cli("--base", with_registry)
        if done.returncode != 1 or "not in the base branch's baseline" not in done.stdout:
            failures.append(f"a baseline moved to a new path with grown lines is refused when the base has a registry: got {done.returncode} {done.stdout[:200]!r}")
        # moving the file with the same lines is not growth (the base's baseline is the union of the two paths)
        put(REGISTRY, "# rows: 2\n" + reg2)
        put("qa/b2.txt", "# size: 1\nREQ-002\n")
        done = cli("--base", with_registry)
        if done.returncode != 0:
            failures.append(f"moving the baseline file with the same lines is clean: got {done.returncode} {done.stdout[:200]!r}")
        (repo / "qa" / "qa.config.yml").unlink()
        # a base with a registry and NO baseline is an empty baseline: adding lines is growth
        fixture_git.run(repo, "rm", "-q", "--cached", BASELINE)
        (repo / BASELINE).unlink()
        registry_only = commit("a registry and no baseline")
        put(BASELINE, "# size: 1\nREQ-002\n")
        done = cli("--base", registry_only)
        if done.returncode != 1 or "REQ-002 is not in the base branch's baseline" not in done.stdout:
            failures.append(f"a base with a registry and no baseline is an empty baseline, so a baseline line is growth: got {done.returncode} {done.stdout[:200]!r}")
        # the default base (origin/dev) is missing here: findings are still reported, and only a clean tree is a skip
        done = cli()
        if done.returncode != 3 or "default base origin/dev cannot be read" not in done.stdout:
            failures.append(f"a clean tree whose default base is missing is a skip (3) with a note: got {done.returncode} {done.stdout[:200]!r}")
        put(CASES, csv_text(("TC-9", "Active", "other")))
        done = cli()
        if done.returncode != 1 or "REQ-001 is named by no ACTIVE case" not in done.stdout:
            failures.append(f"findings are reported, not hidden, when the default base is missing: got {done.returncode} {done.stdout[:200]!r}")
        put(CASES, csv_text(("TC-1", "Active", "REQ-001")))
        # the base is a project setting: `base:` under requirements: is read; a missing configured base is exit 2
        put("qa/qa.config.yml", f'requirements:\n  base: "{with_registry}"\n')
        done = cli()
        if done.returncode != 0:
            failures.append(f"a base set in qa.config.yml is used (no origin/dev needed): got {done.returncode} {done.stdout[:200]!r}")
        put("qa/qa.config.yml", 'requirements:\n  base: "no-such-ref"\n')
        done = cli()
        if done.returncode != 2:
            failures.append(f"a configured base that cannot be read is exit 2, not a skip: got {done.returncode} {done.stdout[:200]!r}")
        marker = repo / "pwned"
        put("qa/qa.config.yml", f'requirements:\n  base: "origin/--upload-pack=touch {marker}"\n')
        done = cli()
        if done.returncode != 2 or "must be a plain ref" not in done.stderr or marker.exists():
            failures.append(f"a configured base with a component that git would read as an option is refused and runs nothing: got {done.returncode} {done.stderr[:160]!r} ran={marker.exists()}")
        put("qa/qa.config.yml", 'requirements:\n  base: "origin/--tags"\n')
        done = cli()
        if done.returncode != 2 or "must be a plain ref" not in done.stderr:
            failures.append(f"a base ref with a component starting with `-` is refused: got {done.returncode} {done.stderr[:160]!r}")
        done = cli("--base", "origin/dev\n")
        if done.returncode != 2 or "must be a plain ref" not in done.stderr:
            failures.append(f"a base ref with a trailing newline is refused (a `$` anchor would accept it): got {done.returncode} {done.stderr[:160]!r}")
        elsewhere = repo / "somedir"
        elsewhere.mkdir()
        fixture_git.init(elsewhere)
        fixture_git.run(elsewhere, "commit", "-q", "--allow-empty", "-m", "elsewhere")
        done = cli("--base", "somedir/main")
        if done.returncode != 2 or (repo / ".git" / "FETCH_HEAD").exists():
            failures.append(f"a base whose first component is not a configured remote is exit 2 and is never fetched from as a path: got {done.returncode} fetched={(repo / '.git' / 'FETCH_HEAD').exists()}")
        done = cli("--base=-x")
        if done.returncode != 2 or "must be a plain ref" not in done.stderr:
            failures.append(f"a base ref that starts with `-` is refused, git would read it as an option: got {done.returncode} {done.stderr[:200]!r}")
    # the CLI end to end: exit codes and --uncased
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "qa").mkdir()
        (root / REGISTRY).write_text("# rows: 2\n" + reg2)
        (root / CASES).write_text(csv_text(("TC-1", "Active", "REQ-001")))
        (root / BASELINE).write_text("# size: 1\nREQ-002\n")
        done = subprocess.run([sys.executable, __file__, "--root", td, "--uncased"], capture_output=True, text=True, timeout=60)
        if done.returncode != 0 or done.stdout.split() != ["REQ-002"]:
            failures.append(f"--uncased lists the uncased ids and exits 0: got exit {done.returncode} {done.stdout!r}")
        done = subprocess.run([sys.executable, __file__, "--root", td], capture_output=True, text=True, timeout=60)
        if done.returncode != 3 or "the default base origin/dev cannot be read" not in done.stdout:
            failures.append(f"a conforming tree whose DEFAULT base cannot be read is a skip (3) with a note, never a pass: got {done.returncode} {done.stdout[:160]!r}")
        (root / BASELINE).write_text("# size: 0\n")
        done = subprocess.run([sys.executable, __file__, "--root", td], capture_output=True, text=True, timeout=60)
        if done.returncode != 1 or "REQ-002" not in done.stdout:
            failures.append(f"the gate exits 1 naming the uncased requirement: got {done.returncode} {done.stdout[:120]!r}")
        (root / CASES).unlink()
        done = subprocess.run([sys.executable, __file__, "--root", td], capture_output=True, text=True, timeout=60)
        if done.returncode != 2:
            failures.append(f"a missing catalogue exits 2: got {done.returncode}")
        (root / CASES).write_text(csv_text(("TC-1", "Active", "REQ-001")))     # a conforming tree again, so only the ref can fail
        (root / BASELINE).write_text("# size: 1\nREQ-002\n")
        done = subprocess.run([sys.executable, __file__, "--root", td], capture_output=True, text=True, timeout=60)
        if done.returncode != 3:
            failures.append(f"control: the restored tree, outside a git repository, is only a skip because the default base cannot be read: got {done.returncode} {done.stdout[:120]!r}")
        done = subprocess.run([sys.executable, __file__, "--root", td, "--base", "no-such-remote/no-such-branch"], capture_output=True, text=True, timeout=120)
        if done.returncode != 2:
            failures.append(f"an unreadable --base ref exits 2, never a pass: got {done.returncode} {done.stdout[:120]!r}")
    return report()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Every requirement is named, by id, in an ACTIVE catalogue case (#1855).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--uncased", action="store_true", help="list the requirement ids with no active case, one per line, and exit 0")
    parser.add_argument("--base", metavar="REF", help="refuse a baseline line that is not in REF's baseline; default: `requirements: base:` in qa/qa.config.yml, else origin/dev (fetches REF)")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the scenario rows whose label contains TEXT (the mutation harness)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match)
    root = Path(args.root).resolve()
    try:
        if args.uncased:
            print("\n".join(uncased(root)))
            return 0
        base, unchecked = None, False
        ref, explicit = base_ref(root, args.base)
        state, lines = base_baseline(ref, root)
        if state == "unreadable":
            if explicit:
                print(f"check_requirements: cannot read {ref}, which is not a commit here and is not on a configured remote (exit 2, not a pass)", file=sys.stderr)
                return 2
            print(f"check_requirements: note: the default base {ref} cannot be read, so growth was not checked; set `base:` under `requirements:` in qa/qa.config.yml")
            unchecked = True
        elif state == "none":
            print(f"check_requirements: note: {ref} holds no registry or baseline, so growth against it was not checked (first adoption)")
        else:
            base = lines
    except ValueError as exc:
        print(f"check_requirements: {exc} (exit 2, not a pass)", file=sys.stderr)
        return 2
    code, found = check(root, base)
    for line in found:
        print(line)
    if code == 0 and unchecked:
        print("check_requirements: the findings above are all there is, but growth was not checked: exit 3 (a skip, not a pass)")
        return 3
    print(f"check_requirements: {'ok' if code == 0 else 'could not check' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
