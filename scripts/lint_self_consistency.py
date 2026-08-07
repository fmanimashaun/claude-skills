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
  component-without-call-site a documented component nothing demonstrates — a reader must
                              infer the invocation, and the call-site rule skips it silently
  undeclared-component-call-site  a call site naming a component no skill declares, so its
                              keywords and slots cannot be checked
  doctrine-call-site-mismatch a call site in skills/ naming an API those skills do not
                              declare — a wrong initializer keyword, an undeclared slot,
                              or an icon passed a size it must not take
  broken-doc-pointer          a documented path to one of OUR files that does not resolve: an
                              agent is told to read doctrine that cannot be opened, and the
                              pointer still reads as authoritative
  controller-inventory-gap    markup in the fidara-design docs naming a Stimulus controller the
                              controller inventory omits — the reader inherits a dependency the
                              doctrine never told them to build

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
# `worktrees` is where Claude Code puts background-agent worktrees — a FULL repo copy each,
# inside `.claude/`, which is one of our roots. Unpruned, a sweep scans every copy: sixteen
# agents took this linter from 129 files to 1526, and an agent's half-finished edit would
# fail the maintainer's own gate run with a finding that is not in the maintainer's tree.
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv", "design-corpora", "worktrees"}

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
# Rule: component-without-call-site  /  undeclared-component-call-site
# ---------------------------------------------------------------------------
# Two halves of one guarantee: every documented component is DEMONSTRATED, and every
# demonstration names something real.
#
# A class definition shows what a component accepts; it does not show how to CALL it, and inferring
# the invocation is how `FieldComponent.new(form:, name:)` and `field_classes` both SHIPPED and
# raised in a user's project (#168, #182). It is also how the doctrine-call-site rule goes quiet: a
# component with no call site has nothing to check, so it is skipped silently.
#
# BOTH RULES WERE ADDABLE ONLY AFTER THE WORK. A call-site rule would have produced 14 findings the
# day it landed (#238) -- and per this file's own thesis a linter that starts red gets suppressed,
# so the class stops being caught at all. The call sites were written first; the rules hold the line
# now that the count is zero. Same for ghosts: `SparklineComponent` (invented while writing those
# call sites) and `DropdownComponent` (undeclared for as long as it existed) both had to be fixed
# before this could be a gate rather than a backlog.
_TOP_LEVEL_COMPONENT = re.compile(
    r"^  class\s+(\w+Component)\s*<\s*ViewComponent::Base", re.M
)
# A NESTED class is reached through its parent's slot setter (`l.with_row(...)`), never a bare
# `render`, so demanding a standalone call site for it would demand something impossible.
_NESTED_COMPONENT = re.compile(
    r"^    class\s+(\w+Component)\s*<\s*ViewComponent::Base", re.M
)
# `**attrs` / `**options` — an initializer that forwards arbitrary keywords. Its call sites
# cannot be checked for unknown keywords, so such components are excluded from that check.
_KW_SPLAT = re.compile(r"\*\*\w+")
_COMPONENT_CALL = re.compile(r"render\(?\s*(?:\w+::)?(\w+Component)\.new")


def check_component_call_sites() -> tuple[list[Finding], int]:
    """Every documented component is demonstrated, and every demonstration names a real one."""
    docs = [p for p in walk(".md") if "skills" in rel(p).split("/")]
    if not docs:
        return [], 0
    body = "\n".join(read(p) for p in docs)

    top = set(_TOP_LEVEL_COMPONENT.findall(body))
    nested = set(_NESTED_COMPONENT.findall(body))
    called = set(_COMPONENT_CALL.findall(body))
    if not top:
        return [], 0

    findings: list[Finding] = []
    for name in sorted(top - called):
        findings.append(Finding(
            "component-without-call-site", "skills/**", 0,
            f"{name} is documented but never called -- a reader must infer the invocation, which "
            "is how a wrong call site ships, and the doctrine-call-site rule silently skips a "
            "component it has no call site for",
        ))
    # A call site naming a component nothing declares is unverifiable by the call-site rule, which
    # skips unknown classes by design. Nested classes are legitimate targets of a bare render too,
    # so they count as declared here.
    for name in sorted(called - top - nested):
        findings.append(Finding(
            "undeclared-component-call-site", "skills/**", 0,
            f"{name} is called but no skill declares it -- its keywords and slots cannot be "
            "checked, so a wrong signature here is invisible",
        ))
    return findings, len(top)


# ---------------------------------------------------------------------------
# Rule: controller-inventory-gap
# ---------------------------------------------------------------------------
#
# fidara-design tells a reader which Stimulus controllers exist, in one inventory under
# `## Controller conventions`, and separately hands them markup carrying `data-controller="…"`.
# Nothing reconciled the two, and they had drifted badly: the inventory said `carousel` was
# "the only new controller the #95 rows need" while the shipped snippets prescribed `dropzone`,
# `clipboard`, `combobox`, `disclosure` and `feed` by name (#95). An agent copying a snippet
# then has to write a controller the doctrine never told it existed -- and for `dropzone` the
# doctrine also warns that none of the four mixins covers a gesture, so the missing entry is
# where the hard part was.
#
# ONE DIRECTION ONLY, deliberately. Markup naming a controller the inventory omits is the
# defect: the reader is left with an unspecified dependency. The reverse -- an inventory entry
# with no snippet -- is ordinary, because the list also names controllers that live in the apps
# (`search`, `multistep`, `countdown`) and appear in no reference markup at all. A rule firing
# on those would be the false-positive kind that gets a linter switched off.

_CONTROLLER_REFS = "skills/fidara-design/references"
_CONTROLLER_INVENTORY = f"{_CONTROLLER_REFS}/interaction-stimulus.md"
_CONTROLLER_INVENTORY_HEADING = "## Controller conventions"

_DATA_CONTROLLER_ATTR = re.compile(r'data-controller~?=\s*(?:"([^"]*)"|([^\s">]+))')
_ERB_TAG = re.compile(r"<%=?-?(.*?)-?%>", re.S)
_QUOTED_LITERAL = re.compile(r"""['"]([^'"]+)['"]""")
# Fenced blocks come out of the section before its code spans are read, and that one line carries
# BOTH reasons the naive version was wrong.
#
#   * The off-by-one. A ``` fence is three backticks, so the span pattern pairs the third with the
#     closing fence's first and every span after it captures the PROSE BETWEEN spans instead of the
#     spans. This rule's first run read an inventory of 38 healthy-looking entries containing not
#     one controller name, and it was visible only because the rule then fired on all 18.
#   * The leniency. A name inside a fenced EXAMPLE is a perfectly well-formed code span, so
#     `dropzone` merely discussed in a snippet would count as the inventory naming it -- silencing
#     a real finding. The rule must read the inventory's prose, not its examples.
#
# Excluding `\n` from the span pattern also kills the first of those, and it was written that way
# at first. It is not here, because with fences already gone it is a defence no fixture and no
# mutation can distinguish from its absence -- and per this file's own thesis, a guard nothing can
# fail is not a guard. One line, one fixture each way, one mutation.
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_BACKTICKED = re.compile(r"`([^`]+)`")
_CONTROLLER_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def controller_names(value: str) -> set[str]:
    """The controller names in one `data-controller` attribute value.

    ERB is read as a SEPARATE half rather than stripped or tokenised whole, because both
    shortcuts are wrong in opposite directions. `data-controller="theme <%= 'native-bridge' if
    native_app? %>"` is a real line in mobile-reference-implementation.md: tokenising the raw
    value accepts `if` as a controller, and deleting the ERB loses `native-bridge` entirely. So
    outside ERB a bare token counts, and inside ERB only a string literal does.
    """
    names: set[str] = set()
    for erb in _ERB_TAG.findall(value):
        names |= {m for m in _QUOTED_LITERAL.findall(erb) if _CONTROLLER_NAME.match(m)}
    names |= {t for t in _ERB_TAG.sub(" ", value).split() if _CONTROLLER_NAME.match(t)}
    return names


def check_controller_inventory() -> tuple[list[Finding], int]:
    """Every controller the fidara-design docs prescribe is named in the inventory."""
    inventory_path = ROOT / _CONTROLLER_INVENTORY
    refs = ROOT / _CONTROLLER_REFS
    if not inventory_path.is_file() or not refs.is_dir():
        return [], 0

    body = read(inventory_path)
    start = body.find(_CONTROLLER_INVENTORY_HEADING)
    if start < 0:
        # Fail LOUD, not quiet. A renamed heading would otherwise silence the rule while
        # leaving its coverage number looking healthy -- `skip` is not `pass`.
        return [Finding(
            "controller-inventory-gap", _CONTROLLER_INVENTORY, 0,
            f"no {_CONTROLLER_INVENTORY_HEADING!r} section — the rule cannot find the inventory "
            "it reconciles markup against, so every controller below is unchecked",
        )], 0
    end = body.find("\n## ", start + len(_CONTROLLER_INVENTORY_HEADING))
    section = _FENCE.sub("", body[start: end if end > 0 else len(body)])
    inventory = {t for t in _BACKTICKED.findall(section) if _CONTROLLER_NAME.match(t)}

    prescribed: dict[str, tuple[str, int]] = {}
    for path in sorted(refs.glob("*.md")):
        for line_no, line in enumerate(read(path).splitlines(), 1):
            for quoted, bare in _DATA_CONTROLLER_ATTR.findall(line):
                for name in controller_names(quoted or bare):
                    prescribed.setdefault(name, (rel(path), line_no))

    findings = [
        Finding(
            "controller-inventory-gap", where, line_no,
            f"`data-controller` names {name!r}, which the {_CONTROLLER_INVENTORY_HEADING!r} "
            "inventory never mentions — a reader copying this markup inherits a controller the "
            "doctrine does not admit exists, and no mixin is named for it",
        )
        for name, (where, line_no) in sorted(prescribed.items())
        if name not in inventory
    ]
    return findings, len(prescribed)


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
# A paren-less call is only an INVOCATION if what follows looks like an argument list: a string
# or symbol literal, or an identifier followed by a comma. Prose *about* the call reads
# `lucide_icon takes no size:/class:` — the words after it are not arguments. Without this the
# rule flags documentation that states the rule, which is how a linter earns a blanket disable
# (same shape as the CHANGELOG false positive already fixed in `unbounded-issue-query`).
_PAREN_LESS_ARGS = re.compile(r"^[ \t]*(?:[\"\':]|\w+[ \t]*,)")


def _icon_call_carries_size(line: str) -> bool:
    """True when a lucide_icon call is itself passed a size:/class: argument.

    Only the call's OWN arguments count. The prescribed shape wraps the icon in a
    styled span — `tag.span(helpers.lucide_icon("x"), class: "with-icon")` — so a
    naive scan forward from `lucide_icon` reads the span's `class:` as the icon's and
    flags the doctrine's own correct example. That happened, hence the paren matching:

      parenthesised  -> read to the matching `)` and inspect only inside it
      paren-less     -> must LOOK like an argument list, then read to the ERB close or EOL

    The paren-less guard matters as much as the paren matching: `lucide_icon takes no size:/class:`
    is a sentence, and flagging the file that documents the rule is how the rule gets deleted.
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
            if not _PAREN_LESS_ARGS.match(rest):
                continue  # prose, not a call — see _PAREN_LESS_ARGS
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
                # A `**attrs` splat means the initializer accepts ARBITRARY keywords, so the
                # extra-keyword check below cannot say anything about it. Recording the component
                # here at all would flag every correct call site that passes `data:`/`aria-*` —
                # which is most of them, since that is how ViewComponent forwards HTML attributes.
                # Found when the rule flagged `ButtonComponent.new(..., data: { action: ... })`,
                # which is legal: its initializer ends in `**attrs`. The ModalComponent flag that
                # preceded it was correct — that one has no splat — so the fix must key on the
                # splat, not weaken the check.
                if not _KW_SPLAT.search(match.group(1)):
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
# Rule: invisible-character
# ---------------------------------------------------------------------------
# A no-break space renders identically to a space and makes the text UNGREPPABLE. Two of them reached
# a shipped behaviour table in v1.39.0 (`role=region`\xa0**or**\xa0`group`), and the way they surfaced
# is the argument for the rule: an anchored edit to that row failed with "0 matches" against a string
# copied from the file, and finding out why took a byte-level diff. A reader searching the doctrine for
# that phrase gets nothing, silently.
#
# Mechanical with no judgement, per this file's bar. Only characters with NO legitimate use in our
# corpus are listed: the em dash, ellipsis, arrows and box-drawing we use deliberately are not here.
# A NARROW NO-BREAK SPACE inside a code fence is still a defect — it is invisible there too.
_INVISIBLE = {
    "\u00a0": "NO-BREAK SPACE",
    "\u2007": "FIGURE SPACE",
    "\u2009": "THIN SPACE",
    "\u200a": "HAIR SPACE",
    "\u202f": "NARROW NO-BREAK SPACE",
    "\u2060": "WORD JOINER",
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\ufeff": "BYTE ORDER MARK",
    # C0 CONTROL BYTES. The table above is typographic -- characters that look like a space and are
    # not. These are worse and were missing: a control byte inside a REGEX LITERAL silently changes
    # what the pattern means, and `inspect.getsource` renders it invisibly, so the source reads
    # correctly while the rule matches nothing. That is `gate-that-cannot-fail` with no symptom.
    #
    # Found the only way it can be: a `\b` written through a shell heredoc became a literal 0x08
    # in `undeclared-skill-dependency` (#513), and the pattern then required a backspace after
    # "stop". The rule reported clean on input it could never match. TAB and the line endings are
    # excluded because they are legitimate.
    "\x08": "BACKSPACE",
    "\x0b": "VERTICAL TAB",
    "\x0c": "FORM FEED",
    "\x1b": "ESCAPE",
    "\x07": "BELL",
    "\x00": "NUL",
    "\u00ad": "SOFT HYPHEN",
    "\u2028": "LINE SEPARATOR",
    "\u2029": "PARAGRAPH SEPARATOR",
}


def check_v4_outline_none() -> tuple[list[Finding], int]:
    """`outline-none` must not appear in shipped doctrine: we mandate Tailwind v4.

    A rename that keeps the old spelling alive with the OPPOSITE meaning. In v3, `outline-none`
    *"didn't actually set `outline-style: none`, and instead set an invisible outline that would
    still show up in forced colors mode for accessibility reasons"*. v4 renamed that safe utility to
    `outline-hidden` and gave the old name to one that really does remove the outline.

    The ring cannot substitute: Tailwind rings are `box-shadow`, and in forced-colors mode
    `box-shadow` computes to `none`, while `outline-color` is merely force-adjusted. So
    `outline-none` + `ring-2` leaves a forced-colors user with NO focus indicator -- WCAG 2.4.7,
    invisible in normal rendering and therefore never caught by eye.

    Nine recipes shipped this way: correct under v3, carried through the v4 migration untouched.
    Prose alone would not have caught it, which is why this is a check and not a paragraph.
    """
    findings: list[Finding] = []
    examined = 0
    for path in walk(".md"):
        if "skills/" not in rel(path).replace("\\", "/"):
            continue
        examined += 1
        body = read(path)
        for index, line in enumerate(body.splitlines(), 1):
            # `outline-hidden` must not match, and neither may prose ABOUT the rename -- the
            # doctrine explaining this defect necessarily names the bad utility. Only a real
            # Tailwind variant usage counts, which always carries a `:` prefix in our recipes.
            if re.search(r"(?<!-)\b(?:focus|focus-visible|active|group-focus)\:outline-none\b", line):
                findings.append(Finding(
                    "v4-outline-none", rel(path), index,
                    "uses `outline-none`, which in Tailwind v4 sets `outline-style: none` and "
                    "removes the focus indicator for forced-colors users -- the ring is a "
                    "box-shadow and computes to `none` there. Use `outline-hidden`, the v4 name "
                    "for v3's accessible utility. See components.md, 'The focus ring'",
                ))
    return findings, examined


def check_unwired_claim_verifier() -> tuple[list[Finding], int]:
    """`claim-verifier` must actually be invoked by the flows that claim to use it (#359).

    Criterion 5 is *"wired into the promotion flow, where the cost of a false claim is highest"*.
    That is a claim about this repo, and leaving it to prose would be the joke version of the
    defect: an agent built because descriptions go unchecked, itself described as wired and never
    called. The agent shipped in v1.52.0 and was referenced from **nowhere** until this rule.

    Deliberately narrow — it checks the wiring exists, not that anyone obeys it. Whether a
    maintainer actually reads the verdict is not mechanically knowable, and pretending otherwise
    would be the same defect one level up.
    """
    findings: list[Finding] = []
    agent = ROOT / "plugins" / "rails-flow" / "agents" / "claim-verifier.md"
    if not agent.is_file():
        return findings, 0            # not shipped in this tree; nothing to wire
    callers = {
        ".claude/agents/release-manager.md":
            "the promotion body becomes the published release notes, so a false sentence there "
            "outlives every other kind",
        ".claude/commands/maintainer-work.md":
            "the PR body is what the next reader believes about the change",
    }
    examined = 0
    for relpath, why in callers.items():
        path = ROOT / relpath
        if not path.is_file():
            continue
        examined += 1
        body = read(path)
        if "claim-verifier" not in body:
            findings.append(Finding(
                "unwired-claim-verifier", relpath, 1,
                f"never invokes `claim-verifier`, but #359 wires it in here because {why}. An "
                f"agent that verifies descriptions, itself described as wired and never called, "
                f"is the defect it was built for",
            ))
        elif "extract_claims.py" not in body:
            findings.append(Finding(
                "unwired-claim-verifier", relpath, 1,
                "names `claim-verifier` without `extract_claims.py`, so the claim list is "
                "gathered by judgement — which is the half #359 proved cannot be relied on",
            ))
    return findings, examined


def check_unhonoured_config_toggle() -> tuple[list[Finding], int]:
    """A boolean config key a plugin scaffolds must be read by one of that plugin's scripts.

    `links.check_external: false` shipped in qa-flow's scaffolded config with prose telling the
    reader to "enable it for a deliberate link audit". Nothing read it. `link_audit.py` counts
    external targets and has no code path that fetches one, so setting it `true` changed nothing
    while the documentation said otherwise.

    That is worse than an absent feature. An absent feature is visible; a dead toggle makes a reader
    believe they have opted in, and they stop looking. It is the same shape as #112's `ignored: []`,
    which the schema advertised while the collector hardcoded the empty list -- and as the five
    `checks.json` gates in #423 that waited on paths nothing writes.

    Scoped to BOOLEANS on purpose. A string or list key is often consumed by an agent rather than a
    script -- `runtime.ignore` is applied by `functional-tester`, which is a real consumer this rule
    must not flag. A boolean is different: it exists to change behaviour, and behaviour lives in
    code. Widening this to every key would make it fire on the agent-applied ones and get switched
    off, which is the failure mode the rule is about.
    """
    findings: list[Finding] = []
    examined = 0
    root = ROOT / "plugins"
    if not root.is_dir():
        return findings, examined
    for command in sorted(root.glob("*/commands/setup*.md")):
        plugin_dir = command.parent.parent
        scripts = "\n".join(
            read(path) for path in plugin_dir.glob("scripts/*")
            if path.is_file() and path.suffix in {".py", ".js"})
        if not scripts:
            continue
        body, in_yaml = read(command), False
        for number, line in enumerate(body.splitlines(), 1):
            if re.match(r"^\s*```ya?ml", line):
                in_yaml = True
                continue
            if in_yaml and re.match(r"^\s*```\s*$", line):
                in_yaml = False
                continue
            if not in_yaml:
                continue
            match = re.match(r"^\s*([a-z_][a-z0-9_]*):\s*(?:true|false)\b", line)
            if not match:
                continue
            examined += 1
            key = match.group(1)
            if not re.search(rf"[\"']{re.escape(key)}[\"']", scripts):
                findings.append(Finding(
                    "unhonoured-config-toggle", rel(command), number,
                    f"scaffolds `{key}` as a boolean, but no script in {plugin_dir.name} reads it -- "
                    f"flipping it changes nothing while the config says it will. Wire it or remove "
                    f"it; a dead toggle is worse than an absent feature because the reader believes "
                    f"they opted in",
                ))
    return findings, examined


def check_findings_schema_drift() -> tuple[list[Finding], int]:
    """qa-flow's reporter must document the SAME record fields `findings.py` enforces (#138).

    Criterion 7 asks that "qa-flow's reporter emits the same shape" so a QA defect and a review
    defect are one kind of thing. The two live in different plugins on purpose — qa-flow is
    documented as independent, so it does not import rails-flow's code — which means the **schema is
    the contract**, and a contract nothing compares is the `claims-vs-enforcement` defect this file
    exists for. Two documents agreeing today is not the same as two documents that must agree.

    Direction matters: a field in the script and missing from the doc means a QA record silently
    omits something every review record carries, and the omission surfaces only when someone runs
    the validator over a QA file. The reverse — documented but unenforced — is a promise to the
    agent that nothing keeps.
    """
    findings: list[Finding] = []
    script = ROOT / "plugins" / "rails-flow" / "scripts" / "findings.py"
    doc = ROOT / "plugins" / "qa-flow" / "agents" / "qa-reporter.md"
    if not (script.is_file() and doc.is_file()):
        return findings, 0
    source = read(script)
    canonical: dict[str, set[str]] = {}
    for group in ("REQUIRED", "OPTIONAL"):
        match = re.search(rf"^{group} = \(([^)]*)\)", source, re.M)
        if not match:
            findings.append(Finding(
                "findings-schema-drift", rel(script), 1,
                f"cannot find the `{group}` field tuple, so the schema cannot be compared. If it "
                f"was renamed, update this rule rather than leaving the comparison silently dead",
            ))
            return findings, 0
        canonical[group] = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    body = read(doc)
    documented = set(re.findall(r"`([a-z_]+)`", body))
    for group, fields in canonical.items():
        missing = sorted(f for f in fields if f not in documented)
        if missing:
            findings.append(Finding(
                "findings-schema-drift", rel(doc), 1,
                f"does not document {group.lower()} field(s) {', '.join(missing)} that "
                f"`findings.py` enforces. A QA record would omit what every review record carries",
            ))
    return findings, len(canonical["REQUIRED"]) + len(canonical["OPTIONAL"])


# --- a DISPATCH is not a MENTION (#491) ------------------------------------------------------
# The rule below used to read a backticked agent name as a dispatch. So one sentence in
# `setup-qa.md` explaining WHO CONSUMES the labels it creates took that command's count from 1 to
# 2 and produced a false `undeclared-topology`. Both escapes from that finding are worse than the
# finding: declare a topology the command does not have (a false statement written into shipped
# doctrine to satisfy a gate), or stop naming the agent (the linter deciding what doctrine may
# say). A gate whose only escapes are "lie" or "stop explaining" gets switched off.
#
# The narrowing below is deliberately BIASED TOWARD COUNTING, because for this rule a false
# negative -- an undeclared fan-out shipping unlabelled -- is worse than a false positive. Every
# knob is set the loose way on purpose:
#
#   * the verb list includes ordinary English (`run`, `use`, `call`), so a noun reading of one of
#     them counts as a dispatch rather than losing a real one;
#   * `to` and `via` are handoffs, so "compared to `x`" counts;
#   * ANY ONE occurrence dispatching is enough -- the agent need not be dispatched everywhere.
#
# What is left out is the one shape that is unambiguously not an instruction: the name buried
# mid-sentence with no imperative in front of it ("Every defect `qa-reporter` files carries ..."),
# and a name appearing only inside a fenced block. `commands_naming_2plus_agents_without_
# dispatching` in the coverage line is the instrument that makes over-narrowing visible: if this
# starts climbing, the narrowing has gone quiet, not the tree.
_FENCED = re.compile(r"^[ \t]*(?P<f>```|~~~)[^\n]*\n.*?^[ \t]*(?P=f)[^\n]*$", re.M | re.S)

# Explicit inflections rather than a stem + `\w*`: an auditable list is the point, and `\brun\w*`
# would also swallow `runtime`.
_DISPATCH_VERB = re.compile(
    r"\b(?:"
    r"dispatch|dispatches|dispatched|dispatching|"
    r"delegate|delegates|delegated|delegating|"
    r"hand|hands|handed|handing|handoff|hand-off|"
    r"invoke|invokes|invoked|invoking|"
    r"launch|launches|launched|launching|"
    r"spawn|spawns|spawned|spawning|"
    r"run|runs|ran|running|"
    r"call|calls|called|calling|"
    r"use|uses|used|using|"
    r"ask|asks|asked|asking|"
    r"send|sends|sent|sending|"
    r"route|routes|routed|routing|"
    r"escalate|escalates|escalated|escalating|"
    r"assign|assigns|assigned|assigning|"
    r"task|tasks|tasked"
    r")\b", re.I)

# `**Security** -> `security-auditor``, `these go to `migration-writer``. A determiner may sit
# between the arrow and the name (`-> the `a11y-auditor` agent`) -- allowed, because the loose
# reading is the safe one here.
_HANDOFF_PREFIX = re.compile(
    r"(?:→|⇒|->|=>|\bto|\bvia)[ \t]*(?:\*\*|__)?[ \t]*(?:the|a|an|our)?[ \t]*(?:\*\*|__)?\s*$",
    re.I)

# The harness invocation itself. Counts wherever it appears, fenced or not -- a fenced
# `Task(subagent_type: "x")` is the most literal dispatch there is.
_TASK_INVOCATION = re.compile(r"\bsubagent_type\b|\bTask\s*\(", re.I)

# Everything a step may open with before its first word: indentation, blockquote/heading markers,
# a list bullet or number, and emphasis. If NOTHING else precedes the name, the name is the
# subject of the step -- `\`qa-reporter\` consolidates.`
_STEP_LEAD = re.compile(r"^[\s>#]*(?:(?:[-*+]|\d+[.)])[ \t]+)?[\s>*_]*$")

# A sentence ends at `.!?` plus any closing punctuation, before whitespace. `:` is NOT a boundary:
# "Dispatch all layers: `e2e-tester` (...), `api-contract-tester` (...)" is one instruction.
_SENTENCE_END = re.compile(r"[.!?][)\]\"'`*_]*(?=\s)")
_LIST_ITEM = re.compile(r"(?:\A|\n)[ \t]*(?:[-*+]|\d+[.)])[ \t]+")

# A block ends at a blank line -- or at a thematic break / frontmatter delimiter, because a
# command's FIRST instruction often sits directly under the closing `---` with no blank line, and
# without this the frontmatter counts as that instruction's prefix and hides its subject position.
_BLOCK_BREAK = re.compile(r"\n[ \t]*\n|\n[ \t]*(?:-{3,}|={3,}|\*{3,}|_{3,})[ \t]*(?=\n)")


def _blank_fences(text: str) -> str:
    """Blank fenced code, preserving every offset so positions stay comparable to the original."""
    return _FENCED.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _dispatch_signal(prose: str, at: int) -> str | None:
    """Name the signal that makes the occurrence at `at` an instruction, or None for a mention."""
    start = 0
    for boundary in _BLOCK_BREAK.finditer(prose[:at]):
        start = boundary.end()
    prefix = prose[start:at]
    # Narrow the block to the sentence (or list item) the name actually sits in, so a verb three
    # sentences earlier cannot vouch for it. This is the half that fixes #491.
    cut = 0
    for end in _SENTENCE_END.finditer(prefix):
        cut = max(cut, end.end())
    for item in _LIST_ITEM.finditer(prefix):
        cut = max(cut, item.start())
    sentence = prefix[cut:]
    if _STEP_LEAD.match(sentence):
        return "subject-position"
    if _HANDOFF_PREFIX.search(sentence):
        return "handoff-arrow"
    if _DISPATCH_VERB.search(sentence):
        return "dispatch-verb"
    return None


def _dispatched_agents(body: str, agents: set[str]) -> dict[str, str]:
    """Map each agent this command DISPATCHES to the signal that says so."""
    prose = _blank_fences(body)
    dispatched: dict[str, str] = {}
    for name in sorted(agents):
        occurrence = re.compile(rf"`{re.escape(name)}`")
        for match in occurrence.finditer(prose):
            signal = _dispatch_signal(prose, match.start())
            if signal:
                dispatched[name] = signal
                break
        else:
            for match in occurrence.finditer(body):
                line_start = body.rfind("\n", 0, match.start()) + 1
                if _TASK_INVOCATION.search(body[line_start:].split("\n", 1)[0]):
                    dispatched[name] = "task-invocation"
                    break
    return dispatched


def check_undeclared_topology() -> tuple[list[Finding], dict[str, int]]:
    """A command dispatching 2+ of its plugin's agents must DECLARE its topology (#137).

    #137 asks for topology doctrine plus existing usages "labelled in-place". Building the check
    first is what showed why the labels have to be explicit: **prose does not correlate with
    topology**. `/rails-flow:review` is the flagship parallel fan-out — seven specialist passes, and
    the README says so — yet the word "parallel" appears nowhere in `review.md`. A keyword gate
    would have missed the one command that gets this right, and passed the ones that do not.

    Two more measurements pushed the same way. Counting dispatched agents alone over-fires:
    `/rails-flow:feature` names eight, sequentially, and a pipeline has nothing to reconcile.
    And searching for merge vocabulary under-fires: `/qa-flow:certify` declares a perfectly good
    precedence rule ("ANY S1/S2 open, or any layer failing its bar -> FAIL") in words no reasonable
    keyword list contains.

    So the command declares, and this checks the declaration:

        parallel  -> must also carry `merge:`  (how duplicate or conflicting outputs combine)
        loop      -> must also carry `exit:`   (the property that ends it)
        sequential/agent-to-agent -> the declaration alone

    Loop BREAKERS are deliberately not required here. `docs/harness-doctrine.md` section 8 records
    attempt caps and no-progress detection as a known gap owned by #128, and says plainly that
    writing them as doctrine before they exist would be the claims-vs-enforcement defect. An exit
    condition is a different thing: it is a property the command can state today.

    A MENTION IS NOT A DISPATCH (#491). Counting a backticked name was the first draft and it was
    wrong: a command explaining who consumes its output was charged with dispatching them. See
    `_dispatch_signal` above for what replaced it, and why that narrowing is set loose.
    """
    findings: list[Finding] = []
    examined = 0
    named_only = 0
    marker = re.compile(r"<!--\s*topology:\s*(sequential|parallel|loop|agent-to-agent)\b(.*?)-->",
                        re.S | re.I)
    root = ROOT / "plugins"
    if not root.is_dir():
        return findings, {"multi_agent_commands_checked_for_topology": 0,
                          "commands_naming_2plus_agents_without_dispatching": 0}
    for command in sorted(root.glob("*/commands/*.md")):
        # `command.parent.parent` rather than indexing into `.parts`: the index version was off by
        # one, resolved every plugin name to "plugins", found no agents directory, and examined ZERO
        # commands while reporting "no findings". The coverage counter is the only reason that was
        # visible -- a clean verdict over an empty scan is the failure mode this whole file exists
        # to catch, and it does not announce itself.
        agents = {path.stem for path in (command.parent.parent / "agents").glob("*.md")}
        body = read(command)
        named = {name for name in agents if re.search(rf"`{re.escape(name)}`", body)}
        dispatched = _dispatched_agents(body, named)
        if len(dispatched) < 2:
            # The second counter, and the reason #491's fix is not itself unfalsifiable: a command
            # that NAMES two agents and dispatches fewer is exactly what the narrowing lets
            # through, so the number it lets through is reported rather than left to be assumed.
            if len(named) >= 2:
                named_only += 1
            continue
        examined += 1
        found = marker.search(body)
        if not found:
            # The signal is named per agent, because #491's reporter had to read this function to
            # find out WHY the count was 2. A count with no evidence behind it is the thing that
            # makes a maintainer reword doctrine to appease the gate.
            evidence = ", ".join(f"{name} via {signal}" for name, signal in sorted(dispatched.items()))
            findings.append(Finding(
                "undeclared-topology", rel(command), 1,
                f"dispatches {len(dispatched)} agents ({evidence}) but declares no topology. Add "
                f"`<!-- topology: sequential|parallel|loop|agent-to-agent -->`; a parallel one also "
                f"needs `merge:`, a loop needs `exit:`. See docs/harness-doctrine.md",
            ))
            continue
        kind, detail = found.group(1).lower(), found.group(2)
        if kind == "parallel" and not re.search(r"\bmerge:", detail, re.I):
            findings.append(Finding(
                "undeclared-topology", rel(command), body[:found.start()].count("\n") + 1,
                "declares `topology: parallel` but no `merge:` rule. A fan-out without one leaves "
                "'both agents reported it' and 'the agents disagree' undefined at the point they "
                "matter most",
            ))
        if kind == "loop" and not re.search(r"\bexit:", detail, re.I):
            findings.append(Finding(
                "undeclared-topology", rel(command), body[:found.start()].count("\n") + 1,
                "declares `topology: loop` but no `exit:` condition. An exit is a property the "
                "command can state today; breakers are a separate known gap (#128)",
            ))
    return findings, {"multi_agent_commands_checked_for_topology": examined,
                      "commands_naming_2plus_agents_without_dispatching": named_only}


def check_unreachable_coercion_fallback() -> tuple[list[Finding], int]:
    """`X.to_sym … || X.to_i` -- the guard raises on exactly the input the fallback is for.

    Found by #352, in the `Ui::Logo` reference snippet users copy verbatim:

        @px = (SIZE[size.to_sym] || size.to_i).clamp(20, 200)

    The `|| size.to_i` says a number may arrive; `.clamp(20, 200)` says so again, and brand.md
    states a 20px digital minimum for the prism, which only means something if a px value can be
    passed. But `Integer#to_sym` does not exist, so `size: 48` raises `NoMethodError` before the
    fallback it was written for can run. **The expression contradicts itself on one line.**

    Measuring it found a second case the report missed: `Symbol#to_i` does not exist either, so
    `size: :xl` -- any key not in SIZE -- raised too. The fallback worked only for Strings, which
    is the one input nobody writes.

    This is the class `lint_markdown_code.py` structurally cannot catch: `ruby -c` accepts it,
    because it is valid syntax that raises at run time. So it needs a pattern rule, and the pattern
    is exact rather than heuristic -- two coercions on the same identifier where each is undefined
    on the type the other implies.
    """
    findings: list[Finding] = []
    examined = 0
    # Backreference `\1`: only the SAME identifier counts. `SIZE[k.to_sym] || other.to_i` is fine.
    pattern = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.to_sym\b[^\n]*\|\|[^\n]*\b\1\.to_(?:i|f)\b")
    for path in walk(".md"):
        slug = rel(path).replace("\\", "/")
        if not (slug.startswith("skills/") or slug.startswith("plugins/")):
            continue
        examined += 1
        for index, line in enumerate(read(path).splitlines(), 1):
            # Skip Ruby comments. The doctrine explaining this defect necessarily quotes the bad
            # expression -- the fix for #352 carries it in a comment two lines above the fix, and
            # the first draft of this rule flagged that comment as the only hit in the repo.
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                findings.append(Finding(
                    "unreachable-coercion-fallback", rel(path), index,
                    "`to_sym` guards a `to_i`/`to_f` fallback on the same value, so the fallback "
                    "is unreachable: `Integer#to_sym` and `Symbol#to_i` both raise NoMethodError. "
                    "Branch on the type first -- `x.is_a?(Integer) ? x : MAP[x.to_sym] || "
                    "x.to_s.to_i`. See #352",
                ))
    return findings, examined


def check_uninstallable_plugins() -> tuple[list[Finding], int]:
    """Every declared plugin needs an actual `/plugin install` line in the README.

    `check_undocumented_plugins` above proves a plugin is named SOMEWHERE, and its own docstring is
    explicit that this is not the same as being in the list that enumerates what ships -- locating a
    prose section needs judgement, which is how a mechanical rule turns noisy.

    An install COMMAND needs no such judgement. `/plugin install <name>@` is a fixed pattern, so
    "this plugin has no install line" is decidable without deciding where a section begins.

    It shipped: `design-flow` was in the manifest, named four times in the README, and **absent from
    the install block** -- so anyone following the README installed four of five plugins and never
    learned the fifth existed. The looser rule stayed green precisely because the name appeared in
    nearby prose, which is the boundary its docstring predicts.
    """
    manifest = ROOT / ".claude-plugin" / "marketplace.json"
    readme = ROOT / "README.md"
    if not manifest.is_file() or not readme.is_file():
        return [], 0
    try:
        payload = json.loads(read(manifest))
    except json.JSONDecodeError:
        return [], 0
    names = [p["name"] for p in payload.get("plugins", []) if isinstance(p, dict) and "name" in p]
    body = read(readme)
    findings = []
    for name in names:
        if not re.search(rf"/plugin\s+install\s+{re.escape(name)}@", body):
            findings.append(Finding(
                "uninstallable-plugin", rel(readme), 1,
                f"`{name}` is declared in marketplace.json but has no `/plugin install {name}@…` "
                "line in the README -- a reader following the install block never gets it"))
    return findings, len(names)


def check_plugin_root_in_ci() -> tuple[list[Finding], int]:
    """`$CLAUDE_PLUGIN_ROOT` must not appear inside a scaffolded YAML block.

    That variable is set only inside Claude Code's own plugin execution context. It does **not**
    exist in GitHub Actions, in a plain shell, or anywhere else -- so a CI job referencing it fails
    on every run with `can't open file '/scripts/…'`.

    We shipped exactly that: a `doctrine` job scaffolded into a user's `ci.yml` by `setup-flow`,
    in the release whose stated purpose was putting guarantees in the deterministic layer. Nothing
    caught it because our OWN workflows never reference the variable -- the workflow we test and the
    workflow we scaffold are different files, so a gate on one says nothing about the other. It
    surfaced when a maintainer ran the command by hand and got the error.

    Scope is a ```yaml fence, which is where our docs put CI and config scaffolding. Prose that
    names the variable is fine and common -- it IS how an agent resolves a plugin path at runtime,
    and the same file legitimately says "copy from ${CLAUDE_PLUGIN_ROOT}/scripts/x.py". Matching
    anywhere would fire on that correct sentence, which is how a rule gets deleted.
    """
    findings: list[Finding] = []
    examined = 0
    for path in walk(".md"):
        rel_path = rel(path).replace("\\", "/")
        if not rel_path.startswith(("plugins/", "skills/")):
            continue
        body = read(path)
        for match in re.finditer(r"(?m)^\s*```ya?ml\s*$(.*?)^\s*```\s*$", body, re.S):
            examined += 1
            block = match.group(1)
            for offset, line in enumerate(block.splitlines()):
                if "CLAUDE_PLUGIN_ROOT" in line and not line.lstrip().startswith("#"):
                    findings.append(Finding(
                        "plugin-root-in-ci", rel_path,
                        body[:match.start()].count("\n") + 2 + offset,
                        "`CLAUDE_PLUGIN_ROOT` inside a YAML block -- it is set only inside Claude "
                        "Code's plugin context, so this fails in CI with `can't open file`. Check "
                        "the toolchain out at a pinned tag, or vendor the script."))
    return findings, examined


def check_invisible_characters() -> tuple[list[Finding], int]:
    """No invisible or confusable whitespace in anything we ship."""
    findings: list[Finding] = []
    examined = 0
    for suffix in (".md", ".py", ".sh", ".json"):
        for path in walk(suffix):
            examined += 1
            body = read(path)
            for char, name in _INVISIBLE.items():
                index = body.find(char)
                if index == -1:
                    continue
                findings.append(Finding(
                    "invisible-character", rel(path), body[:index].count("\n") + 1,
                    f"contains {name} (U+{ord(char):04X}) -- it renders like ordinary whitespace, so "
                    "the text becomes unsearchable and anchored edits fail against a string copied "
                    f"from the file ({body.count(char)} occurrence(s) in this file)",
                ))
    return findings, examined


# A pointer to one of OUR files, in one of the two forms that are unambiguously ours:
#   `${CLAUDE_PLUGIN_ROOT}/reference/x.md`  -- resolved against the OWNING plugin's directory
#   `skills/rails-8/references/style.md`    -- resolved against the repo root
# Both must name a file (a real extension), so `skills/**` and a bare `skills/` stay out: a glob
# is not a pointer. A trailing `:28` line-anchor is stripped -- CLAUDE.md cites doctrine that way.
# ANY extension, not a named list. The first version allowlisted `md|py|sh|json` and therefore
# missed `${CLAUDE_PLUGIN_ROOT}/../templates/env.example` (#272) — a real broken pointer, in a file
# type nobody had thought to add. That is the same failure mode CLAUDE.md already records for
# packaging's binary detection: "never an extension allowlist, which fails open on the first type
# nobody added". A dot-extension still keeps globs and bare directories out, which is all the
# allowlist was ever doing.
_PLUGIN_ROOT_POINTER = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9._/-]*[A-Za-z0-9_-]\.[A-Za-z0-9]+)")
_SKILL_POINTER = re.compile(
    # The lookbehind rejects a path that is only a SUFFIX of a longer one -- `.claude/skills/…`
    # is the user's project directory, not ours, and `/` before `skills` is what tells them apart.
    # It must NOT exclude a backtick: almost every real pointer is written `skills/x/y.md`, and
    # excluding it made this rule silently skip its main case until the selftest caught it.
    r"(?<![\w./-])(skills/[A-Za-z0-9._-]+/[A-Za-z0-9._/-]*[A-Za-z0-9_-]\.[A-Za-z0-9]+)(?::\d+)?"
)


def check_doc_pointers() -> tuple[list[Finding], int]:
    """A documented path to one of our own files must resolve.

    Commands and skills tell an agent to READ a specific file of ours -- setup-flow points at
    `skills/rails-8/references/style.md` for style doctrine, and at its own
    `${CLAUDE_PLUGIN_ROOT}/reference/…` for rationale. Nothing made those true. Rename or move the
    target and the pointer still reads as authoritative while resolving to nothing, so a downstream
    agent is told to consult doctrine it cannot find -- claims-vs-enforcement, in the shipped
    surface. Skills and plugins are edited by different hands (and, here, by parallel sessions),
    which is exactly when a cross-component pointer rots.

    Scoped to the two unambiguous forms above so it cannot false-positive on the many paths in this
    corpus that belong to a USER's project (`docs/brain/STATUS.md`, `config/routes.rb`,
    `.claude/skills/…`) rather than to us.
    """
    findings: list[Finding] = []
    examined = 0
    for path in walk(".md"):
        body = read(path)
        parts = Path(rel(path)).parts
        # `${CLAUDE_PLUGIN_ROOT}` only has a referent INSIDE a plugin. Elsewhere (the CHANGELOG
        # describing a plugin's script, a skill quoting a command) it is prose about a variable,
        # not a path this linter can resolve -- and guessing an owner would invent findings.
        owning_plugin = ROOT / parts[0] / parts[1] if len(parts) >= 2 and parts[0] == "plugins" else None
        if owning_plugin is not None:
            for match in _PLUGIN_ROOT_POINTER.finditer(body):
                examined += 1
                if (owning_plugin / match.group(1)).exists():
                    continue
                findings.append(Finding(
                    "broken-doc-pointer", rel(path), body[:match.start()].count("\n") + 1,
                    f"points at `{match.group(0)}`, which does not exist in "
                    f"{owning_plugin.name} -- an agent told to read it finds nothing",
                ))
        for match in _SKILL_POINTER.finditer(body):
            examined += 1
            if (ROOT / match.group(1)).exists():
                continue
            findings.append(Finding(
                "broken-doc-pointer", rel(path), body[:match.start()].count("\n") + 1,
                f"points at `{match.group(1)}`, which does not exist -- a pointer to doctrine "
                "that cannot be opened reads as authoritative while resolving to nothing",
            ))
    return findings, examined


# ---------------------------------------------------------------------------
# Rule: ci-gate-without-test-step
# ---------------------------------------------------------------------------
# A fenced `CI.run` block is a `config/ci.rb` a user pastes into their project, and `bin/ci` is the
# thing our doctrine calls "the whole gate" and "full-gate confidence". So a shipped example with no
# test step ships a gate that cannot fail -- it runs setup, lint and audits and reports green having
# executed no specs.
#
# It is not hypothetical and the mechanism is not obvious (#391). Rails wraps every test step in
# `config/ci.rb.tt` in `<% unless options[:skip_test] -%>`, and this skill MANDATES `--skip-test`
# (project-setup.md ss1), so the generated file has no `Tests:` step to begin with. Doctrine that
# said "swap the test step" was therefore describing an edit to a line the mandated scaffold never
# writes, while four other places went on calling `bin/ci` the full gate.
#
# The rule cannot catch that wording -- prose is not mechanically checkable -- but it can pin the
# artifact, which is the half that matters: the corrected example can never be "simplified" back,
# and any future `CI.run` we ship has to answer the same question. Deliberately narrow: only blocks
# that actually open a `CI.run` count, so a snippet showing one `step` line in isolation (as
# api-documentation.md does for the OpenAPI drift gate) is not a whole-file example and stays silent.
_CI_RUN_FENCE = re.compile(r"^[ \t]*```[A-Za-z0-9+-]*[ \t]*$(.*?)^[ \t]*```[ \t]*$",
                           re.MULTILINE | re.DOTALL)
_CI_RUN_OPEN = re.compile(r"\bCI\.run\b|\bContinuousIntegration\.run\b")
# `rspec` covers `bundle exec rspec` and `parallel_rspec`; `rails test` covers a Minitest project.
_CI_SUITE_STEP = re.compile(r"^\s*step\b.*\b(?:rspec|rails\s+test)\b", re.MULTILINE)


def check_dangling_conditional_floor() -> tuple[list[Finding], int]:
    """If §2a offers a lower password floor conditional on MFA, the file must say how to get MFA.

    #531. §2a shipped a table dropping the floor from 15 to 8 *"where it is one factor of multi-factor"*
    -- a conditional discount whose condition the skill gave a reader **no way whatsoever to satisfy**.
    Not a false claim; a true one with nothing behind it, which is the same shape as a gate that cannot
    fail. The reader who wants the discount leaves our doctrine to get it, which is the re-invented-
    per-app failure the policy was written to stop.

    So: naming the multi-factor exception obliges the file to carry MFA guidance. The check is
    structural -- does the file discuss the second factor at all -- not a judgement about whether the
    guidance is good. It cannot tell adequate doctrine from a stub, and does not pretend to.
    """
    doc = ROOT / "skills" / "rails-8" / "references" / "auth-security.md"
    if not doc.is_file():
        return [], 0
    body = read(doc)
    offers = re.search(r"one factor of \*multi\*-factor|factor of multi-factor", body)
    if not offers:
        return [], 0
    # Evidence the file actually tells you how to satisfy the condition.
    teaches = re.search(r"\bTOTP\b|\bWebAuthn\b|\bpasskey\b|## 2b\.", body, re.I)
    if teaches:
        return [], 1
    return [Finding(
        "dangling-conditional-floor", rel(doc), 0,
        "the policy table offers a lower password floor for multi-factor auth, but the file carries no "
        "MFA guidance -- a conditional discount whose condition a reader cannot satisfy from this "
        "doctrine. Either add the guidance or drop the row.")], 1


def check_hook_script_count() -> tuple[list[Finding], int]:
    """CLAUDE.md's hook-script count must equal the hook scripts on disk.

    It said *"of the ten hook scripts, eight are advisory"* while eleven existed -- the eleventh being
    `design-flow`'s `design-tells.sh`. Two wrong numbers in one sentence, in the file that spends pages
    warning about claims nothing makes true, and in the paragraph explaining which hooks fail closed.

    That is the third time a doc number about our own files went stale, and the second time the missed
    component was design-flow (#203, #489). A count over files we already hold is a join, so it stops
    being remembered.

    The ADVISORY figure is derived, never read: total minus the gates CLAUDE.md itself names. A second
    hardcoded number would just be a second thing to go stale.
    """
    doc = ROOT / "CLAUDE.md"
    if not doc.is_file():
        return [], 0
    scripts = sorted(ROOT.glob("plugins/*/hooks/scripts/*.sh")) + \
              sorted(ROOT.glob(".claude/hooks/scripts/*.sh"))
    total = len(scripts)
    if not total:
        return [], 0
    WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen"}
    body = read(doc)
    m = re.search(r"Of the (\w+) hook scripts, (\w+) are advisory", body)
    if not m:
        return [Finding(
            "hook-count-drift", "CLAUDE.md", 0,
            "the hook-script sentence is gone or reworded, so nothing reconciles the count against "
            "the scripts on disk -- restore it or drop this rule deliberately")], total
    # The two fail-CLOSED gates CLAUDE.md names by path.
    gates = sum(1 for s in scripts if s.name in {"guard-bash.sh", "release-gate.sh"})
    findings = []
    if m.group(1) != WORDS.get(total, str(total)):
        findings.append(Finding(
            "hook-count-drift", "CLAUDE.md", 0,
            f"says {m.group(1)!r} hook scripts; there are {total}"))
    if m.group(2) != WORDS.get(total - gates, str(total - gates)):
        findings.append(Finding(
            "hook-count-drift", "CLAUDE.md", 0,
            f"says {m.group(2)!r} are advisory; {total} scripts minus {gates} named gates is "
            f"{total - gates}"))
    return findings, total


def check_duplicate_unreleased() -> tuple[list[Finding], int]:
    """At most one `### Unreleased` per `## component` section of the CHANGELOG.

    A manual error I made twice in three releases, both times the same way: two changes each insert
    their bullet using the same `## <section>\n\n` anchor, so the second opens its own `### Unreleased`
    heading above the first. Nothing broke either time -- the promotion pre-flight counts headings and
    would have caught it -- but it should not need catching by a human reading a number, and a repeated
    manual error that a join can detect is exactly what belongs in a gate rather than in a habit.

    Counts HEADING LINES, not the substring: this file's own prose mentions `### Unreleased` while
    describing the rule that forbids a stray one, and a substring count made an earlier arm fail on it.
    """
    doc = ROOT / "CHANGELOG.md"
    if not doc.is_file():
        return [], 0
    findings: list[Finding] = []
    section = None
    counts: dict[str, list[int]] = {}
    for line_no, line in enumerate(read(doc).splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.strip() == "### Unreleased" and section:
            counts.setdefault(section, []).append(line_no)
    for name, lines in counts.items():
        if len(lines) > 1:
            findings.append(Finding(
                "duplicate-unreleased", "CHANGELOG.md", lines[1],
                f"section {name!r} has {len(lines)} `### Unreleased` headings (lines "
                f"{', '.join(map(str, lines))}) -- two inserts used the same anchor, so the second "
                f"opened its own. Collapse them: one Unreleased per component, or the arm converts "
                f"one and leaves the other's notes out of the release."))
    return findings, len(counts)


def check_undeclared_skill_dependency() -> tuple[list[Finding], int]:
    """A command that reads a skill from ANOTHER plugin must check the skill is there.

    #513. All four `design-flow` agents and five of its commands read `skills/fidara-design`, which
    ships only inside the `rails-stack` bundle. No `plugin.json` carries a `requires` field -- checked,
    all four -- so nothing can declare the pairing, and `/plugin install design-flow@claude-skills`
    alone yields agents whose own text calls that doctrine "the law" about a file that is absent.

    The fix is the pattern this repo already uses in six commands for `gh`, Playwright and cloud
    credentials: name what is missing and stop. This rule holds the *commands* to it -- the entry
    points -- rather than every file, because an agent is only ever reached through one.

    NOT A PROSE MATCH ON THE PROSE. It looks for the skill reference and for a stop instruction in
    the same file, both of which are structural. It cannot tell a good message from a bad one and
    does not try.
    """
    findings: list[Finding] = []
    root = ROOT / "plugins"
    if not root.is_dir():
        return findings, 0
    # Which skills ship inside another plugin rather than beside the command that reads them.
    FOREIGN_SKILL = "skills/fidara-design"
    STOP = re.compile(r"and stop\b|must be readable", re.I)
    examined = 0
    for command in sorted(root.glob("*/commands/*.md")):
        body = read(command)
        if FOREIGN_SKILL not in body:
            continue
        examined += 1
        if STOP.search(body):
            continue
        findings.append(Finding(
            "undeclared-skill-dependency", rel(command), 1,
            f"reads {FOREIGN_SKILL!r}, which ships in another plugin, without a precondition that "
            f"names what is missing and stops. No `plugin.json` can declare this pairing, so the "
            f"check has to be in the command -- otherwise the doctrine is simply absent at runtime "
            f"and the agent improvises it."))
    return findings, examined


def check_password_floor() -> tuple[list[Finding], int]:
    """The password floor §2a STATES must equal the one its own worked example enforces.

    #484. The section cites NIST SP 800-63B's `SHALL` of 15 characters for a single-factor password
    and then ships a `validates :password, length: { minimum: N }` a reader copies verbatim. Two
    numbers about the same rule, in one file, is how a relaxed example outlives a table nobody
    re-read -- and this doctrine's *previous* state was exactly that failure: a commented
    `minimum: 12` hint with no stated floor at all.

    DELIBERATELY NOT A PROSE RULE. The obvious gate here would grep for composition rules
    ("at least one uppercase"), and it would fire on the sentence that FORBIDS them -- the same
    mention-versus-prescription false positive as #491. A number-to-number join has no such
    ambiguity, so that is what this checks and all it checks.
    """
    doc = ROOT / "skills" / "rails-8" / "references" / "auth-security.md"
    if not doc.is_file():
        return [], 0
    body = read(doc)
    stated = re.search(r"minimum \*\*(\d+)\*\* characters where the password is the \*only\* factor",
                       body)
    enforced = re.findall(r"validates :password, length: \{ minimum: (\d+) \}", body)
    if not stated:
        return [Finding(
            "password-floor-drift", rel(doc), 0,
            "no stated single-factor minimum found in the policy table -- the rule the worked "
            "example enforces has nothing to be reconciled against, so a relaxed example would "
            "pass unnoticed")], 0
    floor = int(stated.group(1))
    findings = [
        Finding("password-floor-drift", rel(doc), 0,
                f"the policy table states a {floor}-character single-factor floor, but a worked "
                f"example enforces `minimum: {n}`. A reader copies the example, so the example is "
                f"the doctrine -- make them agree.")
        for n in enforced if int(n) != floor
    ]
    return findings, len(enforced) + 1


def check_orphaned_controller() -> tuple[list[Finding], int]:
    """A scaffold prescribes a Stimulus controller whose paired component it never scaffolds.

    #483. `/design-flow:setup` listed the `toast` controller and omitted the component it drives,
    so the controller shipped as dead code in every scaffolded app -- and `crud-modal-pattern.md`
    emits every CRUD success with `turbo_stream.prepend("toasts", ToastComponent.new(...))`, so the
    feedback was dropped silently rather than merely un-styled. Writing the join found `dropdown`
    and `tabs` in the same state, which the report did not mention.

    THE PAIRING IS DISCOVERED, NOT LISTED. A controller `c` is paired iff
    `component-implementations.md` has a `## <Titlecase(c)>` implementation section. That is why
    `sidebar` and `theme` are silent without an exemption: neither has one, because neither drives
    a component. A hardcoded pair list would need editing every time a component is added, and the
    edit nobody makes is the bug this rule exists to catch.
    """
    findings: list[Finding] = []
    impls = ROOT / "skills" / "fidara-design" / "references" / "component-implementations.md"
    setup = ROOT / "plugins" / "design-flow" / "commands" / "setup.md"
    if not impls.is_file() or not setup.is_file():
        return findings, 0

    implemented = {m.lower() for m in re.findall(r"(?m)^##\s+([A-Z][A-Za-z]+)", read(impls))}
    body = read(setup)
    # The controller list is a slash-separated run of backticked names, e.g.
    # `modal`/`dropdown`/`tabs`/`sidebar`/`theme`/`toast`.
    prescribed: set[str] = set()
    for line in body.splitlines():
        if "controllers built on them" in line or "/`" in line:
            prescribed |= {n for n in re.findall(r"`([a-z][a-z-]*)`", line) if n in implemented}
    examined = len(prescribed)
    for name in sorted(prescribed):
        component = f"Ui::{name.capitalize()}"
        if re.search(rf"\b{re.escape(component)}\b", body):
            continue
        findings.append(Finding(
            "orphaned-controller", rel(setup), 1,
            f"scaffolds the {name!r} controller but never scaffolds {component}, which "
            f"component-implementations.md implements under `## {name.capitalize()}`. The "
            f"controller ships as dead code, and any doctrine that targets the component renders "
            f"nothing."))
    return findings, examined


def check_undeclared_component_label() -> tuple[list[Finding], int]:
    """Every shipped skill and plugin needs a `comp:` label in `.github/labels.yml`.

    #489. That file is the source of truth `/maintainer-setup-intake` provisions FROM, and it had
    drifted two labels behind the live tracker: `comp:fidara-design` and `comp:design-flow` existed
    on GitHub and sat on four open issues while being undeclared -- so a fresh clone would never
    create them, and `gh issue create --label comp:design-flow` fails outright. Auditing it for this
    rule found two MORE that were missing from both the file and GitHub (`code-review`,
    `quality-pass`), which is the difference between a grep and a join.

    Deliberately a pure FILE join -- `skills/*/` and `plugins/*/` against the yaml -- with no `gh`
    call. A gate that needs network and auth fails on a runner for reasons unrelated to the repo,
    and teaches people to ignore a red build.

    `rails-stack` is excluded: it is the bundle that ships the skills, and each skill already has
    its own label, so a `comp:rails-stack` would be a second name for the same problem. It was
    tried on a real issue in this tracker and rejected by `gh` for not existing.
    """
    findings: list[Finding] = []
    labels_file = ROOT / ".github" / "labels.yml"
    if not labels_file.is_file():
        return findings, 0
    declared = set(re.findall(r"comp:([a-z0-9-]+)", read(labels_file)))
    # Non-component labels that legitimately have no directory. Declared, so a typo in the yaml
    # cannot hide here -- an unknown extra is reported below.
    NON_DIRECTORY = {"packaging", "marketplace"}
    BUNDLE = {"rails-stack"}
    shipped = {d.name for d in (ROOT / "skills").glob("*") if d.is_dir()} | \
              {d.name for d in (ROOT / "plugins").glob("*") if d.is_dir()}
    shipped -= BUNDLE
    examined = len(shipped) + len(declared)
    for name in sorted(shipped - declared):
        findings.append(Finding(
            "undeclared-component-label", ".github/labels.yml", 0,
            f"no `comp:{name}` declared, but `{name}` is a shipped skill or plugin. "
            f"/maintainer-setup-intake provisions from this file, so on a fresh clone that label "
            f"is never created and `gh issue create --label comp:{name}` fails outright."))
    for name in sorted(declared - shipped - NON_DIRECTORY):
        findings.append(Finding(
            "undeclared-component-label", ".github/labels.yml", 0,
            f"declares `comp:{name}`, which is neither a directory under skills/ or plugins/ nor "
            f"one of the non-directory labels {sorted(NON_DIRECTORY)}. Either it is a typo or a "
            f"component was removed and its label outlived it."))
    return findings, examined


def _command_blocks(text: str, command: str) -> list[tuple[int, str]]:
    """[(line number where `command` starts, the whole shell command)].

    A shell command spans lines via trailing `\\`, and its flags are spread across them. Reading
    one line at a time is why the first version of `unprovisioned-label` would have mis-scoped an
    upstream call: `--repo` on line 1, `--label` on line 3.
    """
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if command in lines[index]:
            start = index
            parts = [lines[index]]
            while parts[-1].rstrip().endswith("\\") and index + 1 < len(lines):
                index += 1
                parts.append(lines[index])
            out.append((start + 1, "\n".join(parts)))
        index += 1
    return out


def check_unprovisioned_label() -> tuple[list[Finding], int]:
    """A plugin files an issue with `--label X` against the USER's repo, and no setup creates X.

    #487 and #490 were the same defect in two plugins: `gh issue create --label` **errors and
    creates nothing** when the label does not exist -- it does not degrade to an unlabelled issue.
    So the defect report, or the reviewer's out-of-scope finding, is silently LOST at exactly the
    moment the flow claims to capture it. Two instances found by hand; this is the join that finds
    the third.

    SCOPE, and it is the whole difficulty. A call carrying `--repo` targets the **upstream**
    tracker (claude-skills), whose taxonomy is provisioned by our own intake command and is not
    this plugin's business -- `claude-skills-reporter.md` correctly passes `<comp:*>`/`<type:*>`
    there. Only calls against the user's own repo are judged.

    PLACEHOLDERS ARE COUNTED, NOT JUDGED. `severity:sN` is a template, not a label; demanding a
    literal `sN` would be a false positive, and quietly dropping it would let a whole family go
    unchecked. They are reported in the coverage line instead, so a run cannot imply it resolved
    something it skipped.
    """
    findings: list[Finding] = []
    examined = 0
    root = ROOT / "plugins"
    if not root.is_dir():
        return findings, examined

    label_flag = re.compile(r"--label\s+[\"']([^\"']+)[\"']")
    placeholder = re.compile(r"[<>*]|\bs?N\b")

    for plugin in sorted(p for p in root.iterdir() if p.is_dir()):
        body_by_path = {path: read(path)
                        for path in sorted(plugin.rglob("*.md"))}
        created = set()
        for text in body_by_path.values():
            created |= set(re.findall(r"gh label create\s+([^\s\\]+)", text))
        for path, text in body_by_path.items():
            for line_no, block in _command_blocks(text, "gh issue create"):
                # `--repo` is judged over the WHOLE BLOCK, not the one line. The real call in
                # `claude-skills-reporter.md` puts `--repo <upstream>` on the first line and
                # `--label` on the third; a per-line test would read the label line as
                # user's-own-repo and flag a correctly-scoped upstream call.
                if "--repo" in block:
                    continue
                for raw in label_flag.findall(block):
                    for token in (tok.strip() for tok in raw.split(",")):
                        if not token:
                            continue
                        examined += 1
                        if placeholder.search(token):
                            continue
                        if token not in created:
                            findings.append(Finding(
                                "unprovisioned-label", rel(path), line_no,
                                f"files with --label {token!r} against the user's own repo, and no "
                                f"`gh label create {token}` exists anywhere in {plugin.name}. "
                                f"`gh issue create` ERRORS on an unknown label, so the issue is "
                                f"never created -- the report is lost, not mislabelled."))
    return findings, examined


def check_ci_gate_without_test_step() -> tuple[list[Finding], int]:
    """A shipped `CI.run` example must run a test suite (#391).

    See the block comment above for why this exists and why it is scoped the way it is.
    """
    findings: list[Finding] = []
    examined = 0
    for path in walk(".md"):
        relpath = rel(path).replace("\\", "/")
        if not (relpath.startswith("skills/") or relpath.startswith("plugins/")):
            continue          # shipped surface only; the CHANGELOG quotes old examples on purpose
        body = read(path)
        for match in _CI_RUN_FENCE.finditer(body):
            block = match.group(1)
            if not _CI_RUN_OPEN.search(block):
                continue
            examined += 1
            if _CI_SUITE_STEP.search(block):
                continue
            findings.append(Finding(
                "ci-gate-without-test-step", relpath, body[:match.start()].count("\n") + 1,
                "ships a `CI.run` example with no step that runs the suite. `bin/ci` is the gate "
                "this doctrine calls full-gate confidence, and Rails omits every `Tests:` step "
                "under the `--skip-test` scaffold we mandate -- so this example is a gate that "
                "reports green having run zero specs. Add `step \"Tests: RSpec\", "
                "\"bundle exec rspec\"` (testing.md ss11)",
            ))
    return findings, examined


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> tuple[list[Finding], dict[str, int]]:
    python_sources = {path: read(path) for path in walk(".py")}
    dead, dead_examined = check_dead_settings_keys(python_sources)
    unenforced, flag_examined = check_unenforced_mandatory_flags(python_sources)
    undocumented, plugins_examined = check_undocumented_plugins()
    unbounded, queries_examined = check_unbounded_issue_queries()
    components, components_examined = check_component_call_sites()
    call_sites, call_coverage = check_doctrine_call_sites()
    invisible, invisible_examined = check_invisible_characters()
    pointers, pointers_examined = check_doc_pointers()
    uninstallable, plugins_installable = check_uninstallable_plugins()
    plugin_root, yaml_blocks = check_plugin_root_in_ci()
    outlines, outlines_examined = check_v4_outline_none()
    coercions, coercions_examined = check_unreachable_coercion_fallback()
    topologies, topology_coverage = check_undeclared_topology()
    schema, schema_examined = check_findings_schema_drift()
    toggles, toggles_examined = check_unhonoured_config_toggle()
    unwired, unwired_examined = check_unwired_claim_verifier()
    ci_gates, ci_gates_examined = check_ci_gate_without_test_step()
    controllers, controllers_examined = check_controller_inventory()
    labels, labels_examined = check_unprovisioned_label()
    comp_labels, comp_labels_examined = check_undeclared_component_label()
    orphans, orphans_examined = check_orphaned_controller()
    pw_floor, pw_floor_examined = check_password_floor()
    skill_dep, skill_dep_examined = check_undeclared_skill_dependency()
    dup_unrel, dup_unrel_examined = check_duplicate_unreleased()
    hook_cnt, hook_cnt_examined = check_hook_script_count()
    dangling, dangling_examined = check_dangling_conditional_floor()
    coverage = {
        "python_modules": len(python_sources),
        "json_settings_files_examined": dead_examined,
        "documented_flag_claims_examined": flag_examined,
        "declared_plugins": plugins_examined,
        "gh_list_calls_examined": queries_examined,
        "documented_components": components_examined,
        "shipped_files_scanned_for_invisibles": invisible_examined,
        "doc_pointers_examined": pointers_examined,
        "plugins_checked_for_install_lines": plugins_installable,
        "yaml_blocks_scanned": yaml_blocks,
        "skill_docs_scanned_for_v4_outline": outlines_examined,
        "shipped_docs_scanned_for_coercion_fallbacks": coercions_examined,
        **topology_coverage,
        "findings_schema_fields_compared": schema_examined,
        "scaffolded_boolean_toggles": toggles_examined,
        "flows_checked_for_claim_verifier": unwired_examined,
        "shipped_ci_run_examples": ci_gates_examined,
        "stimulus_controllers_prescribed": controllers_examined,
        "issue_labels_resolved_or_templated": labels_examined,
        "component_labels_reconciled": comp_labels_examined,
        "scaffolded_controllers_paired": orphans_examined,
        "password_floor_claims_reconciled": pw_floor_examined,
        "commands_reading_a_foreign_skill": skill_dep_examined,
        "changelog_sections_with_unreleased": dup_unrel_examined,
        "hook_scripts_counted": hook_cnt_examined,
        "conditional_floor_claims": dangling_examined,
        **call_coverage,
    }
    return (dead + unenforced + undocumented + unbounded + components + call_sites + invisible
            + pointers + outlines + uninstallable + plugin_root + coercions + topologies + schema + unwired
            + ci_gates + controllers + labels + comp_labels + orphans + pw_floor + skill_dep + dup_unrel + hook_cnt + dangling,
            coverage)


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

    # -- dangling-conditional-floor (#531) --------------------------------
    DCF = "dangling-conditional-floor"
    AUTH = "skills/rails-8/references/auth-security.md"
    # Carries the SINGLE-factor floor line too, so these fixtures stay silent for
    # `password-floor-drift` — otherwise they trip that rule as well and steal its mutation.
    OFFER = ("| minimum **15** characters where the password is the *only* factor | SHALL |\n"
             "| minimum **8** where it is one factor of *multi*-factor | SHALL |\n")
    scenario("the multi-factor discount with no MFA guidance", rule=DCF, expect_finding=True,
             files={AUTH: OFFER})
    scenario("...with a 2b section is silent", rule=DCF, expect_finding=False,
             files={AUTH: OFFER + "\n## 2b. Multi-factor\nEnrol with TOTP.\n"})
    scenario("TOTP mentioned anywhere satisfies it", rule=DCF, expect_finding=False,
             files={AUTH: OFFER + "\nUse a TOTP authenticator.\n"})
    scenario("WebAuthn also satisfies it", rule=DCF, expect_finding=False,
             files={AUTH: OFFER + "\nRegister a WebAuthn passkey.\n"})
    # NO OFFER, NO OBLIGATION. A file that never promises the discount owes no MFA guidance —
    # otherwise the rule would demand MFA doctrine of every auth file in the repo.
    scenario("a file not offering the discount is silent", rule=DCF, expect_finding=False,
             files={AUTH: "| minimum **15** characters where the password is the *only* factor |\n"})
    scenario("no auth file is silent", rule=DCF, expect_finding=False, files={"README.md": "x\n"})

    # -- hook-count-drift -------------------------------------------------
    HC = "hook-count-drift"
    def _hooks(n, sentence):
        files = {"CLAUDE.md": sentence}
        for i in range(n):
            files[f"plugins/p{i}/hooks/scripts/h{i}.sh"] = "#!/bin/sh\n"
        return files
    # ONLY the total is wrong here — advisory is correct (3 scripts, 1 named gate = 2 advisory).
    # A fixture with BOTH numbers wrong cannot isolate the total check: the advisory check fires
    # too, so disabling the total comparison would still leave a finding and the mutation survives.
    only_total = _hooks(2, "Of the ten hook scripts, two are advisory.\n")
    only_total["plugins/pz/hooks/scripts/guard-bash.sh"] = "#!/bin/sh\n"
    scenario("a wrong total is reported", rule=HC, expect_finding=True, files=only_total)
    scenario("the right total and derived advisory count is silent", rule=HC, expect_finding=False,
             files=_hooks(3, "Of the three hook scripts, three are advisory.\n"))
    # The advisory figure is DERIVED (total minus the named gates), not a second free number.
    gated = _hooks(2, "Of the three hook scripts, two are advisory.\n")
    gated["plugins/pz/hooks/scripts/guard-bash.sh"] = "#!/bin/sh\n"
    scenario("advisory is total minus the named gates", rule=HC, expect_finding=False, files=gated)
    wrong = dict(gated); wrong["CLAUDE.md"] = "Of the three hook scripts, three are advisory.\n"
    scenario("a wrong advisory count is reported even when the total is right",
             rule=HC, expect_finding=True, files=wrong)
    # The sentence disappearing must FAIL LOUD, not silently stop checking.
    scenario("a reworded sentence is reported, not ignored", rule=HC, expect_finding=True,
             files=_hooks(3, "We ship some hooks.\n"))
    scenario("no hook scripts at all is silent", rule=HC, expect_finding=False,
             files={"CLAUDE.md": "Of the ten hook scripts, eight are advisory.\n"})

    # -- duplicate-unreleased ---------------------------------------------
    DUP = "duplicate-unreleased"
    scenario("two Unreleased headings in one section", rule=DUP, expect_finding=True,
             files={"CHANGELOG.md": "## qa-flow\n\n### Unreleased\n\n- a\n\n### Unreleased\n\n- b\n"})
    scenario("one per section is silent", rule=DUP, expect_finding=False,
             files={"CHANGELOG.md": "## qa-flow\n\n### Unreleased\n\n- a\n\n## design-flow\n\n"
                                    "### Unreleased\n\n- b\n"})
    scenario("no Unreleased at all is silent", rule=DUP, expect_finding=False,
             files={"CHANGELOG.md": "## qa-flow\n\n### 1.0.0\n\n- a\n"})
    # PROSE MENTIONING IT IS NOT A HEADING -- this file's own docs discuss `### Unreleased`, and an
    # earlier arm failed because a substring count caught the sentence describing the rule.
    scenario("prose mentioning the string is not counted", rule=DUP, expect_finding=False,
             files={"CHANGELOG.md": "## qa-flow\n\n### Unreleased\n\n- a stray `### Unreleased` "
                                    "heading means notes vanish\n"})
    scenario("no CHANGELOG is silent", rule=DUP, expect_finding=False, files={"README.md": "x\n"})

    # -- undeclared-skill-dependency (#513) -------------------------------
    USD_ = "undeclared-skill-dependency"
    READS = "See skills/fidara-design/SKILL.md for the catalog.\n"
    scenario("a command reading a foreign skill with no stop instruction", rule=USD_,
             expect_finding=True, files={"plugins/x/commands/a.md": READS})
    scenario("...with the stop instruction is silent", rule=USD_, expect_finding=False,
             files={"plugins/x/commands/a.md": READS + "If you cannot, name it and stop.\n"})
    scenario("the 'must be readable' phrasing also satisfies it", rule=USD_, expect_finding=False,
             files={"plugins/x/commands/a.md": READS + "The skill must be readable.\n"})
    # A command that never reads the skill is not asked for a precondition.
    scenario("a command not reading it is silent", rule=USD_, expect_finding=False,
             files={"plugins/x/commands/a.md": "nothing relevant here\n"})
    # AGENTS are deliberately out of scope -- an agent is only reached through a command.
    scenario("an agent reading it is not judged", rule=USD_, expect_finding=False,
             files={"plugins/x/agents/a.md": READS})
    scenario("no plugins dir is silent", rule=USD_, expect_finding=False,
             files={"README.md": "x\n"})

    # -- password-floor-drift (#484) --------------------------------------
    PF = "password-floor-drift"
    STATED = "| minimum **15** characters where the password is the *only* factor | SHALL |\n"
    DOCP = "skills/rails-8/references/auth-security.md"
    scenario("a worked example below the stated floor", rule=PF, expect_finding=True,
             files={DOCP: STATED + "validates :password, length: { minimum: 12 }\n"})
    scenario("the example matching the stated floor is silent", rule=PF, expect_finding=False,
             files={DOCP: STATED + "validates :password, length: { minimum: 15 }\n"})
    # ABOVE the floor is still drift: two numbers for one rule, and the reader copies the example.
    scenario("an example ABOVE the stated floor is also drift", rule=PF, expect_finding=True,
             files={DOCP: STATED + "validates :password, length: { minimum: 20 }\n"})
    # A stated floor with NO example is fine; an example with no stated floor is not, because then
    # nothing reconciles it and a relaxed example passes unnoticed.
    scenario("a stated floor with no example is silent", rule=PF, expect_finding=False,
             files={DOCP: STATED})
    scenario("an example with no stated floor is reported", rule=PF, expect_finding=True,
             files={DOCP: "validates :password, length: { minimum: 15 }\n"})
    scenario("no auth doc at all is silent", rule=PF, expect_finding=False,
             files={"README.md": "x\n"})
    # Several examples, one of them wrong -- the bad one must not hide behind the good ones.
    scenario("one wrong example among correct ones still fires", rule=PF, expect_finding=True,
             files={DOCP: STATED + "validates :password, length: { minimum: 15 }\n"
                                   "validates :password, length: { minimum: 8 }\n"})

    # -- orphaned-controller (#483) ---------------------------------------
    OC = "orphaned-controller"
    IMPL = "## Toast\ncode\n\n## Modal\ncode\n"
    def _setup(line: str) -> dict:
        return {"skills/fidara-design/references/component-implementations.md": IMPL,
                "plugins/design-flow/commands/setup.md": line}
    scenario("a controller whose component is not scaffolded", rule=OC, expect_finding=True,
             files=_setup("the `modal`/`toast` controllers built on them.\n`Ui::Modal`\n"))
    scenario("both components scaffolded is silent", rule=OC, expect_finding=False,
             files=_setup("the `modal`/`toast` controllers built on them.\n`Ui::Modal` `Ui::Toast`\n"))
    # A controller with NO implementation section is not paired -- `sidebar` and `theme` are real
    # cases, and exempting them by name would need editing whenever a component is added.
    scenario("an unpaired controller needs no component", rule=OC, expect_finding=False,
             files=_setup("the `theme`/`sidebar` controllers built on them.\n"))
    scenario("...even alongside a paired one that IS scaffolded", rule=OC, expect_finding=False,
             files=_setup("the `theme`/`modal` controllers built on them.\n`Ui::Modal`\n"))
    # Missing either file must not crash, and must not report a clean scan of nothing.
    scenario("no implementations file is silent", rule=OC, expect_finding=False,
             files={"plugins/design-flow/commands/setup.md": "the `toast` controllers\n"})
    scenario("no setup file is silent", rule=OC, expect_finding=False,
             files={"skills/fidara-design/references/component-implementations.md": IMPL})

    # -- undeclared-component-label (#489) --------------------------------
    UCL = "undeclared-component-label"
    YML = ('- name: "comp:alpha"\n  color: "1f6feb"\n  description: "x"\n'
           '- name: "comp:packaging"\n  color: "1f6feb"\n  description: "x"\n'
           '- name: "comp:marketplace"\n  color: "1f6feb"\n  description: "x"\n')
    scenario("a skill with no comp label", rule=UCL, expect_finding=True,
             files={".github/labels.yml": YML, "skills/alpha/SKILL.md": "x\n",
                    "skills/beta/SKILL.md": "x\n"})
    scenario("a plugin with no comp label", rule=UCL, expect_finding=True,
             files={".github/labels.yml": YML, "skills/alpha/SKILL.md": "x\n",
                    "plugins/gamma/commands/a.md": "x\n"})
    scenario("every shipped component declared is silent", rule=UCL, expect_finding=False,
             files={".github/labels.yml": YML, "skills/alpha/SKILL.md": "x\n"})
    # THE OTHER DIRECTION: a label whose component is gone, or whose name is a typo.
    scenario("a declared label with no directory is reported", rule=UCL, expect_finding=True,
             files={".github/labels.yml": YML + '- name: "comp:ghost"\n  color: "x"\n',
                    "skills/alpha/SKILL.md": "x\n"})
    # The non-directory labels are legitimately directory-less and must NOT be reported...
    scenario("packaging and marketplace are exempt", rule=UCL, expect_finding=False,
             files={".github/labels.yml": YML, "skills/alpha/SKILL.md": "x\n"})
    # ...and `rails-stack` is the bundle, not a component: each skill carries its own label.
    scenario("the rails-stack bundle needs no label of its own", rule=UCL, expect_finding=False,
             files={".github/labels.yml": YML, "skills/alpha/SKILL.md": "x\n",
                    "plugins/rails-stack/commands/a.md": "x\n"})
    # No labels.yml at all: report nothing rather than every component. A missing FILE is a
    # different problem from a missing entry, and conflating them would fire 11 findings at once.
    scenario("no labels.yml is silent", rule=UCL, expect_finding=False,
             files={"skills/alpha/SKILL.md": "x\n"})

    # -- unprovisioned-label (#487, #490) ---------------------------------
    UPL = "unprovisioned-label"
    FILE = 'gh issue create --title "x" --label "from-qa"\n'
    scenario("a label nothing creates", rule=UPL, expect_finding=True,
             files={"plugins/x/commands/a.md": FILE})
    scenario("the same label created in the same plugin", rule=UPL, expect_finding=False,
             files={"plugins/x/commands/a.md": FILE,
                    "plugins/x/commands/setup.md": "gh label create from-qa --color 0E8A16\n"})
    # A label created in ANOTHER plugin does not help: plugins install independently.
    scenario("created in a different plugin does not count", rule=UPL, expect_finding=True,
             files={"plugins/x/commands/a.md": FILE,
                    "plugins/y/commands/setup.md": "gh label create from-qa\n"})
    # SCOPE: an upstream call is somebody else's taxonomy. The `--repo` sits on the FIRST line and
    # the `--label` on the third -- a per-line test flagged this, which is why blocks are parsed.
    scenario("an upstream --repo call is out of scope", rule=UPL, expect_finding=False,
             files={"plugins/x/commands/a.md":
                    'gh issue create --repo <upstream> \\\n  --title "t" \\\n'
                    '  --label "type:bug"\n'})
    scenario("...and it is the BLOCK that exempts it, not the word appearing anywhere in the file",
             rule=UPL, expect_finding=True,
             files={"plugins/x/commands/a.md":
                    "Elsewhere we use --repo for upstream.\n\n" + FILE})
    # Placeholders are templates, not labels -- demanding a literal `sN` is a false positive.
    for token in ("severity:sN", "<comp:*>", "type:*"):
        scenario(f"placeholder {token!r} is not judged", rule=UPL, expect_finding=False,
                 files={"plugins/x/commands/a.md":
                        f'gh issue create --title "x" --label "{token}"\n'})
    # A comma list is split, and ONE bad token in it is enough.
    scenario("one bad token in a comma list still fires", rule=UPL, expect_finding=True,
             files={"plugins/x/commands/a.md": 'gh issue create --label "qa,from-qa"\n',
                    "plugins/x/commands/setup.md": "gh label create qa\n"})
    scenario("every token provisioned is silent", rule=UPL, expect_finding=False,
             files={"plugins/x/commands/a.md": 'gh issue create --label "qa,from-qa"\n',
                    "plugins/x/commands/setup.md":
                    "gh label create qa\ngh label create from-qa\n"})
    # No plugins dir at all must not crash or claim a clean scan.
    scenario("a tree with no plugins is silent", rule=UPL, expect_finding=False,
             files={"README.md": "nothing here\n"})

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

    # -- component-without-call-site / undeclared-component-call-site (#238) ----
    # Both directions, plus the nested-class exemption: a class reached only through a parent's slot
    # setter cannot have a standalone call site, so demanding one would demand the impossible.
    DECL = ("skills/x/references/impl.md",
            "```ruby\nmodule Ui\n  class ThingComponent < ViewComponent::Base\n"
            "    def initialize(a:)\n      @a = a\n    end\n  end\nend\n```\n")
    scenario("a documented component with no call site", rule="component-without-call-site",
             expect_finding=True, files={DECL[0]: DECL[1]})
    scenario("a documented component that IS demonstrated", rule="component-without-call-site",
             expect_finding=False,
             files={DECL[0]: DECL[1] + "```erb\n<%= render Ui::ThingComponent.new(a: 1) %>\n```\n"})
    # A nested class is slot-only, so its absence from the call list is correct, not a finding.
    scenario("a nested slot component needs no call site of its own",
             rule="component-without-call-site", expect_finding=False,
             files={DECL[0]: "```ruby\nmodule Ui\n  class OuterComponent < ViewComponent::Base\n"
                             "    renders_many :rows\n"
                             "    class RowComponent < ViewComponent::Base\n"
                             "      def initialize(label:)\n        @label = label\n      end\n"
                             "    end\n  end\nend\n```\n"
                             "```erb\n<%= render Ui::OuterComponent.new do |o| %>\n"
                             "  <% o.with_row(label: \"x\") %>\n<% end %>\n```\n"})
    scenario("a call site naming a component nothing declares",
             rule="undeclared-component-call-site", expect_finding=True,
             files={DECL[0]: DECL[1] + "```erb\n<%= render Ui::GhostComponent.new(a: 1) %>\n```\n"})
    scenario("a call site naming a NESTED component is not a ghost",
             rule="undeclared-component-call-site", expect_finding=False,
             files={DECL[0]: "```ruby\nmodule Ui\n  class OuterComponent < ViewComponent::Base\n"
                             "    class InnerComponent < ViewComponent::Base\n"
                             "      def initialize(x:)\n        @x = x\n      end\n"
                             "    end\n  end\nend\n```\n"
                             "```erb\n<%= render Ui::OuterComponent.new %>\n"
                             "<%= render Ui::InnerComponent.new(x: 1) %>\n```\n"})

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
    # Same shape for the agent-worktree prune: a full repo copy per background agent lives under
    # `.claude/worktrees/`, and scanning it means an agent's half-finished edit fails the
    # MAINTAINER's gate run over a file that is not in the maintainer's tree.
    scenario(
        "a claim inside .claude/worktrees/ is another agent's copy, not ours",
        rule="unenforced-mandatory-flag", expect_finding=False,
        files={".claude/worktrees/agent-x/README.md": CORPORA_CLAIM,
               ".claude/worktrees/agent-x/tool.py": OPTIONAL_FLAG},
    )
    # The prune is by EXACT name, so a directory of ours that merely starts the same way is still
    # scanned. Without this the prune could widen to anything containing "worktree" and go quiet.
    scenario(
        "near miss: a worktrees-notes/ of ours stays scanned",
        rule="unenforced-mandatory-flag", expect_finding=True,
        files={"worktrees-notes/README.md": CORPORA_CLAIM, "tool.py": OPTIONAL_FLAG},
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

    # ---- plugin-root-in-ci ---------------------------------------------------------
    # We shipped a `doctrine` job referencing $CLAUDE_PLUGIN_ROOT, which does not exist in CI. Our
    # own workflows never reference it, so no gate could have caught it -- the workflow we test and
    # the workflow we scaffold are different files.
    PR_ = "plugin-root-in-ci"
    scenario("a scaffolded CI job using the plugin root", rule=PR_, expect_finding=True,
             files={"plugins/x/commands/setup.md":
                    "Add this job:\n\n```yaml\n  doctrine:\n    steps:\n"
                    "      - run: python3 \"$CLAUDE_PLUGIN_ROOT/scripts/gates.py\"\n```\n"})
    scenario("a checked-out toolchain path is fine", rule=PR_, expect_finding=False,
             files={"plugins/x/commands/setup.md":
                    "```yaml\n  doctrine:\n    steps:\n"
                    "      - run: python3 .claude-toolchain/plugins/x/scripts/gates.py\n```\n"})
    # NEAR MISS, and the one that decides whether this rule survives: PROSE naming the variable is
    # correct and common -- it IS how an agent resolves a plugin path at runtime, and the same file
    # legitimately says "copy from ${CLAUDE_PLUGIN_ROOT}/scripts/x.py". Firing on that would get the
    # rule deleted within a day.
    scenario("prose naming the variable stays silent", rule=PR_, expect_finding=False,
             files={"plugins/x/commands/setup.md":
                    "Vendor it from `${CLAUDE_PLUGIN_ROOT}/scripts/x.py` into `.claude/scripts/`.\n"
                    "\n```yaml\n  job:\n    steps:\n      - run: python3 .claude/scripts/x.py\n```\n"})
    # A COMMENT inside the YAML is prose too -- the fixed job explains the trap in one.
    scenario("a YAML comment naming it stays silent", rule=PR_, expect_finding=False,
             files={"plugins/x/commands/setup.md":
                    "```yaml\n  job:\n    steps:\n"
                    "      # $CLAUDE_PLUGIN_ROOT does not exist in CI, so we check out instead\n"
                    "      - run: python3 .claude-toolchain/x.py\n```\n"})

    # ---- uninstallable-plugin ------------------------------------------------------
    # The defect that shipped: design-flow was in the manifest, named FOUR times in the README, and
    # absent from the install block. The looser `undocumented-plugin` rule stayed green because of
    # those prose mentions -- which is exactly the boundary its own docstring predicts.
    UP = "uninstallable-plugin"
    MANIFEST = '{"plugins": [{"name": "rails-flow"}, {"name": "design-flow"}]}'''
    scenario("a declared plugin with no install line", rule=UP, expect_finding=True,
             files={".claude-plugin/marketplace.json": MANIFEST,
                    "README.md": "Use design-flow for UI work.\n\n"
                                 "```\n/plugin install rails-flow@claude-skills\n```\n"})
    scenario("every declared plugin has one", rule=UP, expect_finding=False,
             files={".claude-plugin/marketplace.json": MANIFEST,
                    "README.md": "```\n/plugin install rails-flow@claude-skills\n"
                                 "/plugin install design-flow@claude-skills\n```\n"})
    # NEAR MISS: prose naming the plugin is NOT an install line. This is the whole point of the
    # rule -- if a mention satisfied it, it would be the looser rule again under a new name.
    scenario("prose mentioning the plugin does not satisfy it", rule=UP, expect_finding=True,
             files={".claude-plugin/marketplace.json": MANIFEST,
                    "README.md": "design-flow ships tokens. Install design-flow to use it.\n"
                                 "```\n/plugin install rails-flow@claude-skills\n```\n"})

    # ---- ci-gate-without-test-step (#391) -------------------------------------------
    # `bin/ci` is what the rails-8 skill calls "the whole gate". Rails omits every `Tests:` step
    # under the `--skip-test` scaffold that skill mandates, so a shipped `CI.run` example without
    # one is a gate that reports green having run no specs.
    CIG = "ci-gate-without-test-step"
    CI_STEPS = ('  step "Setup", "bin/setup --skip-server"\n'
                '  step "Style: Ruby", "bin/rubocop"\n')
    scenario("a CI.run example with no test step", rule=CIG, expect_finding=True,
             files={"skills/x/references/testing.md":
                    "```ruby\nCI.run do\n" + CI_STEPS + "end\n```\n"})
    # Also the only PLUGIN-side positive. The scope test is one `or`, so a mutation dropping just
    # the `plugins/` half would survive against skills-only fixtures -- a coverage gap in the rule's
    # own tests, which is the class this linter exists to catch.
    scenario("the same defect in a plugin, written with the full class name",
             rule=CIG, expect_finding=True,
             files={"plugins/x/commands/setup.md":
                    "```ruby\nActiveSupport::ContinuousIntegration.run do\n" + CI_STEPS + "end\n```\n"})
    scenario("a CI.run example that runs the suite is silent", rule=CIG, expect_finding=False,
             files={"skills/x/references/testing.md":
                    "```ruby\nCI.run do\n" + CI_STEPS +
                    '  step "Tests: RSpec", "bundle exec rspec"\nend\n```\n'})
    scenario("a Minitest project's suite counts too", rule=CIG, expect_finding=False,
             files={"skills/x/references/testing.md":
                    "```ruby\nCI.run do\n" + CI_STEPS +
                    '  step "Tests: Rails", "bin/rails test"\nend\n```\n'})
    # NEAR MISS, and the one that keeps the rule usable: a single `step` line quoted to show ONE
    # check (api-documentation.md does this for the OpenAPI drift gate) is not a whole-file example.
    # If it fired there, the fix would be to paste an entire ci.rb into a section about swagger.
    scenario("a lone step line without CI.run is not a whole file", rule=CIG, expect_finding=False,
             files={"skills/x/references/api-documentation.md":
                    '```ruby\nstep "API docs: fresh", "bin/rails rswag:specs:swaggerize"\n```\n'})
    # NEAR MISS: the doctrine EXPLAINING this defect has to name `CI.run` in prose. Fencing is what
    # separates an example a user pastes from a sentence about one.
    scenario("prose naming CI.run outside a fence stays silent", rule=CIG, expect_finding=False,
             files={"skills/x/references/testing.md":
                    "Under `--skip-test`, the `CI.run` block Rails generates has no test step.\n"})
    scenario("the CHANGELOG may quote a superseded example", rule=CIG, expect_finding=False,
             files={"CHANGELOG.md": "```ruby\nCI.run do\n" + CI_STEPS + "end\n```\n"})

    # ---- v4-outline-none (#305) ----------------------------------------------------
    # A rename that kept the old spelling alive with the opposite meaning: v3's `outline-none` was
    # the ACCESSIBLE utility (an invisible outline that survives forced-colors); v4 renamed it to
    # `outline-hidden` and gave the old name to one that really removes the outline. Nine recipes
    # shipped wrong because they were correct under v3 and untouched by the migration.
    ON = "v4-outline-none"
    scenario("a v4 recipe using outline-none", rule=ON, expect_finding=True,
             files={"skills/x/references/t.md":
                    'BASE = "focus-visible:outline-none focus-visible:ring-2"\n'})
    scenario("other variants are caught too, not just focus-visible", rule=ON, expect_finding=True,
             files={"skills/x/references/t.md": '<a class="focus:outline-none ring-2">x</a>\n'})
    # NEAR MISS, and the one that decides whether this rule survives: the doctrine EXPLAINING the
    # defect has to name the bad utility repeatedly. If prose fires, the rule is unusable in the very
    # file that documents it -- components.md mentions `outline-none` five times on purpose.
    scenario("prose naming the utility must stay silent", rule=ON, expect_finding=False,
             files={"skills/x/references/t.md":
                    "Never write `outline-none` in v4: it sets `outline-style: none`. Tailwind v3's\n"
                    "outline-none was renamed to `outline-hidden`, so outline-none now means the\n"
                    "opposite. Use outline-hidden instead.\n"})
    scenario("the correct utility must stay silent", rule=ON, expect_finding=False,
             files={"skills/x/references/t.md":
                    'BASE = "focus-visible:outline-hidden focus-visible:ring-2"\n'})
    # Scope: this is Tailwind-v4 doctrine WE ship. A plugin or script mentioning it is not a recipe.
    scenario("outside skills/ is out of scope", rule=ON, expect_finding=False,
             files={"plugins/x/commands/c.md": 'class="focus-visible:outline-none"\n'})

    # ---- unwired-claim-verifier ----------------------------------------------------
    # Reads real repo paths, so `scenario()`'s synthetic tree cannot drive it. Exercised directly.
    UCV = "unwired-claim-verifier"
    checks += 1
    if check_unwired_claim_verifier()[0]:
        failures.append(f"{UCV}: the shipped flows already fail this rule")
    _root = ROOT
    import tempfile as _t2
    # `expect` is a SUBSTRING of the required message, not a boolean. The boolean version was
    # vacuous and a mutation proved it: disabling the "never invokes" branch left the `elif` to fire
    # instead, so a finding still appeared and `bool(got)` could not tell the two branches apart.
    for label, agent_exists, release_body, expect in (
        ("a flow that never names claim-verifier", True, "Open the promotion PR.\n",
         "never invokes"),
        ("a flow naming it without extract_claims.py", True,
         "Hand the body to `claim-verifier`.\n", "without `extract_claims.py`"),
        ("a flow with both is silent", True,
         "Run extract_claims.py then hand it to `claim-verifier`.\n", None),
        # If the agent is not in the tree there is nothing to wire, and demanding a caller for a
        # non-existent agent would fail every clone that trims plugins.
        ("no agent shipped means nothing to wire", False, "Open the promotion PR.\n", None),
    ):
        checks += 1
        root = Path(_t2.mkdtemp(prefix="unwired-"))
        (root / ".claude/agents").mkdir(parents=True)
        (root / ".claude/commands").mkdir(parents=True)
        if agent_exists:
            (root / "plugins/rails-flow/agents").mkdir(parents=True)
            (root / "plugins/rails-flow/agents/claim-verifier.md").write_text("x\n", encoding="utf-8")
        (root / ".claude/agents/release-manager.md").write_text(release_body, encoding="utf-8")
        (root / ".claude/commands/maintainer-work.md").write_text(
            "Run extract_claims.py then `claim-verifier`.\n", encoding="utf-8")
        ROOT = root
        got, _ = check_unwired_claim_verifier()
        ROOT = _root
        messages = " ".join(f.message for f in got)
        if expect is None and got:
            failures.append(f"{UCV} / {label}: expected silence, got {messages[:80]}")
        if expect is not None and expect not in messages:
            failures.append(f"{UCV} / {label}: expected a finding saying {expect!r}, got {messages[:80]!r}")

    # ---- unhonoured-config-toggle --------------------------------------------------
    # This rule reads real repo paths, so `scenario()`'s synthetic tree cannot drive it. Exercised
    # directly. It matters more than usual that these fixtures are thorough: the live tree now has
    # ZERO boolean toggles (the one that existed was the dead one this rule was written for), so the
    # coverage counter honestly reports 0 examined and the rule is purely preventive. Fixtures are
    # the only thing standing between it and a rule that could never fire.
    UCT = "unhonoured-config-toggle"
    checks += 1
    if check_unhonoured_config_toggle()[0]:
        failures.append(f"{UCT}: the shipped tree already fails this rule")
    _r = ROOT
    import tempfile as _t3
    for label, yaml_line, script_body, expect in (
        ("a toggle no script reads", "  check_external: false\n", "x = 1\n", True),
        ("a toggle a script reads is silent", "  check_external: false\n",
         'cfg.get("check_external")\n', False),
        # A STRING key is often agent-applied -- `runtime.ignore` really is honoured by
        # functional-tester -- so widening past booleans would flag a real consumer.
        ("a non-boolean key is out of scope", "  ignore: [foo]\n", "x = 1\n", False),
        ("a key outside the yaml fence is not config", "", "x = 1\n", False),
    ):
        checks += 1
        root = Path(_t3.mkdtemp(prefix="toggle-"))
        (root / "plugins/qa/commands").mkdir(parents=True)
        (root / "plugins/qa/scripts").mkdir(parents=True)
        fence = f"```yaml\nlinks:\n{yaml_line}```\n" if yaml_line else "check_external: false\n"
        (root / "plugins/qa/commands/setup-qa.md").write_text(fence, encoding="utf-8")
        (root / "plugins/qa/scripts/a.py").write_text(script_body, encoding="utf-8")
        ROOT = root
        got, _ = check_unhonoured_config_toggle()
        ROOT = _r
        if bool(got) != expect:
            failures.append(f"{UCT} / {label}: expected {'a finding' if expect else 'silence'}")

    # ---- findings-schema-drift -----------------------------------------------------
    # This rule reads two REAL repo paths rather than a synthetic tree, so `scenario()` (which
    # rebuilds ROOT in a temp dir) cannot drive it. Exercised directly instead, in both directions.
    FS = "findings-schema-drift"
    real, _ = check_findings_schema_drift()
    checks += 1
    if real:
        failures.append(f"{FS}: the shipped schema and qa-reporter already disagree: {real}")
    _saved_root = ROOT
    import tempfile as _tf
    for label, doc_body, expect in (
        ("a documented field set that matches", None, False),
        ("qa-reporter missing an enforced field",
         "Fields: `id`, `pass`, `severity`, `category`, `file`, `signature`, `issue`, `line`.\n", True),
        ("qa-reporter documenting nothing at all", "No schema here.\n", True),
    ):
        checks += 1
        root = Path(_tf.mkdtemp(prefix="schemadrift-"))
        (root / "plugins/rails-flow/scripts").mkdir(parents=True)
        (root / "plugins/qa-flow/agents").mkdir(parents=True)
        (root / "plugins/rails-flow/scripts/findings.py").write_text(
            'REQUIRED = ("id", "signature")\nOPTIONAL = ("line", "caused_by")\n', encoding="utf-8")
        body = doc_body or "Fields: `id`, `signature`, `line`, `caused_by`.\n"
        (root / "plugins/qa-flow/agents/qa-reporter.md").write_text(body, encoding="utf-8")
        ROOT = root
        got, _ = check_findings_schema_drift()
        ROOT = _saved_root
        if bool(got) != expect:
            failures.append(f"{FS} / {label}: expected {'a finding' if expect else 'silence'}")
    # A renamed tuple must be a FINDING, never a silent pass. This is the `gate-that-cannot-fail`
    # shape: the comparison would simply stop happening and the run would still say "no findings".
    checks += 1
    root = Path(_tf.mkdtemp(prefix="schemadrift-"))
    (root / "plugins/rails-flow/scripts").mkdir(parents=True)
    (root / "plugins/qa-flow/agents").mkdir(parents=True)
    (root / "plugins/rails-flow/scripts/findings.py").write_text(
        'MANDATORY = ("id",)\nOPTIONAL = ("line",)\n', encoding="utf-8")
    (root / "plugins/qa-flow/agents/qa-reporter.md").write_text("`id` `line`\n", encoding="utf-8")
    ROOT = root
    renamed, _ = check_findings_schema_drift()
    ROOT = _saved_root
    if not renamed:
        failures.append(f"{FS}: a renamed field tuple must be a finding, not a silent pass")

    # ---- undeclared-topology ------------------------------------------------------
    UT = "undeclared-topology"
    TWO = {"plugins/x/agents/alpha.md": "a\n", "plugins/x/agents/beta.md": "b\n"}
    scenario("two agents dispatched with no declaration", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md": "---\nd: x\n---\nRun `alpha` then `beta`.\n"})
    scenario("parallel without a merge rule", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n<!-- topology: parallel -->\nRun `alpha` and `beta`.\n"})
    scenario("loop without an exit condition", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n<!-- topology: loop -->\nRun `alpha` and `beta`.\n"})
    # The SILENT half. Each of these is a shape that exists in the real tree, and a rule that
    # fired on any of them would be removed within a week.
    scenario("parallel WITH a merge rule", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n<!-- topology: parallel\n     merge: highest severity wins -->\n"
                    "Run `alpha` and `beta`.\n"})
    scenario("loop WITH an exit condition", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n<!-- topology: loop\n     exit: no new findings -->\n"
                    "Run `alpha` and `beta`.\n"})
    # A pipeline has nothing to reconcile -- this is `/rails-flow:feature`, eight agents deep.
    scenario("sequential needs no merge rule", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n<!-- topology: sequential -->\nRun `alpha` then `beta`.\n"})
    # ONE agent is not a fan-out. Requiring a declaration here would put a topology comment on
    # every command in the repo and make the marker meaningless.
    scenario("a single agent needs no declaration", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md": "---\nd: x\n---\nRun `alpha`.\n"})
    # A name that is not one of THIS plugin's agents must not count toward the two.
    scenario("prose naming a non-agent does not count", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\nRun `alpha`, then check `bundle` and `rubocop`.\n"})

    # ---- a MENTION is not a DISPATCH (#491) ---------------------------------------
    # The NEGATIVE direction, and the reason this narrowing is allowed to exist at all: without
    # a fixture that must stay SILENT, narrowing a rule is indistinguishable from switching it
    # off -- `carve-out-without-negative-test`, from our own code-review skill. The verb in the
    # first sentence is load-bearing: it proves the signal is scoped to the name's OWN sentence,
    # not to the paragraph around it, which is how #491's false positive was produced.
    scenario("two agents merely mentioned, not dispatched", rule=UT, expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\nRun `bin/setup` first. Every defect `alpha` files is triaged "
                    "before `beta` sees it.\nUse the tracker to follow up.\n"})
    # The CONTROL for it. Same two names, same file, in instruction position -- so the silence
    # above is about the SHAPE of the sentence and not about anything else in the fixture.
    scenario("the same two names in instruction position still fire", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\nRun `bin/setup` first. Dispatch `alpha`, then hand off to "
                    "`beta`.\nUse the tracker to follow up.\n"})
    # #491's own shape: a name inside a fenced block, explaining who files against the label.
    scenario("an agent named only inside a fenced block is not dispatched", rule=UT,
             expect_finding=False,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\nDispatch `alpha`.\n\n```bash\n# run this on every re-run\n"
                    "gh label create from-x --description \"filed by `beta`, not a human\"\n```\n"})
    # ...and the one fenced shape that IS a dispatch, however deep in a code block it sits.
    scenario("a Task invocation inside a fence is a dispatch", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\nThe plan is fixed.\n\n```text\nTask(subagent_type: `alpha`)\n"
                    "Task(subagent_type: `beta`)\n```\n"})
    # `**Views & frontend** -> `design-auditor`` -- /rails-flow:review's whole shape, and it
    # carries no verb at all.
    scenario("an arrow handoff is a dispatch", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n1. **Views** → `alpha` across the diff\n"
                    "2. **Security** → `beta` over the whole surface\n"})
    # ``qa-reporter` consolidates.` -- subject position, no imperative anywhere.
    scenario("an agent opening its own step is a dispatch", rule=UT, expect_finding=True,
             files={**TWO, "plugins/x/commands/c.md":
                    "---\nd: x\n---\n`alpha` opens the cycle.\n\n`beta` closes it.\n"})
    # The narrowing's own instrument. A silence fixture proves the rule does not FIRE on a
    # mention; only this proves the rule can still SEE it. Without a number that moves, a
    # narrowing that had gone completely blind would pass every fixture above.
    checks += 1
    _mention_root = Path(_tf.mkdtemp(prefix="topology-mention-"))
    for _rel, _content in {**TWO, "plugins/x/commands/c.md":
                           "---\nd: x\n---\nEvery defect `alpha` files is triaged before "
                           "`beta` sees it.\n"}.items():
        (_mention_root / _rel).parent.mkdir(parents=True, exist_ok=True)
        (_mention_root / _rel).write_text(_content, encoding="utf-8")
    ROOT = _mention_root
    _, _mention_coverage = check_undeclared_topology()
    ROOT = _saved_root
    if _mention_coverage["commands_naming_2plus_agents_without_dispatching"] != 1:
        failures.append(
            f"{UT}: a command naming two agents and dispatching neither must be COUNTED as "
            f"such, not merely unreported -- got {_mention_coverage}")

    # ---- unreachable-coercion-fallback --------------------------------------------
    UC = "unreachable-coercion-fallback"
    scenario("the #352 Logo expression verbatim", rule=UC, expect_finding=True,
             files={"skills/x/references/t.md":
                    "      @px = (SIZE[size.to_sym] || size.to_i).clamp(20, 200)\n"})
    scenario("to_f counts too -- same contradiction, different coercion", rule=UC, expect_finding=True,
             files={"skills/x/references/t.md":
                    "    @ratio = SCALE[ratio.to_sym] || ratio.to_f\n"})
    scenario("plugins/ is in scope as well as skills/", rule=UC, expect_finding=True,
             files={"plugins/x/commands/c.md": "  @px = MAP[size.to_sym] || size.to_i\n"})
    # The FIX must be silent, or the rule fails the file it was written for.
    scenario("the type-branching fix is silent", rule=UC, expect_finding=False,
             files={"skills/x/references/t.md":
                    "      @px = (size.is_a?(Integer) ? size : SIZE[size.to_sym] || "
                    "size.to_s.to_i).clamp(20, 200)\n"})
    # NEAR MISS, and the one that caught a real bug in this rule's first draft: the doctrine
    # explaining #352 has to quote the broken expression, and it sits two lines from the fix.
    scenario("a Ruby comment quoting the bad expression is silent", rule=UC, expect_finding=False,
             files={"skills/x/references/t.md":
                    "      # a bare `SIZE[size.to_sym] || size.to_i` raises on `size: 48`\n"})
    # NEAR MISS: different identifiers is the normal, correct shape -- look up by one, fall back
    # to another. Firing here would flag ordinary code and get the rule switched off.
    scenario("different identifiers are not a contradiction", rule=UC, expect_finding=False,
             files={"skills/x/references/t.md": "    @px = SIZE[key.to_sym] || fallback.to_i\n"})
    # NEAR MISS: `to_sym` alone is the overwhelmingly common case and is perfectly correct.
    scenario("to_sym with no numeric fallback is silent", rule=UC, expect_finding=False,
             files={"skills/x/references/t.md": "    @variant, @size = variant.to_sym, size.to_sym\n"})
    scenario("outside shipped docs is out of scope", rule=UC, expect_finding=False,
             files={"docs/x.md": "    @px = SIZE[size.to_sym] || size.to_i\n"})

    # ---- invisible-character -----------------------------------------------------
    IC = "invisible-character"
    scenario("a no-break space in shipped markdown", rule=IC, expect_finding=True,
             files={"skills/x/references/t.md": "| Carousel | `role=region`\u00a0**or**\u00a0`group` |\n"})
    scenario("a zero-width space in a python module", rule=IC, expect_finding=True,
             files={"scripts/x.py": "VALUE = 1  # trailing\u200b comment\n"})
    scenario("a BOM inside the body of a file", rule=IC, expect_finding=True,
             files={"skills/x/references/t.md": "# Title\n\ufeffbody\n"})
    # NEAR MISS: the characters we use ON PURPOSE must never fire, or the rule gets switched off on
    # its first run over real doctrine — em dash, en dash, ellipsis, arrows, check marks, box drawing.
    scenario("the punctuation our doctrine actually uses is fine", rule=IC, expect_finding=False,
             files={"skills/x/references/t.md":
                    # A THIN SPACE was in this fixture as "punctuation we use on purpose" and the
                    # rule fired. Checked: the corpus contains none, so the FIXTURE was wrong, not
                    # the rule -- a thin space breaks grep exactly like a no-break space does.
                    "A rule — really a guarantee – reads 15\u201320 …\n"
                    "no: \u2192 yes \u2713 \u2717 \u251c\u2500 tree\n"})

    # #95: `**attrs` forwards arbitrary keywords, so unknown-keyword checking is meaningless for
    # those components — the rule flagged a CORRECT `ButtonComponent.new(..., data: {...})`. Three
    # fixtures, because a carve-out without a negative test is how a rule quietly stops finding
    # anything: the splat must silence the keyword check, must NOT silence it for a component
    # without a splat, and must NOT silence slot checking.
    SPLAT = ("```ruby\n  class SplatComponent < ViewComponent::Base\n"
             "    renders_one :title\n"
             "    def initialize(variant: :primary, **attrs)\n      @variant = variant\n"
             "    end\n  end\n```\n")
    NO_SPLAT = ("```ruby\n  class StrictComponent < ViewComponent::Base\n"
                "    def initialize(variant: :primary)\n      @variant = variant\n"
                "    end\n  end\n```\n")
    scenario("a **attrs initializer accepts arbitrary keywords", rule=R, expect_finding=False,
             files={"skills/x/references/impl.md": SPLAT +
                    "```erb\n<%= render SplatComponent.new(variant: :primary, "
                    "data: { action: \"x#y\" }) %>\n```\n"})
    scenario("...but a component with NO splat still fires", rule=R, expect_finding=True,
             files={"skills/x/references/impl.md": NO_SPLAT +
                    "```erb\n<%= render StrictComponent.new(variant: :primary, "
                    "data: { action: \"x#y\" }) %>\n```\n"})
    scenario("...and a splat never excuses an undeclared SLOT", rule=R, expect_finding=True,
             files={"skills/x/references/impl.md": SPLAT +
                    "```erb\n<%= render SplatComponent.new(variant: :primary) do |c| %>\n"
                    "  <% c.with_nope do %>x<% end %>\n<% end %>\n```\n"})

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
    # NEAR MISS: prose stating the rule contains the call name and the banned arg names, but no
    # arguments. It is the doctrine, not a violation of it. (Found by this rule firing on the very
    # comment added to warn readers off `size:` — components.md, #95.)
    scenario("prose naming the banned args is not a call", rule=R, expect_finding=False,
             files={"skills/x/references/i.md":
                    "```erb\n<%# lucide_icon takes no size:/class: — `with-icon` sizes it %>\n"
                    "<span class=\"with-icon\"><%= lucide_icon(\"x\") %></span>\n```\n"})
    # ...but the carve-out must not swallow a call whose first argument is a VARIABLE, which is a
    # real invocation and still wrong. This is the pair that stops the guard becoming a hole.
    scenario("paren-less call on a variable still flagged", rule=R, expect_finding=True,
             files={"skills/x/references/i.md":
                    "```erb\n<%= lucide_icon icon_name, class: \"size-4\" %>\n```\n"})
    scenario("paren-less call with a symbol name still flagged", rule=R, expect_finding=True,
             files={"skills/x/references/i.md":
                    "```erb\n<%= lucide_icon :chevron_right, size: 16 %>\n```\n"})

    # A component whose initializer is not documented is a coverage gap (#168), which is
    # a different finding — this rule must not guess at an undocumented signature.
    scenario("undocumented component is skipped, not guessed at", rule=R, expect_finding=False,
             files={"skills/x/references/impl.md":
                    "```erb\n<%= render(Ui::MysteryComponent.new(whatever: 1)) %>\n```\n"})

    # -- broken-doc-pointer ------------------------------------------------
    P = "broken-doc-pointer"
    scenario("plugin points at a reference file it does not ship", rule=P, expect_finding=True,
             files={"plugins/rails-flow/commands/setup-flow.md":
                    "Read `${CLAUDE_PLUGIN_ROOT}/reference/agent-instruction-conventions.md`.\n"})
    scenario("...and is silent once that file exists", rule=P, expect_finding=False,
             files={"plugins/rails-flow/commands/setup-flow.md":
                    "Read `${CLAUDE_PLUGIN_ROOT}/reference/agent-instruction-conventions.md`.\n",
                    "plugins/rails-flow/reference/agent-instruction-conventions.md": "# rationale\n"})
    scenario("command points at a skill doc that was renamed away", rule=P, expect_finding=True,
             files={"plugins/rails-flow/commands/setup-flow.md":
                    "Before writing Ruby read `skills/rails-8/references/style.md`.\n"})
    scenario("...and is silent when the skill doc is there", rule=P, expect_finding=False,
             files={"plugins/rails-flow/commands/setup-flow.md":
                    "Before writing Ruby read `skills/rails-8/references/style.md`.\n",
                    "skills/rails-8/references/style.md": "# Style\n"})
    # A line anchor is how CLAUDE.md cites doctrine (`jobs-and-realtime.md:28`); the pointer is
    # still the file, so the anchor must not defeat resolution.
    scenario("a `:line` anchor does not break resolution", rule=P, expect_finding=False,
             files={"CLAUDE.md": "see `skills/rails-8/references/jobs-and-realtime.md:28`\n",
                    "skills/rails-8/references/jobs-and-realtime.md": "# jobs\n"})
    # NEAR MISS: the exact false positive this rule had before it shipped. `${CLAUDE_PLUGIN_ROOT}`
    # in a CHANGELOG or a skill is prose ABOUT a plugin variable and has no plugin to resolve
    # against; guessing an owner would invent a finding on correct text.
    # #272: the first version allowlisted md|py|sh|json and so missed a real broken pointer at
    # `templates/env.example`. ANY extension now counts. Both directions, because the whole risk of
    # widening a pattern is that it starts firing on prose.
    scenario("a non-allowlisted extension is still a pointer", rule=P, expect_finding=True,
             files={"plugins/pipeline/commands/setup-cloud.md":
                    "base it on `${CLAUDE_PLUGIN_ROOT}/templates/env.example`\n"})
    scenario("...and is silent when that file exists", rule=P, expect_finding=False,
             files={"plugins/pipeline/commands/setup-cloud.md":
                    "base it on `${CLAUDE_PLUGIN_ROOT}/templates/env.example`\n",
                    "plugins/pipeline/templates/env.example": "RAILS_ENV=production\n"})
    scenario("the spurious /.. that walked out of the plugin (#272)", rule=P, expect_finding=True,
             files={"plugins/pipeline/commands/setup-cloud.md":
                    "base it on `${CLAUDE_PLUGIN_ROOT}/../templates/env.example`\n",
                    "plugins/pipeline/templates/env.example": "RAILS_ENV=production\n"})

    scenario("plugin-root prose outside a plugin is not resolvable", rule=P, expect_finding=False,
             files={"CHANGELOG.md": "the hook runs `${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py`\n"})
    # NEAR MISS: a glob is not a pointer. Flagging `skills/**` would fire on this repo's own
    # doctrine (CLAUDE.md says "after any `skills/**` edit") — the route to being switched off.
    scenario("a glob is not a pointer", rule=P, expect_finding=False,
             files={"CLAUDE.md": "after any `skills/**` edit, repackage; see `skills/` for sources\n"})
    # NEAR MISS: `.claude/skills/` is the USER's project directory, not ours. The prefix is what
    # distinguishes them, so a rule keyed on a bare `skills/` substring would flag a correct path.
    scenario("a user-project skills path is not ours", rule=P, expect_finding=False,
             files={"plugins/rails-flow/commands/curate.md":
                    "distils docs into `.claude/skills/domain/SKILL.md` in the user's repo\n"})

    # -- controller-inventory-gap (#95) ---------------------------------------
    CI = "controller-inventory-gap"
    REFS = "skills/fidara-design/references"

    def _inventory(*names: str) -> str:
        # The helper's own fenced example prescribes `dropdown`, and the rule reads every
        # reference doc including this one — so the helper lists it, rather than each scenario
        # having to remember a controller it is not about.
        listed = ", ".join(f"`{n}`" for n in ("dropdown", *names))
        return (
            "# Interaction\n\n## Per-component behavior contract\n\nprose\n\n"
            "## Controller conventions (mirror the markup ergonomics)\n\n"
            "```erb\n<div data-controller=\"dropdown\">…</div>\n```\n\n"
            f"Reuse the proven controllers already in the apps: {listed}.\n\n"
            "## Real-time & data (standardize)\n\nprose\n"
        )

    scenario("markup names a controller the inventory omits", rule=CI, expect_finding=True,
             files={f"{REFS}/interaction-stimulus.md": _inventory("modal", "dropdown"),
                    f"{REFS}/forms.md": '<div data-controller="dropzone">…</div>\n'})
    scenario("...and is silent once the inventory names it", rule=CI, expect_finding=False,
             files={f"{REFS}/interaction-stimulus.md": _inventory("modal", "dropdown", "dropzone"),
                    f"{REFS}/forms.md": '<div data-controller="dropzone">…</div>\n'})
    # The fence bug this rule found in itself: a ``` fence is three backticks, so a
    # newline-tolerant span pattern pairs off by one and the inventory comes back full of prose and
    # empty of names. Every fixture's inventory sits AFTER a fenced block for that reason.
    scenario("a fenced block before the list does not blind the reader", rule=CI,
             expect_finding=False,
             files={f"{REFS}/interaction-stimulus.md": _inventory("modal", "dropdown", "toast"),
                    f"{REFS}/component-implementations.md":
                        '<div data-controller="toast" data-toast-timeout-value="5000">…</div>\n'})
    # ...and the other half: a name inside a fenced EXAMPLE is a well-formed code span, so without
    # stripping fences it would count as "the inventory names it" and silence a real finding. The
    # inventory prose here lists only `dropdown`; `dropzone` appears solely inside the example.
    scenario("a name mentioned inside an example does not count as listed", rule=CI,
             expect_finding=True,
             files={f"{REFS}/interaction-stimulus.md":
                        "# Interaction\n\n## Controller conventions (mirror the markup ergonomics)\n\n"
                        "```ruby\n# the `dropzone` controller is discussed here, not declared\n```\n\n"
                        "Reuse the proven controllers already in the apps: `dropdown`.\n\n"
                        "## Real-time & data (standardize)\n\nprose\n",
                    f"{REFS}/forms.md": '<div data-controller="dropzone">…</div>\n'})
    # ERB, both directions in one fixture. `native-bridge` is a string literal and IS a
    # controller; `if` and `native_app?` are Ruby and are not. Tokenising the raw attribute
    # accepts `if`; deleting the ERB loses `native-bridge`. Only `if` is left out of the
    # inventory, so silence here proves the extractor did not invent it.
    scenario("ERB contributes its string literals and not its keywords", rule=CI,
             expect_finding=False,
             files={f"{REFS}/interaction-stimulus.md": _inventory("theme", "native-bridge"),
                    f"{REFS}/mobile-reference-implementation.md":
                        "<body data-controller=\"theme <%= 'native-bridge' if native_app? %>\">\n"})
    scenario("...and the ERB literal is still required to be listed", rule=CI, expect_finding=True,
             files={f"{REFS}/interaction-stimulus.md": _inventory("theme"),
                    f"{REFS}/mobile-reference-implementation.md":
                        "<body data-controller=\"theme <%= 'native-bridge' if native_app? %>\">\n"})
    # A renamed heading must fail LOUD. Silence there would leave the coverage number healthy
    # while the rule checked nothing — `skip` is not `pass`.
    scenario("a renamed inventory heading fails loud", rule=CI, expect_finding=True,
             files={f"{REFS}/interaction-stimulus.md":
                        "# Interaction\n\n## Controllers we use\n\n`modal`\n",
                    f"{REFS}/forms.md": '<div data-controller="modal">…</div>\n'})
    # NEAR MISS: the rule is one-directional on purpose. An inventory entry with no markup is
    # ordinary — `search`, `multistep` and `countdown` live in the apps and appear in no snippet
    # — and firing on them is how a linter earns its way to being switched off.
    scenario("an inventory entry with no markup is not a finding", rule=CI, expect_finding=False,
             files={f"{REFS}/interaction-stimulus.md":
                        _inventory("modal", "search", "multistep", "countdown"),
                    f"{REFS}/forms.md": '<div data-controller="modal">…</div>\n'})

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
        "documented_components": "documented component(s)",
        "doc_pointers_examined": "doc pointer(s) to our own files",
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
