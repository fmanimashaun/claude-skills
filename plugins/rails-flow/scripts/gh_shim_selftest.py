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
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

PLUGIN = Path(__file__).resolve().parent.parent
SHIM_DIR = PLUGIN / "git-shim"
HOOK = PLUGIN / "hooks" / "scripts" / "guard-pr-ready.sh"
FAILURES: list[str] = []
CHECKS = 0
CASES: list[tuple[str, object]] = []

STUB = """#!/bin/sh
# the real gh, as far as the shim is concerned: records its argv, and answers `alias list`
if [ "$1" = alias ] && [ "$2" = list ]; then printf '%s\\n' "${STUB_ALIASES:-}"; exit 0; fi
printf '%s\\n' "$*" >> "$STUB_LOG"
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
        FAILURES.append(f"{label}: {detail}" if detail else label)


class Fixture:
    """A repository where project_gates runs (a workflow names it), a stub gh behind the shim, and a way to write the sweep record."""

    def __init__(self, base: Path, in_force: bool = True):
        self.base = base
        self.repo = base / "repo"
        fixture_git.init(self.repo, "-b", "main")
        fixture_git.run(self.repo, "config", "user.email", "t@t")
        fixture_git.run(self.repo, "config", "user.name", "t")
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
        self.env.update(HOME=str(home), STUB_LOG=str(self.log), PATH=f"{SHIM_DIR}{os.pathsep}{self.bin}{os.pathsep}{os.environ['PATH']}")

    def record(self, verdict: str = "green", skips: int = 0, head: str | None = None) -> None:
        d = Path(fixture_git.run(self.repo, "rev-parse", "--git-path", "rails-flow/sweep").stdout.strip())
        d = d if d.is_absolute() else self.repo / d
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{self.head}.json").write_text(json.dumps({"head": head or self.head, "verdict": verdict, "skips": skips, "failed": 0, "errored": 0}))

    def sh(self, command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        """A command line, through a real bash, in the checkout, with the shim first on PATH."""
        return subprocess.run(["bash", "-c", command], cwd=self.repo, env={**self.env, **(env or {})}, capture_output=True, text=True, timeout=60)

    def ran(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def reset(self) -> None:
        if self.log.exists():
            self.log.unlink()


def refused(fx: Fixture, command: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    fx.reset()
    r = fx.sh(command, env)
    return (r.returncode != 0 and fx.ran() == []), f"rc {r.returncode}, stub ran {fx.ran()}, {(r.stdout + r.stderr).strip()[-200:]!r}"


def allowed(fx: Fixture, command: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    fx.reset()
    r = fx.sh(command, env)
    return (r.returncode == 0 and len(fx.ran()) == 1), f"rc {r.returncode}, stub ran {fx.ran()}, {(r.stdout + r.stderr).strip()[-200:]!r}"


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


def main(argv: list[str]) -> int:
    match = ""
    if "--match" in argv:
        i = argv.index("--match")
        match = argv[i + 1] if i + 1 < len(argv) else ""
    chosen = [(label, fn) for label, fn in CASES if match in label]
    if not chosen:
        print(f"SELFTEST FAILED -- no case's label contains {match!r}", file=sys.stderr)
        return 1
    for label, fn in chosen:
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
