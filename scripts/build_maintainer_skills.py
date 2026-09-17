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
import subprocess
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


def committed_blob(relative: str, cwd: Path = ROOT) -> str | None:
    """The file as `HEAD` holds it, or None when HEAD has no such blob.

    THE BLOB AT HEAD, NEVER THE WORKING COPY (#1008). Reading the working copy made this the one
    derived-artifact check in the repo that fails OPEN: rebuild the mirror, forget
    `git add .claude/skills/`, commit the source alone, and the local sweep reads the rebuilt file
    off disk and prints `no drift` — while CI, which checks the commit out, meets a stale committed
    mirror against a new committed source and goes red. The local run structurally could not
    reproduce the CI failure it was supposed to predict. `build_wiki.py` and `doctrine_map.py`
    already read HEAD for exactly this reason, and CLAUDE.md already states the rule: "a page built
    and never `git add`ed fails honestly".

    None (no repository, no blob) counts as drift, not as a pass — an unreadable HEAD is the
    condition this check exists to notice, so treating it as clean would reintroduce the fail-open
    one level down.
    """
    try:
        result = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=cwd,
                                capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


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

        if check:
            # HEAD, not the working tree — see committed_blob(). A rebuilt-but-unstaged mirror is
            # the whole point: it is invisible to every other clone while sitting right there.
            if committed_blob(derived.as_posix()) != want:
                drifted.append(derived.as_posix())
            continue

        have = target.read_text(encoding="utf-8") if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        if have != want:
            target.write_text(want, encoding="utf-8")
            print(f"wrote {derived.as_posix()} from {source.as_posix()}")
        else:
            print(f"ok    {derived.as_posix()} matches {source.as_posix()}")

    strays = unregistered_mirrors()

    if drifted:
        for d in drifted:
            print(f"DRIFT: {d} as COMMITTED is not a clean build of its source")
        # `git add` does NOT clear this: `git show HEAD:` reads the commit, not the index. Saying
        # "add" would send the reader round a loop that cannot end — measured, staged, still red.
        print("  -> python3 scripts/build_maintainer_skills.py, then git add .claude/skills/ and "
              "COMMIT — the check reads HEAD, so a rebuilt or merely staged mirror stays red")
    for s in strays:
        print(f"UNREGISTERED: {s} copies a shipped skill that no MIRRORED entry governs")
    if strays:
        print("  -> add it to MIRRORED and rebuild, or delete the copy")
    if drifted or strays:
        return 1
    if check:
        print(f"maintainer skills: {len(MIRRORED)} derived file(s), no drift, no unregistered copies")
    return 0


def head_read_arm() -> list[str]:
    """Prove `committed_blob` reads the COMMIT, against a real throwaway repository.

    Every other arm stubs this function, which is the right fixture for what the comparison DOES
    with a blob — and leaves the read itself unproven. So this one builds a two-line repository in
    a tempdir and asserts the two mistakes that look identical from the call site: returning the
    working copy, and returning the INDEX. The index is the subtle one — `git show :path` makes
    `git add` alone clear the gate, which is the same fail-open #1008 fixed, moved one step along.
    """
    import tempfile

    problems = []
    with tempfile.TemporaryDirectory(prefix="mskills-head-") as tmp:
        repo = Path(tmp)

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)

        git("init", "-q")
        git("config", "user.email", "selftest@example.invalid")
        git("config", "user.name", "selftest")
        git("config", "commit.gpgsign", "false")
        (repo / "f.md").write_text("committed\n", encoding="utf-8")
        git("add", "f.md")
        git("commit", "-qm", "f")

        # Changed AND staged: the index and the working copy now both differ from HEAD, so a read
        # of either is distinguishable from a read of the commit.
        (repo / "f.md").write_text("staged, not committed\n", encoding="utf-8")
        git("add", "f.md")

        if committed_blob("f.md", cwd=repo) != "committed\n":
            problems.append("committed_blob returned the index or the working copy, not the blob at HEAD")
        if committed_blob("missing.md", cwd=repo) is not None:
            problems.append("committed_blob invented a blob for a path HEAD does not have")
    return problems


def selftest() -> int:
    """Four directions, plus the positive control that keeps the other four honest.

    A generator whose --check cannot fail is the whole class of defect this repo lints for, so each
    arm is proved by mutating a fixture rather than by trusting the comparison. Two arms were paid
    for: the stray arm because the drift arm passed a hand-copied shipped skill (#1006), and the
    unstaged arm because the check read the working tree and so could not see the one state that
    matters (#1008).

    THE ARMS STUB `committed_blob` RATHER THAN STAGING A REPOSITORY. What is under test is what the
    comparison does with a blob, not how git hands it over — and a real-repository fixture cannot
    run inside `mutation_check.py`'s tempdir, which has no `.git`. There every call would return
    None, every arm would "fail" for that reason alone, and every mutation would read as caught.
    The positive control is what states that out loud: if a clean committed copy does not pass,
    nothing below means anything.
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

    failures.extend(head_read_arm())

    real_blob = globals()["committed_blob"]

    def check_against(blob: str | None) -> int:
        """Run --check with HEAD pretending to hold `blob` for every mirrored path."""
        globals()["committed_blob"] = lambda relative: blob
        try:
            return build(check=True)
        finally:
            globals()["committed_blob"] = real_blob

    # The control FIRST: a clean committed copy must pass, or every arm below passes for free.
    if check_against(rendered) != 0:
        failures.append("--check failed on a clean committed copy — the arms below prove nothing")

    # The drift arm: the committed copy is not what the source renders to.
    if check_against(rendered + "\ndrifted\n") == 0:
        failures.append("--check passed against a committed copy that had been edited")

    # The unstaged arm (#1008): rebuilt on disk, never `git add`ed, so HEAD has no blob. This is
    # the state the working-tree read called clean, and it is the one CI fails on.
    if check_against(None) == 0:
        failures.append("--check passed with the mirror rebuilt on disk but never staged")

    # The stray arm: a copy of a shipped skill that no MIRRORED entry governs, HEAD clean.
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
            if check_against(rendered) == 0:
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
            "selftest: ok — the read really is of HEAD (index and working copy both refused); a "
            "clean committed copy passes; an edited one, an unstaged one and an unregistered copy "
            "of a shipped skill each fail"
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
