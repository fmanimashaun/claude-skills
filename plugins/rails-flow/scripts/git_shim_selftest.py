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
import shlex
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
    for args in (("add", "/etc/hosts"), ("add", str(base / "outside.txt")), ("add", ":(exclude)u.txt", "a.txt"), ("add", ":!u.txt"), ("add", "*.txt"), ("add", "src/*"),
                 ("add", "a.t?t"), ("add", "[a].txt"), ("add", "--pathspec-from-file=list.txt"), ("add", "--pathspec-from-file", "list.txt"),
                 ("checkout", "--", "*.txt"), ("restore", "*.txt"), ("add", "../outside")):
        refused(r, label, *args, why="cannot be judged" if "pathspec-from-file" in " ".join(args) else "plain relative paths")
    runs(r, label, "add", "a.txt", "src/b.txt")


@case("shim: an absolute path STRICTLY INSIDE this repository is as plain as a relative one; the root, outside paths and `..` stay refused (#1982)")
def _(base):
    label = "shim: an absolute path STRICTLY INSIDE this repository is as plain as a relative one; the root, outside paths and `..` stay refused (#1982)"
    r = Repo(base, "absin")
    (base / "outside.txt").write_text("o\n")
    top = str(r.work.resolve())
    for args in (("add", top), ("add", top + "/"), ("add", top + "//"), ("add", top + "/."), ("add", top + "/.."), ("add", top + "/src/.."),
                 ("add", top + "/src/../.."), ("add", str(base / "outside.txt")), ("add", str(base)), ("add", "/"), ("add", top + "/*"), ("add", top + "/**"),
                 ("add", top + "/nosuchdir/f.txt"), ("add", top + "-evil/a.txt"), ("add", top + "/src/../../outside.txt"),
                 ("checkout", "--", top), ("checkout", "--", str(base / "outside.txt")), ("restore", top)):
        refused(r, label, *args, why="plain relative paths")
    # an untouched sibling directory whose name merely STARTS WITH the repository's is not inside it
    (base / (r.work.name + "-evil")).mkdir()
    (base / (r.work.name + "-evil") / "a.txt").write_text("e\n")
    refused(r, label, "add", str(base.resolve() / (r.work.name + "-evil") / "a.txt"), why="plain relative paths")
    p = runs(r, label, "add", top + "/a.txt", top + "/src/c.txt")
    check(label, r.real("diff", "--cached", "--name-only").stdout.split() == ["a.txt", "src/c.txt"], f"staged: {r.real('diff', '--cached', '--name-only').stdout!r}")
    r.real("reset", "-q")
    runs(r, label, "add", "--", top + "/src/", cwd=r.work / "src")
    check(label, "src/c.txt" in r.real("diff", "--cached", "--name-only").stdout, "a directory under the root, from a subdirectory, was not staged")
    # SPELLED THROUGH A SYMLINK: a temp directory is often one (/tmp, /var on macOS), and git reports the toplevel physically.
    link = base / "linkto"
    link.symlink_to(r.work, target_is_directory=True)
    r.real("reset", "-q")
    runs(r, label, "add", str(link / "u.txt"))
    check(label, "u.txt" in r.real("diff", "--cached", "--name-only").stdout, "a path spelled through a symlink to the repository was not staged")
    refused(r, label, "add", str(link), why="plain relative paths")


@case("shim: in a LINKED WORKTREE an absolute path inside it passes and one into the main checkout is refused (#1982, the shape that was reported)")
def _(base):
    label = "shim: in a LINKED WORKTREE an absolute path inside it passes and one into the main checkout is refused (#1982, the shape that was reported)"
    r = Repo(base, "wtmain")
    r.real("add", "a.txt")
    r.real("commit", "-q", "-m", "two")
    wt = base / "wtlinked"
    r.real("worktree", "add", "-q", "-b", "feat/x", str(wt))
    (wt / "newdir").mkdir()
    (wt / "newdir" / "only.txt").write_text("n\n")
    wtp = str(wt.resolve())
    p = runs(r, label, "add", "--", wtp + "/newdir/only.txt", cwd=wt)
    check(label, r.real("diff", "--cached", "--name-only", cwd=wt).stdout.split() == ["newdir/only.txt"], f"staged in the worktree: {r.real('diff', '--cached', '--name-only', cwd=wt).stdout!r}")
    for args in (("add", wtp), ("add", wtp + "/."), ("add", str(r.work.resolve() / "a.txt")), ("add", str(r.work.resolve()))):
        before = r.real("diff", "--cached", "--name-only", cwd=wt).stdout
        q = r.g(*args, cwd=wt)
        check(label, q.returncode != 0 and "git-shim" in q.stderr and "plain relative paths" in q.stderr
              and r.real("diff", "--cached", "--name-only", cwd=wt).stdout == before, f"`git {' '.join(args)}` from the worktree: exit {q.returncode}: {q.stderr.strip()[:160]}")


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
    refused(r, label, "-c", "core.hooksPath=/tmp/hooks", "status")
    # ci_match is what reads these two, and it must not depend on tr: a shell alias that names git, and `git config core.hooksPath` (#1982: the -c form is an
    # allowlist now and fails CLOSED when ci_match cannot run, so it no longer shows the fail-open by itself)
    r.real("config", "alias.shellgit", "!git reset --hard")
    refused(r, label, "shellgit", why="mentions git")
    refused(r, label, "config", "core.hooksPath", "/dev/null")
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
                 ("-c", "includeIf.gitdir:/x/.path=y", "status"), ("--config-env=include.path=X", "status"),
                 ):
        refused(r, label, *args, why="may be set on the command line" if args[0].startswith("-") else "can switch the #1789 git hooks off")
    # #1982: the pairs are READ, not refused on sight. What can switch the hooks off, or the shim cannot read, is refused; the rest passes.
    for env in ({"GIT_CONFIG_PARAMETERS": "'user.name'='x'"}, {"GIT_CONFIG_GLOBAL": "/tmp/cfg"}, {"GIT_CONFIG_SYSTEM": "/tmp/cfg"}, {"GIT_CONFIG_FOO": "1"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/tmp/hooks"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "CORE.HOOKSPATH", "GIT_CONFIG_VALUE_0": "/tmp/hooks"},
                {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "x", "GIT_CONFIG_KEY_1": "include.path", "GIT_CONFIG_VALUE_1": "/tmp/x"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "includeIf.gitdir:/x/.path", "GIT_CONFIG_VALUE_0": "y"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "/tmp/x"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "CORE.FSMONITOR", "GIT_CONFIG_VALUE_0": "/tmp/x"},
                {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.sshCommand", "GIT_CONFIG_VALUE_0": "/tmp/x"},
                {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "x", "GIT_CONFIG_KEY_1": "CORE.SSHCOMMAND", "GIT_CONFIG_VALUE_1": "/tmp/x"},
                {"GIT_CONFIG_COUNT": "abc"}, {"GIT_CONFIG_COUNT": "1000000"}, {"GIT_CONFIG_COUNT": "-1"}):
        p = r.g("status", env=env)
        check(label, p.returncode != 0 and "git-shim" in p.stderr, f"{env} in the environment was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    # A count that is not a plain number is refused BY THE COUNT CHECK: git's own alias lookup fails on one too, so "refused" alone would hide a dead check.
    for cnt in ("abc", "1000000", "-1", "1.5", "0x1", "+1", " 1", "1 "):
        p = r.g("status", env={"GIT_CONFIG_COUNT": cnt})
        check(label, p.returncode != 0 and "plain number" in p.stderr, f"GIT_CONFIG_COUNT={cnt!r} was not refused as a count: exit {p.returncode}: {p.stderr.strip()[:120]}")
    # A hermetic fixture's pairs (fixture_git.hermetic()) and the switches that only make git MORE isolated pass, `git init` included.
    for env in ({"GIT_CONFIG_COUNT": "0"}, {"GIT_CONFIG_NOSYSTEM": "1"}, {"GIT_CONFIG_GLOBAL": "/dev/null"}, {"GIT_CONFIG_SYSTEM": "/dev/null"},
                {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "x", "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"},
                fixture_git.hermetic({})):
        p = r.g("status", env=env)
        check(label, p.returncode == 0 and "git-shim" not in p.stderr, f"{sorted(env)} in the environment was refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
        q = r.g("init", "-q", str(base / ("init-" + str(abs(hash(str(sorted(env.items()))))))), env=env)
        check(label, q.returncode == 0 and "git-shim" not in q.stderr, f"`git init` with {sorted(env)} was refused: exit {q.returncode}: {q.stderr.strip()[:120]}")
    # an alias defined by an environment pair is a key like any other: it is not on the allowlist, so it is refused (and `add -A` through one never runs)
    for name, value in (("st", "status"), ("sa", "add -A")):
        p = r.g(name, env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"alias.{name}", "GIT_CONFIG_VALUE_0": value})
        check(label, p.returncode != 0 and "git-shim" in p.stderr, f"an alias from an environment pair was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    runs(r, label, "config", "user.name", "someone")
    runs(r, label, "config", "--get", "user.name")


@case("shim: -c core.hooksPath on the command line is refused")
def _(base):
    label = "shim: -c core.hooksPath on the command line is refused"
    r = Repo(base, "hookspath")
    r.real("add", "a.txt")
    for args in (("-c", "core.hooksPath=/tmp/hooks", "commit", "-m", "x"), ("-c", "core.hookspath=/tmp/hooks", "status"),
                 ("--config-env=core.hooksPath=X", "status")):
        refused(r, label, *args, why="may be set on the command line")
    runs(r, label, "-c", "user.name=u", "-c", "user.email=u@u", "commit", "-m", "y")  # fixture-git: exempt (the shim under test finds the repository from its cwd; fixture_git's GIT_DIR binding would hide that)


@case("shim: -c core.fsmonitor and -c core.sshCommand (a program git runs) are refused, in any case")
def _(base):
    label = "shim: -c core.fsmonitor and -c core.sshCommand (a program git runs) are refused, in any case"
    r = Repo(base, "runsprog")
    for args in (("-c", "core.fsmonitor=/tmp/x", "status"), ("-c", "CORE.FSMONITOR=/tmp/x", "status"), ("-c", "core.sshCommand=/tmp/x", "status"),
                 ("-c", "Core.SshCommand=/tmp/x", "status"), ("--config-env=core.fsmonitor=X", "status"), ("--config-env=core.sshCommand=X", "status")):
        refused(r, label, *args, why="may be set on the command line")
    runs(r, label, "-c", "gc.auto=0", "status")


ALLOWED_KEYS = ("maintenance.auto", "gc.auto", "user.name", "user.email", "commit.gpgsign")
PAIRS_OK = (("core.fsmonitor", "false"), ("core.hooksPath", "/dev/null"), ("core.quotePath", "false"), ("tag.gpgSign", "false"), ("credential.helper", ""),
            ("credential.helper", "!gh auth git-credential"), ("CORE.FSMONITOR", "false"), ("Core.HooksPath", "/dev/null"), ("TAG.GPGSIGN", "false"))
PAIRS_REFUSED = (("core.fsmonitor", "true"), ("core.fsmonitor", "/tmp/x"), ("core.fsmonitor", "False"), ("core.fsmonitor", "false "), ("core.fsmonitor", ""), ("core.fsmonitor", "0"),
                 ("core.hooksPath", "/dev/null/"), ("core.hooksPath", "/dev/nulL"), ("core.hooksPath", ""), ("core.hooksPath", ".git/hooks"), ("core.hooksPath", "/dev/null "),
                 ("core.quotePath", "true"), ("core.quotePath", "false "), ("core.quotePath", ""), ("tag.gpgSign", "true"), ("tag.gpgSign", ""),
                 ("credential.helper", "x"), ("credential.helper", "!gh auth git-credential --evil"), ("credential.helper", "!gh auth git-credential "),
                 ("credential.helper", "! gh auth git-credential"), ("credential.helper", "!GH auth git-credential"), ("credential.helper", " "),
                 ("credential.helper", "!gh auth git-credential; touch /tmp/x"), ("core.pager", "cat"), ("core.editor", "true"), ("core.sshCommand", "false"))
REFUSED_KEYS = ("core.pager", "core.editor", "credential.helper", "gpg.program", "core.fsmonitor", "core.sshCommand", "core.hooksPath", "include.path", "includeIf.gitdir:/x/.path",
                "diff.external", "core.autocrlf", "alias.p", "filter.evil.clean", "core.askPass", "sequence.editor", "user.name.x", "user.namex", "user.nam", "xuser.name",
                "gc.autoDetach", "commit.gpgsign.x", "user.email ", " user.email")


@case("shim: the config a command may carry is an ALLOWLIST of exact keys, in all three forms: GIT_CONFIG_KEY_n, -c and --config-env (#1982)")
def _(base):
    label = "shim: the config a command may carry is an ALLOWLIST of exact keys, in all three forms: GIT_CONFIG_KEY_n, -c and --config-env (#1982)"
    r = Repo(base, "allowlist")

    def forms(key: str) -> list[tuple[str, tuple[str, ...], dict[str, str]]]:
        return [("GIT_CONFIG_KEY_0", ("status",), {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": key, "GIT_CONFIG_VALUE_0": "x"}),
                ("-c", ("-c", f"{key}=x", "status"), {}),
                ("--config-env=", (f"--config-env={key}=CFGV", "status"), {"CFGV": "x"}),
                ("--config-env", ("--config-env", f"{key}=CFGV", "status"), {"CFGV": "x"})]
    for key in REFUSED_KEYS:
        for form, args, env in forms(key):
            p = r.g(*args, env=env)
            check(label, p.returncode != 0 and "git-shim" in p.stderr, f"{key!r} through {form} was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    for key in ALLOWED_KEYS + ("USER.NAME", "Commit.GpgSign", "Maintenance.Auto"):
        for form, args, env in forms(key):
            p = r.g(*args, env=env)
            check(label, p.returncode == 0 and "git-shim" not in p.stderr, f"{key!r} through {form} was refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    # THE EXACT (key, value) PAIRS shipped code passes (#1982): the hardening overrides, with exactly that value, key case-insensitive
    def pair_forms(key: str, value: str) -> list[tuple[str, tuple[str, ...], dict[str, str]]]:
        return [("GIT_CONFIG_KEY_0", ("status",), {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": key, "GIT_CONFIG_VALUE_0": value}),
                ("-c", ("-c", f"{key}={value}", "status"), {}),
                ("--config-env=", (f"--config-env={key}=CFGV", "status"), {"CFGV": value}),
                ("--config-env", ("--config-env", f"{key}=CFGV", "status"), {"CFGV": value})]
    for key, value in PAIRS_OK:
        for form, args, env in pair_forms(key, value):
            p = r.g(*args, env=env)
            check(label, p.returncode == 0 and "git-shim" not in p.stderr, f"{key}={value!r} through {form} was refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    for key, value in PAIRS_REFUSED:
        for form, args, env in pair_forms(key, value):
            p = r.g(*args, env=env)
            check(label, p.returncode != 0 and "git-shim" in p.stderr, f"{key}={value!r} through {form} was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    # core.hooksPath=/dev/null switches the hooks (our pre-commit and pre-push guards) off, so only a command that runs no hook may carry it (#1994)
    for sub_ in ("commit", "push", "merge", "rebase", "pull", "am", "cherry-pick", "revert", "add", "checkout", "rm", "gc", "some-unknown-subcommand"):
        for form, args, env in pair_forms("core.hooksPath", "/dev/null"):
            a = args[:-1] + (sub_,)
            p = r.g(*a, env=env)
            check(label, p.returncode != 0 and "git-shim" in p.stderr and "runs no hook" in p.stderr, f"core.hooksPath=/dev/null through {form} on `{sub_}` was not refused for the hooks reason: exit {p.returncode}: {p.stderr.strip()[:120]}")
    for sub_ in ("diff", "log", "rev-parse", "ls-files", "show-ref", "config", "fetch", "ls-remote"):
        for form, args, env in pair_forms("core.hooksPath", "/dev/null"):
            a = args[:-1] + (sub_,)
            p = r.g(*a, env=env)
            check(label, "git-shim" not in p.stderr, f"core.hooksPath=/dev/null through {form} on the hook-free `{sub_}` was refused: {p.stderr.strip()[:120]}")
    for key in ("core.fsmonitor", "core.hooksPath", "credential.helper", "tag.gpgSign"):
        p = r.g("-c", key, "status")
        check(label, p.returncode != 0 and "git-shim" in p.stderr, f"`-c {key}` with no value (the value true) was not refused: exit {p.returncode}: {p.stderr.strip()[:120]}")
    for key in ("core.fsmonitor", "credential.helper"):
        for args in (("--config-env", f"{key}=NOSUCHVAR", "status"), (f"--config-env={key}=NOSUCHVAR", "status")):
            p = r.g(*args)
            # BY THE PAIR RULE: git's own alias lookup also fails on an unset variable, which would hide a dead check
            check(label, p.returncode != 0 and "may be set on the command line" in p.stderr, f"{args} naming an UNSET variable was not refused as a pair: exit {p.returncode}: {p.stderr.strip()[:120]}")
    # every key a hermetic fixture sets must pass, or the fixture cannot run under the shim: read them from the helper, not from this file
    env = fixture_git.hermetic({})
    for i in range(int(env["GIT_CONFIG_COUNT"])):
        k = env[f"GIT_CONFIG_KEY_{i}"]
        check(label, k.lower() in ALLOWED_KEYS, f"fixture_git.hermetic() sets {k!r}, which the shim's allowlist does not admit")
    identity = [a.split("=")[0] for a in fixture_git.IDENTITY if "=" in a]
    for k in identity:
        check(label, k.lower() in ALLOWED_KEYS, f"fixture_git.IDENTITY passes {k!r} with -c, which the shim's allowlist does not admit")


@case("shim: a hermetic fixture may stage its OWN temp repository whole, under every condition of the exemption (#1982, decision (b))")
def _(base):
    label = "shim: a hermetic fixture may stage its OWN temp repository whole, under every condition of the exemption (#1982, decision (b))"
    proj = Repo(base, "proj")                       # the session's project: outside the temp root used below
    (proj.work / ".git" / "rails-flow-fixture").write_text("")     # so the rows about the PROJECT are refused by what they test (location, symlink, containment), not by the missing identity
    tmproot = base / "tmproot"
    tmproot.mkdir()
    fx = tmproot / "fx"
    fixture_git.init(fx, "-b", "main")
    (fx / "stray.txt").write_text("s\n")
    outside = base / "outside"
    fixture_git.init(outside, "-b", "main")
    evil = base / "tmproot-evil"                    # a sibling whose name merely STARTS with the temp root's
    evil.mkdir()
    fixture_git.init(evil / "fx", "-b", "main")
    (evil / "fx" / "stray.txt").write_text("s\n")
    (tmproot / "link").symlink_to(proj.work, target_is_directory=True)
    (outside / "stray.txt").write_text("s\n")
    anc = base / "anc"                              # a repository that CONTAINS the project
    fixture_git.init(anc, "-b", "main")
    (anc / "stray.txt").write_text("s\n")
    anc_proj = anc / "inner-proj"
    anc_proj.mkdir()
    home = base / "exempt-home"
    home.mkdir()

    def env_for(wt: Path, gd: Path | None = None, **over: str | None) -> dict[str, str]:
        e = {"GIT_DIR": str(gd if gd is not None else wt / ".git"), "GIT_WORK_TREE": str(wt), "TMPDIR": str(tmproot), "HOME": str(home),
             "CLAUDE_SESSION_PROJECT_TOP": str(proj.work)}
        e.update({k: v for k, v in over.items() if v is not None})
        for k, v in over.items():
            if v is None:
                e.pop(k, None)
        return e

    def staged(wt: Path) -> str:
        return subprocess.run([REAL_GIT, "-C", str(wt), "diff", "--cached", "--name-only"], env=fixture_git.hermetic(proj.env), capture_output=True, text=True).stdout

    def attempt(what: str, wt: Path, env: dict[str, str], *, ok: bool, args: tuple[str, ...] = ("add", "-A"), stray_check: bool = True) -> None:
        subprocess.run([REAL_GIT, "-C", str(wt), "reset", "-q"], env=fixture_git.hermetic(proj.env), capture_output=True, text=True)
        e = dict(proj.path_env)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "TMPDIR", "CLAUDE_SESSION_PROJECT_TOP"):
            e.pop(k, None)
        e.update(env)
        p = subprocess.run(["git", *args], cwd=wt, env=e, capture_output=True, text=True, timeout=20)
        if ok:
            check(label, p.returncode == 0 and "git-shim" not in p.stderr and (not stray_check or "stray.txt" in staged(wt)), f"{what}: refused or not staged: exit {p.returncode}: {p.stderr.strip()[:140]}")
        else:
            check(label, p.returncode != 0 and "git-shim" in p.stderr and (not stray_check or "stray.txt" not in staged(wt)), f"{what}: was NOT refused: exit {p.returncode}: {p.stderr.strip()[:140]}")

    # the exemption
    attempt("a fixture repo named by GIT_DIR and GIT_WORK_TREE inside TMPDIR", fx, env_for(fx), ok=True)
    attempt("`add .` in the same repo", fx, env_for(fx), ok=True, args=("add", "."))
    # the temp root is compared PHYSICALLY: a TMPDIR that is a symlink to the real temp root (macOS /var is /private/var) still exempts a fixture, because git reports physical paths
    (base / "tmplink").symlink_to(tmproot, target_is_directory=True)
    attempt("TMPDIR is a symlink to the real temp root: still exempt, the comparison is physical", fx, env_for(fx, TMPDIR=str(base / "tmplink")), ok=True)
    # every condition, each broken alone
    attempt("only GIT_WORK_TREE set", fx, env_for(fx, GIT_DIR=None), ok=False)
    attempt("only GIT_DIR set", fx, env_for(fx, GIT_WORK_TREE=None), ok=False)
    attempt("GIT_WORK_TREE inside TMPDIR but GIT_DIR outside it", fx, env_for(fx, gd=outside / ".git"), ok=False)
    attempt("GIT_DIR inside TMPDIR but GIT_WORK_TREE outside it", outside, env_for(outside, gd=fx / ".git"), ok=False)
    attempt("the repository is outside TMPDIR", outside, env_for(outside), ok=False)
    attempt("a sibling directory whose name merely starts with TMPDIR's", evil / "fx", env_for(evil / "fx"), ok=False)
    attempt("the work tree is a sibling named like TMPDIR's, with GIT_DIR properly inside", evil / "fx", env_for(evil / "fx", gd=fx / ".git"), ok=False)
    attempt("GIT_DIR is a sibling named like TMPDIR's, with the work tree properly inside", fx, env_for(fx, gd=evil / "fx" / ".git"), ok=False)
    attempt("TMPDIR unset", fx, env_for(fx, TMPDIR=None), ok=False)
    attempt("TMPDIR empty", fx, env_for(fx, TMPDIR=""), ok=False)
    attempt("TMPDIR=/", fx, env_for(fx, TMPDIR="/"), ok=False)
    attempt("TMPDIR is HOME", fx, env_for(fx, TMPDIR=str(home), HOME=str(home)), ok=False)
    hfx = home / "fx"
    fixture_git.init(hfx, "-b", "main")
    (hfx / "stray.txt").write_text("s\n")
    attempt("TMPDIR=$HOME with a repository under it", hfx, env_for(hfx, TMPDIR=str(home), HOME=str(home)), ok=False)
    (tmproot / "h").mkdir()
    attempt("HOME inside the temp root is fine: only a TMPDIR that IS HOME or CONTAINS the project is refused", fx, env_for(fx, HOME=str(tmproot / "h")), ok=True)
    attempt("TMPDIR contains the project", fx, env_for(fx, TMPDIR=str(base)), ok=False)
    attempt("CLAUDE_SESSION_PROJECT_TOP unset", fx, env_for(fx, CLAUDE_SESSION_PROJECT_TOP=None), ok=False)
    attempt("CLAUDE_SESSION_PROJECT_TOP names a directory that does not exist", fx, env_for(fx, CLAUDE_SESSION_PROJECT_TOP=str(base / "nope")), ok=False)
    attempt("the work tree IS the session's project", fx, env_for(fx, CLAUDE_SESSION_PROJECT_TOP=str(fx)), ok=False)
    attempt("the work tree CONTAINS the session's project", anc, env_for(anc, TMPDIR=str(base), CLAUDE_SESSION_PROJECT_TOP=str(anc_proj)), ok=False)
    attempt("a symlink in TMPDIR that points at the project (GIT_WORK_TREE through the link)", proj.work, env_for(tmproot / "link"), ok=False)
    attempt("the same with TMPDIR widened over the project", proj.work, env_for(tmproot / "link", TMPDIR=str(base)), ok=False)
    attempt("the project itself, with TMPDIR over it", proj.work, env_for(proj.work, TMPDIR=str(base)), ok=False)
    # the session's own repository is refused by what is ON DISK, whatever the environment claims (the security review of #1994: a wrong but existing marker value let it through)
    mk = tmproot / "marked"
    fixture_git.init(mk, "-b", "main")
    (mk / "stray.txt").write_text("s\n")
    (mk / ".git" / "claude-session-project").write_text("")
    attempt("a repository carrying the session marker, with CLAUDE_SESSION_PROJECT_TOP pointing elsewhere", mk, env_for(mk, CLAUDE_SESSION_PROJECT_TOP=str(home)), ok=False)
    # a REAL linked worktree of the marked repository: its git dir has `commondir`, the marker lives in the common dir, and it carries the fixture identity itself, so only the marker refuses
    fixture_git.run(mk, "commit", "-q", "--allow-empty", "-m", "i")
    lw = tmproot / "marked-wt"
    fixture_git.run(mk, "worktree", "add", "-q", str(lw), "-b", "lw")
    lgd = mk / ".git" / "worktrees" / "marked-wt"
    (lgd / "rails-flow-fixture").write_text("")
    (lw / "stray.txt").write_text("s\n")
    attempt("a linked worktree of a repository carrying the session marker (the marker is in its common dir)", lw, env_for(lw, gd=lgd), ok=False)
    # the adversary pass on #1994: five commands got through. Each is a row here, and each is judged by the refusal it must get.
    # 1. git prefers a command-line --git-dir/--work-tree/-C/--namespace over the environment, so the decoy fixture in GIT_DIR proved nothing about the repository the command named
    pw = str(proj.work)
    for what, args in (("--git-dir and --work-tree", ("--git-dir", f"{pw}/.git", "--work-tree", pw, "add", "-A")), ("--git-dir= and --work-tree=", (f"--git-dir={pw}/.git", f"--work-tree={pw}", "add", "-A")),
                       ("-C the project", ("-C", pw, "add", "-A")), ("--namespace", ("--namespace", "x", "add", "-A"))):
        attempt(f"{what} on the command line beat a decoy fixture named in the environment", fx, env_for(fx), ok=False, args=args)
    # the flags are refused OUTRIGHT, even when they name another valid fixture (one rule to reason about, and it does not depend on the second check)
    fx2 = tmproot / "fx2"
    fixture_git.init(fx2, "-b", "main")
    (fx2 / "stray.txt").write_text("s\n")
    attempt("--git-dir naming another valid fixture is still refused", fx, env_for(fx), ok=False, args=("--git-dir", str(fx2 / ".git"), "add", "-A"))
    attempt("--git-dir= naming another valid fixture is still refused", fx, env_for(fx), ok=False, args=(f"--git-dir={fx2 / '.git'}", "add", "-A"))
    attempt("--work-tree naming another valid fixture is still refused", fx, env_for(fx), ok=False, args=("--work-tree", str(fx2), "add", "-A"))
    attempt("--work-tree= naming another valid fixture is still refused", fx, env_for(fx), ok=False, args=(f"--work-tree={fx2}", "add", "-A"))
    # 2. an index, an object store, a common dir or a namespace in the environment point git at another repository's state while the decoy sits in GIT_DIR
    for var, val in (("GIT_INDEX_FILE", f"{pw}/.git/index"), ("GIT_OBJECT_DIRECTORY", f"{pw}/.git/objects"), ("GIT_ALTERNATE_OBJECT_DIRECTORIES", f"{pw}/.git/objects"),
                     ("GIT_COMMON_DIR", f"{pw}/.git"), ("GIT_NAMESPACE", "x")):
        attempt(f"{var} in the environment redirects git away from the fixture", fx, env_for(fx, **{var: val}), ok=False)
    # 3. a standalone repository that merely sits inside the temp root is not a fixture: only one `fixture_git.init` created carries the identity file
    sa = tmproot / "standalone"
    sa.mkdir()
    subprocess.run([REAL_GIT, "init", "-q", str(sa)], env=fixture_git.hermetic(proj.env), capture_output=True, check=True)
    (sa / "stray.txt").write_text("s\n")
    attempt("a standalone repository inside the temp root that fixture_git did not create", sa, env_for(sa), ok=False)
    # outside a fixture the whole-tree add is still refused, and the other rules still hold INSIDE the exempt repository
    attempt("no GIT_DIR/GIT_WORK_TREE at all", fx, {}, ok=False)
    # the exemption covers STAGING only: the working-tree rules stay refused in a fixture's own repository (widening them waits for an adversary pass)
    for what, args in (("`reset --hard`", ("reset", "--hard")), ("`clean -fd`", ("clean", "-fd")), ("`checkout -f`", ("checkout", "-f")), ("`stash clear`", ("stash", "clear"))):
        attempt(f"{what} is not exempt in the fixture", fx, env_for(fx), ok=False, args=args, stray_check=False)
    # ... nor the rules about hooks, config and --no-verify
    attempt("`commit --no-verify` is not exempt in the fixture", fx, env_for(fx), ok=False, args=("commit", "--no-verify", "-m", "x", "--allow-empty"), stray_check=False)
    attempt("`config core.hooksPath` is not exempt in the fixture", fx, env_for(fx), ok=False, args=("config", "core.hooksPath", "/tmp/h"), stray_check=False)


@case("shim: GIT_CONFIG_GLOBAL is /dev/null, or a file inside the temp root whose every entry is allowlisted (#1982)")
def _(base):
    label = "shim: GIT_CONFIG_GLOBAL is /dev/null, or a file inside the temp root whose every entry is allowlisted (#1982)"
    proj = Repo(base, "gproj")
    tmproot = base / "gtmproot"
    tmproot.mkdir()
    home = base / "ghome"
    home.mkdir()
    outside = base / "goutside"
    outside.mkdir()

    def cfgfile(where: Path, name: str, text: str) -> Path:
        f = where / name
        f.write_text(text)
        return f
    good = cfgfile(tmproot, "good.cfg", "[user]\n\tname = t\n\temail = t@t\n[core]\n\tfsmonitor = false\n[gc]\n\tauto = 0\n")
    base_env = {"TMPDIR": str(tmproot), "HOME": str(home), "CLAUDE_SESSION_PROJECT_TOP": str(proj.work)}

    def go(what: str, glob: str, *, ok: bool, **over: str | None) -> None:
        env = dict(base_env, GIT_CONFIG_GLOBAL=glob)
        for k, v in over.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        e = dict(proj.path_env)
        e.pop("TMPDIR", None)
        e.update(env)
        p = subprocess.run(["git", "status"], cwd=proj.work, env=e, capture_output=True, text=True, timeout=20)
        if ok:
            check(label, p.returncode == 0 and "git-shim" not in p.stderr, f"{what}: refused: exit {p.returncode}: {p.stderr.strip()[:140]}")
        else:
            check(label, p.returncode != 0 and "git-shim" in p.stderr, f"{what}: was NOT refused: exit {p.returncode}: {p.stderr.strip()[:140]}")
    go("/dev/null", "/dev/null", ok=True)
    go("a temp file whose entries are all allowlisted", str(good), ok=True)
    go("an empty temp file", str(cfgfile(tmproot, "empty.cfg", "")), ok=True)
    for name, text in (("hooks.cfg", "[core]\n\thooksPath = /tmp/h\n"), ("hooks-null.cfg", "[core]\n\thooksPath = /dev/null\n[core]\n\tpager = cat\n"),
                       ("hooks-null-only.cfg", "[core]\n\thooksPath = /dev/null\n"),
                       ("inc.cfg", "[include]\n\tpath = /tmp/x\n"), ("incif.cfg", "[includeIf \"gitdir:/x/\"]\n\tpath = /tmp/x\n"), ("pager.cfg", "[core]\n\tpager = less\n"),
                       ("alias.cfg", "[alias]\n\tp = push\n"), ("fsm.cfg", "[core]\n\tfsmonitor = true\n"), ("mixed.cfg", "[user]\n\tname = t\n[core]\n\teditor = vi\n"),
                       ("ml.cfg", "[user]\n\tname = \"a\\nuser.name\"\n")):
        go(f"a temp file with {name}", str(cfgfile(tmproot, name, text)), ok=False)
    go("a missing file", str(tmproot / "missing.cfg"), ok=False)
    go("a directory", str(tmproot), ok=False)
    go("a file OUTSIDE the temp root", str(cfgfile(outside, "o.cfg", "[user]\n\tname = t\n")), ok=False)
    go("a file inside the session PROJECT", str(cfgfile(proj.work, "p.cfg", "[user]\n\tname = t\n")), ok=False)
    (tmproot / "link.cfg").symlink_to(outside / "o.cfg")
    go("a symlink in the temp root that points outside it", str(tmproot / "link.cfg"), ok=False)
    go("TMPDIR unset", str(good), ok=False, TMPDIR=None)
    go("TMPDIR is /", str(good), ok=False, TMPDIR="/")
    go("TMPDIR is HOME", str(good), ok=False, TMPDIR=str(home), HOME=str(home))
    go("TMPDIR contains the project", str(good), ok=False, TMPDIR=str(base))
    go("CLAUDE_SESSION_PROJECT_TOP unset", str(good), ok=False, CLAUDE_SESSION_PROJECT_TOP=None)
    go("a relative path", "good.cfg", ok=False)
    p = proj.g("status", env={"GIT_CONFIG_SYSTEM": str(good), **base_env})
    check(label, p.returncode != 0 and "git-shim" in p.stderr, f"GIT_CONFIG_SYSTEM naming a temp file must stay refused: exit {p.returncode}")


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


def zsh_row(label: str, env_file: Path, root: Path, which=shutil.which) -> None:
    """The SessionStart line under zsh, the maintainer's shell. Where zsh is absent the row is SAID to be skipped and is not counted, never
    silently dropped (#1971: the Linux check had no zsh, so this selftest read 313 checks there against 314 here, and green). `which` is
    injectable so the skip itself is tested (the case after the hook's)."""
    if which("zsh"):
        r = subprocess.run(["zsh", "-c", f'. "{env_file}"; command -v git'], capture_output=True, text=True)
        check(label, r.stdout.strip() == str(root / "git-shim" / "git"), f"under zsh, `command -v git` printed {r.stdout.strip()!r}")
    else:
        print(f"  skip: zsh is not on PATH, so \"{label}\" did NOT run under zsh -- not a pass.", file=sys.stderr)


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
    zsh_row(label, env_file, root)


@case("zsh absent: the zsh row says it did NOT run, and counts nothing")
def _(base):
    # #1971 (9f's review of #1972): the skip line is the only thing that tells a reader the zsh row did not run, so dropping it must fail.
    label = "zsh absent: the zsh row says it did NOT run, and counts nothing"
    import contextlib
    import io
    before = CHECKS
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        zsh_row("a probe row", base / "no-env-file", base, which=lambda _name: None)
    check(label, 'skip: zsh is not on PATH, so "a probe row" did NOT run under zsh -- not a pass.' in err.getvalue(), f"stderr was {err.getvalue()!r}")
    check(label, CHECKS == before + 1, f"the skipped row counted {CHECKS - before - 1} check(s) of its own")


@case("hook: the SessionStart hook records the session's project toplevel for the shim's fixture exemption, once, and nothing outside a repository (#1982)")
def _(base):
    label = "hook: the SessionStart hook records the session's project toplevel for the shim's fixture exemption, once, and nothing outside a repository (#1982)"
    root = copy_plugin(base / "plugin-top")
    r = Repo(base, "ssproj")
    env_file = base / "claude-env-top"
    for _ in range(3):
        run_hook(env_file, root, r.work)
    text = env_file.read_text()
    top = str(r.work.resolve())
    check(label, text.count("CLAUDE_SESSION_PROJECT_TOP=") == 1, f"the line should be written once: {text!r}")
    check(label, f"export CLAUDE_SESSION_PROJECT_TOP={shlex.quote(top)}" in text or f"CLAUDE_SESSION_PROJECT_TOP={top}" in text, f"it should name the physical toplevel {top}: {text!r}")
    e2 = base / "claude-env-top2"
    out = base / "not-a-repo-top"
    out.mkdir()
    run_hook(e2, root, out)
    check(label, "CLAUDE_SESSION_PROJECT_TOP" not in e2.read_text(), "outside a repository no project toplevel may be recorded (the shim then fails closed)")
    check(label, (r.work / ".git" / "claude-session-project").is_file(), "the session repository must carry the marker file the shim reads (an env value can be overridden inline, a file in the git dir cannot)")
    check(label, not any(out.rglob("claude-session-project")), "nothing outside a repository may be marked")
    sub = r.work / "src"
    e3 = base / "claude-env-top3"
    run_hook(e3, root, sub)
    check(label, f"CLAUDE_SESSION_PROJECT_TOP={shlex.quote(top)}" in e3.read_text() or f"CLAUDE_SESSION_PROJECT_TOP={top}" in e3.read_text(), "from a subdirectory the TOPLEVEL is recorded, not the subdirectory")


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
