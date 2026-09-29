#!/usr/bin/env python3
"""Where `design-system` lives — resolved for BOTH layouts, in one place (#617).

WHY THIS EXISTS. design-flow's scripts read doctrine that ships in a different plugin: the
`design-system` skill, bundled in `rails-stack`. Three of them found it by counting `..` hops from
their own file, and that arithmetic is calibrated for the **marketplace clone**:

    <clone>/plugins/design-flow/scripts/x.py   ->  ../../..  ->  <clone>/skills/design-system/

From an **install** — which is what `${CLAUDE_PLUGIN_ROOT}` expands to for everyone who did not
clone — the cache interposes `<plugin>/<version>/`:

    cache/claude-skills/design-flow/1.23.1/scripts/x.py  ->  ../../..  ->  cache/claude-skills/
    actual:                                       cache/claude-skills/rails-stack/1.45.0/skills/…

**The two shapes differ in DEPTH, not in offset**, so no amount of parent-counting reconciles them.
That is substrate fact #4 from `/rails-flow:toolchain-check` wearing different clothes: `rails-stack`
is a skills bundle with **no plugin directory**, so a code plugin and the skills bundle have
genuinely disjoint cache shapes. A resolver assuming one shape covers both is the same mistake as
reading one version source and calling it the version.

WHY IT IS SHARED. One question — *where is the doctrine* — answered in three files is three chances
to answer it differently, and #617 proved they had already drifted apart in style if not in outcome.
`plugin-boundaries` allows this: all three callers are inside design-flow, so this is an intra-plugin
import like `brand_pack_lint`, not a reach across a boundary.

THIS PROJECT'S INSTALL WINS, not the newest in the cache (#1421). Several projects on one machine
run different `rails-stack` versions -- measured: 1.63.0 for fidara-ledger, 1.69.0 for
Retask-platform, both project-scoped in `installed_plugins.json` -- so the newest cached version is
some OTHER project's doctrine. The record rule is the one `toolchain_version.py` uses (#1407): a
record with a `projectPath` applies to that project and its subdirectories, one without applies
everywhere, and the newest `lastUpdated` among those that apply is the one loaded. It is restated
here rather than imported because rails-flow is a different plugin and may not be installed.

The project is `$CLAUDE_PROJECT_DIR`, else the working directory; for a linked git worktree its main
checkout is compared too, since the install may be recorded against either. NEWEST VERSION WINS survives only as
the fallback when `installed_plugins.json` is unreadable or no record applies -- the behaviour
before #1421, so a layout this cannot place resolves no worse than it did.

Stdlib only, no network.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SKILL_REL = Path("skills") / "design-system"


def _version_key(name: str) -> tuple:
    """Sort `1.45.0` above `1.9.0`. String order would not — and picks the stale one."""
    parts = re.findall(r"\d+", name)
    return tuple(int(p) for p in parts) if parts else (0,)


def _project() -> Path:
    """The path this session runs in: `$CLAUDE_PROJECT_DIR`, else the working directory."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _main_checkout(project: Path) -> Path:
    """`project`, or its main checkout when it lies inside a linked git worktree.

    A worktree's `.git` is a FILE, `gitdir: <main>/.git/worktrees/<name>`. A submodule's names
    `.git/modules/<name>` instead and is deliberately NOT mapped: it is its own project.
    """
    for d in (project, *project.parents):
        git = d / ".git"
        if git.is_dir():
            return project
        if git.is_file():
            try:
                line = git.read_text(encoding="utf-8").strip()
            except OSError:
                return project
            gitdir = Path(line.partition("gitdir:")[2].strip())
            if not gitdir.is_absolute():
                gitdir = d / gitdir
            return gitdir.parent.parent.parent if gitdir.parent.name == "worktrees" else project
    return project


def _applies(record: dict, project: Path) -> bool:
    """`toolchain_version.applies_to`'s rule (#1407), restated: design-flow cannot import rails-flow."""
    owner = (record or {}).get("projectPath")
    if not owner:
        return True
    try:
        # BOTH the session's path and its main checkout: a record made inside a worktree names the
        # worktree, one made from the main checkout names that, and either is this project.
        root, sessions = Path(owner).resolve(), {project.resolve(), _main_checkout(project).resolve()}
    except OSError:
        return False
    # A subdirectory still loads its project's plugins.
    dirs = tuple(d for here in sessions for d in (here, *here.parents))
    if root in dirs:
        return True
    # On a case-insensitive volume (APFS by default) a recorded `projectPath` may differ from the
    # working directory in case alone; `samefile` asks the filesystem instead of comparing strings.
    try:
        return root.exists() and any(str(d).lower() == str(root).lower() and os.path.samefile(root, d)
                                       for d in dirs)
    except OSError:
        return False


def project_install(base: Path, project: Path) -> Path | None:
    """This project's `rails-stack` installPath from `installed_plugins.json`, or None.

    `base` is the marketplace's cache directory (`<plugins>/cache/<marketplace>`), so the record
    file is two levels up and the key is `rails-stack@<marketplace>`. None means "cannot tell",
    and the caller falls back to the glob.
    """
    try:
        data = json.loads((base.parent.parent / "installed_plugins.json").read_text(encoding="utf-8"))
        records = data["plugins"][f"rails-stack@{base.name}"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(records, list):
        return None
    mine = [r for r in records if isinstance(r, dict) and r.get("installPath") and _applies(r, project)]
    if not mine:
        return None
    return Path(max(mine, key=lambda r: r.get("lastUpdated") or "")["installPath"])


def candidates(script: Path) -> list[Path]:
    """Every place the skill can live, in the order to try: the clone, then THIS project's install
    (#1421), then every cached version, newest down, as the fallback.

    `base` is the marketplace root in BOTH layouts, which is what makes one function able to serve
    them: they diverge only by the `<bundle>/<version>/` segments the cache adds.
    """
    base = Path(script).resolve().parent.parent.parent.parent
    mine = project_install(base, _project())
    if mine is not None:
        return [base / SKILL_REL, mine / SKILL_REL]
    installed = sorted(
        (p for p in base.glob(str(Path("*") / "*" / SKILL_REL)) if p.is_dir()),
        key=lambda p: _version_key(p.parent.parent.name), reverse=True)
    return [base / SKILL_REL, *installed]


def find(script: Path) -> Path | None:
    """The `design-system` directory, or None. Callers REFUSE on None rather than degrading."""
    for candidate in candidates(script):
        if candidate.is_dir():
            return candidate
    return None


def describe(script: Path) -> str:
    """Every root tried, for an error message.

    Naming ONE path made #617 read as *"the catalogue is missing"* when the truth was *"I looked in
    the wrong place"* — so a reporter checked that path, found nothing, and reasonably concluded
    their `rails-stack` install was broken. A message that lists what it tried is self-diagnosing.
    """
    return "\n".join(f"    - {c}" for c in candidates(script))


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    # THE INSTALLED LAYOUT — the one no fixture exercised until #617, which is why a bug that broke
    # every user could sit behind a green suite. Built as a real tree, because the defect was in how
    # a filesystem is actually shaped.
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "cache" / "claude-skills"
        scripts = cache / "design-flow" / "1.23.1" / "scripts"
        scripts.mkdir(parents=True)
        for ver in ("1.9.0", "1.45.0"):
            (cache / "rails-stack" / ver / SKILL_REL / "references").mkdir(parents=True)
        got = find(scripts / "x.py")
        check("the installed layout resolves", got is not None)
        check(f"...newest version wins (got {got.parent.parent.name if got else None})",
              got is not None and got.parent.parent.name == "1.45.0")
        check("...and the clone root is tried first",
              candidates(scripts / "x.py")[0] == (cache / SKILL_REL).resolve())
        check("every root is named for an error message",
              describe(scripts / "x.py").count("- ") >= 2)

    # THIS PROJECT'S INSTALL, not the newest (#1421). Two projects, two versions, one cache: each
    # project must read its own, and fidara-ledger's older 1.63.0 must not lose to 1.69.0.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        plugins = root / "plugins"
        cache = plugins / "cache" / "claude-skills"
        scripts = cache / "design-flow" / "1.42.1" / "scripts"
        scripts.mkdir(parents=True)
        for ver in ("1.63.0", "1.69.0"):
            (cache / "rails-stack" / ver / SKILL_REL).mkdir(parents=True)
        old, new = root / "old-project", root / "new-project"
        (old / "app").mkdir(parents=True)
        new.mkdir()
        # No `.git` here: the project root is then the working directory itself, so the
        # subdirectory fixture below reaches the projectPath rule instead of the git walk.
        rec = lambda ver, proj, when: {"scope": "project", "version": ver, "projectPath": str(proj),
                                       "installPath": str(cache / "rails-stack" / ver),
                                       "lastUpdated": when}
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "rails-stack@claude-skills": [rec("1.63.0", old, "2026-09-22T00:00:00Z"),
                                          rec("1.69.0", new, "2026-09-29T00:00:00Z")]}}))
        saved = os.environ.get("CLAUDE_PROJECT_DIR")
        try:
            def found_for(project):
                os.environ["CLAUDE_PROJECT_DIR"] = str(project)
                got = find(scripts / "x.py")
                return got.parent.parent.name if got else None
            check(f"the older project reads its own install (got {found_for(old)})",
                  found_for(old) == "1.63.0")
            check(f"the newer project reads its own install (got {found_for(new)})",
                  found_for(new) == "1.69.0")
            check(f"a subdirectory reads its project's install (got {found_for(old / 'app')})",
                  found_for(old / "app") == "1.63.0")
            # A linked worktree lives elsewhere; its `.git` FILE names the main checkout.
            wt = root / "old-project-wt"
            wt.mkdir()
            (wt / ".git").write_text(f"gitdir: {old / '.git' / 'worktrees' / 'wt'}\n")
            check(f"a linked worktree reads its main checkout's install (got {found_for(wt)})",
                  found_for(wt) == "1.63.0")
            # A record made from INSIDE the worktree names the worktree itself; mapping the session
            # to its main checkout must not stop it matching (#1474's review of the same rule).
            records = json.loads((plugins / "installed_plugins.json").read_text())
            (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
                "rails-stack@claude-skills": [rec("1.63.0", wt, "2026-09-22T00:00:00Z")]}}))
            check(f"a record naming the worktree itself applies in it (got {found_for(wt)})",
                  found_for(wt) == "1.63.0")
            (plugins / "installed_plugins.json").write_text(json.dumps(records))
            # Case alone differs. `samefile` is replaced by a case-folding stand-in so this runs on
            # CI's Linux runner too, which does not fold case, rather than only on APFS.
            real_samefile = os.path.samefile
            os.path.samefile = lambda a, b: str(a).lower() == str(b).lower()
            try:
                got_upper = found_for(root / "OLD-PROJECT")
            finally:
                os.path.samefile = real_samefile
            check(f"a projectPath differing only in case still applies (got {got_upper})",
                  got_upper == "1.63.0")
            other = root / "unrecorded"
            other.mkdir()
            check(f"a project with no record falls back to the newest (got {found_for(other)})",
                  found_for(other) == "1.69.0")
            (plugins / "installed_plugins.json").write_text("{not json")
            check(f"an unreadable record file falls back to the newest (got {found_for(old)})",
                  found_for(old) == "1.69.0")
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = saved

    # THE CLONE LAYOUT still resolves — the regression this fix must not cause.
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        (clone / "plugins" / "design-flow" / "scripts").mkdir(parents=True)
        (clone / SKILL_REL / "references").mkdir(parents=True)
        got = find(clone / "plugins" / "design-flow" / "scripts" / "x.py")
        check("the clone layout resolves", got == (clone / SKILL_REL).resolve())

    # NOTHING FOUND is None, never a guess. A caller that got a plausible-looking path would read
    # doctrine that is not there and report zero findings.
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "a" / "b" / "c" / "scripts"
        empty.mkdir(parents=True)
        check("an unresolvable tree returns None", find(empty / "x.py") is None)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} doctrine-path assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
