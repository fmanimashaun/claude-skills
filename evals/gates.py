#!/usr/bin/env python3
"""Deterministic gates for the doctrine-effect benchmark (issue #156).

WHY THIS FILE IS PYTHON AND NOT PROSE
-------------------------------------
The whole point of #156 is that this repo verifies doctrine *content* against
sources but has never verified doctrine *effect*. A benchmark whose gates are
judged rather than computed would put the measurement back into the one layer
we refuse to trust. So every gate here is grep/parse: same input, same verdict,
forever, on anyone's machine.

THE RULE FOR RULES
------------------
Every rule is NAMED, and every rule cites the doctrine file+line it enforces.
A rule with no doctrine behind it is taste, and taste belongs in a discussion,
not in a gate. Two consequences that are easy to get wrong:

  1. A gate must PASS against the doctrine's own reference examples. If a rule
     fails what `references/*.md` shows as correct, the RULE is wrong -- not the
     doctrine. Authoring #156 caught exactly this twice (see JOB_IDEMPOTENT and
     NO_LITERAL_COLOR below), and both would have made the real-skill arm look
     WORSE than baseline. A wrong gate manufactures a false regression.
  2. A gate must be fair. Some doctrine is conditional ("use simple_form for
     dozens of uniform CRUD forms"), so the scaffold has to establish the
     project convention before the gate can hold the agent to it.

Stdlib only. No third-party imports, ever -- this repo has no requirements.txt
and the benchmark must not be the thing that introduces one.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Non-ASCII lands in output (check marks, arrows). Windows consoles default to
# cp1252 and raise UnicodeEncodeError mid-run; this bit us before in
# architecture_graph.py and lint_markdown_shell.py. Fix it once, here.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - exotic stream
        pass


# --------------------------------------------------------------------------
# Finding / Rule primitives
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One reason a gate failed. `line` is 1-indexed, or 0 for whole-file."""

    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.rule}] {where} -- {self.message}"


@dataclass(frozen=True)
class Rule:
    name: str
    doctrine: str  # file:line in skills/ that this enforces. Never blank.
    summary: str
    check: object = field(repr=False)  # Callable[[Path], list[Finding]]


# --------------------------------------------------------------------------
# File helpers
# --------------------------------------------------------------------------

# ERB and Ruby comments are not code. A hex value inside `<%# ... %>`, or after a
# `#` in a Ruby file, is discussion -- not a literal colour in rendered output.
_ERB_COMMENT = re.compile(r"<%#.*?%>", re.S)


def _blank(match: re.Match[str]) -> str:
    """Replace a span with spaces, preserving newlines so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _blank_ruby_comments(line: str) -> str:
    """Blank a trailing Ruby `#` comment, ignoring `#` inside string literals.

    Deliberately hand-rolled rather than regex: the thing we are looking for in
    these files IS a `#` token (`#0077CC`), so a naive `line.split("#")[0]` would
    delete the very violations `no-literal-color` exists to catch. Only a `#`
    *outside* a string starts a comment, which means tracking quote state.

    Ruby interpolation (`"#{x}"`) needs no special case: the `#` is inside a
    double-quoted string, so quote state already suppresses it.
    """
    in_single = in_double = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and (in_single or in_double):
            index += 2  # escaped character, whatever it is
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index] + " " * (len(line) - index)
        index += 1
    return line


def iter_files(workspace: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Files under `workspace` matching any glob, sorted for stable output.

    A nonexistent workspace raises. Returning "0 files, all gates pass" for a
    typo'd path is the single most dangerous failure mode a gate library can
    have -- it reports success for work that was never examined.
    """
    if not workspace.is_dir():
        raise NotADirectoryError(f"workspace is not a directory: {workspace}")
    out: set[Path] = set()
    for pattern in patterns:
        out.update(p for p in workspace.glob(pattern) if p.is_file())
    return sorted(out)


def read_lines(path: Path, *, strip_comments: bool = True) -> list[str]:
    """Read a file as UTF-8 lines with comments blanked out.

    Comments are blanked rather than removed so reported line numbers stay
    truthful.

    Ruby `#` comments are stripped for `.rb` files ONLY, never for `.erb`. In an
    ERB template a bare `#` is ordinary HTML text -- `<p>Invoice #42</p>`,
    `href="#"` -- and treating it as a comment would blank the rest of the line
    and hide real violations after it. False negatives are worse than the
    (already handled) `<%# ... %>` case: a gate that misses violations reports
    every arm as passing.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if not strip_comments:
        return text.splitlines()
    text = _ERB_COMMENT.sub(_blank, text)
    lines = text.splitlines()
    if path.suffix == ".rb":
        lines = [_blank_ruby_comments(line) for line in lines]
    return lines


def rel(path: Path, workspace: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:  # pragma: no cover - path outside workspace
        return path.as_posix()


VIEW_GLOBS = (
    "app/views/**/*.erb",
    "app/components/**/*.erb",
    "app/components/**/*.rb",
    "app/helpers/**/*.rb",
)
CONTROLLER_GLOBS = ("app/controllers/**/*.rb",)
JOB_GLOBS = ("app/jobs/**/*.rb",)
CONCERN_GLOBS = ("app/models/concerns/**/*.rb",)


# --------------------------------------------------------------------------
# Rule: scoped-index
# --------------------------------------------------------------------------

# Doctrine: skills/rails-8/references/auth-security.md:121-122
#   "# scoping IS authorization for ownership:
#    def set_project = @project = Current.user.projects.find(params[:id])  # 404s strangers"
#
# An index action that reaches for the global collection is not merely untidy;
# it is an authorization hole. Scoping through Current is what makes a stranger
# get a 404 instead of someone else's data.

_UNSCOPED_COLLECTION = re.compile(
    r"\b([A-Z][A-Za-z0-9_]*)\s*\.\s*(?:all\b|where\s*\(|order\s*\(|limit\s*\()"
)
# `Current.user.projects` / `Current.account.invoices` -- the scoped form.
_CURRENT_SCOPE = re.compile(r"\bCurrent\s*\.\s*[a-z_][A-Za-z0-9_]*")
# Constants that are not Active Record models and so are not scope violations.
_NOT_A_MODEL = frozenset({"Current", "Rails", "Time", "Date", "DateTime", "ActiveRecord",
                          "JSON", "Hash", "Array", "String", "Integer", "Float", "Kernel",
                          "File", "Dir", "Struct", "Set", "Math", "Process", "URI"})


def check_scoped_index(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    files = iter_files(workspace, CONTROLLER_GLOBS)
    if not files:
        return [Finding("scoped-index", "app/controllers", 0,
                        "no controller was written, so the task was not attempted")]

    for path in files:
        lines = read_lines(path)
        body = "\n".join(lines)
        where = rel(path, workspace)

        for i, line in enumerate(lines, start=1):
            code = line.split("#", 1)[0]
            for match in _UNSCOPED_COLLECTION.finditer(code):
                const = match.group(1)
                if const in _NOT_A_MODEL:
                    continue
                # Scoped through Current on the same line is the correct form.
                if _CURRENT_SCOPE.search(code):
                    continue
                findings.append(Finding(
                    "scoped-index", where, i,
                    f"`{match.group(0).strip()}` reaches the global collection; "
                    f"scope through `Current.<owner>.{const.lower()}s` instead",
                ))

        if not _CURRENT_SCOPE.search(body):
            findings.append(Finding(
                "scoped-index", where, 0,
                "no `Current.` scope anywhere in the controller -- scoping IS "
                "authorization (auth-security.md:121)",
            ))
    return findings


# --------------------------------------------------------------------------
# Rule: simple-form-convention
# --------------------------------------------------------------------------

# Doctrine: skills/fidara-design/references/forms.md:3 ("Use `simple_form`")
#           skills/rails-8/references/ecosystem-gems.md:29
#             "| Forms | `form_with` + partials | Dozens of uniform CRUD forms
#              -> **simple_form** |"
#
# NOTE the conditional. Plain `form_with` is the Rails default and is CORRECT in
# a project that has not adopted simple_form. This rule is therefore only fair
# when the scaffold has already established the convention (Gemfile entry plus
# config/initializers/simple_form.rb). scaffold.py does exactly that; without it
# this gate would punish an agent for following stock Rails.

_FORM_WITH = re.compile(r"\bform_with\b")
_SIMPLE_FORM_FOR = re.compile(r"\bsimple_form_for\b")


def check_simple_form_convention(workspace: Path) -> list[Finding]:
    # Fairness precondition: refuse to judge if the convention was never set up.
    gemfile = workspace / "Gemfile"
    initializer = workspace / "config" / "initializers" / "simple_form.rb"
    convention_established = (
        gemfile.is_file()
        and "simple_form" in gemfile.read_text(encoding="utf-8", errors="replace")
    ) or initializer.is_file()
    if not convention_established:
        return [Finding(
            "simple-form-convention", "Gemfile", 0,
            "scaffold did not establish simple_form as the project convention, so "
            "this gate cannot fairly run (form_with is correct stock Rails)",
        )]

    findings: list[Finding] = []
    files = [p for p in iter_files(workspace, VIEW_GLOBS) if p.suffix == ".erb"]
    if not files:
        return [Finding("simple-form-convention", "app/views", 0,
                        "no view template was written, so the task was not attempted")]

    saw_simple_form = False
    for path in files:
        where = rel(path, workspace)
        for i, line in enumerate(read_lines(path), start=1):
            if _SIMPLE_FORM_FOR.search(line):
                saw_simple_form = True
            if _FORM_WITH.search(line):
                findings.append(Finding(
                    "simple-form-convention", where, i,
                    "raw `form_with` in a project that mandates simple_form "
                    "(forms.md:3); use `simple_form_for`",
                ))
    if not saw_simple_form:
        findings.append(Finding(
            "simple-form-convention", "app/views", 0,
            "no `simple_form_for` anywhere -- the project convention was not followed",
        ))
    return findings


# --------------------------------------------------------------------------
# Rule: no-inline-dark
# --------------------------------------------------------------------------

# Doctrine: skills/fidara-design/references/foundations-tokens.md:205
#   "fidara's role layer needs **zero**: `--primary` is re-pointed once under
#    `.dark` and every component follows."
#           foundations-tokens.md:247
#   "`dark:` class sprawl -> **roles re-point under `.dark`**, component classes
#    stay put."
#
# Scope matters: `dark:` is legitimate in the TOKEN layer (a stylesheet that
# re-points roles under .dark). It is the *inline, per-component* usage that
# doctrine drives to zero. So this rule reads components/views only and never
# looks at app/assets/stylesheets.

_DARK_UTILITY = re.compile(r"(?<![\w:-])dark:[a-z0-9[\]/.\-]+", re.I)


def check_no_inline_dark(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(workspace, VIEW_GLOBS):
        where = rel(path, workspace)
        for i, line in enumerate(read_lines(path), start=1):
            for match in _DARK_UTILITY.finditer(line):
                findings.append(Finding(
                    "no-inline-dark", where, i,
                    f"inline `{match.group(0)}` -- roles re-point under `.dark`; "
                    f"component classes stay put (foundations-tokens.md:247)",
                ))
    return findings


# --------------------------------------------------------------------------
# Rule: no-literal-color
# --------------------------------------------------------------------------

# Doctrine: skills/fidara-design/references/brand.md:87
#   "mark is not themeable. `Ui::Logo` is the only component permitted to carry
#    literal colors."
#
# THE EXCEPTION IS THE POINT. Doctrine names exactly one component that may
# carry literal colour. A naive no-hex rule fails our own `Ui::Logo` reference
# implementation -- i.e. the gate would report our doctrine as a violation of
# itself. Encode the carve-out, or the gate is wrong.

_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")

# Doctrine exempts the COMPONENT `Ui::Logo`, not "any file called logo". An
# exemption matched loosely against the path (`(^|/)(_)?logo\b`) is a one-line
# bypass: name a partial `logo.html.erb` and hardcode whatever you like. So the
# carve-out is an explicit allowlist of the component's canonical locations.
# Adding a path here is a deliberate doctrine decision, not a convenience.
_LOGO_EXEMPT_PATHS = frozenset({
    "app/components/ui/logo.rb",
    "app/components/ui/logo.html.erb",
    "app/components/ui/logo_component.rb",
    "app/components/ui/logo_component.html.erb",
})


def check_no_literal_color(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(workspace, VIEW_GLOBS):
        where = rel(path, workspace)
        if where.lower() in _LOGO_EXEMPT_PATHS:
            continue  # brand.md:87 -- Ui::Logo may carry literal colors.
        for i, line in enumerate(read_lines(path), start=1):
            for match in _HEX.finditer(line):
                findings.append(Finding(
                    "no-literal-color", where, i,
                    f"literal colour `{match.group(0)}` -- consume a role token; "
                    f"only Ui::Logo may carry literals (brand.md:87)",
                ))
    return findings


# --------------------------------------------------------------------------
# Rule: job-idempotent
# --------------------------------------------------------------------------

# Doctrine: skills/rails-8/references/jobs-and-realtime.md:176
#   "- **Idempotent always** -- retries and continuations both re-run code."
#
# WHAT THIS RULE DELIBERATELY DOES NOT CHECK
# ------------------------------------------
# Issue #156 specified "ids only" and "job signature taking an AR object -> fail".
# That contradicts our own doctrine. jobs-and-realtime.md:28 shows:
#     def perform(order)   # pass records, not ids: GlobalID (de)serializes them
# and :39 "Arguments must be serializable: records (GlobalID), primitives".
# An ids-only gate would fail the doctrine's own reference example, making the
# real-skill arm score WORSE than baseline and manufacturing a false finding
# that our doctrine is harmful. The issue's gate spec was wrong; the doctrine is
# right. Only idempotence is gated.

_IDEMPOTENCE_MARKER = re.compile(
    r"\b(find_or_create_by|find_or_initialize_by|upsert|insert_all|"
    r"already_|processed_at|idempotenc|idempotent|"
    r"return\s+if|unless\s+.*\?|exists\?\(|\.lock\b|with_lock)\b",
    re.I,
)
_PERFORM_DEF = re.compile(r"^[ \t]*def[ \t]+perform\b")


def check_job_idempotent(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    files = iter_files(workspace, JOB_GLOBS)
    if not files:
        return [Finding("job-idempotent", "app/jobs", 0,
                        "no job was written, so the task was not attempted")]

    for path in files:
        where = rel(path, workspace)
        lines = read_lines(path)
        body = "\n".join(lines)
        if not any(_PERFORM_DEF.search(line) for line in lines):
            findings.append(Finding(
                "job-idempotent", where, 0,
                "no `def perform` -- not a usable job",
            ))
            continue
        if not _IDEMPOTENCE_MARKER.search(body):
            findings.append(Finding(
                "job-idempotent", where, 0,
                "no guard against re-running (no find_or_create_by / early return / "
                "processed flag / lock): retries re-run this code "
                "(jobs-and-realtime.md:176)",
            ))
    return findings


# --------------------------------------------------------------------------
# Rule: spec-accompanies-behavior
# --------------------------------------------------------------------------

# Doctrine: skills/rails-8/SKILL.md -- pure RSpec is a non-negotiable of the
# stack, and rails-flow's whole premise is spec-proven change. A concern that
# ships without a spec is behaviour nobody proved.

def check_spec_accompanies_behavior(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    concerns = iter_files(workspace, CONCERN_GLOBS)
    if not concerns:
        return [Finding("spec-accompanies-behavior", "app/models/concerns", 0,
                        "no concern was written, so the task was not attempted")]

    spec_files = iter_files(workspace, ("spec/**/*_spec.rb",))
    spec_names = {p.name for p in spec_files}
    spec_blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in spec_files
    )

    for path in concerns:
        where = rel(path, workspace)
        stem = path.stem
        expected = f"{stem}_spec.rb"
        module_name = "".join(part.capitalize() for part in stem.split("_"))
        if expected in spec_names:
            continue
        if re.search(rf"\b{re.escape(module_name)}\b", spec_blob):
            continue  # covered by a differently-named spec that references it
        findings.append(Finding(
            "spec-accompanies-behavior", where, 0,
            f"no spec proves this concern (expected `spec/**/{expected}` or a spec "
            f"referencing `{module_name}`)",
        ))
    return findings


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

RULES: dict[str, Rule] = {
    r.name: r
    for r in (
        Rule("scoped-index",
             "skills/rails-8/references/auth-security.md:121",
             "index/collection reads scope through Current, not the global model",
             check_scoped_index),
        Rule("simple-form-convention",
             "skills/fidara-design/references/forms.md:3",
             "forms use simple_form_for where the project has adopted it",
             check_simple_form_convention),
        Rule("no-inline-dark",
             "skills/fidara-design/references/foundations-tokens.md:247",
             "zero inline dark: utilities in components/views",
             check_no_inline_dark),
        Rule("no-literal-color",
             "skills/fidara-design/references/brand.md:87",
             "no literal colours outside Ui::Logo",
             check_no_literal_color),
        Rule("job-idempotent",
             "skills/rails-8/references/jobs-and-realtime.md:176",
             "jobs guard against re-running (NOT ids-only: doctrine passes records)",
             check_job_idempotent),
        Rule("spec-accompanies-behavior",
             "skills/rails-8/SKILL.md",
             "a concern ships with a spec that proves it",
             check_spec_accompanies_behavior),
    )
}


def run_rules(workspace: Path, rule_names: list[str]) -> tuple[bool, list[Finding]]:
    """Run the named rules. Returns (passed, findings).

    An unknown rule name raises rather than silently scoring a pass -- a typo in
    a case definition must not read as success.
    """
    findings: list[Finding] = []
    for name in rule_names:
        if name not in RULES:
            raise KeyError(
                f"unknown rule {name!r}; known rules: {sorted(RULES)}"
            )
        findings.extend(RULES[name].check(workspace))  # type: ignore[operator]
    return (not findings), findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        print("usage: gates.py <workspace-dir> [rule ...]   (default: all rules)")
        print("\nrules:")
        for rule in RULES.values():
            print(f"  {rule.name:28} {rule.summary}")
            print(f"  {'':28} doctrine: {rule.doctrine}")
        return 0

    workspace = Path(argv[1]).resolve()
    names = argv[2:] or sorted(RULES)
    passed, findings = run_rules(workspace, names)
    for finding in findings:
        print(finding)
    verdict = "PASS" if passed else "FAIL"
    print(f"\n{verdict}: {len(findings)} finding(s) across {len(names)} rule(s) "
          f"in {workspace}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
