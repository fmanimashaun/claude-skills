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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coordination  # noqa: E402

INTEGRATION = ("origin/dev", "dev", "origin/main", "main", "origin/master", "master")
PREFIX = "BLOCKED by rails-flow worktree guard:"
ZOMBIE_WARN = 50
STOPPED_ORPHAN_WARN = 3     # a stopped process nobody waits on is never normal, so far fewer than zombies
# The DOCUMENTED forms only: `issue-77` / `issue_77` (after a separator or at the start), and `77-slug` / `.../77-slug`
# (a number that STARTS a path segment). `slug-20` is not issue 20 (ae's review of #1596: `node-20` and `ubuntu-20`).
ISSUE_WORD = re.compile(r"(?:^|[/_-])issue[-_]?(\d{2,6})(?=[-_/]|$)")
ISSUE_SEGMENT = re.compile(r"(?:^|/)(\d{2,6})(?=[-_/]|$)")
VALUE_OPTS = {"-b", "-B", "--reason"}
# A date (2026-10-02, 2026-10) in a name: its month and day are not issue numbers.
DATE = re.compile(r"(?:19|20)\d{2}[-_]\d{2}(?:[-_]\d{2})?")


def _env_int(name: str, default: int) -> int:
    """A tuning value from the environment; a junk one is the default, never a traceback."""
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


# The hook's own timeout is 15 s and a hook that times out is a NON-blocking error: the command RUNS. So this process must
# answer, with a refusal if need be, before that. Every git call spends from one budget (WORKTREE_GUARD_BUDGET, seconds).
BUDGET = _env_float("WORKTREE_GUARD_BUDGET", 10)
_STARTED = time.monotonic()
UNAVAILABLE = 127


def _remaining() -> float:
    return BUDGET - (time.monotonic() - _STARTED)


def git(cwd, *args: str) -> tuple[int, str]:
    """(exit code, stdout). 127 means git did not answer: missing, out of budget, or too slow."""
    remaining = _remaining()
    if remaining <= 0:
        return UNAVAILABLE, ""
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=min(5, remaining))
    except (OSError, subprocess.TimeoutExpired):
        return UNAVAILABLE, ""
    return done.returncode, done.stdout


def issue_key(name: str | None) -> int | None:
    """The issue number a branch or directory name carries, or None.

    A DATE (`2026-10-02`) is removed first, so its year is not read as issue 2026. A bare number is otherwise an
    issue whatever its size: this repository is past #1500 and will pass #1900, so a year-sized range cannot be
    excluded without ignoring real issues."""
    name = DATE.sub("", name or "")
    for pattern in (ISSUE_WORD, ISSUE_SEGMENT):
        m = pattern.search(name)
        if m:
            return int(m.group(1))
    return None


def keys(*names: str | None) -> set[int]:
    return {k for k in (issue_key(n) for n in names) if k is not None}


def worktrees(cwd) -> list[dict] | None:
    """The worktrees, or None when git could not list them: an empty list would read as "none exist"."""
    rc, out = git(cwd, "worktree", "list", "--porcelain")
    if rc != 0:
        return None
    rows: list[dict] = []
    for block in out.strip().split("\n\n"):
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


# A redirection operator on its own (`>`, `2>`, `>>`, `&>`, `>&`, `<`): its TARGET is the next token.
REDIRECT_ALONE = re.compile(r"^[0-9]*(?:[<>]{1,2}|&>>?|>&|<&)$")


def parse_add_args(args: list[str]) -> tuple[str | None, list[str]]:
    """(branch, positional operands) of `git worktree add`'s arguments, read the way git reads them.

    Redirections are dropped first (`>/dev/null`, `2>&1`, `> log`): they are not operands, and one placed
    before the commit-ish used to BECOME it, hiding the branch. Then git's own option grammar: `-b`/`-B` take
    a value attached (`-Bname`), separate (`-B name`) or after other short flags (`-fb name`, `-fbname`);
    `--reason` takes one (`--reason=x` or `--reason x`); `--` ends the options.
    """
    clean: list[str] = []
    k = 0
    while k < len(args):
        a = args[k]
        if a.isdigit() and k + 1 < len(args) and REDIRECT_ALONE.match(args[k + 1]):
            k += 1                      # `2 >& 1` tokenises as 2, >&, 1: the 2 is the descriptor, not an operand
            continue
        if re.search(r"[<>]", a):
            k += 2 if REDIRECT_ALONE.match(a) else 1     # an operator alone takes the NEXT token as its target
            continue
        clean.append(a)
        k += 1
    branch: str | None = None
    positional: list[str] = []
    j = 0
    while j < len(clean):
        a = clean[j]
        if a == "--":
            positional.extend(clean[j + 1:])
            break
        if a == "--reason":
            j += 2
            continue
        if a.startswith("--") or a == "-":
            if not a.startswith("--"):
                positional.append(a)
            j += 1
            continue
        if a.startswith("-"):
            flags = a[1:]
            for k, ch in enumerate(flags):
                if ch in "bB":
                    value = flags[k + 1:]
                    if not value and j + 1 < len(clean):
                        j += 1
                        value = clean[j]
                    branch = value or branch
                    break
            j += 1
            continue
        positional.append(a)
        j += 1
    return branch, positional


HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z0-9_]+)\2")
SHELL_WORD = re.compile(r"(?:^|[\s;&|(/])(?:ba|z|da|k|a)?sh(?:\s|$)")


def strip_heredocs(command: str) -> str:
    """Drop the BODY of a heredoc fed to a command that is not a shell: it is data (`cat <<'EOF' > notes`), and a
    body that merely mentions `git worktree add` is not a command. A body fed to a SHELL (`bash <<EOF`) IS commands,
    so it stays and is judged like any other."""
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        m = HEREDOC.search(line)
        if not m:
            continue
        delim, dash = m.group(3), m.group(1) == "-"
        j = i
        while j < len(lines) and (lines[j].lstrip("\t") if dash else lines[j]) != delim:
            j += 1
        if j >= len(lines):
            continue                                   # no terminator: leave the text alone (fail toward judging it)
        if SHELL_WORD.search(line[:m.start()]):
            out.extend(lines[i:j + 1])                 # a shell reads it: keep the body AND the terminator
        else:
            out.append(lines[j])                       # data: drop the body, keep the terminator line
        i = j + 1
    return "\n".join(out)


def worktree_adds(command: str, _depth: int = 0) -> list[dict] | None:
    """Each `git ... worktree add ...` in the command as {path, branch, commitish}; None if unreadable.

    A command inside a string (`bash -c 'git worktree add ...'`, `eval "..."`) is one quoted token here; the shell
    wrapper's normaliser surfaces it, so it is read again, two levels deep."""
    command = strip_heredocs(command.replace("\\\n", ""))     # a backslash-newline is a continuation: the shell joins the lines
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
            branch, positional = parse_add_args(args)
            found.append({"path": positional[0] if positional else None, "branch": branch,
                          "commitish": positional[1] if len(positional) > 1 else None})
    if _depth < 2:
        for idx, tok in enumerate(tokens):
            prev = tokens[idx - 1] if idx else ""
            # Only the string a shell WILL run: the argument of `-c` (also `-lc`, `-ic`) or of `eval`. A quoted word
            # elsewhere (`echo "git worktree add"`) is a mention, and reading it as a command would refuse it.
            if (prev == "eval" or re.fullmatch(r"-[A-Za-z]*c", prev)) and "worktree" in tok and "add" in tok:
                found.extend(worktree_adds(tok, _depth + 1) or [])
    return found


def deny(msg: str) -> int:
    print(f"{PREFIX} {msg}", file=sys.stderr)
    return 2


# A command that moves somewhere else before it adds: where the worktree really goes cannot be known from the cwd.
MOVES = re.compile(r"(?:^|[\s;&|(])(?:cd|pushd)\s|\s-C\s|--git-dir|--work-tree")


def check(payload: dict, raw_only: bool = False) -> int:
    """`raw_only`: the wrapper's normaliser saw no worktree add, but the command looks like one once quotes are
    dropped. Then finding none here is a MENTION and passes; when the normaliser DID see one, finding none is a
    parser disagreement, and that is refused."""
    command = str((payload.get("tool_input") or {}).get("command", ""))
    cwd = payload.get("cwd") or os.getcwd()
    sid = payload.get("session_id")
    adds = worktree_adds(command)
    if not adds:
        if raw_only:
            return 0
        return deny("could not read the `git worktree add` in this command, so it cannot be judged. Write it as a plain "
                    "`git worktree add <path> [-b <branch>] [<commit>]` on its own line.")
    inside = git(cwd, "rev-parse", "--is-inside-work-tree")[0]
    if inside == UNAVAILABLE:
        return deny("git did not answer in time, or is not installed, so this `git worktree add` cannot be judged: it timed out "
                    "or could not run. Retry, or create the worktree yourself outside the agent.")
    if inside != 0:
        if MOVES.search(command):
            return deny("this `git worktree add` follows a `cd` or `-C`, and the session's directory is not inside a git "
                        "repository, so which repository it targets cannot be judged. Run it from inside the repository.")
        return 0                                  # dormant outside a git repository
    existing = worktrees(cwd)
    if existing is None:
        return deny("could not list the worktrees (`git worktree list` failed or timed out), so a duplicate cannot be ruled out "
                    "and this `git worktree add` cannot be judged.")
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
        if rp is None:
            return deny("could not locate the coordination record (`git rev-parse --git-common-dir` failed or timed out), so "
                        "this session's lanes cannot be read and this `git worktree add` cannot be judged.")
        try:
            record = coordination.load(rp)
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
    # Inside the budget: session-start's own hook timeout is 10 s, and a `ps` that hangs must not outlast it.
    left = _remaining()
    if left <= 0:
        return 0, []
    try:
        out = subprocess.run(["ps", "-axo", "stat=,ppid=,comm="], capture_output=True, text=True,
                             timeout=min(3, left)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0, []
    by_parent: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].startswith("Z") and parts[1].isdigit():
            by_parent[int(parts[1])] = by_parent.get(int(parts[1]), 0) + 1
    shown = max(1, _env_int("RAILS_FLOW_ZOMBIE_TOP", 3))
    top = sorted(by_parent.items(), key=lambda kv: -kv[1])[:shown]
    names = []
    for ppid, n in top:
        try:
            # The EXECUTABLE NAME only (`comm`, not `command`): a command line can carry a credential
            # (`mysql -pSECRET`, `node server.js --token=...`), and this prints into the model's context,
            # again after every compaction.
            comm = os.path.basename(subprocess.run(["ps", "-o", "comm=", "-p", str(ppid)], capture_output=True, text=True,
                                                   timeout=max(0.5, min(2, _remaining()))).stdout.strip())[:40]
        except (OSError, subprocess.TimeoutExpired):
            comm = "?"
        names.append((ppid, comm or "?", n))
    return sum(by_parent.values()), names


def stopped_orphans() -> tuple[int, list[tuple[int, str]]]:
    """(count of this user's STOPPED ORPHANS, the first few as (pid, session id or "?")) (#1582 slice C).

    Stopped (state T) and re-parented to pid 1: a process a session stopped and left, which no one will ever resume.
    The owner is read from the process's ENVIRONMENT (`CLAUDE_CODE_SESSION_ID`), the same marker the SessionEnd reaper
    uses, and only that one entry is kept: an environment can hold a credential, and this prints into the model's context."""
    left = _remaining()
    if left <= 0:
        return 0, []
    try:
        out = subprocess.run(["ps", "-U", str(os.getuid()), "-o", "pid=,stat=,ppid="], capture_output=True, text=True,
                             timeout=min(3.0, left)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0, []
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].isdigit() and parts[1].startswith("T") and parts[2] == "1":
            pids.append(int(parts[0]))
    # The owner is read by the reaper's own exact parser (the variable named exactly CLAUDE_CODE_SESSION_ID), never from
    # `ps -E` text: that joins argv and environment, so an argument spelling the entry showed as the owner (#1646 S1).
    shown = pids[:max(1, _env_int("RAILS_FLOW_ZOMBIE_TOP", 3))]
    owners = [(pid, "?") for pid in shown]
    reaper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts", "session_reaper.py")
    try:
        got = subprocess.run([sys.executable, reaper, "--owners", *map(str, shown)], capture_output=True, text=True,
                             timeout=max(0.5, min(2, _remaining()))).stdout
        known = dict(line.split(None, 1) for line in got.splitlines() if len(line.split()) == 2)
        owners = [(pid, known.get(str(pid), "?")) for pid in shown]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return len(pids), owners


def resume(session_id: str, cwd: str) -> int:
    """The SessionStart pointer. Silent when there is nothing to say: this prints again after every compaction."""
    global BUDGET
    BUDGET = min(BUDGET, 6)           # this runs inside session-start's 10 s hook timeout; leave room for the rest of it
    if git(cwd, "rev-parse", "--is-inside-work-tree")[0] != 0:
        return 0
    lines: list[str] = []
    existing = worktrees(cwd) or []
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
    if count >= max(1, _env_int("RAILS_FLOW_ZOMBIE_WARN", ZOMBIE_WARN)):
        parents = "; ".join(f"pid {p} `{c}` ({n})" for p, c, n in top)
        lines.append(f"- {count} zombie processes on this machine; busiest parents: {parents}. Every fork() fails at the "
                     f"per-user limit: see parallel-session-lane process-hygiene.")
    orphans, owners = stopped_orphans()
    if orphans >= max(1, _env_int("RAILS_FLOW_STOPPED_ORPHAN_WARN", STOPPED_ORPHAN_WARN)):
        who = ", ".join(f"pid {p} (session {sid})" for p, sid in owners)
        lines.append(f"- {orphans} stopped orphan processes (parent pid 1) that a session left behind: {who}. A session's own "
                     f"are reaped when it ends; to clear one now: echo '{{\"session_id\":\"<id>\"}}' | python3 "
                     f"\"${{CLAUDE_PLUGIN_ROOT}}/scripts/session_reaper.py\".")
    if lines:
        print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--raw", action="store_true", help="the wrapper matched only after dropping quotes")
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
        return check(payload if isinstance(payload, dict) else {}, raw_only=args.raw)
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
    check_("a date is not an issue", issue_key("chore/2026-10-02-x") is None and issue_key("chore/2026-10-x") is None)
    check_("a year-sized number IS an issue when it is written as one", issue_key("fix/2026-again") == 2026
           and issue_key("feature/issue-1999-x") == 1999)
    check_("a version is not an issue", issue_key("chore/arm-v1.153.0") is None)
    check_("no number, no key", issue_key("feature/lane-band") is None)
    adds = worktree_adds("cd /x && git -C repo worktree add -f ../b -b feat/b dev; echo done") or []
    check_("a worktree add is found after cd and git -C", len(adds) == 1 and adds[0]["path"] == "../b"
           and adds[0]["branch"] == "feat/b" and adds[0]["commitish"] == "dev", str(adds))
    check_("a quoted MENTION is not an add (only the argument of -c or eval is read as a command)",
           worktree_adds('echo "git worktree add ../x"') == [])
    check_("a bash -lc string is read", len(worktree_adds("bash -lc 'git worktree add ../x -b y dev'") or []) == 1)
    check_("quoted words are dequoted", len(worktree_adds("'git' worktree \"add\" ../x") or []) == 1)
    check_("slug-20 is not issue 20", issue_key("chore/ubuntu-20") is None and issue_key("pr-20-review") is None)
    check_("20-slug and issue-20 are", issue_key("fix/20-again") == 20 and issue_key("feature/issue-20-x") == 20)
    check_("an existing branch given as the commit-ish is read", (worktree_adds("git worktree add ../x feat/a") or [{}])[0].get("commitish") == "feat/a")
    nested = worktree_adds("bash -c 'git worktree add ../n -b feat/n dev'") or []
    check_("a worktree add inside bash -c is read", len(nested) == 1 and nested[0]["branch"] == "feat/n", str(nested))
    check_("a worktree add inside eval is read", len(worktree_adds('eval "git worktree add ../n -b feat/n dev"') or []) == 1)
    check_("a quoted mention with no git in front is still not an add", worktree_adds("echo 'worktree add ../x'") == [])
    check_("a backslash-newline continuation is joined", (worktree_adds("git worktree add -B \\\nfeat/a ../d") or [{}])[0].get("branch") == "feat/a")
    check_("a heredoc body fed to cat is data, not a command", worktree_adds("cat <<'EOF' > f\ngit worktree add ../x\nEOF") == [])
    check_("a heredoc body fed to a shell is read as commands", len(worktree_adds("bash <<'EOF'\ngit worktree add ../x\nEOF") or []) == 1)
    check_("an unterminated heredoc is left in (judged, not skipped)", len(worktree_adds("cat <<EOF\ngit worktree add ../x") or []) == 1)
    check_("an unbalanced quote is unreadable, not empty", worktree_adds("git worktree add 'x") is None)
    for cmd, want in (("git worktree add -f -Bfeat/a ../d", ("feat/a", ["../d"])),
                      ("git worktree add -fbfeat/a ../d", ("feat/a", ["../d"])),
                      ("git worktree add -fb feat/a ../d", ("feat/a", ["../d"])),
                      ("git worktree add ../d >/dev/null feat/a", (None, ["../d", "feat/a"])),
                      ("git worktree add ../d 2>&1 feat/a", (None, ["../d", "feat/a"])),
                      ("git worktree add ../d -b n dev > log 2>&1", ("n", ["../d", "dev"])),
                      ("git worktree add --reason=x --lock ../d feat/a", (None, ["../d", "feat/a"])),
                      ("git worktree add --reason x ../d feat/a", (None, ["../d", "feat/a"])),
                      ("git worktree add -- ../d feat/a", (None, ["../d", "feat/a"]))):
        got = (worktree_adds(cmd) or [{}])[0]
        check_(f"git's grammar: {cmd}", (got.get("branch"), [x for x in (got.get("path"), got.get("commitish")) if x]) == want, str(got))
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"worktree_guard selftest: {ran[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
