#!/usr/bin/env python3
"""The coordinator's handoff round, end to end (#1725): who gets it, who waits, and whether each reply is true.

    wrap_round.py plan   --sessions sessions.json [--me NAME]
    wrap_round.py verify --sessions sessions.json --replies replies.json [--repo-root .] [--base origin/dev]
                         [--board-out board.json] [--handoff-out handoff.md]
    wrap_round.py --selftest

`plan` prints the round message once and one line per session: `send`, `skip` (it holds a heavy run, so it gets the
round when that run has finished, never mid-run) or `self` (the coordinator does not clear itself; it compacts).

`verify` checks every reply against git instead of believing it; it exits 0 only when every session is READY (a SKIP,
still waiting on a heavy run, is not done). A claimed head must be a full 40-character SHA, and
must be what `origin` holds for that branch -- or, when the branch is gone because it merged, an ancestor of the
integration branch. A worktree the session says it removed must be absent from `git worktree list`. A missing reply
is a finding, not a pass: silence and READY look identical on a board nobody re-derives.

It reports and writes two local files (the board rows and the coordinator handoff); it sends nothing, merges nothing,
and runs only the reads in READ_ONLY, in their exact shapes. Exit: 0 every session READY (or the coordinator), 1 a
finding or a session still waiting (SKIP), 2 usage, 3 a read failed (including a timeout or a missing git).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROUND = (
    "Handoff round from the coordinator. Reply READY only when all four are done:\n"
    "1. commit and push your work in progress;\n"
    "2. write your handoff (step, next command, open review findings, unfinished edits);\n"
    "3. remove each FINISHED worktree with `git worktree remove <path>` -- never `--force`;\n"
    "4. drop the test databases you created.\n"
    'Reply as JSON: {"name": <your name>, "ready": true, "branch": <branch>, "head": <`git rev-parse HEAD`, '
    'all 40 characters>, "removed": [<worktree paths you removed>]}.'
)

# Exact argv SHAPES: fixed words, and None for a positional slot. A prefix match let
# `git ls-remote --upload-pack=<cmd> origin` through (review of #1833); a shape fixes the length and every word, and a
# slot may not start with "-", so no option can be smuggled into one. `git worktree` is never a two-token key: `list`
# reads, `remove` destroys.
READ_ONLY: tuple[tuple[str | None, ...], ...] = (
    ("git", "ls-remote", "origin", None),
    ("git", "worktree", "list", "--porcelain"),
    ("git", "merge-base", "--is-ancestor", None, None),
)

# `git ls-remote` reads its pattern as a GLOB: `*`, `feat/*` and `feat/rea?` all match feat/real, so a reply naming
# branch "*" verified any branch's head as READY (review of #1833, reproduced). A branch name must be a plain ref name.
BAD_BRANCH = re.compile(r"[*?\[\\\s]|^-|\.\.|^$")

SHA = re.compile(r"[0-9a-f]{40}")


class WriteAttempted(RuntimeError):
    pass


class ReadFailed(RuntimeError):
    def __init__(self, argv: list[str], returncode: int, stderr: str):
        super().__init__(f"{' '.join(argv[:4])} failed (exit {returncode}): {stderr.strip()[:200]}")
        self.returncode = returncode


def allowed(argv: list[str]) -> bool:
    return any(len(argv) == len(shape) and all(w == s if s is not None else not w.startswith("-")
                                               for w, s in zip(argv, shape)) for shape in READ_ONLY)


def run(argv: list[str], cwd: Path, execute=subprocess.run, ok_codes: tuple[int, ...] = (0,)) -> tuple[int, str]:
    """A read from READ_ONLY, or an exception. `ok_codes` names the non-zero codes that are ANSWERS, not failures:
    `merge-base --is-ancestor` says "no" with exit 1, and folding that into "the read failed" would hide a real
    mismatch behind an unknown. A read that hangs or whose binary is missing is a failed read (exit 3), never a
    traceback."""
    if not allowed(argv):
        raise WriteAttempted(f"refused: {' '.join(argv[:4])} is not a read this round needs, in the exact shape it needs")
    try:
        r = execute(argv, cwd=cwd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise ReadFailed(argv, 124, "timed out after 60 s")
    except FileNotFoundError as exc:
        raise ReadFailed(argv, 127, str(exc))
    if r.returncode not in ok_codes:
        raise ReadFailed(argv, r.returncode, r.stderr)
    return r.returncode, r.stdout


def plan(sessions: list[dict], me: str | None) -> list[tuple[str, str, str]]:
    """(verb, name, why) per session. A heavy run is never interrupted: the round waits for it."""
    rows = []
    for s in sessions:
        name = s["name"]
        if name == me or s.get("role") == "coordinator":
            rows.append(("self", name, "the coordinator compacts; it does not clear"))
        elif s.get("heavy_run"):
            rows.append(("skip", name, f"holds a heavy run ({s['heavy_run']}); send the round when it has finished"))
        else:
            rows.append(("send", name, ""))
    return rows


def remote_head(branch: str, root: Path, runner=run) -> str | None:
    """The head origin holds for EXACTLY refs/heads/<branch>, or None. Never line 1 of a glob's answer."""
    ref = f"refs/heads/{branch}"
    _, out = runner(["git", "ls-remote", "origin", ref], root)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def worktrees(root: Path, runner=run) -> set[str]:
    _, out = runner(["git", "worktree", "list", "--porcelain"], root)
    return {l[len("worktree "):].rstrip("/") for l in out.splitlines() if l.startswith("worktree ")}


def verify(sessions: list[dict], replies: list[dict], root: Path, base: str, me: str | None,
           runner=run) -> list[dict]:
    by_name = {r.get("name"): r for r in replies}
    present = worktrees(root, runner)
    rows = []
    for verb, name, why in plan(sessions, me):
        row = {"session": name, "state": verb.upper() if verb != "send" else "", "findings": [], "head": None}
        if verb != "send":
            row["findings"] = [why]
            rows.append(row)
            continue
        r = by_name.get(name)
        if r is None:
            row["state"], row["findings"] = "MISSING", ["no reply: silence is not READY"]
            rows.append(row)
            continue
        f = row["findings"]
        if r.get("ready") is not True:
            f.append("replied, but not ready")
        head, branch = str(r.get("head") or ""), r.get("branch")
        row["head"] = head
        if not SHA.fullmatch(head):
            f.append(f"head {head!r} is not a full 40-character SHA (a short or placeholder SHA is not a claim git can check)")
        elif not branch:
            f.append("no branch named, so the head cannot be checked")
        elif BAD_BRANCH.search(str(branch)):
            f.append(f"branch {branch!r} is not a plain ref name (git ls-remote would read it as a glob)")
        else:
            on_origin = remote_head(branch, root, runner)
            if on_origin is None:
                code, _ = runner(["git", "merge-base", "--is-ancestor", head, base], root, ok_codes=(0, 1))
                if code != 0:
                    f.append(f"{branch} is not on origin and {head[:12]} is not in {base}: the work is neither pushed nor merged")
            elif on_origin != head:
                f.append(f"origin/{branch} is {on_origin[:12]}, not the claimed {head[:12]}: the push did not land")
        for path in r.get("removed") or []:
            if str(path).rstrip("/") in present:
                f.append(f"worktree {path} is still in `git worktree list`")
        row["state"] = "READY" if not f else "MISMATCH"
        rows.append(row)
    return rows


def exit_code(rows: list[dict]) -> int:
    """SKIP is not done: a session still holding a heavy run has not had the round, so `verify && compact` must not
    compact yet (review of #1833). 0 means every session is READY, or is the coordinator."""
    return 0 if all(r["state"] in ("READY", "SELF") for r in rows) else 1


def handoff(rows: list[dict]) -> str:
    lines = ["# Coordinator handoff -- handoff round", "", "| session | state | head | findings |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['session']} | {r['state']} | {(r['head'] or '')[:12]} | {'; '.join(r['findings'])} |")
    waiting = [r["session"] for r in rows if r["state"] == "SKIP"]
    failing = [r["session"] for r in rows if r["state"] in ("MISSING", "MISMATCH")]
    lines += ["", "## Next"]
    lines.append(f"- Send the round to {', '.join(waiting)} when their heavy runs finish." if waiting else "- No session is waiting on a heavy run.")
    lines.append(f"- Chase {', '.join(failing)}: their replies did not verify." if failing else "- Every reply verified.")
    lines.append("- Then compact: the coordinator keeps its context; each READY session clears itself (#1687).")
    return "\n".join(lines) + "\n"


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}: {detail}")

    def never(*_a, **_k):
        raise AssertionError("EXECUTED a command that is not a read")

    for argv in (["git", "worktree", "remove", "x"], ["git", "push", "origin", "x"], ["gh", "pr", "merge", "1"],
                 ["git", "worktree", "prune"],
                 # #1833 review: options smuggled into an allowed read, and shapes one word too long or short.
                 ["git", "ls-remote", "--upload-pack=touch /tmp/x", "origin"], ["git", "ls-remote", "--exec=x", "origin"],
                 ["git", "ls-remote", "origin", "--upload-pack=x"], ["git", "merge-base", "--is-ancestor", "--help", "x"],
                 ["git", "worktree", "list"], ["git", "ls-remote", "origin", "refs/heads/a", "extra"]):
        try:
            run(argv, Path("."), execute=never)
            failures.append(f"{argv} was NOT refused")
        except WriteAttempted:
            pass
        except AssertionError as exc:
            failures.append(f"{argv}: {exc}")

    # The three reads the round needs are ACCEPTED. Without this, narrowing READ_ONLY to nothing passes every refusal.
    seen: list[list[str]] = []

    def spy(argv, **_k):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    for argv in (["git", "ls-remote", "origin", "refs/heads/feat/a"], ["git", "worktree", "list", "--porcelain"],
                 ["git", "merge-base", "--is-ancestor", "a" * 40, "origin/dev"]):
        try:
            run(argv, Path("."), execute=spy)
        except Exception as exc:  # any refusal or crash is this fixture's failure, reported by name
            failures.append(f"accept: {argv} was refused: {exc}")
    check("accept: each of the three reads reached the executor", len(seen) == 3, str(seen))

    def hang(argv, **_k):
        raise subprocess.TimeoutExpired(argv, 60)

    try:
        run(["git", "worktree", "list", "--porcelain"], Path("."), execute=hang)
        failures.append("timeout: a hung read did not raise ReadFailed")
    except ReadFailed as exc:
        check("timeout: a hung read is a failed read with code 124", exc.returncode == 124, str(exc))
    except Exception as exc:
        failures.append(f"timeout: a hung read escaped as {type(exc).__name__}, not ReadFailed")

    A, B, C = "a" * 40, "b" * 40, "c" * 40
    remote = {"feat/a": A, "feat/c": "d" * 40}            # feat/b merged and deleted; feat/c's push did not land
    ancestors = {B}
    tree = ["/w/main", "/w/keep"]

    def stub(argv, root, ok_codes=(0,)):
        if argv[:2] == ["git", "ls-remote"]:
            # As git does: the pattern is a glob, matched against every ref (the #1833 bypass).
            import fnmatch
            return 0, "".join(f"{sha}\trefs/heads/{br}\n" for br, sha in remote.items()
                              if fnmatch.fnmatchcase(f"refs/heads/{br}", argv[3]))
        if argv[:3] == ["git", "worktree", "list"]:
            return 0, "".join(f"worktree {p}\nHEAD {A}\n\n" for p in tree)
        if argv[:3] == ["git", "merge-base", "--is-ancestor"]:
            return (0 if argv[3] in ancestors else 1), ""
        raise AssertionError(f"unexpected {argv}")

    sessions = [{"name": "coord", "role": "coordinator"}, {"name": "s1"}, {"name": "s2"}, {"name": "s3"},
                {"name": "s4", "heavy_run": "rspec, pid 4242"}, {"name": "s5"}, {"name": "s6"}, {"name": "s7"}]
    replies = [
        {"name": "s1", "ready": True, "branch": "feat/a", "head": A, "removed": ["/w/gone"]},
        {"name": "s2", "ready": True, "branch": "feat/b", "head": B, "removed": []},
        {"name": "s3", "ready": True, "branch": "feat/c", "head": C, "removed": []},
        {"name": "s5", "ready": True, "branch": "feat/a", "head": "abc1234", "removed": []},
        {"name": "s6", "ready": True, "branch": "feat/a", "head": A, "removed": ["/w/keep/"]},
    ]
    p = {n: v for v, n, _ in plan(sessions, None)}
    check("plan: the coordinator is self, not sent the round", p["coord"] == "self", str(p))
    check("plan: a session holding a heavy run is skipped, not interrupted", p["s4"] == "skip", str(p))
    check("plan: an idle session gets the round", p["s1"] == "send", str(p))

    rows = {r["session"]: r for r in verify(sessions, replies, Path("."), "origin/dev", None, runner=stub)}
    check("verify: a pushed head that origin holds is READY", rows["s1"]["state"] == "READY", str(rows["s1"]))
    check("verify: a merged-and-deleted branch whose head is in base is READY", rows["s2"]["state"] == "READY", str(rows["s2"]))
    check("verify: a head origin does not hold is a MISMATCH", rows["s3"]["state"] == "MISMATCH"
          and "did not land" in " ".join(rows["s3"]["findings"]), str(rows["s3"]))
    check("verify: a skipped session stays SKIP", rows["s4"]["state"] == "SKIP", str(rows["s4"]))
    check("verify: a short SHA is refused, not prefix-matched", rows["s5"]["state"] == "MISMATCH"
          and "40-character" in " ".join(rows["s5"]["findings"]), str(rows["s5"]))
    check("verify: a worktree claimed removed but still listed is a MISMATCH (trailing slash too)",
          rows["s6"]["state"] == "MISMATCH" and "still in" in " ".join(rows["s6"]["findings"]), str(rows["s6"]))
    check("verify: no reply is MISSING, never READY", rows["s7"]["state"] == "MISSING", str(rows["s7"]))
    check("verify: an unpushed, unmerged branch is a MISMATCH",
          verify([{"name": "x"}], [{"name": "x", "ready": True, "branch": "feat/none", "head": C}], Path("."),
                 "origin/dev", None, runner=stub)[0]["state"] == "MISMATCH", "")
    def one(reply):
        return verify([{"name": "x"}], [{"name": "x", **reply}], Path("."), "origin/dev", None, runner=stub)[0]

    g = one({"ready": True, "branch": "*", "head": A})
    check("verify: a glob branch is refused, never matched against every ref", g["state"] == "MISMATCH"
          and "plain ref name" in " ".join(g["findings"]), str(g))
    g = one({"ready": True, "branch": "feat/?", "head": A})
    check("verify: a glob branch is refused, never matched against every ref (?)", g["state"] == "MISMATCH", str(g))
    check("verify: not ready is a MISMATCH even when the head checks out",
          one({"ready": False, "branch": "feat/a", "head": A})["state"] == "MISMATCH", "")
    nb = one({"ready": True, "head": A})
    check("verify: no branch named is a MISMATCH", nb["state"] == "MISMATCH"
          and "no branch named" in " ".join(nb["findings"]), str(nb))
    def broad(argv, root, ok_codes=(0,)):   # an answer whose FIRST line is a different ref
        return 0, f"{B}\trefs/heads/feat/a-old\n{A}\trefs/heads/feat/a\n"

    check("remote_head: exact ref only, never line 1 of a broader answer",
          remote_head("feat/a", Path("."), runner=broad) == A, "")
    check("exit: a session still waiting on a heavy run (SKIP) is not done", exit_code([rows["s1"], rows["s4"]]) == 1, "")
    check("exit: every session READY or the coordinator is done", exit_code([rows["s1"], rows["s2"]]) == 0, "")
    h = handoff(list(rows.values()))
    check("handoff: names who to resend to after their heavy run", "Send the round to s4" in h, h)
    check("handoff: names who to chase", "Chase s3, s5, s6, s7" in h, h)
    for f in failures:
        print(f"FAIL {f}")
    print(f"wrap_round selftest: {'FAILED ' + str(len(failures)) if failures else 'ok'}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=("plan", "verify"))
    ap.add_argument("--sessions")
    ap.add_argument("--replies")
    ap.add_argument("--me")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--base", default="origin/dev")
    ap.add_argument("--board-out")
    ap.add_argument("--handoff-out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.mode or not a.sessions or (a.mode == "verify" and not a.replies):
        ap.print_usage(sys.stderr)
        return 2
    sessions = json.loads(Path(a.sessions).read_text(encoding="utf-8"))
    if a.mode == "plan":
        print(ROUND, end="\n\n")
        for verb, name, why in plan(sessions, a.me):
            print(f"{verb} {name}" + (f": {why}" if why else ""))
        return 0
    replies = json.loads(Path(a.replies).read_text(encoding="utf-8"))
    try:
        rows = verify(sessions, replies, Path(a.repo_root), a.base, a.me)
    except ReadFailed as exc:
        print(f"wrap_round: {exc} -- nothing was verified", file=sys.stderr)
        return 3
    for r in rows:
        print(f"{r['state']:8} {r['session']}" + (f": {'; '.join(r['findings'])}" if r["findings"] else ""))
    if a.board_out:
        Path(a.board_out).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if a.handoff_out:
        Path(a.handoff_out).write_text(handoff(rows), encoding="utf-8")
    return exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
