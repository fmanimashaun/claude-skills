#!/usr/bin/env python3
"""Refuse a promotion where a component's files changed and its CHANGELOG section did not.

Run:  python3 scripts/check_changelog_coverage.py               # against origin/main
      python3 scripts/check_changelog_coverage.py --base <ref>
      python3 scripts/check_changelog_coverage.py --selftest

WHY THIS EXISTS (#728). CLAUDE.md states it outright -- **"Every bump gets a CHANGELOG entry** under
the component's section" -- and nothing made it true. `changelog-section-missing` only asserts the
`## ` heading EXISTS. `changelog-bullet-misfiled` and `-unplaceable` only judge bullets that are
already present. A component whose files changed with **no bullet at all** passed every gate.

It bit on the v1.94.0 arm. Resolving a CHANGELOG conflict, the file was rebuilt from dev's side and
only the rails-flow body was re-grafted; the rails-stack bullet lived in the other merge stage and was
silently dropped, while `skills/parallel-session-lane/SKILL.md` itself merged fine:

    $ git show origin/dev:CHANGELOG.md | grep -c 'parallel-session-lane. §0 now says'
    0
    $ git diff --name-only origin/main..origin/dev -- skills/
    skills/parallel-session-lane/SKILL.md
    $ python3 scripts/lint_self_consistency.py
    no findings.

A changed component, no note, every gate green. It surfaced only because the arm script happened to
assert the number of `### Unreleased` headings -- an assertion in throwaway code, not in the repo.

WHY IT MATTERS MORE THAN A MISSING LINE. Every block for a tag publishes now (#699), so the CHANGELOG
*is* the release notes. A dropped bullet ships a component version with no published account of what
changed in it -- and a reader cannot tell that from a component that legitimately changed nothing,
because both look identical: a bump with silence beneath it.

WHY THIS IS A DIAGNOSTIC AND NOT A GATE. It needs `origin/main` to diff against, and `gates.yml` uses
`actions/checkout` with no `fetch-depth`, so CI has a one-commit clone. A gate that cannot see its own
input would report clean on input it never read -- the defect class this repo files most. So the live
check runs in `maintainer_doctor.py` (skipped by `--gates-only`, exactly like the promotion-ancestry
check), and the SELFTEST is the gate. That is the same split `build_coverage.py` uses. This constraint
is inherited, not rediscovered: it is what killed #701's first proposed mechanism.

WHAT COUNTS AS A NOTE. A new `- ` bullet inside that component's `## ` section, comparing the base's
CHANGELOG to this one. Not a heading, not a reworded line: an added bullet. Converting `### Unreleased`
to a release heading at arm time therefore does not, by itself, satisfy anything -- which is right,
because renaming a heading is not writing a note.

Exit codes:  0 = every changed component has a note · 1 = one or more do not · 2 = not this repo

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

# Reuse the existing mapping rather than adding a second one. Two derivations of "which component
# owns this path" would drift, and the one that drifted would be the one nobody was reading.
from lint_self_consistency import _changelog_owner, _changelog_section_owner  # noqa: E402

BULLET = re.compile(r"^- ")


def section_bullets(text: str, plugins: list[str]) -> dict[str, set[str]]:
    """{component: set of bullet lines} across the whole CHANGELOG."""
    out: dict[str, set[str]] = {}
    owner = None
    for line in text.split("\n"):
        if line.startswith("## "):
            owner = _changelog_section_owner(line[3:].strip(), plugins)
            out.setdefault(owner, set())
        elif owner and BULLET.match(line):
            out[owner].add(line.strip())
    return out


def missing_notes(changed: list[str], before: str, after: str,
                  plugins: list[str]) -> list[str]:
    """Components whose files changed but which gained no CHANGELOG bullet.

    `repository` is excluded deliberately: `scripts/`, `docs/` and the root files are maintainer
    tooling that ships to nobody, and CLAUDE.md's rule is about a component BUMP. Requiring a note
    for every script edit would fire on correct work, and a check that does that gets switched off.
    """
    touched = {_changelog_owner(p, plugins) for p in changed if p != "CHANGELOG.md"}
    touched.discard("repository")
    if not touched:
        return []
    was, now = section_bullets(before, plugins), section_bullets(after, plugins)
    findings = []
    for comp in sorted(touched):
        added = now.get(comp, set()) - was.get(comp, set())
        if not added:
            findings.append(
                f"{comp}: files changed but its CHANGELOG section gained no bullet. Every bump gets "
                f"an entry — a version shipping with silence beneath it is indistinguishable from a "
                f"component that changed nothing.")
    return findings


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def _plugins() -> list[str]:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return [p["name"] for p in data.get("plugins", [])]


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    plugins = ["rails-flow", "qa-flow", "rails-stack"]
    base = ("# Changelog\n\n## rails-flow (agentic flow plugin)\n\n### 1.0.0\n\n- old rails-flow note\n"
            "\n## rails-stack (rails-8 skills)\n\n### 1.0.0\n\n- old skills note\n")

    # THE REPORTED CASE: a skill changed, only the other component gained a bullet.
    after = base.replace("- old rails-flow note", "- old rails-flow note\n- new rails-flow note")
    f = missing_notes(["plugins/rails-flow/x.md", "skills/parallel-session-lane/SKILL.md"],
                      base, after, plugins)
    # Indexed defensively: under a mutation that empties this list, `f[0]` would CRASH, and a crash
    # is not a verdict -- the mutation harness rejects a fixture that dies instead of failing.
    check("a changed skill with no new bullet is a finding",
          len(f) == 1 and f[0].startswith("rails-stack:"))
    check("...and the component that DID gain one is silent",
          bool(f) and "rails-flow" not in f[0])

    after2 = after.replace("- old skills note", "- old skills note\n- new skills note")
    check("both noted is silent",
          missing_notes(["plugins/rails-flow/x.md", "skills/a/SKILL.md"], base, after2, plugins) == [])

    # THE COMMON CASE MUST NOT FIRE. No component files changed at all.
    check("a repository-only change is silent",
          missing_notes(["scripts/x.py", "docs/y.html", "CLAUDE.md"], base, base, plugins) == [])
    check("a CHANGELOG-only change is silent",
          missing_notes(["CHANGELOG.md"], base, after, plugins) == [])

    # A RENAMED HEADING IS NOT A NOTE. Arming converts `### Unreleased`; that must not satisfy this.
    armed = base.replace("### 1.0.0", "### 1.1.0 — 2026-01-01 (release v9.9.9)")
    check("converting a heading is not a note",
          any(x.startswith("rails-stack:") for x in
              missing_notes(["skills/a/SKILL.md"], base, armed, plugins)))

    # An EDITED bullet counts as added, because the set differs -- stated so nobody reads it as a bug.
    edited = base.replace("- old skills note", "- old skills note, now with more detail")
    check("a reworded bullet counts as a note",
          missing_notes(["skills/a/SKILL.md"], base, edited, plugins) == [])

    # A REMOVED bullet with nothing added must still fire.
    removed = base.replace("- old skills note\n", "")
    check("removing the only bullet is a finding",
          any(x.startswith("rails-stack:") for x in
              missing_notes(["skills/a/SKILL.md"], base, removed, plugins)))

    # Against the REAL repo: whatever the tree says, the function must not crash and must agree with
    # itself. A selftest that only sees fixtures is the bug maintainer_doctor was written about.
    try:
        real = missing_notes([], "", "", _plugins())
        check("no changed paths means no findings, on the real manifest", real == [])
    except Exception as exc:                                          # noqa: BLE001
        check(f"the real manifest loads ({exc})", False)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if not (REPO / ".claude-plugin" / "marketplace.json").is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    if a.selftest:
        return _selftest()

    if not _git("rev-parse", "--verify", a.base).strip():
        # Absent base is a SKIP, never a pass -- say so and exit 0, because a shallow CI clone is a
        # legitimate reason not to know, and the caller decides what to do with that.
        print(f"skipped: {a.base} is not available in this clone (shallow checkout?)")
        return 0
    changed = [p for p in _git("diff", "--name-only", f"{a.base}..HEAD").split("\n") if p]
    before = _git("show", f"{a.base}:CHANGELOG.md")
    after = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    findings = missing_notes(changed, before, after, _plugins())
    if findings:
        print(f"{len(findings)} component(s) changed with no CHANGELOG entry:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"clean — every component changed since {a.base} has a CHANGELOG entry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
