#!/usr/bin/env python3
"""A merge into an ARMED `dev` re-opens `### Unreleased` and breaks the next promotion (#1170).

Run:  python3 scripts/check_arm_window.py            # this branch against origin/dev
      python3 scripts/check_arm_window.py --selftest

THE WINDOW NOTHING ANNOUNCES. Between the **arm** (`chore/arm-vX.Y.Z` -> `dev`, which converts every
`### Unreleased` heading into `### <ver> (release vX.Y.Z)`) and the **promotion** (`dev` -> `main`),
the CHANGELOG's shape is load-bearing -- and `dev` looks identical to merge into before, during and
after. A PR merged in that window carries its bullet under its own `### Unreleased`, **re-opening
that heading on dev**. The next promotion PR then fails `extract_release_notes.py --promotion`, which
refuses any `### Unreleased` -- correctly, and with no indication that the cause was a merge three
minutes earlier rather than anything in the promotion.

`CLAUDE.md` already prescribes the repair: a fix landing after an arm and before its promotion is
**folded** into the armed block, never left `Unreleased` and never re-armed. The doctrine is
complete. It was performed by nothing.

HOW IT SURFACED, twice in one afternoon, and only the second was noticed at the time. A session
merged at 16:12 with an arm in flight and told nobody; it landed BELOW the arm commit, so the arm
swept its bullet up and nothing broke. **Three minutes later and it would not have.** Earlier, a
different session held their arm for a peer and asked to be pinged -- that worked because a message
was sent, not because anything checked. Two arms, one saved by a message and one by luck, neither by
a mechanism.

THE DISCRIMINATOR IS THE UN-PROMOTED RELEASE BLOCK, NOT THE ABSENCE OF `### Unreleased`. Keying on
the absence alone fires constantly, because "no Unreleased yet" is `dev`'s ordinary state just after
a promotion -- a check that fires constantly is switched off within a week. Armed means BOTH: zero
`### Unreleased` AND at least one `(release vX.Y.Z)` block whose tag does not exist yet.

AND THE TAG IS CHECKED AGAINST THE REAL TAG LIST, never against the CHANGELOG's own text. The
CHANGELOG naming `v1.141.0` is the claim under test; using it as its own evidence would leave an
already-promoted `dev` reporting as armed forever, and the window would never close.

THE SECOND HALF IS THE `Closes` LIST, and it is the part the incident actually cost. Folding a bullet
into the armed block without adding its `Closes #n` to the promotion is the same silent merge with
the CHANGELOG tidied up: the issue then sits open over a release that contains it, and the next
person reads it as unshipped. `--promotion-closes` compares the issues referenced in the armed blocks
against the `Closes` in a promotion PR body.

Stdlib only, no network. Git is read through `git`, which is already required by every other gate.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

UNRELEASED = re.compile(r"^### Unreleased\s*$", re.M)
# ANCHORED THE WAY `extract_release_notes.py` ANCHORS IT, not stricter. Its `PUBLISHING_SHAPE`
# looks for `(release vX.Y.Z)` ANYWHERE in the heading, because the real headings carry a date
# after the paren -- `### 1.47.0 (release v1.141.0) — 2026-09-22`. A `\)\s*$` anchor matches
# none of them, and this check would then report every armed dev as unarmed and stay silent
# forever. Caught by a fixture written in the real heading format rather than a tidy one.
RELEASE_BLOCK = re.compile(r"^### .*\(release (v\d+\.\d+\.\d+)\)", re.M)
# `Refs #n` and `Closes #n` both appear in bullets; the arm does not rewrite them, so an armed block
# carries whatever the merged PRs wrote. Only the NUMBER matters for reconciliation.
ISSUE_REF = re.compile(r"\(#(\d+)\)")
CLOSES = re.compile(r"\bcloses\s+#(\d+)\b", re.I)


def git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(("git",) + args, cwd=cwd or REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def existing_tags(cwd: Path | None = None) -> set[str]:
    """The REAL tag list. Never the CHANGELOG's own text -- see the module docstring."""
    return {t.strip() for t in git("tag", "-l", cwd=cwd).splitlines() if t.strip()}


def armed_for(changelog: str, tags: set[str]) -> str | None:
    """The version `dev` is armed for, or None. BOTH halves, or a freshly promoted dev reads armed."""
    if UNRELEASED.search(changelog):
        return None                       # still accepting work; not armed
    pending = [v for v in RELEASE_BLOCK.findall(changelog) if v not in tags]
    return sorted(pending)[-1] if pending else None


def reopens_unreleased(base: str, head: str) -> list[str]:
    """Sections where the head opens a `### Unreleased` the base does not have."""
    return [] if not UNRELEASED.search(head) else _sections_with_unreleased(head) - _sections_with_unreleased(base)


def _sections_with_unreleased(text: str) -> set[str]:
    section, found = None, set()
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif UNRELEASED.match(line) and section:
            found.add(section)
    return found


def check(base_changelog: str, head_changelog: str, tags: set[str]) -> list[str]:
    version = armed_for(base_changelog, tags)
    if version is None:
        return []                         # not in the window; nothing to say
    reopened = sorted(reopens_unreleased(base_changelog, head_changelog))
    if not reopened:
        return []
    return [
        f"dev is ARMED for {version} (its tag does not exist yet), and this branch re-opens "
        f"`### Unreleased` in: {', '.join(reopened)}.",
        f"  Merging it would leave an `### Unreleased` on dev, and the promotion PR would be "
        f"refused by `extract_release_notes.py --promotion` with no sign that a merge caused it.",
        f"  FOLD the bullet into the armed `(release {version})` block in its section instead — "
        f"never a second `### Unreleased`, never a second arm — and make sure the promotion's "
        f"`Closes #n` list gains this issue, or it stays open over a release containing it.",
    ]


def promotion_closes(changelog: str, body: str, tags: set[str]) -> list[str]:
    """Every issue in the armed blocks must be `Closes`d by the promotion that ships them."""
    version = armed_for(changelog, tags)
    if version is None:
        return ["no armed release block — a promotion PR must be raised from an armed dev"]
    shipped: set[str] = set()
    grabbing = False
    for line in changelog.splitlines():
        m = RELEASE_BLOCK.match(line)
        if m:
            grabbing = m.group(1) == version
            continue
        if line.startswith("### ") or line.startswith("## "):
            grabbing = False
        if grabbing:
            shipped.update(ISSUE_REF.findall(line))
    missing = sorted(shipped - set(CLOSES.findall(body)), key=int)
    return [] if not missing else [
        f"the armed {version} blocks ship #{', #'.join(missing)}, and the promotion body does not "
        f"close them. An issue left open over a release containing it reads as unshipped work.",
    ]


# --------------------------------------------------------------------------- selftest

ARMED = "## rails-flow\n\n### 1.47.0 (release v9.9.9) — 2026-09-22\n\n- a thing (#1157)\n- another (#1154)\n"
ARMED_PROMOTED = "## rails-flow\n\n### 1.47.0 (release v0.0.1) — 2026-09-22\n\n- a thing (#1157)\n"
OPEN = "## rails-flow\n\n### Unreleased\n\n- a thing (#1)\n"
ARMED_PLUS_NEW = ARMED + "\n### Unreleased\n\n- my new bullet (#1170)\n"
NO_BLOCKS = "## rails-flow\n\n- prose only, no headings\n"


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    tags = {"v0.0.1"}          # v9.9.9 does NOT exist; v0.0.1 does

    # THE DEFECT, in the shape it happened.
    f = check(ARMED, ARMED_PLUS_NEW, tags)
    check_that("a merge that re-opens Unreleased on an ARMED dev is refused", bool(f), str(f))
    check_that("...and the finding names the version and the repair",
               bool(f) and "v9.9.9" in f[0] and "FOLD" in f[2], str(f))

    # THE CONTROL THAT MATTERS MOST. `dev`'s ordinary state is "has Unreleased"; a check keying on
    # its ABSENCE alone fires on every merge and is switched off within a week.
    check_that("a merge into an UNARMED dev is silent", check(OPEN, OPEN + "\n- more\n", tags) == [])
    check_that("...even when the branch itself adds an Unreleased section",
               check(OPEN, OPEN + "\n## qa-flow\n\n### Unreleased\n\n- x (#2)\n", tags) == [])

    # THE WINDOW CLOSES BY ITSELF. Tag exists -> promoted -> not armed. This is why the tag list is
    # read from git and never from the CHANGELOG: using the file as its own evidence would leave a
    # promoted dev armed forever.
    check_that("an already-PROMOTED dev is not armed", armed_for(ARMED_PROMOTED, tags) is None)
    check_that("...so a merge into it is silent", check(ARMED_PROMOTED, ARMED_PROMOTED + "\n### Unreleased\n\n- x (#3)\n", tags) == [])

    # Both halves are required for "armed".
    check_that("zero release blocks is not armed", armed_for(NO_BLOCKS, tags) is None)
    check_that("an Unreleased heading anywhere means not armed", armed_for(ARMED + "\n### Unreleased\n", tags) is None)
    check_that("armed is detected when both halves hold", armed_for(ARMED, tags) == "v9.9.9")

    # A merge that does NOT touch the CHANGELOG is fine during the window -- most merges are.
    check_that("a merge into an armed dev that adds no Unreleased is silent", check(ARMED, ARMED + "\n- folded bullet (#1170)\n", tags) == [])

    # THE `Closes` HALF -- the part the incident actually cost.
    missing = promotion_closes(ARMED, "Promotes v9.9.9.\n\nCloses #1157\n", tags)
    check_that("a promotion missing a Closes for a shipped issue is refused", bool(missing) and "1154" in missing[0], str(missing))
    check_that("...and a complete promotion body passes",
               promotion_closes(ARMED, "Closes #1157\nCloses #1154\n", tags) == [], str(promotion_closes(ARMED, "Closes #1157\nCloses #1154\n", tags)))
    # THE CONTROL FOR IT: without this, "refuses a missing Closes" is satisfied by a check that
    # refuses every promotion body.
    check_that("a promotion body closing MORE than it ships is not refused",
               promotion_closes(ARMED, "Closes #1157\nCloses #1154\nCloses #999\n", tags) == [])

    for f2 in failures:
        print(f"selftest FAIL: {f2}")
    print(f"check_arm_window selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--base", default="origin/dev", help="the ref this branch would merge into")
    ap.add_argument("--promotion-closes", metavar="BODY_FILE",
                    help="check a promotion PR body closes every issue the armed blocks ship")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    base_cl = git("show", f"{args.base}:CHANGELOG.md")
    if not base_cl:
        print(f"check_arm_window: cannot read CHANGELOG.md at {args.base} — skipping, not passing")
        return 0
    tags = existing_tags()

    if args.promotion_closes:
        findings = promotion_closes(base_cl, Path(args.promotion_closes).read_text(encoding="utf-8"), tags)
    else:
        findings = check(base_cl, (REPO / "CHANGELOG.md").read_text(encoding="utf-8"), tags)

    if findings:
        print("arm window:")
        for f in findings:
            print(f"  {f}")
        return 1
    version = armed_for(base_cl, tags)
    print(f"arm window: {args.base} is {'ARMED for ' + version + ', and this branch does not re-open Unreleased' if version else 'not armed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
