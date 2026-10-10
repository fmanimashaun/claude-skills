#!/usr/bin/env python3
"""Judge the release-only layers (#1428) of a repository this checkout is NOT, from the evidence as committed there.

Run:  python3 remote_evidence.py --repo OWNER/REPO --sha FULL_SHA --record [--budget SECONDS]   (BEFORE the promotion)
      python3 remote_evidence.py --repo OWNER/REPO --sha FULL_SHA --check-verdict --tree TREE_ID  (what the release gate runs)
      python3 remote_evidence.py --repo OWNER/REPO --sha FULL_SHA [--budget SECONDS]              (judge, print, record nothing)
      python3 remote_evidence.py --selftest

WHY A SEPARATE STEP (#1686). Judging a repository with real evidence took 35.7 s wall (measured against a 2055-file `qa/`,
`--filter=blob:none` turns every blob it reads into a network round trip), and the hook has 15 s. So the judgement runs here, ahead of
the promotion, with minutes to spare, and writes a VERDICT FILE that the release gate only READS. A verdict is keyed by repository,
the exact commit and the evidence tree id (`git rev-parse SHA:qa`, which the gate recomputes in one API call), expires after 30
minutes, lives in `~/.claude/qa-flow/remote-verdicts` (never in a repository, so it cannot be committed), and anything missing, stale,
unparsable, mismatched or FAIL refuses, naming which one it was and the command to run.
THREAT MODEL: this guards against an ACCIDENTAL promotion, not against a session that hand-writes a PASS file.

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
import json
import os
import re
import shutil
import signal
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
VERDICT_TTL = 30 * 60     # seconds a recorded verdict is honoured (#1686)


def verdict_path(repo: str, sha: str) -> Path:
    """Where the verdict for (repo, sha) lives: `~/.claude/qa-flow/remote-verdicts`, never inside a repository. It does NOT depend on
    CLAUDE_PLUGIN_DATA: Claude Code gives that variable to hook processes and NOT to Bash-tool commands (code.claude.com/docs/en/plugins/manifest-reference.md),
    and the recording runs through Bash while the gate runs as a hook, so the two would have looked in different places. QA_FLOW_VERDICT_DIR is for tests."""
    base = os.environ.get("QA_FLOW_VERDICT_DIR") or str(Path.home() / ".claude" / "qa-flow")
    return Path(base) / "remote-verdicts" / f"{repo.replace('/', '__')}@{sha}.json"


def read_verdict(repo: str, sha: str, tree: str, now: float | None = None) -> tuple[str, str]:
    """(kind, detail). kind is "ok" only for a fresh PASS recorded for exactly this repo, commit and evidence tree; detail is then the
    evidence listing the gate lets the stamp's commit carry. Every other kind is a refusal: missing, unparsable, mismatch, stale, FAIL."""
    path = verdict_path(repo, sha)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return "missing", "no verdict has been recorded for this commit"
    except OSError as exc:
        return "unparsable", f"the verdict file could not be read: {exc}"
    try:
        v = json.loads(text)
        if not isinstance(v, dict) or not all(k in v for k in ("repo", "sha", "tree", "verdict", "at", "evidence")):
            raise ValueError("a field is missing")
        at = float(v["at"])
    except (ValueError, TypeError) as exc:
        return "unparsable", f"the verdict file is not a verdict: {exc}"
    if v["repo"] != repo or v["sha"] != sha:
        return "mismatch", f"the verdict is for {v['repo']}@{str(v['sha'])[:12]}, not {repo}@{sha[:12]}"
    if not tree or v["tree"] != tree:
        return "mismatch", f"the evidence tree is {tree[:12] or 'unknown'} but the verdict judged {str(v['tree'])[:12]}"
    if (time.time() if now is None else now) - at > VERDICT_TTL:
        return "stale", "the verdict is older than 30 minutes"
    if at > (time.time() if now is None else now) + 60:
        return "unparsable", "the verdict is dated in the future"
    if v["verdict"] != "PASS":
        return "FAIL", str(v.get("why") or "the release-only layers do not pass")
    return "ok", str(v["evidence"])


def record(clock: Clock, repo: str, sha: str, url: str | None = None, evidence_script: Path | None = None) -> int:
    """Judge as `judge` does, and write the verdict file. Exit 0 PASS, 1 FAIL (both recorded); unusable records nothing."""
    scratch = Path(tempfile.mkdtemp(prefix="qa-remote-evidence."))
    try:
        snapshot(clock, repo, sha, scratch, url)
        tree = git(clock, scratch, "rev-parse", f"{sha}:qa")
        if tree.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", tree.stdout.decode().strip() if isinstance(tree.stdout, bytes) else tree.stdout.strip()):
            raise Unusable(f"{repo} at {sha[:12]} has no qa/ tree to judge")
        tree_id = tree.stdout.decode().strip() if isinstance(tree.stdout, bytes) else tree.stdout.strip()
        left = clock.left()
        if left <= 0:
            raise Unusable("the time budget ran out before the evidence could be judged")
        try:
            done = run_group([sys.executable, str(evidence_script or HERE / "release_evidence.py"), "stamp", "--rev", sha], scratch, left)
        except subprocess.TimeoutExpired as exc:
            raise Unusable("the evidence was not judged within the time budget") from exc
        out, err = done.stdout, done.stderr
        out = out.decode() if isinstance(out, bytes) else out
        err = err.decode() if isinstance(err, bytes) else err
        if done.returncode not in (EXIT_OK, EXIT_FINDINGS):
            raise Unusable(f"release_evidence.py could not judge it: {err.strip()[:200]}")
        why = " ".join(line for line in err.splitlines() if line.startswith("FAIL"))[:600]
        body = {"repo": repo, "sha": sha, "tree": tree_id, "verdict": "PASS" if done.returncode == EXIT_OK else "FAIL",
                "at": time.time(), "evidence": out, "why": why}
        path = verdict_path(repo, sha)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(body, fh)
        os.replace(tmp, path)
        sys.stderr.write(err)
        print(f"recorded {body['verdict']} for {repo}@{sha[:12]} (evidence tree {tree_id[:12]}), good for 30 minutes: {path}")
        return done.returncode
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


class Unusable(Exception):
    """The evidence could not be fetched or judged: nothing is read as 'the evidence is fine'."""


class Clock:
    """What is left of the budget, so no step can outlive it."""

    def __init__(self, budget: float, now=time.monotonic):
        self.now, self.end = now, now() + budget

    def left(self) -> float:
        return self.end - self.now()


def run_group(argv: list, cwd: Path, timeout: float, env: dict | None = None) -> subprocess.CompletedProcess:
    """`subprocess.run`, in its own session, so a timeout kills EVERY process the step started. `subprocess.run(timeout=)`
    kills only the direct child: git forks `git-remote-https` and a credential helper, and those ran on after the helper had
    given up (the straggler class of #1575). Raises `subprocess.TimeoutExpired` after killing the group."""
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                            text=True, env=env, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.communicate(timeout=5)         # reap it; never wait on a pipe a leaver still holds
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def git(clock: Clock, cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    left = clock.left()
    if left <= 0:
        raise Unusable("the time budget ran out before the evidence could be read")
    try:
        return run_group(["git", *args], cwd, left, env)
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
            done = run_group([sys.executable, str(evidence_script or HERE / "release_evidence.py"), "stamp", "--rev", sha],
                             scratch, left)
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
    ap.add_argument("--record", action="store_true", help="judge, then write the verdict file the release gate reads (#1686)")
    ap.add_argument("--check-verdict", action="store_true", help="read the recorded verdict; exit 0 only for a fresh matching PASS")
    ap.add_argument("--tree", help="with --check-verdict: the evidence tree id, `git rev-parse SHA:qa`")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        if not args.repo or not REPO.match(args.repo):
            raise Unusable(f"--repo must be OWNER/REPO, got {args.repo!r}")
        if not args.sha or not SHA.match(args.sha):
            raise Unusable(f"--sha must be a full 40-digit commit, got {args.sha!r}")
        if args.check_verdict:
            kind, detail = read_verdict(args.repo, args.sha, args.tree or "")
            if kind == "ok":
                sys.stdout.write(detail)
                return EXIT_OK
            print(f"{kind}: {detail}", file=sys.stderr)
            return EXIT_FINDINGS if kind == "FAIL" else EXIT_UNUSABLE
        if args.record:
            return record(Clock(args.budget), args.repo, args.sha)
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
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fixture_git  # (#1588) the fixture's git touches only its own temp repo
        src = d / "src.git"
        subprocess.run(["git", "init", "-q", "--bare", str(src)], check=True)
        work = fixture_git.init(d / "work")
        (work / "a.txt").write_text("a\n", encoding="utf-8")
        fixture_git.run(work, "add", "a.txt")
        fixture_git.run(work, "commit", "-q", "-m", "a")
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
        # (#1686) A verdict is recorded ahead of the promotion and READ by the gate: keyed by repository, commit and evidence tree id,
        # good for 30 minutes, outside every repository. A commit with no qa/ tree has nothing to judge and records nothing.
        (work / "qa").mkdir()
        (work / "qa" / "e.txt").write_text("e\n", encoding="utf-8")
        fixture_git.run(work, "add", "qa")
        fixture_git.run(work, "commit", "-q", "-m", "qa")
        sha2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        tree2 = subprocess.run(["git", "rev-parse", "HEAD:qa"], cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "push", "-q", str(src), "HEAD:refs/heads/dev"], cwd=work, check=True)
        saved_data = os.environ.get("QA_FLOW_VERDICT_DIR")
        os.environ["QA_FLOW_VERDICT_DIR"] = str(d / "data")

        def recorded(commit: str, script: Path) -> tuple[int, str]:
            keep = (sys.stdout, sys.stderr)
            with open(out / "ro", "w+", encoding="utf-8") as so, open(out / "re", "w+", encoding="utf-8") as se:
                sys.stdout, sys.stderr = so, se
                try:
                    try:
                        rc = record(Clock(30), "o/r", commit, url=str(src), evidence_script=script)
                    except Unusable as exc:
                        print(f"unusable: {exc}", file=sys.stderr)
                        rc = EXIT_UNUSABLE
                finally:
                    sys.stdout, sys.stderr = keep
                se.seek(0)
                return rc, se.read()

        fake.write_text("import sys\nprint('qa/manual-tests/first-boot-v1/')\nsys.exit(0)\n", encoding="utf-8")
        rc, se = recorded(sha2, fake)
        vpath = verdict_path("o/r", sha2)
        check("a PASS is recorded, and read back for the same repository, commit and evidence tree",
              rc == 0 and read_verdict("o/r", sha2, tree2) == ("ok", "qa/manual-tests/first-boot-v1/\n"), f"rc={rc} {se!r} {read_verdict('o/r', sha2, tree2)}")
        check("the verdict is kept under the verdict directory, owner-only", str(vpath).startswith(str(d / "data"))
              and oct(vpath.stat().st_mode & 0o777) == "0o600", f"{vpath} {oct(vpath.stat().st_mode & 0o777)}")
        check("a verdict for another evidence tree is a mismatch", read_verdict("o/r", sha2, "c" * 40)[0] == "mismatch")
        check("a verdict read with no evidence tree is a mismatch, not a pass", read_verdict("o/r", sha2, "")[0] == "mismatch")
        check("a verdict for another repository is missing", read_verdict("x/y", sha2, tree2)[0] == "missing")
        check("a verdict for another commit is missing", read_verdict("o/r", sha, tree2)[0] == "missing")
        at = json.loads(vpath.read_text())["at"]
        check("a verdict 31 minutes old is stale", read_verdict("o/r", sha2, tree2, now=at + 31 * 60)[0] == "stale")
        check("a verdict 29 minutes old is still good", read_verdict("o/r", sha2, tree2, now=at + 29 * 60)[0] == "ok")
        check("a verdict dated in the future is refused", read_verdict("o/r", sha2, tree2, now=at - 3600)[0] == "unparsable")
        good_text = vpath.read_text()
        for label, text in (("garbage", "nope {"), ("a list", "[1]"), ("an object without its fields", "{}")):
            vpath.write_text(text, encoding="utf-8")
            check(f"a verdict file that is {label} is unparsable", read_verdict("o/r", sha2, tree2)[0] == "unparsable", read_verdict("o/r", sha2, tree2))
        for field, value in (("repo", "x/y"), ("sha", "e" * 40)):
            vpath.write_text(json.dumps({**json.loads(good_text), field: value}), encoding="utf-8")
            check(f"a verdict whose own `{field}` field names another is a mismatch", read_verdict("o/r", sha2, tree2)[0] == "mismatch",
                  read_verdict("o/r", sha2, tree2))
        vpath.write_text(good_text, encoding="utf-8")
        cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--repo", "o/r", "--sha", sha2, "--check-verdict", "--tree", tree2],
                             capture_output=True, text=True, timeout=60)
        check("--check-verdict exits 0 and prints the evidence listing for a good verdict",
              cli.returncode == 0 and "first-boot-v1/" in cli.stdout, f"rc={cli.returncode} {cli.stdout!r} {cli.stderr!r}")
        cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--repo", "o/r", "--sha", sha2, "--check-verdict", "--tree", "d" * 40],
                             capture_output=True, text=True, timeout=60)
        check("--check-verdict exits 2 and names the reason for a mismatch", cli.returncode == EXIT_UNUSABLE and "mismatch" in cli.stderr,
              f"rc={cli.returncode} {cli.stderr!r}")
        fake.write_text("import sys\nprint('FAIL layer: HOLE', file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")
        rc, se = recorded(sha2, fake)
        kind, why = read_verdict("o/r", sha2, tree2)
        check("a FAIL is recorded as a FAIL naming the finding, and exits 1", rc == 1 and kind == "FAIL" and "HOLE" in why, f"rc={rc} {kind} {why!r}")
        cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--repo", "o/r", "--sha", sha2, "--check-verdict", "--tree", tree2],
                             capture_output=True, text=True, timeout=60)
        check("--check-verdict exits 1 for a FAIL verdict", cli.returncode == EXIT_FINDINGS, f"rc={cli.returncode} {cli.stderr!r}")
        vpath.unlink()
        fake.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        rc, se = recorded(sha2, fake)
        check("an unusable judgement records NO verdict", rc == EXIT_UNUSABLE and not vpath.exists(), f"rc={rc} exists={vpath.exists()}")
        rc, se = recorded(sha, fake)
        check("a commit with no qa/ tree is unusable and records NO verdict",
              rc == EXIT_UNUSABLE and "no qa/ tree" in se and not verdict_path("o/r", sha).exists(), f"rc={rc} {se!r}")
        if saved_data is None:
            os.environ.pop("QA_FLOW_VERDICT_DIR", None)
        else:
            os.environ["QA_FLOW_VERDICT_DIR"] = saved_data
        slow = d / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        started = time.monotonic()
        rc, _, se = judged(sha, str(src), slow, budget=4)
        check("a judge that outlives the budget is unusable, and stops at the budget", rc == EXIT_UNUSABLE
              and "time budget" in se and time.monotonic() - started < 15, f"rc={rc} {se!r} {time.monotonic() - started:.1f}s")
        # A timeout kills the whole process group, not only the step's own process: each stub forks a child that would outlive it.
        def child_gone(pidfile: Path) -> tuple:
            for _ in range(20):
                if pidfile.exists() and pidfile.read_text().strip():
                    break
                time.sleep(0.1)
            if not (pidfile.exists() and pidfile.read_text().strip()):
                return False, "the stub never recorded its child"
            pid = int(pidfile.read_text().strip())
            for _ in range(30):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return True, ""
                time.sleep(0.1)
            os.kill(pid, signal.SIGKILL)            # do not leave it behind either way
            return False, f"child {pid} is still running"

        kid = d / "kid.pid"
        slow_kid = d / "slow-kid.py"
        slow_kid.write_text(f"import subprocess, time\nk = subprocess.Popen(['sleep', '30'])\nopen({str(kid)!r}, 'w').write(str(k.pid))\ntime.sleep(30)\n",
                            encoding="utf-8")
        rc, _, se = judged(sha, str(src), slow_kid, budget=4)
        gone, why = child_gone(kid)
        check("a judge that times out leaves no child running", rc == EXIT_UNUSABLE and gone, f"rc={rc} {why} {se!r}")
        shim = d / "shimbin"
        shim.mkdir()
        fkid = d / "fetch-kid.pid"
        real_git = shutil.which("git")
        (shim / "git").write_text(f'#!/bin/sh\ncase " $* " in *" fetch "*) sleep 30 & echo $! > "{fkid}"; wait ;; esac\nexec {real_git} "$@"\n',
                                  encoding="utf-8")
        (shim / "git").chmod(0o755)
        saved_path, os.environ["PATH"] = os.environ["PATH"], f"{shim}{os.pathsep}{os.environ['PATH']}"
        try:
            rc, _, se = judged(sha, str(src), fake, budget=3)
        finally:
            os.environ["PATH"] = saved_path
        gone, why = child_gone(fkid)
        check("a fetch that times out leaves no child running", rc == EXIT_UNUSABLE and gone, f"rc={rc} {why} {se!r}")
        leftovers = [p for p in d.glob("qa-remote-evidence.*")]
        check("no scratch repository is left behind", not leftovers, leftovers)
        tempfile.tempdir = saved_tmp

    for f in failures:
        print(f"SELFTEST FAILED: {f}", file=sys.stderr)
    print(f"remote_evidence selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
