#!/usr/bin/env python3
"""The worktree guard's judgement (#1581): may this session add another worktree?

Called by `guard-worktree.sh` (PreToolUse[Bash]) with the hook payload on stdin, and by
`session-start.sh` for the resume pointer. Two rules, from the owner's direction on #1581:

  1. ONE ISSUE AT A TIME. A session that holds an unmerged lane in the coordination record
     (`coordination.py`) may not add another worktree: finish it, or hand the new task back.
  2. NO DUPLICATE. A worktree for a branch, or an issue, that already has an unmerged one is how a
     restart orphans the first. Resume there. This rule reads `git worktree list` alone: it needs no
     record and no session identity, so it holds for everyone, coordinator or not.

Merged means the worktree's HEAD is reachable from the integration branch (the first of origin/dev,
dev, origin/main, main, origin/master, master that exists). With none, nothing counts as merged:
a lane that cannot be judged is not finished.

THE LIMIT, STATED. A session's identity is the `session_id` in the payload, and the record is written
by the coordinator, so this protects against ACCIDENT (a resumed or over-eager session creating a
second worktree), not against impersonation. A session nobody recorded passes rule 1; rule 2 still holds.
The issue number is read only from a branch or directory name written `issue-N`, `N-slug` or `.../N-`;
a branch that carries none gets the exact-branch rule alone.

    python3 worktree_guard.py check            < PreToolUse payload   exit 0 allow, 2 deny (stderr says why)
    python3 worktree_guard.py resume --session-id ID [--cwd DIR]      prints a pointer, silent when empty
    python3 worktree_guard.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coordination  # noqa: E402

INTEGRATION = ("origin/dev", "dev", "origin/main", "main", "origin/master", "master")
PREFIX = "BLOCKED by rails-flow worktree guard:"
ZOMBIE_WARN = 50
# `issue-77`, `issue_77`, `feat/77-x`, `77-x`: a number written as an issue, after a separator.
ISSUE = re.compile(r"(?:^|[/_-])(?:issue[-_]?)?(\d{2,6})(?=[-_/]|$)")
VALUE_OPTS = {"-b", "-B", "--reason"}
# A date (2026-10-02, 2026-10) in a name: its month and day are not issue numbers.
DATE = re.compile(r"(?:19|20)\d{2}[-_]\d{2}(?:[-_]\d{2})?")


def git(cwd, *args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return done.returncode, done.stdout


def issue_key(name: str | None) -> int | None:
    """The issue number a branch or directory name carries, or None. A year is not an issue."""
    name = DATE.sub("", name or "")
    for m in ISSUE.finditer(name):
        n = int(m.group(1))
        if not 1900 <= n <= 2100:
            return n
    return None


def keys(*names: str | None) -> set[int]:
    return {k for k in (issue_key(n) for n in names) if k is not None}


def worktrees(cwd) -> list[dict]:
    rc, out = git(cwd, "worktree", "list", "--porcelain")
    rows: list[dict] = []
    for block in out.strip().split("\n\n") if rc == 0 else []:
        row: dict = {}
        for line in block.splitlines():
            k, _, v = line.partition(" ")
            row[k] = v
        if "worktree" in row:
            rows.append({"path": os.path.realpath(row["worktree"]), "head": row.get("HEAD", ""),
                         "branch": row.get("branch", "").removeprefix("refs/heads/") or None})
    return rows


def integration_ref(cwd) -> str | None:
    for ref in INTEGRATION:
        if git(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")[0] == 0:
            return ref
    return None


def merged(cwd, sha: str, integ: str | None) -> bool:
    """Is this commit reachable from the integration branch? Nothing is merged when there is none."""
    return bool(sha) and integ is not None and git(cwd, "merge-base", "--is-ancestor", sha, integ)[0] == 0


def branch_sha(cwd, branch: str) -> str:
    rc, out = git(cwd, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")
    return out.strip() if rc == 0 else ""


def worktree_adds(command: str) -> list[dict] | None:
    """Each `git ... worktree add ...` in the command as {path, branch, commitish}; None if unreadable."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return None
    ops = {";", "&&", "||", "|", "&", "(", ")", "\n"}
    found: list[dict] = []
    seg_start = 0
    for i, tok in enumerate(tokens):
        if tok in ops or set(tok) <= set(";&|()"):
            seg_start = i + 1
            continue
        if tok == "worktree" and tokens[i + 1:i + 2] == ["add"] and any(
                os.path.basename(t) in ("git", "git.exe") for t in tokens[seg_start:i]):
            args: list[str] = []
            for t in tokens[i + 2:]:
                if t in ops or set(t) <= set(";&|()"):
                    break
                args.append(t)
            branch, positional, j = None, [], 0
            while j < len(args):
                a = args[j]
                if a in VALUE_OPTS and j + 1 < len(args):
                    if a in ("-b", "-B"):
                        branch = args[j + 1]
                    j += 2
                    continue
                if not a.startswith("-") or a == "-":
                    positional.append(a)
                j += 1
            found.append({"path": positional[0] if positional else None, "branch": branch,
                          "commitish": positional[1] if len(positional) > 1 else None})
    return found


def deny(msg: str) -> int:
    print(f"{PREFIX} {msg}", file=sys.stderr)
    return 2


def check(payload: dict) -> int:
    command = str((payload.get("tool_input") or {}).get("command", ""))
    cwd = payload.get("cwd") or os.getcwd()
    sid = payload.get("session_id")
    adds = worktree_adds(command)
    if not adds:
        return deny("could not read the `git worktree add` in this command, so it cannot be judged. Write it as a plain "
                    "`git worktree add <path> [-b <branch>] [<commit>]` on its own line.")
    if git(cwd, "rev-parse", "--is-inside-work-tree")[0] != 0:
        return 0                                  # dormant outside a git repository
    existing = worktrees(cwd)
    integ = integration_ref(cwd)
    for add in adds:
        path = os.path.realpath(os.path.join(cwd, add["path"])) if add["path"] else None
        branch = add["branch"]
        if not branch and add["commitish"] and branch_sha(cwd, add["commitish"]):
            branch = add["commitish"]             # an existing local branch is the branch being checked out
        new_keys = keys(branch, os.path.basename(path or ""))
        for w in existing:
            if w["path"] == path:
                continue
            same_branch = bool(branch) and w["branch"] == branch
            same_issue = bool(new_keys & keys(w["branch"], os.path.basename(w["path"]))) and not merged(cwd, w["head"], integ)
            if same_branch or same_issue:
                what = f"branch `{branch}`" if same_branch else f"issue {sorted(new_keys & keys(w['branch'], os.path.basename(w['path'])))[0]}"
                return deny(f"a worktree for {what} already exists at {w['path']} (branch `{w['branch'] or 'detached'}`). "
                            f"Resume there: cd {w['path']}. A new worktree for work already started is how a restart "
                            f"orphans the first one.")
    if sid:
        rp = coordination.record_path(cwd)
        try:
            record = coordination.load(rp) if rp else None
        except coordination.RecordError as e:
            return deny(f"the coordination record is unreadable ({e}). Fix or delete {rp}, then retry; a lane that "
                        f"cannot be read cannot be judged.")
        by_path = {w["path"]: w for w in existing}
        for lane_path, row in coordination.lanes_for(record, sid) if record else []:
            wt = by_path.get(os.path.realpath(lane_path))
            if wt is None:
                continue                          # the worktree is gone: that lane is finished
            sha = branch_sha(cwd, row.get("branch", "")) or wt["head"]
            if not merged(cwd, sha, integ):
                return deny(f"this session already owns an unmerged worktree: {wt['path']} (branch `{row.get('branch', '?')}`). "
                            f"One issue at a time: finish it (merge, then `git worktree remove {wt['path']}`), or hand the new "
                            f"task back to whoever assigned it. Resume there: cd {wt['path']}.")
    return 0


def zombies() -> tuple[int, list[tuple[int, str, int]]]:
    """(count of zombie processes, the busiest parents as (ppid, command, zombies))."""
    try:
        out = subprocess.run(["ps", "-axo", "stat=,ppid=,comm="], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0, []
    by_parent: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].startswith("Z") and parts[1].isdigit():
            by_parent[int(parts[1])] = by_parent.get(int(parts[1]), 0) + 1
    top = sorted(by_parent.items(), key=lambda kv: -kv[1])[:3]
    names = []
    for ppid, n in top:
        try:
            comm = subprocess.run(["ps", "-o", "command=", "-p", str(ppid)], capture_output=True, text=True,
                                  timeout=5).stdout.strip()[:60]
        except (OSError, subprocess.TimeoutExpired):
            comm = "?"
        names.append((ppid, comm or "?", n))
    return sum(by_parent.values()), names


def resume(session_id: str, cwd: str) -> int:
    """The SessionStart pointer. Silent when there is nothing to say: this prints again after every compaction."""
    if git(cwd, "rev-parse", "--is-inside-work-tree")[0] != 0:
        return 0
    lines: list[str] = []
    existing = worktrees(cwd)
    integ = integration_ref(cwd)
    by_path = {w["path"]: w for w in existing}
    rp = coordination.record_path(cwd)
    try:
        record = coordination.load(rp) if rp else None
    except coordination.RecordError:
        record = None
    for lane_path, row in coordination.lanes_for(record, session_id) if record and session_id else []:
        wt = by_path.get(os.path.realpath(lane_path))
        if wt:
            lines.append(f"- resume in place: {wt['path']} (branch {row.get('branch', '?')}). Continue there; never create "
                         f"a new worktree for work already started.")
    finished = [w for w in existing[1:] if merged(cwd, w["head"], integ) and not git(w["path"], "status", "--porcelain")[1].strip()]
    if finished:
        shown = ", ".join(w["path"] for w in finished[:3])
        lines.append(f"- {len(finished)} finished worktree(s) (merged, clean): {shown}{' ...' if len(finished) > 3 else ''}. "
                     f"Remove each with `git worktree remove <path>` (never --force).")
    count, top = zombies()
    if count >= int(os.environ.get("RAILS_FLOW_ZOMBIE_WARN") or ZOMBIE_WARN):
        parents = "; ".join(f"pid {p} `{c}` ({n})" for p, c, n in top)
        lines.append(f"- {count} zombie processes on this machine; busiest parents: {parents}. Every fork() fails at the "
                     f"per-user limit: see parallel-session-lane process-hygiene.")
    if lines:
        print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check")
    r = sub.add_parser("resume")
    r.add_argument("--session-id", default="")
    r.add_argument("--cwd", default=".")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "check":
        try:
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
        except json.JSONDecodeError:
            return deny("the hook payload could not be read, so a `git worktree add` cannot be judged.")
        return check(payload if isinstance(payload, dict) else {})
    if args.cmd == "resume":
        return resume(args.session_id, args.cwd)
    ap.print_usage(sys.stderr)
    return 3


def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def check_(label: str, ok: bool, detail: str = "") -> None:
        ran[0] += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    check_("issue-N", issue_key("feature/issue-1581-worktree") == 1581)
    check_("N-slug", issue_key("fix/1495-label-check-edges") == 1495)
    check_("a directory name", issue_key("issue-77") == 77)
    check_("a year is not an issue", issue_key("chore/2026-10-02-x") is None)
    check_("a version is not an issue", issue_key("chore/arm-v1.153.0") is None)
    check_("no number, no key", issue_key("feature/lane-band") is None)
    adds = worktree_adds("cd /x && git -C repo worktree add -f ../b -b feat/b dev; echo done") or []
    check_("a worktree add is found after cd and git -C", len(adds) == 1 and adds[0]["path"] == "../b"
           and adds[0]["branch"] == "feat/b" and adds[0]["commitish"] == "dev", str(adds))
    check_("a quoted mention is not a worktree add", worktree_adds('echo "git worktree add ../x"') == [])
    check_("an existing branch given as the commit-ish is read", (worktree_adds("git worktree add ../x feat/a") or [{}])[0].get("commitish") == "feat/a")
    check_("an unbalanced quote is unreadable, not empty", worktree_adds("git worktree add 'x") is None)
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"worktree_guard selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
