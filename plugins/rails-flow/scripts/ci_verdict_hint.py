#!/usr/bin/env python3
"""Put `ci_verdict.py` in front of a session the moment it reads a red CI result (#1173).

Run:  python3 ci_verdict_hint.py < hook-payload.json     # what the hook does
      python3 ci_verdict_hint.py --selftest

WHY THIS EXISTS. `ci_verdict.py` (#1077) answers the one question a `failure` conclusion cannot: did
the suite run and fail, or did no runner ever start? It answers correctly. On 2026-09-22 it went
unused for about four hours while two sessions diagnosed ten BLOCKED pull requests on a repository
whose Actions billing had lapsed -- every job `failure`, every job `steps=0` -- and one of them told
the maintainer the red was real. Both sessions had typed `gh pr checks` into a shell. The tool was
reachable only from the claim-verifier agent and `/rails-flow:pr-comments`, so the moment the
mistake was made was the one moment nothing fired. A sentence in a skill already said all of this.

WHAT IT DOES. Reads the hook payload for a finished Bash call. When the command reads CI results AND
its output shows a failing one, it adds ONE line of context naming `ci_verdict.py`. Otherwise it is
silent. It never runs the verdict itself (a network call on every red `gh pr checks` is a latency and
rate-limit cost no advisory should impose) and it never guesses the cause -- billing, a quota and a
downed self-hosted pool look identical from outside, which is `ci_verdict.py`'s own stated boundary.

TWO EVENTS, AND THE REASON IS MEASURED. A Bash call that exits non-zero fires `PostToolUseFailure`,
not `PostToolUse`: in one session's transcript, PostToolUse was recorded on 2348 of 2348 successful
Bash calls and on 0 of 43 failed ones. Plain `gh pr checks <n>` exits 1 when a check fails -- the
exact case this exists for -- while `--json`, `gh run list` and `gh run view` exit 0. So the text to
read is `tool_response.stdout`/`stderr` on one event and `error` on the other. The `error` shape is
taken from the official `claude-security` plugin, which parses `Exit code N` from it; the hooks
documentation is silent on that event's payload and on whether it honours `additionalContext`.

ADVISORY, SO IT FAILS OPEN. Under `docs/doctrine/harness-doctrine.md` section 5: if a model ignores
this line the cost is a wrong diagnosis, not a broken repository. Any error here -- unreadable
payload, an unexpected shape -- exits 0 and prints nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Commands that read a CI conclusion. `gh pr view` only when it asks for the check rollup: a plain
# `gh pr view` prints a description, and a description may say "failure" in prose.
CI_READ = re.compile(
    r"\bgh\s+(?:"
    r"pr\s+checks\b"
    r"|run\s+(?:list|view|watch)\b"
    r"|pr\s+view\b[^|;&]*\b(?:statusCheckRollup|checks)\b"
    r"|api\b[^|;&]*\b(?:check-runs|check-suites|actions/runs)\b"
    r")"
)

# Already measuring the thing this points at: say nothing, or the one session doing it right is
# nagged for it.
ALREADY = re.compile(r"ci_verdict(?:\.py)?\b")
STEP_COUNT = re.compile(r"\bsteps\s*=\s*\d|\bdid-not-run\b|steps\|length")

# A failing conclusion, in each rendering `gh` actually emits. Every pattern is anchored to a
# field boundary so a passing row, or the word "fail" inside a check NAME, cannot match it.
FAILING = re.compile(
    r"(?:^|\t)fail(?:\t|$)"                                   # gh pr checks          name<TAB>fail<TAB>
    r"|\"(?:state|conclusion|bucket)\"\s*:\s*\"(?:FAILURE|failure|fail)\""  # --json forms
    r"|^completed\tfailure\t"                                 # gh run list (non-tty)
    r"|^X\s+\S"                                               # gh run view           X lint in 5s
    r"|\bconclusion=failure\b",
    re.M,
)

HINT = (
    "A `failure` conclusion cannot tell a suite that ran and failed from a runner that never "
    "started (Actions billing, a spending limit, a quota) — `gh` prints the same word for both. "
    "Before classifying this as a test failure, run: {cmd}"
)


def verdict_command(command: str) -> str:
    """The `ci_verdict.py` invocation to suggest, carrying the repository the reader asked about."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or "${CLAUDE_PLUGIN_ROOT}"
    repo = re.search(r"(?:-R|--repo)[=\s]+([\w.-]+/[\w.-]+)", command)
    flag = f" -R {repo.group(1)}" if repo else ""
    return f'python3 "{root}/scripts/ci_verdict.py"{flag} --limit 10'


def output_text(payload: dict) -> str:
    """The tool's visible output, from whichever event delivered it."""
    parts: list[str] = []
    response = payload.get("tool_response")
    if isinstance(response, dict):
        parts += [str(response.get(k) or "") for k in ("stdout", "stderr")]
    elif isinstance(response, str):
        parts.append(response)
    error = payload.get("error")
    if error:
        parts.append(str(error))
    return "\n".join(parts)


def hint_for(payload: dict) -> str | None:
    """The context line to add, or None to stay silent."""
    if payload.get("tool_name") not in (None, "Bash"):
        return None
    tool_input = payload.get("tool_input")
    command = str(tool_input.get("command", "")) if isinstance(tool_input, dict) else ""
    if not CI_READ.search(command) or ALREADY.search(command):
        return None
    text = output_text(payload)
    if STEP_COUNT.search(text) or not FAILING.search(text):
        return None
    return HINT.format(cmd=verdict_command(command))


def run(raw: str) -> str:
    """Hook stdout for one payload: the JSON context object, or nothing."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    line = hint_for(payload)
    if line is None:
        return ""
    event = payload.get("hook_event_name") or "PostToolUse"
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": line}})


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def success(command: str, stdout: str) -> str:
        return run(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                               "tool_input": {"command": command},
                               "tool_response": {"stdout": stdout, "stderr": "", "exit_code": 0}}))

    def failure(command: str, output: str, code: int = 1) -> str:
        return run(json.dumps({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                               "tool_input": {"command": command},
                               "error": f"Exit code {code}\n{output}", "is_interrupt": False}))

    # REAL OUTPUT, captured 2026-09-22 from a repository whose runners never started. One canonical
    # tidy form would miss the renderings the data actually arrives in, so each is `gh`'s own.
    PLAIN_FAIL = (
        "architecture-graph\tfail\t8s\thttps://github.com/o/r/actions/runs/1/job/1\t\n"
        "doctrine\tfail\t9s\thttps://github.com/o/r/actions/runs/1/job/2\t\n"
        "test\tfail\t8s\thttps://github.com/o/r/actions/runs/1/job/3\t\n"
        "GitGuardian Security Checks\tpass\t1s\thttps://dashboard.gitguardian.com\t\n")
    PLAIN_PASS = (
        "AccessLint\tpass\t0\t\tReview complete\n"
        "Analyze (python)\tpass\t1m13s\thttps://github.com/o/r/actions/runs/2/job/1\t\n"
        "gates\tpass\t1m10s\thttps://github.com/o/r/actions/runs/2/job/2\t\n")
    JSON_FAIL = '[{"name":"test","state":"FAILURE"},{"name":"lint","state":"FAILURE"}]'
    JSON_PASS = '[{"name":"test","state":"SUCCESS"},{"name":"lint","state":"SUCCESS"}]'
    LIST_FAIL = "completed\tfailure\tRe-cut the floor (#581)\tCI\tdev\tpush\t35770364031\t8s\t2026-09-22T18:55:06Z\n"
    LIST_PASS = "completed\tsuccess\tMerge pull request #1171\tGates\tdev\tpush\t35766636194\t12m8s\t2026-09-22T18:21:41Z\n"
    VIEW_FAIL = ("\nX dev CI o/r#2 · 35770364031\nTriggered via push about 12 minutes ago\n\n"
                 "JOBS\nX lint in 5s (ID 106890231185)\nX test in 4s (ID 106890231462)\n")
    VIEW_PASS = ("\n✓ dev Gates o/r#9 · 35766636194\nTriggered via push\n\n"
                 "JOBS\n✓ gates in 12m8s (ID 1)\n")

    # 1. THE CASE THIS EXISTS FOR. Plain `gh pr checks` exits 1 on a failing check, so it arrives
    #    as PostToolUseFailure with the text in `error` -- a hook reading only `tool_response`
    #    would be silent in exactly this case.
    out = failure("gh pr checks 580", PLAIN_FAIL)
    check("plain `gh pr checks` with a failing check, via PostToolUseFailure, adds the hint",
          "ci_verdict.py" in out, repr(out[:120]))
    check("...under the event it arrived on, so the harness attributes it correctly",
          '"hookEventName": "PostToolUseFailure"' in out, repr(out[:120]))
    check("...as additionalContext, the documented channel Claude reads",
          '"additionalContext"' in out, repr(out[:120]))

    # 2. Each exit-0 rendering, via PostToolUse and `tool_response.stdout`.
    for label, cmd, text in (("--json", "gh pr checks 580 --json name,state", JSON_FAIL),
                             ("run list", "gh run list --limit 5", LIST_FAIL),
                             ("run view", "gh run view 35770364031", VIEW_FAIL)):
        check(f"failing `{label}` output adds the hint", "ci_verdict.py" in success(cmd, text))

    # 3. THE NEGATIVE CASES, one per rendering, on the SAME commands -- a control for every positive
    #    above, or "it fires" could be a pattern that fires on everything.
    for label, cmd, text in (("plain", "gh pr checks 1172", PLAIN_PASS),
                             ("--json", "gh pr checks 1172 --json name,state", JSON_PASS),
                             ("run list", "gh run list --limit 5", LIST_PASS),
                             ("run view", "gh run view 35766636194", VIEW_PASS)):
        check(f"all-passing `{label}` output is silent", success(cmd, text) == "",
              repr(success(cmd, text)[:80]))

    # 4. A failing-looking output from a command that does not read CI is not this hook's business:
    #    rspec prints "failures", a log prints "fail". Keyed on the command, never the words alone.
    check("a non-CI command whose output says `fail` is silent",
          failure("bundle exec rspec", "test\tfail\t8s\t\n3 examples, 1 failure") == "")
    check("a plain `gh pr view` (a description, not checks) is silent",
          success("gh pr view 580", PLAIN_FAIL) == "")
    check("but `gh pr view --json statusCheckRollup` reads checks and does fire",
          "ci_verdict.py" in success("gh pr view 580 --json statusCheckRollup", JSON_FAIL))

    # 5. Silent for the session already doing it right.
    check("a command that already runs ci_verdict is silent",
          success("gh pr checks 580; python3 ci_verdict.py --limit 5", PLAIN_FAIL) == "")
    check("output that already carries a step count is silent",
          success("gh run list --limit 5", LIST_FAIL + "[did-not-run] steps=0\n") == "")

    # 6. A check NAMED like a failure must not read as one: the field boundary is what holds that.
    check("a passing check whose NAME contains `fail` is silent",
          success("gh pr checks 9", "failover-drill\tpass\t3s\thttps://x\t\n") == "")

    # 7. The suggestion carries the repository the reader was asking about.
    out = failure("gh pr checks 580 -R fmanimashaun/Retask-platform", PLAIN_FAIL)
    check("`-R owner/repo` is carried into the suggested command",
          "-R fmanimashaun/Retask-platform" in out, repr(out[:160]))

    # 8. FAILS OPEN. An advisory that errors on odd input must say nothing, never crash the call.
    for label, raw in (("not JSON", "not json at all"), ("a JSON list", "[1,2]"), ("empty", ""),
                       ("no tool_input", json.dumps({"hook_event_name": "PostToolUse"}))):
        try:
            check(f"{label} payload is silent, not an exception", run(raw) == "")
        except Exception as exc:  # noqa: BLE001 -- the assertion IS that nothing escapes
            check(f"{label} payload is silent, not an exception", False, repr(exc))

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} ci-verdict-hint assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    out = run(sys.stdin.read())
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
