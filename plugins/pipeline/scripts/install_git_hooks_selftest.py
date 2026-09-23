#!/usr/bin/env python3
"""Selftest: install-git-hooks.sh installs a hook that GIT ACTUALLY RUNS.

The installer used to write `$(git rev-parse --git-dir)/hooks/post-merge`. That is where git runs
hooks in a plain clone and nowhere else: a repo that sets `core.hooksPath` never reads `.git/hooks`,
and a linked worktree's `--git-dir` is `.git/worktrees/<name>`, whose `hooks/` git never reads
either. In both cases the installer printed "installed", the file existed, and the QA-verify nudge
never fired. It went unnoticed for days on a project that sets `core.hooksPath .githooks`.

So every positive check here is a real merge on the dev branch followed by a look for the marker
the hook writes. "The file exists where we expected" is exactly the assertion that passed over
the defect, and none of these checks relies on it.

Global and system git config are isolated: a maintainer with a personal `core.hooksPath` would
otherwise redirect the "plain clone" case and make it measure their machine.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "install-git-hooks.sh"
MARKER = "# >>> pipeline-nudge >>>"

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k not in {"HOME", "XDG_CONFIG_HOME"}}
    gc = home / "gitconfig"
    gc.write_text("")
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL=str(gc), GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return env


def git(cwd: Path, env: dict[str, str], *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {r.stderr.strip()}")
    return r.stdout.strip()


def install(cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True)


def repo(root: Path, env: dict[str, str], name: str = "r", dev_checked_out: bool = True) -> Path:
    r = root / name
    r.mkdir()
    git(r, env, "init", "-q", "-b", "main")
    (r / "README").write_text("x\n")
    git(r, env, "add", "README")
    git(r, env, "commit", "-q", "-m", "init")
    git(r, env, "branch", "dev")
    git(r, env, "branch", "feature", "dev")
    if dev_checked_out:
        git(r, env, "checkout", "-q", "dev")
    return r


def commit_on_feature(r: Path, env: dict[str, str]) -> None:
    here = git(r, env, "branch", "--show-current")
    git(r, env, "checkout", "-q", "feature")
    (r / "f").write_text("f\n")
    git(r, env, "add", "f")
    git(r, env, "commit", "-q", "-m", "feature work")
    git(r, env, "checkout", "-q", here)


def pending(cwd: Path, env: dict[str, str]) -> Path:
    gd = Path(git(cwd, env, "rev-parse", "--git-dir"))
    return (gd if gd.is_absolute() else cwd / gd) / "pipeline-pending"


def merge_fires(cwd: Path, env: dict[str, str], label: str) -> None:
    """Install, merge feature into dev, and require the hook's marker to appear."""
    _tick()
    marker_file = pending(cwd, env)
    if marker_file.exists():
        FAILURES.append(f"{label}: the marker existed BEFORE the merge, so its presence after "
                        "would prove nothing")
        return
    res = install(cwd, env)
    if res.returncode != 0:
        FAILURES.append(f"{label}: the installer exited {res.returncode}: {res.stdout.strip()}")
        return
    git(cwd, env, "merge", "--no-ff", "-q", "-m", "merge feature", "feature")
    if not marker_file.exists():
        FAILURES.append(f"{label}: a real merge on dev did not fire the nudge — the hook was "
                        f"installed where git does not run it (installer said: "
                        f"{res.stdout.strip()!r})")


def run() -> int:
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)

        # 1. A plain clone. The case the old code got right — the control for the two it did not.
        home = base / "h1"; home.mkdir(); env = _env(home)
        r = repo(base, env, "plain")
        commit_on_feature(r, env)
        merge_fires(r, env, "plain clone: a real merge fires the nudge")

        # 2. core.hooksPath pointing at a COMMITTED directory, as Retask-platform does.
        home = base / "h2"; home.mkdir(); env = _env(home)
        r = repo(base, env, "hookspath")
        (r / ".githooks").mkdir()
        (r / ".githooks" / "pre-push").write_text("#!/usr/bin/env bash\nexit 0\n")
        git(r, env, "add", ".githooks/pre-push")
        git(r, env, "commit", "-q", "-m", "team hook")
        git(r, env, "config", "core.hooksPath", ".githooks")
        commit_on_feature(r, env)
        merge_fires(r, env, "core.hooksPath: a real merge fires the nudge")

        _tick()
        status = git(r, env, "status", "--porcelain")
        if ".githooks/post-merge" in status:
            FAILURES.append("core.hooksPath: the installed hook stays out of git status — it shows "
                            f"as {status!r}, so a routine `git add` commits one machine's local nudge")

        # 3. A linked worktree with no hooksPath. `--git-dir` there is .git/worktrees/<name>.
        home = base / "h3"; home.mkdir(); env = _env(home)
        r = repo(base, env, "wtmain", dev_checked_out=False)
        commit_on_feature(r, env)
        wt = base / "wt"
        git(r, env, "worktree", "add", "-q", str(wt), "dev")
        merge_fires(wt, env, "linked worktree: a real merge fires the nudge")

        # 4. A TRACKED post-merge under core.hooksPath is the team's; the installer must not touch it.
        home = base / "h4"; home.mkdir(); env = _env(home)
        r = repo(base, env, "tracked")
        (r / ".githooks").mkdir()
        team = "#!/usr/bin/env bash\necho team post-merge\n"
        (r / ".githooks" / "post-merge").write_text(team)
        git(r, env, "add", ".githooks/post-merge")
        git(r, env, "commit", "-q", "-m", "team post-merge")
        git(r, env, "config", "core.hooksPath", ".githooks")
        res = install(r, env)
        _tick()
        after = (r / ".githooks" / "post-merge").read_text()
        if res.returncode == 0 or after != team or git(r, env, "status", "--porcelain"):
            FAILURES.append("a tracked hook is never modified — the installer "
                            f"exited {res.returncode} and the committed hook "
                            f"{'CHANGED' if after != team else 'is unchanged'}; editing a shared, "
                            "committed hook from a local nudge dirties every clone that runs it")

        # 5. Re-running is idempotent: one managed block, not two.
        home = base / "h5"; home.mkdir(); env = _env(home)
        r = repo(base, env, "twice")
        install(r, env); install(r, env)
        _tick()
        hook = Path(git(r, env, "rev-parse", "--git-path", "hooks"))
        hook = (hook if hook.is_absolute() else r / hook) / "post-merge"
        n = hook.read_text().count(MARKER)
        if n != 1:
            FAILURES.append(f"re-running the installer is idempotent — found {n} managed blocks")

        # 6. An existing, untracked, non-managed hook is backed up and preserved, not clobbered.
        home = base / "h6"; home.mkdir(); env = _env(home)
        r = repo(base, env, "existing")
        hooks = r / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "post-merge").write_text("#!/usr/bin/env bash\necho mine\n")
        install(r, env)
        _tick()
        text = (hooks / "post-merge").read_text()
        bak = hooks / "post-merge.pre-pipeline.bak"
        if "echo mine" not in text or MARKER not in text or not bak.exists():
            FAILURES.append("an existing non-managed hook is backed up and preserved — "
                            f"original kept: {'echo mine' in text}, block added: {MARKER in text}, "
                            f"backup written: {bak.exists()}")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"install-git-hooks selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
