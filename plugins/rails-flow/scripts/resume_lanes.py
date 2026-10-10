#!/usr/bin/env python3
"""List the lanes a cut-off session left unfinished, and print a brief for a fresh agent to resume each one (#1564).

Run:  resume_lanes.py [--root DIR] [--handoff-dir docs/product/handoff] ...
      resume_lanes.py --selftest
Exit: 0 every work order is done (or there is none), 1 at least one lane is unfinished and is listed, 2 cannot read (no such root)

WHAT IT READS. The committed work orders (`/rails-flow:handoff`, `docs/product/handoff/<slug>.md`; the pre-layout
`docs/handoff/<slug>.md` too). An order is UNFINISHED when its `## Progress` section says a Status other than `done`, or when it has
no Progress section at all (nothing is recorded, so nothing says it finished). For each it checks, with read-only git and no network:
the branch named on the Base commit line exists locally (else as `refs/remotes/origin/<branch>`, recoverable with `git fetch`, else
MISSING), the worktree that has it checked out, and that Last green is a commit here. It prints the Progress fields and the one command to
start with.

READ-ONLY, AND NOT A HOOK. It writes nothing, fetches nothing, commits nothing and runs no script the repository supplies: it runs
`git` (rev-parse, worktree list) and reads Markdown. It is invoked by a person or a session on purpose, never by a hook (#1821: a
hook runs under an environment a project's settings can set, so a hook that executed anything repository-controlled is the thing this
issue's threat model refuses).

LIMITS. The branch comes from the Base commit line ("`sha` on `feature/x`"); an order that names none is reported `branch unknown`.
It does not decide a lane is dead, merge anything, delete a worktree or re-run a gate: it says where the lane stands and what the
order itself recorded as next. Gate idempotence is the order's `Pending gates:` line, which a resuming agent re-runs and nothing else.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_handoff as ch  # noqa: E402  (one parser for the work order, not a copy that drifts)

HANDOFF_DIRS = ("docs/product/handoff", "docs/handoff")
BRANCH_RE = re.compile(r"\bon\s+`([^`]+)`")


def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def worktrees(root: Path) -> dict[str, str]:
    """branch name -> worktree path, from `git worktree list --porcelain`."""
    rc, out = _git(root, "worktree", "list", "--porcelain")
    if rc != 0:
        return {}
    found: dict[str, str] = {}
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and path:
            found[line[len("branch refs/heads/"):]] = path
    return found


def branch_state(root: Path, branch: str, trees: dict[str, str]) -> tuple[str, str]:
    """(state, detail): local / remote-only / missing / unknown."""
    if not branch:
        return "unknown", "the Base commit line names no branch"
    if _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")[0] == 0:
        return "local", trees.get(branch, "no worktree has it checked out")
    if _git(root, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}")[0] == 0:
        return "remote-only", f"recover with: git fetch origin {branch} && git worktree add <path> {branch}"
    return "missing", "neither a local nor an origin branch of that name exists"


def lane(path: Path, root: Path, trees: dict[str, str]) -> dict | None:
    """One work order -> its resume record, or None when it is done. An unreadable file is a lane too (`unreadable`)."""
    try:
        sections = ch.parse(path)
    except ch.Unusable as exc:
        return {"slug": path.stem, "file": str(path), "status": "unreadable", "note": str(exc)[:160], "branch": "", "state": "unknown",
                "detail": "", "fields": {}}
    base = next((sec for sec in sections if sec.matches(("base commit", "base", "written against", "from commit", "starting point"))), None)
    branch = ""
    if base is not None:
        m = BRANCH_RE.search("\n".join(base.lines))
        branch = m.group(1) if m else ""
    progress = next((sec for sec in sections if sec.matches(ch.PROGRESS_ALIASES)), None)
    fields = ch.parse_progress(progress.lines) if progress is not None else {}
    status = ch.progress_status(fields.get("status", "")) if fields.get("status") else "no-progress-recorded"
    if status == "done":
        return None
    state, detail = branch_state(root, branch, trees)
    green = fields.get("last green", "")
    if green and green.lower() != "none":
        shas = ch.SHA_RE.findall(green.lower())
        if not any(_git(root, "rev-parse", "--verify", "-q", f"{s}^{{commit}}")[0] == 0 for s in shas):
            detail += f"; Last green {green!r} is not a commit here"
    return {"slug": path.stem, "file": str(path.relative_to(root)) if path.is_relative_to(root) else str(path), "status": status,
            "branch": branch, "state": state, "detail": detail, "fields": fields}


def brief(item: dict) -> str:
    f = item["fields"]
    where = {"local": f"worktree: {item['detail']}", "remote-only": item["detail"], "missing": f"BRANCH MISSING: {item['detail']}",
             "unknown": item["detail"]}[item["state"]]
    lines = [f"- {item['slug']}  [{item['status']}]  branch: {item['branch'] or '(unknown)'}  ({item['state']})", f"    {where}",
             f"    order: {item['file']}"]
    if item["status"] == "unreadable":
        lines.append(f"    the order does not parse: {item.get('note', '')}")
    for name in ("last green", "current step", "next step", "pending gates"):
        lines.append(f"    {name.title()}: {f.get(name, '(not recorded)')}")
    start = (f"cd {item['detail']} && read {item['file']}" if item["state"] == "local" and not item["detail"].startswith("no worktree")
             else f"read {item['file']}; the order's Pending gates are the only gates to re-run")
    lines.append(f"    start with: {start}")
    return "\n".join(lines)


def collect(root: Path, dirs: tuple[str, ...]) -> list[dict]:
    trees = worktrees(root)
    items: list[dict] = []
    seen: set[str] = set()
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            if path.stem in seen:
                continue
            seen.add(path.stem)
            item = lane(path, root, trees)
            if item is not None:
                items.append(item)
    return items


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="resume_lanes.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--handoff-dir", action="append", help="a work-order directory relative to --root (repeatable); default: both layouts")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.root.is_dir():
        print(f"UNUSABLE: no such directory: {a.root}", file=sys.stderr)
        return 2
    items = collect(a.root.resolve(), tuple(a.handoff_dir) if a.handoff_dir else HANDOFF_DIRS)
    if not items:
        print("NO UNFINISHED LANES -- every work order says done (or there is none)")
        return 0
    print(f"{len(items)} UNFINISHED LANE(S):")
    print("\n".join(brief(i) for i in items))
    return 1


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    checks = [0]

    def expect(label: str, ok: bool, detail: object = "") -> None:
        checks[0] += 1
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        import fixture_git as _fg  # the fixture's git touches only its own temp repo (#1588)
        _fg.init(root, "-b", "dev")
        g = lambda *a: _fg.run(root, *a)
        (root / "a.txt").write_text("a\n")
        g("add", "."); g("commit", "-q", "-m", "base")
        head = g("rev-parse", "HEAD").stdout.strip()
        g("branch", "feature/live")
        g("branch", "feature/other")
        # a remote-tracking ref for a branch that has no local branch
        g("update-ref", "refs/remotes/origin/feature/remote-only", head)
        order_dir = root / "docs/product/handoff"
        order_dir.mkdir(parents=True)

        def order(slug: str, branch: str | None, progress: str | None) -> None:
            base = f"## Base commit\n`{head[:10]}`" + (f" on `{branch}`" if branch else "") + " -- the tree.\n"
            body = f"# Work order — {slug}\n\n{base}\n## Goal\nx\n"
            if progress is not None:
                body += "\n## Progress\n" + progress
            (order_dir / f"{slug}.md").write_text(body)

        full = lambda status, green=head[:10], gates="test-runner": (
            f"Status: {status}\nLast green: `{green}`\nCurrent step: AC-2\nNext step: the full suite\nPending gates: {gates}\n")
        order("live", "feature/live", full("in-progress"))
        order("finished", "feature/other", full("done", gates="none"))
        order("remote", "feature/remote-only", full("in-progress"))
        order("gone", "feature/deleted", full("stopped"))
        order("unrecorded", "feature/live", None)
        order("nobranch", None, full("in-progress"))
        order("badgreen", "feature/live", full("in-progress", green="deadbeef"))
        (order_dir / "junk.md").write_text("not a work order at all\n")
        wt = Path(td) / "wt-live"
        g("worktree", "add", "-q", str(wt), "feature/live")

        items = {i["slug"]: i for i in collect(root, HANDOFF_DIRS)}
        expect("a DONE order is not listed", "finished" not in items, sorted(items))
        expect("an in-progress order is listed", "live" in items and items["live"]["status"] == "in-progress", items.get("live"))
        expect("the worktree that has the branch is named", str(wt) in items["live"]["detail"], items["live"]["detail"])
        expect("a remote-only branch says how to recover it", items["remote"]["state"] == "remote-only" and "git fetch origin" in items["remote"]["detail"],
               items.get("remote"))
        expect("a branch that exists nowhere is MISSING", items["gone"]["state"] == "missing", items.get("gone"))
        expect("an order with no Progress section is listed as no-progress-recorded", items["unrecorded"]["status"] == "no-progress-recorded", items.get("unrecorded"))
        expect("an order that names no branch is `unknown`, not a crash", items["nobranch"]["state"] == "unknown", items.get("nobranch"))
        expect("a Last green that is not a commit is reported", "not a commit here" in items["badgreen"]["detail"], items.get("badgreen"))
        expect("a file that is not a work order is listed as unreadable, never skipped", items["junk"]["status"] == "unreadable", items.get("junk"))
        text = brief(items["live"])
        expect("the brief carries the recorded next step and pending gates", "Next Step: the full suite" in text and "Pending Gates: test-runner" in text, text)

        # THE CLI, end to end; and READ-ONLY: the repository is byte-identical afterwards
        before = g("status", "--porcelain").stdout + g("rev-parse", "HEAD").stdout + "".join(sorted(p.name for p in order_dir.iterdir()))
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(root)], capture_output=True, text=True)
        after = g("status", "--porcelain").stdout + g("rev-parse", "HEAD").stdout + "".join(sorted(p.name for p in order_dir.iterdir()))
        expect("CLI: unfinished lanes exit 1 and say so", done.returncode == 1 and "UNFINISHED LANE(S)" in done.stdout, (done.returncode, done.stdout[:200]))
        expect("CLI: it writes nothing and moves no ref", before == after, (before, after))
        for slug in ("live", "remote", "gone", "unrecorded", "nobranch", "badgreen", "junk"):
            (order_dir / f"{slug}.md").unlink()
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(root)], capture_output=True, text=True)
        expect("CLI: only done orders left exits 0", done.returncode == 0 and "NO UNFINISHED" in done.stdout, (done.returncode, done.stdout))
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(Path(td) / "nowhere")], capture_output=True, text=True)
        expect("CLI: a root that does not exist exits 2", done.returncode == 2, (done.returncode, done.stderr))
        legacy = root / "docs/handoff"
        legacy.mkdir(parents=True)
        (legacy / "old.md").write_text((order_dir / "finished.md").read_text().replace("done", "in-progress").replace("Pending gates: none", "Pending gates: x"))
        expect("the pre-layout docs/handoff/ is read too", any(i["slug"] == "old" for i in collect(root, HANDOFF_DIRS)))

    for f in failures:
        print(f"FAIL: {f}")
    print(f"resume_lanes selftest: {checks[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
