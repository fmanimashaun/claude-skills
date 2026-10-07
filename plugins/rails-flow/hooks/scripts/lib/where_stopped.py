#!/usr/bin/env python3
"""Where this worktree stopped (#1639): a facts file rewritten every turn, and a warning about unpushed work.

A session can be killed without warning (a restart, a spend limit, an expired login), and then the only record of
where it was is whatever it left on disk. `/rails-flow:handoff` writes a work order on request and the context nudge
fires at 70%; neither runs when the process is killed. This runs at every Stop, so the last completed turn is
always on disk:

  <git-common-dir>/handoff/<worktree-key>.md   branch, HEAD sha, commits not on any remote, uncommitted files, time

KEYED BY WORKTREE, never by session or by project directory: names rotate at every start, and a first-person
handoff keyed by the project directory misled two sessions into reporting another's work as their own
(CHANGELOG v1.143.0). The file says which worktree it describes and the HEAD it saw; a reader whose HEAD differs
is told the file describes an older state (the drift `check_handoff.py` flags for a work order).

ADVISORY, FAIL OPEN (docs/doctrine/harness-doctrine.md): if a model ignores this, nothing breaks, so nothing here
may stop a turn. Every failure is swallowed and the exit status is 0.

    python3 where_stopped.py stop    [--cwd DIR] < Stop payload   writes the file; prints {"systemMessage": ...} only
                                                                  when there is unpushed or uncommitted work AND the
                                                                  counts changed since the last turn
    python3 where_stopped.py pointer [--cwd DIR]                  SessionStart lines, silent when there is nothing to say
    python3 where_stopped.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

GIT_TIMEOUT = 5          # seconds per git call: a hung git must not hold the turn
DEADLINE_SECONDS = 8     # for ALL git calls of one run (#1643 review N1): a hung git costs at most this, not 5 s per call
DIRTY_LISTED = 10        # paths written to the file; the count is always the full one
MARKER = "<!-- rails-flow where-stopped v1 -->"
UNKNOWN = "unknown (git timed out or failed)"


_deadline = [time.monotonic() + DEADLINE_SECONDS]
TIMED_OUT = [False]      # set when a call ran out of time, so "no answer" is never read as "nothing there"


def start_clock() -> None:
    """The deadline is per RUN, started where a run begins (`stop`, `pointer`), never at import: a long-lived caller
    (the selftest, under load) would otherwise find every later git call already out of time. Called by `facts`, which
    every run calls exactly once."""
    _deadline[0] = time.monotonic() + DEADLINE_SECONDS
    TIMED_OUT[0] = False


def git(cwd: Path, *args: str) -> str | None:
    left = min(GIT_TIMEOUT, _deadline[0] - time.monotonic())
    if left <= 0:
        TIMED_OUT[0] = True
        return None
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=left)
    except subprocess.TimeoutExpired:
        TIMED_OUT[0] = True
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def worktree_key(toplevel: str) -> str:
    """The worktree's directory name, made path-safe, plus a hash of its full path: readable, and unique per worktree."""
    slug = re.sub(r"[^a-z0-9]+", "-", Path(toplevel).name.lower()).strip("-")[:40] or "worktree"
    return f"{slug}-{hashlib.sha1(toplevel.encode()).hexdigest()[:8]}"


def facts(cwd: Path) -> dict | None:
    start_clock()                                          # one deadline per run: each run reads the facts once
    top = git(cwd, "rev-parse", "--show-toplevel")
    common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not top or not common:
        return None
    head = git(cwd, "rev-parse", "HEAD")                       # None on an unborn branch
    has_remote = bool(git(cwd, "remote"))
    # NOT ON ANY REMOTE: commits reachable from HEAD that no remote-tracking ref contains. With no remote at all there is
    # nowhere to push, so the count is not reported rather than reported as "every commit".
    unpushed = None
    if head and has_remote:
        n = git(cwd, "rev-list", "--count", "HEAD", "--not", "--remotes")
        unpushed = int(n) if n and n.isdigit() else None
    status = git(cwd, "status", "--porcelain", "-uall")
    # UNKNOWN, NEVER CLEAN (#1643 review N2): a `git status` that failed or timed out has said nothing about the tree, and
    # reading its silence as "0 uncommitted files" is the false all-clear this file exists to prevent.
    dirty = None if status is None else [line[3:] for line in status.splitlines()]
    return {"toplevel": top, "common": common, "branch": git(cwd, "branch", "--show-current") or "(detached)",
            "head": head, "unpushed": unpushed, "dirty": dirty}


def path_for(f: dict) -> Path:
    return Path(f["common"]) / "handoff" / f"{worktree_key(f['toplevel'])}.md"


def render(f: dict, now: str) -> str:
    lines = [MARKER, f"# Where this worktree stopped: {f['toplevel']}", "",
             f"Written {now} by the rails-flow Stop hook (#1639), at the end of the last completed turn. Facts only, rewritten",
             "every turn; claims and next steps belong in HANDOFF.md, not here.", "",
             f"- worktree: {f['toplevel']}", f"- branch: {f['branch']}", f"- HEAD: {f['head'] or '(no commits)'}",
             f"- commits not on any remote: {'n/a (no remote)' if f['unpushed'] is None else f['unpushed']}",
             f"- uncommitted files: {UNKNOWN if f['dirty'] is None else len(f['dirty'])}"]
    lines += [f"  - {p}" for p in (f["dirty"] or [])[:DIRTY_LISTED]]
    if f["dirty"] is not None and len(f["dirty"]) > DIRTY_LISTED:
        lines.append(f"  - … and {len(f['dirty']) - DIRTY_LISTED} more (git status --porcelain -uall)")
    return "\n".join(lines) + "\n"


def read_recorded(path: Path) -> dict:
    """The HEAD and counts the file last recorded; empty when there is no file or it is not ours."""
    try:
        text = path.read_text()
    except OSError:
        return {}
    if not text.startswith(MARKER):
        return {}
    got = {}
    for key, pat in (("head", r"^- HEAD: (\S+)"), ("unpushed", r"^- commits not on any remote: (\d+)"),
                     ("dirty", r"^- uncommitted files: (\d+)"), ("written", r"^Written (\S+)")):
        m = re.search(pat, text, re.M)
        if m:
            got[key] = m.group(1)
    return got


def unsaved_phrase(unpushed: int | None, dirty: int | None) -> str:
    """`dirty` None means git could not say, which is reported, never treated as zero."""
    parts = []
    if unpushed:
        parts.append(f"{unpushed} commit{'s' if unpushed != 1 else ''} not on any remote")
    if dirty is None:
        parts.append(f"uncommitted files {UNKNOWN}")
    elif dirty:
        parts.append(f"{dirty} uncommitted file{'s' if dirty != 1 else ''}")
    return ", ".join(parts)


def dirty_count(f: dict) -> int | None:
    return None if f["dirty"] is None else len(f["dirty"])


def stop(cwd: Path, stdin: str) -> str:
    """Writes the facts file; returns the hook's stdout (a JSON systemMessage, or empty)."""
    try:
        if json.loads(stdin or "{}").get("stop_hook_active"):
            return ""
    except (ValueError, AttributeError):
        pass
    f = facts(cwd)
    if f is None:
        return ""
    path = path_for(f)
    before = read_recorded(path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(render(f, now))
        os.replace(tmp, path)                          # never a half-written file for the next reader
    except OSError:
        pass
    phrase = unsaved_phrase(f["unpushed"], dirty_count(f))
    if not phrase:
        return ""
    # ONCE PER CHANGE, not every turn: the same two numbers repeated after every reply are read once and then ignored. An
    # UNKNOWN count is never "the same" as last turn's, so it is always said.
    if f["dirty"] is not None and before.get("unpushed", "0") == str(f["unpushed"] or 0) \
            and before.get("dirty") == str(len(f["dirty"])):
        return ""
    return json.dumps({"systemMessage": f"rails-flow: {phrase} in {f['toplevel']} — "
                                        "push, or commit WIP, so a killed session loses nothing."})


def pointer(cwd: Path) -> str:
    f = facts(cwd)
    if f is None:
        return ""
    out = []
    phrase = unsaved_phrase(f["unpushed"], dirty_count(f))
    if phrase:
        out.append(f"- unsaved work: {phrase}")
    path = path_for(f)
    rec = read_recorded(path)
    drift = bool(rec.get("head") and f["head"] and rec["head"] != f["head"])
    # ONLY WHEN THERE IS SOMETHING TO RESUME (#1643 review D1, the coordinator's decision): unsaved work or a HEAD that
    # moved. A clean, pushed worktree has nothing to recover, and this hook runs again after every compaction.
    if rec and (phrase or drift):
        line = f"- where this worktree stopped (last turn, {rec.get('written', '?')}): {path}"
        if drift:
            line += f" — HEAD has moved since ({rec['head'][:8]} → {f['head'][:8]}): it describes the older state"
        out.append(line)
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------------------- selftest
def _sh(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f"  [{detail[:200]}]"))
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        remote, repo = root / "remote.git", root / "repo"
        _sh(root, "init", "-q", "--bare", str(remote))
        _sh(root, "init", "-q", "-b", "dev", str(repo))
        (repo / "a").write_text("a\n")
        _sh(repo, "add", "a")
        _sh(repo, "commit", "-q", "-m", "one")
        _sh(repo, "remote", "add", "origin", str(remote))
        _sh(repo, "push", "-q", "origin", "dev")

        check("clean and pushed: the stop says nothing", stop(repo, "{}") == "")
        f = facts(repo)
        check("the file is keyed by worktree, under the common git dir", path_for(f).parent == Path(f["common"]) / "handoff"
              and path_for(f).name.startswith("repo-"), str(path_for(f)))
        check("clean and pushed: the SessionStart pointer is silent, even with a facts file on disk (#1643 D1)",
              path_for(f).exists() and pointer(repo) == "", pointer(repo))

        (repo / "b").write_text("b\n")
        _sh(repo, "add", "b")
        _sh(repo, "commit", "-q", "-m", "two")
        (repo / "c").write_text("c\n")
        msg = stop(repo, "{}")
        check("one unpushed commit and one untracked file are both named",
              "1 commit not on any remote" in msg and "1 uncommitted file" in msg and "systemMessage" in msg, msg)
        check("the same counts on the next turn are not repeated", stop(repo, "{}") == "")
        text = path_for(facts(repo)).read_text()
        check("the file records branch, full HEAD, both counts and the dirty path",
              "- branch: dev" in text and facts(repo)["head"] in text and "- commits not on any remote: 1" in text
              and "  - c" in text, text)
        check("stop_hook_active: nothing written, nothing said", stop(repo, '{"stop_hook_active": true}') == "")
        check("the SessionStart pointer states the unsaved work", "- unsaved work: 1 commit not on any remote, 1 uncommitted file"
              in pointer(repo), pointer(repo))

        # DRIFT: HEAD moves without a Stop (another session, a rebase, a pull) and the pointer says the file is older.
        recorded = facts(repo)["head"]
        _sh(repo, "add", "c")
        _sh(repo, "commit", "-q", "-m", "three")
        p = pointer(repo)
        check("a HEAD that moved after the last Stop is flagged as drift", f"({recorded[:8]} →" in p and "older state" in p, p)

        # DRIFT ALONE (clean, pushed, but HEAD moved since the file) still points at it.
        _sh(repo, "push", "-q", "origin", "dev")
        p = pointer(repo)
        check("clean and pushed but HEAD moved: the pointer is printed for the drift alone",
              "unsaved work" not in p and "older state" in p, p)
        stop(repo, "{}")

        # UNKNOWN, NEVER CLEAN: a `git status` that gives no answer is reported, and said, rather than read as 0.
        real_git = globals()["git"]
        globals()["git"] = lambda cwd, *a: None if a and a[0] == "status" else real_git(cwd, *a)
        try:
            msg = stop(repo, "{}")
            text = path_for(facts(repo)).read_text()
            check("a git status with no answer is 'unknown', in the file and in the warning, never 0",
                  UNKNOWN in text and "- uncommitted files: 0" not in text and UNKNOWN in msg, msg + text[-200:])
            check("an unknown count is said again every turn, never taken as unchanged", UNKNOWN in stop(repo, "{}"))
            check("the SessionStart line says unknown too", UNKNOWN in pointer(repo), pointer(repo))
        finally:
            globals()["git"] = real_git

        # THE DEADLINE: once it has passed, every git call returns at once, and the run is marked timed out.
        saved = _deadline[0]
        _deadline[0] = time.monotonic() - 1
        TIMED_OUT[0] = False
        t0 = time.monotonic()
        none = git(repo, "status")
        check("past the overall deadline git is not called at all, and the run is marked timed out",
              none is None and TIMED_OUT[0] and time.monotonic() - t0 < 0.5)
        _deadline[0] = saved

        # A SECOND WORKTREE gets its own file, never the first one's.
        wt = root / "wt-two"
        _sh(repo, "worktree", "add", "-q", "-b", "feature/x", str(wt))
        (wt / "wip").write_text("w\n")                 # something to resume, or the pointer is rightly silent (D1)
        stop(wt, "{}")
        check("a second worktree writes its own file", path_for(facts(wt)) != path_for(facts(repo))
              and path_for(facts(wt)).exists(), str(path_for(facts(wt))))
        check("its pointer names its own file", str(path_for(facts(wt))) in pointer(wt), pointer(wt))

        # NO REMOTE: the count is not reported (not "every commit"), and a foreign file is never parsed as ours.
        lone = root / "lone"
        _sh(root, "init", "-q", "-b", "main", str(lone))
        (lone / "x").write_text("x\n")
        _sh(lone, "add", "x")
        _sh(lone, "commit", "-q", "-m", "x")
        check("no remote: nothing is called unpushed", stop(lone, "{}") == "" and "not on any remote" not in pointer(lone),
              pointer(lone))
        path_for(facts(lone)).write_text("- HEAD: deadbeef\n")
        check("a file without our marker is ignored", "HEAD has moved" not in pointer(lone), pointer(lone))

        # FAIL OPEN: outside a repository, and with the handoff directory unwritable.
        outside = root / "plain"
        outside.mkdir()
        check("outside a git repository: silent", stop(outside, "{}") == "" and pointer(outside) == "")
        hand = Path(facts(repo)["common"]) / "handoff"
        for p in hand.iterdir():
            p.unlink()
        hand.rmdir()
        hand.write_text("a file where the directory should be")
        try:
            out = stop(repo, "{}")
            check("an unwritable handoff directory does not raise", True)
        except Exception as e:  # noqa: BLE001
            check("an unwritable handoff directory does not raise", False, repr(e))
        check("not a JSON payload: treated as empty", stop(outside, "not json") == "")
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", choices=("stop", "pointer"))
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        cwd = Path(a.cwd)
        if a.command == "stop":
            out = stop(cwd, sys.stdin.read() if not sys.stdin.isatty() else "")
        elif a.command == "pointer":
            out = pointer(cwd)
        else:
            return 0
        if out:
            print(out)
    except Exception:  # noqa: BLE001 — advisory: any failure is silence, never a stopped turn
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
