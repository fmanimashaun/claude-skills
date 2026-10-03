#!/usr/bin/env python3
"""Git for test fixtures: it can only touch the temp repo it names, and starts nothing in the background.

CANONICAL COPY. Byte-identical copies live in `plugins/qa-flow/scripts/` and `plugins/pipeline/scripts/`
(each plugin installs alone and cannot import another's code); `fixture-git-drift` in
`scripts/lint_self_consistency.py` keeps them identical. Maintainer `scripts/` import this one.

#1588. On 2026-10-03 three empty commits -- author `t <t@t>`, message `m` -- landed on the maintainer's
real `dev` checkout. The user was at the process limit, so `fork()` failed: a fixture's temp repo was
never initialised, and a later `git commit` ran in the INHERITED cwd, which was the real repository.
`GIT_CEILING_DIRECTORIES` cannot stop that (it only stops git walking UP, and the cwd already was a
repo). What stops it is naming the repository exactly: `run()` sets `GIT_DIR` and `GIT_WORK_TREE` to
the temp repo, so git discovers nothing; it refuses a path outside the temp root, and a repo whose
`.git` is missing because its init failed.

#1577. A commit in a fixture repo starts a detached `git maintenance` that can still be writing when the
fixture removes its temp dir (#1493). `maintenance.auto=false` and `gc.auto=0` go in through git's own
environment config, appended to any `GIT_CONFIG_*` pairs already there -- the rules of
`scripts/hermetic_git.py`, which shipped code cannot import.

    fixture_git.init(repo)                       # repo must be inside tempfile.gettempdir()
    fixture_git.run(repo, "commit", "-q", "--allow-empty", "-m", "m")
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false")
SETTINGS: tuple[tuple[str, str], ...] = (("maintenance.auto", "false"), ("gc.auto", "0"))
# THE #1588 CAUSE. git exports GIT_DIR (and the rest of `git rev-parse --local-env-vars`) to every
# hook it runs. A selftest run under a hook inherits it, and `git -C <tmp> commit` then commits into
# $GIT_DIR -- the REAL repository -- while `git init <tmp>` "succeeds" by re-initialising it. Measured:
# the mutation_check_selftest probe, verbatim, under an inherited GIT_DIR wrote `t <t@t>`/`m` into the
# repo it named and left the temp dir with no .git. These are the repository-LOCATING variables of
# that list (git 2.50); the config ones stay, because callers append their own GIT_CONFIG_* pairs.
REPO_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE",
                "GIT_PREFIX", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE")


class NotATempRepo(RuntimeError):
    """Raised instead of letting a fixture's git touch anything but its own temp repo."""


def temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _inside_temp(repo: str | os.PathLike) -> Path:
    path, root = Path(repo).resolve(), temp_root()
    if path == root or root not in path.parents:
        raise NotATempRepo(f"{path} is not inside the temp root {root}: fixture git only touches temp repos (#1588)")
    return path


def hermetic(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """`base` with SETTINGS appended to its GIT_CONFIG_* pairs. A count git would reject is left untouched."""
    out = {k: v for k, v in (os.environ if base is None else base).items() if k not in REPO_LOCATORS}
    count = out.get("GIT_CONFIG_COUNT", "")
    if count and not (count.isascii() and count.isdigit()):
        return out
    start = int(count) if count else 0
    for i, (key, value) in enumerate(SETTINGS, start):
        out[f"GIT_CONFIG_KEY_{i}"] = key
        out[f"GIT_CONFIG_VALUE_{i}"] = value
    out["GIT_CONFIG_COUNT"] = str(start + len(SETTINGS))
    return out


def env(repo: str | os.PathLike, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment for a git command in `repo`: hermetic, and bound to exactly that repository."""
    path = _inside_temp(repo)
    out = hermetic(base)
    out["GIT_DIR"] = str(path / ".git")
    out["GIT_WORK_TREE"] = str(path)
    out["GIT_CEILING_DIRECTORIES"] = str(path.parent)
    return out


def init(repo: str | os.PathLike, *extra: str) -> Path:
    """Create `repo` (inside the temp root) and `git init` it."""
    path = _inside_temp(repo)
    path.mkdir(parents=True, exist_ok=True)
    e = hermetic()
    for key in ("GIT_DIR", "GIT_WORK_TREE"):     # init creates them; never inherit someone else's
        e.pop(key, None)
    subprocess.run(["git", "init", "-q", *extra, str(path)], check=True, env=e, capture_output=True)
    return path


def run(repo: str | os.PathLike, *args: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    """`git <args>` in `repo` and nowhere else. A repo whose init failed is refused, not searched past."""
    path = _inside_temp(repo)
    if not (path / ".git").exists():
        raise NotATempRepo(f"{path} has no .git -- its init failed; refusing rather than letting git find "
                           "another repository (#1588)")
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(["git", *IDENTITY, *args], env=env(path, kw.pop("env", None)), cwd=path,
                          check=check, **kw)


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    def commits(repo: Path) -> str:
        return subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "--all"],
                              capture_output=True, text=True).stdout.strip()

    work = Path(tempfile.mkdtemp(prefix="fixture-git-selftest-"))
    try:
        # A stand-in for the maintainer's real checkout: the repo a misdirected fixture would hit.
        real = work / "real"
        subprocess.run(["git", "init", "-q", str(real)], check=True)
        subprocess.run(["git", "-C", str(real), *IDENTITY, "commit", "-q", "--allow-empty", "-m", "real"], check=True)
        before = commits(real)
        cwd = os.getcwd()
        os.chdir(real)                         # the INHERITED cwd of the incident
        try:
            # 1. THE INCIDENT: the fixture's repo dir exists but its init failed (no .git).
            broken = work / "fixture"
            broken.mkdir()
            raised = None
            try:
                run(broken, "commit", "-q", "--allow-empty", "-m", "m")
            except Exception as e:     # any exception, so a missing refusal FAILS BY NAME instead of crashing
                raised = e
            check("a commit in a repo whose init failed is REFUSED", isinstance(raised, NotATempRepo),
                  f"got {type(raised).__name__ if raised else 'no refusal'}")
            check("...and nothing reaches the repo the cwd sits in", commits(real) == before,
                  f"real repo went from {before} to {commits(real)} commits")
            # 2. The fixture's temp dir was never created at all.
            raised2 = None
            try:
                run(work / "never-created", "commit", "-q", "--allow-empty", "-m", "m")
            except Exception as e:
                raised2 = e
            check("a commit in a repo that does not exist is refused", isinstance(raised2, NotATempRepo),
                  f"got {type(raised2).__name__ if raised2 else 'no refusal'}")
            check("...and still nothing reaches the cwd's repo", commits(real) == before, f"now {commits(real)}")
        finally:
            os.chdir(cwd)
        # 3. A path outside the temp root is refused before git runs.
        for outside in (Path.home() / "fixture-git-never", temp_root()):
            try:
                _inside_temp(outside)
                ok = False
            except NotATempRepo:
                ok = True
            check(f"a path outside the temp root is refused: {outside}", ok, "accepted")
        # 4. CONTROL: a properly initialised temp repo works, and only it changes.
        good = init(work / "good")
        run(good, "commit", "-q", "--allow-empty", "-m", "m")
        check("CONTROL: a commit in an initialised temp repo lands there", commits(good) == "1", f"{commits(good)}")
        check("CONTROL: ...and not in the cwd's repo", commits(real) == before, f"now {commits(real)}")
        # 4b. A stray `-C <elsewhere>` in a caller's arguments cannot leave the temp repo: GIT_DIR binds the
        # repository, and `-C` then only changes the directory git runs in.
        run(good, "-C", str(real), "commit", "-q", "--allow-empty", "-m", "stray", check=False)
        check("a stray -C in the arguments cannot commit into another repo", commits(real) == before,
              f"real repo went from {before} to {commits(real)} commits")
        # 5. #1577: the background-maintenance settings reach git.
        # From a CLEAN base: the mutation harness already exports these settings (scripts/hermetic_git.py),
        # and a check that reads them from the inherited environment passes whatever this module does.
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
        auto = run(good, "config", "--get", "maintenance.auto", env=clean, check=False).stdout.strip()
        check("fixture git runs with maintenance.auto=false (#1577)", auto == "false", f"got {auto!r}")
        bare = hermetic({})
        check("hermetic() on an empty base sets both settings and the count",
              bare.get("GIT_CONFIG_COUNT") == "2" and bare.get("GIT_CONFIG_KEY_0") == "maintenance.auto"
              and bare.get("GIT_CONFIG_KEY_1") == "gc.auto", f"got {bare}")
        # 5b. THE #1588 CAUSE: an inherited GIT_DIR (git exports it to hooks). The probe that wrote the
        # incident's commits, verbatim -- `git init <tmp>` then `git -C <tmp> commit -m m` -- through this
        # module's environment, must not reach the repo that GIT_DIR names.
        poisoned = {**os.environ, "GIT_DIR": str(real / ".git"), "GIT_WORK_TREE": str(real)}
        tmp = work / "probe"
        subprocess.run(["git", "init", "-q", str(tmp)], env=hermetic(poisoned), capture_output=True)
        subprocess.run(["git", "-C", str(tmp), *IDENTITY, "commit", "-q", "--allow-empty", "-m", "m"],
                       env=hermetic(poisoned), capture_output=True)
        check("an inherited GIT_DIR cannot redirect a fixture commit into the repo it names (#1588)",
              commits(real) == before, f"real repo went from {before} to {commits(real)} commits")
        check("...because the hermetic environment drops it", "GIT_DIR" not in hermetic(poisoned), "kept")
        # 6. A malformed GIT_CONFIG_COUNT is left alone, as git would reject it anyway.
        check("a malformed GIT_CONFIG_COUNT is left untouched", hermetic({"GIT_CONFIG_COUNT": "-1"}) ==
              {"GIT_CONFIG_COUNT": "-1"}, "rewritten")
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    print(f"fixture_git selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else 2)
