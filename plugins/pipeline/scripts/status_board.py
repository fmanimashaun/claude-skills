#!/usr/bin/env python3
"""The status board: a measured collector and a static drawing-sheet page (#1585, PR 1 of 3).

Run:  python3 status_board.py collect [--root DIR] [--audience owner|coordinator] [--budget-seconds N]
      python3 status_board.py render  [--root DIR] [--audience owner|coordinator]
      python3 status_board.py --selftest

WHAT IT DOES. `collect` measures the state of one repository at the moment it runs and writes two
files under `.claude/state/`: `board.json`, the record, and `board.html`, one self-contained page
rendered from it. The page has no network request and no script, so it opens in any project and any
harness. Every figure is measured here (`gh`, `git`, `ps`, `sysctl`), never remembered.

THE RULE THAT SHAPES IT: a source that cannot be read shows as UNKNOWN, never as 0. Each panel is
`ok` or `unknown` with a reason, and a count that may be too low (a list that hit its `--limit`)
says "N or more". A default must not hide present data.

WHERE THE SESSIONS COME FROM. `coordination.json` in the common git dir, the record
`plugins/rails-flow/hooks/scripts/lib/coordination.py` owns (#1581). It is READ here and never
written here: the coordinator is its only writer. `pipeline` cannot import rails-flow's module (each
plugin resolves its own `${CLAUDE_PLUGIN_ROOT}`), so this reads the JSON directly, and the selftest
compares the field names it reads with the ones `coordination.py` writes, so they cannot drift.
The record's `workspace.repos` names sibling repositories; each one's own record is read and its
rows carry that repo's name. A sibling that cannot be read shows as "repo unavailable".

WHAT IT DOES NOT DO (later PRs of #1585): refresh from a hook, write the check-in, write `asks` and
`events`, or publish a live artifact. It READS `asks` and `events` now, so the page is complete the
day the coordinator starts writing them.

EXIT: 0 the files were written (panels may be unknown), 2 not inside a git repository, 3 could not
write the files.

TEXT. Every SENTENCE this script writes comes from the `TEXT` table (column names and one-word labels in
the page are literals in the renderer), in ASD-STE100 style: active
voice, one instruction per sentence, at most 20 words in an instruction and 25 in a description. The
selftest lints the table (`ste_flags`): it flags, it does not rewrite. Names that come from data (a
PR title, a branch) are not lint targets.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

SCHEMA = 1
# The record's field names this module READS. `coordination.py` WRITES every one (PR 2 of #1585 added `pr`,
# `asks` and `events`); the PLANNED set is for a key read before its writer exists, and is empty today. A
# reader tolerates the absence of any key. `check_coordination_readers.py` checks both sets against
# coordination.py, so neither can drift unseen.
RECORD_KEYS_WRITTEN = ("coordinator", "sessions", "workspace", "session_id", "name", "since", "branch", "issue",
                       "state", "updated", "repos", "path", "remote", "pr", "asks", "events")
RECORD_KEYS_PLANNED = ()
STATE_DIR = ".claude/state"
BOARD_JSON = "board.json"
BOARD_HTML = "board.html"
CONFIG = ".claude/board.config.json"
COORD_FILE = "coordination.json"

RUN_LIMIT = 20          # runs read per head, to find the dispatched one
CALL_TIMEOUT = 20.0     # the longest one command may run, seconds
PR_LIMIT = 100          # open pull requests read per repository
PR_DETAIL_CAP = 30      # pull requests that get a per-PR review and run lookup
ISSUE_LIMIT = 200       # open issues read for a count
MERGED_LIMIT = 50       # merged pull requests read for "Today"
DEFAULTS = {
    "title": "Status board",
    "full_run_workflow": None,          # no default: a run that is not configured is unknown, not "none"
    "full_run_event": "workflow_dispatch",
    "integration_branch": None,         # None: `integration_branch_of` finds it (dev when origin/dev exists)
    "review_pattern": None,             # None: `verdict_of` reads the shapes in use. A regex here replaces it
                                        # (group 1 = the commit, group 2 = CLEAN or BLOCKED)
    "stale_minutes": 60,
    "drafted_hours": 4,
    "zombie_warn": 50,
    "worktree_warn": 20,
    "process_warn_pct": 80,
    "release_lines": [],
    "notes": {},
}

# --------------------------------------------------------------------------------------------------
# TEXT: every sentence the collector or the page writes. `kind` is "instruction" (an imperative that
# tells the reader to do something, at most 20 words, active) or "description" (at most 25 words).
# --------------------------------------------------------------------------------------------------
TEXT: dict[str, tuple[str, str]] = {
    # panel headings and short labels
    "h.asks": ("Needs you", "label"),
    "h.lines": ("Release lines", "label"),
    "h.prs": ("Open pull requests", "label"),
    "h.sessions": ("Sessions", "label"),
    "h.limits": ("Limits", "label"),
    "h.today": ("Today", "label"),
    # empty and unknown states
    "empty.asks": ("Nothing is waiting on you.", "description"),
    "empty.prs": ("No pull request is open.", "description"),
    "empty.sessions": ("No session holds a lane.", "description"),
    "empty.events": ("No event is recorded today.", "description"),
    "unknown.value": ("unknown", "label"),
    "unknown.source": ("This source cannot be read: {why}.", "description"),
    "unknown.gh": ("The gh command failed or is missing", "label"),
    "unknown.budget": ("The time budget ended before this source ran", "label"),
    "unknown.config_lines": ("The config declares no release line. Add release_lines to .claude/board.config.json.", "instruction"),
    "unknown.workflow": ("The config declares no full-run workflow. Set full_run_workflow in .claude/board.config.json.", "instruction"),
    "unknown.record": ("The coordination record cannot be read: {why}.", "description"),
    "unknown.no_record": ("This repository has no coordination record.", "description"),
    "unavailable.repo": ("Repo unavailable: {why}.", "description"),
    "sibling.origin_unreadable": ("The origin of {path} cannot be read, so it cannot be checked against {remote}.", "description"),
    "sibling.origin_differs": ("The origin of {path} is {own}, not {remote}.", "description"),
    "partial.count": ("{n} or more", "label"),
    "partial.note": ("The list reached its limit of {n}, so the count is a minimum.", "description"),
    # next actions on a pull request (a PR row says one thing to do)
    "next.conflict": ("Resolve the conflict.", "instruction"),
    "next.draft": ("Finish the draft.", "instruction"),
    "next.no_review": ("Assign a review.", "instruction"),
    "next.stale_review": ("Request a new review of the head.", "instruction"),
    "next.blocked": ("Fix the findings.", "instruction"),
    "next.no_run": ("Dispatch a full run.", "instruction"),
    "next.run_wait": ("Wait for the full run.", "instruction"),
    "next.run_red": ("Fix the full run.", "instruction"),
    "next.run_unknown": ("Check the full run.", "instruction"),
    "next.merge": ("Merge.", "instruction"),
    "next.behind": ("Update the branch.", "instruction"),
    "next.merge_blocked": ("Find the missing check or review.", "instruction"),
    "next.unstable": ("Fix the failing check.", "instruction"),
    "next.merge_unknown": ("Check the merge state.", "instruction"),
    # limits
    "limit.processes": ("Processes of this user", "label"),
    "limit.zombies": ("Zombie processes", "label"),
    "limit.stopped": ("Stopped orphan processes", "label"),
    "limit.worktrees": ("Worktrees", "label"),
    "limit.issues": ("Open issues", "label"),
    # coordination
    "coord.stale": ("The coordinator has not updated its row for {mins} minutes.", "description"),
    "coord.fresh_unknown": ("The record has no row for the coordinator.", "description"),
    "coord.drafted_stale": ("{n} question(s) stayed drafted for more than {hours} hours. Ask them now.", "instruction"),
    "coord.asked_where": ("Answer in {where}.", "instruction"),
    # title block
    "tb.title": ("Title", "label"),
    "tb.repos": ("Repositories", "label"),
    "tb.coordinator": ("Coordinator", "label"),
    "tb.updated": ("Updated", "label"),
    "tb.commit": ("Commit", "label"),
    "tb.sheet": ("Sheet", "label"),
    "tb.sheet_value": ("1 of 1", "label"),
    "tb.mode": ("Mode", "label"),
    "tb.mode_single": ("One session", "label"),
    "tb.mode_orchestrated": ("Several sessions", "label"),
    "tb.stale": ("stale", "label"),
    # the console line
    "cli.done": ("The board is at {path}.", "description"),
    "cli.ignore": ("Add .claude/state/ to .gitignore.", "instruction"),
}

STATUS_OF = {  # state words -> (glyph, css class). The glyph carries the meaning, not only the color.
    "clean": ("✓", "m-ok"), "green": ("✓", "m-ok"), "merged": ("✓", "m-ok"), "working": ("●", "m-ok"),
    "finished": ("✓", "m-ok"),
    "pending": ("○", "m-run"), "running": ("◷", "m-run"),
    "waiting": ("◔", "m-wait"), "stale": ("◔", "m-wait"), "conflict": ("!", "m-wait"), "draft": ("◔", "m-wait"),
    "blocked": ("✗", "m-bad"), "red": ("✗", "m-bad"), "failing": ("✗", "m-bad"),
    "idle": ("–", "m-idle"), "none": ("–", "m-idle"), "closed": ("–", "m-idle"),
    "not dispatched": ("–", "m-idle"), "unknown": ("?", "m-idle"), "cancelled": ("–", "m-idle"),
}


def say(key: str, **kw: object) -> str:
    """The one way a sentence enters the board: through the table the selftest lints."""
    return TEXT[key][0].format(**kw) if kw else TEXT[key][0]


# --------------------------------------------------------------------------------------------------
# ASD-STE100 lint. Flags, never rewrites. Names (backticked or path-like words) count as one word.
# --------------------------------------------------------------------------------------------------
LIMITS = {"instruction": 20, "description": 25}
_PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?([a-z]+(?:ed|en))\b", re.I)
_NOT_PARTICIPLES = {"open", "green", "listen", "even", "often", "then", "when", "seven", "token", "broken"}


def ste_flags(text: str, kind: str) -> list[str]:
    """Problems with one string: too many words for its kind, or the passive voice in an instruction."""
    flags: list[str] = []
    if kind not in LIMITS:
        return flags
    words = len(text.split())
    if words > LIMITS[kind]:
        flags.append(f"{words} words; the limit for an {kind} is {LIMITS[kind]}")
    if kind == "instruction":
        for m in _PASSIVE.finditer(text):
            if m.group(1).lower() not in _NOT_PARTICIPLES:
                flags.append(f"passive voice: '{m.group(0)}'")
    return flags


def lint_text_table() -> list[str]:
    out = []
    for key, (text, kind) in TEXT.items():
        for f in ste_flags(text, kind):
            out.append(f"{key}: {f}")
    return out


# --------------------------------------------------------------------------------------------------
# The outside world, behind two injectable functions, so a fixture can hand it canned output.
# --------------------------------------------------------------------------------------------------
Runner = Callable[[list, "str | None", float], "tuple[int, str]"]
Reader = Callable[[Path], "str | None"]


class Env:
    def __init__(self, run: Runner, read: Reader, now: dt.datetime, budget: float = 40.0,
                 clock: Callable[[], float] = time.monotonic):
        self.run, self.read, self.now, self.clock = run, read, now, clock
        self.deadline = clock() + budget
        self.calls = 0

    def sh(self, argv: list, cwd: "str | Path | None" = None) -> tuple[int, str]:
        """Run one command; (124, "") when the time budget is spent, (127, "") when it cannot start."""
        left = self.deadline - self.clock()
        if left <= 0:
            return 124, ""
        self.calls += 1
        # Exactly the time left (capped), with no floor: a floor lets the last call overrun the budget.
        return self.run(argv, str(cwd) if cwd else None, min(CALL_TIMEOUT, left))


def real_run(argv: list, cwd: "str | None", timeout: float = 20.0) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""
    return p.returncode, p.stdout


def real_read(path: Path) -> "str | None":
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"{path}: {e}") from e


def panel(state: str, reason: str = "", **extra: object) -> dict:
    return {"state": state, "reason": reason, **extra}


def unknown(reason: str, **extra: object) -> dict:
    return panel("unknown", reason, **extra)


def _json(out: str) -> "object | None":
    try:
        return json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return None


def slug_of(remote: str) -> "str | None":
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", remote or "")
    return m.group(1) if m else None


def _ts(s: str) -> "dt.datetime | None":
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


# --------------------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------------------
def load_config(env: Env, root: Path) -> tuple[dict, str]:
    cfg = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    try:
        raw = env.read(root / CONFIG)
    except ValueError as e:
        return cfg, f"The config cannot be read: {e}"
    if raw is None:
        return cfg, ""
    data = _json(raw)
    if not isinstance(data, dict):
        return cfg, f"The config is not a JSON object: {root / CONFIG}"
    for k, v in data.items():
        if k in DEFAULTS:
            cfg[k] = v
    return cfg, ""


# --------------------------------------------------------------------------------------------------
# Sources. Each returns a panel dict, and none raises: an error is an UNKNOWN panel with its reason.
# --------------------------------------------------------------------------------------------------
class Repo:
    def __init__(self, name: str, root: "Path | None", slug: "str | None", is_self: bool):
        self.name, self.root, self.slug, self.is_self = name, root, slug, is_self

    def gh(self, env: Env, args: list) -> tuple[int, str]:
        # In the repository's OWN directory, so a sibling with no parseable remote is still read as itself:
        # gh with no --repo reads the repository of its working directory, and this one's would be wrong.
        argv = ["gh", *args] + (["--repo", self.slug] if self.slug else [])
        return env.sh(argv, self.root)


def collect_prs(env: Env, repo: Repo, cfg: dict, sessions: list[dict]) -> dict:
    fields = "number,title,headRefOid,isDraft,mergeStateStatus,url"
    rc, out = repo.gh(env, ["pr", "list", "--state", "open", "--limit", str(PR_LIMIT), "--json", fields])
    data = _json(out) if rc == 0 else None
    if not isinstance(data, list):
        why = say("unknown.budget") if rc == 124 else say("unknown.gh")
        return unknown(why)
    by_pr = {s["pr"]: s for s in sessions if isinstance(s.get("pr"), int)}
    items = []
    for i, pr in enumerate(data):
        n = pr.get("number")
        head = str(pr.get("headRefOid") or "")
        item = {"repo": repo.name, "n": n, "title": str(pr.get("title") or ""), "url": str(pr.get("url") or ""),
                "head": head[:7], "draft": bool(pr.get("isDraft")), "merge_state": str(pr.get("mergeStateStatus") or ""),
                "author": (by_pr.get(n) or {}).get("name") or say("unknown.value")}
        if i < PR_DETAIL_CAP:
            item["review"] = review_of(env, repo, cfg, n, head)
            item["run"] = run_of(env, repo, cfg, head)
        else:
            item["review"] = {"state": "unknown", "head": ""}
            item["run"] = {"state": "unknown"}
        item["next"] = next_action(item)
        items.append(item)
    p = panel("ok", "", items=items, count=len(items))
    if len(data) >= PR_LIMIT:
        p["partial"] = True
        p["note"] = say("partial.note", n=PR_LIMIT)
    return p


_VERDICT_WORD = re.compile(r"\b(CLEAN|BLOCKED)\b")
_VERDICT_SHA = re.compile(r"\b(?:at|of|head|commit)\s+([0-9a-f]{7,40})\b")


def verdict_of(body: str) -> "tuple[str, str] | None":
    """(commit, verdict) of one review comment, or None when the comment is not a verdict. A verdict is a comment
    whose FIRST LINE says `review` or `re-check` (Review, Re-review, Delta review, Independent review) and holds CLEAN or
    BLOCKED in capitals. A verdict worded only in prose ("one mechanical blocker remains") is not read: the board then
    shows the review before it as stale, which asks for a re-review.
    The verdict is the LAST such word on the line, because a delta review quotes the one before it ("since my CLEAN
    at 0fdb8eb): CLEAN"). The commit is the first hex word after at, of, head or commit, so a run id is never read
    as one. A verdict that names no commit gives "" for it: it is a verdict, and it cannot be compared with a head."""
    first = next((ln for ln in str(body or "").splitlines() if ln.strip()), "")
    if not re.search(r"\b(?:review|re-?check)\b", first, re.I):
        return None
    words = _VERDICT_WORD.findall(first)
    if not words:
        return None
    m = _VERDICT_SHA.search(first)
    return (m.group(1) if m else ""), words[-1]


def review_of(env: Env, repo: Repo, cfg: dict, n: object, head: str) -> dict:
    if not head:
        return {"state": "unknown"}          # no head commit: no verdict can be compared with it
    rc, out = repo.gh(env, ["pr", "view", str(n), "--json", "comments"])
    data = _json(out) if rc == 0 else None
    if not isinstance(data, dict):
        return {"state": "unknown"}
    custom = cfg.get("review_pattern")
    try:
        pat = re.compile(str(custom)) if custom else None
    except re.error:
        return {"state": "unknown"}
    found = None
    for c in data.get("comments") or []:
        body = str((c or {}).get("body") or "")
        if pat:
            m = pat.search(body)
            v = (m.group(1), m.group(2)) if m else None
        else:
            v = verdict_of(body)
        if v:
            found = v                       # the LAST matching comment decides
    if not found:
        return {"state": "none"}
    sha, verdict = found[0], found[1].upper()
    if not sha:
        return {"state": "unknown", "head": ""}        # a verdict that names no commit: not "none", not a match
    if not head.startswith(sha) and not sha.startswith(head[: len(sha)]):
        return {"state": "stale", "head": sha[:7], "verdict": verdict}
    return {"state": "clean" if verdict == "CLEAN" else "blocked", "head": sha[:7], "verdict": verdict}


def run_of(env: Env, repo: Repo, cfg: dict, head: str) -> dict:
    wf = cfg.get("full_run_workflow")
    if not wf or not head:
        # no workflow, or no head: `gh run list --commit ""` ignores the empty filter and returns the newest
        # runs of other commits, which would be drawn as THIS pull request's run
        return {"state": "unknown"}
    rc, out = repo.gh(env, ["run", "list", "--workflow", str(wf), "--commit", head, "--limit", str(RUN_LIMIT),
                            "--json", "databaseId,status,conclusion,event"])
    data = _json(out) if rc == 0 else None
    if not isinstance(data, list):
        return {"state": "unknown"}
    ev = cfg.get("full_run_event")
    runs = [r for r in data if not ev or r.get("event") == ev]
    if not runs:
        # A full window of other events says nothing about a dispatched run beyond it.
        return {"state": "unknown", "partial": True} if len(data) >= RUN_LIMIT else {"state": "not dispatched"}
    r = runs[0]                              # gh lists newest first
    if r.get("status") != "completed":
        return {"state": "running", "id": r.get("databaseId")}
    c = r.get("conclusion")
    return {"state": "green" if c == "success" else "cancelled" if c in ("cancelled", "skipped") else "red",
            "id": r.get("databaseId")}


def next_action(item: dict) -> str:
    if item["merge_state"] in ("DIRTY", "CONFLICTING"):
        return say("next.conflict")
    if item["draft"]:
        return say("next.draft")
    rv, run = item["review"]["state"], item["run"]["state"]
    if rv == "none":
        return say("next.no_review")
    if rv == "stale":
        return say("next.stale_review")
    if rv == "blocked":
        return say("next.blocked")
    if rv == "unknown":
        return say("next.run_unknown")
    if run == "red":
        return say("next.run_red")
    if run == "not dispatched":
        return say("next.no_run")
    if run == "running":
        return say("next.run_wait")
    if run == "green":
        ms = item["merge_state"]
        if ms in ("CLEAN", "HAS_HOOKS"):
            return say("next.merge")
        return say({"BEHIND": "next.behind", "BLOCKED": "next.merge_blocked", "UNSTABLE": "next.unstable"}.get(ms, "next.merge_unknown"))
    return say("next.run_unknown")


def collect_worktrees(env: Env, root: Path, integration: str) -> dict:
    rc, out = env.sh(["git", "worktree", "list", "--porcelain"], root)
    if rc != 0:
        return unknown(say("unknown.budget") if rc == 124 else say("unknown.source", why="git worktree list failed"))
    rows, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                rows.append(cur)
                cur = {}
            continue
        k, _, v = line.partition(" ")
        cur[k] = v
    items = []
    for r in rows:
        path, head = r.get("worktree", ""), r.get("HEAD", "")
        if "bare" in r or not path:
            continue
        mrc = env.sh(["git", "merge-base", "--is-ancestor", head, f"origin/{integration}"], root)[0] if head else None
        merged = True if mrc == 0 else False if mrc == 1 else None     # 128 (no such ref) is UNKNOWN, not "not merged"
        src, status = env.sh(["git", "-C", path, "status", "--porcelain"], None)
        clean = (src == 0 and status.strip() == "")
        items.append({"path": path, "branch": r.get("branch", "(detached)").replace("refs/heads/", ""),
                      "head": head[:7], "merged": merged, "clean": clean if src == 0 else None,
                      "finished": bool(merged is True and clean is True)})
    return panel("ok", "", items=items, count=len(items), finished=sum(1 for i in items if i["finished"]))


def collect_issue_count(env: Env, repo: Repo) -> dict:
    rc, out = repo.gh(env, ["issue", "list", "--state", "open", "--limit", str(ISSUE_LIMIT), "--json", "number,title,labels"])
    data = _json(out) if rc == 0 else None
    if not isinstance(data, list):
        return unknown(say("unknown.budget") if rc == 124 else say("unknown.gh"))
    return panel("ok", "", count=len(data), partial=len(data) >= ISSUE_LIMIT, items=data)


def collect_machine(env: Env, cfg: dict) -> dict:
    """Processes of this user against the per-user limit, zombies, and stopped orphans."""
    rc, out = env.sh(["ps", "-A", "-o", "user=,stat=,ppid="])
    if rc != 0:
        return unknown(say("unknown.budget") if rc == 124 else say("unknown.source", why="ps failed"))
    me, procs, zomb, stopped = getpass.getuser(), 0, 0, 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] != me:
            continue
        procs += 1
        zomb += parts[1].startswith("Z")
        stopped += parts[1].startswith("T") and parts[2] == "1"
    limit = None
    rc2, out2 = env.sh(["sysctl", "-n", "kern.maxprocperuid"])
    if rc2 == 0 and out2.strip().isdigit():
        limit = int(out2.strip())
    else:
        rc3, out3 = env.sh(["sh", "-c", "ulimit -u"])
        if rc3 == 0 and out3.strip().isdigit():
            limit = int(out3.strip())
    meters = []
    if limit:
        meters.append({"key": "processes", "label": say("limit.processes"), "n": procs, "max": limit, "unit": "",
                       "warn": int(limit * cfg["process_warn_pct"] / 100)})
    else:
        meters.append({"key": "processes", "label": say("limit.processes"), "n": procs, "max": None,
                       "unit": "", "warn": None, "note": say("unknown.value")})
    meters.append({"key": "zombies", "label": say("limit.zombies"), "n": zomb, "max": None, "warn": cfg["zombie_warn"]})
    meters.append({"key": "stopped", "label": say("limit.stopped"), "n": stopped, "max": None, "warn": 1})
    return panel("ok", "", meters=meters)


# ---- coordination record ---------------------------------------------------------------------------
def read_record(env: Env, root: Path) -> tuple[str, "dict | str"]:
    """('ok', record) | ('none', '') | ('unreadable', reason). A corrupt file is never an empty record."""
    try:
        return _read_record(env, root)
    except Exception as e:                       # noqa: BLE001 -- reported as unreadable, never as 'no record'
        return "unreadable", type(e).__name__


def _read_record(env: Env, root: Path) -> tuple[str, "dict | str"]:
    rc, out = env.sh(["git", "rev-parse", "--git-common-dir"], root)
    if rc != 0 or not out.strip():
        return "unreadable", "git rev-parse failed"
    path = (Path(root) / out.strip()).resolve() / COORD_FILE
    try:
        raw = env.read(path)
    except ValueError as e:
        return "unreadable", str(e)
    if raw is None:
        return "none", ""
    data = _json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("sessions", {}), dict) \
            or not (data.get("coordinator") is None or isinstance(data.get("coordinator"), dict)):
        return "unreadable", f"{path} is not a coordination record"
    return "ok", data


def sessions_of(record: dict, repo_name: str) -> list[dict]:
    rows = []
    for path, row in sorted((record.get("sessions") or {}).items()):
        if not isinstance(row, dict):
            continue
        rows.append({"repo": repo_name, "path": path, "name": row.get("name"), "session_id": row.get("session_id"),
                     "branch": row.get("branch"), "issue": row.get("issue"), "pr": row.get("pr"),
                     "state": row.get("state") or "unknown", "updated": row.get("updated")})
    return rows


def coordinator_of(env: Env, record: dict, cfg: dict) -> "dict | None":
    c = record.get("coordinator")
    if not isinstance(c, dict) or not c.get("session_id"):
        return None
    row = next((r for r in (record.get("sessions") or {}).values()
                if isinstance(r, dict) and r.get("session_id") == c["session_id"]), None)
    stale, why = None, say("coord.fresh_unknown")
    if row:
        t = _ts(row.get("updated") or "")
        if t:
            mins = int((env.now - t).total_seconds() // 60)
            stale = mins > int(cfg["stale_minutes"])
            why = say("coord.stale", mins=mins) if stale else ""
    return {"name": c.get("name"), "session_id": c["session_id"], "since": c.get("since"), "stale": stale, "why": why}


def asks_of(env: Env, record: dict, cfg: dict) -> dict:
    """Only asks that REACHED the owner (`asked`) are shown. A `drafted` ask goes to the coordinator."""
    shown, drafted_stale = [], 0
    for a in record.get("asks") or []:
        if not isinstance(a, dict):
            continue
        if a.get("state") == "asked":
            shown.append({"title": str(a.get("title") or ""), "detail": str(a.get("detail") or ""),
                          "ref": str(a.get("ref") or ""), "where": str(a.get("where") or ""),
                          "asked_at": str(a.get("asked_at") or "")})
        elif a.get("state") == "drafted":
            t = _ts(str(a.get("drafted_at") or ""))
            if t and (env.now - t).total_seconds() > float(cfg["drafted_hours"]) * 3600:
                drafted_stale += 1
    return {"items": shown, "drafted_stale": drafted_stale}


def events_of(record: dict) -> list[dict]:
    return [{"time": str(e.get("time") or ""), "text": str(e.get("text") or ""), "source": "record"}
            for e in record.get("events") or [] if isinstance(e, dict)]


def collect_merged_today(env: Env, repo: Repo) -> "tuple[list[dict], bool] | None":
    """(events, reached_the_limit), or None when the list cannot be read."""
    try:
        return _merged_today(env, repo)
    except Exception:                            # noqa: BLE001 -- None means UNKNOWN, rendered as such
        return None


def _merged_today(env: Env, repo: Repo) -> "tuple[list[dict], bool] | None":
    today = env.now.strftime("%Y-%m-%d")
    rc, out = repo.gh(env, ["pr", "list", "--state", "merged", "--search", f"merged:>={today}", "--limit",
                            str(MERGED_LIMIT), "--json", "number,title,mergedAt"])
    data = _json(out) if rc == 0 else None
    if not isinstance(data, list):
        return None
    ev = []
    for p in data:
        t = str(p.get("mergedAt") or "")
        ev.append({"time": t[11:16] if len(t) >= 16 else "", "text": f"#{p.get('number')} {p.get('title')}",
                   "repo": repo.name, "source": "merged"})
    return sorted(ev, key=lambda e: e["time"]), len(data) >= MERGED_LIMIT


def collect_lines(env: Env, repo: Repo, cfg: dict, issues: dict) -> dict:
    lines = cfg.get("release_lines") or []
    if not lines:
        return unknown(say("unknown.config_lines"))
    if issues.get("state") != "ok":
        return unknown(issues.get("reason") or say("unknown.gh"))
    out = []
    for ln in lines:
        if not isinstance(ln, dict) or not ln.get("name"):
            continue
        skip = set(ln.get("exclude_labels") or [])
        blockers = [i for i in issues["items"] if not skip & {(lb or {}).get("name") for lb in i.get("labels") or []}]
        out.append({"name": str(ln["name"]), "blockers": len(blockers), "partial": bool(issues.get("partial")),
                    "steps": [{"n": b.get("number"), "title": str(b.get("title") or ""), "state": "blocked"} for b in blockers[:6]],
                    "next": str(ln.get("next") or "")})
    return panel("ok", "", items=out)


# --------------------------------------------------------------------------------------------------
# The whole board
# --------------------------------------------------------------------------------------------------
def guarded(label: str, fn: Callable[[], dict]) -> dict:
    """A collector never raises into the run: an error becomes an UNKNOWN panel that says so."""
    try:
        return fn()
    except Exception as e:                       # noqa: BLE001 -- converted to a visible unknown, never a silent 0
        return unknown(say("unknown.source", why=f"{label}: {type(e).__name__}"))


def integration_branch_of(env: Env, root: Path, cfg: dict) -> str:
    """The branch a finished worktree's commits must reach. First that exists: the configured one; `dev` when
    `origin/dev` exists (the git flow this marketplace ships: work merges to dev, and origin/HEAD is the install
    surface, so it lags dev by every unreleased commit); the remote's default branch; `main`."""
    named = cfg.get("integration_branch")
    if isinstance(named, str) and named.strip():
        return named.strip()
    if env.sh(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/dev"], root)[0] == 0:
        return "dev"
    rc, br = env.sh(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    return br.strip().split("/", 1)[-1] if rc == 0 and br.strip() else "main"


def sibling_origin_mismatch(env: Env, sroot: Path, declared: "str | None") -> str:
    """Why the sibling's directory is NOT the repository the record says it is, or "". The record gives a path AND
    a remote; `gh --repo <remote>` would read one repository while `git` reads the directory, and a relative path
    with `..` can point anywhere. So the directory's OWN origin must name the declared remote, or the sibling is
    left out and named. A sibling that declares no remote is read from its own directory only."""
    if not declared:
        return ""
    rc, out = env.sh(["git", "remote", "get-url", "origin"], sroot)
    own = slug_of(out.strip()) if rc == 0 else None
    if own is None:
        return say("sibling.origin_unreadable", path=str(sroot), remote=declared)
    if own.lower() != declared.lower():
        return say("sibling.origin_differs", path=str(sroot), own=own, remote=declared)
    return ""


def collect(env: Env, root: Path) -> dict:
    cfg, cfg_err = load_config(env, root)
    integration = integration_branch_of(env, root, cfg)
    me = Repo(root.name, root, None, True)     # gh infers the current repository from its directory: no --repo
    status, rec = read_record(env, root)
    record = rec if status == "ok" else {}
    repos: list[Repo] = [me]
    sessions: list[dict] = sessions_of(record, me.name) if status == "ok" else []
    unavailable: list[dict] = []
    ws = record.get("workspace") if isinstance(record.get("workspace"), dict) else {}
    for sib in (ws or {}).get("repos") or []:
        if not isinstance(sib, dict) or not sib.get("name"):
            continue
        sroot = Path(str(sib.get("path") or ""))
        if sib.get("path") and not sroot.is_absolute():
            sroot = (root / sroot).resolve()         # relative to the repository, never to the process directory
        if not sib.get("path") or not sroot.is_dir():
            unavailable.append({"repo": sib["name"], "why": "its path is missing"})
            continue
        declared = slug_of(str(sib.get("remote") or ""))
        bad = sibling_origin_mismatch(env, sroot, declared)
        if bad:
            unavailable.append({"repo": sib["name"], "why": bad})
            continue
        s_status, s_rec = read_record(env, sroot)
        if s_status == "unreadable":
            unavailable.append({"repo": sib["name"], "why": str(s_rec)})
            continue
        repos.append(Repo(str(sib["name"]), sroot, declared, False))
        if s_status == "ok":
            sessions += sessions_of(s_rec, str(sib["name"]))

    coord = coordinator_of(env, record, cfg) if status == "ok" else None
    open_sessions = [s for s in sessions if s["state"] != "closed"]
    mode = "orchestrated" if coord or len(open_sessions) > 1 else "single"

    prs_items: list[dict] = []
    prs_reasons: list[str] = []
    partial = False
    pr_unavailable = list(unavailable)
    for r in repos:
        p = guarded("pull requests", lambda r=r: collect_prs(env, r, cfg, sessions))
        if p["state"] == "ok":
            prs_items += p["items"]
            partial = partial or bool(p.get("partial"))
        else:
            prs_reasons.append(p["reason"])
            pr_unavailable.append({"repo": r.name, "why": p["reason"]})
    # A repo that cannot be read is NAMED, and the repos that can be read still show: one missing
    # sibling must not blank the whole sheet, and must never read as "no pull request".
    if prs_reasons and len(prs_reasons) == len(repos):
        prs = unknown(prs_reasons[0], items=[], unavailable=pr_unavailable)
    else:
        prs = panel("ok", "", items=prs_items, count=len(prs_items), partial=partial, unavailable=pr_unavailable)

    worktrees = guarded("worktrees", lambda: collect_worktrees(env, root, integration))
    issues = guarded("issues", lambda: collect_issue_count(env, me))
    machine = guarded("machine", lambda: collect_machine(env, cfg))
    meters = list(machine.get("meters") or []) if machine["state"] == "ok" else []
    limits = panel("ok", "", meters=meters) if machine["state"] == "ok" else unknown(machine["reason"], meters=[])
    if worktrees["state"] == "ok":
        limits["meters"].append({"key": "worktrees", "label": say("limit.worktrees"), "n": worktrees["count"],
                                 "max": None, "warn": cfg["worktree_warn"], "finished": worktrees["finished"]})
    if issues["state"] == "ok":
        limits["meters"].append({"key": "issues", "label": say("limit.issues"), "n": issues["count"], "max": None,
                                 "warn": None, "partial": issues["partial"]})
    limits["unknown"] = [k for k, p in (("worktrees", worktrees), ("issues", issues), ("processes", machine))
                         if p["state"] != "ok"]

    lines = guarded("release lines", lambda: collect_lines(env, me, cfg, issues))

    merged: list[dict] = []
    merged_unknown = False
    merged_partial = False
    for r in repos:
        m = collect_merged_today(env, r)
        if m is None:
            merged_unknown = True
        else:
            merged += m[0]
            merged_partial = merged_partial or m[1]
    events = sorted(events_of(record) + merged, key=lambda e: e["time"]) if status == "ok" or status == "none" else merged

    if status == "unreadable":
        sess_panel = unknown(say("unknown.record", why=str(rec)))
    elif status == "none" and not sessions:
        sess_panel = panel("ok", say("unknown.no_record"), items=[], none=True)
    else:
        sess_panel = panel("ok", "", items=sessions, unavailable=unavailable)
    asks = asks_of(env, record, cfg)
    if status == "unreadable":
        asks_panel = unknown(say("unknown.record", why=str(rec)), items=[], drafted_stale=0)
    else:
        asks_panel = panel("ok", say("unknown.no_record") if status == "none" else "", **asks)
    events_panel = panel("ok" if not merged_unknown else "unknown", say("unknown.gh") if merged_unknown else "", items=events)
    if events_panel["state"] == "ok" and status == "unreadable":
        events_panel.update(partial=True, note=say("unknown.record", why=str(rec)))      # recorded events cannot be read
    elif events_panel["state"] == "ok" and merged_partial:
        events_panel.update(partial=True, note=say("partial.note", n=MERGED_LIMIT))

    ste = [f"{k}: {f}" for k, v in (cfg.get("notes") or {}).items() if isinstance(v, str) for f in ste_flags(v, "description")]
    rc, head = env.sh(["git", "rev-parse", "--short", "HEAD"], root)
    return {
        "schema": SCHEMA,
        "generated": env.now.strftime("%Y-%m-%dT%H:%MZ"),
        "title": str(cfg["title"]),
        "repo": {"name": me.name, "commit": head.strip() if rc == 0 else None, "integration": integration},
        "mode": mode,
        "coordinator": coord,
        "workspace": {"repos": [r.name for r in repos], "unavailable": unavailable} if ws else None,
        "config_error": cfg_err,
        "panels": {
            "asks": asks_panel,
            "lines": lines,
            "prs": prs,
            "sessions": sess_panel,
            "limits": limits,
            "worktrees": worktrees,
            "events": events_panel,
        },
        "notes": {k: v for k, v in (cfg.get("notes") or {}).items() if isinstance(v, str)},
        "ste_warnings": ste,
    }


# --------------------------------------------------------------------------------------------------
# The page: one drawing sheet, server-rendered, no network, no script.
# --------------------------------------------------------------------------------------------------
CSS = """
:root {
  color-scheme: light dark;
  --paper: #ffffff; --ink: #14181f; --rule: #14181f; --hair: #c9ced6; --zebra: #f5f7fa; --muted: #5d6673;
  --blue: #1f5fbf; --blue-soft: #e7eefa; --red: #c42b1c; --green: #1f7a46; --amber: #a35f00;
  --f-sans: "Arial Narrow", "Helvetica Neue", Arial, system-ui, sans-serif;
  --f-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #11151b; --ink: #e4e8ee; --rule: #cfd5dd; --hair: #333c48; --zebra: #171c24; --muted: #98a2b0;
  --blue: #86a9f0; --blue-soft: #1c2840; --red: #ff8578; --green: #6fd39c; --amber: #f0b45c; } }
:root[data-theme="dark"] {
  --paper: #11151b; --ink: #e4e8ee; --rule: #cfd5dd; --hair: #333c48; --zebra: #171c24; --muted: #98a2b0;
  --blue: #86a9f0; --blue-soft: #1c2840; --red: #ff8578; --green: #6fd39c; --amber: #f0b45c; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.45 var(--f-sans); }
.page { padding-inline: 16px; padding-block: 16px 32px; }
.sheet { max-width: 1500px; margin: 0 auto; border: 1.5px solid var(--rule); }
.zones { display: grid; grid-template-columns: repeat(8, 1fr); font: 11px var(--f-mono); color: var(--muted); }
.zones span { text-align: center; padding: 2px 0; border-right: 1px solid var(--hair); }
.zones span:last-child { border-right: 0; }
.zones.top { border-bottom: 1px solid var(--rule); } .zones.bot { border-top: 1px solid var(--rule); }
.body { display: grid; grid-template-columns: 22px 1fr 22px; }
.rows { display: grid; grid-template-rows: repeat(4, 1fr); font: 11px var(--f-mono); color: var(--muted); }
.rows span { display: grid; place-items: center; border-bottom: 1px solid var(--hair); }
.rows span:last-child { border-bottom: 0; }
.rows.l { border-right: 1px solid var(--rule); } .rows.r { border-left: 1px solid var(--rule); }
.grid { padding: 18px; display: grid; gap: 18px; grid-template-columns: repeat(12, minmax(0, 1fr)); align-items: start; min-width: 0; }
.panel { border: 1.5px solid var(--rule); background: var(--paper); min-width: 0; display: grid; }
.ph { display: flex; align-items: stretch; border-bottom: 1.5px solid var(--rule); }
.ph .tab { background: var(--ink); color: var(--paper); font-weight: 600; width: 36px; display: grid; place-items: center; flex: none; }
.ph h2 { font-size: 1.15rem; font-weight: 600; margin: 0; padding: 7px 12px; flex: 1; }
.ph .ref { font: 11px var(--f-mono); color: var(--muted); padding: 10px 12px; white-space: nowrap; }
.pb { padding: 12px 16px 14px; min-width: 0; }
.foot { font-size: .82rem; color: var(--muted); padding: 8px 16px 10px; border-top: 1px solid var(--hair); }
.span-12 { grid-column: span 12; } .span-8 { grid-column: span 8; } .span-7 { grid-column: span 7; }
.span-5 { grid-column: span 5; } .span-4 { grid-column: span 4; }
@media (max-width: 1100px) { .span-8, .span-7, .span-5, .span-4 { grid-column: span 12; } }
@media (max-width: 640px) { .body { grid-template-columns: 0 1fr 0; } .rows { visibility: hidden; } .grid { padding: 12px; gap: 14px; }
  table { min-width: 0; } thead { display: none; } tbody tr { display: block; border-bottom: 1px solid var(--rule); padding: 4px 0; }
  td { display: grid; grid-template-columns: 76px 1fr; gap: 0 8px; border-bottom: 0; padding: 3px 10px; }
  td::before { content: attr(data-label); font: 11px var(--f-mono); color: var(--muted); } }
.mono { font-family: var(--f-mono); font-size: .86em; font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); } .mark { white-space: nowrap; font-weight: 500; }
.m-ok { color: var(--green); } .m-bad { color: var(--red); } .m-run { color: var(--blue); } .m-wait { color: var(--amber); } .m-idle { color: var(--muted); }
.unknown { color: var(--muted); font-style: italic; }
.ask { padding: 10px 0; border-bottom: 1px solid var(--hair); } .ask:last-child { border-bottom: 0; }
.ask .ref { font: .82rem var(--f-mono); color: var(--blue); display: block; }
.lines { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.line { border: 1px solid var(--rule); min-width: 0; }
.line-h { background: var(--blue-soft); border-bottom: 1px solid var(--rule); padding: 8px 12px; display: flex; justify-content: space-between; gap: 8px; }
.line-h .cnt { font: 500 .8rem var(--f-mono); color: var(--red); white-space: nowrap; }
.line ul { list-style: none; margin: 0; padding: 8px 12px; } .line li { padding: 3px 0; font-size: .92rem; }
.line .nx { font-size: .85rem; color: var(--muted); padding: 6px 12px 10px; border-top: 1px solid var(--hair); }
.tbl { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .92rem; min-width: 720px; }
th { text-align: left; font: 400 .78rem var(--f-mono); color: var(--muted); padding: 6px 10px; border-bottom: 1px solid var(--rule); }
td { padding: 8px 10px; border-bottom: 1px solid var(--hair); vertical-align: top; }
tbody tr:nth-child(odd) td { background: var(--zebra); } tr:last-child td { border-bottom: 0; }
td .sub { display: block; font: .76rem var(--f-mono); color: var(--muted); }
a { color: var(--blue); }
.sess { display: grid; grid-template-columns: minmax(120px, auto) 1fr auto; gap: 0 14px; }
.sess > div { padding: 7px 0; border-bottom: 1px solid var(--hair); min-width: 0; overflow-wrap: anywhere; }
.sess .q { display: block; font-size: .8rem; color: var(--muted); }
.bars { display: grid; gap: 14px; }
.bar-h { display: flex; justify-content: space-between; gap: 8px; font-size: .92rem; }
.bar-h .v { font: .82rem var(--f-mono); color: var(--blue); white-space: nowrap; }
.bar-h .v.hot { color: var(--red); }
.scale { position: relative; height: 12px; border: 1px solid var(--hair); background: var(--zebra); margin-top: 4px; }
.scale .fill { position: absolute; inset: 0 auto 0 0; background: var(--blue-soft); border-right: 2px solid var(--blue); }
.scale .fill.hot { background: color-mix(in srgb, var(--red) 18%, transparent); border-right-color: var(--red); }
.ticks { display: flex; justify-content: space-between; font: 10px var(--f-mono); color: var(--muted); margin-top: 2px; }
.tl { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(110px, 1fr); overflow-x: auto; padding-top: 4px; }
.tl .ev { position: relative; text-align: center; padding: 0 6px 4px; display: grid; gap: 6px; justify-items: center; }
.tl .ev::before { content: ""; position: absolute; top: 31px; left: 0; right: 0; border-top: 1px solid var(--ink); }
.tl .dot { width: 11px; height: 11px; border: 1.5px solid var(--ink); border-radius: 50%; background: var(--paper); position: relative; z-index: 1; }
.tl .x { font-size: .82rem; color: var(--muted); overflow-wrap: anywhere; }
.tb { border: 1.5px solid var(--rule); display: grid; grid-template-columns: 1fr 1fr; grid-column: -6 / -1; min-width: 0; }
@media (max-width: 1100px) { .tb { grid-column: 1 / -1; } }
.tb > div { padding: 6px 12px 8px; border-bottom: 1px solid var(--rule); min-width: 0; }
.tb .wide { grid-column: span 2; }
.tb small { display: block; font: 11px var(--f-mono); color: var(--muted); }
.tb b { font-weight: 600; overflow-wrap: anywhere; }
.empty { color: var(--muted); padding: 6px 0; }
"""

_e = html.escape


def mark(state: str) -> str:
    glyph, css = STATUS_OF.get(str(state).lower(), ("·", "m-idle"))
    return f'<span class="mark {css}">{glyph} {_e(str(state).capitalize())}</span>'


def _unknown_html(reason: str) -> str:
    return f'<div class="unknown">{_e(say("unknown.value").capitalize())}. {_e(reason)}</div>'


def _count(n: int, partial: bool) -> str:
    return say("partial.count", n=n) if partial else str(n)


def _gone(u: dict) -> str:
    """'Repo unavailable: <repo>, <why>.' for one unreadable repository."""
    return say("unavailable.repo", why=u["repo"] + ", " + u["why"])


def _step_li(s: dict) -> str:
    return "<li>" + mark(s["state"]) + " #" + _e(str(s["n"])) + " " + _e(s.get("title", "")) + "</li>"


def render_asks(board: dict, audience: str) -> str:
    a = board["panels"]["asks"]
    if a["state"] != "ok":
        return _unknown_html(a["reason"])
    body = "".join(
        f'<div class="ask"><b>{_e(i["title"])}</b><div>{_e(i["detail"])}</div>'
        + (f'<span class="ref">{_e(i["ref"])}</span>' if i["ref"] else "")
        + (f'<div class="muted">{_e(say("coord.asked_where", where=i["where"]))}</div>' if i["where"] else "")
        + "</div>" for i in a["items"]) or f'<div class="empty">{_e(say("empty.asks"))}</div>'
    if audience == "coordinator" and a.get("drafted_stale"):
        body += f'<div class="ask muted">{_e(say("coord.drafted_stale", n=a["drafted_stale"], hours=DEFAULTS["drafted_hours"]))}</div>'
    if a.get("reason") and not a["items"]:
        body += f'<div class="muted">{_e(a["reason"])}</div>'
    return body


def render_lines(board: dict) -> str:
    p = board["panels"]["lines"]
    if p["state"] != "ok":
        return _unknown_html(p["reason"])
    return '<div class="lines">' + "".join(
        f'<div class="line"><div class="line-h"><b>{_e(l["name"])}</b>'
        f'<span class="cnt">{_e(_count(l["blockers"], l["partial"]))} blocking</span></div>'
        "<ul>" + "".join(_step_li(s) for s in l["steps"]) + "</ul>"
        + (f'<div class="nx">{_e(l["next"])}</div>' if l["next"] else "") + "</div>" for l in p["items"]) + "</div>"


def render_prs(board: dict) -> str:
    p = board["panels"]["prs"]
    miss = "".join(f'<div class="unknown">{_e(_gone(u))}</div>'
                   for u in p.get("unavailable") or [])
    if p["state"] != "ok":
        return f'<div class="pb">{_unknown_html(p["reason"])}{miss}</div>'
    if not p["items"]:
        return f'<div class="pb"><div class="empty">{_e(say("empty.prs"))}</div>{miss}</div>'
    rows = "".join(
        "<tr><td class=\"mono\" data-label=\"PR\">"
        + (f'<a href="{_e(i["url"], quote=True)}">#{_e(str(i["n"]))}</a>' if i["url"].startswith("https://") else f"#{_e(str(i['n']))}")
        + f'<span class="sub">{_e(i["repo"])}</span></td><td data-label="Title">{_e(i["title"])}</td><td class="mono" data-label="Author">{_e(i["author"])}</td>'
        f'<td data-label="Review">{mark(i["review"]["state"])}'
        + (f'<span class="sub">{_e(i["review"]["head"])}</span>' if i["review"].get("head") else "")
        + f'</td><td data-label="Full run">{mark(i["run"]["state"])}<span class="sub">{_e(i["head"])}</span></td><td data-label="Next">{_e(i["next"])}</td></tr>'
        for i in p["items"])
    return ('<div class="pb tbl"><table><thead><tr><th>PR</th><th>Title</th><th>Author</th><th>Review</th>'
            f'<th>Full run</th><th>Next</th></tr></thead><tbody>{rows}</tbody></table>{miss}</div>')


def render_sessions(board: dict) -> str:
    p = board["panels"]["sessions"]
    if p["state"] != "ok":
        return _unknown_html(p["reason"])
    out = ""
    if p["items"]:
        out = '<div class="sess">' + "".join(
            f'<div class="mono">{_e(r["name"] or say("unknown.value"))}<span class="q">{_e(r["repo"])}</span></div>'
            f'<div>{_e(str(r["branch"] or ""))}'
            + (f'<span class="q">issue {_e(str(r["issue"]))}</span>' if r["issue"] else "") + "</div>"
            f'<div>{mark(r["state"])}</div>' for r in p["items"]) + "</div>"
    else:
        out = f'<div class="empty">{_e(p["reason"] or say("empty.sessions"))}</div>'
    for u in p.get("unavailable") or []:
        out += f'<div class="unknown">{_e(_gone(u))}</div>'
    return out


def render_limits(board: dict) -> str:
    p = board["panels"]["limits"]
    out = []
    for m in p["meters"]:
        hot = m.get("warn") is not None and m["n"] >= m["warn"] and m["warn"] > 0
        n = _count(m["n"], bool(m.get("partial")))
        if m.get("max"):
            pct = max(0, min(100, m["n"] / m["max"] * 100))
            out.append(f'<div><div class="bar-h"><span>{_e(m["label"])}</span><span class="v{" hot" if hot else ""}">{_e(n)} of {_e(str(m["max"]))}</span></div>'
                       f'<div class="scale" role="img" aria-label="{_e(m["label"])}: {_e(n)} of {_e(str(m["max"]))}"><div class="fill{" hot" if hot else ""}" style="width:{pct:.0f}%"></div></div>'
                       f'<div class="ticks"><span>0</span><span>{m["max"] // 2}</span><span>{m["max"]}</span></div></div>')
        else:
            note = f' <span class="unknown">{_e(m["note"])}</span>' if m.get("note") else ""
            out.append(f'<div class="bar-h"><span>{_e(m["label"])}</span><span class="v{" hot" if hot else ""}">{_e(n)}{note}</span></div>')
    for k in p.get("unknown") or []:
        out.append(f'<div class="bar-h"><span>{_e(k.capitalize())}</span><span class="unknown">{_e(say("unknown.value"))}</span></div>')
    return '<div class="bars">' + "".join(out) + "</div>" if out else _unknown_html(p.get("reason", ""))


def render_events(board: dict) -> str:
    p = board["panels"]["events"]
    if p["state"] != "ok":
        return _unknown_html(p["reason"])
    note = f'<div class="unknown">{_e(p["note"])}</div>' if p.get("partial") and p.get("note") else ""
    if not p["items"]:
        return (note or f'<div class="empty">{_e(say("empty.events"))}</div>')
    return note + '<div class="tl">' + "".join(
        f'<div class="ev"><span>{_e(e["time"])}</span><span class="dot"></span><span class="x">{_e(e["text"])}</span></div>'
        for e in p["items"]) + "</div>"


def render_html(board: dict, audience: str = "owner") -> str:
    prs, sess, lines = board["panels"]["prs"], board["panels"]["sessions"], board["panels"]["lines"]
    asks = board["panels"]["asks"]
    coord, orchestrated = board["coordinator"], board["mode"] == "orchestrated"
    notes = board.get("notes") or {}

    def foot(key: str) -> str:
        return f'<div class="foot">{_e(notes[key])}</div>' if notes.get(key) else ""

    def pan(letter: str, span: str, key: str, ref: str, body: str, note: str = "") -> str:
        return (f'<section class="panel {span}" aria-labelledby="h-{letter}"><div class="ph"><span class="tab">{letter}</span>'
                f'<h2 id="h-{letter}">{_e(say(key))}</h2><span class="ref">{_e(ref)}</span></div>{body}{note}</section>')

    tb = [f'<div class="wide"><small>{_e(say("tb.title"))}</small><b>{_e(board["title"])}</b></div>',
          f'<div><small>{_e(say("tb.repos"))}</small><b>{_e(", ".join((board.get("workspace") or {}).get("repos") or [board["repo"]["name"]]))}</b></div>',
          f'<div><small>{_e(say("tb.mode"))}</small><b>{_e(say("tb.mode_orchestrated" if orchestrated else "tb.mode_single"))}</b></div>']
    if orchestrated and coord:
        stale = f' ({_e(say("tb.stale"))})' if coord["stale"] else ""
        tb.append(f'<div><small>{_e(say("tb.coordinator"))}</small><b>{_e(coord["name"] or say("unknown.value"))}{stale}</b></div>')
    tb += [f'<div><small>{_e(say("tb.updated"))}</small><b>{_e(board["generated"])}</b></div>',
           f'<div><small>{_e(say("tb.commit"))}</small><b>{_e(board["repo"]["commit"] or say("unknown.value"))}</b></div>',
           f'<div><small>{_e(say("tb.sheet"))}</small><b>{_e(say("tb.sheet_value"))}</b></div>']

    pr_ref = say("unknown.value") if prs["state"] != "ok" else f'{_count(prs["count"], bool(prs.get("partial")))} open'
    panels = "".join([
        pan("A", "span-5", "h.asks", f'{len(asks["items"])} waiting', f'<div class="pb">{render_asks(board, audience)}</div>', foot("asks")),
        pan("B", "span-7", "h.lines", "blockers until release", f'<div class="pb">{render_lines(board)}</div>', foot("lines")),
        pan("C", "span-8", "h.prs", pr_ref, render_prs(board), foot("prs")),
        pan("D", "span-4", "h.sessions", say("unknown.value") if sess["state"] != "ok" else f'{len(sess["items"])} rows',
            f'<div class="pb">{render_sessions(board)}</div>', foot("sessions")),
        pan("E", "span-5", "h.limits", "current against maximum", f'<div class="pb">{render_limits(board)}</div>', foot("limits")),
        pan("F", "span-7", "h.today", "merges and events", f'<div class="pb">{render_events(board)}</div>', foot("today")),
        f'<div class="span-12" style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:18px"><div class="tb">{"".join(tb)}</div></div>',
    ])
    z = "".join(f"<span>{i}</span>" for i in range(1, 9))
    rows = "".join(f"<span>{c}</span>" for c in "ABCD")
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{_e(board["title"])}</title>\n'
            f'<style>{CSS}</style>\n</head>\n<body>\n<div class="page"><div class="sheet">'
            f'<div class="zones top">{z}</div><div class="body"><div class="rows l">{rows}</div>'
            f'<div class="grid">{panels}</div><div class="rows r">{rows}</div></div><div class="zones bot">{z}</div>'
            f'</div></div>\n</body>\n</html>\n')


# --------------------------------------------------------------------------------------------------
# Files and the command line
# --------------------------------------------------------------------------------------------------
def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".board-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def toplevel(env: Env, cwd: Path) -> "Path | None":
    rc, out = env.sh(["git", "rev-parse", "--show-toplevel"], cwd)
    return Path(out.strip()) if rc == 0 and out.strip() else None


def cmd_collect(args: argparse.Namespace, env: "Env | None" = None) -> int:
    env = env or Env(real_run, real_read, dt.datetime.now(dt.timezone.utc), float(args.budget_seconds))
    root = toplevel(env, Path(args.root))
    if root is None:
        print("not inside a git repository: no board", file=sys.stderr)
        return 2
    board = collect(env, root)
    state = root / STATE_DIR
    try:
        write_atomic(state / BOARD_JSON, json.dumps(board, indent=2, ensure_ascii=False) + "\n")
        write_atomic(state / BOARD_HTML, render_html(board, args.audience))
    except OSError as e:
        print(f"could not write the board: {e}", file=sys.stderr)
        return 3
    ok = sum(1 for p in board["panels"].values() if p["state"] == "ok")
    print(f"{say('cli.done', path=state / BOARD_HTML)} {ok} of {len(board['panels'])} panels measured.")
    if env.sh(["git", "check-ignore", "-q", f"{STATE_DIR}/{BOARD_JSON}"], root)[0] != 0:
        print(say("cli.ignore"))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    root = toplevel(Env(real_run, real_read, dt.datetime.now(dt.timezone.utc)), Path(args.root))
    if root is None:
        print("not inside a git repository: no board", file=sys.stderr)
        return 2
    try:
        board = json.loads((root / STATE_DIR / BOARD_JSON).read_text(encoding="utf-8"))
        write_atomic(root / STATE_DIR / BOARD_HTML, render_html(board, args.audience))
    except (OSError, ValueError) as e:
        print(f"could not render the board: {e}", file=sys.stderr)
        return 3
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("collect", "render"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--audience", choices=("owner", "coordinator"), default="owner")
        if name == "collect":
            p.add_argument("--budget-seconds", type=float, default=40.0)
    args = ap.parse_args(argv)
    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import status_board_selftest
        return status_board_selftest.run()
    if args.cmd == "collect":
        return cmd_collect(args)
    if args.cmd == "render":
        return cmd_render(args)
    ap.print_usage(sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
