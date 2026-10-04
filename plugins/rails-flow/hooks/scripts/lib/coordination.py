#!/usr/bin/env python3
"""The coordination record: which session holds which worktree lane (#1581, #1585).

One record per repository, `$(git rev-parse --git-common-dir)/coordination.json`, so every worktree of
a clone sees the same file and a sibling repository keeps its own. It is keyed by WORKTREE PATH, not
by session name: names rotate at every restart, a path does not. `session_id` and `name` are
attributes of a row.

THE COORDINATOR IS THE ONLY WRITER (the owner's direction on #1585). Sessions' hooks only READ the
record; the write commands refuse a caller whose session id is not `coordinator.session_id`, unless
no coordinator is recorded and the caller is claiming the role. The file is replaced whole (a
temp file in the same directory, then rename), so a reader never sees half of it, and every read-modify-
write holds an exclusive `fcntl.flock` from read to rename: "one writer" is a role, and one coordinator
still runs commands in parallel (the #1590 review measured lost rows and several winning claims without it).
A lock that cannot be had within the timeout is exit 3, never a write without it. A lone session is its own coordinator: it claims the role and records its own lane.

UNKNOWN KEYS SURVIVE. The record carries a `workspace` block and per-row fields that other features
add (#1585); every write loads the whole record and puts back what it does not understand, so adding
a field needs no migration.

    python3 coordination.py lanes   --session-id ID [--cwd DIR]
    python3 coordination.py claim   --session-id ID [--name N] [--cwd DIR]
    python3 coordination.py assign  --session-id ID --path P --branch B [--issue N] [--owner ID] [--name N] [--cwd DIR]
    python3 coordination.py close   --session-id ID --path P [--cwd DIR]
    python3 coordination.py workspace --session-id ID --coordinator-name N [--sibling NAME PATH REMOTE]... [--cwd DIR]
    python3 coordination.py pointer [--session-id ID | --stdin] [--cwd DIR]   # SessionStart: one line, or nothing
    python3 coordination.py --selftest

The caller's identity is the `--session-id` it passes, so this protects against ACCIDENT (a session writing
when it is not the coordinator), not against impersonation: anything that can pass the coordinator's id is
accepted.

Exit: 0 done, 2 refused (the message names the coordinator), 3 could not read or lock the record.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
NAME = "coordination.json"
LOCK_NAME = "coordination.lock"
# How long a command waits for another writer. Past it the command exits 3 ("could not lock"), never
# proceeds unlocked: a record written without the lock is the lost update the lock exists to prevent.
def _env_float(name: str, default: float) -> float:
    """A tuning value from the environment; a junk one is ignored, never a traceback."""
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


LOCK_TIMEOUT = _env_float("COORDINATION_LOCK_TIMEOUT", 10)


class RecordError(Exception):
    """The record exists but cannot be read: a corrupt file is NOT an empty one."""


class LockError(Exception):
    """Another writer held the lock past the timeout."""


@contextlib.contextmanager
def locked(record_file: Path):
    """Hold an exclusive lock from READ to RENAME. "One writer" is a role, not a process: a coordinator
    runs commands in parallel, and six sessions can claim an empty record at the same instant, so each
    read-modify-write is serialised. `fcntl.flock` is the Python module, not the flock(1) binary that
    macOS lacks. Closing the descriptor releases it, so a crashed writer cannot leave the record locked."""
    lock = record_file.with_name(LOCK_NAME)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)    # owner-only (CodeQL py/overly-permissive-file, #1590)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockError(f"{lock}: could not lock within {LOCK_TIMEOUT:g}s")
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)


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
    if (not isinstance(data, dict) or not isinstance(data.get("sessions", {}), dict)
            or not (data.get("coordinator") is None or isinstance(data["coordinator"], dict))):
        raise RecordError(f"{path}: not a coordination record (sessions must be an object, coordinator an object or null)")
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
    if not coord or not coord.get("session_id"):      # none recorded, or an object that names nobody
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


def pointer_line(record: dict, session_id: str, worktree: str) -> str:
    """The one line a session sees at SessionStart, or "". Silent unless a coordinator is recorded AND this session
    holds no open lane: a session that already has a lane, a repository nobody coordinates, and a payload with no
    session id all print nothing, so the hook adds no bytes to the many sessions it does not concern. The session
    cannot write the record (only the coordinator does), so the line tells it to ASK: send the coordinator its
    current name and this worktree, and the coordinator runs `checkin`."""
    coord = record.get("coordinator")
    if not session_id or not isinstance(coord, dict) or not coord.get("session_id"):
        return ""
    if lanes_for(record, session_id):
        return ""
    holder = coord.get("name") or "the coordinator"
    return f"- coordination: {holder} coordinates this repository. Tell it your current name and this worktree ({worktree})."


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
    pp = sub.add_parser("pointer")
    pp.add_argument("--session-id", default="")
    pp.add_argument("--stdin", action="store_true", help="read the session id from the hook payload on stdin")
    pp.add_argument("--cwd", default=".")
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
    if args.cmd == "pointer":      # an ADVISORY: every failure is silence and exit 0, never a blocked session start
        try:
            sid = args.session_id
            if args.stdin and not sid:
                payload = json.loads(sys.stdin.read() or "{}")
                sid = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
            rp = record_path(args.cwd)
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=args.cwd, capture_output=True, text=True, timeout=5)
            if rp is not None and top.returncode == 0:
                line = pointer_line(load(rp), sid, os.path.realpath(top.stdout.strip()))
                if line:
                    print(line)
        except Exception:      # noqa: BLE001 -- fail open
            pass
        return 0
    rp = record_path(args.cwd)
    if rp is None:
        print("not inside a git repository: no coordination record", file=sys.stderr)
        return 3
    if args.cmd == "lanes":        # a read: the record is replaced whole, so no lock is needed to read it
        try:
            record = load(rp)
        except RecordError as e:
            print(f"could not read the coordination record: {e}", file=sys.stderr)
            return 3
        for path, row in lanes_for(record, args.session_id):
            print(f"{path}\t{row.get('branch', '')}\t{row.get('issue', '')}")
        return 0
    try:
        with locked(rp):
            try:
                record = load(rp)
            except RecordError as e:
                print(f"could not read the coordination record: {e}", file=sys.stderr)
                return 3
            if args.cmd == "claim":
                err = claim(record, args.session_id, args.name)
            elif args.cmd == "assign":
                # realpath, not abspath: a symlinked path and its target are ONE worktree, and `git rev-parse
                # --show-toplevel` (what the guard compares against) already resolves symlinks.
                err = assign(record, args.session_id, os.path.realpath(args.path), args.branch, args.issue, args.owner,
                             args.name)
            elif args.cmd == "workspace":
                err = set_workspace(record, args.session_id, args.coordinator_name,
                                    [{"name": n, "path": pth, "remote": r} for n, pth, r in args.sibling])
            else:
                err = close(record, args.session_id, os.path.realpath(args.path))
            if err:
                print(err, file=sys.stderr)
                return 2
            hold = _env_float("COORDINATION_TEST_HOLD", 0)
            if hold:
                time.sleep(hold)    # a TEST SEAM: widens the read-to-write window so the race fixtures are deterministic
            save(rp, record)
            return 0
    except LockError as e:
        print(f"could not write the coordination record: {e}", file=sys.stderr)
        return 3


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

        # The CLI paths themselves, not only the functions behind them.
        ws = subprocess.run([sys.executable, __file__, "workspace", "--session-id", "S1", "--coordinator-name", "solo",
                             "--sibling", "retask", "/r", "git@x:r.git", "--cwd", str(repo)], capture_output=True, text=True)
        check("the CLI records the workspace siblings as {name, path, remote}", ws.returncode == 0 and
              load(record_path(repo)).get("workspace", {}).get("repos") == [{"name": "retask", "path": "/r", "remote": "git@x:r.git"}],
              f"{ws.returncode} {ws.stderr!r}")
        cl = subprocess.run([sys.executable, __file__, "close", "--session-id", "S1", "--path", "/w/a", "--cwd", str(repo)],
                            capture_output=True, text=True)
        check("the CLI closes a lane, so it leaves the session's open lanes",
              cl.returncode == 0 and lanes_for(load(record_path(repo)), "S1") == [], f"{cl.returncode} {cl.stderr!r}")

        # R1 (#1590 review): "one writer" does not mean one PROCESS. Parallel commands race a read-modify-write.
        # The test seam holds each command between its read and its write, so the race is certain without a lock.
        race = Path(td) / "race"
        race.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=race, check=True)
        slow = dict(os.environ, COORDINATION_TEST_HOLD="0.3")

        def parallel(argvs: list[list[str]]) -> list[int]:
            procs = [subprocess.Popen([sys.executable, __file__, *a], env=slow, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL) for a in argvs]
            return [p.wait() for p in procs]

        codes = parallel([["claim", "--session-id", f"C{i}", "--name", f"n{i}", "--cwd", str(race)] for i in range(6)])
        check("six parallel claims on an empty record: exactly one wins and five are refused",
              codes.count(0) == 1 and codes.count(2) == 5, str(codes))
        won = load(record_path(race))["coordinator"]["session_id"] if codes.count(0) == 1 else None
        check("...and the record names the session that was told it won", won == f"C{codes.index(0)}" if won else False,
              f"{won} {codes}")
        codes = parallel([["assign", "--session-id", won or "C0", "--path", f"/p/{i}", "--branch", f"b{i}",
                           "--cwd", str(race)] for i in range(6)])
        rows = load(record_path(race))["sessions"]
        check("six parallel assigns by the coordinator: all six exit 0 and all six rows survive",
              codes == [0] * 6 and len(rows) == 6, f"{codes} rows={len(rows)}")

        # R2 (#1590 review): a record of the wrong shape is a RECORD error (exit 3), never a traceback.
        for body in ('{"coordinator": "x", "sessions": {}}', '{"coordinator": [], "sessions": {}}',
                     '{"coordinator": null, "sessions": []}', '[]'):
            rp.write_text(body)
            bad = subprocess.run([sys.executable, __file__, "claim", "--session-id", "S1", "--cwd", str(repo)],
                                 capture_output=True, text=True)
            check(f"a malformed record {body} exits 3, not a traceback", bad.returncode == 3 and "Traceback" not in bad.stderr,
                  f"{bad.returncode} {bad.stderr[-120:]!r}")
        rp.unlink()

        # R3 (#1590 review): a symlinked path and its target are ONE worktree, so one row.
        sym = Path(td) / "sym"
        sym.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=sym, check=True)
        real_wt, link_wt = Path(td) / "real-wt", Path(td) / "link-wt"
        real_wt.mkdir()
        link_wt.symlink_to(real_wt)
        subprocess.run([sys.executable, __file__, "claim", "--session-id", "S1", "--cwd", str(sym)])
        for given in (link_wt, real_wt):
            subprocess.run([sys.executable, __file__, "assign", "--session-id", "S1", "--path", str(given),
                            "--branch", "b", "--cwd", str(sym)])
        srows = load(record_path(sym))["sessions"]
        check("a symlinked worktree path and its target are ONE row, keyed by the real path",
              list(srows) == [os.path.realpath(real_wt)], str(list(srows)))

        # A command that cannot get the lock is exit 3 and writes nothing; it never proceeds unlocked.
        srp = record_path(sym)
        before = srp.read_bytes()
        holder = subprocess.Popen([sys.executable, "-c", "import fcntl,os,sys,time\nfd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR)\n"
                                   "fcntl.flock(fd,fcntl.LOCK_EX)\nprint('held',flush=True)\ntime.sleep(10)",
                                   str(srp.with_name(LOCK_NAME))], stdout=subprocess.PIPE, text=True)
        try:
            holder.stdout.readline()
            busy = subprocess.run([sys.executable, __file__, "claim", "--session-id", "S2", "--cwd", str(sym)],
                                  env=dict(os.environ, COORDINATION_LOCK_TIMEOUT="0.3"), capture_output=True, text=True)
        finally:
            holder.kill()
            holder.wait()
        check("a command that cannot get the lock exits 3, says so, and writes nothing",
              busy.returncode == 3 and "could not" in busy.stderr and srp.read_bytes() == before,
              f"{busy.returncode} {busy.stderr!r}")

        # R4 (#1590 review, CodeQL py/overly-permissive-file): the lock file is not world-readable.
        import stat
        lockf = record_path(sym).with_name(LOCK_NAME)
        check("the lock file is created owner-only (0600)", lockf.exists() and stat.S_IMODE(lockf.stat().st_mode) == 0o600,
              oct(stat.S_IMODE(lockf.stat().st_mode)) if lockf.exists() else "no lock file")
        check("the record file is owner-only too (0600)",
              stat.S_IMODE(record_path(sym).stat().st_mode) == 0o600, oct(stat.S_IMODE(record_path(sym).stat().st_mode)))
        # A junk tuning value is ignored, not a traceback, and does not break a read.
        junk = Path(td) / "junk"
        junk.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=junk, check=True)
        for var in ("COORDINATION_LOCK_TIMEOUT", "COORDINATION_TEST_HOLD"):
            done = subprocess.run([sys.executable, __file__, "claim", "--session-id", "J1", "--cwd", str(junk)],
                                  env=dict(os.environ, **{var: "soon"}), capture_output=True, text=True)
            check(f"a junk {var} is ignored: the claim succeeds with no traceback",
                  done.returncode == 0 and "Traceback" not in done.stderr, f"{done.returncode} {done.stderr[-120:]!r}")
            record_path(junk).unlink(missing_ok=True)
        done = subprocess.run([sys.executable, __file__, "lanes", "--session-id", "J1", "--cwd", str(junk)],
                              env=dict(os.environ, COORDINATION_LOCK_TIMEOUT="soon"), capture_output=True, text=True)
        check("a junk COORDINATION_LOCK_TIMEOUT does not break a read", done.returncode == 0 and "Traceback" not in done.stderr,
              f"{done.returncode} {done.stderr[-120:]!r}")
        # An empty coordinator object names nobody, so it must not make the record unclaimable.
        record_path(junk).write_text('{"coordinator": {}, "sessions": {}}')
        done = subprocess.run([sys.executable, __file__, "claim", "--session-id", "J2", "--cwd", str(junk)],
                              capture_output=True, text=True)
        check("a coordinator object with no session_id counts as no coordinator, so a claim succeeds",
              done.returncode == 0 and load(record_path(junk))["coordinator"]["session_id"] == "J2",
              f"{done.returncode} {done.stderr!r}")

        # #1585 part 2b: the SessionStart pointer. One line, and only when it concerns the session.
        pr = {"version": VERSION, "coordinator": None, "sessions": {}}
        check("no coordinator recorded: the pointer is silent", pointer_line(pr, "S1", "/w/a") == "")
        claim(pr, "C1", "claude-skills-5a")
        line = pointer_line(pr, "S1", "/w/a")
        check("a coordinator is recorded and this session holds no lane: ONE line naming the coordinator and the worktree",
              line.count("\n") == 0 and "claude-skills-5a" in line and "/w/a" in line and "current name" in line, line)
        assign(pr, "C1", "/w/a", "feature/a", 1, "S1")
        check("this session holds an open lane: silent", pointer_line(pr, "S1", "/w/a") == "")
        check("a different session still gets the line", pointer_line(pr, "S2", "/w/b") != "")
        close(pr, "C1", "/w/a")
        check("a CLOSED lane is no lane: the line returns", pointer_line(pr, "S1", "/w/a") != "")
        check("no session id in the payload: silent", pointer_line(pr, "", "/w/a") == "")
        pr["coordinator"] = {"session_id": "", "name": "ghost"}
        check("a coordinator object that names nobody is no coordinator: silent", pointer_line(pr, "S1", "/w/a") == "")
        pr["coordinator"] = "not-a-dict"
        check("a coordinator of the wrong type is silent, not a traceback", pointer_line(pr, "S1", "/w/a") == "")

        # Through the CLI in a real process, as the hook runs it: payload on stdin, exit 0 whatever happens.
        pcli = Path(td) / "pcli"
        pcli.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=pcli, check=True)
        subprocess.run([sys.executable, __file__, "claim", "--session-id", "C1", "--name", "boss", "--cwd", str(pcli)], check=True)

        def run_pointer(payload: str, cwd: Path) -> "subprocess.CompletedProcess":
            return subprocess.run([sys.executable, __file__, "pointer", "--stdin", "--cwd", str(cwd)], input=payload,
                                  capture_output=True, text=True)
        got = run_pointer('{"session_id": "S7"}', pcli)
        check("the hook path prints the line for a session with no lane, and exits 0",
              got.returncode == 0 and "boss" in got.stdout and os.path.realpath(str(pcli)) in got.stdout, f"{got.returncode} {got.stdout!r}")
        subprocess.run([sys.executable, __file__, "assign", "--session-id", "C1", "--path", str(pcli), "--branch", "b",
                        "--owner", "S7", "--cwd", str(pcli)], check=True)
        got = run_pointer('{"session_id": "S7"}', pcli)
        check("...and prints nothing once the coordinator has recorded that session's lane", got.returncode == 0 and got.stdout == "", repr(got.stdout))
        for label, payload, where in (("a payload that is not JSON", "{not json", pcli), ("an empty payload", "", pcli),
                                      ("a payload with no session_id", "{}", pcli), ("a payload that is a list", "[1]", pcli),
                                      ("a directory that is no repository", '{"session_id": "S7"}', Path(td))):
            got = run_pointer(payload, where)
            check(f"{label}: silent, exit 0, no traceback", got.returncode == 0 and got.stdout == "" and "Traceback" not in got.stderr,
                  f"{got.returncode} {got.stdout!r} {got.stderr[-80:]!r}")
        record_path(pcli).write_text("{corrupt")
        got = run_pointer('{"session_id": "S8"}', pcli)
        check("a corrupt record: silent, exit 0 (an advisory never blocks a session start)",
              got.returncode == 0 and got.stdout == "" and "Traceback" not in got.stderr, f"{got.returncode} {got.stderr[-80:]!r}")

        outside = Path(td) / "not-a-repo"
        outside.mkdir()
        check("outside a git repository there is no record", record_path(outside) is None)

    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"coordination selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
