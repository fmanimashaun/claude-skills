#!/usr/bin/env python3
"""Catch guarantees this repo states but does not enforce.

WHY THIS EXISTS
---------------
A rented reviewer kept finding a class of bug our own review missed, and it had
no proprietary advantage: it checked the diff against rules already written in
this codebase's markdown. The recurring class is **claims-vs-enforcement** -- a
guarantee stated in prose that nothing makes true:

  * `--check || echo` made a release gate unable to block            (#151)
  * README said "always pass --max-total-usd"; the flag was optional (#161)
  * suite.json declared `max_turns: 30`; no CLI flag could enforce it (#161)

Three strikes across three PRs. The full class list -- including the ones that
need judgement -- lives in the shipped `code-review` skill
(`skills/code-review/SKILL.md`), so the rules sit where reviewers already look
and we are held to the same doctrine we sell. This file mechanises only the
subset needing no judgement, because per this repo's own thesis a rule that stays
in prose gets violated again. `lint_markdown_shell.py` exists for exactly that
reason; this is the same move pointed at our own claims.

WHAT IT CHECKS
--------------
  dead-settings-key         a key in a JSON settings block that no reader reads
  unenforced-mandatory-flag a flag documented as mandatory that code leaves optional

Deliberately narrow. Both rules are mechanical with no judgement, so a finding is
always real. Classes that need judgement (a docstring promising behaviour the code
lacks, a carve-out with no negative test) belong to the rubric and the reviewers,
not here -- a linter with false positives gets disabled, and then catches nothing.

Stdlib only. Run:
    python3 scripts/lint_self_consistency.py
    python3 scripts/lint_self_consistency.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

# The tree being scanned. Swapped by --selftest so the rules can be exercised
# against synthetic fixtures: a linter nobody tested is a claim, not a check.
ROOT = REPO_ROOT

SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv"}

# Object names that conventionally mean "settings". A key here is a promise that
# something honours it. Data-bearing objects are excluded on purpose: `cases[]`
# entries carry human metadata (`title`, `measures`) that no code reads by design,
# and flagging those would make the rule noisy enough to be switched off.
SETTINGS_BLOCK_NAMES = {"defaults", "config", "settings", "options"}

# "always pass `--flag`" / "`--flag` is required" / "must set `--flag`"
_MANDATORY_FLAG_PATTERNS = (
    re.compile(r"(?:always|must)\s+(?:pass|set|supply|provide|use)\s+`?(--[a-z0-9][a-z0-9-]*)`?", re.I),
    re.compile(r"`?(--[a-z0-9][a-z0-9-]*)`?\s+is\s+(?:\*\*)?required(?:\*\*)?", re.I),
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.rule}] {where} -- {self.message}"


def walk(suffix: str) -> list[Path]:
    """Collect files under ROOT, pruning SKIP_DIRS during traversal.

    `rglob` + post-filter looks equivalent and is not: it descends into `.git`,
    `node_modules`, and `.venv` in full and only discards the results afterwards,
    so SKIP_DIRS documented a pruning that never happened. `os.walk` with in-place
    `dirnames` mutation actually prevents the recursion.
    """
    import os

    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(suffix):
                out.append(Path(dirpath) / filename)
    return sorted(out)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Rule: dead-settings-key
# ---------------------------------------------------------------------------

def settings_keys(payload: object, *, inside_block: bool = False) -> set[str]:
    """Collect keys that live inside a settings block, recursively."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.startswith("$"):  # $comment / $schema are documentation
                continue
            if inside_block:
                found.add(key)
            nested = inside_block or key in SETTINGS_BLOCK_NAMES
            found |= settings_keys(value, inside_block=nested)
    elif isinstance(payload, list):
        for item in payload:
            found |= settings_keys(item, inside_block=inside_block)
    return found


def check_dead_settings_keys(python_sources: dict[Path, str]) -> tuple[list[Finding], int]:
    """A settings key nothing reads is a condition quietly declared false."""
    findings: list[Finding] = []
    examined = 0

    for json_path in walk(".json"):
        try:
            payload = json.loads(read(json_path))
        except json.JSONDecodeError:
            continue

        keys = settings_keys(payload)
        if not keys:
            continue

        # Only JSON that our own Python reads. marketplace.json / plugin.json are
        # consumed by Claude Code, so "no Python reads it" proves nothing there.
        basename = json_path.name
        readers = {p: src for p, src in python_sources.items() if basename in src}
        if not readers:
            continue

        examined += 1
        blob = "\n".join(readers.values())
        for key in sorted(keys):
            if re.search(rf"['\"]{re.escape(key)}['\"]", blob):
                continue
            if re.search(rf"\b{re.escape(key)}\b", blob):
                continue  # read via attribute/arg name, e.g. argparse dest
            findings.append(Finding(
                "dead-settings-key", rel(json_path), 0,
                f"settings key {key!r} is read by no module that loads "
                f"{basename} ({', '.join(sorted(rel(p) for p in readers))}); "
                f"either wire it up or delete it -- a declared condition nothing "
                f"enforces is worse than an absent one",
            ))
    return findings, examined


# ---------------------------------------------------------------------------
# Rule: unenforced-mandatory-flag
# ---------------------------------------------------------------------------

def flag_is_enforced(flag: str, source: str) -> bool:
    """True when code actually makes `flag` mandatory.

    Two accepted forms: argparse `required=True` on that argument, or an explicit
    guard that errors out naming the flag (`parser.error("--x is required...")`).
    """
    dest = flag.lstrip("-").replace("-", "_")

    # required=True within the add_argument(...) call for this flag.
    for match in re.finditer(r"add_argument\((.*?)\)\s*$", source, re.S | re.M):
        call = match.group(1)
        if flag in call and re.search(r"required\s*=\s*True", call):
            return True

    # An explicit error path naming the flag (either spelling). The receiver is
    # matched as any identifier, not literally `parser`: the ArgumentParser is
    # often bound to `p`/`ap`/`cli`, and hardcoding one name made this rule miss
    # a guard that was right there (caught by --selftest).
    for match in re.finditer(r"(?:\w+\.error|sys\.exit|raise\s+SystemExit)\s*\((.*?)\)",
                             source, re.S):
        body = match.group(1)
        if flag in body or dest in body:
            return True
    return False


def check_unenforced_mandatory_flags(python_sources: dict[Path, str]) -> tuple[list[Finding], int]:
    """Docs that call a flag mandatory while code shrugs."""
    findings: list[Finding] = []
    examined = 0

    for md_path in walk(".md"):
        text = read(md_path)
        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            flags: set[str] = set()
            for pattern in _MANDATORY_FLAG_PATTERNS:
                flags.update(match.group(1) for match in pattern.finditer(line))
            for flag in sorted(flags):
                # Locate the module that defines the flag.
                definers = {
                    path: src for path, src in python_sources.items()
                    if f'"{flag}"' in src or f"'{flag}'" in src
                }
                if not definers:
                    continue  # documented for a third-party tool, not ours
                examined += 1
                if any(flag_is_enforced(flag, src) for src in definers.values()):
                    continue
                findings.append(Finding(
                    "unenforced-mandatory-flag", rel(md_path), index,
                    f"documented as mandatory but "
                    f"{', '.join(sorted(rel(p) for p in definers))} leaves {flag} "
                    f"optional; enforce it in code or soften the wording",
                ))
    return findings, examined


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> tuple[list[Finding], dict[str, int]]:
    python_sources = {path: read(path) for path in walk(".py")}
    dead, dead_examined = check_dead_settings_keys(python_sources)
    unenforced, flag_examined = check_unenforced_mandatory_flags(python_sources)
    coverage = {
        "python_modules": len(python_sources),
        "json_settings_files_examined": dead_examined,
        "documented_flag_claims_examined": flag_examined,
    }
    return dead + unenforced, coverage


def selftest() -> int:
    """Exercise both rules against synthetic trees, in both directions.

    The silent direction matters most: a rule that fires on everything looks
    rigorous, gets switched off after the third false positive, and then catches
    nothing at all.
    """
    global ROOT
    import tempfile

    failures: list[str] = []
    checks = 0

    def scenario(label: str, files: dict[str, str], *, rule: str, expect_finding: bool) -> None:
        nonlocal checks
        global ROOT
        checks += 1
        root = Path(tempfile.mkdtemp(prefix="selfconsist-"))
        for relpath, content in files.items():
            target = root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        previous, ROOT = ROOT, root
        try:
            findings, _ = run()
        finally:
            ROOT = previous
        got = [f for f in findings if f.rule == rule]
        if bool(got) != expect_finding:
            want = "a finding" if expect_finding else "silence"
            detail = "; ".join(str(f) for f in got) or "(none)"
            failures.append(f"{rule} / {label}: expected {want}, got {detail}")

    # -- dead-settings-key ------------------------------------------------
    scenario(
        "settings key no reader reads", rule="dead-settings-key", expect_finding=True,
        files={
            "suite.json": '{"defaults": {"runs": 3, "max_turns": 30}}\n',
            "run.py": 'import json\nCFG="suite.json"\nd=json.load(open(CFG))["defaults"]\nprint(d["runs"])\n',
        },
    )
    scenario(
        "every settings key is read", rule="dead-settings-key", expect_finding=False,
        files={
            "suite.json": '{"defaults": {"runs": 3, "model": "sonnet"}}\n',
            "run.py": 'import json\nCFG="suite.json"\nd=json.load(open(CFG))["defaults"]\n'
                      'print(d["runs"], d["model"])\n',
        },
    )
    # JSON nothing of ours reads proves nothing -- marketplace.json / plugin.json
    # are consumed by Claude Code, not by our Python.
    scenario(
        "no python reader means no verdict", rule="dead-settings-key", expect_finding=False,
        files={"marketplace.json": '{"defaults": {"never_read_by_us": true}}\n'},
    )
    # Data-bearing objects are out of scope on purpose; `title` here is human
    # metadata, and flagging it would make the rule noisy enough to be disabled.
    scenario(
        "non-settings objects are out of scope", rule="dead-settings-key", expect_finding=False,
        files={
            "suite.json": '{"cases": [{"id": "a", "title": "human only"}]}\n',
            "run.py": 'import json\nCFG="suite.json"\n'
                      'print([c["id"] for c in json.load(open(CFG))["cases"]])\n',
        },
    )

    # -- unenforced-mandatory-flag ---------------------------------------
    scenario(
        "docs say always pass, code leaves optional",
        rule="unenforced-mandatory-flag", expect_finding=True,
        files={
            "README.md": "Always pass `--budget-usd` when running live.\n",
            "tool.py": 'import argparse\np=argparse.ArgumentParser()\n'
                       'p.add_argument("--budget-usd", type=float, default=None)\n',
        },
    )
    scenario(
        "argparse required=True satisfies the claim",
        rule="unenforced-mandatory-flag", expect_finding=False,
        files={
            "README.md": "Always pass `--budget-usd` when running live.\n",
            "tool.py": 'import argparse\np=argparse.ArgumentParser()\n'
                       'p.add_argument("--budget-usd", type=float, required=True)\n',
        },
    )
    scenario(
        "an explicit parser.error guard satisfies the claim",
        rule="unenforced-mandatory-flag", expect_finding=False,
        files={
            "README.md": "`--budget-usd` is **required** for a live run.\n",
            "tool.py": 'import argparse\np=argparse.ArgumentParser()\n'
                       'p.add_argument("--budget-usd", type=float, default=None)\n'
                       'a=p.parse_args()\n'
                       'if a.budget_usd is None:\n'
                       '    p.error("--budget-usd is required for a live run")\n',
        },
    )
    scenario(
        "a flag we do not define is not our claim to enforce",
        rule="unenforced-mandatory-flag", expect_finding=False,
        files={"README.md": "Always pass `--no-cache` to that third-party tool.\n"},
    )

    print(f"ran {checks} self-consistency assertion(s)")
    if failures:
        print(f"\n{len(failures)} FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("both rules behave as specified")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--selftest", action="store_true",
                        help="prove both rules fire and stay silent (no repo scan)")
    parser.add_argument("--root", default=None,
                        help="scan this tree instead of the repo (for auditing a "
                             "checkout of another commit)")
    args = parser.parse_args(argv[1:])

    if args.selftest:
        return selftest()

    if args.root:
        global ROOT
        candidate = Path(args.root).resolve()
        if not candidate.is_dir():
            parser.error(f"--root is not a directory: {candidate}")
        ROOT = candidate

    findings, coverage = run()

    if args.json:
        print(json.dumps(
            {"findings": [asdict(f) for f in findings], "coverage": coverage},
            indent=2,
        ))
        return 1 if findings else 0

    # Report coverage even when clean. "no findings" over input the linter never
    # read is worse than no linter -- the --audit-coverage lesson from
    # lint_markdown_shell.py, where a regex silently skipped 11 blocks.
    print(f"scanned {coverage['python_modules']} python module(s); "
          f"{coverage['json_settings_files_examined']} json settings file(s); "
          f"{coverage['documented_flag_claims_examined']} documented flag claim(s)")

    if not findings:
        print("no findings.")
        return 0

    for finding in findings:
        print(finding)
    print(f"\n{len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
