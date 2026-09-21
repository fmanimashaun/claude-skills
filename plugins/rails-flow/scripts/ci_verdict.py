#!/usr/bin/env python3
"""Tell a CI run that FAILED apart from one that never started (#1077).

Run:  python3 ci_verdict.py                          # this repo, recent runs
      python3 ci_verdict.py -R owner/repo --limit 10
      python3 ci_verdict.py --branch dev --event push
      python3 ci_verdict.py --from runs.json         # judge a recorded payload, no network
      python3 ci_verdict.py --selftest

WHY THIS EXISTS. When GitHub cannot allocate a runner -- Actions billing, a spending limit, a quota
-- it marks every job in the run `failure`. That is the SAME STRING a suite that ran and failed
produces, and the two demand opposite responses: one means fix your diff, the other means your diff
was never tested and the red is not about you.

Measured live while this was written, one API call apart:

    fmanimashaun/claude-skills      conclusion=failure   steps=10    <- ran, really failed
    fmanimashaun/Retask-platform    conclusion=failure   steps=0     <- no runner, 8 runs straight

`conclusion` cannot separate those rows. Nothing in `gh pr checks`, `gh run list` or the checks API
can. It cost two sessions in one morning on one repository: one read three red checks as real,
pushed a fix, saw FIVE red and concluded their change had made things worse -- it had not, the
failure mode had gone from selective (54 steps ran, 3 jobs failed) to total (0 steps ran, all 5
failed instantly), and **the count rose because nothing ran at all**. A second session read
`completed/success` rows that were three days old and reported the repository healthy.

THE DISCRIMINATOR IS THE STEP COUNT, and it is a property of the RUN rather than of whichever job
you happened to open:

    gh api repos/OWNER/REPO/actions/runs/<id>/jobs --jq '[.jobs[].steps|length]|add'

Zero executed steps under a `completed` status means no runner ever picked the work up. There is no
log to read -- which is why `gh run view --log-failed` comes back EMPTY in this state and reads like
a permissions or tooling problem. It is neither; no step wrote a log because no step ran.

WHY NOT THE ANNOTATION. `repos/{owner}/{repo}/check-runs/{id}/annotations` sometimes names the cause
outright ("The job was not started because recent account payments have failed..."). It is better
prose and a worse signal: it needs a check-run id rather than a run id, it is not always readable
with the same token, and it was unreachable on the very runs that produced this issue. It is
reported when present and never depended on.

WHAT THIS DELIBERATELY DOES NOT DO. It does not guess WHY no runner came -- billing, a quota, a
self-hosted pool that is down and an org policy all look identical from here. `did-not-run` is the
finding; the cause is for whoever owns the account. A tool that guessed would be confidently wrong
in a way nobody could check, which is the defect this exists to remove rather than relocate.

EXIT CODES ARE THE POINT, so a caller cannot collapse the two back into one verdict:

    0  every run examined passed (or is still going)
    1  at least one run RAN and failed          -- a finding about the diff
    3  nothing ran                              -- a finding about the ENVIRONMENT, not the diff
    2  bad usage / could not measure

Stdlib only. `--selftest` and `--from` never touch the network.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

# A run that reached `completed` with one of these conclusions AND executed zero steps was never
# picked up. `success` is excluded on purpose: a genuinely successful run with no steps is not a
# thing, and if it ever were, calling it "did not run" would be the flattering error.
NEVER_STARTED_CONCLUSIONS = frozenset({"failure", "cancelled", "startup_failure", "stale", None})

PASSED, FAILED, DID_NOT_RUN, RUNNING = "passed", "failed", "did-not-run", "running"


def verdict(run: dict) -> str:
    """One run's verdict from its status, conclusion and TOTAL executed step count.

    The step count is the whole mechanism. Reading `conclusion` alone is what produced two wrong
    calls in one morning, and no amount of care with the other fields recovers the distinction --
    the string is identical.
    """
    status = (run.get("status") or "").lower()
    conclusion = run.get("conclusion")
    conclusion = conclusion.lower() if isinstance(conclusion, str) else conclusion
    steps = run.get("steps")

    if status != "completed":
        return RUNNING
    if conclusion == "success":
        return PASSED
    # `steps` is None when we could not measure it. That is NOT zero -- an unmeasured run must not
    # be reported as "no runner", which would send someone to their billing page over a real
    # failing suite. Unknown falls back to the conclusion, which is what we had before.
    if steps == 0 and conclusion in NEVER_STARTED_CONCLUSIONS:
        return DID_NOT_RUN
    return FAILED


def classify(runs: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {PASSED: [], FAILED: [], DID_NOT_RUN: [], RUNNING: []}
    for run in runs:
        out[verdict(run)].append(run)
    return out


def _gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout


def step_count(repo: str, run_id: int) -> int | None:
    """Total executed steps across every job, or None when it could not be measured.

    None and 0 are different answers and the difference is load-bearing -- see `verdict()`.
    """
    raw = _gh(["api", f"repos/{repo}/actions/runs/{run_id}/jobs",
               "--jq", "[.jobs[].steps|length]|add"])
    raw = raw.strip()
    if not raw or raw == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def collect(repo: str, limit: int, branch: str | None, event: str | None) -> list[dict]:
    args = ["run", "list", "-R", repo, "--limit", str(limit),
            "--json", "databaseId,conclusion,status,name,event,headBranch,createdAt"]
    if branch:
        args += ["--branch", branch]
    if event:
        args += ["--event", event]
    raw = _gh(args)
    if not raw:
        return []
    runs = json.loads(raw)
    for run in runs:
        run["steps"] = step_count(repo, run["databaseId"])
    return runs


def _describe(run: dict) -> str:
    steps = run.get("steps")
    return (f"{run.get('createdAt', '?')}  {run.get('name', '?')} "
            f"[{run.get('event', '?')}@{run.get('headBranch', '?')}]  "
            f"conclusion={run.get('conclusion')}  steps={'unmeasured' if steps is None else steps}")


def report(runs: list[dict]) -> int:
    if not runs:
        print("NOT APPLICABLE: no runs matched — this check examined nothing.")
        return 2
    buckets = classify(runs)
    for name in (DID_NOT_RUN, FAILED, PASSED, RUNNING):
        for run in buckets[name]:
            print(f"  [{name:<11}] {_describe(run)}")
    print(f"\n{len(runs)} run(s) examined: {len(buckets[PASSED])} passed, "
          f"{len(buckets[FAILED])} failed, {len(buckets[DID_NOT_RUN])} did not run, "
          f"{len(buckets[RUNNING])} still going.")

    if buckets[DID_NOT_RUN]:
        print(
            f"\nENVIRONMENT, NOT THE DIFF — {len(buckets[DID_NOT_RUN])} run(s) completed without "
            f"executing a single step. No runner ever picked the work up (Actions billing, a "
            f"spending limit, a quota, or a self-hosted pool that is down). These are NOT test "
            f"failures: nothing was tested, so the change that triggered them is UNVERIFIED rather "
            f"than broken. `gh run view --log-failed` will come back empty — there is no log "
            f"because no step wrote one. Do not file these against the diff, and do not read a "
            f"rising red count as a regression.")
    if buckets[FAILED]:
        print(f"\n{len(buckets[FAILED])} run(s) really ran and failed — those are about the code.")

    if buckets[FAILED]:
        return 1                      # a real failure is actionable; report it even alongside the other
    return 3 if buckets[DID_NOT_RUN] else 0


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # THE PAIR THE WHOLE TOOL EXISTS FOR. Identical status and conclusion; only `steps` differs,
    # and the verdicts are opposite. Both rows were measured live, one API call apart.
    REAL_FAILURE = {"status": "completed", "conclusion": "failure", "steps": 10,
                    "name": "Gates", "createdAt": "2026-09-21T10:20:21Z"}
    NO_RUNNER = {"status": "completed", "conclusion": "failure", "steps": 0,
                 "name": "CI", "createdAt": "2026-09-21T09:35:50Z"}
    expect("a completed failure that executed steps is a real failure",
           verdict(REAL_FAILURE) == FAILED)
    expect("a completed failure that executed ZERO steps did not run",
           verdict(NO_RUNNER) == DID_NOT_RUN)
    expect("...and the two differ ONLY in the step count",
           {k: v for k, v in REAL_FAILURE.items() if k not in ("steps", "name", "createdAt")}
           == {k: v for k, v in NO_RUNNER.items() if k not in ("steps", "name", "createdAt")})

    expect("a success is a pass", verdict({"status": "completed", "conclusion": "success",
                                           "steps": 24}) == PASSED)
    # A success with no steps is NOT reported as "did not run": there is no such run, and the
    # flattering error would be to invent one.
    expect("a success is a pass even with no step count",
           verdict({"status": "completed", "conclusion": "success", "steps": 0}) == PASSED)
    expect("an in-progress run is neither passed nor failed",
           verdict({"status": "in_progress", "conclusion": None, "steps": 22}) == RUNNING)
    expect("a queued run is not judged",
           verdict({"status": "queued", "conclusion": None, "steps": None}) == RUNNING)

    # UNMEASURED IS NOT ZERO, and this is the assertion that keeps the tool honest when the jobs
    # endpoint is unreadable. Calling it "did not run" would send someone to a billing page over a
    # genuinely failing suite -- the same confident-verdict-over-no-evidence defect, inverted.
    expect("an UNMEASURED step count falls back to the conclusion, it does not claim no runner",
           verdict({"status": "completed", "conclusion": "failure", "steps": None}) == FAILED)

    # A cancelled run with no steps is the same environment story under a different label.
    expect("a cancelled run that executed nothing also did not run",
           verdict({"status": "completed", "conclusion": "cancelled", "steps": 0}) == DID_NOT_RUN)
    expect("a cancelled run that HAD executed steps is a real outcome, not an environment one",
           verdict({"status": "completed", "conclusion": "cancelled", "steps": 31}) == FAILED)

    buckets = classify([REAL_FAILURE, NO_RUNNER, {"status": "completed", "conclusion": "success",
                                                  "steps": 24}])
    expect("classify sorts a mixed batch into three distinct buckets",
           len(buckets[FAILED]) == 1 and len(buckets[DID_NOT_RUN]) == 1
           and len(buckets[PASSED]) == 1)

    # THE EXIT CODES ARE THE CONTRACT. A caller that only checks truthiness must still be unable
    # to collapse "nothing ran" into "something failed".
    import contextlib
    import io
    def code(runs):
        with contextlib.redirect_stdout(io.StringIO()):
            return report(runs)
    expect("nothing ran exits 3 — an ENVIRONMENT finding", code([NO_RUNNER]) == 3)
    expect("a real failure exits 1 — a finding about the diff", code([REAL_FAILURE]) == 1)
    expect("all green exits 0",
           code([{"status": "completed", "conclusion": "success", "steps": 24}]) == 0)
    expect("a real failure alongside a no-runner still exits 1 — the actionable one wins",
           code([NO_RUNNER, REAL_FAILURE]) == 1)
    # Zero runs is NOT a pass. "0 failures over 0 runs" reads exactly like a healthy repository,
    # and reporting a repo healthy from rows that were not there is half of what #1077 cost.
    expect("no runs at all is exit 2, not a clean bill of health", code([]) == 2)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        report([NO_RUNNER])
    text = out.getvalue()
    expect("the no-runner report says it is the environment and not the diff",
           "ENVIRONMENT, NOT THE DIFF" in text and "UNVERIFIED" in text)
    expect("...and warns that --log-failed will be empty rather than broken",
           "no log" in text)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a failure that executed steps and one that executed none get opposite verdicts")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-R", "--repo", default="", help="owner/repo (default: the current repo)")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--branch", default=None)
    ap.add_argument("--event", default=None, help="push / pull_request — the PR run is the fast one")
    ap.add_argument("--from", dest="payload", default=None,
                    help="judge a recorded JSON array instead of calling the API")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    if args.payload:
        with open(args.payload, encoding="utf-8") as handle:
            return report(json.load(handle))

    repo = args.repo
    if not repo:
        repo = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]).strip()
    if not repo:
        print("cannot determine the repository — pass -R owner/repo", file=sys.stderr)
        return 2
    return report(collect(repo, args.limit, args.branch, args.event))


if __name__ == "__main__":
    raise SystemExit(main())
