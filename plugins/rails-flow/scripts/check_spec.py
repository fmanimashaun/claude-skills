#!/usr/bin/env python3
"""Refuse a technical spec that cannot be built from, or that points at nothing (#1375).

Run:  check_spec.py docs/product/specs/<slug>.md [--decisions docs/brain/DECISIONS.md] [--root DIR]
      check_spec.py --selftest

Exit: 0 clean · 1 findings · 2 unusable (no file, or not a spec).

WHY. `/rails-flow:brief` writes the PRODUCT brief: what, for whom, scope, journeys. Nothing wrote the
TECHNICAL spec (the model, the interfaces, where it will be tested, what was decided and why), so
`/rails-flow:feature` planned inside a session and the plan left with the session. `/rails-flow:spec`
grills the gaps and writes it; this script is what makes "written" mean something.

THE HEADINGS ARE A CONTRACT (REQUIRED). Beyond their presence it refuses:
  * a Sources section citing nothing -- the spec must show what was READ before anyone was asked;
  * a citation (`path § "locator"`) whose file or locator does not exist, and a `D-nnn` that
    DECISIONS.md does not define (both through check_brief's own checkers, never a second copy);
  * a user story not in the form "As a <actor>, I want <capability>, so that <benefit>";
  * a FILE PATH in Implementation decisions -- decisions name modules, interfaces and contracts;
    a path goes stale in a week and turns the spec into a patch plan (fenced code is exempt: a
    prototype's schema or state machine can say a decision more precisely than prose);
  * Testing decisions with no `Seam:` line -- the highest point the behaviour will be tested at,
    agreed with the user before any code;
  * an Out of scope that is only "none", and an open question with no owner.

WHAT IT DOES NOT: judge whether the right questions were asked, or one at a time, or whether a
decision is a good one. The interview is the command's discipline; this is its artifact's floor.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_brief as cb  # noqa: E402  -- one section parser and one citation checker, never a second

REQUIRED = (
    ("Problem", ("problem",)),
    ("Solution", ("solution",)),
    ("Sources", ("sources", "what was read")),
    ("Terms", ("terms", "glossary")),
    ("User stories", ("user stories", "stories")),
    ("Implementation decisions", ("implementation decisions", "implementation")),
    ("Testing decisions", ("testing decisions", "testing")),
    ("Out of scope", ("out of scope", "non-goals")),
    ("Open questions", ("open questions",)),
    ("Decisions", ("decisions", "decision log")),
)
STORY = re.compile(r"^\**as an?\b.+\bi want\b.+\bso that\b.+", re.I)
PATH = re.compile(r"(?<![\w/.-])(?:app|lib|config|db|spec|test|bin|script)/[\w./-]+")
SEAM = re.compile(r"^\**seam\**\s*:\s*\S", re.I)


def section(sections: list, label: str, aliases: tuple[str, ...]):
    """The first section whose heading starts with one of the label's aliases."""
    return next((s for s in sections if any(s.title.strip().lower().startswith(a) for a in aliases)), None)


def prose(sec) -> list[tuple[int, str]]:
    return [(sec.first_body_line + i, line) for i, line in enumerate(sec.lines)
            if not (i < len(sec.fenced) and sec.fenced[i])]


def check(path: Path, root: Path, decisions: Path | None) -> list[str]:
    sections = cb.split_sections(path)
    found = {label: section(sections, label, aliases) for label, aliases in REQUIRED}
    if not any(found.values()):
        raise cb.Unusable(f"{path} has none of the {len(REQUIRED)} sections a spec requires "
                          f"({', '.join(label for label, _ in REQUIRED)}) -- this is not a spec")
    findings = [f"missing section `## {label}`" for label, sec in found.items() if sec is None]

    cb.check_sources(sections, root, findings)
    sources = found["Sources"]
    if sources is not None and not any(cb.SOURCE_REF_RE.search(line) for _, line in prose(sources)):
        findings.append(f"line {sources.start}: Sources cites nothing -- list what was read before "
                        f"anyone was asked, as `path` § \"locator\", so the interview is visibly not "
                        f"asking what the repo already answers")
    cb.check_decisions(sections, decisions, findings)

    stories = found["User stories"]
    if stories is not None:
        bullets = stories.bullets()
        if not bullets:
            findings.append(f"line {stories.start}: User stories has no stories")
        for line_no, text in bullets:
            if not STORY.match(text.strip()):
                findings.append(f"line {line_no}: a story reads \"As a <actor>, I want <capability>, "
                                f"so that <benefit>\", got {text.strip()[:60]!r}")

    impl = found["Implementation decisions"]
    if impl is not None:
        for line_no, line in prose(impl):
            for m in PATH.finditer(cb.INLINE_CODE_RE.sub(lambda c: c.group(0).strip("`"), line)):
                findings.append(f"line {line_no}: Implementation decisions names the file `{m.group(0)}` -- "
                                f"name the module, interface or contract; a path goes stale")

    testing = found["Testing decisions"]
    if testing is not None and not any(SEAM.match(t.strip()) for _, t in testing.bullets()):
        findings.append(f"line {testing.start}: Testing decisions has no `Seam:` line -- say where "
                        f"the behaviour will be tested, agreed with the user before any code")

    out = found["Out of scope"]
    if out is not None:
        cb.check_non_goals(out, findings)
    questions = found["Open questions"]
    if questions is not None:
        cb.check_open_questions(questions, findings)
    return findings


# --------------------------------------------------------------------------- selftest

GOOD = """# Spec — notification bell

## Problem
> "I never know a request was returned until someone phones me."

## Solution
A bell in the header that opens a dropdown of the last ten notifications.

## Sources
- `docs/brain/BRIEF.md` § "Journeys"
- `app/models/notification.rb` § "class Notification"

## Terms
- **Notification**: one event a user is told about. _Avoid_: alert, message.

## User stories
1. As a reviewer, I want to see unread notifications in the header, so that I act on a return the same day.
2. As a reviewer, I want to mark all as read, so that the count means something.

## Implementation decisions
- A `Notifications::Feed` query object returns the last ten for the current user.
- The dropdown is a Turbo Frame loaded on open, not on every page.

```ruby
# from the prototype (it lived in app/models/notification.rb): the unread scope
scope :unread, -> { where(read_at: nil) }
```

## Testing decisions
- Seam: a system spec driving the header dropdown as a signed-in reviewer.
- Prior art: the existing header system specs.

## Out of scope
- Email digests: a separate delivery channel with its own consent question.

## Open questions
- Should the count cap at 99? owner: product

## Decisions
- D-004 — dropdown over a page, because the owner approved the mock-up that way.
"""


def selftest() -> int:
    fails: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            fails.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs/brain").mkdir(parents=True)
        (root / "app/models").mkdir(parents=True)
        (root / "docs/brain/BRIEF.md").write_text("## Journeys\nreviewers act on returns\n")
        (root / "app/models/notification.rb").write_text("class Notification < ApplicationRecord\nend\n")
        (root / "docs/brain/DECISIONS.md").write_text("## D-004 dropdown\n")
        spec = root / "spec.md"
        dec = root / "docs/brain/DECISIONS.md"

        def run(text: str) -> list[str]:
            spec.write_text(text)
            return check(spec, root, dec)

        f = run(GOOD)
        check_that("CONTROL: a complete spec passes", f == [], f)
        f = run(GOOD.replace("## Terms\n", "## Vocabulary list\n"))
        check_that("a missing section is refused", any("missing section `## Terms`" in x for x in f), f)
        f = run(GOOD.replace('- `docs/brain/BRIEF.md` § "Journeys"\n- `app/models/notification.rb` § "class Notification"\n',
                             "- the brief and the model\n"))
        check_that("a Sources section citing nothing is refused", any("Sources cites nothing" in x for x in f), f)
        f = run(GOOD.replace('§ "class Notification"', '§ "class Alert"'))
        check_that("a citation whose locator is not in the file is refused",
                   any("does not contain" in x for x in f), f)
        f = run(GOOD.replace("D-004", "D-009"))
        check_that("an undefined D-nnn is refused", any("D-009" in x for x in f), f)
        f = run(GOOD.replace("2. As a reviewer, I want to mark all as read, so that the count means something.",
                             "2. Mark all as read."))
        check_that("a story not in As/I want/so that form is refused", any("a story reads" in x for x in f), f)
        f = run(GOOD.replace("returns the last ten", "in `app/queries/notifications/feed.rb` returns the last ten"))
        check_that("a file path in Implementation decisions is refused",
                   any("app/queries/notifications/feed.rb" in x for x in f), f)
        check_that("CONTROL: the fenced prototype snippet in Implementation decisions is exempt",
                   not any("app/models/notification.rb" in x for x in run(GOOD)), run(GOOD))
        f = run(GOOD.replace("- Seam: a system spec", "- A system spec"))
        check_that("Testing decisions with no Seam: line is refused", any("no `Seam:` line" in x for x in f), f)
        check_that("CONTROL: a path in Testing decisions is not an implementation path",
                   run(GOOD.replace("the existing header system specs", "`spec/system/header_spec.rb`")) == [])
        f = run(GOOD.replace("- Email digests: a separate delivery channel with its own consent question.", "- None"))
        check_that("an Out of scope of only \"none\" is refused", f != [], f)
        f = run(GOOD.replace("? owner: product", "?"))
        check_that("an open question with no owner is refused", f != [], f)
        spec.write_text("# notes\n\n## Random\ntext\n")
        try:
            check(spec, root, dec)
            check_that("a file with none of the sections is unusable, not a list of misses", False)
        except cb.Unusable:
            pass

    for f in fails:
        print(f"selftest FAIL: {f}")
    print(f"check_spec selftest: {'FAILED' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_spec.py", description=__doc__.splitlines()[0])
    ap.add_argument("spec", nargs="?", type=Path)
    ap.add_argument("--decisions", type=Path, default=Path("docs/brain/DECISIONS.md"))
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.spec is None:
        ap.error("a spec path is required")
    try:
        findings = check(a.spec, a.root.resolve(), a.decisions)
    except cb.Unusable as exc:
        print(f"UNUSABLE: {exc}")
        return 2
    if findings:
        print(f"{len(findings)} spec finding(s) in {a.spec}:")
        print("\n".join(f"  {x}" for x in findings))
        return 1
    print(f"spec: {a.spec} is complete, and every citation resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
