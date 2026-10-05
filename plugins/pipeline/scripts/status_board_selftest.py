#!/usr/bin/env python3
"""Prove the status board measures, says "unknown" when it cannot, and draws one honest sheet.

Run:  python3 status_board.py --selftest   (or execute this file directly)

Every outside source (`gh`, `git`, `ps`, `sysctl`) is answered from canned output, so nothing here needs
a network, a token or a running machine. The fixtures follow the rule the board exists for: a source
that cannot be read shows as UNKNOWN, never as 0. Each firing fixture has the near miss that must stay
quiet beside it (a count of 99 against a limit of 100, a drafted ask that is not yet old).

Not checked here: that `coordination.py` still writes the field names this module reads. That spans two
plugins, so `scripts/check_coordination_readers.py` owns it.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import status_board as sb  # noqa: E402

NOW = dt.datetime(2026, 10, 3, 18, 0, tzinfo=dt.timezone.utc)
FAILURES: list[str] = []
CHECKS = [0]
sb.getpass.getuser = lambda: "me"          # the user whose processes are counted


def check(label: str, ok: bool, detail: str = "") -> None:
    CHECKS[0] += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}" if detail else label)


# ---- the canned world ------------------------------------------------------------------------------
PR_FIELDS = "number,title,headRefOid,isDraft,mergeStateStatus,url"
RUN_FIELDS = "databaseId,status,conclusion,event"
SELF_REPO = "acme/app"


def head(n: int) -> str:
    return f"{n:02d}" + "0" * 38


def pr(n: int, *, draft: bool = False, merge: str = "CLEAN", title: str = "", url: str = "") -> dict:
    return {"number": n, "title": title or f"PR {n}", "headRefOid": head(n), "isDraft": draft,
            "mergeStateStatus": merge, "url": url or f"https://github.com/{SELF_REPO}/pull/{n}"}


def review(sha: str, verdict: str) -> dict:
    return {"body": f"**Independent review at {sha}: {verdict}.** Details follow."}


class World:
    """Canned answers for one repository, plus a log of every command the board ran."""

    def __init__(self, tmp: Path, name: str = "app", slug: "str | None" = None):
        self.root = (tmp / name).resolve()
        self.root.mkdir(exist_ok=True)
        self.slug = slug                         # gh gets `--repo slug` for a sibling only
        self.ans: dict = {}
        self.files: dict[str, "str | Exception"] = {}
        self.calls: list[list] = []
        self.cwd_log: list[tuple] = []
        self.timeouts: list[float] = []
        self.sibling_worlds: list["World"] = []
        r = str(self.root)
        self.on(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], "origin/dev\n", cwd=r)
        self.on(["git", "rev-parse", "--git-common-dir"], ".git\n", cwd=r)
        self.on(["git", "rev-parse", "--short", "HEAD"], "abc1234\n", cwd=r)
        if slug:                                 # a sibling's own origin names the repository it is
            self.on(["git", "remote", "get-url", "origin"], f"git@github.com:{slug}.git\n", cwd=r)
        self.on(["git", "worktree", "list", "--porcelain"], f"worktree {r}\nHEAD {'1' * 40}\nbranch refs/heads/dev\n\n", cwd=r)
        self.on(["git", "merge-base", "--is-ancestor", "1" * 40, "origin/dev"], "", cwd=r)
        self.on(["git", "-C", r, "status", "--porcelain"], "")
        self.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [])
        self.gh_set(["issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,labels"], [])
        self.gh_set(["pr", "list", "--state", "merged", "--search", "merged:>=2026-10-03", "--limit", "50",
                     "--json", "number,title,mergedAt"], [])

    @property
    def record_path(self) -> Path:
        return (self.root / ".git").resolve() / sb.COORD_FILE

    def on(self, argv: list, out: str = "", rc: int = 0, cwd: "str | None" = None) -> None:
        self.ans[(tuple(argv), cwd)] = (rc, out)

    def gh_set(self, args: list, data: object, rc: int = 0) -> None:
        argv = ["gh", *args] + (["--repo", self.slug] if self.slug else [])
        self.on(argv, json.dumps(data) if not isinstance(data, str) else data, rc,
                cwd=None if self.slug else str(self.root))

    def machine(self, ps: str = "", maxproc: "str | None" = "2666\n") -> None:
        self.on(["ps", "-A", "-o", "user=,stat=,ppid="], ps)
        if maxproc is None:
            self.on(["sysctl", "-n", "kern.maxprocperuid"], "", rc=1)
            self.on(["sh", "-c", "ulimit -u"], "", rc=1)
        else:
            self.on(["sysctl", "-n", "kern.maxprocperuid"], maxproc)

    def record(self, data: "dict | str | Exception") -> None:
        self.files[str(self.record_path)] = data if isinstance(data, (str, Exception)) else json.dumps(data)

    def config(self, data: dict) -> None:
        self.files[str(self.root / sb.CONFIG)] = json.dumps(data)

    def run(self, argv: list, cwd: "str | None", timeout: float = 20.0) -> tuple[int, str]:
        self.calls.append(list(argv))
        self.cwd_log.append((list(argv), cwd))
        self.timeouts.append(timeout)
        for w in (self, *self.sibling_worlds):
            hit = w.ans.get((tuple(argv), cwd)) or w.ans.get((tuple(argv), None))
            if hit is not None:
                return hit
        return 1, ""

    def read(self, path: Path) -> "str | None":
        for w in (self, *self.sibling_worlds):
            v = w.files.get(str(path))
            if isinstance(v, Exception):
                raise ValueError(str(v))
            if v is not None:
                return v
        return None

    def env(self, budget: float = 40.0, clock=None) -> "sb.Env":
        return sb.Env(self.run, self.read, NOW, budget, clock) if clock else sb.Env(self.run, self.read, NOW, budget)

    def board(self, budget: float = 40.0) -> dict:
        return sb.collect(self.env(budget), self.root)


def w_with(tmp: Path, name: str = "app", **kw: object) -> World:
    return World(tmp, name, **kw)


def items(board: dict, panel: str) -> list[dict]:
    return board["panels"][panel].get("items", [])


def by_n(board: dict) -> dict:
    return {i["n"]: i for i in items(board, "prs")}


def fstring_quote_reuse(source: str) -> list:
    """Line numbers where an f-string's replacement field holds a string quoted with the f-string's OWN
    quote. Python 3.12 allows it and every older Python refuses the file (the stock macOS python3 is 3.9),
    and CI runs 3.12, so nothing else sees it. On Python before 3.12 the tokenizer cannot see inside an
    f-string, but there such a file does not compile at all, so there is nothing to find."""
    import io
    import tokenize
    if not hasattr(tokenize, "FSTRING_START"):
        return []
    stack: list = []                         # (quote character, is triple) per open f-string
    bad: list = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.FSTRING_START:
            q = tok.string.lstrip("fFrRbBuU")
            if stack and not stack[-1][1] and stack[-1][0] == q[0]:
                bad.append(tok.start[0])
            stack.append((q[0], len(q) == 3))
        elif tok.type == tokenize.FSTRING_END:
            stack.pop()
        elif tok.type == tokenize.STRING and stack and not stack[-1][1]:
            if tok.string.lstrip("rRbBuUfF")[0] == stack[-1][0]:
                bad.append(tok.start[0])
    return sorted(set(bad))


def run() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td).resolve()
        pull_requests(tmp)
        measured_panels(tmp)
        unknown_not_zero(tmp)
        review_59(tmp)
        integration_branch(tmp)
        review_shapes(tmp)
        bounded_counts(tmp)
        coordination(tmp)
        workspace(tmp)
        asks_rules(tmp)
        ste(tmp)
        the_page(tmp)
        the_command(tmp)
        read_only(tmp)
        portable()
    for f in FAILURES:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"status_board selftest: {CHECKS[0]} checks, {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


# ---- the integration branch, and the review shapes in use (#1595 review, F1 to F3) -------------------
def integration_branch(tmp: Path) -> None:
    """Finished means the head reached the integration branch. The default stub makes origin/HEAD and origin/dev
    the same, which is why a repo whose origin/HEAD is main and whose work lands on dev was never tried."""
    done = "2" * 40

    def world(name: str, *, head_branch: str, has_dev: bool, config: "dict | None" = None, reaches: str = "dev") -> World:
        w = w_with(tmp, name)
        r = str(w.root)
        w.on(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], f"origin/{head_branch}\n", cwd=r)
        w.on(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/dev"], "", rc=0 if has_dev else 1, cwd=r)
        w.on(["git", "worktree", "list", "--porcelain"],
             f"worktree {r}\nHEAD {'1' * 40}\nbranch refs/heads/dev\n\nworktree /w/done\nHEAD {done}\nbranch refs/heads/fix/done\n\n", cwd=r)
        for b in ("main", "dev", "release"):
            w.on(["git", "merge-base", "--is-ancestor", done, f"origin/{b}"], "", rc=0 if b == reaches else 1, cwd=r)
        w.on(["git", "-C", "/w/done", "status", "--porcelain"], "")
        if config is not None:
            w.config(config)
        return w

    def done_row(w: World) -> dict:
        b = w.board()
        return {i["branch"]: i for i in items(b, "worktrees")}["fix/done"], b

    row, b = done_row(world("ib-dev", head_branch="main", has_dev=True))
    check("origin/HEAD is main, origin/dev exists, and the work is on dev: the board uses dev and the worktree is finished",
          b["repo"]["integration"] == "dev" and row["merged"] is True and row["finished"] is True,
          f'{b["repo"]["integration"]} {row}')
    row, b = done_row(world("ib-nodev", head_branch="main", has_dev=False, reaches="main"))
    check("with no origin/dev the integration branch is the remote's default branch",
          b["repo"]["integration"] == "main" and row["merged"] is True, str(b["repo"]))
    row, b = done_row(world("ib-cfg", head_branch="main", has_dev=True, config={"integration_branch": "release"}, reaches="release"))
    check("a configured integration_branch beats dev and origin/HEAD, and reaches the board (the key was dropped before)",
          b["repo"]["integration"] == "release" and row["merged"] is True, str(b["repo"]))
    row, b = done_row(world("ib-blank", head_branch="main", has_dev=True, config={"integration_branch": "  "}))
    check("a blank integration_branch is no configuration", b["repo"]["integration"] == "dev", str(b["repo"]))
    check("integration_branch is declared in DEFAULTS, so the config schema names it and load_config keeps it",
          "integration_branch" in sb.DEFAULTS
          and sb.load_config(world("ib-keep2", head_branch="main", has_dev=True, config={"integration_branch": "x"}).env(),
                             tmp / "ib-keep2")[0].get("integration_branch") == "x")


def review_shapes(tmp: Path) -> None:
    """The default reads the shapes reviewers write. status_board_verdicts.json holds the first line of every verdict
    comment on the last 40 pull requests (collected 2026-10-04), with the commit and verdict read BY EYE, so the
    expected values are not the matcher's own output. The old default read 29 of the 57."""
    data = json.loads((Path(__file__).with_name("status_board_verdicts.json")).read_text())
    verdicts, others = data["verdicts"], data["not_verdicts"]
    check("the fixture holds the 57 verdicts and 10 near-misses it was collected with", len(verdicts) == 57 and len(others) == 10,
          f"{len(verdicts)} {len(others)}")
    wrong = [(v["pr"], v["line"][:50], sb.verdict_of(v["line"])) for v in verdicts if sb.verdict_of(v["line"]) != (v["sha"], v["verdict"])]
    check("every real verdict comment is read: its commit and CLEAN or BLOCKED", wrong == [], str(wrong[:3]))
    read = [o for o in others if sb.verdict_of(o["line"]) is not None]
    check("no real near-miss is read as a verdict (dispositions, handoffs, a prose-worded re-review)", read == [], str(read[:3]))
    old = re.compile(r"Independent review at ([0-9a-f]{7,40})\W[^\n]{0,80}?\b(CLEAN|BLOCKED)\b")
    missed = [v for v in verdicts if not old.search(v["line"])]
    check("the fixture can see the defect: the old default misses 28 of the 57", len(missed) == 28, str(len(missed)))
    for line, why in [("mergeStateStatus is CLEAN, merge it", "no word review"),
                      ("Please review at abc1234 when you can", "no verdict word"),
                      ("a CLEAN build at abc1234", "no word review"),
                      ("", "an empty comment")]:
        check(f"a near-miss is not a verdict ({why}): {line[:40]}", sb.verdict_of(line) is None, str(sb.verdict_of(line)))
    check("a delta review that quotes the verdict before it is read by its own: 'since my CLEAN at 0fdb8eb): CLEAN'",
          sb.verdict_of("## Delta review of #1602 at 01a8be43 (since my CLEAN at 0fdb8eb): BLOCKED") == ("01a8be43", "BLOCKED"))
    check("a run id is never read as the commit", sb.verdict_of("## Review - CLEAN (run 37150723162, head fc28fcef)") == ("fc28fcef", "CLEAN"))

    h = head(50)
    w = w_with(tmp, "rv-shapes")
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(50), pr(51), pr(52)])
    w.gh_set(["pr", "view", "50", "--json", "comments"], {"comments": [{"body": f"**Independent re-review at {h[:7]}: CLEAN**"}]})
    w.gh_set(["pr", "view", "51", "--json", "comments"], {"comments": [{"body": "Independent review of #51: **CLEAN**. No blockers."}]})
    w.gh_set(["pr", "view", "52", "--json", "comments"], {"comments": [{"body": f"## Review - CLEAN (head {head(52)[:7]})"}, {"body": f"Re-check at {'f' * 7}: still CLEAN."}]})
    rv = {n: i["review"] for n, i in by_n(w.board()).items()}
    check("a re-review is a verdict on the head", rv[50]["state"] == "clean", str(rv[50]))
    check("a verdict that names no commit is UNKNOWN, never 'none' (which says 'Assign a review.')", rv[51]["state"] == "unknown", str(rv[51]))
    check("the last verdict decides, and a re-check of an older commit makes the review stale", rv[52]["state"] == "stale", str(rv[52]))
    w.config({"review_pattern": r"VERDICT at ([0-9a-f]{7,40}) (CLEAN|BLOCKED)"})
    w.gh_set(["pr", "view", "50", "--json", "comments"], {"comments": [{"body": f"VERDICT at {h[:7]} BLOCKED"}]})
    w.gh_set(["pr", "view", "51", "--json", "comments"], {"comments": [{"body": f"**Independent re-review at {head(51)[:7]}: CLEAN**"}]})
    rv = {n: i["review"] for n, i in by_n(w.board()).items()}
    check("a configured review_pattern (group 1 the commit, group 2 the verdict) is read in place of the built-in reader",
          rv[50]["state"] == "blocked" and rv[51]["state"] == "none", f"{rv[50]} {rv[51]}")


# ---- panel C: the pull requests ----------------------------------------------------------------------
def pull_requests(tmp: Path) -> None:
    w = w_with(tmp, "prs")
    w.config({"full_run_workflow": "gates.yml"})
    rows = [pr(11), pr(12), pr(13), pr(14), pr(15, draft=True), pr(16, merge="DIRTY"), pr(17), pr(18), pr(19),
            pr(20), pr(21), pr(22)]
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], rows)
    comments = {11: [review(head(11)[:7], "CLEAN")], 12: [review(head(12)[:7], "BLOCKED")],
                13: [review("deadbee", "CLEAN")], 14: [], 15: [review(head(15)[:7], "CLEAN")],
                16: [review(head(16)[:7], "CLEAN")], 17: [review(head(17)[:7], "CLEAN")],
                18: [review(head(18)[:7], "CLEAN")], 19: [review(head(19)[:7], "CLEAN")],
                20: [review(head(20)[:7], "BLOCKED"), {"body": "a plain comment"}, review(head(20)[:7], "CLEAN")],
                21: [review(head(21)[:7], "CLEAN")], 22: [review(head(22)[:7], "CLEAN")]}
    for n, c in comments.items():
        w.gh_set(["pr", "view", str(n), "--json", "comments"], {"comments": c})

    def runs(n: int, data: list) -> None:
        w.gh_set(["run", "list", "--workflow", "gates.yml", "--commit", head(n), "--limit", "20", "--json", RUN_FIELDS], data)
    d = "workflow_dispatch"
    runs(11, [{"databaseId": 1, "status": "completed", "conclusion": "success", "event": d}])
    for n in (12, 13, 14, 15, 16):
        runs(n, [])
    runs(17, [])
    runs(18, [{"databaseId": 2, "status": "in_progress", "conclusion": "", "event": d}])
    runs(19, [{"databaseId": 3, "status": "completed", "conclusion": "failure", "event": d}])
    runs(20, [{"databaseId": 4, "status": "completed", "conclusion": "success", "event": d}])
    runs(21, [{"databaseId": 5, "status": "completed", "conclusion": "success", "event": "pull_request"}])
    runs(22, [{"databaseId": 6, "status": "completed", "conclusion": "cancelled", "event": d}])
    w.record({"version": 1, "coordinator": None, "sessions": {
        "/w/a": {"session_id": "S1", "name": "claude-skills-be", "branch": "fix/x", "issue": 7, "pr": 11,
                 "state": "working", "updated": "2026-10-03T17:50Z"}}})
    b = w.board()
    t = by_n(b)
    check("the pull request panel is measured", b["panels"]["prs"]["state"] == "ok" and b["panels"]["prs"]["count"] == 12,
          str(b["panels"]["prs"].get("count")))
    expect = {11: ("clean", "green", "Merge."), 12: ("blocked", "not dispatched", "Fix the findings."),
              13: ("stale", "not dispatched", "Request a new review of the head."),
              14: ("none", "not dispatched", "Assign a review."), 15: ("clean", "not dispatched", "Finish the draft."),
              16: ("clean", "not dispatched", "Resolve the conflict."),
              17: ("clean", "not dispatched", "Dispatch a full run."), 18: ("clean", "running", "Wait for the full run."),
              19: ("clean", "red", "Fix the full run."), 20: ("clean", "green", "Merge."),
              21: ("clean", "not dispatched", "Dispatch a full run."), 22: ("clean", "cancelled", "Check the full run.")}
    for n, (rv, rn, nx) in expect.items():
        got = (t[n]["review"]["state"], t[n]["run"]["state"], t[n]["next"])
        check(f"PR {n}: review {rv}, run {rn}, next '{nx}'", got == (rv, rn, nx), str(got))
    check("a review of an OLDER commit reads stale, not clean", t[13]["review"]["state"] == "stale"
          and t[13]["review"]["head"] == "deadbee")
    check("the LAST matching review comment decides (BLOCKED then CLEAN is clean)", t[20]["review"]["state"] == "clean")
    check("a run from another event does not count as the dispatched full run", t[21]["run"]["state"] == "not dispatched")
    check("a pull request's author comes from the session row that holds it", t[11]["author"] == "claude-skills-be"
          and t[12]["author"] == "unknown", f"{t[11]['author']} / {t[12]['author']}")
    check("each row carries its repository and a link", t[11]["repo"] == "prs" and t[11]["url"].startswith("https://"))

    w2 = w_with(tmp, "prs2")                    # no workflow declared: the run is unknown, not 'none'
    w2.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(30)])
    w2.gh_set(["pr", "view", "30", "--json", "comments"], {"comments": [review(head(30)[:7], "CLEAN")]})
    b2 = w2.board()
    check("with no full-run workflow declared the run is UNKNOWN, never 'not dispatched'",
          by_n(b2)[30]["run"]["state"] == "unknown" and by_n(b2)[30]["next"] == "Check the full run.",
          str(by_n(b2)[30]["run"]))


# ---- panels B, D-limits, E, F, worktrees --------------------------------------------------------------
def measured_panels(tmp: Path) -> None:
    w = w_with(tmp, "panels")
    w.config({"release_lines": [{"name": "v1.2.0", "exclude_labels": ["post-launch", "v1.3.0"], "next": "Close the blockers."},
                                {"name": "v1.3.0", "exclude_labels": []}]})
    w.gh_set(["issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,labels"],
             [{"number": 1, "title": "Issue one", "labels": [{"name": "bug"}]}, {"number": 2, "title": "Issue two", "labels": [{"name": "post-launch"}]},
              {"number": 3, "title": "Issue three", "labels": [{"name": "v1.3.0"}]}, {"number": 4, "title": "Issue four", "labels": []},
              {"number": 5, "title": "Issue five", "labels": [{"name": "bug"}, {"name": "post-launch"}]}])
    r = str(w.root)
    w.on(["git", "worktree", "list", "--porcelain"],
         f"worktree {r}\nHEAD {'1' * 40}\nbranch refs/heads/dev\n\n"
         f"worktree /w/done\nHEAD {'2' * 40}\nbranch refs/heads/fix/done\n\n"
         f"worktree /w/dirty\nHEAD {'3' * 40}\nbranch refs/heads/fix/dirty\n\n"
         f"worktree /w/live\nHEAD {'4' * 40}\nbranch refs/heads/fix/live\n\n"
         f"worktree /w/unk\nHEAD {'5' * 40}\nbranch refs/heads/fix/unk\n\n"
         f"worktree /w/bare\nbare\n\n", cwd=r)
    w.on(["git", "merge-base", "--is-ancestor", "5" * 40, "origin/dev"], "", rc=128, cwd=r)
    w.on(["git", "-C", "/w/unk", "status", "--porcelain"], "")
    for h, merged in (("1", True), ("2", True), ("3", True), ("4", False)):
        w.on(["git", "merge-base", "--is-ancestor", h * 40, "origin/dev"], "", rc=0 if merged else 1, cwd=r)
    w.on(["git", "-C", r, "status", "--porcelain"], "")
    w.on(["git", "-C", "/w/done", "status", "--porcelain"], "")
    w.on(["git", "-C", "/w/dirty", "status", "--porcelain"], " M file.rb\n")
    w.on(["git", "-C", "/w/live", "status", "--porcelain"], "")
    w.machine("me S 1\nme Z 100\nme Z 101\nme T 1\nme T 4242\nme R 5\nroot Z 1\nother T 1\n")
    w.record({"version": 1, "coordinator": None, "sessions": {},
              "events": [{"time": "09:30", "text": "Decision recorded."}]})
    w.gh_set(["pr", "list", "--state", "merged", "--search", "merged:>=2026-10-03", "--limit", "50",
              "--json", "number,title,mergedAt"],
             [{"number": 7, "title": "Late fix", "mergedAt": "2026-10-03T16:05:00Z"},
              {"number": 6, "title": "Early fix", "mergedAt": "2026-10-03T08:15:00Z"}])
    b = w.board()
    ln = {l["name"]: l for l in items(b, "lines")}
    check("a release line counts open issues without its excluded labels", ln["v1.2.0"]["blockers"] == 2
          and [s["n"] for s in ln["v1.2.0"]["steps"]] == [1, 4], str(ln["v1.2.0"]))
    check("a line with no excluded label counts every open issue", ln["v1.3.0"]["blockers"] == 5)
    check("a release line step names its issue by number and title, in the record and on the page",
          ln["v1.2.0"]["steps"][0]["title"] == "Issue one" and "#1 Issue one" in sb.render_html(b)
          and "#2 Issue two" not in sb.render_html(b).split("v1.3.0")[0], str(ln["v1.2.0"]["steps"][:1]))
    wt = {i["branch"]: i for i in items(b, "worktrees")}
    check("a worktree is finished only when merged AND clean", wt["fix/done"]["finished"] is True
          and wt["fix/dirty"]["finished"] is False and wt["fix/dirty"]["merged"] is True
          and wt["fix/live"]["finished"] is False and wt["fix/live"]["merged"] is False, str(wt))
    check("a merge state git cannot answer (exit 128) is UNKNOWN, never 'not merged', and not finished",
          wt["fix/unk"]["merged"] is None and wt["fix/unk"]["finished"] is False, str(wt["fix/unk"]))
    check("a bare worktree is not listed", len(wt) == 5 and b["panels"]["worktrees"]["finished"] == 2,
          str(len(wt)))
    m = {x["key"]: x for x in b["panels"]["limits"]["meters"]}
    check("processes are counted for this user only, against the per-user limit", m["processes"]["n"] == 6
          and m["processes"]["max"] == 2666, str(m["processes"]))
    check("zombies are counted for this user only", m["zombies"]["n"] == 2, str(m["zombies"]))
    check("a stopped process counts as an orphan only when its parent is init", m["stopped"]["n"] == 1,
          str(m["stopped"]))
    check("worktrees and open issues are counted", m["worktrees"]["n"] == 5 and m["issues"]["n"] == 5)
    ev = items(b, "events")
    check("today lists recorded events and measured merges, in time order",
          [e["time"] for e in ev] == ["08:15", "09:30", "16:05"] and ev[0]["text"] == "#6 Early fix", str(ev))
    # near miss: a process count under its warning level is not hot
    page = sb.render_html(b)
    check("a meter under its warning level is not drawn hot", 'class="fill hot"' not in page)
    w.machine("".join("me S 1\n" for _ in range(2200)))
    hot = sb.render_html(w.board())
    check("a meter over its warning level is drawn hot", 'class="fill hot"' in hot)


# ---- the rule: unknown, never 0 ---------------------------------------------------------------------
def unknown_not_zero(tmp: Path) -> None:
    w = w_with(tmp, "down")
    for argv in list(w.ans):
        if argv[0][0] == "gh":
            w.ans[argv] = (1, "")
    w.machine("", maxproc=None)
    w.on(["ps", "-A", "-o", "user=,stat=,ppid="], "", rc=1)
    b = w.board()
    page = sb.render_html(b)
    check("with gh unavailable the pull request panel is UNKNOWN", b["panels"]["prs"]["state"] == "unknown"
          and "gh" in b["panels"]["prs"]["reason"], str(b["panels"]["prs"]))
    check("...and the page says unknown, not '0 open' or an empty table",
          "0 open" not in page and "No pull request is open" not in page and "Unknown" in page)
    check("with ps unavailable the limits panel is UNKNOWN", b["panels"]["limits"]["state"] == "unknown")
    check("an unmeasured issue count is listed as unknown, not 0",
          "issues" in b["panels"]["limits"]["unknown"] and not any(x["key"] == "issues" for x in b["panels"]["limits"]["meters"]))
    check("with no release line declared the panel is UNKNOWN and says what to add",
          b["panels"]["lines"]["state"] == "unknown" and "release_lines" in b["panels"]["lines"]["reason"])
    check("with gh unavailable Today is UNKNOWN, not an empty timeline", b["panels"]["events"]["state"] == "unknown")

    w = w_with(tmp, "nolimit")
    w.machine("me S 1\nme S 1\n", maxproc=None)
    m = {x["key"]: x for x in w.board()["panels"]["limits"]["meters"]}
    check("an unreadable per-user limit shows the count and an unknown maximum, with no bar",
          m["processes"]["n"] == 2 and m["processes"]["max"] is None and "bar-h" in sb.render_html(w.board())
          and 'class="scale"' not in sb.render_html(w.board()))

    w = w_with(tmp, "corrupt")
    w.record("{not json")
    b = w.board()
    check("a corrupt coordination record is UNKNOWN with its reason, never an empty session list",
          b["panels"]["sessions"]["state"] == "unknown" and "coordination record" in b["panels"]["sessions"]["reason"],
          str(b["panels"]["sessions"]))
    for body in ('[]', '{"sessions": []}', '{"coordinator": "x", "sessions": {}}'):
        w.record(body)
        check(f"a wrong-shaped record {body} is unknown", w.board()["panels"]["sessions"]["state"] == "unknown")
    w.record(OSError("permission denied"))
    check("an unreadable record file is unknown", w.board()["panels"]["sessions"]["state"] == "unknown")
    w = w_with(tmp, "norecord")
    b = w.board()
    check("no record at all is a measured fact, not an error: ok, and it says so",
          b["panels"]["sessions"]["state"] == "ok" and "no coordination record" in b["panels"]["sessions"]["reason"])

    w = w_with(tmp, "short")
    w.board(budget=5.0)
    check("every call is given a timeout no longer than the time left (budget 5 s)", w.timeouts and max(w.timeouts) <= 5.0
          and min(w.timeouts) >= 1.0, f"{min(w.timeouts):.2f}..{max(w.timeouts):.2f}")
    w = w_with(tmp, "long")
    w.board()
    check("with the default budget no call waits longer than 20 s", max(w.timeouts) == 20.0, str(max(w.timeouts)))
    w = w_with(tmp, "late")
    check("a spent time budget leaves every measured panel UNKNOWN", all(
        p["state"] == "unknown" for k, p in w.board(budget=-1)["panels"].items()
        if k in ("prs", "limits", "worktrees", "lines")))

    class Boom(World):
        def run(self, argv, cwd, timeout=20.0):
            if argv[:2] == ["gh", "pr"]:
                raise RuntimeError("boom")
            return super().run(argv, cwd, timeout)
    w = Boom(tmp, "boom")
    try:
        b = w.board()
    except Exception as e:                   # a collector that lets the error escape is the defect under test
        b = None
        check("a collector that raises becomes an UNKNOWN panel that names the error, and the run continues",
              False, f"the error escaped: {e!r}")
    if b is not None:
        check("a collector that raises becomes an UNKNOWN panel that names the error, and the run continues",
              b["panels"]["prs"]["state"] == "unknown" and "RuntimeError" in b["panels"]["prs"]["reason"]
              and b["panels"]["worktrees"]["state"] == "ok", str(b["panels"]["prs"]))
    w = w_with(tmp, "badcfg")
    w.files[str(w.root / sb.CONFIG)] = "{nope"
    check("a broken config is reported and the defaults still draw", w.board()["config_error"] != "")


# ---- the findings of the independent review of #1595 (59) ---------------------------------------------
def review_59(tmp: Path) -> None:
    # 1. An unreadable record: asks and events are UNKNOWN too, not "nothing is waiting" / "no events".
    w = w_with(tmp, "r59a")
    w.record("{ not json")
    b = w.board()
    page = sb.render_html(b)
    check("an unreadable record makes the ASKS panel UNKNOWN, with the record's reason",
          b["panels"]["asks"]["state"] == "unknown" and "coordination record" in b["panels"]["asks"]["reason"],
          str(b["panels"]["asks"]))
    check("...and the page does not say 'Nothing is waiting on you.'", "Nothing is waiting on you." not in page)
    ev = b["panels"]["events"]
    check("an unreadable record makes TODAY partial, never a plain empty timeline",
          ev.get("partial") is True and "coordination record" in ev.get("note", "") and "No event is recorded today." not in page,
          str(ev))
    check("the summary does not count the asks panel as measured", sum(1 for p in b["panels"].values() if p["state"] == "ok")
          == sum(1 for k, p in b["panels"].items() if p["state"] == "ok" and k != "asks"))
    w.record({"version": 1, "coordinator": None, "sessions": {}, "events": [{"time": "09:00", "text": "Recorded event."}]})
    b = w.board()
    check("near miss: a readable record with no asks says nothing is waiting, and Today is not partial",
          b["panels"]["asks"]["state"] == "ok" and not b["panels"]["events"].get("partial")
          and "Nothing is waiting on you." in sb.render_html(b))
    w = w_with(tmp, "r59b")
    b = w.board()
    check("no record at all: asks is ok and empty, and the page says why there are none",
          b["panels"]["asks"]["state"] == "ok" and "no coordination record" in sb.render_html(b))

    # 2. An empty HEAD is unknown, not "not merged"
    w = w_with(tmp, "r59c")
    r = str(w.root)
    w.on(["git", "worktree", "list", "--porcelain"], f"worktree {r}\nHEAD {'1' * 40}\nbranch refs/heads/dev\n\nworktree /w/nohead\nbranch refs/heads/x\n\n", cwd=r)
    w.on(["git", "-C", "/w/nohead", "status", "--porcelain"], "")
    wt = {i["branch"]: i for i in items(w.board(), "worktrees")}
    check("a worktree row with no HEAD reads merged UNKNOWN, never 'not merged'", wt["x"]["merged"] is None and wt["x"]["finished"] is False,
          str(wt["x"]))

    # 3. An empty head cannot make a review look current
    w = w_with(tmp, "r59d")
    p = pr(40)
    p["headRefOid"] = ""
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [p])
    w.gh_set(["pr", "view", "40", "--json", "comments"], {"comments": [review("abc1234", "CLEAN")]})
    check("a pull request with no head commit has an UNKNOWN review, not a current one",
          by_n(w.board())[40]["review"]["state"] == "unknown", str(by_n(w.board())[40]["review"]))
    # ...and cannot make ANOTHER commit's run look like this pull request's: `gh run list --commit ""` ignores the
    # empty filter and returns the newest runs, so the lookup must not be made at all (#1595 review, non-blocking)
    w.config({"full_run_workflow": "gates.yml"})
    w.gh_set(["run", "list", "--workflow", "gates.yml", "--commit", "", "--limit", "20", "--json", RUN_FIELDS],
             [{"databaseId": 9, "status": "completed", "conclusion": "success", "event": "workflow_dispatch"}])
    got = by_n(w.board())[40]
    check("a pull request with no head commit has an UNKNOWN run, never the newest run of another commit",
          got["run"]["state"] == "unknown", str(got["run"]))
    check("...and no run lookup is made for an empty commit",
          not any(c[:3] == ["gh", "run", "list"] and "" in c[c.index("--commit") + 1:c.index("--commit") + 2] for c in w.calls
                  if "--commit" in c), str([c for c in w.calls if c[:3] == ["gh", "run", "list"]]))

    # 4. A run list that hit its window cannot say "not dispatched"
    w = w_with(tmp, "r59e")
    w.config({"full_run_workflow": "gates.yml"})
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(41), pr(42)])
    for n in (41, 42):
        w.gh_set(["pr", "view", str(n), "--json", "comments"], {"comments": [review(head(n)[:7], "CLEAN")]})
    other = lambda k: [{"databaseId": i, "status": "completed", "conclusion": "success", "event": "pull_request"} for i in range(k)]
    w.gh_set(["run", "list", "--workflow", "gates.yml", "--commit", head(41), "--limit", "20", "--json", RUN_FIELDS], other(20))
    w.gh_set(["run", "list", "--workflow", "gates.yml", "--commit", head(42), "--limit", "20", "--json", RUN_FIELDS], other(19))
    t = by_n(w.board())
    check("20 runs of other events (the whole window) is UNKNOWN: a dispatched run may lie beyond it",
          t[41]["run"]["state"] == "unknown" and t[41]["run"].get("partial") is True, str(t[41]["run"]))
    check("near miss: 19 runs of other events (the window not full) is 'not dispatched'", t[42]["run"]["state"] == "not dispatched",
          str(t[42]["run"]))

    # 5. "Merge." only when GitHub says the pull request can merge
    w = w_with(tmp, "r59f")
    w.config({"full_run_workflow": "gates.yml"})
    states = {50: "CLEAN", 51: "HAS_HOOKS", 52: "BLOCKED", 53: "UNKNOWN", 54: "BEHIND", 55: "UNSTABLE", 56: ""}
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(n, merge=m) for n, m in states.items()])
    for n in states:
        w.gh_set(["pr", "view", str(n), "--json", "comments"], {"comments": [review(head(n)[:7], "CLEAN")]})
        w.gh_set(["run", "list", "--workflow", "gates.yml", "--commit", head(n), "--limit", "20", "--json", RUN_FIELDS],
                 [{"databaseId": n, "status": "completed", "conclusion": "success", "event": "workflow_dispatch"}])
    t = by_n(w.board())
    check("CLEAN and HAS_HOOKS with a clean review and a green run say 'Merge.'", t[50]["next"] == "Merge." and t[51]["next"] == "Merge.")
    for n in (52, 53, 54, 55, 56):
        check(f"merge state {states[n] or '(empty)'} with a clean review and a green run does NOT say 'Merge.'",
              t[n]["next"] != "Merge." and t[n]["next"] in {v for v, _ in sb.TEXT.values()}, t[n]["next"])
    check("BLOCKED names what to look for", "Find" in t[52]["next"], t[52]["next"])

    # 6. Today marks itself partial at its limit
    w = w_with(tmp, "r59g")
    day = lambda k: [{"number": i, "title": f"m{i}", "mergedAt": "2026-10-03T10:00:00Z"} for i in range(k)]
    argv = ["pr", "list", "--state", "merged", "--search", "merged:>=2026-10-03", "--limit", "50", "--json", "number,title,mergedAt"]
    w.gh_set(argv, day(50))
    b = w.board()
    check("a merged-today list that hit its limit marks Today partial, in the record and on the page",
          b["panels"]["events"].get("partial") is True and "50 or more" not in "" and "minimum" in sb.render_html(b), str(b["panels"]["events"].get("note")))
    w.gh_set(argv, day(49))
    check("near miss: 49 merged today is exact", not w.board()["panels"]["events"].get("partial"))

    # 7. The time floor: the last call cannot overrun the budget
    class Clock:
        t = 0.0
        def __call__(self): return self.t
    clk = Clock()
    seen: list[float] = []
    def slow(argv, cwd, timeout=20.0):
        seen.append(timeout)
        clk.t += 4.5                       # each call "takes" 4.5 s of a 5 s budget
        return 1, ""
    env = sb.Env(slow, lambda p: None, NOW, 5.0, clk)
    first = env.sh(["x"])
    second = env.sh(["y"])
    third = env.sh(["z"])
    check("a call is given exactly the time left, never a 1 s floor (0.5 s left -> a 0.5 s timeout)",
          len(seen) == 2 and seen[0] == 5.0 and abs(seen[1] - 0.5) < 1e-9, str(seen))
    check("once the budget is spent a call does not run at all (124)", third == (124, "") and len(seen) == 2, str((third, seen)))
    del first, second

    # 8. A relative sibling path resolves against --root, not the process directory
    a = w_with(tmp, "r59h")
    sib = World(tmp, "r59h-sib")
    a.sibling_worlds.append(sib)
    sib.record({"version": 1, "coordinator": None, "sessions": {"/s/x": {"session_id": "Z", "name": "z", "branch": "b", "state": "working"}}})
    a.record({"version": 1, "coordinator": None, "sessions": {}, "workspace": {"repos": [{"name": "sib", "path": "../r59h-sib", "remote": ""}]}})
    b = a.board()
    check("a relative sibling path resolves against the repository root", not b["panels"]["sessions"]["unavailable"]
          and [s["repo"] for s in items(b, "sessions")] == ["sib"], str(b["panels"]["sessions"]))


# ---- counts are bounded ------------------------------------------------------------------------------
def bounded_counts(tmp: Path) -> None:
    w = w_with(tmp, "many")
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(n) for n in range(1, 101)])
    w.gh_set(["issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,labels"],
             [{"number": n, "labels": []} for n in range(200)])
    w.config({"release_lines": [{"name": "r"}]})
    b = w.board()
    page = sb.render_html(b)
    check("a pull request list that hit its limit says 'or more', not an exact count",
          b["panels"]["prs"]["partial"] is True and "100 or more open" in page)
    check("an issue count that hit its limit says 'or more'", "200 or more" in page)
    check("a release line over a truncated issue list says 'or more'", items(b, "lines")[0]["partial"] is True)
    detail = [c for c in w.calls if c[:3] == ["gh", "pr", "view"]]
    check("per-pull-request lookups are capped, and the rest read unknown",
          len(detail) == sb.PR_DETAIL_CAP and by_n(b)[100]["review"]["state"] == "unknown", str(len(detail)))
    w = w_with(tmp, "few")
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(n) for n in range(1, 100)])
    b = w.board()
    check("99 against a limit of 100 is an exact count", not b["panels"]["prs"]["partial"]
          and "99 open" in sb.render_html(b))


# ---- coordination: the two modes, the coordinator, the rows --------------------------------------------
def coordination(tmp: Path) -> None:
    row = {"session_id": "S1", "name": "claude-skills-be", "branch": "fix/x", "issue": 7, "state": "working",
           "updated": "2026-10-03T17:50Z"}
    w = w_with(tmp, "single")
    w.record({"version": 1, "coordinator": None, "sessions": {"/w/a": row}})
    b = w.board()
    page = sb.render_html(b)
    check("one session and no coordinator is single-session mode", b["mode"] == "single" and b["coordinator"] is None)
    check("single-session mode draws no coordinator in the title block", "Coordinator" not in page and "One session" in page)

    two = {"/w/a": row, "/w/b": {**row, "session_id": "S2", "name": "claude-skills-cc", "branch": "fix/y"}}
    w.record({"version": 1, "coordinator": None, "sessions": two})
    check("two open sessions make it orchestrated even with no coordinator recorded",
          w.board()["mode"] == "orchestrated")
    w.record({"version": 1, "coordinator": None, "sessions": {**two, "/w/b": {**two["/w/b"], "state": "closed"}}})
    check("a closed lane does not count as a session", w.board()["mode"] == "single")

    coord = {"session_id": "C", "name": "claude-skills-60", "since": "2026-10-03T12:58Z"}
    crow = {"session_id": "C", "name": "claude-skills-60", "branch": "dev", "state": "working", "updated": "2026-10-03T17:40Z"}
    w.record({"version": 1, "coordinator": coord, "sessions": {"/w/c": crow, "/w/a": row}})
    b = w.board()
    page = sb.render_html(b)
    check("a recorded coordinator makes it orchestrated and names the coordinator in the title block",
          b["mode"] == "orchestrated" and "claude-skills-60" in page and "Several sessions" in page)
    check("a coordinator that updated 20 minutes ago is not stale", b["coordinator"]["stale"] is False
          and "(stale)" not in page, str(b["coordinator"]))
    w.record({"version": 1, "coordinator": coord, "sessions": {"/w/c": {**crow, "updated": "2026-10-03T14:00Z"}}})
    b = w.board()
    check("a coordinator silent for 240 minutes shows as STALE, never silently replaced",
          b["coordinator"]["stale"] is True and "(stale)" in sb.render_html(b)
          and b["coordinator"]["session_id"] == "C" and "240 minutes" in b["coordinator"]["why"], str(b["coordinator"]))
    w.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": row}})
    check("a coordinator with no row of its own has an UNKNOWN freshness, not fresh",
          w.board()["coordinator"]["stale"] is None and "no row" in w.board()["coordinator"]["why"])
    w.record({"version": 1, "coordinator": {}, "sessions": {"/w/a": row}})
    check("a coordinator object that names nobody is no coordinator", w.board()["coordinator"] is None)
    w.record({"version": 1, "coordinator": coord, "sessions": {"/w/c": {**crow, "updated": "2026-10-03T17:55Z"}, "/w/a": row}})
    sess = items(w.board(), "sessions")
    check("session rows are keyed by worktree path: one row per path, each with its repo",
          [s["path"] for s in sess] == ["/w/a", "/w/c"] and {s["repo"] for s in sess} == {"single"}, str(sess))
    check("the same name on two paths is two rows", len({s["path"] for s in sess}) == 2)
    row2 = {**row, "name": None}
    w.record({"version": 1, "coordinator": None, "sessions": {"/w/a": row2}})
    check("a row with no recorded name shows unknown, never an old name",
          "Unknown" in sb.render_html(w.board()) and "claude-skills-be" not in sb.render_html(w.board()))


# ---- workspace: one coordinator, two repositories, one record each --------------------------------------
def workspace(tmp: Path) -> None:
    a = w_with(tmp, "repoA")
    b_ = World(tmp, "repoB", slug="acme/sib")
    a.sibling_worlds.append(b_)
    rowA = {"session_id": "S1", "name": "sess-a", "branch": "fix/a", "issue": 1, "state": "working", "updated": "2026-10-03T17:50Z"}
    rowB = {"session_id": "S2", "name": "sess-b", "branch": "fix/b", "issue": 2, "state": "working", "updated": "2026-10-03T17:50Z"}
    coord = {"session_id": "C", "name": "claude-skills-60", "since": "2026-10-03T12:58Z"}
    ws = {"coordinator": {"session_id": "C", "name": "claude-skills-60"},
          "repos": [{"name": "repoB", "path": str(b_.root), "remote": "git@github.com:acme/sib.git"}]}
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA}, "workspace": ws})
    b_.record({"version": 1, "coordinator": coord, "sessions": {"/w/b": rowB}})
    a.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(1, title="A one")])
    b_.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(2, title="B two", url="https://github.com/acme/sib/pull/2")])
    board = a.board()
    page = sb.render_html(board)
    sess = {s["path"]: s["repo"] for s in items(board, "sessions")}
    check("the combined sheet shows both repositories' sessions, each tagged with its repo",
          sess == {"/w/a": "repoA", "/w/b": "repoB"}, str(sess))
    prs = {i["n"]: i["repo"] for i in items(board, "prs")}
    check("the combined sheet shows both repositories' pull requests, each tagged", prs == {1: "repoA", 2: "repoB"}, str(prs))
    check("the title block lists both repositories", "repoA, repoB" in page)
    check("a session of repo A is not in repo B's record (each row comes from its own file)",
          "/w/a" not in json.dumps(json.loads(b_.files[str(b_.record_path)])["sessions"])
          and "/w/b" not in json.dumps(json.loads(a.files[str(a.record_path)])["sessions"]))
    gh_b = [c for c in a.calls if c[:3] == ["gh", "pr", "list"] and "--repo" in c]
    check("a sibling repository is read with its own --repo, the current one without", len(gh_b) >= 1
          and all(c[-1] == "acme/sib" for c in gh_b))

    # a sibling with no parseable remote: gh must run IN that sibling's directory, never in this one
    c_ = World(tmp, "repoC")
    a.sibling_worlds.append(c_)
    c_.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(5, title="C five", url="https://github.com/acme/c/pull/5")])
    c_.record({"version": 1, "coordinator": coord, "sessions": {}})
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA},
              "workspace": {"repos": [{"name": "repoC", "path": str(c_.root), "remote": ""}]}})
    board = a.board()
    got = {i["n"]: i["repo"] for i in items(board, "prs")}
    check("a sibling with no parseable remote is read from its own directory, and its pull requests are tagged with it",
          got.get(5) == "repoC" and got.get(1) == "repoA", str(got))
    own = [cwd for argv, cwd in a.cwd_log if argv[:3] == ["gh", "pr", "list"] and "open" in argv and "--repo" not in argv]
    check("gh for every repository without --repo runs in that repository's directory",
          set(own) == {str(a.root), str(c_.root)} and None not in own, str(sorted(map(str, set(own)))))
    a.sibling_worlds.remove(c_)

    # a sibling whose path is missing: named, never zero, and the other repo still draws
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA},
              "workspace": {"repos": [{"name": "gone", "path": str(tmp / "no-such-dir"), "remote": ""}]}})
    board = a.board()
    page = sb.render_html(board)
    check("a missing sibling shows 'Repo unavailable', and the pull requests that can be read still show",
          "Repo unavailable: gone" in page and board["panels"]["prs"]["state"] == "ok" and 1 in by_n(board), page[:0])
    check("...and its absence is not read as zero sessions or zero pull requests",
          board["panels"]["sessions"]["unavailable"] and board["panels"]["prs"]["unavailable"])
    # a sibling whose record is corrupt
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA}, "workspace": ws})
    b_.record("{not json")
    board = a.board()
    check("a sibling with a corrupt record is unavailable, not empty",
          any(u["repo"] == "repoB" for u in board["panels"]["sessions"]["unavailable"]), str(board["panels"]["sessions"]))
    # a sibling with no record file is just a repo with no sessions
    b_.files.pop(str(b_.record_path))
    board = a.board()
    check("a sibling with NO record is a readable repo with no sessions, not unavailable",
          not board["panels"]["sessions"]["unavailable"] and {s["repo"] for s in items(board, "sessions")} == {"repoA"})
    # a coordinator restart in either repo finds the sibling through the workspace block
    check("the workspace block alone leads to the sibling (nothing else names it)", "repoB" in board["workspace"]["repos"])
    # the record's path and remote must agree with the directory's OWN origin (#1595 review, non-blocking)
    b_.record({"version": 1, "coordinator": coord, "sessions": {"/w/b": rowB}})
    lie = {"workspace": {"repos": [{"name": "repoB", "path": str(b_.root), "remote": "git@github.com:acme/other.git"}]}}
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA}, **lie})
    a.cwd_log.clear()
    board = a.board()
    why = [u["why"] for u in board["panels"]["prs"]["unavailable"] if u["repo"] == "repoB"]
    check("a sibling whose directory has a different origin than the record declares is left out and says so",
          len(why) == 1 and "acme/sib" in why[0] and "acme/other" in why[0] and 2 not in by_n(board) and 1 in by_n(board), str(why))
    check("...and none of its sessions is read as the repository's",
          {s["repo"] for s in items(board, "sessions")} == {"repoA"}, str(items(board, "sessions")))
    ran_there = [argv for argv, cwd in a.cwd_log if cwd == str(b_.root)]
    check("nothing but the origin check runs in a sibling whose origin differs, and no gh call names it",
          ran_there == [["git", "remote", "get-url", "origin"]]
          and not any(argv[:2] == ["gh", "pr"] and "--repo" in argv for argv, _ in a.cwd_log), str(ran_there))
    b_.on(["git", "remote", "get-url", "origin"], "", rc=128, cwd=str(b_.root))
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA}, "workspace": ws})
    board = a.board()
    why = [u["why"] for u in board["panels"]["prs"]["unavailable"] if u["repo"] == "repoB"]
    check("a sibling whose origin cannot be read is unavailable, never trusted on the record's word",
          len(why) == 1 and "cannot be read" in why[0] and 2 not in by_n(board), str(why))
    b_.on(["git", "remote", "get-url", "origin"], "https://github.com/ACME/Sib.git\n", cwd=str(b_.root))
    board = a.board()
    check("the origin match ignores case and the https form (near miss: the same repository)", 2 in by_n(board), str(sorted(by_n(board))))
    # a relative path with `..` is resolved against THIS repository and then held to the same origin rule
    rel = os.path.relpath(b_.root, a.root)
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA},
              "workspace": {"repos": [{"name": "repoB", "path": rel, "remote": "git@github.com:acme/sib.git"}]}})
    check("a relative sibling path with .. that leads to the declared repository is read", 2 in by_n(a.board()), rel)
    b_.on(["git", "remote", "get-url", "origin"], "git@github.com:acme/elsewhere.git\n", cwd=str(b_.root))
    check("a relative sibling path with .. that leads to another repository is refused",
          2 not in by_n(a.board()) and any(u["repo"] == "repoB" for u in a.board()["panels"]["prs"]["unavailable"]))
    b_.on(["git", "remote", "get-url", "origin"], "git@github.com:acme/sib.git\n", cwd=str(b_.root))

    # a sibling whose gh fails: that repo is unavailable for pull requests, the other still shows
    a.record({"version": 1, "coordinator": coord, "sessions": {"/w/a": rowA}, "workspace": ws})
    b_.record({"version": 1, "coordinator": coord, "sessions": {}})
    b_.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], "", rc=1)
    board = a.board()
    check("a sibling whose gh fails is named unavailable and the current repo's pull requests still show",
          any(u["repo"] == "repoB" for u in board["panels"]["prs"]["unavailable"]) and 1 in by_n(board))


# ---- asks: only a question that REACHED the owner is shown -----------------------------------------------
def asks_rules(tmp: Path) -> None:
    w = w_with(tmp, "asks")
    asks = [{"title": "Choose the branch", "detail": "Two options.", "ref": "#9", "state": "asked", "where": "the owner window",
             "asked_at": "2026-10-03T17:00Z"},
            {"title": "Draft only", "detail": "Not sent.", "state": "drafted", "drafted_at": "2026-10-03T17:30Z"},
            {"title": "Old draft", "detail": "Never sent.", "state": "drafted", "drafted_at": "2026-10-03T10:00Z"},
            {"title": "Closed", "detail": "Answered.", "state": "answered"}, "junk", {"title": "no state"}]
    w.record({"version": 1, "coordinator": None, "sessions": {}, "asks": asks})
    b = w.board()
    owner = sb.render_html(b, "owner")
    coordinator = sb.render_html(b, "coordinator")
    check("an ask shows only when its state is 'asked', and says where to answer",
          "Choose the branch" in owner and "Answer in the owner window." in owner, "")
    check("drafted, answered and stateless asks do not reach the owner",
          all(x not in owner for x in ("Draft only", "Old draft", "Closed", "no state")))
    check("a draft older than the limit is counted for the COORDINATOR, not shown to the owner",
          b["panels"]["asks"]["drafted_stale"] == 1 and "stayed drafted" not in owner and "stayed drafted" in coordinator,
          str(b["panels"]["asks"]))
    check("a draft younger than the limit is not counted (near miss)", b["panels"]["asks"]["drafted_stale"] == 1)
    w.record({"version": 1, "coordinator": None, "sessions": {}})
    check("with no asks the panel says nothing is waiting", "Nothing is waiting on you." in sb.render_html(w.board()))


# ---- ASD-STE100 --------------------------------------------------------------------------------------
def ste(tmp: Path) -> None:
    check("every sentence the board writes passes the STE lint", sb.lint_text_table() == [], str(sb.lint_text_table()))
    kinds = [k for _, k in sb.TEXT.values()]
    check("the lint is not vacuous: the table holds instructions and descriptions",
          kinds.count("instruction") >= 10 and kinds.count("description") >= 8, f"{kinds.count('instruction')} / {kinds.count('description')}")
    twenty = " ".join(["Run"] + ["now"] * 19)
    check("an instruction of exactly 20 words passes", sb.ste_flags(twenty, "instruction") == [])
    check("an instruction of 21 words is flagged", any("21 words" in f for f in sb.ste_flags(twenty + " now", "instruction")))
    check("a description of 25 words passes and 26 is flagged", sb.ste_flags(" ".join(["word"] * 25), "description") == []
          and any("26 words" in f for f in sb.ste_flags(" ".join(["word"] * 26), "description")))
    check("an instruction in the passive voice is flagged", any("passive" in f for f in sb.ste_flags("The findings are fixed by the author.", "instruction")))
    check("an active instruction is not flagged", sb.ste_flags("Fix the findings.", "instruction") == [])
    check("'open' and 'green' are not read as passive participles (near miss)",
          sb.ste_flags("The window is open and the run is green.", "instruction") == [])
    check("a description is checked for length only", sb.ste_flags("The finding was fixed by the author.", "description") == [])
    check("a label is never linted", sb.ste_flags("word " * 90, "label") == [])
    # the text the collector writes in a real run is in the table (a hand-typed sentence would not be)
    w = w_with(tmp, "text")
    w.config({"full_run_workflow": "gates.yml", "notes": {"prs": "A merge needs one clean review and one green run on the same commit.",
                                                          "sessions": " ".join(["word"] * 30)}})
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(1), pr(2, draft=True)])
    b = w.board()
    nexts = {i["next"] for i in items(b, "prs")}
    table = {t for t, _ in sb.TEXT.values()}
    check("every 'next' action is a sentence from the table", nexts <= table, str(nexts - table))
    check("a note in the config that breaks the rules is flagged in the record, not rewritten",
          any(f.startswith("sessions:") and "30 words" in f for f in b["ste_warnings"]) and not any(f.startswith("prs:") for f in b["ste_warnings"])
          and b["notes"]["sessions"] == " ".join(["word"] * 30), str(b["ste_warnings"]))


# ---- the page ----------------------------------------------------------------------------------------
def the_page(tmp: Path) -> None:
    w = w_with(tmp, "page")
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS],
             [pr(1, title="<script>alert(1)</script>", url='https://github.com/x/y/pull/1"onmouseover="z'),
              pr(2, title="Plain", url="javascript:alert(1)")])
    w.record({"version": 1, "coordinator": None, "sessions": {"/w/a": {"session_id": "S", "name": "<b>bold</b>",
              "branch": 'br"anch', "state": "working", "updated": "2026-10-03T17:50Z"}},
              "asks": [{"title": "<i>q</i>", "detail": "d", "state": "asked"}]})
    b = w.board()
    page = sb.render_html(b)
    check("no network: no link, script, import, source or url() that loads anything",
          not re.search(r"<link\b|<script\b|@import|\bsrc=|url\(", page), "")
    check("the only href is an https anchor", all(h.startswith("https://") for h in re.findall(r'href="([^"]*)"', page)),
          str(re.findall(r'href="([^"]*)"', page)))
    check("a javascript: link is not drawn as a link", "javascript:" not in page)
    check("page data is escaped: a title, a name, a branch and an ask cannot inject markup",
          "<script>alert" not in page and "&lt;script&gt;" in page and "<b>bold" not in page and "<i>q" not in page
          and 'br"anch' not in page and 'onmouseover="z' not in page)
    check("the document is complete: doctype, lang, charset, viewport and title",
          page.startswith("<!doctype html>") and '<html lang="en">' in page and '<meta charset="utf-8">' in page
          and 'name="viewport" content="width=device-width, initial-scale=1"' in page and "<title>Status board</title>" in page)
    check("theme tokens are on :root, dark follows the system, and a forced theme wins",
          ":root {" in page and "--paper:" in page and "@media (prefers-color-scheme: dark)" in page
          and ':root:not([data-theme="light"])' in page and ':root[data-theme="dark"]' in page)
    check("the body has an explicit background", re.search(r"body \{[^}]*background: var\(--paper\)", page) is not None)
    check("phone width: a 16px gutter, a narrow breakpoint, and tables scroll inside their own box",
          "padding-inline: 16px" in page and "@media (max-width: 640px)" in page and ".tbl { overflow-x: auto; }" in page)
    labels = re.findall(r'<td[^>]*data-label="([^"]+)"', page)
    check("on a phone each table cell carries its column name, and the header row is hidden",
          labels[:6] == ["PR", "Title", "Author", "Review", "Full run", "Next"] and "thead { display: none; }" in page
          and "attr(data-label)" in page, str(labels[:6]))
    css = re.sub(r'@media \(prefers-color-scheme: dark\) \{ :root:not\(\[data-theme="light"\]\) \{[^}]*\} \}', "", sb.CSS)
    css = re.sub(r":root[^{]*\{[^}]*\}", "", css)
    check("a hard-coded colour appears only in the theme blocks (everything else uses a token)",
          re.findall(r"#[0-9a-fA-F]{3,8}\b", css) == [] and "var(--ink)" in css, str(re.findall(r"#[0-9a-fA-F]{3,8}\b", css)[:5]))
    check("the drawing sheet has its zone frame: zones 1 to 8 top and bottom, rows A to D left and right",
          page.count('<div class="zones') == 2 and all(f"<span>{i}</span>" in page for i in range(1, 9))
          and page.count('<div class="rows') == 2)
    for letter, head_ in zip("ABCDEF", ("Needs you", "Release lines", "Open pull requests", "Sessions", "Limits", "Today")):
        check(f"panel {letter} is drawn with its heading", f'<span class="tab">{letter}</span><h2 id="h-{letter}">{head_}</h2>' in page)
    check("the title block carries title, repositories, mode, updated, commit and sheet",
          all(x in page for x in ("Title", "Repositories", "Mode", "Updated", "Commit", "Sheet", "1 of 1", "abc1234", "2026-10-03T18:00Z")))
    check("a status is a glyph AND a word, never a color alone", "● Working" in page and "? Unknown" in page and "– Closed" not in page, "")
    check("the page is a pure function of the record (render twice, and from the JSON text)",
          sb.render_html(b) == sb.render_html(json.loads(json.dumps(b))) == page)


# ---- the command line, end to end, with a stub gh ----------------------------------------------------
def the_command(tmp: Path) -> None:
    stub = tmp / "stub"
    stub.mkdir()
    gh = stub / "gh"
    gh.write_text("#!/bin/sh\necho '[]'\n")
    gh.chmod(0o755)
    repo = tmp / "cli-repo"
    repo.mkdir()
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "GIT_CEILING_DIRECTORIES": str(tmp)}
    for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(cmd, cwd=repo, env=env, check=True, capture_output=True)
    me = [sys.executable, str(Path(__file__).resolve().parent / "status_board.py")]
    done = subprocess.run([*me, "collect", "--root", str(repo)], capture_output=True, text=True, env=env)
    state = repo / ".claude" / "state"
    check("collect exits 0 and writes board.json and board.html", done.returncode == 0
          and (state / "board.json").is_file() and (state / "board.html").is_file(), f"{done.returncode} {done.stderr!r}")
    data = json.loads((state / "board.json").read_text())
    check("board.json is the record: schema, panels, mode and a timestamp", data["schema"] == 1 and "prs" in data["panels"]
          and data["mode"] == "single" and data["generated"].endswith("Z"))
    check("it tells the user to ignore the state directory when git does not", "Add .claude/state/ to .gitignore." in done.stdout, done.stdout)
    check("no temp file is left behind", [p.name for p in state.glob(".board-*")] == [])
    (repo / ".gitignore").write_text(".claude/state/\n")
    again = subprocess.run([*me, "collect", "--root", str(repo)], capture_output=True, text=True, env=env)
    check("once the directory is ignored the hint goes away", again.returncode == 0 and "gitignore" not in again.stdout, again.stdout)
    html_before = (state / "board.html").read_text()
    (state / "board.html").write_text("stale")
    rr = subprocess.run([*me, "render", "--root", str(repo)], capture_output=True, text=True, env=env)
    check("render rebuilds the page from board.json alone", rr.returncode == 0 and (state / "board.html").read_text() != "stale"
          and "<!doctype html>" in (state / "board.html").read_text(), rr.stderr)
    outside = tmp / "not-a-repo"
    outside.mkdir()
    no = subprocess.run([*me, "collect", "--root", str(outside)], capture_output=True, text=True, env=env)
    check("outside a git repository it exits 2 and says so", no.returncode == 2 and "not inside a git repository" in no.stderr,
          f"{no.returncode} {no.stderr!r}")
    blocked = tmp / "cli-blocked"
    blocked.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=blocked, env=env, check=True, capture_output=True)
    (blocked / ".claude").write_text("a file, not a directory")
    bad = subprocess.run([*me, "collect", "--root", str(blocked)], capture_output=True, text=True, env=env)
    check("when the files cannot be written it exits 3 and says so", bad.returncode == 3 and "could not write" in bad.stderr,
          f"{bad.returncode} {bad.stderr!r}")
    check("the console line is one sentence and a count (the SessionStart budget in PR 2 depends on it)",
          len(done.stdout.splitlines()[0].split()) < 30)
    check("the file mode is owner-only", oct((state / "board.json").stat().st_mode & 0o777) == "0o600")
    del html_before


# ---- shipped scripts must parse on the stock python3 (3.9) ---------------------------------------------
def portable() -> None:
    here = Path(__file__).resolve().parent
    check("the lint sees an f-string that reuses its own quote",
          fstring_quote_reuse('x = f"{d["k"]}"\n') != [] or not hasattr(__import__("tokenize"), "FSTRING_START"))
    check("near miss: an f-string with a different inner quote is fine",
          fstring_quote_reuse("x = f\"{d['k']}\"\n") == [] and fstring_quote_reuse("x = f'{d[\"k\"]}'\n") == [])
    check("near miss: a triple-quoted f-string may hold a single-quoted string",
          fstring_quote_reuse('x = f"""{d["k"]}"""\n') == [])
    for name in ("status_board.py", "status_board_selftest.py"):
        found = fstring_quote_reuse((here / name).read_text(encoding="utf-8"))
        check(f"no f-string in {name} reuses its own quote (that file would not parse on Python 3.9)", found == [], str(found))


# ---- read-only ---------------------------------------------------------------------------------------
def read_only(tmp: Path) -> None:
    w = w_with(tmp, "ro")
    w.config({"full_run_workflow": "gates.yml", "release_lines": [{"name": "r"}]})
    w.gh_set(["pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], [pr(1)])
    w.record({"version": 1, "coordinator": None, "sessions": {}, "workspace": {"repos": [{"name": "x", "path": str(tmp), "remote": ""}]}})
    w.board()
    gh_ok = {("pr", "list"), ("pr", "view"), ("run", "list"), ("issue", "list")}
    git_ok = {"rev-parse", "symbolic-ref", "remote", "worktree", "merge-base", "-C", "check-ignore"}
    bad = []
    for c in w.calls:
        if c[0] == "gh" and tuple(c[1:3]) not in gh_ok:
            bad.append(c)
        if c[0] == "gh" and c[2] == "list" and "--limit" not in c:
            bad.append(["UNBOUNDED"] + c)
        if c[0] == "git" and c[1] not in git_ok:
            bad.append(c)
        if c[0] not in ("gh", "git", "ps", "sysctl", "sh"):
            bad.append(c)
    check("the board runs only read verbs, and every gh list is bounded by --limit", not bad, str(bad[:3]))
    check("the board ran a real set of commands (the check above is not vacuous)", len(w.calls) >= 12, str(len(w.calls)))
    writes = [c for c in w.calls if c[0] == "git" and c[1] in ("fetch", "checkout", "commit", "add", "push")]
    check("it never fetches, checks out, commits or pushes", writes == [])


if __name__ == "__main__":
    sys.exit(run())
