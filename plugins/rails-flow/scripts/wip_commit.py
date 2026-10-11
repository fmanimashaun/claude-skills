#!/usr/bin/env python3
"""Commit a lane's tracked changes as WIP when a turn ends, so a cut-off session loses at most one turn (#1564).

Run:  wip_commit.py [--root DIR] [--dry-run]        # what the Stop hook runs; the hook's JSON payload on stdin may carry `cwd`
      wip_commit.py --selftest
Exit: always 0 as a hook (an advisory: it fails open, and a missing git, an odd repository or a failed commit is silence, never a blocked
      turn); `--dry-run` prints the decision. `--selftest` exits 1 on a failure.

WHAT IT DOES, in order, and each step has a fixture that goes red without it:
  1. finds `git` itself, from ABSOLUTE `PATH` entries outside the repository (`test_preflight.trusted_which`, the one resolver), never
     by the bare name: a repository's settings can put `./bin` first on `PATH` (#1843);
  2. runs every git command in a SCRUBBED environment: no `GIT_*` at all from the parent (`GIT_CONFIG_*`, `GIT_EXTERNAL_DIFF`,
     `GIT_SSH_COMMAND` and the rest), a one-directory `PATH`, and `-c core.hooksPath=/dev/null -c core.fsmonitor=false`, so no hook, no
     fsmonitor command and no environment-supplied configuration runs;
  3. acts only on a LANE branch: `feature/*` or `fix/*`. Never `main`, `master`, `dev`, a detached HEAD, or `chore/*` (an arm);
  4. acts only when TRACKED files changed (`git add -u`-style: never untracked files, never `git add -A`) and nothing is in progress
     (merge, rebase, cherry-pick, revert, bisect, or an unmerged path);
  5. commits with `--no-verify`, a fixed message `WIP(auto): <branch> <UTC time>` with no closing keyword, and the user's own git identity
     (no identity configured means no commit: it never invents one);
  6. ROLLS: when HEAD is already an unpushed `WIP(auto):` commit it amends that one rather than stacking a commit per turn; once any
     remote-tracking ref contains it, the next change is a new commit (it never rewrites what was pushed);
  7. never pushes, never merges, never touches another branch.

WHY A STOP HOOK AND NOT PreToolUse. A `PreToolUse` hook runs BEFORE the user is asked about the command, under an environment a
project's own settings can set (`docs/evidence/audits/2026-10-11-hook-environment-1843.md`, `...2026-10-10-hook-environment-1821.md`).
Running `git` there would run whatever the repository chose before the user answered. `Stop` runs after the turn the user already
allowed. The #1564 proposal's `PreToolUse[Bash]` WIP commit on `git push`, `gh pr merge` and `gh pr ready` is deliberately not built.

LIMITS. A filter driver or a global hook the USER configured still runs, as it does for any git command they run; this scrubs what a
repository or the environment can add, it does not turn git into a sandbox. It cannot recover work a session lost before the turn ended.
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_preflight import trusted_which  # noqa: E402  (the one resolver for "a tool found outside the repository")

LANE = re.compile(r"^(?:feature|fix)/[^/\s].*$")
MARK = "WIP(auto): "
GIT_TIMEOUT = 20.0
HARD_CONFIG = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false", "-c", "gc.auto=0",
               "-c", "maintenance.auto=false", "-c", "core.pager=cat", "-c", "protocol.ext.allow=never"]
IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-merge", "rebase-apply")


def scrubbed_env(git: str, env=None) -> dict[str, str]:
    """The ONLY environment git runs in: HOME (the user's own gitconfig and identity), a one-directory PATH, a C locale. Nothing else is
    inherited, so no GIT_*, PYTHON*, LD_*, DYLD_*, BASH_ENV or proxy variable of the parent reaches git."""
    env = os.environ if env is None else env
    out = {"PATH": os.path.dirname(git), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    if env.get("HOME"):
        out["HOME"] = env["HOME"]
    return out


def run_git(git: str, root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([git, *HARD_CONFIG, "-C", str(root), *args], env=env, capture_output=True, text=True,
                              timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def decide(root: Path, parent_env=None, now: float | None = None, dry_run: bool = False) -> tuple[str, str]:
    """(action, detail). action is `committed`, `amended`, or a `skip:<why>`; a skip is never an error."""
    parent_env = os.environ if parent_env is None else parent_env
    git = trusted_which("git", parent_env, root)
    if git is None:
        return "skip:no-trusted-git", "no git in an absolute PATH entry outside the repository"
    env = scrubbed_env(git, parent_env)

    def g(*args: str) -> subprocess.CompletedProcess | None:
        return run_git(git, root, env, *args)

    top = g("rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return "skip:not-a-repository", "no repository here"
    toplevel = Path(top.stdout.strip())
    gitdir_out = g("rev-parse", "--git-dir")
    if gitdir_out is None or gitdir_out.returncode != 0:
        return "skip:no-git-dir", "git-dir unreadable"
    gitdir = Path(gitdir_out.stdout.strip())
    if not gitdir.is_absolute():
        gitdir = toplevel / gitdir
    branch = g("symbolic-ref", "--short", "-q", "HEAD")
    if branch is None or branch.returncode != 0 or not branch.stdout.strip():
        return "skip:detached-head", "HEAD is not on a branch"
    name = branch.stdout.strip()
    if not LANE.match(name):
        return "skip:not-a-lane", f"{name!r} is not a feature/* or fix/* lane branch"
    if any((gitdir / marker).exists() for marker in IN_PROGRESS):
        return "skip:operation-in-progress", "a merge, rebase, cherry-pick, revert or bisect is in progress"
    status = g("status", "--porcelain", "--untracked-files=no")
    if status is None or status.returncode != 0:
        return "skip:status-failed", "git status failed"
    lines = [l for l in status.stdout.splitlines() if l.strip()]
    if not lines:
        return "skip:clean", "no tracked change"
    if any(l[:2] in ("UU", "AA", "DD", "AU", "UA", "DU", "UD") for l in lines):
        return "skip:unmerged-paths", "unmerged paths"
    if dry_run:
        return "skip:dry-run", f"{len(lines)} tracked change(s) on {name}"
    stamp = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(now if now is not None else time.time()))
    message = f"{MARK}{name} {stamp}"
    subject = g("log", "-1", "--format=%s")
    head_is_wip = subject is not None and subject.returncode == 0 and subject.stdout.strip().startswith(MARK)
    pushed = True
    if head_is_wip:
        contained = g("for-each-ref", "--contains", "HEAD", "--format=%(refname)", "refs/remotes")
        pushed = contained is None or contained.returncode != 0 or bool(contained.stdout.strip())
    args = ["commit", "-a", "--no-verify", "-q", "-m", message]
    action = "committed"
    if head_is_wip and not pushed:
        args.insert(1, "--amend")
        action = "amended"
    done = g(*args)
    if done is None or done.returncode != 0:
        return "skip:commit-failed", ((done.stderr or "").strip()[:160] if done else "git did not run")
    return action, message


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wip_commit.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = a.root
    if root is None:
        payload = {}
        try:
            if not sys.stdin.isatty():
                payload = json.loads(sys.stdin.read(65536) or "{}")
        except (ValueError, OSError):
            payload = {}
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        root = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    try:
        action, detail = decide(root, dry_run=a.dry_run)
    except Exception as exc:        # an advisory: nothing here may block the turn
        action, detail = "skip:error", str(exc)[:160]
    if a.dry_run:
        print(f"{action}: {detail}")
    return 0


def selftest() -> int:
    import shutil
    import tempfile

    failures: list[str] = []
    checks = [0]

    def expect(label: str, ok: bool, detail: object = "") -> None:
        checks[0] += 1
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    real_git = shutil.which("git")
    if not real_git:
        print("wip_commit selftest: no git on PATH, nothing to test", file=sys.stderr)
        return 2
    git_dir = os.path.dirname(os.path.realpath(real_git))

    with tempfile.TemporaryDirectory() as td:
        base = Path(td).resolve()
        home = base / "home"
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n\tname = Lane Tester\n\temail = lane@example.com\n")
        marker = base / "MARKER"

        def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
            env = {"HOME": str(home), "PATH": git_dir + os.pathsep + "/usr/bin:/bin", "LC_ALL": "C"}
            env.update(extra or {})
            return env

        def git(repo: Path, *args: str, check: bool = True) -> str:
            done = subprocess.run([real_git, "-C", str(repo), *args], env=clean_env(), capture_output=True, text=True)
            if check and done.returncode != 0:
                raise RuntimeError(f"git {args}: {done.stderr}")
            return done.stdout.strip()

        def make_repo(name: str, branch: str = "feature/x") -> Path:
            repo = base / name
            repo.mkdir()
            git(repo, "init", "-q", "-b", "dev")
            (repo / "a.txt").write_text("one\n")
            git(repo, "add", "a.txt")
            git(repo, "commit", "-q", "-m", "base")
            if branch != "dev":
                git(repo, "checkout", "-q", "-b", branch)
            return repo

        def count(repo: Path) -> int:
            return int(git(repo, "rev-list", "--count", "HEAD"))

        def run(repo: Path, env_extra: dict[str, str] | None = None) -> tuple[str, str]:
            return decide(repo, clean_env(env_extra))

        # ---- the happy path, and what it must not take
        repo = make_repo("lane")
        (repo / "a.txt").write_text("two\n")
        (repo / "new.txt").write_text("untracked\n")
        action, detail = run(repo)
        expect("a dirty tracked change on a feature lane is committed", action == "committed" and count(repo) == 2, (action, detail))
        expect("the commit message is WIP(auto) with the branch and no closing keyword",
               git(repo, "log", "-1", "--format=%s").startswith("WIP(auto): feature/x ")
               and not re.search(r"\b(fix(es|ed)?|close[sd]?|resolve[sd]?)\s+#\d", git(repo, "log", "-1", "--format=%B"), re.I),
               git(repo, "log", "-1", "--format=%B"))
        expect("the tracked change is in the commit", git(repo, "show", "HEAD:a.txt") == "two", git(repo, "show", "HEAD:a.txt"))
        expect("an UNTRACKED file is never committed (never `git add -A`)", "new.txt" not in git(repo, "ls-tree", "-r", "--name-only", "HEAD"),
               git(repo, "ls-tree", "-r", "--name-only", "HEAD"))
        expect("the user's own identity signs it", git(repo, "log", "-1", "--format=%an <%ae>") == "Lane Tester <lane@example.com>")
        action, _ = run(repo)
        expect("a clean tracked tree commits nothing", action == "skip:clean" and count(repo) == 2, action)

        # ---- ROLLING: an unpushed WIP commit is amended, a pushed one is not
        (repo / "a.txt").write_text("three\n")
        action, _ = run(repo)
        expect("a second dirty turn AMENDS the unpushed WIP commit instead of stacking", action == "amended" and count(repo) == 2, (action, count(repo)))
        git(repo, "update-ref", "refs/remotes/origin/feature/x", "HEAD")
        (repo / "a.txt").write_text("four\n")
        action, _ = run(repo)
        expect("once a remote-tracking ref contains the WIP commit, the next change is a NEW commit", action == "committed" and count(repo) == 3, (action, count(repo)))
        expect("...and the pushed commit was not rewritten", git(repo, "rev-parse", "origin/feature/x") == git(repo, "rev-parse", "HEAD~1"))

        # ---- branches it must leave alone
        for branch in ("dev", "main", "master", "chore/arm-v1.0.0", "feature", "release/x", "hotfix/y"):
            other = make_repo("b-" + re.sub(r"\W", "_", branch), branch)
            (other / "a.txt").write_text("changed\n")
            action, _ = run(other)
            expect(f"branch {branch!r} is not a lane: nothing committed", action == "skip:not-a-lane" and count(other) == 1, (action, count(other)))
        fixlane = make_repo("fixlane", "fix/1564-thing")
        (fixlane / "a.txt").write_text("changed\n")
        expect("a fix/* lane is committed", run(fixlane)[0] == "committed")
        detached = make_repo("detached")
        git(detached, "checkout", "-q", "--detach")
        (detached / "a.txt").write_text("changed\n")
        expect("a detached HEAD is left alone", run(detached)[0] == "skip:detached-head")

        # ---- operations in progress
        merging = make_repo("merging")
        (merging / ".git" / "MERGE_HEAD").write_text(git(merging, "rev-parse", "HEAD") + "\n")
        (merging / "a.txt").write_text("changed\n")
        expect("a merge in progress is never committed over", run(merging)[0] == "skip:operation-in-progress")

        # ---- HOSTILE ENVIRONMENT (#1843): every row below must leave the marker absent AND still commit
        def hostile(label: str, extra: dict[str, str], setup=None) -> None:
            repo = make_repo("h-" + re.sub(r"\W", "_", label))
            (repo / "bin").mkdir()
            fake = repo / "bin" / "fakegit"
            fake.write_text(f"#!/bin/sh\necho ran >> {marker}\nexec {real_git} \"$@\"\n")
            fake.chmod(0o755)
            if setup:
                setup(repo, fake)
            (repo / "a.txt").write_text("changed\n")
            marker.unlink(missing_ok=True)
            here = os.getcwd()
            os.chdir(repo)          # the hook runs with the project as its working directory: a relative PATH entry means THIS repository
            try:
                action, detail = decide(repo, clean_env({k: v.replace("@REPO@", str(repo)) for k, v in extra.items()}))
            finally:
                os.chdir(here)
            expect(f"hostile: {label}: the marker never ran", not marker.exists(), (action, detail))
            expect(f"hostile: {label}: the lane is still committed", action == "committed", (action, detail))

        hostile("GIT_CONFIG_COUNT core.fsmonitor", {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "@REPO@/bin/fakegit"})
        hostile("GIT_CONFIG_COUNT core.hooksPath", {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "@REPO@/bin"},
                setup=lambda repo, fake: (repo / "bin" / "pre-commit").write_text(f"#!/bin/sh\necho ran >> {marker}\n") or (repo / "bin" / "pre-commit").chmod(0o755))
        def attr_filter(repo: Path, fake: Path) -> None:
            clean = repo / "bin" / "clean"
            clean.write_text(f"#!/bin/sh\necho ran >> {marker}\ncat\n")
            clean.chmod(0o755)
            (repo / ".gitattributes").write_text("*.txt filter=evil\n")
            git(repo, "add", ".gitattributes")
            git(repo, "commit", "-q", "-m", "attributes")

        hostile("a clean filter defined through GIT_CONFIG_COUNT (a -c override cannot name it)",
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "filter.evil.clean", "GIT_CONFIG_VALUE_0": "@REPO@/bin/clean"}, setup=attr_filter)
        hostile("GIT_EXTERNAL_DIFF", {"GIT_EXTERNAL_DIFF": "@REPO@/bin/fakegit"})
        hostile("GIT_SSH_COMMAND", {"GIT_SSH_COMMAND": "@REPO@/bin/fakegit"})
        hostile("GIT_EXEC_PATH", {"GIT_EXEC_PATH": "@REPO@/bin"})
        hostile("GIT_DIR pointing elsewhere", {"GIT_DIR": "/nonexistent-dir"})
        hostile("a relative `./bin` first on PATH", {"PATH": "./bin" + os.pathsep + git_dir},
                setup=lambda repo, fake: fake.rename(repo / "bin" / "git"))
        hostile("an empty PATH entry first", {"PATH": os.pathsep + git_dir},
                setup=lambda repo, fake: fake.rename(repo / "bin" / "git"))
        hostile("an ABSOLUTE PATH entry inside the repository first", {"PATH": "@REPO@/bin" + os.pathsep + git_dir},
                setup=lambda repo, fake: fake.rename(repo / "bin" / "git"))
        hostile("a repository-local hook (.git/hooks/pre-commit and post-commit)", {},
                setup=lambda repo, fake: [((repo / ".git" / "hooks" / n).write_text(f"#!/bin/sh\necho ran >> {marker}\n"),
                                           (repo / ".git" / "hooks" / n).chmod(0o755)) for n in ("pre-commit", "post-commit", "commit-msg")])
        hostile("a repository-local core.fsmonitor in .git/config", {},
                setup=lambda repo, fake: git(repo, "config", "core.fsmonitor", str(fake)))
        hostile("a repository-local core.hooksPath in .git/config", {},
                setup=lambda repo, fake: (git(repo, "config", "core.hooksPath", str(repo / "bin")),
                                          (repo / "bin" / "pre-commit").write_text(f"#!/bin/sh\necho ran >> {marker}\n"),
                                          (repo / "bin" / "pre-commit").chmod(0o755)))
        # no trusted git at all: silence, no commit
        norepo = make_repo("notrusted")
        (norepo / "a.txt").write_text("changed\n")
        action, _ = decide(norepo, {"HOME": str(home), "PATH": "relative/only:" + os.pathsep})
        expect("no git outside the repository means no commit, not a fallback to a bare `git`", action == "skip:no-trusted-git" and count(norepo) == 1, (action, count(norepo)))
        # never pushes
        remote = base / "remote.git"
        subprocess.run([real_git, "init", "-q", "--bare", str(remote)], check=True, env=clean_env())
        pushing = make_repo("pushing")
        git(pushing, "remote", "add", "origin", str(remote))
        (pushing / "a.txt").write_text("changed\n")
        run(pushing)
        expect("it never pushes: the remote has no refs", git(remote, "for-each-ref") == "", git(remote, "for-each-ref"))
        # no identity: no commit
        bare_home = base / "nohome"
        bare_home.mkdir()
        noid = make_repo("noid")
        (noid / "a.txt").write_text("changed\n")
        action, _ = decide(noid, {"HOME": str(bare_home), "PATH": git_dir})
        expect("with no git identity configured it commits nothing and invents none", action == "skip:commit-failed" and count(noid) == 1, (action, count(noid)))
        # the scrub itself
        env = scrubbed_env("/usr/bin/git", {"HOME": "/h", "GIT_CONFIG_COUNT": "1", "PYTHONPATH": "x", "BASH_ENV": "y", "LD_PRELOAD": "z", "PATH": "/p"})
        expect("the scrubbed env keeps only HOME and its own PATH, never a GIT_*, PYTHON*, LD_* or BASH_ENV of the parent",
               env["HOME"] == "/h" and env["PATH"] == "/usr/bin" and not [k for k in env if k.startswith(("PYTHON", "LD_", "BASH_", "DYLD_"))]
               and "GIT_CONFIG_COUNT" not in env, env)
        # the CLI as a hook: stdin payload, exit 0 always
        cli = make_repo("cli")
        (cli / "a.txt").write_text("changed\n")
        done = subprocess.run([sys.executable, str(Path(__file__).resolve())], input=json.dumps({"cwd": str(cli)}), capture_output=True, text=True,
                              env=clean_env({"PYTHONDONTWRITEBYTECODE": "1"}))
        expect("CLI: the hook payload's cwd is honoured and the exit status is 0", done.returncode == 0 and count(cli) == 2, (done.returncode, done.stderr[:200], count(cli)))
        done = subprocess.run([sys.executable, str(Path(__file__).resolve())], input="not json", capture_output=True, text=True,
                              cwd=str(base), env=clean_env())
        expect("CLI: a garbage payload outside any repository still exits 0", done.returncode == 0, (done.returncode, done.stderr[:200]))

    for f in failures:
        print(f"FAIL: {f}")
    print(f"wip_commit selftest: {checks[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
