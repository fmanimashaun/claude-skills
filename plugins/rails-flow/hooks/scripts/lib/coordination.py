#!/usr/bin/env python3
"""The coordination record: which session holds which worktree lane (#1581, #1585).

One record per repository, `$(git rev-parse --git-common-dir)/coordination.json`, so every worktree of
a clone sees the same file and a sibling repository keeps its own. It is keyed by WORKTREE PATH, not
by session name: names rotate at every restart, a path does not. `session_id` and `name` are
attributes of a row.

THE COORDINATOR IS THE ONLY WRITER (the owner's direction on #1585). Sessions' hooks only READ the
record; the write commands refuse a caller whose session id is not `coordinator.session_id`, unless
no coordinator is recorded and the caller is claiming the role. One writer means no lock, and the
file is replaced whole (a temp file in the same directory, then rename), so a reader never sees half
of it. A lone session is its own coordinator: it claims the role and records its own lane.

UNKNOWN KEYS SURVIVE. The record carries a `workspace` block and per-row fields that other features
add (#1585); every write loads the whole record and puts back what it does not understand, so adding
a field needs no migration.

    python3 coordination.py lanes   --session-id ID [--cwd DIR]
    python3 coordination.py claim   --session-id ID [--name N] [--cwd DIR]
    python3 coordination.py assign  --session-id ID --path P --branch B [--issue N] [--owner ID] [--name N] [--cwd DIR]
    python3 coordination.py close   --session-id ID --path P [--cwd DIR]
    python3 coordination.py workspace --session-id ID --coordinator-name N [--sibling NAME PATH REMOTE]... [--cwd DIR]
    python3 coordination.py --selftest

Exit: 0 done, 2 refused (the message names the coordinator), 3 could not read the record.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
NAME = "coordination.json"


class RecordError(Exception):
    """The record exists but cannot be read: a corrupt file is NOT an empty one."""


def common_dir(cwd: str | os.PathLike = ".") -> Path | None:
    """The repository's common git dir, absolute, or None outside a git repository."""
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=str(cwd), capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return (Path(cwd) / out.stdout.strip()).resolve()


def record_path(cwd: str | os.PathLike = ".") -> Path | None:
    gd = common_dir(cwd)
    return gd / NAME if gd else None


def load(path: Path) -> dict:
    """The record, or a fresh one when there is no file. An unreadable file raises RecordError."""
    if not path.exists():
        return {"version": VERSION, "coordinator": None, "sessions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RecordError(f"{path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("sessions", {}), dict):
        raise RecordError(f"{path}: not a coordination record")
    data.setdefault("version", VERSION)
    data.setdefault("coordinator", None)
    data.setdefault("sessions", {})
    return data


def save(path: Path, record: dict) -> None:
    """Replace the file whole: a temp file in the same directory, then rename."""
    fd, tmp = tempfile.mkstemp(prefix=".coordination-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def lanes_for(record: dict, session_id: str) -> list[tuple[str, dict]]:
    """(worktree path, row) for each OPEN lane this session holds."""
    return [(p, r) for p, r in record.get("sessions", {}).items()
            if isinstance(r, dict) and r.get("session_id") == session_id and r.get("state") != "closed"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _refuse_unless_coordinator(record: dict, caller: str, claiming: bool) -> str | None:
    """None when the write may go ahead, else the refusal (it names the holder)."""
    coord = record.get("coordinator")
    if coord is None:
        return None if claiming else ("no coordinator is recorded, so there is nobody to write: run "
                                      "`coordination.py claim` first (a lone session is its own coordinator)")
    if coord.get("session_id") == caller:
        return None
    holder = coord.get("name") or coord.get("session_id")
    return (f"refused: only the coordinator writes the coordination record, and that is `{holder}` "
            f"(session {coord.get('session_id')}). Ask it to record this, or have it release the role")


def claim(record: dict, caller: str, name: str | None) -> str | None:
    err = _refuse_unless_coordinator(record, caller, claiming=True)
    if err:
        return err
    coord = record.get("coordinator") or {"since": _now()}
    coord["session_id"] = caller
    if name:
        coord["name"] = name
    record["coordinator"] = coord
    return None


def assign(record: dict, caller: str, path: str, branch: str, issue: int | None, owner: str | None,
           name: str | None = None) -> str | None:
    err = _refuse_unless_coordinator(record, caller, claiming=False)
    if err:
        return err
    row = record["sessions"].get(path)
    row = row if isinstance(row, dict) else {}
    row.update({"session_id": owner or caller, "branch": branch, "state": "working", "updated": _now()})
    if issue is not None:
        row["issue"] = issue
    if name:
        row["name"] = name       # an attribute: a renamed session updates ITS row, never adds a second
    record["sessions"][path] = row
    return None


def close(record: dict, caller: str, path: str) -> str | None:
    err = _refuse_unless_coordinator(record, caller, claiming=False)
    if err:
        return err
    row = record["sessions"].get(path)
    if not isinstance(row, dict):
        return f"refused: no lane is recorded for {path}"
    row.update({"state": "closed", "updated": _now()})
    return None


def set_workspace(record: dict, caller: str, coordinator_name: str, siblings: list[dict]) -> str | None:
    """The `workspace` block: the coordinator's identity plus the sibling repositories it coordinates
    ([{name, path, remote}]). It is only a pointer: a guard reads ITS OWN repository's record."""
    err = _refuse_unless_coordinator(record, caller, claiming=False)
    if err:
        return err
    block = record.get("workspace")
    block = block if isinstance(block, dict) else {}
    block["coordinator"] = {"session_id": caller, "name": coordinator_name}
    block["repos"] = siblings
    record["workspace"] = block
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("lanes", "claim", "assign", "close", "workspace"):
        p = sub.add_parser(name)
        p.add_argument("--session-id", required=True)
        p.add_argument("--cwd", default=".")
        if name in ("claim", "assign"):
            p.add_argument("--name")
        if name == "workspace":
            p.add_argument("--coordinator-name", required=True)
            p.add_argument("--sibling", nargs=3, action="append", metavar=("NAME", "PATH", "REMOTE"), default=[])
        if name in ("assign", "close"):
            p.add_argument("--path", required=True)
        if name == "assign":
            p.add_argument("--branch", required=True)
            p.add_argument("--issue", type=int)
            p.add_argument("--owner")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_usage(sys.stderr)
        return 3
    rp = record_path(args.cwd)
    if rp is None:
        print("not inside a git repository: no coordination record", file=sys.stderr)
        return 3
    try:
        record = load(rp)
    except RecordError as e:
        print(f"could not read the coordination record: {e}", file=sys.stderr)
        return 3
    if args.cmd == "lanes":
        for path, row in lanes_for(record, args.session_id):
            print(f"{path}\t{row.get('branch', '')}\t{row.get('issue', '')}")
        return 0
    if args.cmd == "claim":
        err = claim(record, args.session_id, args.name)
    elif args.cmd == "assign":
        err = assign(record, args.session_id, os.path.abspath(args.path), args.branch, args.issue, args.owner, args.name)
    elif args.cmd == "workspace":
        err = set_workspace(record, args.session_id, args.coordinator_name,
                            [{"name": n, "path": pth, "remote": r} for n, pth, r in args.sibling])
    else:
        err = close(record, args.session_id, os.path.abspath(args.path))
    if err:
        print(err, file=sys.stderr)
        return 2
    save(rp, record)
    return 0


def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def check(label: str, ok: bool, detail: str = "") -> None:
        ran[0] += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        rp = record_path(repo)
        check("the record lives in the common git dir", rp is not None and rp.parent.name == ".git", str(rp))
        # Every worktree of a clone must see the SAME record, or a lane assigned from one is invisible
        # from another. A plain clone cannot tell --git-dir from --git-common-dir; a linked worktree can.
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"],
                       cwd=repo, check=True, capture_output=True)
        linked = Path(td) / "linked"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "side", str(linked)], cwd=repo, check=True,
                       capture_output=True)
        check("a linked worktree resolves the SAME record file as the main checkout",
              record_path(linked) == rp, f"{record_path(linked)} vs {rp}")
        rec = load(rp)
        check("no file reads as an empty record, not an error", rec["sessions"] == {} and rec["coordinator"] is None)

        err = assign(rec, "S1", "/w/a", "feature/a", 7, None)
        check("assign with no coordinator recorded is refused (it must claim first)", err and "claim" in err, str(err))
        check("a lone session claims the role", claim(rec, "S1", "solo") is None and rec["coordinator"]["session_id"] == "S1")
        check("the coordinator records a lane", assign(rec, "S1", "/w/a", "feature/a", 7, None) is None)
        err = assign(rec, "S2", "/w/b", "feature/b", None, None)
        check("a NON-coordinator write is refused and names the holder", bool(err) and "solo" in err and "S1" in err, str(err))
        check("...and recorded nothing", "/w/b" not in rec["sessions"])
        err = claim(rec, "S2", "usurper")
        check("a second claim while a coordinator is recorded is refused, naming the holder",
              bool(err) and "solo" in err and rec["coordinator"]["session_id"] == "S1", str(err))
        check("the coordinator may assign a lane to ANOTHER session",
              assign(rec, "S1", "/w/b", "feature/b", 8, "S2") is None and rec["sessions"]["/w/b"]["session_id"] == "S2")

        # Unknown keys survive a write: #1585 adds a workspace block and per-row fields with no migration.
        rec["workspace"] = {"coordinator": "x", "repos": [{"name": "sibling"}]}
        rec["sessions"]["/w/a"]["name"] = "claude-skills-9"
        rec["x_future"] = [1, 2]
        save(rp, rec)
        again = load(rp)
        assign(again, "S1", "/w/a", "feature/a", 7, None)
        save(rp, again)
        final = load(rp)
        check("unknown top-level keys survive a write", final.get("workspace", {}).get("repos") == [{"name": "sibling"}]
              and final.get("x_future") == [1, 2], str(sorted(final)))
        check("unknown row fields survive a write", final["sessions"]["/w/a"].get("name") == "claude-skills-9")

        check("a session sees only ITS open lanes", [p for p, _ in lanes_for(final, "S2")] == ["/w/b"]
              and [p for p, _ in lanes_for(final, "S1")] == ["/w/a"])
        check("a new process reading the same file finds the same lane (restart)",
              subprocess.run([sys.executable, __file__, "lanes", "--session-id", "S2", "--cwd", str(repo)],
                             capture_output=True, text=True).stdout.split("\t")[0] == "/w/b")
        check("closing a lane removes it from the session's open lanes",
              close(final, "S1", "/w/b") is None and lanes_for(final, "S2") == [])
        check("a non-coordinator cannot close a lane", bool(close(final, "S2", "/w/a")))
        check("closing a lane nobody recorded is refused", bool(close(final, "S1", "/w/zzz")))

        # The write is a rename of a temp file: nothing is left behind, and the CLI refuses the same way.
        check("no temp file is left after a write", [p.name for p in rp.parent.glob(".coordination-*")] == [])
        done = subprocess.run([sys.executable, __file__, "assign", "--session-id", "S2", "--path", "/w/c",
                               "--branch", "feature/c", "--cwd", str(repo)], capture_output=True, text=True)
        check("the CLI refuses a non-coordinator write with exit 2, naming the holder",
              done.returncode == 2 and "solo" in done.stderr, f"{done.returncode} {done.stderr!r}")

        rp.write_text("{not json")
        try:
            load(rp)
            check("a corrupt record is an ERROR, not an empty record", False, "load returned")
        except RecordError:
            pass
        done = subprocess.run([sys.executable, __file__, "lanes", "--session-id", "S1", "--cwd", str(repo)],
                              capture_output=True, text=True)
        check("the CLI exits 3 on a corrupt record", done.returncode == 3, str(done.returncode))

        # A restart gives the session a new NAME. The row is keyed by the worktree path, so the same row is
        # rewritten and no second one appears.
        rec2 = {"version": VERSION, "coordinator": None, "sessions": {}}
        claim(rec2, "S1", "solo")
        assign(rec2, "S1", "/w/a", "feature/a", 7, None, "claude-skills-old")
        assign(rec2, "S1", "/w/a", "feature/a", 7, None, "claude-skills-new")
        check("a restart with a new name rewrites the SAME row", list(rec2["sessions"]) == ["/w/a"]
              and rec2["sessions"]["/w/a"]["name"] == "claude-skills-new", str(rec2["sessions"]))
        assign(rec2, "S1", "/w/b", "feature/b", 8, "S2", "claude-skills-new")
        check("two worktrees never share a row (the same name on two paths is two rows)",
              sorted(rec2["sessions"]) == ["/w/a", "/w/b"])

        # The workspace block: written only by the coordinator, and a write keeps what it does not know.
        rec2["workspace"] = {"note": "keep me"}
        check("a non-coordinator cannot set the workspace block",
              bool(set_workspace(rec2, "S2", "x", [])) and rec2["workspace"] == {"note": "keep me"})
        sib = [{"name": "retask", "path": "/r", "remote": "git@x:r.git"}]
        check("the coordinator sets the workspace block", set_workspace(rec2, "S1", "solo", sib) is None
              and rec2["workspace"]["repos"] == sib and rec2["workspace"]["coordinator"]["name"] == "solo")
        check("...and a workspace write keeps its other keys", rec2["workspace"].get("note") == "keep me")

        # Each repository keeps its OWN record: a sibling clone has a different common git dir.
        other = Path(td) / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=other, check=True)
        rp.unlink()     # the corrupt file from the check above
        subprocess.run([sys.executable, __file__, "claim", "--session-id", "S1", "--name", "solo", "--cwd", str(repo)])
        subprocess.run([sys.executable, __file__, "assign", "--session-id", "S1", "--path", "/w/a", "--branch",
                        "feature/a", "--cwd", str(repo)])
        other_rp = record_path(other)
        check("two repositories have two different record files", other_rp != record_path(repo), str(other_rp))
        check("a lane recorded in one repository is invisible in the other",
              lanes_for(load(record_path(repo)), "S1") != [] and not other_rp.exists())
        out = subprocess.run([sys.executable, __file__, "lanes", "--session-id", "S1", "--cwd", str(other)],
                             capture_output=True, text=True)
        check("`lanes` in the other repository lists nothing for that session", out.returncode == 0 and out.stdout == "",
              repr(out.stdout))
        again = subprocess.run([sys.executable, __file__, "claim", "--session-id", "S2", "--cwd", str(repo)],
                               capture_output=True, text=True)
        check("the CLI refuses a second claim with exit 2, naming the holder",
              again.returncode == 2 and "solo" in again.stderr, f"{again.returncode} {again.stderr!r}")

        outside = Path(td) / "not-a-repo"
        outside.mkdir()
        check("outside a git repository there is no record", record_path(outside) is None)

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"coordination selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
