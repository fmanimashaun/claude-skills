#!/usr/bin/env python3
"""Which of the repo's PR-template sections a PR body is missing (#1389). Called by guard-claims.sh.

Run:  pr_template.py <repo-root> <body-file>   # prints each missing heading; exit 1 if any, 0 if none
      pr_template.py --selftest

Exit 0 also when the repo has no PR template: the rule is the project's own template, and a
project without one has declared nothing.

WHY. A downstream project's independent pr-reviewer BLOCKED 5 of 5 PRs in one day for the same
finding: the body lacked its template's Documentation Contract sections, and 3 earlier PRs had
merged without them. The rule was prose, followed 0 times in 5. A hook runs without being
remembered.

THE TEMPLATE IS THE AUTHORITY, AND IT IS READ, NEVER HARDCODED. Its `##` headings are required,
with two refinements the templates themselves demand:
  * a section headed `## If …` is conditional by its own wording ("If this touches skills/**"), so
    it may be left out;
  * a heading matches on its CORE text, before an em dash, a colon or a parenthesis, and case-
    and punctuation-insensitively, so "Change type — required, before the first edit" in the
    template is satisfied by "## Change type" in the body.
A section that does not apply stays in the body, saying "N/A" and why. A section that has been
deleted cannot be told apart from one that was forgotten, which is the failure this exists for.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# GitHub's three homes for a single template, in its own lookup order. The name is matched
# case-insensitively by LISTING the directory: a filesystem that ignores case would otherwise make a
# fixture pass on macOS that fails on Linux.
DIRS = (".github", "", "docs")
NAME = "pull_request_template.md"
HEADING = re.compile(r"^\s{0,3}(#{2,3})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def template_path(root: Path) -> Path | None:
    for d in DIRS:
        folder = root / d
        if folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if entry.name.lower() == NAME and entry.is_file():
                    return entry
    return None


def core(heading: str) -> str:
    text = re.split(r"\s[—–-]\s|:|\(", heading, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def headings(text: str, level: str | None = None) -> list[str]:
    """Headings outside fenced blocks and HTML comments. `level` restricts to `##` for a template."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else HEADING.match(line)
        if m and (level is None or m.group(1) == level):
            out.append(m.group(2))
    return out


# A section the template itself marks conditional may be left out. Judged on the FULL heading, before
# `core()` drops the parenthesis: "Screenshots (if applicable)" and "Related issues (optional)" are
# common downstream, and trimming first made them required (pre-release review of #1398).
CONDITIONAL = re.compile(r"^\s*(if|optional)\b|\((optional|if\b[^)]*)\)", re.I)


def missing(template_text: str, body_text: str) -> list[str]:
    have = {core(h) for h in headings(body_text)}
    return [h for h in headings(template_text, "##")
            if not CONDITIONAL.search(h) and core(h) and core(h) not in have]


def selftest() -> int:
    fails: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            fails.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    tpl = ("<!--\n## Not a heading, it is in a comment\n-->\n"
           "## What changed, and why\n\n## How to test\n\n## Change type — required, before the first edit\n\n"
           "## Rules enforced in code (spec §9)\n\n## If this touches `skills/**`\n\n"
           "```\n## not a heading, it is in a fence\n```\n")
    full = ("## What changed, and why\nx\n## How to test\nN/A — copy only\n"
            "## Change type\nour design\n## Rules enforced in code\nnone\n")
    check_that("CONTROL: a body carrying every section passes", missing(tpl, full) == [], missing(tpl, full))
    m = missing(tpl, full.replace("## How to test\nN/A — copy only\n", ""))
    check_that("a body missing one section is refused, and names it", m == ["How to test"], m)
    check_that("CONTROL: a heading matches on its core text (before the em dash)",
               "Change type — required, before the first edit" not in missing(tpl, full))
    check_that("CONTROL: a heading matches on its core text (before the parenthesis)",
               "Rules enforced in code (spec §9)" not in missing(tpl, full))
    check_that("CONTROL: an `If …` section is conditional and may be left out",
               not any(h.startswith("If ") for h in missing(tpl, full)))
    check_that("CONTROL: a heading inside a template comment or fence is not required",
               missing(tpl, full) == [])
    m = missing(tpl, "## What changed, and why\n## How to test\n## Change type\n")
    check_that("a body missing a parenthesised section is refused", m == ["Rules enforced in code (spec §9)"], m)
    m = missing(tpl, "Everything in prose: what changed, how to test, change type, rules.\n")
    check_that("section names in prose are not sections", len(m) == 4, m)
    check_that("a body heading at ### still counts", missing(tpl, full.replace("## ", "### ")) == [])
    opt = "## Summary\n\n## Screenshots (if applicable)\n\n## Related issues (optional)\n\n## Optional notes\n"
    check_that("CONTROL: (if applicable), (optional) and a leading Optional mark a section conditional",
               missing(opt, "## Summary\nx\n") == [], missing(opt, "## Summary\nx\n"))
    check_that("...while an unmarked parenthesis does not", missing("## Proof (screens)\n", "## Summary\n") == ["Proof (screens)"])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        check_that("a repo with no template has no template", template_path(root) is None)
        (root / "docs").mkdir()
        (root / "docs/PULL_REQUEST_TEMPLATE.md").write_text(tpl)
        check_that("an uppercase template under docs/ is found", template_path(root) is not None)

    for f in fails:
        print(f"selftest FAIL: {f}")
    print(f"pr_template selftest: {'FAILED' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if len(argv) != 2:
        print("usage: pr_template.py <repo-root> <body-file>", file=sys.stderr)
        return 2
    tpl = template_path(Path(argv[0]))
    if tpl is None:
        return 0
    # errors="replace": a body with stray bytes is still a body; a crash here must not decide anything.
    gaps = missing(tpl.read_text(encoding="utf-8", errors="replace"),
                   Path(argv[1]).read_text(encoding="utf-8", errors="replace"))
    for h in gaps:
        print(h)
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
