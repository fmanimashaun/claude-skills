#!/usr/bin/env python3
"""Selftest: the pre-push and pre-commit guards (#1789) stop the EFFECT, whatever the command was spelled like.

Every positive check is a real `git push` into a bare remote, or a real `git commit`, through the hook the installer wrote where git
runs hooks, and then a look at what happened: the remote ref still where it was, `HEAD` still where it was. "The hook exited 1" is not
the assertion; "nothing moved" is. Every refusal has a near-miss that must pass, so a hook that refuses everything fails here too.

    python3 git_guard_selftest.py               # all cases
    python3 git_guard_selftest.py --match NAME  # only the cases whose label contains NAME (the mutation runner uses this)

Global and system git config are isolated: a maintainer's own `core.hooksPath` would otherwise redirect every case.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

PLUGIN = Path(__file__).resolve().parent.parent
INSTALLER = PLUGIN / "scripts" / "install-git-guards.sh"
MIB = 1024 * 1024

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


def _env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and not k.startswith("RAILS_FLOW_") and k not in {"HOME", "XDG_CONFIG_HOME"}}
    gc = home / "gitconfig"
    gc.write_text("")
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL=str(gc), GIT_CONFIG_NOSYSTEM="1")
    return env


class World:
    """A work clone, optionally with a bare remote, with the guards installed by the real installer."""

    def __init__(self, base: Path, name: str, remote: bool = True, guards: bool = True, guardrails: str | None = None):
        home = base / f"{name}-home"; home.mkdir()
        self.env = _env(home)
        self.work = base / name
        self.bare = base / f"{name}-remote.git"
        fixture_git.init(self.work, "-b", "main")
        self.write("README", "x\n")
        if guardrails is not None:
            self.write("GUARDRAILS.md", guardrails)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.commit_file("second.txt")      # a second commit, so `diverge` has a parent to step back to
        self.has_remote = remote
        if remote:
            fixture_git.init(self.bare, "--bare")
            self.git("remote", "add", "origin", str(self.bare))
            for b in ("dev",):
                self.git("branch", b)
            self.git("push", "-q", "origin", "main", "dev")
        if guards:
            self.install()

    def git(self, *args: str, check_rc: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        e = dict(self.env)
        e.update(env or {})
        return fixture_git.run(self.work, *args, check=check_rc, env=e)

    def write(self, rel: str, text: str | bytes = "x\n") -> None:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode())

    def install(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(INSTALLER)], cwd=self.work, env=fixture_git.hermetic(self.env), capture_output=True, text=True)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def remote_ref(self, ref: str) -> str:
        r = subprocess.run(["git", "--git-dir", str(self.bare), "rev-parse", "-q", "--verify", ref], env=fixture_git.hermetic(self.env),
                           capture_output=True, text=True)
        return r.stdout.strip()

    def commit_file(self, rel: str, text: str = "x\n", msg: str = "c") -> None:
        self.write(rel, text)
        self.git("add", "--", rel)
        self.git("commit", "-q", "-m", msg)

    def diverge(self, branch: str = "main") -> None:
        """Put the local branch on a commit that does NOT contain the remote tip."""
        self.git("checkout", "-q", branch)
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.commit_file(f"diverged-{branch}.txt", branch, "other history")


def refused(p: subprocess.CompletedProcess) -> bool:
    return p.returncode != 0


# ---------------------------------------------------------------------------------------------------------------- pre-push
@case("pre-push: a fast-forward to main, dev and staging is allowed")
def _(base):
    w = World(base, "ff")
    w.git("branch", "staging")
    for b in ("main", "dev", "staging"):
        w.git("checkout", "-q", b)
        w.commit_file(f"{b}.txt")
        p = w.git("push", "origin", b, check_rc=False)
        check("pre-push: a fast-forward to main, dev and staging is allowed", p.returncode == 0 and w.remote_ref(f"refs/heads/{b}") == w.head(),
              f"{b}: exit {p.returncode}: {p.stderr.strip()[:160]}")


for _name in ("main", "dev", "staging"):
    @case(f"pre-push: a force push to {_name} is refused and the remote does not move")
    def _(base, _name=_name):
        label = f"pre-push: a force push to {_name} is refused and the remote does not move"
        w = World(base, f"force-{_name}")
        w.git("branch", "staging")
        w.git("push", "-q", "origin", "staging")
        before = w.remote_ref(f"refs/heads/{_name}")
        w.diverge(_name)
        p = w.git("push", "--force", "origin", _name, check_rc=False)
        check(label, refused(p) and w.remote_ref(f"refs/heads/{_name}") == before,
              f"exit {p.returncode}, remote {'moved' if w.remote_ref(f'refs/heads/{_name}') != before else 'unmoved'}")
        check(label, "not a fast-forward" in p.stderr, f"the refusal does not say why: {p.stderr.strip()[:160]}")


@case("pre-push: every spelling of a force push to main is refused")
def _(base):
    label = "pre-push: every spelling of a force push to main is refused"
    w = World(base, "spell")
    before = w.remote_ref("refs/heads/main")
    w.diverge("main")
    for args in (("push", "-f", "origin", "main"), ("push", "origin", "+main"), ("push", "origin", "+HEAD:main"),
                 ("push", "origin", "+HEAD:refs/heads/main"), ("push", "--force-with-lease", "origin", "main"),
                 ("push", "--force-with-lease", "--force-if-includes", "origin", "main"),
                 ("-c", "alias.p=push --force", "p", "origin", "main"), ("push", "--forc", "origin", "main"),
                 ("push", "--mirror", "origin"), ("push", "--mir", "origin")):
        p = w.git(*args, check_rc=False)
        check(label, refused(p) and w.remote_ref("refs/heads/main") == before,
              f"`git {' '.join(args)}`: exit {p.returncode}, remote {'moved' if w.remote_ref('refs/heads/main') != before else 'unmoved'}")


@case("pre-push: deleting a protected branch is refused and it still exists on the remote")
def _(base):
    label = "pre-push: deleting a protected branch is refused and it still exists on the remote"
    w = World(base, "del")
    for args in (("push", "origin", "--delete", "dev"), ("push", "origin", ":dev"), ("push", "origin", "-d", "dev")):
        p = w.git(*args, check_rc=False)
        check(label, refused(p) and w.remote_ref("refs/heads/dev") != "", f"`git {' '.join(args)}`: exit {p.returncode}, dev {'gone' if not w.remote_ref('refs/heads/dev') else 'present'}")
    check(label, "a delete" in p.stderr, f"the refusal does not say it is a delete: {p.stderr.strip()[:160]}")


@case("pre-push: a force push or a delete of a branch that is not protected is allowed")
def _(base):
    label = "pre-push: a force push or a delete of a branch that is not protected is allowed"
    w = World(base, "free")
    w.git("checkout", "-q", "-b", "feature")
    w.commit_file("a.txt")
    w.git("push", "-q", "origin", "feature")
    w.git("reset", "-q", "--hard", "HEAD~1")
    w.commit_file("b.txt")
    p = w.git("push", "--force", "origin", "feature", check_rc=False)
    check(label, p.returncode == 0 and w.remote_ref("refs/heads/feature") == w.head(), f"force push of feature: exit {p.returncode}: {p.stderr.strip()[:160]}")
    p = w.git("push", "origin", "--delete", "feature", check_rc=False)
    check(label, p.returncode == 0 and w.remote_ref("refs/heads/feature") == "", f"delete of feature: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-push: the first push of a new protected branch is allowed")
def _(base):
    label = "pre-push: the first push of a new protected branch is allowed"
    w = World(base, "first")
    p = w.git("push", "origin", "main:refs/heads/staging", check_rc=False)
    check(label, p.returncode == 0 and w.remote_ref("refs/heads/staging") != "", f"exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-push: a remote tip this clone has never seen is refused until it is fetched")
def _(base):
    label = "pre-push: a remote tip this clone has never seen is refused until it is fetched"
    w = World(base, "unseen")
    other = World(base, "other", remote=False, guards=False)
    other.git("remote", "add", "origin", str(w.bare))
    other.git("fetch", "-q", "origin")
    other.git("checkout", "-q", "-B", "main", "origin/main")
    other.commit_file("elsewhere.txt")
    other.git("push", "-q", "origin", "main")
    tip = w.remote_ref("refs/heads/main")
    w.commit_file("mine.txt")
    p = w.git("push", "--force", "origin", "main", check_rc=False)
    check(label, refused(p) and w.remote_ref("refs/heads/main") == tip, f"exit {p.returncode}, remote {'moved' if w.remote_ref('refs/heads/main') != tip else 'unmoved'}")
    check(label, "git fetch first" in p.stderr, f"the refusal does not say to fetch first: {p.stderr.strip()[:200]}")


@case("pre-push: a declared protected-branches adds a name and a glob")
def _(base):
    label = "pre-push: a declared protected-branches adds a name and a glob"
    w = World(base, "decl", guardrails="# Guardrails\n\n- protected-branches: release/* hotfix\n")
    for b in ("release/1", "hotfix", "feature"):
        w.git("checkout", "-q", "-b", b, "main")
        w.commit_file(f"{b.replace('/', '-')}.txt")
        w.git("push", "-q", "origin", b, check_rc=False)   # the first push of a branch is a create: allowed for every name
        w.git("reset", "-q", "--hard", "HEAD~1")
        w.commit_file(f"{b.replace('/', '-')}-2.txt")
        before = w.remote_ref(f"refs/heads/{b}")
        p = w.git("push", "--force", "origin", b, check_rc=False)
        should_refuse = b != "feature"
        check(label, refused(p) == should_refuse and (w.remote_ref(f"refs/heads/{b}") == before) == should_refuse,
              f"{b}: exit {p.returncode} (a force push should be {'refused' if should_refuse else 'allowed'})")


@case("pre-push: a protected-branches line inside a code block, a comment or an indented block is not read")
def _(base):
    label = "pre-push: a protected-branches line inside a code block, a comment or an indented block is not read"
    text = ("# Guardrails\n\n```\nprotected-branches: feature\n```\n\n<!--\nprotected-branches: feature\n-->\n\n"
            "    protected-branches: feature\n\n~~~\nprotected-branches: feature\n~~~\n")
    w = World(base, "fenced", guardrails=text)
    w.git("checkout", "-q", "-b", "feature", "main")
    w.commit_file("a.txt")
    w.git("push", "-q", "origin", "feature")
    w.git("reset", "-q", "--hard", "HEAD~1")
    w.commit_file("b.txt")
    p = w.git("push", "--force", "origin", "feature", check_rc=False)
    check(label, p.returncode == 0, f"a declaration that sits in code was read: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-push: RAILS_FLOW_PROTECTED_OK=1 lets a rewrite through and says so")
def _(base):
    label = "pre-push: RAILS_FLOW_PROTECTED_OK=1 lets a rewrite through and says so"
    w = World(base, "escape")
    w.diverge("main")
    p = w.git("push", "--force", "origin", "main", check_rc=False, env={"RAILS_FLOW_PROTECTED_OK": "1"})
    check(label, p.returncode == 0 and w.remote_ref("refs/heads/main") == w.head(), f"exit {p.returncode}: {p.stderr.strip()[:160]}")
    check(label, "RAILS_FLOW_PROTECTED_OK=1" in p.stderr, "it did not say the check was skipped")


def run_hook(w: World, hook: str, stdin: str = "", env: dict[str, str] | None = None, *args: str) -> subprocess.CompletedProcess:
    e = fixture_git.env(w.work, w.env)
    e.update(env or {})
    return subprocess.run(["bash", str(w.work / ".git" / "hooks" / hook), *args], input=stdin, cwd=w.work, env=e, capture_output=True, text=True)


@case("pre-push: an unreadable line from git is refused")
def _(base):
    label = "pre-push: an unreadable line from git is refused"
    w = World(base, "unreadable")
    head = w.head()
    p = run_hook(w, "pre-push", "refs/heads/main abc\n", None, "origin", str(w.bare))
    check(label, p.returncode == 1 and "cannot read this line" in p.stderr, f"two fields: exit {p.returncode}: {p.stderr.strip()[:160]}")
    p = run_hook(w, "pre-push", f"refs/heads/main {head} refs/heads/main {head} extra\n", None, "origin", str(w.bare))
    check(label, p.returncode == 1 and "cannot read this line" in p.stderr, f"five fields: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-push: a local commit it cannot resolve is refused")
def _(base):
    label = "pre-push: a local commit it cannot resolve is refused"
    w = World(base, "unresolved")
    tip = w.remote_ref("refs/heads/main")
    p = run_hook(w, "pre-push", f"refs/heads/main {'a' * 40} refs/heads/main {tip}\n", None, "origin", str(w.bare))
    check(label, p.returncode == 1 and "cannot resolve the commit" in p.stderr, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


# -------------------------------------------------------------------------------------------------------------- pre-commit
def stage_and_commit(w: World, files: dict[str, str | bytes], msg: str = "c", env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    for rel, text in files.items():
        w.write(rel, text)
    w.git("add", "-f", "--", *files)
    return w.git("commit", "-q", "-m", msg, check_rc=False, env=env)


def refused_and_unmoved(label: str, w: World, files: dict[str, str | bytes], what: str) -> None:
    before = w.head()
    p = stage_and_commit(w, files)
    check(label, refused(p) and w.head() == before, f"{what}: exit {p.returncode}, HEAD {'moved' if w.head() != before else 'unmoved'}: {p.stderr.strip()[:120]}")
    w.git("reset", "-q")
    for rel in files:
        (w.work / rel).unlink()


@case("pre-commit: an ordinary commit is allowed")
def _(base):
    w = World(base, "plain-c", remote=False)
    p = stage_and_commit(w, {"app/models/user.rb": "class User; end\n", "docs/notes.md": "n\n"})
    check("pre-commit: an ordinary commit is allowed", p.returncode == 0, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


for _label, _files in (
    ("a new env file", [".env", ".env.local", ".env.production", "config/.env", ".ENV", ".Env", ".Env.Local", ".env.example.bak"]),
    ("a key or certificate", ["config/master.key", "server.pem", "cert.p12", "id_rsa", "id_rsa.bak", "KEY.PEM", "ID_RSA"]),
    ("a database, a log or an OS file", ["db/dev.sqlite3", "x.log", ".DS_Store", "docs/.DS_Store", "Foo.LOG", "DB/X.SQLITE3", ".DS_STORE"]),
    ("a dependency or temp directory", ["node_modules/x/index.js", "tmp/cache/x", "log/dev.out", "coverage/index.html", ".bundle/config", "web/node_modules/y.js", "app/.bundle/config", "TMP/x", "Log/y.out", "Node_Modules/z.js"]),
):
    @case(f"pre-commit: {_label} is refused and nothing is committed")
    def _(base, _label=_label, _files=_files):
        label = f"pre-commit: {_label} is refused and nothing is committed"
        w = World(base, "never-" + _label.split()[1][:6], remote=False)
        for rel in _files:
            refused_and_unmoved(label, w, {rel: "secret\n"}, rel)


@case("pre-commit: look-alikes are allowed")
def _(base):
    label = "pre-commit: look-alikes are allowed"
    w = World(base, "lookalike", remote=False)
    for rel in (".env.example", ".env.sample", ".env.template", "config/.env.example", "tmp/.keep", "log/.gitkeep", "config/environment.rb", "lib/env.rb",
                "docs/keys.md", "app/models/log_entry.rb", "notes.logger", "src/node_modules_notes.md",
                "id_rsa.pub", "app/services/log/x.rb", "lib/tmp/y.rb", "docs/coverage/z.md", "app/tmp/x"):
        p = stage_and_commit(w, {rel: "ok\n"}, rel)
        check(label, p.returncode == 0, f"{rel}: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: a tracked env file that is only modified or deleted is allowed")
def _(base):
    label = "pre-commit: a tracked env file that is only modified or deleted is allowed"
    w = World(base, "tracked-env", remote=False)
    p = stage_and_commit(w, {".env": "a\n"}, "seed", env={"RAILS_FLOW_STAGING_OK": "1"})
    check(label, p.returncode == 0, f"setup: exit {p.returncode}: {p.stderr.strip()[:120]}")
    p = stage_and_commit(w, {".env": "b\n"}, "modify")
    check(label, p.returncode == 0, f"modify: exit {p.returncode}: {p.stderr.strip()[:160]}")
    w.git("rm", "-q", ".env")
    p = w.git("commit", "-q", "-m", "delete", check_rc=False)
    check(label, p.returncode == 0, f"delete: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: a rename into a never-commit path is refused")
def _(base):
    label = "pre-commit: a rename into a never-commit path is refused"
    w = World(base, "rename", remote=False)
    w.commit_file("config/settings.txt", "line one\nline two\nline three\n")
    before = w.head()
    w.git("mv", "config/settings.txt", ".env")
    p = w.git("commit", "-q", "-m", "rename", check_rc=False)
    check(label, refused(p) and w.head() == before, f"exit {p.returncode}, HEAD {'moved' if w.head() != before else 'unmoved'}: {p.stderr.strip()[:120]}")


@case("pre-commit: the size limit boundary is 5 MiB")
def _(base):
    label = "pre-commit: the size limit boundary is 5 MiB"
    w = World(base, "size", remote=False)
    p = stage_and_commit(w, {"exact.bin": b"x" * (5 * MIB)})
    check(label, p.returncode == 0, f"exactly 5 MiB: exit {p.returncode}: {p.stderr.strip()[:160]}")
    refused_and_unmoved(label, w, {"over.bin": b"x" * (5 * MIB + 1)}, "5 MiB + 1 byte")


@case("pre-commit: a size limit declared in GUARDRAILS.md is read, and one in a code block is not")
def _(base):
    label = "pre-commit: a size limit declared in GUARDRAILS.md is read, and one in a code block is not"
    w = World(base, "size-decl", remote=False, guardrails="# G\n\n- max-staged-file-mb: 10\n")
    p = stage_and_commit(w, {"six.bin": b"x" * (6 * MIB)})
    check(label, p.returncode == 0, f"declared 10: a 6 MiB file: exit {p.returncode}: {p.stderr.strip()[:160]}")
    refused_and_unmoved(label, w, {"eleven.bin": b"x" * (10 * MIB + 1)}, "10 MiB + 1 byte under a declared 10")
    w2 = World(base, "size-fenced", remote=False, guardrails="# G\n\n```\nmax-staged-file-mb: 50\n```\n\n    max-staged-file-mb: 50\n")
    refused_and_unmoved(label, w2, {"six.bin": b"x" * (6 * MIB)}, "a limit that sits in code was read")


@case("pre-commit: a malformed declared limit is refused, not guessed")
def _(base):
    label = "pre-commit: a malformed declared limit is refused, not guessed"
    w = World(base, "malformed", remote=False, guardrails="# G\n\n- max-new-files-per-commit: plenty\n")
    before = w.head()
    p = stage_and_commit(w, {"a.txt": "a\n"})
    check(label, refused(p) and w.head() == before and "not a whole number" in p.stderr, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: the new-file count boundary is 100")
def _(base):
    label = "pre-commit: the new-file count boundary is 100"
    w = World(base, "count", remote=False)
    p = stage_and_commit(w, {f"gen/a{i}.txt": "x\n" for i in range(100)})
    check(label, p.returncode == 0, f"exactly 100 new files: exit {p.returncode}: {p.stderr.strip()[:160]}")
    refused_and_unmoved(label, w, {f"gen2/b{i}.txt": "x\n" for i in range(101)}, "101 new files")


@case("pre-commit: a declared new-file limit is read")
def _(base):
    label = "pre-commit: a declared new-file limit is read"
    w = World(base, "count-decl", remote=False, guardrails="# G\n\n- max-new-files-per-commit: 150\n")
    p = stage_and_commit(w, {f"gen/a{i}.txt": "x\n" for i in range(150)})
    check(label, p.returncode == 0, f"150 under a declared 150: exit {p.returncode}: {p.stderr.strip()[:160]}")
    refused_and_unmoved(label, w, {f"gen2/b{i}.txt": "x\n" for i in range(151)}, "151 new files under a declared 150")


@case("pre-commit: the first commit of a repository may add any number of files")
def _(base):
    label = "pre-commit: the first commit of a repository may add any number of files"
    w = World(base, "first-c", remote=False, guards=False)
    fresh = base / "fresh"
    fixture_git.init(fresh, "-b", "main")
    for i in range(150):
        (fresh / f"f{i}.txt").write_text("x\n")
    fixture_git.run(fresh, "add", "-A", env=w.env)
    hooks = fresh / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_bytes((PLUGIN / "git-hooks" / "pre-commit").read_bytes())
    (hooks / "pre-commit").chmod(0o755)
    p = fixture_git.run(fresh, "commit", "-q", "-m", "first", check=False, env=w.env)
    check(label, p.returncode == 0, f"150 files in the first commit: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: modified files are not counted as new files")
def _(base):
    label = "pre-commit: modified files are not counted as new files"
    w = World(base, "modified", remote=False, guardrails="# G\n\n- max-new-files-per-commit: 150\n")
    p = stage_and_commit(w, {f"m/f{i}.txt": "a\n" for i in range(150)}, "seed")
    check(label, p.returncode == 0, f"setup: exit {p.returncode}: {p.stderr.strip()[:120]}")
    w.git("config", "--local", "gc.auto", "0")
    (w.work / "GUARDRAILS.md").write_text("# G\n\n- max-new-files-per-commit: 10\n")
    w.git("add", "GUARDRAILS.md")
    w.git("commit", "-q", "-m", "tighten", check_rc=False)
    p = stage_and_commit(w, {f"m/f{i}.txt": "b\n" for i in range(150)}, "edit all")
    check(label, p.returncode == 0, f"150 modified files under a limit of 10 new ones: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: git add -A of a tree with strays is refused however it was spelled")
def _(base):
    label = "pre-commit: git add -A of a tree with strays is refused however it was spelled"
    w = World(base, "addall", remote=False)
    w.write("app/ok.rb", "ok\n")
    w.write("node_modules/dep/index.js", "dep\n")
    w.write(".env", "S=1\n")
    for add in (("add", "-A"), ("add", "."), ("add", "--al"), ("add", "--", "*"), ("add", ":/")):
        before = w.head()
        w.git(*add)
        p = w.git("commit", "-q", "-m", "all", check_rc=False)
        check(label, refused(p) and w.head() == before, f"`git {' '.join(add)}`: exit {p.returncode}, HEAD {'moved' if w.head() != before else 'unmoved'}")
        w.git("reset", "-q")
    w.git("add", "app/ok.rb")
    p = w.git("commit", "-q", "-m", "one file", check_rc=False)
    check(label, p.returncode == 0, f"a commit of the one intended file with strays left unstaged: exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: RAILS_FLOW_STAGING_OK=1 lets a commit through and says so")
def _(base):
    label = "pre-commit: RAILS_FLOW_STAGING_OK=1 lets a commit through and says so"
    w = World(base, "stage-escape", remote=False)
    p = stage_and_commit(w, {".env": "S=1\n"}, env={"RAILS_FLOW_STAGING_OK": "1"})
    check(label, p.returncode == 0, f"exit {p.returncode}: {p.stderr.strip()[:160]}")
    check(label, "RAILS_FLOW_STAGING_OK=1" in p.stderr, "it did not say the check was skipped")


@case("pre-commit: when it cannot create its temp file it refuses")
def _(base):
    label = "pre-commit: when it cannot create its temp file it refuses"
    w = World(base, "notmp", remote=False)
    w.write("a.txt", "a\n")
    w.git("add", "a.txt")
    p = run_hook(w, "pre-commit", env={"TMPDIR": str(base / "does-not-exist")})
    check(label, p.returncode == 1 and "cannot create a temp file" in p.stderr, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


@case("pre-commit: a corrupt index refuses")
def _(base):
    label = "pre-commit: a corrupt index refuses"
    w = World(base, "corrupt", remote=False)
    bad = base / "corrupt-index"
    bad.write_bytes(b"DIRC-not-an-index" * 8)
    p = run_hook(w, "pre-commit", env={"GIT_INDEX_FILE": str(bad)})
    check(label, p.returncode == 1 and "cannot read the index" in p.stderr, f"exit {p.returncode}: {p.stderr.strip()[:160]}")


# ---------------------------------------------------------------------------------------------------------------- installer
@case("installer: both guards are installed where git runs hooks and fire")
def _(base):
    label = "installer: both guards are installed where git runs hooks and fire"
    w = World(base, "inst-plain", remote=False, guards=False)
    p = w.install()
    check(label, p.returncode == 0 and "installed:" in p.stdout, f"exit {p.returncode}: {p.stdout.strip()[:200]}")
    before = w.head()
    q = stage_and_commit(w, {".env": "S=1\n"})
    check(label, refused(q) and w.head() == before, "a real commit of .env was not stopped, so the installed pre-commit does not fire")


@case("installer: with core.hooksPath on a committed directory the guards fire and stay out of git status")
def _(base):
    label = "installer: with core.hooksPath on a committed directory the guards fire and stay out of git status"
    w = World(base, "inst-hp", remote=False, guards=False)
    w.write(".githooks/post-merge", "#!/usr/bin/env bash\nexit 0\n")
    w.git("add", ".githooks/post-merge")
    w.git("commit", "-q", "-m", "team hook")
    w.git("config", "core.hooksPath", ".githooks")
    p = w.install()
    check(label, p.returncode == 0 and (w.work / ".githooks" / "pre-commit").exists(), f"exit {p.returncode}: {p.stdout.strip()[:200]}")
    before = w.head()
    q = stage_and_commit(w, {".env": "S=1\n"})
    check(label, refused(q) and w.head() == before, "the pre-commit guard in the committed hooks directory did not fire")
    status = w.git("status", "--porcelain").stdout
    check(label, ".githooks/pre-commit" not in status and ".githooks/pre-push" not in status, f"the installed guards show in git status: {status!r}")


@case("installer: a linked worktree gets guards that fire")
def _(base):
    label = "installer: a linked worktree gets guards that fire"
    w = World(base, "inst-wt", remote=False, guards=False)
    wt = base / "inst-wt-linked"
    w.git("worktree", "add", "-q", str(wt), "-b", "side")
    env = fixture_git.hermetic(w.env)
    p = subprocess.run(["bash", str(INSTALLER)], cwd=wt, env=env, capture_output=True, text=True)
    check(label, p.returncode == 0, f"exit {p.returncode}: {p.stdout.strip()[:200]}")
    (wt / ".env").write_text("S=1\n")
    subprocess.run(["git", "-C", str(wt), "add", "-f", ".env"], env=env, capture_output=True, text=True)
    q = subprocess.run(["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"], env=env, capture_output=True, text=True)  # fixture-git: exempt (a linked worktree, which fixture_git refuses by design)
    check(label, q.returncode != 0, "a commit of .env from the linked worktree was not stopped")


@case("installer: a tracked hook of the same name is refused and left as it was")
def _(base):
    label = "installer: a tracked hook of the same name is refused and left as it was"
    w = World(base, "inst-tracked", remote=False, guards=False)
    team = "#!/usr/bin/env bash\necho team pre-push\n"
    w.write(".githooks/pre-push", team)
    w.git("add", ".githooks/pre-push")
    w.git("commit", "-q", "-m", "team hook")
    w.git("config", "core.hooksPath", ".githooks")
    p = w.install()
    check(label, p.returncode == 1 and (w.work / ".githooks" / "pre-push").read_text() == team and not w.git("status", "--porcelain").stdout.strip(),
          f"exit {p.returncode}; the committed hook {'CHANGED' if (w.work / '.githooks' / 'pre-push').read_text() != team else 'is unchanged'}")
    check(label, (w.work / ".githooks" / "pre-commit").exists(), "the other guard (pre-commit) was not installed because pre-push was refused")


@case("installer: a tracked copy of our own guard is refused too and left as it was")
def _(base):
    label = "installer: a tracked copy of our own guard is refused too and left as it was"
    w = World(base, "inst-tracked-own", remote=False, guards=False)
    team = (PLUGIN / "git-hooks" / "pre-commit").read_text() + "\n# the team's own edit\n"
    w.write(".githooks/pre-commit", team)
    w.git("add", ".githooks/pre-commit")
    w.git("commit", "-q", "-m", "team copy of the guard")
    w.git("config", "core.hooksPath", ".githooks")
    p = w.install()
    check(label, p.returncode == 1 and (w.work / ".githooks" / "pre-commit").read_text() == team and "is tracked by git" in p.stdout,
          f"exit {p.returncode}; the committed guard {'CHANGED' if (w.work / '.githooks' / 'pre-commit').read_text() != team else 'is unchanged'}: {p.stdout.strip()[:160]}")


@case("installer: a foreign hook that is not tracked is refused and left as it was")
def _(base):
    label = "installer: a foreign hook that is not tracked is refused and left as it was"
    w = World(base, "inst-foreign", remote=False, guards=False)
    mine = "#!/usr/bin/env bash\necho mine\n"
    (w.work / ".git" / "hooks").mkdir(exist_ok=True)
    (w.work / ".git" / "hooks" / "pre-push").write_text(mine)
    p = w.install()
    check(label, p.returncode == 1 and (w.work / ".git" / "hooks" / "pre-push").read_text() == mine and "cannot be chained" in p.stdout,
          f"exit {p.returncode}; {p.stdout.strip()[:200]}")


@case("installer: re-running refreshes a stale guard and reports an unchanged one")
def _(base):
    label = "installer: re-running refreshes a stale guard and reports an unchanged one"
    w = World(base, "inst-twice", remote=False, guards=False)
    w.install()
    again = w.install()
    check(label, again.returncode == 0 and again.stdout.count("unchanged:") == 2, f"second run: {again.stdout.strip()[:200]}")
    hook = w.work / ".git" / "hooks" / "pre-commit"
    hook.write_text(hook.read_text() + "\n# stale\n")
    third = w.install()
    check(label, "updated:" in third.stdout and "# stale" not in hook.read_text(), f"a stale managed guard was not refreshed: {third.stdout.strip()[:200]}")


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
        base = Path(t)
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
    print(f"git-guard selftest: {CHECKS} checks passed in {len(chosen)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
