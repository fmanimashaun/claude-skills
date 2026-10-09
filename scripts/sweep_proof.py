#!/usr/bin/env python3
"""Record, and look up, a full gate sweep that passed on an exact tree (#1635).

Run:  (record and record_failure are called by `maintainer_doctor.py --record-proof` only: a status needs the sweep's own snapshot)
      python3 scripts/sweep_proof.py verify [--tree <sha>]  # exit 0 and print the source, or exit 1
      python3 scripts/sweep_proof.py check-wiring           # release.yml, gates.yml, release_local.sh agree
      python3 scripts/sweep_proof.py --selftest

WHY (owner's decision, #1635). A push to `dev` runs the fast sweep on GitHub; the full sweep, with
`mutation coverage`, runs on the maintainer's machine before a promotion. `release.yml` then has to
know that the full sweep already passed on the content it is about to publish, and run it itself when
it did not.

THE FORM: a commit status named `full-sweep` posted by `gh` on the commit the sweep ran on, whose
description is `tree=<tree sha>`. Why not a committed file: a file stating "this tree passed" changes
the tree it vouches for, so it can never be true of the commit that carries it. Why the TREE and not
the commit: the promotion is a merge commit, which is a new commit over the same content, so a status
keyed to dev's commit would never match it. The tree sha is a hash of the content, so equal trees are
the same bytes, and a lookup walks dev's recent commits for one with that tree and reads its statuses.

WHO CAN FORGE ONE. Anyone with write access can post a status with any text, so the lookup also requires
the status's CREATOR to be the repository owner's account (`creator.login`, set by GitHub, not by the
poster). A collaborator's or a workflow's status (`github-actions[bot]`) is ignored and the full sweep
runs. Today the owner is the only collaborator (`gh api repos/<repo>/collaborators`). The owner's own
token can still post one, which is the intended trust: they are the person who promotes. A status says the maintainer ran the full
doctor and it passed; it is not produced by a hosted runner (accepted on #1635). `record` refuses a
dirty worktree, so the sweep it vouches for ran on the committed bytes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Callable

REPO = os.environ.get("GITHUB_REPOSITORY") or "fmanimashaun/claude-skills"
CONTEXT = "full-sweep"
# Only a status CREATED by the repository owner's account counts. Anyone with write access can post a
# status with any description, and a workflow's GITHUB_TOKEN posts as `github-actions[bot]`; neither is
# the maintainer running the full doctor, so neither may excuse the release from its sweep.
TRUSTED_CREATOR = REPO.split("/")[0]
# How many of dev's newest commits are searched for one whose tree matches. The promotion's tree is
# dev's tip when nothing landed after the sweep, so this only needs to cover a few folded fixes.
DEPTH = 30

Run = Callable[..., str]


def real_run(*args: str) -> str:
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}: {out.stderr.strip() or 'failed'}")
    return out.stdout


def description(tree: str) -> str:
    return f"tree={tree}"


def find_proof(tree: str, commits: list[tuple[str, str]], statuses: Callable[[str], list[dict]]) -> str | None:
    """The sha of a commit carrying the NEWEST owner `full-sweep` status for this tree, when that status is a success.

    A tree's verdict is its newest status, not any success: an old pass followed by a failing re-run is no proof
    (review of #1636, F2). A non-success without a timestamp counts as the newest, so a malformed answer cannot
    resurrect an older success. The description must name the SAME tree: a status posted on a commit whose tree
    later differs (a hand-posted status) does not count, and only the repository owner's statuses are read."""
    newest: tuple[str, str, str] | None = None            # (created_at, sha, state)
    for sha, commit_tree in commits:
        if commit_tree != tree:
            continue
        for s in statuses(sha):
            if not (s.get("context") == CONTEXT and s.get("description") == description(tree)
                    and (s.get("creator") or {}).get("login") == TRUSTED_CREATOR):
                continue
            state = str(s.get("state"))
            stamp = str(s.get("created_at") or ("9999" if state != "success" else ""))
            # A same-second tie goes to the NON-success, so a failure can never lose to the pass it followed (review of #1636).
            if newest is None or (stamp, state != "success") > (newest[0], newest[2] != "success"):
                newest = (stamp, sha, state)
    return newest[1] if newest and newest[2] == "success" else None


def head_tree(run: Run) -> str:
    return run("git", "rev-parse", "HEAD^{tree}").strip()


def recent_commits(run: Run, ref: str = "origin/dev") -> list[tuple[str, str]]:
    out = run("git", "log", f"-{DEPTH}", "--format=%H %T", ref)
    return [tuple(line.split()) for line in out.splitlines() if line.strip()]  # type: ignore[misc]


def statuses_for(run: Run, sha: str) -> list[dict]:
    # --paginate would return concatenated arrays; a commit has a handful of statuses and the API
    # returns the newest 30 by default, which is far more than the one context this reads.
    return json.loads(run("gh", "api", f"repos/{REPO}/commits/{sha}/statuses?per_page=100"))


def verify(tree: str, run: Run = real_run) -> int:
    try:
        sha = find_proof(tree, recent_commits(run), lambda s: statuses_for(run, s))
    except Exception as e:                                # any odd answer fails SAFE, and says so readably
        print(f"no proof: lookup failed ({type(e).__name__}: {e}) — the full sweep will run")
        return 1
    if sha is None:
        print(f"no proof: no commit on dev with tree {tree} carries a passing `{CONTEXT}` status — the full sweep will run")
        return 1
    print(f"proof: tree {tree} passed the full sweep (status `{CONTEXT}` on commit {sha})")
    return 0


def snapshot(run: Run = real_run) -> tuple[str, str] | None:
    """(HEAD sha, its tree) to record, taken BEFORE the sweep starts; None when the worktree is not clean."""
    if run("git", "status", "--porcelain").strip():
        return None
    return run("git", "rev-parse", "HEAD").strip(), head_tree(run)


def record(run: Run = real_run, before: tuple[str, str] | None = None) -> int:
    """Post the status for `before`, the commit and tree the sweep STARTED on (review of #1636, F1).

    Reading HEAD after a 30 to 60 minute sweep would record a tree the sweep never ran on if anything was committed
    or edited meanwhile. Refuses when HEAD, the tree or the cleanliness differ now from the snapshot."""
    now = snapshot(run)
    if now is None:
        print("refusing to record: the worktree is not clean, so the sweep did not run on committed bytes", file=sys.stderr)
        return 1
    if before is None:
        before = now
    if now != before:
        print(f"refusing to record: the tree moved during the sweep (started {before[0][:8]}, now {now[0][:8]}); "
              "the sweep proves the bytes it STARTED on", file=sys.stderr)
        return 1
    sha, tree = before
    run("gh", "api", f"repos/{REPO}/statuses/{sha}", "-f", "state=success", "-f", f"context={CONTEXT}",
        "-f", f"description={description(tree)}")
    print(f"recorded: `{CONTEXT}` on {sha} for tree {tree}")
    return 0


def record_failure(before: tuple[str, str], run: Run = real_run) -> int:
    """Post a `failure` status for the tree a full sweep FAILED on, so an older success for it stops counting (review of #1636).

    Called by the doctor when a sweep that started on `before` ended with a failing gate; it is the newest owner status, which is
    the one `find_proof` obeys. Nothing else posts a failure."""
    sha, tree = before
    run("gh", "api", f"repos/{REPO}/statuses/{sha}", "-f", "state=failure", "-f", f"context={CONTEXT}",
        "-f", f"description={description(tree)}")
    print(f"recorded: `{CONTEXT}` FAILED on {sha} for tree {tree}")
    return 0


# ---- wiring -----------------------------------------------------------------------------


def check_wiring(release_yml: str, gates_yml: str, release_local: str) -> list[str]:
    """What must be true of the three files that use a proof, or a skipped sweep is unearned (#1635).

    A text check, on purpose: the claims are "the release skips `gates` only when `proof` found one" and
    "a dev push is fast", and the failure mode of each is a one-word edit nothing else would notice."""
    out: list[str] = []
    gates_job = release_yml.split("\n  gates:", 1)[1].split("\n  release:", 1)[0] if "\n  gates:" in release_yml else ""
    release_job = release_yml.split("\n  release:", 1)[1] if "\n  release:" in release_yml else ""
    if "needs.proof.outputs.found != 'true'" not in gates_job:
        out.append("release.yml: `gates` must run unless `proof` found a recorded sweep (needs.proof.outputs.found != 'true')")
    if "needs.gates.result == 'success'" not in release_job:
        out.append("release.yml: `release` must publish when `gates` succeeded")
    if "needs.gates.result == 'skipped' && needs.proof.outputs.found == 'true'" not in release_job:
        out.append("release.yml: `release` may publish after a skipped `gates` ONLY when `proof` found a recorded sweep")
    if "!cancelled()" not in release_job:
        out.append("release.yml: `release` needs !cancelled(), or a skipped `gates` skips it too")
    for job, text in (("release.yml `proof`", release_yml.split("\n  proof:", 1)[-1].split("\n  gates:", 1)[0]),
                      ("release.yml `release`", release_job), ("gates.yml `gates`", gates_yml)):
        if "timeout-minutes:" not in text:
            out.append(f"{job}: needs `timeout-minutes`, or a hung job holds a runner for GitHub's 6 h default")
    if "sweep_proof.py verify" not in release_yml:
        out.append("release.yml: the `proof` job must run `sweep_proof.py verify`")
    if "github.ref == 'refs/heads/dev'" not in gates_yml or "'--fast'" not in gates_yml:
        out.append("gates.yml: a push to dev must run --fast")
    if "'--require-slow'" not in gates_yml:
        out.append("gates.yml: every other run (the release's call) must run --require-slow")
    out += shard_wiring(gates_yml)
    if "sweep_proof.py verify" not in release_local:
        out.append("release_local.sh: it must reuse a proven sweep the way release.yml does (sweep_proof.py verify)")
    if "maintainer_doctor.py --gates-only --require-slow" not in release_local:
        out.append("release_local.sh: it must still run the full sweep when no proof matches")
    return out


def shard_wiring(gates_yml: str) -> list[str]:
    """What must be true of the mutation shards in gates.yml, or a missing or failed shard could read as a pass (#1739).

    A text check, like the rest: the matrix size, the `--shard I/N` and the `--expect-shards N` are three places one number is written, and
    editing one of them is exactly the change that leaves a shard unrun and the summary still green."""
    import re
    out: list[str] = []
    if "--mutation-shards" not in gates_yml:
        out.append("gates.yml: the full sweep must pass --mutation-shards, or `mutation coverage` runs twice: in the sweep and in the shards")
    sizes = re.findall(r"shard: \[([0-9, ]+)\]", gates_yml)
    count = len([x for x in sizes[0].split(",") if x.strip()]) if sizes else 0
    if not count:
        out.append("gates.yml: the `mutation` job needs a `shard: [1, 2, ...]` matrix")
    if count and f'--shard "${{SHARD}}/{count}"' not in gates_yml:
        out.append(f"gates.yml: each shard must run `--shard \"${{SHARD}}/{count}\"`, the matrix size")
    if count and f"--expect-shards {count}" not in gates_yml:
        out.append(f"gates.yml: the summary must `--expect-shards {count}`, the matrix size, or a missing shard goes unnoticed")
    mutation_job = gates_yml.split("\n  mutation:", 1)[1].split("\n  mutation-coverage:", 1)[0] if "\n  mutation:" in gates_yml else ""
    summary_job = gates_yml.split("\n  mutation-coverage:", 1)[1] if "\n  mutation-coverage:" in gates_yml else ""
    if "fail-fast: false" not in mutation_job:
        out.append("gates.yml: the `mutation` matrix needs fail-fast: false, or one shard's failure cancels the others and hides their findings")
    if "needs: mutation" not in summary_job:
        out.append("gates.yml: the `mutation coverage` summary job must `needs: mutation`")
    if "if: ${{ always() }}" not in summary_job:
        out.append("gates.yml: the `mutation coverage` summary job must run `if: ${{ always() }}`, or a failed shard skips it and a skipped job reads as green")
    if "mutation_incremental.py verdict" not in summary_job:
        out.append("gates.yml: the summary must read the shards' result (mutation_incremental.py verdict)")
    if "--merge-shards" not in summary_job:
        out.append("gates.yml: the summary must check every shard is present (mutation_check.py --merge-shards)")
    return out


def check_weekly(weekly_yml: str) -> list[str]:
    """The weekly full sweep (#1738): scheduled, on both operating systems, with no incremental skip, and failing on a missing shard."""
    out: list[str] = []
    if "schedule:" not in weekly_yml or "cron:" not in weekly_yml:
        out.append("mutation-weekly.yml: it must run on a schedule (cron)")
    for system in ("ubuntu-latest", "macos-latest"):
        if system not in weekly_yml:
            out.append(f"mutation-weekly.yml: the matrix must include {system}")
    if "--full" not in weekly_yml:
        out.append("mutation-weekly.yml: the weekly run must pass --full, or it skips what it exists to re-prove")
    if "--expect-shards" not in weekly_yml or "mutation_incremental.py verdict" not in weekly_yml:
        out.append("mutation-weekly.yml: its summary must verify every shard (verdict and --merge-shards --expect-shards)")
    if "fail-fast: false" not in weekly_yml:
        out.append("mutation-weekly.yml: fail-fast: false, so one OS's failure does not hide the other's")
    return out


def wiring_gate() -> int:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    problems = check_wiring(*(( root / f).read_text(encoding="utf-8") for f in
                              (".github/workflows/release.yml", ".github/workflows/gates.yml", "scripts/release_local.sh")))
    problems += check_weekly((root / ".github/workflows/mutation-weekly.yml").read_text(encoding="utf-8")
                             if (root / ".github/workflows/mutation-weekly.yml").is_file() else "")
    for pr in problems:
        print(f"FAIL: {pr}")
    print(f"sweep proof wiring: {'FAILED' if problems else 'ok'} ({len(problems)} problem(s))")
    return 1 if problems else 0


# ---- selftest ---------------------------------------------------------------------------


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool) -> None:
        if not ok:
            failures.append(label)

    ok_status = {"context": CONTEXT, "state": "success", "description": "tree=T1", "creator": {"login": TRUSTED_CREATOR}}
    commits = [("c3", "T3"), ("c2", "T1"), ("c1", "T0")]

    def table(d: dict[str, list[dict]]) -> Callable[[str], list[dict]]:
        return lambda sha: d.get(sha, [])

    check("a passing status on a commit with the tree is found", find_proof("T1", commits, table({"c2": [ok_status]})) == "c2")
    check("no status means no proof", find_proof("T1", commits, table({})) is None)
    check("a status on a commit with a DIFFERENT tree is ignored", find_proof("T1", commits, table({"c3": [ok_status]})) is None)
    check("a failing status is no proof", find_proof("T1", commits, table({"c2": [dict(ok_status, state="failure")]})) is None)
    check("a status for another context is no proof", find_proof("T1", commits, table({"c2": [dict(ok_status, context="ci")]})) is None)
    check("a status created by someone else is ignored (forgery)",
          find_proof("T1", commits, table({"c2": [dict(ok_status, creator={"login": "someone-else"})]})) is None)
    check("a status created by the actions bot is ignored",
          find_proof("T1", commits, table({"c2": [dict(ok_status, creator={"login": "github-actions[bot]"})]})) is None)
    check("a status with no creator is ignored", find_proof("T1", commits, table({"c2": [{k: v for k, v in ok_status.items() if k != "creator"}]})) is None)
    check("a status whose description names another tree is no proof",
          find_proof("T1", commits, table({"c2": [dict(ok_status, description="tree=T9")]})) is None)

    # F2: the newest owner status for the tree decides.
    old_ok = dict(ok_status, created_at="2026-10-06T10:00:00Z")
    new_fail = dict(ok_status, state="failure", created_at="2026-10-06T11:00:00Z")
    new_ok = dict(ok_status, created_at="2026-10-06T12:00:00Z")
    check("a newer failure beats an older success",
          find_proof("T1", commits, table({"c2": [old_ok, new_fail]})) is None)
    check("a newer failure on ANOTHER commit with the same tree beats an older success",
          find_proof("T1", [("c2", "T1"), ("c9", "T1")], table({"c2": [old_ok], "c9": [new_fail]})) is None)
    check("a newer error beats an older success", find_proof("T1", commits, table({"c2": [old_ok, dict(new_fail, state="error")]})) is None)
    check("a newer success after a failure is a proof again", find_proof("T1", commits, table({"c2": [old_ok, new_fail, new_ok]})) == "c2")
    check("a failure with no timestamp is treated as newest",
          find_proof("T1", commits, table({"c2": [old_ok, {k: v for k, v in new_fail.items() if k != "created_at"}]})) is None)
    tie_ok = dict(ok_status, created_at="2026-10-06T12:00:00Z")
    tie_fail = dict(ok_status, state="failure", created_at="2026-10-06T12:00:00Z")
    check("a same-second tie goes to the failure (success seen first)",
          find_proof("T1", [("c1", "T1"), ("c2", "T1")], table({"c1": [tie_ok], "c2": [tie_fail]})) is None)
    check("a same-second tie goes to the failure (failure seen first)",
          find_proof("T1", [("c1", "T1"), ("c2", "T1")], table({"c1": [tie_fail], "c2": [tie_ok]})) is None)
    check("a failure by someone else does not cancel the owner's success",
          find_proof("T1", commits, table({"c2": [old_ok, dict(new_fail, creator={"login": "x"})]})) == "c2")

    calls: list[tuple[str, ...]] = []

    def fake(statuses_json: str, dirty: bool = False, fail_gh: bool = False) -> Run:
        def run(*args: str) -> str:
            calls.append(args)
            if args[:2] == ("git", "status"):
                return " M x\n" if dirty else ""
            if args[:3] == ("git", "rev-parse", "HEAD^{tree}"):
                return "T1\n"
            if args[:2] == ("git", "rev-parse"):
                return "c2\n"
            if args[:2] == ("git", "log"):
                return "c3 T3\nc2 T1\n"
            if args[0] == "gh":
                if fail_gh:
                    raise RuntimeError("gh: boom")
                return statuses_json if "statuses?" in args[2] else ""
            raise AssertionError(args)
        return run

    import contextlib
    import io

    def quiet(fn: Callable[[], int]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn()

    check("verify exits 0 on a matching proof", quiet(lambda: verify("T1", fake(json.dumps([ok_status])))) == 0)
    check("verify exits 1 with none", quiet(lambda: verify("T1", fake("[]"))) == 1)
    check("verify exits 1 (not a crash) when gh fails: the full sweep runs", quiet(lambda: verify("T1", fake("[]", fail_gh=True))) == 1)
    check("verify exits 1 on unparseable output", quiet(lambda: verify("T1", fake("not json"))) == 1)
    calls.clear()
    check("record refuses a dirty worktree", quiet(lambda: record(fake("[]", dirty=True))) == 1)
    check("a refused record posts nothing", not any(c[0] == "gh" for c in calls))
    # F1: the snapshot is taken before the sweep; the tree changing during it must refuse, and what is posted is the snapshot.
    def moving(head: list[str], dirty: list[bool]) -> Run:
        def run(*args: str) -> str:
            calls.append(args)
            if args[:2] == ("git", "status"):
                return " M x\n" if dirty[0] else ""
            if args[:3] == ("git", "rev-parse", "HEAD^{tree}"):
                return head[1] + "\n"
            if args[:2] == ("git", "rev-parse"):
                return head[0] + "\n"
            return ""
        return run
    state = ["c2", "T1"]
    started = snapshot(moving(state, [False]))
    check("the snapshot is the sha and tree at the start", started == ("c2", "T1"))
    for label, head, dirty in (("a commit during the sweep", ["c3", "T3"], [False]),
                               ("an edit to a tracked file during the sweep", ["c2", "T1"], [True]),
                               ("an amend to the same tree under a new sha", ["c3", "T1"], [False])):
        calls.clear()
        check(f"record refuses {label}", quiet(lambda: record(moving(head, dirty), before=started)) == 1)
        check(f"...and posts nothing for {label}", not any(c[0] == "gh" for c in calls))
    calls.clear()
    check("record posts the SNAPSHOT when nothing moved", quiet(lambda: record(moving(["c2", "T1"], [False]), before=started)) == 0)
    check("the post names the snapshot's sha", any(c[0] == "gh" and "statuses/c2" in c[2] for c in calls))
    calls.clear()
    check("record_failure posts a failure for the snapshot's sha and tree", quiet(lambda: record_failure(("c2", "T1"), moving(["c2", "T1"], [False]))) == 0
          and any(c[0] == "gh" and "statuses/c2" in c[2] and "state=failure" in c and "description=tree=T1" in c for c in calls))
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            main(["record"])
        check("sweep_proof has no `record` subcommand a person could run without a sweep", False)
    except SystemExit as e:
        check("sweep_proof has no `record` subcommand a person could run without a sweep", e.code == 2)
    check("snapshot is None on a dirty worktree", snapshot(moving(["c2", "T1"], [True])) is None)
    check("verify turns an unexpected answer into 'the full sweep will run', not a traceback",
          quiet(lambda: verify("T1", fake('{"not": "a list"}'))) == 1)
    calls.clear()
    check("record posts the status on a clean tree", quiet(lambda: record(fake("[]"))) == 0)
    posted = [c for c in calls if c[0] == "gh"]
    check("the post carries the tree and the context",
          len(posted) == 1 and "description=tree=T1" in posted[0] and f"context={CONTEXT}" in posted[0] and "state=success" in posted[0])

    good_release = ("\n  proof:\n    timeout-minutes: 10\n    steps: x\n\n  gates:\n    needs: proof\n    if: needs.proof.outputs.found != 'true'\n"
                    "\n  release:\n    timeout-minutes: 30\n    if: >-\n      github.ref == 'refs/heads/main' && !cancelled() &&\n"
                    "      (needs.gates.result == 'success' ||\n"
                    "       (needs.gates.result == 'skipped' && needs.proof.outputs.found == 'true'))\n"
                    "      python3 scripts/sweep_proof.py verify\n")
    good_gates = ("timeout-minutes: 25\n(github.ref == 'refs/heads/dev') && '--fast' || '--require-slow' --mutation-shards\n"
                  "\n  mutation:\n    strategy:\n      fail-fast: false\n      matrix:\n        shard: [1, 2, 3, 4]\n"
                  '    run: python3 scripts/mutation_check.py --shard "${SHARD}/4"\n'
                  "\n  mutation-coverage:\n    needs: mutation\n    if: ${{ always() }}\n"
                  "    run: python3 scripts/mutation_incremental.py verdict x full\n"
                  "    run: python3 scripts/mutation_check.py --merge-shards d --expect-shards 4\n")
    good_local = "sweep_proof.py verify\nmaintainer_doctor.py --gates-only --require-slow\n"
    check("the good wiring has no problem", check_wiring(good_release, good_gates, good_local) == [])
    for label, mutate in (
        ("gates always runs-or-skips wrongly", lambda r, g, l: (r.replace("!= 'true'", "== 'true'"), g, l)),
        ("release ignores a successful gates", lambda r, g, l: (r.replace("needs.gates.result == 'success'", "true"), g, l)),
        ("release publishes after ANY skipped gates", lambda r, g, l: (r.replace(" && needs.proof.outputs.found == 'true'", ""), g, l)),
        ("release loses !cancelled()", lambda r, g, l: (r.replace("!cancelled()", "true"), g, l)),
        ("the proof job loses its timeout", lambda r, g, l: (r.replace("timeout-minutes: 10", ""), g, l)),
        ("the release job loses its timeout", lambda r, g, l: (r.replace("timeout-minutes: 30", ""), g, l)),
        ("the gates job loses its timeout", lambda r, g, l: (r, g.replace("timeout-minutes: 25", ""), l)),
        ("no proof job runs verify", lambda r, g, l: (r.replace("sweep_proof.py verify", "true"), g, l)),
        ("dev push runs the full sweep", lambda r, g, l: (r, g.replace("'--fast'", "'--require-slow'"), l)),
        ("the release never runs the full sweep", lambda r, g, l: (r, g.replace("'--require-slow'", "'--fast'"), l)),
        ("the full sweep also runs mutation coverage itself", lambda r, g, l: (r, g.replace(" --mutation-shards", ""), l)),
        ("the matrix grows and the shard count does not", lambda r, g, l: (r, g.replace("[1, 2, 3, 4]", "[1, 2, 3, 4, 5]"), l)),
        ("a shard is told it is one of a different N", lambda r, g, l: (r, g.replace('"${SHARD}/4"', '"${SHARD}/3"'), l)),
        ("the summary expects a different N", lambda r, g, l: (r, g.replace("--expect-shards 4", "--expect-shards 3"), l)),
        ("the summary does not need the shards", lambda r, g, l: (r, g.replace("needs: mutation\n", ""), l)),
        ("the summary can be skipped by a failed shard", lambda r, g, l: (r, g.replace("if: ${{ always() }}", ""), l)),
        ("the summary does not read the shards' result", lambda r, g, l: (r, g.replace("mutation_incremental.py verdict", "true"), l)),
        ("the summary does not merge the shards", lambda r, g, l: (r, g.replace("--merge-shards", "--nothing"), l)),
        ("one failed shard cancels the rest", lambda r, g, l: (r, g.replace("fail-fast: false", "fail-fast: true"), l)),
        ("release_local skips the proof lookup", lambda r, g, l: (r, g, l.replace("sweep_proof.py verify", ""))),
        ("release_local drops the full sweep", lambda r, g, l: (r, g, l.replace("maintainer_doctor.py --gates-only --require-slow", ""))),
    ):
        check(f"wiring: {label} is reported", check_wiring(*mutate(good_release, good_gates, good_local)) != [])

    good_weekly = ("schedule:\n  - cron: '17 3 * * 1'\nfail-fast: false\nos: [ubuntu-latest, macos-latest]\n"
                   "--full --shard x\n--expect-shards 4\nmutation_incremental.py verdict\n")
    check("the good weekly has no problem", check_weekly(good_weekly) == [])
    for label, edit in (("no schedule", lambda w: w.replace("schedule:", "")), ("no macOS", lambda w: w.replace("macos-latest", "")),
                        ("no Linux", lambda w: w.replace("ubuntu-latest", "")), ("it skips unchanged guards", lambda w: w.replace("--full", "")),
                        ("it does not verify the shards", lambda w: w.replace("--expect-shards", "")),
                        ("one OS cancels the other", lambda w: w.replace("fail-fast: false", ""))):
        check(f"weekly: {label} is reported", check_weekly(edit(good_weekly)) != [])
    check("weekly: a missing file is reported", check_weekly("") != [])

    for f in failures:
        print(f"FAIL: {f}")
    print(f"sweep_proof selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", nargs="?", choices=("verify", "check-wiring"))
    p.add_argument("--tree", help="verify: the tree to look up (default: HEAD's)")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check-wiring":
        return wiring_gate()
    if a.cmd == "verify":
        return verify(a.tree or head_tree(real_run))
    p.error("a command (verify | check-wiring) or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
