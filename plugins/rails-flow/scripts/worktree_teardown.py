#!/usr/bin/env python3
"""End a finished worktree: stop ITS servers, drop ITS databases, remove it, and prove nothing is left (#2058).

THE LEAK. `git worktree remove <path>` ends the checkout and nothing else. Every worktree that ran a suite or a server
leaves its development, test and parallel-shard databases behind (113 on one machine, 2026-10-14), and sometimes a
running server. Owner rule: a teardown drops its databases and stops its processes; there is never a leftover database.

WHOSE IT IS, DECIDED BY CONFIGURATION AND BY DIRECTORY, NEVER BY A PATTERN.
  * Databases: the names the worktree's OWN `config/database.yml` resolves to (read by its `bin/rails runner` before
    anything is removed), plus those names followed by `_p<digits>` EXACTLY (the parallel-test shards). Not a `LIKE`, not
    a prefix: another worktree's `app_test_wt2x` is not `app_test_wt2`'s shard. A name the MAIN checkout also resolves to
    is shared, so it is never dropped. Dropped with `dropdb --if-exists --force` (PostgreSQL 13 or later; `--force` ends only
    connections the running role may terminate with `pg_terminate_backend`, and the drop fails while a prepared transaction or an
    active logical replication slot holds the database: a failed drop is reported and the worktree is left in place). PostgreSQL
    only; another adapter has nothing to drop here.
  * Processes: the PIDs written in the worktree's own `tmp/pids/*.pid`, each accepted only while the process's working
    directory is inside the worktree. Never `pkill`, never a name match: a puma retitles itself, and another session's
    server must not be hit.
  * Removal: `git worktree remove`, never `--force`. A dirty tree, an unmerged head, a locked worktree and the main
    checkout are REFUSED before anything is stopped or dropped.

FAILS CLOSED. If the databases cannot be read or listed, nothing is removed. It ends by checking, not assuming: the
databases are gone, the PIDs are gone, the path is gone.

    python3 worktree_teardown.py <worktree> [--dry-run] [--assume-merged] [--pg-bin DIR]
    python3 worktree_teardown.py --check-wording [--root DIR]     # every place that tells an agent how to end a worktree names this script
    python3 worktree_teardown.py --selftest

`--assume-merged` is for a squash-merged branch, whose head is not an ancestor of the integration branch: confirm the PR
merged (`gh pr view`), then pass it. The tree must still be clean. `--pg-bin` (or `PG_BIN`) names the directory holding
`psql` and `dropdb` when they are not on PATH.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

INTEGRATION = ("origin/dev", "dev", "origin/main", "main", "origin/master", "master")     # as hooks/scripts/lib/worktree_guard.py
GIT_REMOVE = ("worktree", "remove")                                                      # never `--force`, never `-f`
DROP_FLAGS = ("--if-exists", "--force")
SHARD = r"_p\d+"
RUNNER = ("ActiveRecord::Base.configurations.configs_for(env_name: 'development').each{|c| puts [c.adapter, c.database].join(\"\\t\")}; "
          "ActiveRecord::Base.configurations.configs_for(env_name: 'test').each{|c| puts [c.adapter, c.database].join(\"\\t\")}")
STOP_WAIT = 5.0


def run(cmd, cwd=None, env=None, timeout=60) -> tuple[int, str]:
    """(exit code, output); never raises: a missing program is 127, a hang is 124."""
    try:
        p = subprocess.run(list(cmd), cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, TypeError) as e:                       # a missing program, or a tool that was never found (None)
        return 127, str(e)
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def git(cwd, *args) -> tuple[int, str]:
    return run(["git", *args], cwd=cwd)


def worktrees(cwd) -> list[dict]:
    rc, out = git(cwd, "worktree", "list", "--porcelain")
    rows: list[dict] = []
    for block in out.strip().split("\n\n") if rc == 0 else []:
        row: dict = {}
        for line in block.splitlines():
            key, _, val = line.partition(" ")
            row[key] = val
        if "worktree" in row:
            rows.append({"path": os.path.realpath(row["worktree"]), "head": row.get("HEAD", ""), "locked": "locked" in row})
    return rows


def integration_ref(cwd) -> str | None:
    for ref in INTEGRATION:
        if git(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")[0] == 0:
            return ref
    return None


def refusal(path: str, assume_merged: bool) -> str | None:
    """Why this worktree may not be ended, or None. Nothing has been touched when this answers."""
    rows = worktrees(path)
    if not rows:
        return f"{path} is not a worktree of a git repository"
    row = next((r for r in rows if r["path"] == path), None)
    if row is None:
        return f"{path} is not a worktree of this repository"
    if row is rows[0]:
        return "that is the main checkout, not a worktree to end"
    if row["locked"]:
        return "the worktree is locked (`git worktree unlock` first, deliberately)"
    rc, status = git(path, "status", "--porcelain", "--ignore-submodules=dirty")
    if rc != 0 or status.strip():
        return "uncommitted work (commit or push it first): " + (status.strip().splitlines() or ["git status failed"])[0]
    if not assume_merged:
        integ = integration_ref(path)
        if integ is None or git(path, "merge-base", "--is-ancestor", row["head"], integ)[0] != 0:
            return f"its head is not merged into {integ or 'any integration branch'} (a squash merge: confirm the PR merged, then --assume-merged)"
    return None


def database_names(path: str) -> list[str] | None:
    """The PostgreSQL databases this checkout's own config resolves to; [] when it has none; None when it cannot be read."""
    rails = Path(path) / "bin" / "rails"
    if not rails.exists():
        return []
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}      # the file's config decides, not an override
    rc, out = run([str(rails), "runner", RUNNER], cwd=path, env=env, timeout=180)
    if rc != 0:
        return None
    names = []
    for line in out.splitlines():
        adapter, _, database = line.partition("\t")
        if adapter.strip() == "postgresql" and database.strip() and database.strip() not in names:
            names.append(database.strip())
    return names


def pg_tool(pg_bin: str | None, name: str) -> str | None:
    if pg_bin:
        p = Path(pg_bin) / name
        return str(p) if p.exists() else None
    return shutil.which(name)


def existing_databases(psql: str) -> list[str] | None:
    rc, out = run([psql, "-At", "-d", "postgres", "-c", "select datname from pg_database"])
    return [line.strip() for line in out.splitlines() if line.strip()] if rc == 0 else None


def owned(existing: list[str], names: list[str], shared: set[str]) -> list[str]:
    """Existing databases that are exactly one of NAMES or NAME + `_p<digits>`, less the names the main checkout shares."""
    keep = [n for n in names if n not in shared]
    return [d for d in existing if any(d == n or re.fullmatch(re.escape(n) + SHARD, d) for n in keep)]


def alive(pid: int) -> bool:
    rc, out = run(["ps", "-o", "stat=", "-p", str(pid)])
    return rc == 0 and bool(out.strip()) and not out.strip().startswith("Z")


def cwd_of(pid: int) -> str | None:
    rc, out = run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    if rc == 0:
        for line in out.splitlines():
            if line.startswith("n"):
                return os.path.realpath(line[1:])
    try:
        return os.path.realpath(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return None


def own_pids(path: str) -> list[int]:
    """PIDs in the worktree's own tmp/pids/*.pid that are alive and whose working directory is inside the worktree."""
    found = []
    for pidfile in sorted((Path(path) / "tmp" / "pids").glob("*.pid")):
        try:
            pid = int(pidfile.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            continue
        if pid <= 1 or pid == os.getpid() or not alive(pid):
            continue
        where = cwd_of(pid)
        if where is not None and (where == path or where.startswith(path + os.sep)) and pid not in found:
            found.append(pid)
    return found


def stop(pid: int) -> None:
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + STOP_WAIT
    while time.time() < deadline and alive(pid):
        time.sleep(0.1)
    if alive(pid):
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.2)


def teardown(path: str, dry_run=False, assume_merged=False, pg_bin: str | None = None, say=print) -> int:
    path = os.path.realpath(path)
    why = refusal(path, assume_merged)
    if why:
        say(f"worktree_teardown: REFUSED, {why}")
        return 1
    main = worktrees(path)[0]["path"]
    names = database_names(path)
    shared = database_names(main)
    if names is None or shared is None:
        say("worktree_teardown: FAILED CLOSED, could not read the databases from config/database.yml (`bin/rails runner` failed); nothing was changed")
        return 1
    existing: list[str] = []
    if names:
        psql, dropdb = pg_tool(pg_bin or os.environ.get("PG_BIN"), "psql"), pg_tool(pg_bin or os.environ.get("PG_BIN"), "dropdb")
        listed = existing_databases(psql) if psql and dropdb else None
        if listed is None:
            say("worktree_teardown: FAILED CLOSED, cannot reach PostgreSQL (psql/dropdb missing or the server is down; see --pg-bin); nothing was changed")
            return 1
        existing = listed
    doomed = owned(existing, names, set(shared))
    skipped = [n for n in names if n in shared]
    pids = own_pids(path)
    say(f"worktree_teardown: {path}")
    say(f"  stop {len(pids)} process(es): {pids}")
    say(f"  drop {len(doomed)} database(s): {doomed}" + (f" (shared with the main checkout, left alone: {skipped})" if skipped else ""))
    if dry_run:
        say("  --dry-run: nothing changed")
        return 0
    for pid in pids:
        stop(pid)
    for database in doomed:
        rc, out = run([dropdb, *DROP_FLAGS, database])
        if rc != 0:
            say(f"worktree_teardown: FAILED, dropdb {database}: {out.strip()}")
            return 1
    rc, out = git(main, *GIT_REMOVE, path)
    if rc != 0:
        say(f"worktree_teardown: FAILED, git worktree remove: {out.strip()}")
        return 1
    left = []
    now = existing_databases(psql) if names else []
    left += ["databases (PostgreSQL could not be asked afterwards)"] if now is None else [f"database {d}" for d in owned(now, names, set(shared))]
    left += [f"process {p}" for p in pids if alive(p)]
    left += [f"worktree {path}"] if os.path.exists(path) or any(r["path"] == path for r in worktrees(main)) else []
    if left:
        say("worktree_teardown: LEFT BEHIND: " + ", ".join(left))
        return 1
    say("worktree_teardown: done, nothing left: no database, no process, no worktree")
    return 0


# ---------------------------------------------------------------------------------------------------------------- wording

# Where an agent is told how to end a worktree: (path from the repository root, the line that opens the instruction, how many lines it spans, the text
# that names this script there: the hook builds its path from the constant `{TEARDOWN}`). Each must name this script. `git worktree remove` alone leaves the databases behind, so a place that says only that is the defect (#2058).
WORDING_SITES = (
    ("skills/parallel-session-lane/SKILL.md", "3. **Clean up when done", 4, "worktree_teardown.py"),
    ("skills/parallel-session-lane/references/one-issue-at-a-time.md", "3. **Clean up when done", 3, "worktree_teardown.py"),
    ("plugins/rails-flow/hooks/scripts/lib/worktree_guard.py", "End each with", 2, "{TEARDOWN}"),
    ("plugins/rails-flow/scripts/wrap_round.py", "3. end each FINISHED worktree", 2, "worktree_teardown.py"),
)


def check_wording(root: str) -> list[str]:
    """Findings, one per site that does not name worktree_teardown.py (or whose opening line has gone: that is a finding too)."""
    findings = []
    for rel, opener, span, token in WORDING_SITES:
        f = Path(root) / rel
        if not f.exists():
            findings.append(f"{rel}: the file is missing")
            continue
        lines = f.read_text().splitlines()
        at = next((i for i, ln in enumerate(lines) if opener in ln), None)
        if at is None:
            findings.append(f"{rel}: the instruction opening with `{opener}` is gone; update WORDING_SITES with it")
        elif token not in " ".join(lines[at:at + span]):
            findings.append(f"{rel}:{at + 1}: tells an agent how to end a worktree without naming worktree_teardown.py")
    return findings


# ---------------------------------------------------------------------------------------------------------------- selftest

FAKE_RAILS = """#!/bin/sh
# prints what a Rails app with a checkout suffix resolves to: the main checkout has no suffix, `shared` resolves to main's names
d=$(basename "$(pwd)")
case "$d" in
  main|shared) printf 'postgresql\\tapp_dev\\npostgresql\\tapp_test\\n' ;;
  *) printf "postgresql\\tapp_dev_$d\\npostgresql\\tapp_test_$d\\nsqlite3\\tstorage/$d.sqlite3\\n" ;;
esac
"""
FAKE_PSQL = """#!/bin/sh
cat "$FAKE_PG/dbs"
"""
FAKE_DROPDB = """#!/bin/sh
echo "$@" >> "$FAKE_PG/log"
for last; do :; done
grep -vx -- "$last" "$FAKE_PG/dbs" > "$FAKE_PG/dbs.new"; mv "$FAKE_PG/dbs.new" "$FAKE_PG/dbs"
"""


def selftest() -> int:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fixture_git      # git for fixtures: bound to the temp repo it names, hermetic, starts nothing in the background (#1588)
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}{(': ' + detail) if detail else ''}")

    with tempfile.TemporaryDirectory() as raw:
        root = os.path.realpath(raw)
        main = os.path.join(root, "main")
        pgdir, binpath = os.path.join(root, "pg"), os.path.join(root, "pgbin")
        for d in (main, pgdir, binpath):
            os.makedirs(d)
        os.environ["FAKE_PG"] = pgdir

        def g(*a):       # always the main repository: fixture_git refuses a linked worktree's `.git` file (fails closed), so every commit is made here
            return fixture_git.run(main, *a).stdout

        fixture_git.init(main, "-b", "dev")
        os.makedirs(os.path.join(main, "bin"))
        Path(main, "bin", "rails").write_text(FAKE_RAILS)
        os.chmod(os.path.join(main, "bin", "rails"), 0o755)
        Path(main, ".gitignore").write_text("tmp/\n")
        Path(main, "a.txt").write_text("a\n")
        g("add", ".gitignore", "a.txt", "bin/rails")
        g("commit", "-qm", "base")
        for tool, body in (("psql", FAKE_PSQL), ("dropdb", FAKE_DROPDB)):
            Path(binpath, tool).write_text(body)
            os.chmod(os.path.join(binpath, tool), 0o755)

        def add(name: str, merged=True) -> str:
            p = os.path.join(root, name)
            if merged:
                g("worktree", "add", "-q", "-b", f"b-{name}", p)
            else:       # a branch with a commit dev does not have, made in the main repository, then checked out as a worktree
                g("checkout", "-q", "-b", f"b-{name}")
                Path(main, "new.txt").write_text("n\n")
                g("add", "new.txt")
                g("commit", "-qm", "work")
                g("checkout", "-q", "dev")
                g("worktree", "add", "-q", p, f"b-{name}")
            return os.path.realpath(p)

        def universe(*dbs: str) -> None:
            Path(pgdir, "dbs").write_text("".join(d + "\n" for d in dbs))
            Path(pgdir, "log").write_text("")

        def dropped() -> list[str]:
            return [ln.split()[-1] for ln in Path(pgdir, "log").read_text().splitlines() if ln.strip()]

        def listed(p: str) -> bool:
            return any(r["path"] == p for r in worktrees(main))

        def serve(p: str, name: str = "server") -> subprocess.Popen:
            os.makedirs(os.path.join(p, "tmp", "pids"), exist_ok=True)
            proc = subprocess.Popen(["sleep", "60"], cwd=p)
            Path(p, "tmp", "pids", f"{name}.pid").write_text(f"{proc.pid}\n")
            return proc

        quiet = lambda _m: None  # noqa: E731
        spawned: list[subprocess.Popen] = []
        try:
            # 1. the refusals touch nothing
            wd = add("dirty")
            Path(wd, "a.txt").write_text("changed\n")
            universe("app_dev_dirty", "app_test_dirty")
            srv = serve(wd)
            spawned.append(srv)
            check("a dirty worktree is refused", teardown(wd, pg_bin=binpath, say=quiet) == 1)
            check("a refused worktree keeps its databases, its process and its checkout",
                  dropped() == [] and srv.poll() is None and listed(wd))

            wu = add("unmerged", merged=False)
            universe("app_dev_unmerged")
            check("an unmerged head is refused", teardown(wu, pg_bin=binpath, say=quiet) == 1 and dropped() == [] and listed(wu))

            universe("app_dev", "app_test")
            ms = serve(main)
            spawned.append(ms)
            check("the main checkout is refused and its databases and server are left alone",
                  teardown(main, pg_bin=binpath, say=quiet) == 1 and dropped() == [] and ms.poll() is None)

            wl = add("locked")
            g("worktree", "lock", wl)
            universe("app_dev_locked")
            check("a locked worktree is refused", teardown(wl, pg_bin=binpath, say=quiet) == 1 and dropped() == [] and listed(wl))

            # 2. a merged, clean worktree ends completely, and only itself
            w2 = add("wt2")
            universe("app_dev", "app_test", "app_dev_wt2", "app_test_wt2", "app_test_wt2_p1", "app_test_wt2_p12",
                     "app_test_wt2x", "app_test_wt2_pending", "app_test_wt2_p1_x", "app_dev_wt3", "app_test_wt3_p1")
            mine = serve(w2)
            elsewhere = subprocess.Popen(["sleep", "60"], cwd=root)
            spawned += [mine, elsewhere]
            Path(w2, "tmp", "pids", "other.pid").write_text(f"{elsewhere.pid}\n")
            Path(w2, "tmp", "pids", "bad.pid").write_text("not a pid\n")
            Path(w2, "tmp", "pids", "gone.pid").write_text("999999\n")
            check("a clean merged worktree ends with status 0", teardown(w2, pg_bin=binpath, say=quiet) == 0)
            check("it drops exactly its own databases and shards, nothing that only looks like them",
                  sorted(dropped()) == ["app_dev_wt2", "app_test_wt2", "app_test_wt2_p1", "app_test_wt2_p12"], str(dropped()))
            log = Path(pgdir, "log").read_text().splitlines()
            check("every drop is `dropdb --if-exists --force`", bool(log) and all(ln.startswith("--if-exists --force ") for ln in log), str(log))
            try:
                mine.wait(timeout=10)
                stopped = True
            except subprocess.TimeoutExpired:
                stopped = False
            check("it stops its own server", stopped)
            check("it never signals a process outside the worktree, even one named in its pid file", elsewhere.poll() is None)
            check("the worktree is gone", not listed(w2) and not os.path.exists(w2))

            # 3. a database the main checkout shares is never dropped
            ws = add("shared")
            universe("app_dev", "app_test", "app_dev_shared")
            check("a worktree that resolves to the main checkout's databases still ends", teardown(ws, pg_bin=binpath, say=quiet) == 0)
            check("a database shared with the main checkout is never dropped", "app_dev" not in dropped() and "app_test" not in dropped(), str(dropped()))

            # 4. fail closed
            wf = add("closed")
            universe("app_dev_closed")
            check("an unreachable PostgreSQL fails closed and removes nothing",
                  teardown(wf, pg_bin=os.path.join(root, "nowhere"), say=quiet) == 1 and listed(wf))

            # 5. a dry run changes nothing
            wr = add("dry")
            universe("app_dev_dry")
            sd = serve(wr)
            spawned.append(sd)
            check("--dry-run changes nothing", teardown(wr, dry_run=True, pg_bin=binpath, say=quiet) == 0
                  and dropped() == [] and sd.poll() is None and listed(wr))

            # 6. a squash-merged branch needs the flag, and only the flag
            wq = add("squashed", merged=False)
            universe("app_dev_squashed")
            check("--assume-merged ends a branch whose head is not an ancestor", teardown(wq, assume_merged=True, pg_bin=binpath, say=quiet) == 0
                  and dropped() == ["app_dev_squashed"] and not listed(wq))

            # 7. the git call is never forced
            check("git worktree remove is never forced", GIT_REMOVE == ("worktree", "remove"), str(GIT_REMOVE))
        finally:
            for proc in spawned:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
    with tempfile.TemporaryDirectory() as raw:
        tree = os.path.realpath(raw)
        for rel, opener, span, token in WORDING_SITES:
            f = Path(tree, rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"intro\n{opener} with `python3 x/{token} <path>`\nmore\n")
        check("the wording check passes on a tree whose sites all name the teardown", check_wording(tree) == [], str(check_wording(tree)))
        for rel, opener, span, token in WORDING_SITES:
            f = Path(tree, rel)
            f.write_text(f"intro\n{opener} with `git worktree remove <path>`\nmore\n")
            found = check_wording(tree)
            check(f"the wording check names {rel} when it says only `git worktree remove`", len(found) == 1 and found[0].startswith(rel), str(found))
            f.write_text("intro\nunrelated\n")
            found = check_wording(tree)
            check(f"the wording check notices when the instruction in {rel} has gone", len(found) == 1 and "is gone" in found[0], str(found))
            f.write_text(f"intro\n{opener} with `python3 x/{token} <path>`\nmore\n")
        Path(tree, WORDING_SITES[0][0]).unlink()
        check("the wording check notices a missing file", any("is missing" in m for m in check_wording(tree)))
    if failures:
        print("worktree_teardown selftest FAILED:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    print("worktree_teardown selftest: all checks passed")
    return 0


def main_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="End a finished worktree: stop its servers, drop its databases, remove it, prove nothing is left.")
    ap.add_argument("worktree", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assume-merged", action="store_true")
    ap.add_argument("--pg-bin")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check-wording", action="store_true")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.check_wording:
        found = check_wording(args.root)
        for line in found:
            print(f"teardown wording: {line}")
        print(f"teardown wording: {len(WORDING_SITES)} place(s) checked, {len(found)} finding(s)")
        return 1 if found else 0
    if not args.worktree:
        ap.error("a worktree path is required")
    return teardown(args.worktree, dry_run=args.dry_run, assume_merged=args.assume_merged, pg_bin=args.pg_bin)


if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:]))
