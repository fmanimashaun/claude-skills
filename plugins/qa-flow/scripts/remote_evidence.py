#!/usr/bin/env python3
"""Judge the release-only layers (#1428) of a repository this checkout is NOT, from the evidence as committed there.

Run:  python3 remote_evidence.py --repo OWNER/REPO --sha FULL_SHA [--budget SECONDS]
      python3 remote_evidence.py --selftest

WHY (#1591). `release_evidence.py stamp --rev R` judges the first-boot walkthrough and the authorization
sweep a PASS stamp names, from the files COMMITTED at R, in the repository it runs in. The release gate
holds this checkout to that, and used to hold every OTHER repository (`gh -R`, `GH_REPO`, a `repos/<o>/<r>`
path, a second remote) to less: a bare PASS stamp was enough, because their evidence files are not here.

WHAT IT DOES. It fetches the one commit into a scratch repository (depth 1, no file contents, so only
the commit and its trees come across; `git archive` then fetches the few evidence files it needs), fetches
the last PUBLISHED release (`refs/heads/main`, when the repository has one) so the same copied-evidence and
already-published checks run, and runs `release_evidence.py stamp --rev SHA` there. The judgement is the
same code, not a copy of it. Its output and exit code are passed through unchanged:
0 clean (stdout lists the evidence paths the release gate lets the stamp's commit carry), 1 findings
(`FAIL` lines on stderr), 2 unusable.

FAIL CLOSED, AND INSIDE THE HOOK'S TIME. A PreToolUse hook that outlives its timeout does not deny, so
this stops by itself: every step gets what is left of `--budget` (default 8 s) and a step that cannot
finish is exit 2 "unusable", which the gate turns into a denial. Anything it cannot fetch, resolve or run is
exit 2 for the same reason; an error never reads as "the evidence is fine". A repository whose `main` cannot
be listed is unusable too, and one that has no `main` is a repository with nothing published yet.

Two things are weaker than for this checkout, in the strict direction. The scratch repository has no history,
so a stamp with no `schema` is dated by the commit that is judged (`git log` sees one commit), never by the
commit that wrote the stamp: such a stamp is refused unless that commit predates the #1428 cutoff.
The commit must be given in full (40 hex digits); a short one is unusable.
Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_BUDGET = 8.0      # the release gate (hook timeout 15 s) passes what it has left, never more than this
HERE = Path(__file__).resolve().parent


class Unusable(Exception):
    """The evidence could not be fetched or judged: nothing is read as 'the evidence is fine'."""


class Clock:
    """What is left of the budget, so no step can outlive it."""

    def __init__(self, budget: float, now=time.monotonic):
        self.now, self.end = now, now() + budget

    def left(self) -> float:
        return self.end - self.now()


def git(clock: Clock, cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    left = clock.left()
    if left <= 0:
        raise Unusable("the time budget ran out before the evidence could be read")
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=left,
                              stdin=subprocess.DEVNULL, env=env)
    except subprocess.TimeoutExpired as exc:
        raise Unusable("a git step did not finish within the time budget") from exc
    except OSError as exc:
        raise Unusable(f"git cannot run: {exc}") from exc


def snapshot(clock: Clock, repo: str, sha: str, scratch: Path, url: str | None = None) -> None:
    """Fetch the commit (and the published `main`, when there is one) into `scratch`."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    # gh already holds the credentials this machine pushes with; ask it, never a prompt.
    cred = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    steps = (("init", "-q"), ("remote", "add", "origin", url or f"https://github.com/{repo}.git"))
    for step in steps:
        done = git(clock, scratch, *step, env=env)
        if done.returncode != 0:
            raise Unusable(f"git {step[0]} failed: {done.stderr.strip()[:200]}")
    fetch = [*cred, "fetch", "-q", "--depth=1", "--filter=blob:none", "--no-tags", "origin"]
    done = git(clock, scratch, *fetch, sha, env=env)
    if done.returncode != 0:
        raise Unusable(f"{repo} at {sha[:12]} could not be fetched: {done.stderr.strip()[:200]}")
    listed = git(clock, scratch, *cred, "ls-remote", "origin", "refs/heads/main", env=env)
    if listed.returncode != 0:
        raise Unusable(f"the published release of {repo} could not be listed: {listed.stderr.strip()[:200]}")
    if listed.stdout.strip():
        done = git(clock, scratch, *fetch, "+refs/heads/main:refs/remotes/origin/main", env=env)
        if done.returncode != 0:
            raise Unusable(f"the published release of {repo} could not be fetched: {done.stderr.strip()[:200]}")


def judge(clock: Clock, repo: str, sha: str, url: str | None = None, evidence_script: Path | None = None) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="qa-remote-evidence."))
    try:
        snapshot(clock, repo, sha, scratch, url)
        left = clock.left()
        if left <= 0:
            raise Unusable("the time budget ran out before the evidence could be judged")
        try:
            done = subprocess.run([sys.executable, str(evidence_script or HERE / "release_evidence.py"), "stamp", "--rev", sha],
                                  cwd=scratch, capture_output=True, text=True, timeout=left, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise Unusable("the evidence was not judged within the time budget") from exc
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        return done.returncode
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo")
    ap.add_argument("--sha")
    ap.add_argument("--budget", type=float, default=DEFAULT_BUDGET)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        if not args.repo or not REPO.match(args.repo):
            raise Unusable(f"--repo must be OWNER/REPO, got {args.repo!r}")
        if not args.sha or not SHA.match(args.sha):
            raise Unusable(f"--sha must be a full 40-digit commit, got {args.sha!r}")
        return judge(Clock(args.budget), args.repo, args.sha)
    except Unusable as exc:
        print(f"unusable: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE


# --------------------------------------------------------------------------- selftest
def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def check(label: str, ok: bool, detail: object = "") -> None:
        ran[0] += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def run(*argv: str) -> tuple[int, str]:
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), *argv], capture_output=True, text=True, timeout=120)
        return done.returncode, done.stderr

    # Arguments are refused before anything is fetched, and BY THEIR OWN MESSAGE: a value wrongly let through would end as
    # "unusable" too (a failed network fetch), so only the validation message tells a refusal from an accident.
    repo_msg, sha_msg = "--repo must be OWNER/REPO", "--sha must be a full 40-digit commit"
    for label, argv, want in (("no repository", ["--sha", "a" * 40], repo_msg),
                              ("no commit", ["--repo", "o/r"], sha_msg),
                              ("a short commit", ["--repo", "o/r", "--sha", "abc1234"], sha_msg),
                              ("an upper-case commit", ["--repo", "o/r", "--sha", "A" * 40], sha_msg),
                              ("a repository that is a URL", ["--repo", "https://github.com/o/r", "--sha", "a" * 40], repo_msg),
                              ("a repository with a space", ["--repo", "o/r x", "--sha", "a" * 40], repo_msg),
                              ("a repository that names an option", ["--repo=--upload-pack=x/y", "--sha", "a" * 40], repo_msg)):
        rc, err = run(*argv)
        check(f"{label} is unusable, not fetched", rc == EXIT_UNUSABLE and want in err, f"rc={rc} {err!r}")

    clock = Clock(10, now=iter([0.0, 3.0, 11.0]).__next__)
    check("a clock reports what is left", clock.left() == 7.0)
    check("a spent clock reports nothing left", clock.left() < 0)
    try:
        git(Clock(-1), Path("."), "status")
        check("a step started with no time left is refused", False, "ran")
    except Unusable as exc:
        check("a step started with no time left is refused", "ran out" in str(exc), str(exc))

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        saved_tmp, tempfile.tempdir = tempfile.tempdir, str(d)     # scratch repositories land here, not in a shared /tmp
        g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        src = d / "src.git"
        subprocess.run(["git", "init", "-q", "--bare", str(src)], check=True)
        work = d / "work"
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        (work / "a.txt").write_text("a\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.txt"], cwd=work, check=True)
        subprocess.run([*g, "commit", "-q", "-m", "a"], cwd=work, check=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "push", "-q", str(src), "HEAD:refs/heads/dev"], cwd=work, check=True)
        for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
            subprocess.run(["git", "config", k, v], cwd=src, check=True)
        fake = d / "evidence.py"
        fake.write_text("import sys\nprint('qa/manual-tests/first-boot-v1/')\nprint('judged', sys.argv[1:], file=sys.stderr)\nsys.exit(0)\n",
                        encoding="utf-8")
        out = d / "out"
        out.mkdir()

        def judged(commit: str, url: str, script: Path, budget: float = 30) -> tuple[int, str, str]:
            keep = (sys.stdout, sys.stderr)
            with open(out / "o", "w+", encoding="utf-8") as so, open(out / "e", "w+", encoding="utf-8") as se:
                sys.stdout, sys.stderr = so, se
                try:
                    try:
                        rc = judge(Clock(budget), "o/r", commit, url=url, evidence_script=script)
                    except Unusable as exc:
                        print(f"unusable: {exc}", file=sys.stderr)
                        rc = EXIT_UNUSABLE
                finally:
                    sys.stdout, sys.stderr = keep
                so.seek(0), se.seek(0)
                return rc, so.read(), se.read()

        rc, so, se = judged(sha, str(src), fake)
        check("a fetched commit is judged by release_evidence in the scratch repository", rc == 0 and "first-boot-v1/" in so
              and "'stamp', '--rev'" in se, f"rc={rc} {so!r} {se!r}")
        fake.write_text("import sys\nprint('FAIL layer: HOLE', file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")
        rc, so, se = judged(sha, str(src), fake)
        check("a finding is passed through as exit 1", rc == 1 and "HOLE" in se, f"rc={rc} {se!r}")
        fake.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        rc, _, _ = judged(sha, str(src), fake)
        check("an unusable verdict is passed through as exit 2", rc == 2, rc)
        rc, _, se = judged("b" * 40, str(src), fake)
        check("a commit that does not exist is unusable", rc == EXIT_UNUSABLE and "could not be fetched" in se, f"rc={rc} {se!r}")
        rc, _, se = judged(sha, str(d / "nowhere"), fake)
        check("a repository that cannot be reached is unusable", rc == EXIT_UNUSABLE, f"rc={rc} {se!r}")
        slow = d / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        started = time.monotonic()
        rc, _, se = judged(sha, str(src), slow, budget=4)
        check("a judge that outlives the budget is unusable, and stops at the budget", rc == EXIT_UNUSABLE
              and "time budget" in se and time.monotonic() - started < 15, f"rc={rc} {se!r} {time.monotonic() - started:.1f}s")
        leftovers = [p for p in d.glob("qa-remote-evidence.*")]
        check("no scratch repository is left behind", not leftovers, leftovers)
        tempfile.tempdir = saved_tmp

    for f in failures:
        print(f"SELFTEST FAILED: {f}", file=sys.stderr)
    print(f"remote_evidence selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
