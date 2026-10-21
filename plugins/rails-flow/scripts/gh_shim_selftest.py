#!/usr/bin/env python3
"""Selftest: the gh shim (#1839) refuses `gh pr ready` unless the sweep record for HEAD is green, from the argv the shell FINALLY hands gh.

Every check runs the shim as `gh` on a real PATH in a real repository, with a STUB gh behind it that records what it was run with. "The shim exited 1" is not the assertion: the
assertion is whether the stub ran. Every refusal has a near miss that must still run, so a shim that refuses every gh command fails here too. The six spellings the hook
`guard-pr-ready.sh` documents as limits of its text match (#1831) are run through a real shell: the HOOK alone lets each of them through, the SHIM refuses each.

    python3 gh_shim_selftest.py               # all cases
    python3 gh_shim_selftest.py --match NAME  # only the cases whose label contains NAME (the mutation runner uses this)
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

for _k, _v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"), ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):  # fixture-git: exempt (an identity for fixture_git.run's own commit; it names no repository)
    os.environ[_k] = _v

PLUGIN = Path(__file__).resolve().parent.parent
SHIM_DIR = PLUGIN / "git-shim"
HOOK = PLUGIN / "hooks" / "scripts" / "guard-pr-ready.sh"
FAILURES: list[str] = []
CHECKS = 0
CURRENT = ""          # the label of the case running: every failure names it, which is what the mutation runner's `expects` (a case label) looks for
CASES: list[tuple[str, object]] = []

STUB = """#!/bin/sh
# the real gh, as far as the shim is concerned: records its argv, and answers `alias list`
if [ "$1" = alias ] && [ "$2" = list ]; then printf '%s\\n' "${STUB_ALIASES:-}"; exit 0; fi
line="$*"; nl='
'; printf '%s\\n' "${line%%"$nl"*}" >> "$STUB_LOG"   # one line per run (the first line of a multi-line inline body), with no external command
echo "stub gh ran"
exit 0
"""


def case(label: str):
    def register(fn):
        CASES.append((label, fn))
        return fn
    return register


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"[{CURRENT}] {label}: {detail}" if detail else f"[{CURRENT}] {label}")


class Fixture:
    """A repository where project_gates runs (a workflow names it), a stub gh behind the shim, and a way to write the sweep record."""

    def __init__(self, base: Path, in_force: bool = True):
        self.base = base
        self.repo = base / "repo"
        fixture_git.init(self.repo, "-b", "main")
        (self.repo / "a.txt").write_text("one\n")
        if in_force:
            wf = self.repo / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "ci.yml").write_text("run: python3 project_gates.py\n")
        fixture_git.run(self.repo, "add", "-A")
        fixture_git.run(self.repo, "commit", "-q", "-m", "init")
        self.head = fixture_git.run(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.bin = base / "realbin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(STUB)
        (self.bin / "gh").chmod(0o755)
        self.log = base / "stub.log"
        home = base / "home"
        home.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RAILS_FLOW_", "GH_")) and k not in {"HOME", "STUB_LOG", "STUB_ALIASES"}}
        import pwd
        self.env.update(HOME=pwd.getpwuid(os.getuid()).pw_dir, STUB_LOG=str(self.log), PATH=f"{SHIM_DIR}{os.pathsep}{self.bin}{os.pathsep}{os.environ['PATH']}")

    def record(self, verdict: str = "green", skips: int = 0, head: str | None = None) -> None:
        d = Path(fixture_git.run(self.repo, "rev-parse", "--git-path", "rails-flow/sweep").stdout.strip())
        d = d if d.is_absolute() else self.repo / d
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{self.head}.json").write_text(json.dumps({"head": head or self.head, "verdict": verdict, "skips": skips, "failed": 0, "errored": 0}))

    def sh(self, command: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """A command line, through a real bash, in the checkout (or `cwd`), with the shim first on PATH."""
        return subprocess.run(["bash", "-c", command], cwd=cwd or self.repo, env={**self.env, **(env or {})}, capture_output=True, text=True, timeout=60)

    def ran(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def reset(self) -> None:
        if self.log.exists():
            self.log.unlink()


def refused(fx: Fixture, command: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> tuple[bool, str]:
    fx.reset()
    r = fx.sh(command, env, cwd)
    return (r.returncode != 0 and fx.ran() == []), f"rc {r.returncode}, stub ran {fx.ran()}, {(r.stdout + r.stderr).strip()[-200:]!r}"


def allowed(fx: Fixture, command: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> tuple[bool, str]:
    fx.reset()
    r = fx.sh(command, env, cwd)
    return (r.returncode == 0 and len(fx.ran()) == 1), f"rc {r.returncode}, stub ran {fx.ran()}, {(r.stdout + r.stderr).strip()[-200:]!r}"


@case("claim bodies")
def _claim_bodies(base: Path) -> None:
    # #2258: the body of `gh pr create` / `pr edit` / `issue comment` is judged here, with the argv the shell expanded and in the real directory, by guard-claims.sh. The hook alone
    # could not tell the directory for a heredoc, a VAR or a `cd` chain (88% of 3,211 real calls), and read nothing of an inline --body or a `--body-file "$F"`. Each shape is run
    # with a body the repository's PR template refuses AND with one it accepts, so a shim that refuses every body fails here too.
    fx = Fixture(base, in_force=False)
    # The shim's judged copies go to THIS case's own TMPDIR: a shared temp directory races with parallel runs (a guard's mutant jobs created and removed
    # their own copies under the leftover check, which then stat'ed a vanished file), and another run's live copy is not a leftover of this one.
    own_tmp = base / "tmp"
    own_tmp.mkdir()
    fx.env["TMPDIR"] = str(own_tmp)
    (fx.repo / ".github").mkdir(exist_ok=True)
    (fx.repo / ".github" / "pull_request_template.md").write_text("## Summary\n\n## Notes\n")
    bad, good = base / "bad.md", base / "good.md"
    bad.write_text("A free-form body with no template sections.\n")
    good.write_text("## Summary\n\nA fix.\n\n## Notes\n\nSee the log.\n")
    for which, body, judge in (("refused", bad, refused), ("allowed", good, allowed)):
        text = body.read_text()
        shapes = {
            "a plain --body-file": f"gh pr create --title t --body-file {body}",
            "a heredoc before gh": f"cat > {body}.h <<'E'\n{text}E\ngh pr create --title t --body-file {body}.h",
            "a cd and a heredoc (pr edit)": f"cd {fx.repo} && cat > {body}.h <<'E'\n{text}E\ngh pr edit 1 --body-file {body}.h",
            "a VAR named as \"$F\"": f'F={body}; gh pr create --title t --body-file "$F"',
            "an inline --body": f'gh pr create --title t --body "$(cat {body})"',
            "an inline --body= (issue comment, no template)": f'gh issue comment 5 --body="$(cat {body})"',
            "a relative --body-file": f"gh pr create --title t --body-file ../{body.name}",
            "a short flag joined to its value (-FPATH)": f"gh pr create --title t -F{body}",
            "a short inline flag (-b=TEXT)": f'gh pr create --title t "-b=$(cat {body})"',
            "a body path with a space and a semicolon": f"cp {body} '{base}/a b;c.md' && gh pr create --title t --body-file '{base}/a b;c.md'",
        }
        for shape, command in shapes.items():
            if which == "refused" and "issue comment" in shape:
                continue      # a comment has no template; its claims are judged below
            ok, why = judge(fx, command)
            check(f"{shape}: a body the template {which.replace('ed', 's')} is {which}", ok, why)
    claim = base / "claim.md"
    claim.write_text("## Summary\n\nIt passed 12 checks.\n\n## Notes\n\nnone\n")
    ok, why = refused(fx, f'gh issue comment 5 --body "$(cat {claim})"')
    check("an inline issue comment making an unchecked number claim is refused", ok, why)
    fx.reset()
    r = fx.sh(f"gh pr create -R someone/else --title t --body-file {bad}")
    check("-R: another repository's template is NOT checked, said on stderr, and the command runs",
          r.returncode == 0 and len(fx.ran()) == 1 and "NOT checked" in r.stderr, f"rc {r.returncode}, {r.stderr.strip()[-160:]!r}")
    ok, why = refused(fx, f"gh pr create -R someone/else --title t --body-file {claim}")
    check("-R: the claims in the body are still judged", ok, why)
    fx.reset()
    r = fx.sh(f"cat {bad} | gh pr create --title t -F -")
    check("a body on stdin is NOT checked, said on stderr, and the command runs",
          r.returncode == 0 and len(fx.ran()) == 1 and "stdin" in r.stderr and "NOT checked" in r.stderr, f"rc {r.returncode}, {r.stderr.strip()[-160:]!r}")
    ok, why = allowed(fx, "gh pr list")
    check("a gh command that carries no body is untouched", ok, why)
    # #2268 review: what the shim does not judge is passed through and SAID, never silent; what it judges is what gh posts.
    for flag in ("--fill", "--fill-first", "--template x.md", "--editor"):
        fx.reset()
        r = fx.sh(f"gh pr create --title t {flag}")
        check(f"`pr create {flag}`: gh composes the body, so it is NOT checked, said, and runs",
              r.returncode == 0 and len(fx.ran()) == 1 and "NOT checked" in r.stderr, f"rc {r.returncode}, {r.stderr.strip()[-160:]!r}")
    for stream in ("/dev/stdin",):
        fx.reset()
        r = fx.sh(f"cat {bad} | gh pr create --title t --body-file {stream}")
        check(f"a body read from {stream} is gh's: NOT checked, said, and gh gets the stream (not an empty copy)",
              r.returncode == 0 and len(fx.ran()) == 1 and "NOT checked" in r.stderr and stream in fx.ran()[0], f"rc {r.returncode}, ran {fx.ran()}, {r.stderr.strip()[-160:]!r}")
    fifo = base / "body.fifo"
    os.mkfifo(fifo)
    fx.reset()
    try:      # no writer: a shim that reads it HANGS, which must be this check failing by name, not the selftest crashing on a timeout
        proc = subprocess.Popen(["bash", "-c", f"gh pr create --title t --body-file {fifo}"], cwd=fx.repo, env=fx.env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        out, err = proc.communicate(timeout=15)
        ok, why = proc.returncode == 0 and len(fx.ran()) == 1 and "NOT checked" in err, f"rc {proc.returncode}, {err.strip()[-160:]!r}"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)       # the whole group: a `cat` blocked on the fifo would otherwise outlive the test
        proc.communicate()
        ok, why = False, "the shim hung reading the fifo (15 s)"
    check("a fifo body is not read by the shim (no hang): NOT checked, said, and it runs", ok, why)
    fx.reset()
    r = fx.sh(f"gh pr create --title t --body-file {bad}", env={"GH_REPO": "someone/else"})
    check("GH_REPO names another repository as -R does: its template is NOT checked, said", r.returncode == 0 and "NOT checked" in r.stderr and "-R" in r.stderr,
          f"rc {r.returncode}, {r.stderr.strip()[-200:]!r}")
    fx.reset()
    r = fx.sh(f'gh pr create --title t --body "$(cat {good})"')
    posted = fx.ran()[0] if fx.ran() else ""
    check("gh is handed the judged copy (--body-file <temp>), not the original flag", r.returncode == 0 and "--body-file" in posted and "--body ##" not in posted,
          f"ran {fx.ran()}")
    leftovers = sorted(own_tmp.glob("rf-gh-body.*"))
    check("the judged copy is removed after gh runs", leftovers == [], f"{leftovers[-3:]}")
    # --web opens gh's browser form: a body given beside it is still judged, and gh gets the judged copy (#2268 review: pin it).
    ok, why = refused(fx, f"gh pr create --title t --body-file {bad} --web")
    check("`--body X --web`: the body is judged (a template miss is refused)", ok, why)
    fx.reset()
    r = fx.sh(f'gh pr create --title t --body "$(cat {good})" --web')
    posted = fx.ran()[0] if fx.ran() else ""
    check("`--body X --web`: a good body runs, with --web kept and the judged copy as --body-file",
          r.returncode == 0 and "--web" in posted and "--body-file" in posted, f"ran {fx.ran()}")
    # A SIGNAL MID-JUDGE ENDS THE SHIM (#2268 review): the trap removed the copy, so carrying on would run gh with a missing --body-file. Timing is not
    # deterministic, so short delays are tried until one lands while the judge runs (the shim exits 143); in that run gh must not have run and no copy may be left.
    landed = None
    for delay in (0.15, 0.3, 0.05, 0.5, 0.1, 0.7, 0.02, 1.0):
        fx.reset()
        for leftover in own_tmp.glob("rf-gh-body.*"):
            leftover.unlink()
        proc = subprocess.Popen(["bash", "-c", f'exec gh pr create --title t --body "$(cat {good})"'], cwd=fx.repo, env=fx.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        time.sleep(delay)
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        if proc.returncode == 143:
            landed = (delay, fx.ran(), sorted(own_tmp.glob("rf-gh-body.*")))
            break
    check("a SIGTERM while the body is judged ends the shim (143): gh never runs and the copy is removed",
          landed is not None and landed[1] == [] and landed[2] == [], f"landed {landed}")
    ok, why = refused(fx, f"gh pc --title t --body-file {bad}", env={"STUB_ALIASES": "pc: pr create"})
    check("an alias that expands to pr create has its body judged", ok, why)
    ok, why = allowed(fx, f"gh pc --title t --body-file {good}", env={"STUB_ALIASES": "pc: pr create"})
    check("an alias that expands to pr create with a good body runs", ok, why)
    ok, why = refused(fx, "gh pr create --title t --body-file /nonexistent/body.md")
    check("a --body-file that cannot be read is refused, not passed unchecked", ok, why)
    # STRICT reaches the hook: a body the claim extractor cannot decode (not UTF-8) is "claims not judged", which the tripwire alone allows and the shim refuses.
    garbled = base / "garbled.md"
    garbled.write_bytes(b"A comment\n\n\xff\xfe not text\n")
    ok, why = refused(fx, f"gh issue comment 5 --body-file {garbled}")
    check("a body the claim extractor cannot read (not UTF-8) is refused: the shim runs the hook strict", ok, why)


@case("no record")
def _no_record(base: Path) -> None:
    fx = Fixture(base)
    ok, why = refused(fx, "gh pr ready 5")
    check("shim: `gh pr ready 5` with no sweep record for HEAD is refused and the real gh never runs", ok, why)
    ok, why = allowed(fx, "gh pr view 5")
    check("shim: CONTROL: `gh pr view 5` is untouched", ok, why)
    ok, why = allowed(fx, "gh pr list --state open")
    check("shim: CONTROL: `gh pr list` is untouched", ok, why)
    ok, why = allowed(fx, "gh issue ready 5")
    check("shim: CONTROL: `ready` under another command (`gh issue ready`) is not `pr ready`", ok, why)
    ok, why = allowed(fx, "gh pr comment 5 --body 'pr ready'")
    check("shim: CONTROL: the words `pr ready` inside one argument are not a `pr ready`", ok, why)
    ok, why = allowed(fx, "gh pr ready --undo 5")
    check("shim: `gh pr ready --undo` passes (marking a PR draft again needs no sweep)", ok, why)
    for cmd, env in (("gh --repo o/r pr ready --undo 5", None), ("gh pr ready --undo 5", {"GH_REPO": "o/r"})):
        ok, why = allowed(fx, cmd, env)
        check(f"shim: `{cmd}`{' with GH_REPO' if env else ''}: --undo harms no repository, so it is judged before the explicit-target refusal (as the hook does)", ok, why)
    for cmd in ("gh pr ready --undo --web 5", "gh pr ready 5 --undo -R o/r", "gh pr ready --undo=false 5"):
        ok, why = refused(fx, cmd)
        check(f"shim: `{cmd}`: `--undo` does not excuse the other arguments, and `--undo=false` is not `--undo`", ok, why)
    # With NO record the mutant `--undo=false` counts as `--undo` is refused anyway (nothing to judge), so the checks above cannot see it.
    # A GREEN record makes the difference observable: `--undo=false` is not a plain PR number and must still be refused.
    fx.record()
    ok, why = refused(fx, "gh pr ready --undo=false 5")
    check("shim: `gh pr ready --undo=false 5` is refused even with a GREEN record: `--undo=false` is not `--undo`", ok, why)
    ok, why = allowed(fx, "gh pr ready 5")
    check("shim: CONTROL: the same green record lets a plain `gh pr ready 5` through", ok, why)


@case("green record")
def _green(base: Path) -> None:
    fx = Fixture(base)
    fx.record()
    ok, why = allowed(fx, "gh pr ready 5")
    check("shim: a green record for HEAD with zero skips lets `gh pr ready 5` through, with its argv unchanged", ok and fx.ran() == ["pr ready 5"], why)
    ok, why = allowed(fx, "gh pr ready some-branch")
    check("shim: ...a branch name too", ok, why)


@case("bad record")
def _bad(base: Path) -> None:
    for label, kw in (("a RED record", dict(verdict="red")), ("a record with skips", dict(skips=2)), ("a record naming another HEAD", dict(head="0" * 40))):
        fx = Fixture(base / label.replace(" ", "-"))
        fx.record(**kw)
        ok, why = refused(fx, "gh pr ready 5")
        check(f"shim: {label} is refused", ok, why)


@case("not in force")
def _not_in_force(base: Path) -> None:
    fx = Fixture(base, in_force=False)
    ok, why = allowed(fx, "gh pr ready 5")
    check("shim: a repository that does not run project_gates is left alone", ok, why)


@case("explicit target")
def _explicit(base: Path) -> None:
    fx = Fixture(base)
    fx.record()
    for label, cmd, env in (("-R", "gh pr ready 5 -R o/r", None), ("--repo", "gh pr ready 5 --repo o/r", None), ("--repo=", "gh pr ready 5 --repo=o/r", None),
                            ("a flag before pr", "gh -R o/r pr ready 5", None), ("-R between pr and ready", "gh pr -R o/r ready 5", None), ("--repo= between pr and ready", "gh pr --repo=o/r ready 5", None), ("a PR URL", "gh pr ready https://github.com/o/r/pull/5", None),
                            ("GH_REPO", "gh pr ready 5", {"GH_REPO": "o/r"})):
        ok, why = refused(fx, cmd, env)
        check(f"shim: a repository named by {label} is refused even with a green record (it cannot be matched to a local one)", ok, why)


@case("allowlist")
def _allowlist(base: Path) -> None:
    fx = Fixture(base)
    fx.record()
    for cmd in ("gh pr ready 5 --body x", "gh pr ready --web 5", "gh pr ready 5 -x"):
        ok, why = refused(fx, cmd)
        check(f"shim: `{cmd}`: an argument that is not a plain PR number or branch is refused", ok, why)


@case("six spellings")
def _spellings(base: Path) -> None:
    """The documented limits of the hook's text match (#1831): each is allowed by the HOOK alone and refused by the SHIM."""
    fx = Fixture(base)
    for label, cmd in (("a variable builds the verb", "x=ready; gh pr $x 5"), ("env in front", "/usr/bin/env gh pr ready 5"),
                       ("a brace expansion", "gh pr rea{d,}y 5"), ("sh reads it from a pipe", "echo 'gh pr ready 5' | sh"),
                       ("bash reads it from a here-string", "bash <<< 'gh pr ready 5'"), ("a git alias runs it", "git -c alias.x='!gh pr ready 5' x")):
        # the hook, alone: it reads the command's text and does not see through any of these
        payload = json.dumps({"tool_name": "Bash", "cwd": str(fx.repo), "tool_input": {"command": cmd}})
        hook = subprocess.run(["bash", str(HOOK)], input=payload, cwd=fx.repo, env={**fx.env, "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}, capture_output=True, text=True, timeout=60)
        check(f"hook alone: {label} (`{cmd}`) is a documented limit, the text match lets it through", hook.returncode == 0, f"hook rc {hook.returncode}: {hook.stderr.strip()[-160:]!r}")
        ok, why = refused(fx, cmd)
        check(f"shim: {label} (`{cmd}`) is refused after the shell has expanded it, and the real gh never runs", ok, why)


@case("alias")
def _alias(base: Path) -> None:
    fx = Fixture(base)
    ok, why = refused(fx, "gh mark 5", {"STUB_ALIASES": "mark: pr ready"})
    check("shim: a gh alias that expands to `pr ready` is judged", ok, why)
    ok, why = allowed(fx, "gh mine", {"STUB_ALIASES": "mine: pr list --author @me"})
    check("shim: CONTROL: a gh alias that expands to something else is untouched", ok, why)
    fx.record()
    ok, why = allowed(fx, "gh mark 5", {"STUB_ALIASES": "mark: pr ready"})
    check("shim: ...and an alias to `pr ready` passes with a green record", ok, why)


@case("escape")
def _escape(base: Path) -> None:
    fx = Fixture(base)
    fx.reset()
    r = fx.sh("gh pr ready 5", {"RAILS_FLOW_GH_OK": "1"})
    check("shim: RAILS_FLOW_GH_OK=1 runs the real gh and says so", r.returncode == 0 and fx.ran() == ["pr ready 5"] and "RAILS_FLOW_GH_OK=1" in r.stderr, f"rc {r.returncode}, {r.stderr.strip()[-160:]!r}")


@case("no python3")
def _no_python(base: Path) -> None:
    fx = Fixture(base)
    bare = base / "bare"
    bare.mkdir()
    for tool in ("bash", "git"):
        found = shutil.which(tool)
        if found:
            (bare / tool).symlink_to(found)
    env = {**fx.env, "PATH": f"{SHIM_DIR}{os.pathsep}{fx.bin}{os.pathsep}{bare}"}
    fx.reset()
    r = subprocess.run([str(bare / "bash"), "-c", "gh pr ready 5"], cwd=fx.repo, env=env, capture_output=True, text=True, timeout=60)
    check("shim: with no python3 a `pr ready` is refused (a guarantee that cannot be checked is not a pass)", r.returncode != 0 and fx.ran() == [], f"rc {r.returncode}, ran {fx.ran()}, {r.stderr.strip()[-160:]!r}")
    fx.reset()
    r = subprocess.run([str(bare / "bash"), "-c", "gh pr list"], cwd=fx.repo, env=env, capture_output=True, text=True, timeout=60)
    check("shim: ...but `gh pr list` still runs with no python3", r.returncode == 0 and fx.ran() == ["pr list"], f"rc {r.returncode}, ran {fx.ran()}")


@case("redirecting variable")
def _redirecting(base: Path) -> None:
    """A GIT_* / GH_HOST / GH_REPO variable can point gh or git at another repository, and used to make the shim fail OPEN (git could not find a repository, so it read as none)."""
    fx = Fixture(base)
    fx.record()                      # a GREEN record: only the variable can explain a refusal
    for var in ("GIT_CONFIG_COUNT=0", "GIT_CONFIG_GLOBAL=/dev/null", "GIT_DIR=/nonexistent", "GIT_WORK_TREE=/tmp", "GH_HOST=ghe.example.com", "GH_REPO=o/r"):
        for how, cmd in (("a prefix", f"{var} gh pr ready 5"), ("env in front", f"/usr/bin/env {var} gh pr ready 5")):
            ok, why = refused(fx, cmd)
            check(f"shim: {var} as {how} is refused even with a green record (it can point gh elsewhere)", ok, why)
    for var in ("HOME=/tmp", "XDG_CONFIG_HOME=/tmp", "GH_CONFIG_DIR=/tmp"):
        ok, why = refused(fx, f"{var} gh pr ready 5")
        check(f"shim: {var}: git and gh read their config from it (a `url.insteadOf` there retargets a PR), so a HOME that is not the account's, or an XDG_CONFIG_HOME, is refused where in force", ok, why)
    for var in ("GH_ENTERPRISE_HOST=x", "GH_CONFIG_DIR=/x", "GIT_NAMESPACE=x", "GIT_ALTERNATE_OBJECT_DIRECTORIES=/x", "GH_SOMETHING_NEW=1"):
        ok, why = refused(fx, f"{var} gh pr ready 5")
        check(f"shim: {var}: an allowlist of the harmless, not a list of the dangerous: any other GIT_*/GH_* variable is refused where in force", ok, why)
    for var in ("GIT_EDITOR=true", "GH_TOKEN=t", "GIT_AUTHOR_NAME=a", "GH_PROMPT_DISABLED=1"):
        ok, why = allowed(fx, f"{var} gh pr ready 5")
        check(f"shim: CONTROL: {var} points nowhere, so it is not refused", ok, why)
    nofx = Fixture(base / "nf", in_force=False)
    ok, why = allowed(nofx, "GH_REPO=o/r gh pr ready 5")
    check("shim: IN FORCE ONLY where project_gates runs: a named repository from a repository that does not run it is not checked (the stated carve-out)", ok, why)
    outside = base / "outside"
    outside.mkdir()
    ok, why = allowed(fx, "GH_REPO=o/r gh pr ready 5", cwd=outside)
    check("shim: ...nor from a directory outside any repository", ok, why)


@case("git cannot answer")
def _git_down(base: Path) -> None:
    fx = Fixture(base)
    fx.record()
    broken = base / "brokengit"
    broken.mkdir()
    (broken / "git").write_text("#!/bin/sh\necho 'fatal: something git could not explain' >&2\nexit 128\n")
    (broken / "git").chmod(0o755)
    ok, why = refused(fx, "gh pr ready 5", {"PATH": f"{broken}{os.pathsep}{fx.env['PATH']}"})
    check("shim: where git cannot answer (it fails for a reason that is not `not a git repository`) a `pr ready` is refused, not read as outside any repository, even with a green record", ok, why)
    outside = base / "outside2"
    outside.mkdir()
    ok, why = allowed(fx, "gh pr ready 5", cwd=outside)
    check("shim: CONTROL: outside any repository (git says so) a `pr ready` is not this shim's business", ok, why)


@case("alias flags")
def _alias_flags(base: Path) -> None:
    fx = Fixture(base)
    for cmd in ("gh -R o/r rdy 5", "gh --repo o/r rdy 5", "gh --repo=o/r rdy 5"):
        ok, why = refused(fx, cmd, {"STUB_ALIASES": "rdy: pr ready"})
        check(f"shim: `{cmd}`: an alias after a flag with a value is still resolved and judged", ok, why)
    ok, why = refused(fx, "gh rdy 5", {"STUB_ALIASES": "rdy:\tpr ready"})
    check("shim: an alias whose expansion follows the colon after a TAB is read", ok, why)
    ok, why = refused(fx, "gh rdy 5", {"STUB_ALIASES": "rdy:    pr ready"})
    check("shim: ...or after several spaces", ok, why)
    for exp in ("'pr' ready", 'pr "ready"', "pr\\ ready", 'pr "rea"dy', "pr re\\ady", "pr 'rea'dy", 'a"p"i graphql -f query=mutation{markPullRequestReadyForReview(input:{pullRequestId:"x"}){clientMutationId}}'):
        ok, why = refused(fx, "gh rdy 5", {"STUB_ALIASES": f"rdy: {exp}"})
        check(f"shim: an alias expansion that is not plain words is refused where in force, whatever it mentions, and never un-quoted: {exp[:40]}", ok, why)
    ok, why = refused(fx, "gh mine", {"STUB_ALIASES": "mine: pr list --search \"a b\""})
    check("shim: ...so even a harmless quoted expansion is refused where in force (the stated cost of an allowlist; RAILS_FLOW_GH_OK=1 is the escape)", ok, why)
    # THE REAL FORMAT of `gh alias list` (gh 2.102.0, measured by the adversary): YAML, so a multi-line expansion is a block scalar, not `name: expansion` on one line (review of 1d2151c9, M1)
    for shape, listing in (("a `|-` block scalar", "rdy2: |-\n    pr\n    ready"), ("a `>` folded scalar", "rdy2: >-\n    pr\n    ready"), ("a first line of plain words and an indented continuation", "rdy2: pr\n    ready"),
                           ("a block scalar followed by another alias", "rdy2: |-\n    pr\n    ready\nother: pr list")):
        ok, why = refused(fx, "gh rdy2 5", {"STUB_ALIASES": listing})
        check(f"shim: a multi-line alias expansion as `gh alias list` prints it ({shape}) is refused where in force, not read as its first line", ok, why)
    ok, why = allowed(fx, "gh other", {"STUB_ALIASES": "rdy2: |-\n    pr\n    ready\nother: pr list"})
    check("shim: CONTROL: the alias AFTER a multi-line one is read as its own single line and untouched", ok, why)
    nof = Fixture(base / "nf2", in_force=False)
    ok, why = allowed(nof, "gh mine", {"STUB_ALIASES": "mine: pr list --search \"a b\""})
    check("shim: CONTROL: ...and it runs where project_gates does not", ok, why)


@case("alias placeholder")
def _alias_placeholder(base: Path) -> None:
    fx = Fixture(base)
    fx.record()
    ok, why = allowed(fx, "gh rdy 5", {"STUB_ALIASES": "rdy: pr ready $1"})
    check("shim: an alias with a `$1` placeholder is judged by what gh will RUN (`pr ready 5`): a green record lets it through", ok, why)
    ok, why = allowed(fx, "gh rdy 5", {"STUB_ALIASES": 'rdy: pr ready "$1"'})
    check("shim: a quoted placeholder (`\"$1\"`) is the placeholder", ok, why)
    ok, why = refused(fx, "gh rdy 5 -R o/r", {"STUB_ALIASES": "rdy: pr ready $1"})
    check("shim: ...and the arguments after the placeholder are appended and judged (`-R o/r` is refused)", ok, why)
    fx2 = Fixture(base / "nr")
    ok, why = refused(fx2, "gh rdy 5", {"STUB_ALIASES": "rdy: pr ready $1"})
    check("shim: ...and with no record the same alias is refused", ok, why)


@case("gh api")
def _api(base: Path) -> None:
    fx = Fixture(base)
    mutation = "gh api graphql -f query='mutation{markPullRequestReadyForReview(input:{pullRequestId:\"x\"}){clientMutationId}}'"
    ok, why = refused(fx, mutation)
    check("shim: a `gh api graphql` that marks a PR ready is refused with no sweep record", ok, why)
    ok, why = refused(fx, "gh api graphql --input q.json")
    check("shim: a `gh api` whose body comes from a file cannot be judged, so it is refused where in force", ok, why)
    ok, why = refused(fx, "gh api graphql -F query=@q.graphql")
    check("shim: ...also as `-F field=@file`", ok, why)
    fxr = Fixture(base / "r2")
    fxr.record()
    ok, why = refused(fxr, "gh -R o/r api graphql -f query='mutation{markPullRequestReadyForReview(input:{pullRequestId:\"x\"}){clientMutationId}}'")
    check("shim: a `gh api` naming a repository or host is refused where in force even with a green record", ok, why)
    ok, why = refused(fxr, "gh api --hostname ghe.example.com graphql -f query='mutation{markPullRequestReadyForReview(input:{pullRequestId:\"x\"}){clientMutationId}}'")
    check("shim: ...also --hostname", ok, why)
    ok, why = allowed(fx, "gh api user")
    check("shim: CONTROL: `gh api user` is untouched", ok, why)
    ok, why = allowed(fx, "gh api repos/o/r/pulls/5 -f title=x")
    check("shim: CONTROL: another `gh api` call with a field is untouched", ok, why)
    fx.record()
    ok, why = allowed(fx, mutation)
    check("shim: ...and the mutation passes with a green record for HEAD", ok, why)


@case("two shims")
def _two_shims(base: Path) -> None:
    fx = Fixture(base)
    copy_dir = base / "copy"
    copy_dir.mkdir()
    shutil.copy(SHIM_DIR / "gh", copy_dir / "gh")
    env = {"PATH": f"{SHIM_DIR}{os.pathsep}{copy_dir}{os.pathsep}{fx.bin}{os.pathsep}{os.environ['PATH']}"}
    # A real loop (two shims exec each other) never ends; a loaded machine only takes longer. A fixed 8 s limit read the sweep's load as a
    # loop (#1156 sweep: the UNMUTATED fixture timed out), so the limit is derived from one measured shim hop under the SAME load.
    fx.reset()
    t0 = time.monotonic()
    one = subprocess.run(["bash", "-c", "gh pr list"], cwd=fx.repo, env=fx.env, capture_output=True, text=True, timeout=120)
    hop = time.monotonic() - t0
    limit = max(30.0, 20 * hop)
    fx.reset()
    try:
        r = subprocess.run(["bash", "-c", "gh pr list"], cwd=fx.repo, env={**fx.env, **env}, capture_output=True, text=True, timeout=limit)
        looped = False
    except subprocess.TimeoutExpired:
        r, looped = None, True
    check("shim: a second copy of the shim on PATH is not taken for the real gh (it would exec itself forever)", not looped and r is not None and r.returncode == 0 and fx.ran() == ["pr list"],
          f"timed out after {limit:.0f}s (one hop took {hop:.1f}s, rc {one.returncode}): the two shims exec each other" if looped else f"rc {r.returncode}, ran {fx.ran()}")


@case("interpreter")
def _interpreter(base: Path) -> None:
    """The judge must not be a python3 the repository ships: one that exits 0 would read as `allowed`."""
    fx = Fixture(base)
    witness = base / "repo-python-ran"
    (fx.repo / "bin").mkdir(exist_ok=True)
    (fx.repo / "bin" / "python3").write_text(f"#!/bin/sh\n: > {witness}\nexit 0\n")
    (fx.repo / "bin" / "python3").chmod(0o755)
    ok, why = refused(fx, "gh pr ready 5", {"PATH": f"{fx.repo / 'bin'}{os.pathsep}{fx.env['PATH']}"})
    check("shim: a python3 the repository ships, first on PATH by an absolute entry, is NOT the judge (it would exit 0 and read as allowed)", ok and not witness.exists(), why + f", repo python ran: {witness.exists()}")
    ok, why = refused(fx, "gh pr ready 5", {"PATH": f"bin{os.pathsep}.{os.pathsep}{fx.env['PATH']}"})
    check("shim: ...nor one reached through a relative or `.` PATH entry", ok and not witness.exists(), why + f", repo python ran: {witness.exists()}")


@case("real gh path")
def _real_gh_path(base: Path) -> None:
    """The real gh must not be one the repository ships, by an absolute entry inside it or a relative/empty one: it would answer `alias list` and run for every unjudged command."""
    fx = Fixture(base)
    witness = base / "repo-gh-ran"
    plant = f"#!/bin/sh\n: > {witness}\nexit 0\n"
    (fx.repo / "bin").mkdir(exist_ok=True)
    for where in (fx.repo / "bin" / "gh", fx.repo / "gh"):
        where.write_text(plant)
        where.chmod(0o755)
    sep = os.pathsep
    outside = base / "outside"  # a directory that is no checkout, so only the relative-entry rule (not the in-checkout one) can refuse its gh
    (outside / "bin").mkdir(parents=True)
    for where in (outside / "bin" / "gh", outside / "gh"):
        where.write_text(plant)
        where.chmod(0o755)
    for label, entries, cwd in (("an absolute PATH entry inside the checkout", f"{fx.repo / 'bin'}{sep}", None),
                                ("a relative PATH entry", f"bin{sep}", outside), ("an empty PATH entry", f"{sep}", outside), ("a `.` PATH entry", f".{sep}", outside)):
        env = {"PATH": f"{SHIM_DIR}{sep}{entries}{fx.bin}{sep}{os.environ['PATH']}"}
        ok, why = allowed(fx, "gh pr list", env, cwd)
        check(f"shim: a gh the repository ships, reached by {label}, is not the real gh (the real one runs)", ok and fx.ran() == ["pr list"] and not witness.exists(), why + f", repo gh ran: {witness.exists()}")
        witness.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    match = ""
    if "--match" in argv:
        i = argv.index("--match")
        match = argv[i + 1] if i + 1 < len(argv) else ""
    chosen = [(label, fn) for label, fn in CASES if match in label]
    if not chosen:
        print(f"SELFTEST FAILED -- no case's label contains {match!r}", file=sys.stderr)
        return 1
    global CURRENT
    for label, fn in chosen:
        CURRENT = label
        td = tempfile.mkdtemp(prefix="ghshim-")
        try:
            fn(Path(td))
        finally:
            shutil.rmtree(td, ignore_errors=True)
    if FAILURES:
        print(f"gh-shim selftest FAILED -- {len(FAILURES)} of {CHECKS}:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"gh-shim selftest: {CHECKS} checks passed in {len(chosen)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
