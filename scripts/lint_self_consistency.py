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
  dead-settings-key           a key in a JSON settings block that no reader reads
  unenforced-mandatory-flag   a flag documented as mandatory that code leaves optional
  undocumented-plugin         a plugin declared in marketplace.json that CLAUDE.md or
                              README.md never names — it ships while the doc describing
                              what ships omits it
  unbounded-issue-query       a `gh issue/pr list` with no --limit: it defaults to 30, so
                              the call reports a page as the total
  doctrine-call-site-mismatch a call site in skills/ naming an API those skills do not
                              declare — a wrong initializer keyword, an undeclared slot,
                              or an icon passed a size it must not take

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

# `design-corpora` is the gitignored nested clone of the licensed design kits (#197). It holds
# ~125 third-party markdown files, and this linter checks OUR claims against OUR code — a
# finding in a vendor CHANGELOG would be both false and unactionable, since we cannot edit
# licensed corpora. Before #197 the kits were symlinked in and os.walk skipped them for free;
# a real subdirectory has to be pruned deliberately. Pruned by EXACT name, so a
# `design-corpora-notes/` of ours is still scanned — proved by --selftest.
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv", "design-corpora"}

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
# Rule: unbounded-issue-query
# ---------------------------------------------------------------------------

# `gh issue list` and `gh pr list` default to --limit 30. A call without an explicit bound
# reports a PAGE as if it were the total, which is `unverified-negative` from the shipped
# code-review skill: a count from a list nobody read to the end.
#
# This bit for real (#211). The maintainer was told "30 open issues" when there were 42, and
# grepping for the pattern found two shipped call sites with the same defect -- one of them
# `issue-triager`'s DUPLICATE DETECTION, which would decide "no duplicate exists" after
# reading 30 of 42 and then file the duplicate it exists to prevent.
#
# Not delegated to lint_markdown_shell.py on purpose: both real instances were inline in
# prose, not inside a fenced block, so a fence-based scanner cannot see them.
#
# SCOPE BOUNDARY, checked rather than assumed (#233). This covers `gh issue/pr list` and
# `gh search`, where the default is 30 and a miscount is near-certain. It deliberately does NOT
# cover `gh api` collection iteration (e.g. `gh api .../contents/x --jq '.[].name'`, which
# brain-sync.md does): the risk profile is different (~1000, not 30), and firing correctly there
# would mean distinguishing collection-returning endpoints from object-returning ones — judgement,
# which is how a linter becomes noisy and then gets switched off. Known gap, not an oversight.
_GH_LIST = re.compile(r"gh\s+(?:issue|pr)\s+list\b|gh\s+search\s+(?:issues|prs)\b")
# `--limit N`, or a REST call paginating explicitly. `--paginate` fetches every page, so it
# bounds nothing but also truncates nothing -- it is a correct answer to the same question.
_BOUNDED = re.compile(r"--limit\b|per_page\b|--paginate\b")
# Only INVOCATIONS are graded, identified by carrying at least one flag. A bare prose mention
# of the command name is a reference, not something an agent runs -- CHANGELOG.md line 674 says
# "the command only ever saw `gh issue list` before", which is history and must not be rewritten
# to satisfy a lint. Both real #211 defects carried a flag (`--search`, `--label`), so this
# targets exactly what it should without needing a per-file exemption to keep honest.
_INVOCATION = re.compile(r"--[a-z]")


def check_unbounded_issue_queries() -> tuple[list[Finding], int]:
    """A `gh` list call with no page bound turns a page into a reported total."""
    findings: list[Finding] = []
    examined = 0
    for path in walk(".md"):
        for lineno, line in enumerate(read(path).splitlines(), start=1):
            if not _GH_LIST.search(line) or not _INVOCATION.search(line):
                continue
            examined += 1
            if _BOUNDED.search(line):
                continue
            findings.append(Finding(
                "unbounded-issue-query", rel(path), lineno,
                "`gh issue/pr list` defaults to --limit 30, so this reads a page and reports "
                "it as the total -- pass `--limit N` (or `--paginate`). A count from a "
                "truncated list is the unverified-negative class (#211)",
            ))
    return findings, examined


# ---------------------------------------------------------------------------
# Rule: undocumented-plugin
# ---------------------------------------------------------------------------

# Docs that must name every distributed plugin. A plugin missing from these is invisible to one
# of the two audiences: CLAUDE.md is what orients a maintainer (or an agent reading it) about what
# this repo ships, README.md is what orients a user.
PLUGIN_DOCS = ("CLAUDE.md", "README.md")


def check_undocumented_plugins() -> tuple[list[Finding], int]:
    """Every plugin declared in `marketplace.json` must be named in the docs that describe them.

    `design-flow` was declared, packaged and shipped while CLAUDE.md's opening section -- the
    definition of what this repo distributes -- said "four app-builder plugins" and listed the
    other four. It named design-flow zero times, so anything orienting from that file could not
    know the plugin existed (#203).

    COUNTS ARE DELIBERATELY NOT CHECKED. Prose legitimately refers to subsets ("the plugins
    above help you build apps"), so a rule matching "four plugins" against the real total would
    fire on correct writing, and per this file's own thesis a linter that cries wolf gets
    switched off and then catches nothing. Name presence needs no judgement: either the declared
    plugin is mentioned or it is not.

    WHAT THIS DOES NOT CATCH, stated because the boundary is easy to overclaim: it proves the name
    appears SOMEWHERE in the file, not that it appears in the list that enumerates what ships. A
    mention in surrounding prose satisfies it. Found by mutation-testing this rule -- deleting
    `design-flow` from CLAUDE.md's distributed list left the linter green, because a nearby
    sentence still named it. Locating "the right section" needs judgement about where a section
    starts and ends, which is how a mechanical rule turns into a noisy one, so the narrow
    guarantee is the honest one: it catches a plugin documented NOWHERE, which is the defect that
    actually shipped (design-flow had zero mentions).
    """
    manifest = ROOT / ".claude-plugin" / "marketplace.json"
    if not manifest.is_file():
        return [], 0
    try:
        payload = json.loads(read(manifest))
    except json.JSONDecodeError:
        return [], 0
    names = [p["name"] for p in payload.get("plugins", []) if isinstance(p, dict) and "name" in p]
    if not names:
        return [], 0

    findings: list[Finding] = []
    for doc in PLUGIN_DOCS:
        path = ROOT / doc
        if not path.is_file():
            continue  # a tree without that doc cannot contradict it
        blob = read(path)
        for name in names:
            if name in blob:
                continue
            findings.append(Finding(
                "undocumented-plugin", doc, 0,
                f"plugin {name!r} is declared in .claude-plugin/marketplace.json but never named "
                f"in {doc}; it ships to users while the doc that describes what ships omits it",
            ))
    return findings, len(names)


# ---------------------------------------------------------------------------
# Rule: doctrine-call-site-mismatch
# ---------------------------------------------------------------------------

# Skills are doctrine other agents follow VERBATIM, so a call site naming an API
# that does not exist is generated code that raises in a user's project. This class
# surfaced seven times in two days (#182): five were caught by throwaway scripts
# written in the moment and discarded, and two shipped. Ad-hoc catching is not
# enforcement, which is the same lesson as #151 and #171.

_COMPONENT_CLASS = re.compile(
    r"class\s+(\w+)\s*<\s*ViewComponent::Base(.*?)(?=\nclass |\n```|\Z)", re.S
)
_SLOT_DECL = re.compile(r"renders_(?:one|many)\s+:(\w+)")
_INIT_KW = re.compile(r"def\s+initialize\(([^)]*)\)", re.S)
_KEYWORD = re.compile(r"(\w+):")
# `render(` and paren-less `render ` both, because ERB idiomatically omits the outer parens.
# #182 fixed this same blind spot for the icon rule -- "the rule initially required
# parentheses, so it would not have caught the violation that motivated it" -- but the fix was
# never applied to these two render rules. Found by mutating a new call site and watching
# nothing fire (#142). `\w+\.new\(` immediately after keeps this from matching
# `render partial:` and friends.
_RENDER_CALL = re.compile(r"render\(?\s*(?:\w+::)?(\w+)\.new\(([^)]*)\)", re.S)
# A slot use only counts when the receiver is the block variable of a `render(...)`
# call, because `with_*` is a common Ruby idiom elsewhere: ActiveRecord has
# `with_lock` / `with_connection`, ruby_llm has `with_instructions` / `with_tool`.
# Matching every `.with_x` in the corpus produced six false positives against one
# real finding — and a linter that cries wolf gets disabled, which is the failure
# this rule exists to prevent.
_RENDER_BLOCK = re.compile(
    r"render\(?\s*(?:\w+::)?(\w+)\.new\([^)]*\)\s*\)?\s*do\s*\|\s*(\w+)\s*\|"
)
# Both call forms, because Ruby allows dropping the parens and ERB usually does —
# the original version required `(` and so would not have caught the very violation
# that motivated this rule (`lucide_icon "chevron-right", class: "size-4"`).
_ICON_CALL = re.compile(r"lucide_icon\s*\(?")
_ICON_BAD_ARG = re.compile(r"\b(?:size|class)\s*:")


def _icon_call_carries_size(line: str) -> bool:
    """True when a lucide_icon call is itself passed a size:/class: argument.

    Only the call's OWN arguments count. The prescribed shape wraps the icon in a
    styled span — `tag.span(helpers.lucide_icon("x"), class: "with-icon")` — so a
    naive scan forward from `lucide_icon` reads the span's `class:` as the icon's and
    flags the doctrine's own correct example. That happened, hence the paren matching:

      parenthesised  -> read to the matching `)` and inspect only inside it
      paren-less     -> read to the ERB tag close or end of line
    """
    for match in _ICON_CALL.finditer(line):
        rest = line[match.end():]
        if match.group(0).rstrip().endswith("("):
            depth, args = 1, []
            for char in rest:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                args.append(char)
            scope = "".join(args)
        else:
            stop = rest.find("%>")
            scope = rest if stop == -1 else rest[:stop]
        if _ICON_BAD_ARG.search(scope):
            return True
    return False


def check_doctrine_call_sites() -> tuple[list[Finding], dict[str, int]]:
    """Call sites in skills/ must name APIs those same skills declare."""
    docs = [p for p in walk(".md") if "skills" in rel(p).split("/")]
    if not docs:
        return [], {"skill_docs": 0, "declared_components": 0}

    bodies = {p: read(p) for p in docs}

    slots_by_class: dict[str, set[str]] = {}
    init_kw: dict[str, set[str]] = {}
    for body in bodies.values():
        for name, class_body in _COMPONENT_CLASS.findall(body):
            declared = set(_SLOT_DECL.findall(class_body))
            if declared:
                slots_by_class[name] = declared
            match = _INIT_KW.search(class_body)
            if match:
                init_kw[name] = set(_KEYWORD.findall(match.group(1)))

    findings: list[Finding] = []
    for path, body in bodies.items():
        where = rel(path)
        for index, line in enumerate(body.splitlines(), start=1):
            # Icon call shape. The doctrine's stated reason: `with-icon` sizes the svg
            # to 1em and SVG presentation attributes carry zero CSS specificity, so a
            # per-call size is both redundant and against the non-negotiable.
            if _icon_call_carries_size(line):
                findings.append(Finding(
                    "doctrine-call-site-mismatch", where, index,
                    "lucide_icon must not receive size:/class: — icons size via the "
                    "`with-icon` utility (component-implementations.md -> Icons)",
                ))
        # Slot names, scoped to the receiver of a render block. For each
        # `render(Cls.new(...)) do |v|`, every `v.with_x` until the NEXT render block must be a
        # slot Cls declares. A class whose slots are undocumented is skipped: that is a
        # coverage gap (#168), a different finding from a wrong call.
        #
        # The window ends at the next render block rather than at end-of-document, because two
        # blocks in one file routinely bind the SAME variable name -- `do |d|` for a Disclosure
        # and `do |d|` for a Dropdown. Scanning to end-of-document attributed the second block's
        # slots to the first class and reported a false positive on correct markup (found in
        # #142, where a new `do |d|` block landed above an existing one). A rule that flags
        # correct input is the failure mode this whole file warns about.
        blocks = list(_RENDER_BLOCK.finditer(body))
        for position, match in enumerate(blocks):
            cls, var = match.group(1), match.group(2)
            declared = slots_by_class.get(cls)
            if declared is None:
                continue
            stop = blocks[position + 1].start() if position + 1 < len(blocks) else len(body)
            tail = body[match.end():stop]
            for used in set(re.findall(rf"\b{re.escape(var)}\.with_(\w+)\b", tail)):
                # `renders_many :options` declares the slot as `options` but ViewComponent's setter
                # is the SINGULAR `with_option`, so a correct call site must not be flagged. Accept
                # the declared name or a naive de-pluralisation of it. Deliberately naive rather
                # than reaching for a real inflector: this is a lint with no ActiveSupport, and
                # over-accepting one form is far cheaper than flagging correct doctrine. A genuinely
                # undeclared slot (`with_choice`) still fires, which the fixtures pin.
                #
                # Never surfaced before #95 because no shipped call site used a renders_many slot —
                # existing components pass collections as initializer args instead.
                if used in declared or f"{used}s" in declared:
                    continue
                line_no = body[:match.end()].count("\n") + 1
                findings.append(Finding(
                    "doctrine-call-site-mismatch", where, line_no,
                    f"`{var}.with_{used}` — {cls} declares slots {sorted(declared)}",
                ))

        # Initializer keywords, per component, only where the initializer is shown.
        # An undeclared component is a coverage gap (#168), a different finding.
        for cls, args in _RENDER_CALL.findall(body):
            declared = init_kw.get(cls)
            if declared is None:
                continue
            unknown = sorted(set(_KEYWORD.findall(args)) - declared)
            if unknown:
                findings.append(Finding(
                    "doctrine-call-site-mismatch", where, 0,
                    f"{cls}.new called with {unknown} but its initializer accepts "
                    f"{sorted(declared)}",
                ))

    return findings, {"skill_docs": len(docs), "declared_components": len(init_kw)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> tuple[list[Finding], dict[str, int]]:
    python_sources = {path: read(path) for path in walk(".py")}
    dead, dead_examined = check_dead_settings_keys(python_sources)
    unenforced, flag_examined = check_unenforced_mandatory_flags(python_sources)
    undocumented, plugins_examined = check_undocumented_plugins()
    unbounded, queries_examined = check_unbounded_issue_queries()
    call_sites, call_coverage = check_doctrine_call_sites()
    coverage = {
        "python_modules": len(python_sources),
        "json_settings_files_examined": dead_examined,
        "documented_flag_claims_examined": flag_examined,
        "declared_plugins": plugins_examined,
        "gh_list_calls_examined": queries_examined,
        **call_coverage,
    }
    return dead + unenforced + undocumented + unbounded + call_sites, coverage


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

    # -- unbounded-issue-query (#211) --------------------------------------
    # `gh issue list` defaults to --limit 30. This shipped twice: issue-triager's DUPLICATE
    # detection and maintainer-audit's clustering both read a page and treated it as the whole
    # tracker. The maintainer was told "30 open issues" when there were 42.
    Q = "unbounded-issue-query"
    scenario(
        "an unbounded duplicate search", rule=Q, expect_finding=True,
        files={"cmd.md": 'Dedupe with `gh issue list --state all --search "x"`.\n'},
    )
    scenario(
        "bounded with --limit", rule=Q, expect_finding=False,
        files={"cmd.md": 'Dedupe with `gh issue list --state all --search "x" --limit 200`.\n'},
    )
    # --paginate bounds nothing but truncates nothing either, so it answers the same question.
    scenario(
        "--paginate is a correct answer, not a violation", rule=Q, expect_finding=False,
        files={"cmd.md": "`gh api --paginate -X GET search/issues -f q='is:open'`\n"},
    )
    scenario(
        "gh pr list is the same defect", rule=Q, expect_finding=True,
        files={"cmd.md": "`gh pr list --state open --json number`\n"},
    )
    # NEAR MISS, and the reason this rule grades invocations rather than mentions: CHANGELOG.md
    # records "the command only ever saw `gh issue list` before". That is history. A rule that
    # fired on it would demand rewriting a past record, get overridden, and then catch nothing.
    scenario(
        "near miss: a bare prose mention is a reference, not an invocation",
        rule=Q, expect_finding=False,
        files={"CHANGELOG.md": "the command only ever saw `gh issue list` before\n"},
    )
    # ...but the same file is NOT exempt when it actually documents an unbounded invocation, so
    # the narrowing is about invocation-shape, not about trusting a filename.
    scenario(
        "near miss: history is not a blanket exemption",
        rule=Q, expect_finding=True,
        files={"CHANGELOG.md": "Run `gh issue list --label comp:x` to cluster.\n"},
    )

    # -- undocumented-plugin (#203) ---------------------------------------
    # design-flow shipped while CLAUDE.md's "what this repo distributes" section named the other
    # four and said "four app-builder plugins". Both directions pinned.
    MANIFEST = '{"plugins":[{"name":"rails-stack"},{"name":"design-flow"}]}\n'
    scenario(
        "a declared plugin CLAUDE.md never names", rule="undocumented-plugin", expect_finding=True,
        files={
            ".claude-plugin/marketplace.json": MANIFEST,
            "CLAUDE.md": "We ship rails-stack.\n",
            "README.md": "We ship rails-stack and design-flow.\n",
        },
    )
    scenario(
        "a declared plugin README.md never names", rule="undocumented-plugin", expect_finding=True,
        files={
            ".claude-plugin/marketplace.json": MANIFEST,
            "CLAUDE.md": "We ship rails-stack and design-flow.\n",
            "README.md": "We ship rails-stack.\n",
        },
    )
    scenario(
        "every declared plugin is named in both docs",
        rule="undocumented-plugin", expect_finding=False,
        files={
            ".claude-plugin/marketplace.json": MANIFEST,
            "CLAUDE.md": "We ship rails-stack and design-flow.\n",
            "README.md": "design-flow layers onto rails-stack.\n",
        },
    )
    # Counts are NOT the rule. Prose referring to a subset is correct writing, and flagging it is
    # how a linter earns being switched off — so this must stay silent despite saying "one plugin"
    # about a two-plugin marketplace.
    scenario(
        "near miss: a subset count in prose is not a finding",
        rule="undocumented-plugin", expect_finding=False,
        files={
            ".claude-plugin/marketplace.json": MANIFEST,
            "CLAUDE.md": "The one plugin above builds apps; design-flow and rails-stack ship.\n",
            "README.md": "rails-stack, plus design-flow.\n",
        },
    )
    # No manifest means no verdict — the rule must not fire on trees it cannot judge, or every
    # other fixture in this file would produce a spurious finding.
    scenario(
        "no marketplace.json means no verdict", rule="undocumented-plugin", expect_finding=False,
        files={"CLAUDE.md": "No plugins declared anywhere.\n"},
    )

    # -- SKIP_DIRS: the licensed corpora are not our claims (#197) ---------
    # The kits are a gitignored nested clone carrying ~125 vendor markdown files. Both
    # directions are pinned: before #197 they were symlinked in and os.walk skipped them for
    # free, so nothing here was load-bearing; a real subdirectory needs a deliberate prune.
    # The prune is by EXACT directory name, and the near-miss proves a same-prefix directory of
    # OURS is still scanned — so the exemption cannot be widened by naming a folder
    # `design-corpora-anything`.
    CORPORA_CLAIM = "Always pass `--budget-usd` when running live.\n"
    OPTIONAL_FLAG = ('import argparse\np=argparse.ArgumentParser()\n'
                     'p.add_argument("--budget-usd", type=float, default=None)\n')
    scenario(
        "a vendor claim inside design-corpora/ is not ours to enforce",
        rule="unenforced-mandatory-flag", expect_finding=False,
        files={"design-corpora/flowbite/README.md": CORPORA_CLAIM, "tool.py": OPTIONAL_FLAG},
    )
    scenario(
        "near miss: design-corpora-notes/ is ours and stays scanned",
        rule="unenforced-mandatory-flag", expect_finding=True,
        files={"design-corpora-notes/README.md": CORPORA_CLAIM, "tool.py": OPTIONAL_FLAG},
    )

    # -- doctrine-call-site-mismatch --------------------------------------
    R = "doctrine-call-site-mismatch"
    COMPONENT = (
        "skills/x/references/impl.md",
        "```ruby\nmodule Ui\n  class CardComponent < ViewComponent::Base\n"
        "    renders_one :header\n    renders_one :body\n"
        "    def initialize(title:, size: :md)\n      @title, @size = title, size\n"
        "    end\n  end\nend\n```\n",
    )

    scenario("initializer keyword that does not exist", rule=R, expect_finding=True,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render(Ui::CardComponent.new(form: f, title: \"x\")) %>\n```\n"})
    scenario("initializer keywords all declared", rule=R, expect_finding=False,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render(Ui::CardComponent.new(title: \"x\", size: :lg)) %>\n```\n"})
    scenario("slot that the component does not declare", rule=R, expect_finding=True,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render(Ui::CardComponent.new(title: \"x\")) do |c| %>\n"
                    "  <% c.with_rail do %>nope<% end %>\n<% end %>\n```\n"})
    scenario("declared slot", rule=R, expect_finding=False,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render(Ui::CardComponent.new(title: \"x\")) do |c| %>\n"
                    "  <% c.with_header do %>ok<% end %>\n<% end %>\n```\n"})

    # Paren-less `render Cls.new(...)` — the form ERB idiomatically uses. Both render rules
    # required the outer paren, so these two escaped entirely until #142's new call site fell
    # into the gap. #182 records fixing exactly this blind spot for the ICON rule; the fix was
    # never carried to its two siblings.
    scenario("paren-less render: undeclared slot is still caught", rule=R, expect_finding=True,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render Ui::CardComponent.new(title: \"x\") do |c| %>\n"
                    "  <% c.with_rail do %>nope<% end %>\n<% end %>\n```\n"})
    scenario("paren-less render: wrong initializer keyword is still caught",
             rule=R, expect_finding=True,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render Ui::CardComponent.new(form: f, title: \"x\") %>\n```\n"})
    scenario("paren-less render: a correct call stays silent", rule=R, expect_finding=False,
             files={COMPONENT[0]: COMPONENT[1] +
                    "```erb\n<%= render Ui::CardComponent.new(title: \"x\") do |c| %>\n"
                    "  <% c.with_header do %>ok<% end %>\n<% end %>\n```\n"})

    # renders_many declares a PLURAL slot but ViewComponent's setter is SINGULAR, so a correct
    # `with_option` against `renders_many :options` must stay silent. Found by writing the first
    # shipped call site that uses a renders_many slot (#95) and watching the linter flag it.
    MANY = (
        "skills/x/references/impl.md",
        "```ruby\nmodule Ui\n  class ListComponent < ViewComponent::Base\n"
        "    renders_many :options\n    def initialize(id:)\n      @id = id\n    end\n  end\nend\n```\n",
    )
    scenario("renders_many: the singular setter is correct, not a mismatch",
             rule=R, expect_finding=False,
             files={MANY[0]: MANY[1] +
                    "```erb\n<%= render Ui::ListComponent.new(id: \"x\") do |c| %>\n"
                    "  <% c.with_option { \"a\" } %>\n<% end %>\n```\n"})
    scenario("renders_many: the plural setter is accepted too", rule=R, expect_finding=False,
             files={MANY[0]: MANY[1] +
                    "```erb\n<%= render Ui::ListComponent.new(id: \"x\") do |c| %>\n"
                    "  <% c.with_options { \"a\" } %>\n<% end %>\n```\n"})
    # NEAR MISS: accepting a de-pluralisation must not accept an unrelated slot.
    scenario("renders_many: a genuinely undeclared slot still fires", rule=R, expect_finding=True,
             files={MANY[0]: MANY[1] +
                    "```erb\n<%= render Ui::ListComponent.new(id: \"x\") do |c| %>\n"
                    "  <% c.with_choice { \"a\" } %>\n<% end %>\n```\n"})

    # TWO blocks binding the SAME variable. Scanning to end-of-document attributed the second
    # block's slots to the first class and flagged correct markup — found in #142, where a new
    # `do |d|` landed above an existing one. The window must end at the next render block.
    # ONE class per fenced block: the declaration parser registers a single component per fence,
    # so two classes in one fence silently leaves the second unregistered — which made the first
    # version of the cross-contamination fixture below VACUOUS (it passed with the fix reverted).
    # Found by reverting the fix and checking the fixture actually failed.
    TWO_CLASSES = (
        "skills/x/references/impl.md",
        "```ruby\nmodule Ui\n  class OneComponent < ViewComponent::Base\n"
        "    renders_one :alpha\n    def initialize(a:)\n      @a = a\n    end\n  end\nend\n```\n"
        "```ruby\nmodule Ui\n  class TwoComponent < ViewComponent::Base\n"
        "    renders_one :beta\n    def initialize(b:)\n      @b = b\n    end\n  end\nend\n```\n",
    )
    scenario("two render blocks reusing one variable name do not bleed into each other",
             rule=R, expect_finding=False,
             files={TWO_CLASSES[0]: TWO_CLASSES[1] +
                    "```erb\n<%= render Ui::OneComponent.new(a: 1) do |d| %>\n"
                    "  <% d.with_alpha do %>ok<% end %>\n<% end %>\n"
                    "<%= render Ui::TwoComponent.new(b: 2) do |d| %>\n"
                    "  <% d.with_beta do %>ok<% end %>\n<% end %>\n```\n"})
    # ...and narrowing the window must not blind the rule inside its own block.
    scenario("narrowing the window still catches a bad slot in the FIRST block",
             rule=R, expect_finding=True,
             files={TWO_CLASSES[0]: TWO_CLASSES[1] +
                    "```erb\n<%= render Ui::OneComponent.new(a: 1) do |d| %>\n"
                    "  <% d.with_nope do %>bad<% end %>\n<% end %>\n"
                    "<%= render Ui::TwoComponent.new(b: 2) do |d| %>\n"
                    "  <% d.with_beta do %>ok<% end %>\n<% end %>\n```\n"})

    # The six false positives that the first version of this rule produced. `with_*` is
    # a common Ruby idiom outside ViewComponent, and flagging it made the rule useless.
    scenario("ActiveRecord and gem `with_*` idioms are not slots", rule=R, expect_finding=False,
             files={"skills/x/references/models.md":
                    "```ruby\nrecord.with_lock { record.save! }\n"
                    "ActiveRecord::Base.with_connection { |c| c.execute(sql) }\n"
                    "chat.with_instructions(\"be terse\").with_temperature(0.2)\n"
                    "  .with_tool(Weather).with_schema(Schema)\n```\n"})

    scenario("icon call carrying a size class", rule=R, expect_finding=True,
             files={"skills/x/references/i.md":
                    "```erb\n<%= lucide_icon \"chevron-right\", class: \"size-4\" %>\n```\n"})
    scenario("bare icon call", rule=R, expect_finding=False,
             files={"skills/x/references/i.md":
                    "```erb\n<span class=\"with-icon\"><%= lucide_icon(\"x\") %></span>\n```\n"})
    # The prescribed shape passes `class:` to the WRAPPER, not the icon. Scanning
    # forward from `lucide_icon` flagged this — i.e. the rule flagged the doctrine's
    # own correct example, which is why the check matches parens.
    scenario("class: belongs to the wrapping tag, not the icon", rule=R, expect_finding=False,
             files={"skills/x/references/i.md":
                    "```ruby\ndef sep = tag.span(helpers.lucide_icon(\"chevron-right\"), "
                    "class: \"with-icon\", aria: { hidden: true })\n```\n"})
    scenario("paren-less icon call with a size class", rule=R, expect_finding=True,
             files={"skills/x/references/i.md":
                    "```erb\n<%= lucide_icon \"chevron-right\", class: \"size-4\" %>\n```\n"})

    # A component whose initializer is not documented is a coverage gap (#168), which is
    # a different finding — this rule must not guess at an undocumented signature.
    scenario("undocumented component is skipped, not guessed at", rule=R, expect_finding=False,
             files={"skills/x/references/impl.md":
                    "```erb\n<%= render(Ui::MysteryComponent.new(whatever: 1)) %>\n```\n"})

    print(f"ran {checks} self-consistency assertion(s)")
    if failures:
        print(f"\n{len(failures)} FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("every rule fires on a violation and stays silent on conforming input")
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
    # Every counter is printed, not a hand-picked subset: a clean result over input a
    # rule never read reads as a pass, so the report must show what each rule saw.
    labels = {
        "python_modules": "python module(s)",
        "json_settings_files_examined": "json settings file(s)",
        "documented_flag_claims_examined": "documented flag claim(s)",
        "declared_plugins": "declared plugin(s)",
        "gh_list_calls_examined": "gh list call(s)",
        "skill_docs": "skill doc(s)",
        "declared_components": "declared component(s)",
    }
    print("scanned " + "; ".join(
        f"{value} {labels.get(key, key)}" for key, value in coverage.items()
    ))

    if not findings:
        print("no findings.")
        return 0

    for finding in findings:
        print(finding)
    print(f"\n{len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
