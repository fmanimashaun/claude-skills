#!/usr/bin/env python3
"""The maintainer sessions need the doctrine they collide over.

`skills/parallel-session-lane` is SHIPPED: it reaches downstream projects inside `rails-stack`, and
a consuming repo loads it because that repo enables the plugin. This repository does not. Measured
on 17 Sep 2026, `.claude/settings.json` here enables exactly one plugin — `remember` — so a session
maintaining this marketplace never loads the parallel-session skill at all.

That is how four maintainer sessions spent a day rediscovering it: the doctrine was shipped to
everyone except the people writing it. Four collisions in one shared checkout, a decision number
claimed by three branches at once, and a ledger four numbers stale.

WHY A GENERATED COPY AND NOT A SECOND FILE. `plugin-boundaries` allows exactly one home per concern,
and this repo's own review doctrine treats two copies of one rule as a defect waiting to happen —
the copy that drifts is always the one nobody is reading. So `skills/**` stays the single source and
`.claude/skills/**` is DERIVED from it, committed, and drift-gated, the same shape as
`docs/evidence/coverage.html` and the wiki pages.

WHY NOT JUST ENABLE `rails-stack` HERE. It would pull rails-8, hotwire, design-system, code-review,
quality-pass and derived-artifacts into every maintainer session of a repository that is not a Rails
app — CLAUDE.md's own words: "If you are here to build a Rails app, you want the plugins, not this
file." One skill is wanted; a stack is not.

WHY NOT A SYMLINK. Cheaper, and it fails on the platform CLAUDE.md already says is supported: a
committed symlink needs developer mode on Windows, and a reader who lands on the broken link has no
way to tell what it was for. A generated file carries its own banner.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# source -> derived. One entry today; the list is the mechanism, not the special case.
MIRRORED = {
    Path("skills/parallel-session-lane/SKILL.md"): Path(".claude/skills/parallel-session-lane/SKILL.md"),
}

BANNER = (
    "<!-- GENERATED from {source} by scripts/build_maintainer_skills.py — do not edit.\n"
    "     The shipped skill is the source of truth; this copy exists because this repository's\n"
    "     own sessions do not load `rails-stack`, so the doctrine would otherwise reach every\n"
    "     consumer except its maintainers. Edit the source and re-run the script. -->\n"
)


def render(source: Path) -> str:
    """The derived file: the source verbatim, with a banner after the frontmatter.

    AFTER the frontmatter, not before it: a skill's YAML block has to start at byte zero, and a
    comment above it makes the loader read the whole file as prose. Found by putting it on top
    first — the skill silently stopped being a skill.
    """
    text = (ROOT / source).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{source} does not open with a frontmatter block")
    if "\n---\n" not in text[4:]:
        raise SystemExit(f"{source} opens a frontmatter block and never closes it")

    end = text.index("\n---\n", 4) + len("\n---\n")
    return text[:end] + "\n" + BANNER.format(source=source.as_posix()) + text[end:]


def unregistered_mirrors() -> list[str]:
    """Copies of a SHIPPED skill sitting in `.claude/skills/` that no registry entry governs.

    `--check` proves every mirror it KNOWS ABOUT is a clean build. It cannot prove there are no
    other copies, and `cp skills/code-review/SKILL.md .claude/skills/code-review/` — the likeliest
    route by far, because it needs nobody to read this file — passed a full green sweep. That is
    exactly the two-homes defect the module docstring says this design prevents.

    The rule is not "nothing unregistered": `.claude/skills/plugin-boundaries/` is maintainer-only,
    has no counterpart under `skills/`, and is correct. A derived directory is illegal only when a
    SHIPPED skill of the same name exists and the registry does not govern it.
    """
    registered = {derived.as_posix() for derived in MIRRORED.values()}
    strays = []
    for derived in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        relative = derived.relative_to(ROOT).as_posix()
        if relative in registered:
            continue
        if (ROOT / "skills" / derived.parent.name / "SKILL.md").exists():
            strays.append(relative)
    return strays


def build(check: bool) -> int:
    drifted = []
    for source, derived in MIRRORED.items():
        want = render(source)
        target = ROOT / derived
        have = target.read_text(encoding="utf-8") if target.exists() else None

        if check:
            if have != want:
                drifted.append(derived.as_posix())
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if have != want:
            target.write_text(want, encoding="utf-8")
            print(f"wrote {derived.as_posix()} from {source.as_posix()}")
        else:
            print(f"ok    {derived.as_posix()} matches {source.as_posix()}")

    strays = unregistered_mirrors()

    if drifted:
        for d in drifted:
            print(f"DRIFT: {d} is not a clean build of its source")
        print("  -> python3 scripts/build_maintainer_skills.py && git add .claude/skills/")
    for s in strays:
        print(f"UNREGISTERED: {s} copies a shipped skill that no MIRRORED entry governs")
    if strays:
        print("  -> add it to MIRRORED and rebuild, or delete the copy")
    if drifted or strays:
        return 1
    if check:
        print(f"maintainer skills: {len(MIRRORED)} derived file(s), no drift, no unregistered copies")
    return 0


def selftest() -> int:
    """Three directions: the banner lands after the frontmatter, drift fails, a stray copy fails.

    A generator whose --check cannot fail is the whole class of defect this repo lints for, so each
    arm is proved by mutating the tree rather than by trusting the comparison. The stray arm exists
    because the drift arm passed a hand-copied shipped skill: proving the registry is clean is not
    proving there is only one home.
    """
    failures = []
    source = next(iter(MIRRORED))
    rendered = render(source)

    if not rendered.startswith("---\n"):
        failures.append("the derived file does not open with the frontmatter block")
    if "GENERATED from" not in rendered:
        failures.append("the derived file carries no banner")
    body_start = rendered.index("\n---\n", 4)
    if "GENERATED from" in rendered[:body_start]:
        failures.append("the banner is INSIDE the frontmatter, which breaks the loader")

    # The drift arm, against a deliberately wrong copy.
    target = ROOT / MIRRORED[source]
    if target.exists():
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(original + "\ndrifted\n", encoding="utf-8")
            if build(check=True) == 0:
                failures.append("--check passed against a file that had been edited")
        finally:
            target.write_text(original, encoding="utf-8")
    else:
        failures.append("no derived file to mutate — run the generator first")

    # The stray arm: a copy of a shipped skill that no MIRRORED entry governs.
    shipped = sorted(
        s.parent.name
        for s in (ROOT / "skills").glob("*/SKILL.md")
        if not (ROOT / ".claude" / "skills" / s.parent.name).exists()
    )
    if shipped:
        stray = ROOT / ".claude" / "skills" / shipped[0] / "SKILL.md"
        try:
            stray.parent.mkdir(parents=True)
            stray.write_text(
                (ROOT / "skills" / shipped[0] / "SKILL.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            if build(check=True) == 0:
                failures.append(f"--check passed against an unregistered copy of skills/{shipped[0]}")
        finally:
            stray.unlink(missing_ok=True)
            stray.parent.rmdir()
    else:
        failures.append("every shipped skill already has a derived directory — the stray arm cannot run")

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    if not failures:
        print(
            "selftest: ok — the banner sits after the frontmatter, an edited copy fails --check, "
            "and an unregistered copy of a shipped skill fails too"
        )
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    return build(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
