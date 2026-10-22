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
  * Never another's: a database that the main checkout, ANY other registered worktree, or the production config resolves to is
    never dropped. A process with its working directory inside the worktree but no pid file is not guessed at: it is named and the
    teardown REFUSES, so "nothing left" is never printed while one still runs.
  * Removal: `git worktree remove`, never `--force`. A dirty tree, an unmerged head, a locked worktree and the main
    checkout are REFUSED before anything is stopped or dropped.

FAILS CLOSED. If the databases cannot be read or listed, nothing is removed. That includes ANOTHER registered worktree whose `bin/rails runner`
fails: without its names the script cannot tell which databases are shared, so one broken sibling worktree blocks every teardown until it is
fixed or removed, and the refusal names it. It ends by checking, not assuming: the
databases are gone, the PIDs are gone, the path is gone.

    python3 worktree_teardown.py <worktree> [--dry-run] [--assume-merged] [--pg-bin DIR]
    python3 worktree_teardown.py --check-wording [--root DIR]     # every place that tells an agent how to end a worktree names this script
    python3 worktree_teardown.py --selftest

`--assume-merged` is for a squash-merged branch, whose head is not an ancestor of the integration branch: confirm the PR
merged (`gh pr view`), then pass it. The tree must still be clean. `--pg-bin` (or `PG_BIN`) names the directory holding
`psql` and `dropdb` when they are not on PATH. Gitignored files in the worktree (a copied `config/master.key`, logs, QA output) go with it, silently.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
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
RUNNER = ("%w[development test production].each{|e| ActiveRecord::Base.configurations.configs_for(env_name: e).each{|c| "
          "puts [e, c.adapter, c.database].join(\"\\t\")}}")
STOP_WAIT = 5.0
# NOTHING LEFT BEHIND (#2296, owner rule 2026-10-22: "a teardown worktree should never leave a file or folder behind"). A worktree's
# artifacts (reviewer exports, baselines, logs) go in its own SCRATCH dir, which the teardown removes; the shared parent of the
# worktrees keeps only other worktrees and the declared KEEP entries. The main checkout's own parent holds other projects, so it is
# never scanned.
SCRATCH = ".rf-scratch"
KEEP = frozenset({"_logs", "_handoff", "_board", "_tools", ".DS_Store"})   # .DS_Store: macOS writes it, nobody chose to


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
            rows.append({"path": os.path.realpath(row["worktree"]), "head": row.get("HEAD", ""), "locked": "locked" in row,
                         "branch": row.get("branch", "").removeprefix("refs/heads/")})
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
    status = "\n".join(ln for ln in status.splitlines() if ln.strip() and not ln[3:].startswith(SCRATCH + "/"))   # the scratch dir goes with it
    if rc != 0 or status.strip():
        return "uncommitted work (commit or push it first): " + (status.strip().splitlines() or ["git status failed"])[0]
    if not assume_merged:
        integ = integration_ref(path)
        if integ is None or git(path, "merge-base", "--is-ancestor", row["head"], integ)[0] != 0:
            return f"its head is not merged into {integ or 'any integration branch'} (a squash merge: confirm the PR merged, then --assume-merged)"
    return None


def database_config(path: str) -> dict | None:
    """The PostgreSQL databases this checkout's own config resolves to: {"own": development + test, "production": production};
    both empty when it has no bin/rails; None when the config cannot be read."""
    rails = Path(path) / "bin" / "rails"
    if not rails.exists():
        return {"own": [], "production": []}
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}      # the file's config decides, not an override
    rc, out = run([str(rails), "runner", RUNNER], cwd=path, env=env, timeout=180)
    if rc != 0:
        return None
    config: dict = {"own": [], "production": []}
    for line in out.splitlines():
        env_name, _, rest = line.partition("\t")
        adapter, _, database = rest.partition("\t")
        if adapter.strip() != "postgresql" or not database.strip():
            continue
        bucket = config["production"] if env_name.strip() == "production" else config["own"]
        if database.strip() not in bucket:
            bucket.append(database.strip())
    return config


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
    rc, out = run(["ps", "-o", "stat=", "-p", str(pid)], cwd="/")
    return rc == 0 and bool(out.strip()) and not out.strip().startswith("Z")


def cwd_of(pid: int) -> str | None:
    rc, out = run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], cwd="/")
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


def own_tree() -> set[int]:
    """This process, its parents, everything it started, and everything in ITS PROCESS GROUP: a teardown run from a shell inside the worktree must count
    neither that shell, nor its own `lsof`/`ps` children, nor the other stages of its own pipeline (`... 2>&1 | tail`, whose working directory is also the
    worktree) as a stray. A process in ANOTHER group (a server started elsewhere) still is one."""
    parent: dict[int, int] = {}
    group: dict[int, int] = {}
    for line in run(["ps", "-A", "-o", "pid=,ppid=,pgid="], cwd="/")[1].splitlines():
        row = line.split()
        if len(row) == 3 and all(x.isdigit() for x in row):
            parent[int(row[0])], group[int(row[0])] = int(row[1]), int(row[2])
    me = os.getpid()
    tree, pid = {me}, me
    while parent.get(pid, 0) > 1 and parent[pid] not in tree:      # the parents: a sibling of this process is NOT one of them
        pid = parent[pid]
        tree.add(pid)
    below, grown = {me}, True                                       # and only what THIS process started, not what its parents did
    while grown:
        grown = False
        for child, up in parent.items():
            if up in below and child not in below:
                below.add(child)
                grown = True
    mine = group.get(me)
    same_group = {q for q, g in group.items() if g == mine} if mine is not None else set()
    return tree | below | same_group


def processes_in(path: str) -> dict[int, str]:
    """Every process whose working directory is inside PATH, with its command, whether or not a pid file names it."""
    found: dict[int, str] = {}
    rc, out = run(["lsof", "-d", "cwd", "-Fpn"], cwd="/", timeout=60)
    if rc != 127 and out:
        pid = None
        for line in out.splitlines():
            if line.startswith("p") and line[1:].isdigit():
                pid = int(line[1:])
            elif line.startswith("n") and pid is not None:
                where = os.path.realpath(line[1:])
                if where == path or where.startswith(path + os.sep): found[pid] = ""
    else:
        for entry in Path("/proc").glob("[0-9]*"):
            try:
                where = os.path.realpath(os.readlink(entry / "cwd"))
            except OSError:
                continue
            if where == path or where.startswith(path + os.sep):
                found[int(entry.name)] = ""
    found = {pid: "" for pid in found if alive(pid)}      # a process that ended while the table was read is not a stray
    for pid in found:
        found[pid] = run(["ps", "-o", "command=", "-p", str(pid)], cwd="/")[1].strip()[:80]
    return found


def stop(pid: int) -> None:
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + STOP_WAIT
    while time.time() < deadline and alive(pid):
        time.sleep(0.1)
    if alive(pid):
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.2)


def born(path: str) -> float | None:
    """When `git worktree add` made this worktree: the mtime of its admin dir's `commondir`, written once at the add."""
    rc, gitdir = git(path, "rev-parse", "--absolute-git-dir")
    f = Path(gitdir.strip(), "commondir")
    return f.stat().st_mtime if rc == 0 and f.is_file() else None


def parent_leftovers(parent: str, main: str, registered: set[str], since: float | None = None) -> list[str]:
    """Entries in a worktrees' parent that are neither a registered worktree nor KEEP (made at or after `since`, when given)."""
    if os.path.realpath(parent) == os.path.realpath(os.path.dirname(main)) or not os.path.isdir(parent):
        return []
    out = []
    for name in sorted(os.listdir(parent)):
        full = os.path.realpath(os.path.join(parent, name))
        if name in KEEP or full in registered:
            continue
        if since is not None and os.lstat(os.path.join(parent, name)).st_mtime < since:
            continue
        out.append(name)
    return out


def open_prs_on(branch: str, cwd: str) -> list[int] | None:
    """Open PRs that use `branch` as their BASE (they stack on it) or their HEAD (still in review), or None when `gh` cannot say: the
    remote branch is then kept (fails closed)."""
    found: list[int] = []
    for side in ("--base", "--head"):
        rc, out = run(["gh", "pr", "list", "--state", "open", side, branch, "--limit", "200", "--json", "number", "--jq", ".[].number"], cwd=cwd)
        if rc != 0:
            return None
        found += [int(n) for n in out.split()]
    return sorted(set(found))


PR_BASES = open_prs_on     # the selftest swaps in a stub, so it never calls the network


def protected(main: str, branch: str) -> bool:
    """Never deleted (commit security review): an integration branch, the remote's default branch, or the main checkout's branch."""
    names = {i.removeprefix("origin/") for i in INTEGRATION}
    rc, default = git(main, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and default.strip():
        names.add(default.strip().removeprefix("origin/"))
    rc, current = git(main, "symbolic-ref", "-q", "--short", "HEAD")
    if rc == 0 and current.strip():
        names.add(current.strip())
    return branch in names


def delete_branch(main: str, branch: str, tip: str) -> list[str]:
    """Delete the worktree's merged branch, local and remote (#2296 scope addition); what was left, by name.

    LOCAL: `git update-ref -d refs/heads/<b> <tip>`, which refuses if the branch moved since the merge check. Not `git branch -d`: that judges
    "merged" against the checkout it runs in, and the main checkout's HEAD is often behind the integration branch, so it would refuse a branch
    this script has already proved merged (measured 2026-10-22: four merged branches, `-d` refused all four from a stale main). Never `-D`.
    REMOTE: deleted only when the branch is on `origin`, no open PR uses it as its base or its head, and its remote tip is still `tip`
    (`--force-with-lease`, so a branch someone pushed to since is never deleted); when `gh` cannot say, it is kept and named.
    NEVER an integration branch, the remote's default branch or the main checkout's branch (`protected`)."""
    left = []
    if not branch or protected(main, branch):
        return left
    if git(main, "update-ref", "-d", f"refs/heads/{branch}", tip)[0] != 0 and git(main, "rev-parse", "-q", "--verify", f"refs/heads/{branch}")[0] == 0:
        left.append(f"branch {branch} (it moved since the merge check)")
    if git(main, "remote", "get-url", "origin")[0] != 0 or not git(main, "ls-remote", "--heads", "origin", branch)[1].strip():
        return left
    prs = PR_BASES(branch, main)
    if prs is None:
        left.append(f"remote branch origin/{branch} (`gh` could not say whether an open PR uses it)")
    elif prs:
        left.append(f"remote branch origin/{branch} (open PR(s) {', '.join(f'#{n}' for n in prs)} use it: retarget or close them first)")
    elif (git(main, "push", "-q", f"--force-with-lease=refs/heads/{branch}:{tip}", "origin", f":refs/heads/{branch}")[0] != 0
          or git(main, "ls-remote", "--heads", "origin", branch)[1].strip()):
        left.append(f"remote branch origin/{branch} (the delete failed, or its tip moved since the merge check)")
    return left


def audit(root: str, say=print, parents: list[str] | None = None) -> int:
    """Every entry in every worktrees' parent that is not a registered worktree or KEEP (#2296): 1 when any, so a doctor can fail on it.
    The parents are those of the registered worktrees, the conventional `<main checkout>-wt` sibling, and any `parents` given: after the last
    worktree in a parent is torn down, only the convention or an explicit parent still finds what it left."""
    rows = worktrees(os.path.realpath(root))
    if not rows:
        say(f"worktree_teardown --audit: {root} is not a git repository")
        return 2
    main = rows[0]["path"]
    registered = {os.path.realpath(r["path"]) for r in rows}
    where = {os.path.dirname(r["path"]) for r in rows[1:]} | {main + "-wt"} | {os.path.realpath(p) for p in parents or []}
    found = {p: parent_leftovers(p, main, registered) for p in sorted(where)}
    found = {p: f for p, f in found.items() if f}
    for p, f in found.items():
        say(f"worktree_teardown --audit: {p} holds {len(f)} entr{'y' if len(f) == 1 else 'ies'} that no worktree owns: " + ", ".join(f[:20])
            + (" ..." if len(f) > 20 else ""))
    if not found:
        say("worktree_teardown --audit: every worktrees' parent holds only worktrees and " + ", ".join(sorted(KEEP)))
    return 1 if found else 0


def teardown(path: str, dry_run=False, assume_merged=False, pg_bin: str | None = None, say=print) -> int:
    path = os.path.realpath(path)
    why = refusal(path, assume_merged)
    if why:
        say(f"worktree_teardown: REFUSED, {why}")
        return 1
    main = worktrees(path)[0]["path"]
    config = database_config(path)
    shared_cfgs = {w["path"]: database_config(w["path"]) for w in worktrees(path) if w["path"] != path}      # the main checkout and every other worktree
    if config is None or any(c is None for c in shared_cfgs.values()):
        broken = ([path] if config is None else []) + [w for w, c in shared_cfgs.items() if c is None]
        say("worktree_teardown: FAILED CLOSED, could not read the databases from config/database.yml (`bin/rails runner` failed) in: " + ", ".join(broken)
            + "; without every registered worktree's names it cannot tell which databases are shared. Nothing was changed.")
        return 1
    names = config["own"]
    shared = set(config["production"])                   # a production name is never dropped, whatever this config says
    for c in shared_cfgs.values():
        shared |= set(c["own"]) | set(c["production"])   # nor one another registered worktree resolves to
    existing: list[str] = []
    if names:
        psql, dropdb = pg_tool(pg_bin or os.environ.get("PG_BIN"), "psql"), pg_tool(pg_bin or os.environ.get("PG_BIN"), "dropdb")
        listed = existing_databases(psql) if psql and dropdb else None
        if listed is None:
            say("worktree_teardown: FAILED CLOSED, cannot reach PostgreSQL (psql/dropdb missing or the server is down; see --pg-bin); nothing was changed")
            return 1
        existing = listed
    doomed = owned(existing, names, shared)
    skipped = [n for n in names if n in shared]
    pids = own_pids(path)
    listed_here = processes_in(path)
    known = set(pids) | own_tree()
    strays = {p: c for p, c in listed_here.items() if p not in known}
    say(f"worktree_teardown: {path}")
    say(f"  stop {len(pids)} process(es): {pids}")
    say(f"  drop {len(doomed)} database(s): {doomed}" + (f" (shared with the main checkout, another worktree or production, left alone: {skipped})" if skipped else ""))
    if strays:
        say(f"worktree_teardown: REFUSED, {len(strays)} process(es) have their working directory inside the worktree but no pid file naming them: "
            + "; ".join(f"{p} {c}" for p, c in strays.items()) + ". Stop them, then run this again; nothing was changed.")
        return 1
    if dry_run:
        say("  --dry-run: nothing changed")
        return 0
    since = born(path)
    row = next(r for r in worktrees(path) if r["path"] == path)
    shutil.rmtree(os.path.join(path, SCRATCH), ignore_errors=True)      # the worktree's own artifacts (#2296), before the remove that would refuse them
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
    left += ["databases (PostgreSQL could not be asked afterwards)"] if now is None else [f"database {d}" for d in owned(now, names, shared)]
    left += [f"process {p}" for p in pids if alive(p)]
    left += [f"worktree {path}"] if os.path.exists(path) or any(r["path"] == path for r in worktrees(main)) else []
    left += delete_branch(main, row["branch"], row["head"])
    registered = {os.path.realpath(r["path"]) for r in worktrees(main)}
    left += [f"{os.path.join(os.path.dirname(path), e)} (made in the worktrees' parent during this worktree's life: it belongs under "
             f"<worktree>/{SCRATCH}, which goes with the worktree)" for e in parent_leftovers(os.path.dirname(path), main, registered, since)]
    if left:
        say("worktree_teardown: LEFT BEHIND: " + ", ".join(left))
        return 1
    say("worktree_teardown: done, nothing left: no database, no process, no worktree, no branch, nothing beside it")
    return 0


# ---------------------------------------------------------------------------------------------------------------- wording

# Where an agent is told how to end a worktree: (path from the repository root, the line that opens the instruction, how many lines it spans, the text
# that names this script there: the hook builds its path from the constant `{TEARDOWN}`). Each must name this script. `git worktree remove` alone leaves the databases behind, so a place that says only that is the defect (#2058).
WORDING_SITES = (
    ("plugins/rails-stack/skills/parallel-session-lane/SKILL.md", "3. **Clean up when done", 4, "worktree_teardown.py"),
    ("plugins/rails-stack/skills/parallel-session-lane/references/one-issue-at-a-time.md", "3. **Clean up when done", 3, "worktree_teardown.py"),
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
# prints (env, adapter, database) as a Rails app with a checkout suffix resolves them: the main checkout has no suffix, `shared` resolves to main's
# names, `prodnamed` resolves its development database to the production name, `prodown` to a production name of its OWN (no other checkout
# lists it), `badcfg` cannot boot; every other checkout shares the production name
d=$(basename "$(pwd)")
case "$d" in
  badcfg) echo boom >&2; exit 3 ;;
  prodown) printf 'development\\tpostgresql\\tapp_production_prodown\\ntest\\tpostgresql\\tapp_test_prodown\\nproduction\\tpostgresql\\tapp_production_prodown\\n' ;;
  main|shared) printf 'development\\tpostgresql\\tapp_dev\\ntest\\tpostgresql\\tapp_test\\nproduction\\tpostgresql\\tapp_production\\n' ;;
  prodnamed) printf 'development\\tpostgresql\\tapp_production\\ntest\\tpostgresql\\tapp_test_prodnamed\\nproduction\\tpostgresql\\tapp_production\\n' ;;
  *) printf "development\\tpostgresql\\tapp_dev_$d\\ntest\\tpostgresql\\tapp_test_$d\\ndevelopment\\tsqlite3\\tstorage/$d.sqlite3\\nproduction\\tpostgresql\\tapp_production\\n" ;;
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
        os.chmod(os.path.join(main, "bin", "rails"), 0o700)
        Path(main, ".gitignore").write_text("tmp/\n")
        Path(main, "a.txt").write_text("a\n")
        g("add", ".gitignore", "a.txt", "bin/rails")
        g("commit", "-qm", "base")
        for tool, body in (("psql", FAKE_PSQL), ("dropdb", FAKE_DROPDB)):
            Path(binpath, tool).write_text(body)
            os.chmod(os.path.join(binpath, tool), 0o700)

        def add(name: str, merged=True, parent: str = "") -> str:
            p = os.path.join(root, parent, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if merged:
                g("worktree", "add", "-q", "-b", f"b-{name}-{parent or 'r'}", p)
            else:       # a branch with a commit dev does not have, made in the main repository, then checked out as a worktree
                g("checkout", "-q", "-b", f"b-{name}-{parent or 'r'}")
                Path(main, "new.txt").write_text("n\n")
                g("add", "new.txt")
                g("commit", "-qm", "work")
                g("checkout", "-q", "dev")
                g("worktree", "add", "-q", p, f"b-{name}-{parent or 'r'}")
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

            # 7. nothing left beside it (#2296): scratch goes with the worktree; an export in the worktrees' parent fails by name;
            #    the KEEP entries stay; the merged branch goes, locally and on origin unless a PR stacks on it.
            global PR_BASES
            said: list[str] = []
            wt_parent = os.path.join(root, "repo-wt")
            w7 = add("scratchy", parent="repo-wt")
            universe()
            os.makedirs(os.path.join(w7, SCRATCH, "export"))
            Path(w7, SCRATCH, "export", "big.txt").write_text("x\n")
            os.makedirs(os.path.join(wt_parent, "_logs"), exist_ok=True)
            check("a worktree whose artifacts are in its scratch dir ends with status 0", teardown(w7, pg_bin=binpath, say=quiet) == 0)
            check("the scratch dir goes with the worktree, and the KEEP entry stays", not os.path.exists(w7) and os.path.isdir(os.path.join(wt_parent, "_logs")))
            check("its merged branch is deleted locally", g("branch", "--list", "b-scratchy-repo-wt").strip() == "")
            w8 = add("leaky", parent="repo-wt")
            universe()
            os.makedirs(os.path.join(wt_parent, "_review-leaky"))
            code = teardown(w8, pg_bin=binpath, say=said.append)
            check("an export left in the worktrees' parent fails the teardown, by name",
                  code == 1 and any("_review-leaky" in ln and SCRATCH in ln for ln in said), str(said[-2:]))
            check("the worktree itself is still removed", not os.path.exists(w8))
            check("--audit finds the conventional <main>-wt parent with no worktree left in it", audit(main, say=quiet) == 0)
            check("--audit names what no worktree owns in a given parent", audit(main, say=quiet, parents=[wt_parent]) == 1)
            os.rmdir(os.path.join(wt_parent, "_review-leaky"))
            check("--audit is clean when the parent holds only worktrees and KEEP", audit(main, say=quiet, parents=[wt_parent]) == 0)
            os.makedirs(main + "-wt/_doctrine-old")
            check("--audit scans the conventional <main>-wt parent even when no worktree is registered there", audit(main, say=quiet) == 1)
            os.rmdir(main + "-wt/_doctrine-old")
            bare = os.path.join(root, "origin.git")
            fixture_git.init(bare, "--bare", "-b", "dev")
            g("remote", "add", "origin", bare)
            for name, bases, want, needle in (("pushed", [], 0, None), ("stacked", [41], 1, "#41"), ("unknown", None, 1, "could not say")):
                wp = add(name, parent="repo-wt")
                universe()
                g("push", "-q", "origin", f"b-{name}-repo-wt")
                PR_BASES = lambda branch, cwd, _b=bases: _b  # noqa: E731
                said.clear()
                code = teardown(wp, pg_bin=binpath, say=said.append)
                on_origin = bool(g("ls-remote", "--heads", "origin", f"b-{name}-repo-wt").strip())
                if needle is None:
                    check("a merged branch with no stacked PR is deleted on origin too", code == 0 and not on_origin, str(said[-2:]))
                else:
                    check(f"the remote branch is kept and named when {name}", code == 1 and on_origin and any(needle in ln for ln in said), str(said[-2:]))
            # a remote tip that moved since the merge check is never deleted (force-with-lease)
            wm = add("moved", parent="repo-wt")
            universe()
            g("push", "-q", "origin", "b-moved-repo-wt")
            tip = g("rev-parse", "b-moved-repo-wt").strip()
            later = g("commit-tree", "-p", tip, "-m", "pushed after the merge", f"{tip}^{{tree}}").strip()      # the remote moves, the local branch does not
            g("push", "-q", "origin", f"{later}:refs/heads/b-moved-repo-wt")
            PR_BASES = lambda branch, cwd: []  # noqa: E731
            said.clear()
            code = teardown(wm, pg_bin=binpath, say=said.append)
            check("a remote branch whose tip moved since the merge check is kept and named",
                  code == 1 and bool(g("ls-remote", "--heads", "origin", "b-moved-repo-wt").strip()) and any("moved" in ln for ln in said), str(said[-2:]))
            check("an integration branch is protected from deletion", protected(main, "dev") and protected(main, "main") and not protected(main, "b-x"))
            PR_BASES = open_prs_on

            def td(path, **kw):      # a raise inside the teardown is a failed fixture with a label, not a crashed selftest
                try:
                    return teardown(path, pg_bin=binpath, say=quiet, **kw)
                except Exception as e:      # noqa: BLE001
                    failures.append(f"the teardown raised on {os.path.basename(path)}: {e!r}")
                    return 99

            def cli(path, *flags, cwd="/"):      # the script as a separate process: the selftest's own children are then siblings of it, not descendants
                r = subprocess.run([sys.executable, os.path.abspath(__file__), path, "--pg-bin", binpath, *flags], cwd=cwd, capture_output=True, text=True, timeout=300)
                return r.returncode, r.stdout + r.stderr

            # 8. a path that is not a worktree of this repository is refused, and nothing is touched
            plain = os.path.join(root, "plain")
            os.makedirs(plain)
            other = os.path.join(root, "other")
            fixture_git.init(other, "-b", "dev")
            wsub = add("subw")
            os.makedirs(os.path.join(wsub, "inner"))
            universe("app_dev_subw", "app_test_subw", "app_dev", "app_test")
            srv_sub = serve(wsub)
            spawned.append(srv_sub)
            check("a plain directory is refused", td(plain) == 1 and dropped() == [])
            check("another repository's checkout is refused, not ended", td(other) == 1 and dropped() == [])
            check("a subdirectory of a worktree is refused (it is not a worktree of this repository)",
                  td(os.path.join(wsub, "inner")) == 1 and dropped() == [] and srv_sub.poll() is None and listed(wsub))

            # 9. an unreadable database config fails closed: nothing dropped, stopped or removed
            wbad = add("badcfg")
            universe("app_dev_badcfg", "app_test_badcfg")
            srv_bad = serve(wbad)
            spawned.append(srv_bad)
            check("an unreadable database config fails closed and removes nothing",
                  td(wbad) == 1 and dropped() == [] and srv_bad.poll() is None and listed(wbad))
            srv_bad.kill()
            srv_bad.wait()
            g("worktree", "remove", "--force", wbad)      # the fixture's own cleanup: the broken worktree would block every later teardown, by design

            # 10. another registered worktree's databases, and a production name, are never dropped
            wax, wbx = add("x", parent="a"), add("x", parent="b")
            universe("app_dev_x", "app_test_x", "app_dev", "app_test", "app_production")
            check("a worktree that resolves to the same names as another registered worktree still ends", td(wax) == 0)
            check("a database another registered worktree resolves to is never dropped", dropped() == [] and listed(wbx), str(dropped()))
            wprod = add("prodnamed")
            universe("app_production", "app_test_prodnamed", "app_dev", "app_test")
            check("a worktree whose config resolves to the production name still ends", td(wprod) == 0)
            check("a production database name is never dropped, whatever the worktree's config says", dropped() == ["app_test_prodnamed"], str(dropped()))

            wown = add("prodown")
            universe("app_production_prodown", "app_test_prodown", "app_production")
            check("a worktree whose own production name is its development name still ends", td(wown) == 0)
            check("a production database name is never dropped, even one only this worktree's config lists", dropped() == ["app_test_prodown"], str(dropped()))

            # 12. THE DOCUMENTED FLOW: run from a shell whose working directory is the worktree being ended
            wcli = add("fromin")
            universe("app_dev_fromin", "app_test_fromin")
            ran = cli(wcli, cwd=wcli)
            check("run with its working directory inside the worktree, the CLI ends it (its own children are not strays)",
                  ran[0] == 0 and not listed(wcli) and sorted(dropped()) == ["app_dev_fromin", "app_test_fromin"], ran[1][-300:])

            # 13. A PIPELINE: `teardown ... 2>&1 | cat` from inside the worktree, the way our sessions always run it: cat is a sibling in the same process group
            wpipe = add("piped")
            universe("app_dev_piped", "app_test_piped")
            piped = subprocess.run(f"{shlex.quote(sys.executable)} {shlex.quote(os.path.abspath(__file__))} {shlex.quote(wpipe)} --pg-bin {shlex.quote(binpath)} 2>&1 | cat",
                                   shell=True, cwd=wpipe, capture_output=True, text=True, timeout=300)
            check("run from inside the worktree and piped into cat, it ends it (a stage of its own pipeline is not a stray)",
                  not listed(wpipe) and sorted(dropped()) == ["app_dev_piped", "app_test_piped"], piped.stdout[-300:])

            # 11. a process with no pid file is noticed: the teardown refuses and never reports 'nothing left'
            wstray = add("stray")
            universe("app_dev_stray", "app_test_stray")
            stray = subprocess.Popen(["sleep", "60"], cwd=wstray, start_new_session=True)      # its own process group: the selftest's group is excluded by design
            spawned.append(stray)
            check("a process with no pid file is noticed and the teardown refuses", cli(wstray)[0] == 1 and dropped() == [] and stray.poll() is None and listed(wstray))
            check("a dry run says so too, and changes nothing", cli(wstray, "--dry-run")[0] == 1 and dropped() == [] and listed(wstray))
            stray.kill()
            stray.wait()
            check("once the stray is gone the same worktree ends", cli(wstray)[0] == 0 and sorted(dropped()) == ["app_dev_stray", "app_test_stray"], str(dropped()))

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
    ap = argparse.ArgumentParser(description="End a finished worktree: stop its servers, drop its databases, remove it, prove nothing is left.",
                                 epilog="Fails closed. One registered worktree whose config cannot be read (bin/rails runner fails) blocks every teardown, "
                                        "and the refusal names it: fix or remove that worktree first.")
    ap.add_argument("worktree", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assume-merged", action="store_true")
    ap.add_argument("--pg-bin")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check-wording", action="store_true")
    ap.add_argument("--audit", action="store_true", help="list what no worktree owns in each worktrees' parent (exit 1 when any)")
    ap.add_argument("--parent", action="append", default=[], help="with --audit: another worktrees' parent to scan")
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
    if args.audit:
        return audit(args.root, parents=args.parent)
    if not args.worktree:
        ap.error("a worktree path is required")
    return teardown(args.worktree, dry_run=args.dry_run, assume_merged=args.assume_merged, pg_bin=args.pg_bin)


if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:]))
