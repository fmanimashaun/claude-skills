#!/usr/bin/env python3
"""Selftest: the git shim (#1790) refuses the commands that destroy work, by what git is ASKED TO DO and not by how it was spelled.

Every check runs the shim as `git` on a real PATH against a real repository and then looks at what MOVED: a dirty file still dirty, an
untracked file still there, nothing staged, `HEAD` unmoved. "It exited 1" is not the assertion. Every refusal has a near-miss that must
still run, so a shim that refuses everything fails here too; and the SessionStart hook that puts the shim first on PATH is run for real.

    python3 git_shim_selftest.py               # all cases
    python3 git_shim_selftest.py --match NAME  # only the cases whose label contains NAME (the mutation runner uses this)

Global and system git config are isolated: a maintainer's own aliases or `core.hooksPath` would otherwise change what is measured.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

PLUGIN = Path(__file__).resolve().parent.parent
SHIM_DIR = PLUGIN / "git-shim"
HOOK = PLUGIN / "hooks" / "scripts" / "session-start.sh"
REAL_GIT = shutil.which("git") or "/usr/bin/git"

FAILURES: list[str] = []
CHECKS = 0
CASES: list[tuple[str, object]] = []


def case(label: str):
    def register(fn):
        CASES.append((label, fn))
        return fn
    return register


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}" if detail else label)


class Repo:
    """A repository with a tracked dirty file, a tracked subdirectory, and untracked strays; `g()` runs the SHIM as `git`."""

    def __init__(self, base: Path, name: str, shim_dir: Path | None = None):
        self.base = base
        self.work = base / name
        home = base / f"{name}-home"; home.mkdir()
        gc = home / "gitconfig"; gc.write_text("")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RAILS_FLOW_")) and k not in {"HOME", "XDG_CONFIG_HOME"}}
        # NO GIT_CONFIG_* here: the shim refuses a command run with one (they can define aliases and hooks it cannot see), so the home directory isolates.
        self.env.update(HOME=str(home), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",  # fixture-git: exempt (the shim under test finds the repository from its cwd; fixture_git's GIT_DIR binding would hide that)
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", GIT_TERMINAL_PROMPT="0", GIT_EDITOR=":")  # fixture-git: exempt (the shim under test finds the repository from its cwd; fixture_git's GIT_DIR binding would hide that)
        fixture_git.init(self.work, "-b", "main")
        self.real("config", "commit.gpgsign", "false"); self.real("config", "maintenance.auto", "false"); self.real("config", "gc.auto", "0")
        self.write("a.txt", "one\n"); self.write("src/b.txt", "b\n")
        self.real("add", "a.txt", "src/b.txt"); self.real("commit", "-q", "-m", "init")
        self.real("branch", "other")
        self.write("a.txt", "dirty\n"); self.write("u.txt", "stray\n"); self.write("src/c.txt", "stray2\n"); self.write("--all", "a file named like an option\n")
        shim = shim_dir or SHIM_DIR
        self.path_env = dict(self.env, PATH=f"{shim}{os.pathsep}{os.environ['PATH']}")

    def write(self, rel: str, text: str) -> None:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def real(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([REAL_GIT, *args], cwd=cwd or self.work, env=fixture_git.hermetic(self.env), capture_output=True, text=True)

    def g(self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None, stdin: str = "") -> subprocess.CompletedProcess:
        e = dict(self.path_env)
        e.update(env or {})
        return subprocess.run(["git", *args], cwd=cwd or self.work, env=e, capture_output=True, text=True, input=stdin, timeout=20)

    def snapshot(self) -> tuple:
        status = self.real("status", "--porcelain=v1", "-uall").stdout
        return (self.real("rev-parse", "HEAD").stdout.strip(), self.real("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), status,
                (self.work / "a.txt").read_text(), (self.work / "u.txt").exists(), (self.work / "src" / "c.txt").exists(),
                self.real("diff", "--cached", "--name-only").stdout)


def refused(repo: Repo, label: str, *args: str, cwd: Path | None = None, why: str = "") -> None:
    before = repo.snapshot()
    p = repo.g(*args, cwd=cwd)
    after = repo.snapshot()
    check(label, p.returncode != 0 and "git-shim" in p.stderr and after == before,
          f"`git {' '.join(args)}`: exit {p.returncode}, {'unchanged' if after == before else 'THE REPOSITORY CHANGED'}: {p.stderr.strip()[:140]}")
    if why:
        check(label, why in p.stderr, f"`git {' '.join(args)}` is refused for the wrong reason: {p.stderr.strip()[:200]}")


def runs(repo: Repo, label: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    p = repo.g(*args, cwd=cwd)
    check(label, p.returncode == 0 and "git-shim" not in p.stderr, f"`git {' '.join(args)}`: exit {p.returncode}: {p.stderr.strip()[:160]}")
    return p


@case("shim: add --all and every prefix of it is refused and nothing is staged")
def _(base):
    label = "shim: add --all and every prefix of it is refused and nothing is staged"
    r = Repo(base, "addall")
    for args in (("add", "-A"), ("add", "--all"), ("add", "--al"), ("add", "--a"), ("add", "-vA"), ("add", "-Av"), ("add", "-A", "a.txt")):
        refused(r, label, *args, why="stages every change")


@case("shim: add of the repository root is refused in every spelling")
def _(base):
    label = "shim: add of the repository root is refused in every spelling"
    r = Repo(base, "addroot")
    for args in (("add", "."), ("add", "./."), ("add", "src/.."), ("add", ":/"), ("add", ":(top)"), ("add", ":(top)."), ("add", "*"), ("add", "**"),
                 ("add", "--", "."), ("add", "a.txt", "."), ("add", str(r.work.resolve())), ("add", ":/.")):
        refused(r, label, *args, why="plain relative paths")
    refused(r, label, "-C", str(r.work), "add", ".", cwd=base, why="plain relative paths")


@case("shim: a pathspec that is not a plain relative path is refused (absolute, magic, glob, a file list)")
def _(base):
    label = "shim: a pathspec that is not a plain relative path is refused (absolute, magic, glob, a file list)"
    r = Repo(base, "plain")
    (r.work / "list.txt").write_text("a.txt\n")
    for args in (("add", str(r.work / "a.txt")), ("add", "/etc/hosts"), ("add", ":(exclude)u.txt", "a.txt"), ("add", ":!u.txt"), ("add", "*.txt"), ("add", "src/*"),
                 ("add", "a.t?t"), ("add", "[a].txt"), ("add", "--pathspec-from-file=list.txt"), ("add", "--pathspec-from-file", "list.txt"),
                 ("checkout", "--", "*.txt"), ("restore", "*.txt"), ("add", "../outside")):
        refused(r, label, *args, why="cannot be judged" if "pathspec-from-file" in " ".join(args) else "plain relative paths")
    runs(r, label, "add", "a.txt", "src/b.txt")


@case("shim: --no-<option> negates a dry run, and a dry run counts only while it is still in force")
def _(base):
    label = "shim: --no-<option> negates a dry run, and a dry run counts only while it is still in force"
    r = Repo(base, "negate")
    for args in (("add", "-n", "--no-dry-run", "."), ("add", "--dry-run", "--no-dry-run", "-A"), ("add", "-n", "--no-dry", "."),
                 ("clean", "-n", "--no-dry-run", "-f"), ("clean", "-nf", "--no-dry-run")):
        refused(r, label, *args)
    runs(r, label, "add", "--no-dry-run", "-n", "-A")
    runs(r, label, "clean", "--no-dry-run", "-nf")
    check(label, (r.work / "u.txt").exists(), "a dry run deleted a file")
    r.real("add", "a.txt")
    runs(r, label, "commit", "--no-verify", "--verify", "-m", "x")
    check(label, r.real("log", "-1", "--format=%s").stdout.strip() == "x", "commit --no-verify --verify should run as a verified commit")
    r.write("a.txt", "again\n"); r.real("add", "a.txt")
    refused(r, label, "commit", "--verify", "--no-verify", "-m", "y")


@case("shim: add near-misses run and stage only what was named")
def _(base):
    label = "shim: add near-misses run and stage only what was named"
    r = Repo(base, "addok")
    runs(r, label, "add", "a.txt")
    check(label, r.real("diff", "--cached", "--name-only").stdout.split() == ["a.txt"], "add a.txt staged something else")
    r.real("reset", "-q")
    runs(r, label, "add", "src/")
    check(label, sorted(r.real("diff", "--cached", "--name-only").stdout.split()) == ["src/c.txt"], "add src/ staged something else")
    r.real("reset", "-q")
    runs(r, label, "add", "-u")
    check(label, r.real("diff", "--cached", "--name-only").stdout.split() == ["a.txt"], "add -u should stage the tracked change only")
    r.real("reset", "-q")
    runs(r, label, "add", "-n", ".")
    runs(r, label, "add", "--dry-run", ".")
    check(label, r.real("diff", "--cached", "--name-only").stdout == "", "a dry run staged something")
    runs(r, label, "add", "-u", ".")
    r.real("reset", "-q")
    runs(r, label, "add", "--", "--all")
    check(label, "--all" in r.real("diff", "--cached", "--name-only").stdout, "a FILE named --all after -- was not added")
    r.real("reset", "-q")
    runs(r, label, "add", ".", cwd=r.work / "src")
    staged = sorted(r.real("diff", "--cached", "--name-only").stdout.split())
    check(label, staged == ["src/c.txt"], f"`add .` from a subdirectory should stage only that subdirectory: {staged}")


@case("shim: reset --hard and its prefixes are refused and the work survives")
def _(base):
    label = "shim: reset --hard and its prefixes are refused and the work survives"
    r = Repo(base, "reset")
    for args in (("reset", "--hard"), ("reset", "--ha"), ("reset", "--har"), ("reset", "--hard", "HEAD~0"), ("reset", "-q", "--hard")):
        refused(r, label, *args, why="destroys uncommitted work")


@case("shim: reset near-misses run")
def _(base):
    label = "shim: reset near-misses run"
    r = Repo(base, "resetok")
    r.real("add", "a.txt")
    runs(r, label, "reset", "--soft", "HEAD")
    runs(r, label, "reset", "--mixed")
    runs(r, label, "reset", "-q")
    check(label, (r.work / "a.txt").read_text() == "dirty\n", "a soft or mixed reset changed the file")
    r.real("add", "a.txt")
    runs(r, label, "reset", "HEAD", "a.txt")
    check(label, r.real("diff", "--cached", "--name-only").stdout == "", "reset HEAD a.txt did not unstage")


@case("shim: checkout and switch that discard work are refused")
def _(base):
    label = "shim: checkout and switch that discard work are refused"
    r = Repo(base, "checkout")
    for args in (("checkout", "-f"), ("checkout", "--force"), ("checkout", "--fo"), ("checkout", "-f", "other"), ("checkout", "."), ("checkout", "--", "."),
                 ("checkout", "HEAD", "--", "."), ("checkout", ":/"), ("checkout", "-q", "."), ("switch", "-f", "other"),
                 ("switch", "--force", "other"), ("switch", "--discard-changes", "other"), ("switch", "--disc", "other")):
        refused(r, label, *args)


@case("shim: checkout and switch near-misses run")
def _(base):
    label = "shim: checkout and switch near-misses run"
    r = Repo(base, "checkoutok")
    runs(r, label, "checkout", "-b", "feature")
    check(label, r.real("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature", "checkout -b did not switch")
    runs(r, label, "checkout", "other")
    runs(r, label, "switch", "-c", "x")
    runs(r, label, "switch", "main")
    runs(r, label, "checkout", "--", "src/b.txt")
    check(label, (r.work / "a.txt").read_text() == "dirty\n", "checkout of one path touched another file")


@case("shim: restore of the working tree root is refused, and restore --staged passes")
def _(base):
    label = "shim: restore of the working tree root is refused, and restore --staged passes"
    r = Repo(base, "restore")
    for args in (("restore", "."), ("restore", ":/"), ("restore", "--worktree", "."), ("restore", "--source=HEAD", "."), ("restore", "-SW", "."),
                 ("restore", "--staged", "--worktree", "."), ("restore", "-W", ".")):
        refused(r, label, *args, why="plain relative paths")
    r.real("add", "a.txt")
    runs(r, label, "restore", "--staged", ".")
    check(label, r.real("diff", "--cached", "--name-only").stdout == "" and (r.work / "a.txt").read_text() == "dirty\n",
          "restore --staged . should unstage and leave the file as it was")
    r.real("add", "a.txt")
    runs(r, label, "restore", "-S", ".")
    runs(r, label, "restore", "a.txt")
    check(label, (r.work / "a.txt").read_text() == "one\n", "restore a.txt (one named path) did not restore it")


@case("shim: stash drop and clear, checkout-index -f, read-tree --reset -u and rm of the root are refused")
def _(base):
    label = "shim: stash drop and clear, checkout-index -f, read-tree --reset -u and rm of the root are refused"
    r = Repo(base, "more")
    r.real("stash", "push", "-m", "saved")
    r.write("a.txt", "dirty again\n")
    for args in (("stash", "drop"), ("stash", "clear"), ("stash", "-q", "drop"), ("checkout-index", "-f", "a.txt"), ("checkout-index", "--force", "-a"),
                 ("checkout-index", "--fo", "-a"), ("read-tree", "--reset", "-u", "HEAD"), ("read-tree", "-u", "--reset", "HEAD"), ("read-tree", "--res", "-u", "HEAD"),
                 ("rm", "-r", "."), ("rm", "-rf", "."), ("rm", "-r", "--", "."), ("rm", "-r", "*"), ("rm", "-rf", "src/..")):
        refused(r, label, *args)
    check(label, r.real("stash", "list").stdout.strip() != "", "the stash was dropped")
    runs(r, label, "stash", "list")
    runs(r, label, "read-tree", "--reset", "HEAD")
    p = r.g("rm", "-n", "-r", ".")                                   # a dry run: the shim lets it through (git may still complain about a dirty file)
    check(label, "git-shim" not in p.stderr, f"`git rm -n -r .` was refused by the shim: {p.stderr.strip()[:140]}")
    runs(r, label, "rm", "--cached", "-r", "src")
    check(label, (r.work / "src" / "b.txt").exists(), "rm --cached deleted a file from disk")
    r.real("add", "src/b.txt")
    runs(r, label, "rm", "-r", "src")
    check(label, not (r.work / "src" / "b.txt").exists(), "rm -r src (a named path) did not remove it")
    runs(r, label, "stash", "push", "-m", "drop")                  # a message that says drop
    q = r.g("rm", "--cached", "-r", ".")                           # index only: the shim must let even the root through with --cached
    check(label, "git-shim" not in q.stderr and (r.work / "a.txt").exists(), f"`git rm --cached -r .` was refused or deleted a file: {q.stderr.strip()[:140]}")


@case("shim: with no tr or dirname on PATH it still refuses and still passes the rest through")
def _(base):
    label = "shim: with no tr or dirname on PATH it still refuses and still passes the rest through"
    r = Repo(base, "bare-path")
    only = base / "only-git"
    only.mkdir()
    (only / "git").symlink_to(REAL_GIT)
    (only / "bash").symlink_to(shutil.which("bash") or "/bin/bash")     # the shebang is `env bash`; tr and dirname are what is missing
    r.path_env = dict(r.env, PATH=f"{SHIM_DIR}{os.pathsep}{only}")
    for tool in ("tr", "dirname"):
        check(label, shutil.which(tool, path=r.path_env["PATH"]) is None, f"{tool} is still on the test PATH")
    refused(r, label, "reset", "--hard")
    refused(r, label, "-c", "core.hooksPath=/dev/null", "status")
    p = r.g("status", "--porcelain")
    check(label, p.returncode == 0 and "a.txt" in p.stdout, f"status through the shim with a bare PATH: exit {p.returncode}: {p.stderr.strip()[:140]}")


@case("shim: clean --force in every spelling is refused and the strays survive")
def _(base):
    label = "shim: clean --force in every spelling is refused and the strays survive"
    r = Repo(base, "clean")
    for args in (("clean", "-f"), ("clean", "-fd"), ("clean", "-xdf"), ("clean", "-fdx"), ("clean", "--force"), ("clean", "--for"), ("clean", "-ff"),
                 ("clean", "-d", "-f"), ("clean", "-f", "u.txt")):
        refused(r, label, *args, why="deletes untracked files")


@case("shim: clean dry runs pass, and a bare clean is refused when requireForce is off")
def _(base):
    label = "shim: clean dry runs pass, and a bare clean is refused when requireForce is off"
    r = Repo(base, "cleanok")
    runs(r, label, "clean", "-n")
    runs(r, label, "clean", "-nfd")
    runs(r, label, "clean", "--dry-run", "-f")
    runs(r, label, "clean", "-nd")
    check(label, (r.work / "u.txt").exists(), "a dry run deleted a file")
    r.real("config", "clean.requireForce", "false")
    refused(r, label, "clean", "-d", why="clean.requireForce=false")
    runs(r, label, "clean", "-n")


@case("shim: --no-verify in every spelling is refused and nothing is committed")
def _(base):
    label = "shim: --no-verify in every spelling is refused and nothing is committed"
    r = Repo(base, "noverify")
    r.real("add", "a.txt")
    for args in (("commit", "--no-verify", "-m", "x"), ("commit", "-n", "-m", "x"), ("commit", "--no-v", "-m", "x"), ("commit", "-nm", "x"),
                 ("commit", "-anm", "x"), ("commit", "-m", "x", "--no-verify"), ("push", "--no-verify", "origin", "main"),
                 ("merge", "--no-verify", "other"), ("rebase", "--no-verify", "other"), ("pull", "--no-verify"), ("am", "--no-verify", "x.patch"),
                 ("cherry-pick", "--no-verify", "other"), ("revert", "--no-verify", "HEAD")):
        refused(r, label, *args, why="--no-verify")


@case("shim: commit near-misses run, including a message that says --no-verify")
def _(base):
    label = "shim: commit near-misses run, including a message that says --no-verify"
    r = Repo(base, "commitok")
    r.real("add", "a.txt")
    runs(r, label, "commit", "-m", "--no-verify")
    check(label, r.real("log", "-1", "--format=%s").stdout.strip() == "--no-verify", "the message was not committed as given")
    r.write("a.txt", "two\n"); r.real("add", "a.txt")
    runs(r, label, "commit", "--amend", "--no-edit")
    r.write("a.txt", "three\n")
    runs(r, label, "commit", "-am", "a b  c")
    check(label, r.real("log", "-1", "--format=%s").stdout.strip() == "a b  c", "an argument with spaces was not passed through exactly")
    bare = r.base / "bare.git"
    fixture_git.init(bare, "--bare")
    r.real("remote", "add", "origin", str(bare))
    runs(r, label, "push", "-n", "origin", "main")
    r.write("a.txt", "four\n"); r.real("add", "a.txt")
    runs(r, label, "commit", "-uno", "-m", "attached value")     # -u takes the attached mode `no`; it is not -n
    check(label, r.real("log", "-1", "--format=%s").stdout.strip() == "attached value", "commit -uno was refused or not committed")
    runs(r, label, "merge", "-n", "other")                        # merge -n is --no-stat


@case("shim: git config of core.hooksPath or include.*, a GIT_CONFIG_* variable, and -c include.path are refused")
def _(base):
    label = "shim: git config of core.hooksPath or include.*, a GIT_CONFIG_* variable, and -c include.path are refused"
    r = Repo(base, "cfg")
    for args in (("config", "core.hooksPath", "/dev/null"), ("config", "--local", "core.hookspath", "x"), ("config", "--get", "core.hooksPath"),
                 ("config", "include.path", "/tmp/x"), ("config", "includeIf.gitdir:/x/.path", "y"), ("-c", "include.path=/tmp/x", "status"),
                 ("-c", "includeIf.gitdir:/x/.path=y", "status"), ("--config-env=include.path=X", "status")):
        refused(r, label, *args, why="can switch the #1789 git hooks off")
    for var in ("GIT_CONFIG_COUNT", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_PARAMETERS"):
        p = r.g("status", env={var: "0"})
        check(label, p.returncode != 0 and "GIT_CONFIG_" in p.stderr, f"{var} in the environment was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    runs(r, label, "config", "user.name", "someone")
    runs(r, label, "config", "--get", "user.name")


@case("shim: -c core.hooksPath on the command line is refused")
def _(base):
    label = "shim: -c core.hooksPath on the command line is refused"
    r = Repo(base, "hookspath")
    r.real("add", "a.txt")
    for args in (("-c", "core.hooksPath=/dev/null", "commit", "-m", "x"), ("-c", "core.hookspath=/dev/null", "status"),
                 ("--config-env=core.hooksPath=X", "status")):
        refused(r, label, *args, why="switch the #1789 git hooks off")
    runs(r, label, "-c", "user.name=u", "-c", "user.email=u@u", "commit", "-m", "y")  # fixture-git: exempt (the shim under test finds the repository from its cwd; fixture_git's GIT_DIR binding would hide that)


@case("shim: a git alias is expanded before the rules are applied")
def _(base):
    label = "shim: a git alias is expanded before the rules are applied"
    r = Repo(base, "alias")
    refused(r, label, "-c", "alias.nuke=reset --hard", "nuke")
    refused(r, label, "-c", "alias.p=add -A", "p")
    r.real("config", "alias.cleanall", "clean -fd")
    refused(r, label, "cleanall")
    r.real("config", "alias.st", "status --short")
    runs(r, label, "st")
    r.real("config", "alias.hi", "!echo hi")
    p = runs(r, label, "hi")
    check(label, p.stdout.strip() == "hi", f"a shell alias that does not mention git should run: {p.stdout!r}")


@case("shim: a shell alias that mentions git is refused, because the git it calls never reaches the shim")
def _(base):
    label = "shim: a shell alias that mentions git is refused, because the git it calls never reaches the shim"
    r = Repo(base, "shellalias")
    for name, text in (("x", "!git reset --hard"), ("y", "!echo hi; git clean -fd"), ("z", "!cd . && /usr/bin/git add -A"), ("w", "!exec git checkout -f"),
                       ("v", "!sh -c 'g=gi; ${g}t reset --hard'"), ("u", "!GIT=1 Git reset --hard")):
        r.real("config", f"alias.{name}", text)
    for name in ("x", "y", "z", "w", "u"):
        refused(r, label, name, why="mentions git")


@case("shim: an alias with a quote in its value, or a chain deeper than 5, is refused")
def _(base):
    label = "shim: an alias with a quote in its value, or a chain deeper than 5, is refused"
    r = Repo(base, "aliasdeep")
    r.real("config", "alias.q", "log --format='%h'")
    r.real("config", "alias.q2", 'log --format="%h"')
    r.real("config", "alias.q3", "log --format=\\%h")
    for name in ("q", "q2", "q3"):
        refused(r, label, name, why="quote or a backslash")
    for k in range(1, 8):
        r.real("config", f"alias.c{k}", f"c{k + 1}")
    r.real("config", "alias.c8", "status --short")
    refused(r, label, "c1", why="deeper than 5")
    runs(r, label, "c5")


@case("shim: -C is honoured when it decides what the root is")
def _(base):
    label = "shim: -C is honoured when it decides what the root is"
    r = Repo(base, "dashc")
    refused(r, label, "-C", str(r.work), "add", ".", cwd=base, why="repository root")
    runs(r, label, "-C", str(r.work / "src"), "add", ".", cwd=base)
    check(label, sorted(r.real("diff", "--cached", "--name-only").stdout.split()) == ["src/c.txt"], "-C src add . should stage only src/")


@case("shim: everything it does not guard behaves exactly like git")
def _(base):
    label = "shim: everything it does not guard behaves exactly like git"
    r = Repo(base, "passthrough")
    for args in (("status", "--porcelain"), ("log", "--oneline"), ("rev-parse", "--show-toplevel"), ("--version",), ("diff", "--stat"),
                 ("log", "--grep=--hard"), ("branch", "--list")):
        a, b = r.g(*args), r.real(*args)
        check(label, (a.returncode, a.stdout) == (b.returncode, b.stdout), f"`git {' '.join(args)}` differs from the real git")
    a, b = r.g("not-a-command"), r.real("not-a-command")
    check(label, a.returncode == b.returncode and a.stderr == b.stderr, f"a failing command's exit code or message changed: {a.returncode} vs {b.returncode}")
    a = r.g("hash-object", "--stdin", stdin="same bytes\n")
    b = subprocess.run([REAL_GIT, "hash-object", "--stdin"], cwd=r.work, env=fixture_git.hermetic(r.env), capture_output=True, text=True, input="same bytes\n")
    check(label, a.returncode == 0 and a.stdout == b.stdout and len(a.stdout.strip()) == 40, "stdin was not passed through to git unchanged")


@case("shim: RAILS_FLOW_GIT_OK=1 runs the real git and says so")
def _(base):
    label = "shim: RAILS_FLOW_GIT_OK=1 runs the real git and says so"
    r = Repo(base, "escape")
    p = r.g("reset", "--hard", env={"RAILS_FLOW_GIT_OK": "1"})
    check(label, p.returncode == 0 and (r.work / "a.txt").read_text() == "one\n" and "RAILS_FLOW_GIT_OK=1" in p.stderr, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("shim: the shim directory on PATH twice, or through a symlink, does not loop")
def _(base):
    label = "shim: the shim directory on PATH twice, or through a symlink, does not loop"
    r = Repo(base, "loop")
    link = base / "shimlink"
    link.symlink_to(SHIM_DIR)
    r.path_env = dict(r.env, PATH=f"{link}{os.pathsep}{SHIM_DIR}{os.pathsep}{os.environ['PATH']}")
    p = r.g("status", "--porcelain")
    check(label, p.returncode == 0 and "a.txt" in p.stdout, f"exit {p.returncode}: {p.stderr.strip()[:160]}")
    refused(r, label, "reset", "--hard")


# --------------------------------------------------------------------------------------------- the SessionStart hook that puts it first
def run_hook(env_file: Path | None, plugin_root: Path, cwd: Path, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in {"CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_ROOT"} and not k.startswith("GIT_")}
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    if env_file is not None:
        env["CLAUDE_ENV_FILE"] = str(env_file)
    env.update(extra or {})
    return subprocess.run(["bash", str(plugin_root / "hooks" / "scripts" / "session-start.sh")], cwd=cwd, env=env, input="", capture_output=True, text=True, timeout=60)


def copy_plugin(dest: Path) -> Path:
    dest.mkdir(parents=True)
    (dest / "hooks" / "scripts").mkdir(parents=True)
    shutil.copy2(HOOK, dest / "hooks" / "scripts" / "session-start.sh")
    shutil.copytree(PLUGIN / "hooks" / "scripts" / "lib", dest / "hooks" / "scripts" / "lib")
    shutil.copytree(SHIM_DIR, dest / "git-shim")
    return dest


@case("hook: the SessionStart hook puts the shim first, so `command -v git` names it")
def _(base):
    label = "hook: the SessionStart hook puts the shim first, so `command -v git` names it"
    root = copy_plugin(base / "plugin with space")
    env_file = base / "claude-env"
    out = base / "not-a-repo"; out.mkdir()
    p = run_hook(env_file, root, out)
    check(label, p.returncode == 0 and env_file.exists(), f"exit {p.returncode}, env file {'written' if env_file.exists() else 'NOT written'}: {p.stderr.strip()[:160]}")
    r = subprocess.run(["bash", "-c", f'. "{env_file}"; command -v git'], capture_output=True, text=True)
    check(label, r.stdout.strip() == str(root / "git-shim" / "git"), f"`command -v git` printed {r.stdout.strip()!r}")
    r = subprocess.run(["zsh", "-c", f'. "{env_file}"; command -v git'], capture_output=True, text=True) if shutil.which("zsh") else None
    if r is not None:
        check(label, r.stdout.strip() == str(root / "git-shim" / "git"), f"under zsh, `command -v git` printed {r.stdout.strip()!r}")


@case("hook: running the SessionStart hook again does not repeat the line")
def _(base):
    label = "hook: running the SessionStart hook again does not repeat the line"
    root = copy_plugin(base / "plugin")
    env_file = base / "claude-env"
    for _ in range(3):
        run_hook(env_file, root, base)
    n = env_file.read_text().count("git-shim")
    check(label, n == 1, f"{n} lines after three starts")


@case("hook: with no CLAUDE_ENV_FILE the hook is a clean no-op")
def _(base):
    label = "hook: with no CLAUDE_ENV_FILE the hook is a clean no-op"
    root = copy_plugin(base / "plugin")
    before = sorted(p.name for p in base.iterdir())
    p = run_hook(None, root, base)
    after = sorted(p.name for p in base.iterdir())
    check(label, p.returncode == 0 and after == before and "git-shim" not in p.stdout and "git-shim" not in p.stderr,
          f"exit {p.returncode}; new files {sorted(set(after) - set(before))}; output {p.stdout.strip()[:100]!r}")


@case("hook: an env file it cannot write, or a plugin with no shim, does not break the hook")
def _(base):
    label = "hook: an env file it cannot write, or a plugin with no shim, does not break the hook"
    root = copy_plugin(base / "plugin")
    p = run_hook(base / "no-such-dir" / "env", root, base)
    check(label, p.returncode == 0, f"an unwritable env file: exit {p.returncode}: {p.stderr.strip()[:160]}")
    shutil.rmtree(root / "git-shim")
    env_file = base / "claude-env2"
    p = run_hook(env_file, root, base)
    check(label, p.returncode == 0 and not env_file.exists(), f"no shim: exit {p.returncode}, env file {'written' if env_file.exists() else 'not written'}")


def run(argv: list[str]) -> int:
    match = ""
    if "--match" in argv:
        i = argv.index("--match")
        match = argv[i + 1] if i + 1 < len(argv) else ""
    chosen = [(label, fn) for label, fn in CASES if match in label]
    if not chosen:
        print(f"SELFTEST FAILED -- no case's label contains {match!r}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        for n, (label, fn) in enumerate(chosen):
            sub = base / f"c{n}"
            sub.mkdir()
            try:
                fn(sub)
            except Exception as exc:  # a case that cannot run is a failure, never a pass
                FAILURES.append(f"{label}: the case itself failed to run: {type(exc).__name__}: {str(exc)[:300]}")
    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} failure(s) in {len(chosen)} case(s), {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"git-shim selftest: {CHECKS} checks passed in {len(chosen)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
