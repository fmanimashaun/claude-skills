#!/usr/bin/env python3
"""Record, and look up, a full gate sweep that passed on an exact tree (#1635).

Run:  python3 scripts/sweep_proof.py record                 # after a clean full doctor run, on that commit
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

WHAT IT DOES NOT PROVE. Only someone with write access to the repository can post a status, which is
the same trust the owner already places in whoever promotes. A status says the maintainer ran the full
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
    """The sha of a commit with this tree carrying a successful `full-sweep` status for it, else None.

    The status description must name the SAME tree: a status posted on a commit whose tree later
    differs (a rebase reusing nothing, a hand-posted status) does not count."""
    for sha, commit_tree in commits:
        if commit_tree != tree:
            continue
        for s in statuses(sha):
            if s.get("context") == CONTEXT and s.get("state") == "success" and s.get("description") == description(tree):
                return sha
    return None


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
    except (RuntimeError, ValueError) as e:
        print(f"no proof: lookup failed ({e}) — the full sweep will run")
        return 1
    if sha is None:
        print(f"no proof: no commit on dev with tree {tree} carries a passing `{CONTEXT}` status — the full sweep will run")
        return 1
    print(f"proof: tree {tree} passed the full sweep (status `{CONTEXT}` on commit {sha})")
    return 0


def record(run: Run = real_run) -> int:
    if run("git", "status", "--porcelain").strip():
        print("refusing to record: the worktree is not clean, so the sweep did not run on committed bytes", file=sys.stderr)
        return 1
    sha = run("git", "rev-parse", "HEAD").strip()
    tree = head_tree(run)
    run("gh", "api", f"repos/{REPO}/statuses/{sha}", "-f", "state=success", "-f", f"context={CONTEXT}",
        "-f", f"description={description(tree)}")
    print(f"recorded: `{CONTEXT}` on {sha} for tree {tree}")
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
    if "sweep_proof.py verify" not in release_yml:
        out.append("release.yml: the `proof` job must run `sweep_proof.py verify`")
    if "github.ref == 'refs/heads/dev'" not in gates_yml or "'--fast'" not in gates_yml:
        out.append("gates.yml: a push to dev must run --fast")
    if "'--require-slow'" not in gates_yml:
        out.append("gates.yml: every other run (the release's call) must run --require-slow")
    if "sweep_proof.py verify" not in release_local:
        out.append("release_local.sh: it must reuse a proven sweep the way release.yml does (sweep_proof.py verify)")
    if "maintainer_doctor.py --gates-only --require-slow" not in release_local:
        out.append("release_local.sh: it must still run the full sweep when no proof matches")
    return out


def wiring_gate() -> int:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    problems = check_wiring(*(( root / f).read_text(encoding="utf-8") for f in
                              (".github/workflows/release.yml", ".github/workflows/gates.yml", "scripts/release_local.sh")))
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

    ok_status = {"context": CONTEXT, "state": "success", "description": "tree=T1"}
    commits = [("c3", "T3"), ("c2", "T1"), ("c1", "T0")]

    def table(d: dict[str, list[dict]]) -> Callable[[str], list[dict]]:
        return lambda sha: d.get(sha, [])

    check("a passing status on a commit with the tree is found", find_proof("T1", commits, table({"c2": [ok_status]})) == "c2")
    check("no status means no proof", find_proof("T1", commits, table({})) is None)
    check("a status on a commit with a DIFFERENT tree is ignored", find_proof("T1", commits, table({"c3": [ok_status]})) is None)
    check("a failing status is no proof", find_proof("T1", commits, table({"c2": [dict(ok_status, state="failure")]})) is None)
    check("a status for another context is no proof", find_proof("T1", commits, table({"c2": [dict(ok_status, context="ci")]})) is None)
    check("a status whose description names another tree is no proof",
          find_proof("T1", commits, table({"c2": [dict(ok_status, description="tree=T9")]})) is None)

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
    calls.clear()
    check("record posts the status on a clean tree", quiet(lambda: record(fake("[]"))) == 0)
    posted = [c for c in calls if c[0] == "gh"]
    check("the post carries the tree and the context",
          len(posted) == 1 and "description=tree=T1" in posted[0] and f"context={CONTEXT}" in posted[0] and "state=success" in posted[0])

    good_release = ("\n  gates:\n    needs: proof\n    if: needs.proof.outputs.found != 'true'\n"
                    "\n  release:\n    if: >-\n      github.ref == 'refs/heads/main' && !cancelled() &&\n"
                    "      (needs.gates.result == 'success' ||\n"
                    "       (needs.gates.result == 'skipped' && needs.proof.outputs.found == 'true'))\n"
                    "      python3 scripts/sweep_proof.py verify\n")
    good_gates = "(github.ref == 'refs/heads/dev') && '--fast' || '--require-slow'"
    good_local = "sweep_proof.py verify\nmaintainer_doctor.py --gates-only --require-slow\n"
    check("the good wiring has no problem", check_wiring(good_release, good_gates, good_local) == [])
    for label, mutate in (
        ("gates always runs-or-skips wrongly", lambda r, g, l: (r.replace("!= 'true'", "== 'true'"), g, l)),
        ("release ignores a successful gates", lambda r, g, l: (r.replace("needs.gates.result == 'success'", "true"), g, l)),
        ("release publishes after ANY skipped gates", lambda r, g, l: (r.replace(" && needs.proof.outputs.found == 'true'", ""), g, l)),
        ("release loses !cancelled()", lambda r, g, l: (r.replace("!cancelled()", "true"), g, l)),
        ("no proof job runs verify", lambda r, g, l: (r.replace("sweep_proof.py verify", "true"), g, l)),
        ("dev push runs the full sweep", lambda r, g, l: (r, g.replace("'--fast'", "'--require-slow'"), l)),
        ("the release never runs the full sweep", lambda r, g, l: (r, g.replace("'--require-slow'", "'--fast'"), l)),
        ("release_local skips the proof lookup", lambda r, g, l: (r, g, l.replace("sweep_proof.py verify", ""))),
        ("release_local drops the full sweep", lambda r, g, l: (r, g, l.replace("maintainer_doctor.py --gates-only --require-slow", ""))),
    ):
        check(f"wiring: {label} is reported", check_wiring(*mutate(good_release, good_gates, good_local)) != [])

    for f in failures:
        print(f"FAIL: {f}")
    print(f"sweep_proof selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", nargs="?", choices=("record", "verify", "check-wiring"))
    p.add_argument("--tree", help="verify: the tree to look up (default: HEAD's)")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "record":
        return record()
    if a.cmd == "check-wiring":
        return wiring_gate()
    if a.cmd == "verify":
        return verify(a.tree or head_tree(real_run))
    p.error("a command (record | verify) or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
