#!/usr/bin/env python3
"""A status line for Claude Code: `5h 34% · 7d 6% · ctx 21% · $1.20 · high · feature-x (wt-name)` (#1829, slice 3 of #1685).

    python3 statusline.py            # reads the status line JSON on stdin, prints ONE line
    python3 statusline.py --selftest

VENDOR IT: a project copies this ONE file to `.claude/scripts/statusline.py` and points `statusLine` at the copy (setup-flow carries the snippet). `${CLAUDE_PLUGIN_ROOT}`
resolves only in a plugin's own hook, monitor, MCP and LSP fields, never in a user's or project's `statusLine` command, so the command cannot name the plugin. The file has
no imports from its siblings and passes `--selftest` alone. The setup-flow snippet runs it as `python3 "$(git rev-parse --show-toplevel)/.claude/scripts/statusline.py"`: the page says a
`statusLine` may be set in project settings and that its command is "a script path or an inline shell command", but not what a relative path is relative to, so the command
finds the repository root itself; a command that fails prints nothing, and the page says a script that exits non-zero or prints nothing blanks the line.

THE INPUT, from https://code.claude.com/docs/en/statusline (read live by `doctrine-verifier` on 2026-10-10, verdict CONFIRMED; registry rows re-read the sentences weekly):
`rate_limits.five_hour` and `rate_limits.seven_day`, each `used_percentage` (0 to 100) and `resets_at` (Unix epoch seconds), present "only for claude.ai Pro and Max subscribers, or
behind a Claude apps gateway that sets a spend limit for you, and only after the first API response in the session", each window possibly absent; `context_window.used_percentage`
("May be `null` early in the session"); `cost.total_cost_usd`; `effort.level` ("Absent when the current model does not support the effort parameter"); `workspace.git_worktree`
("Absent in the main working tree"). Every field is optional here: an absent or null one is left out, and a payload that is not JSON prints nothing and exits 0 (a status line must
never crash or print a traceback into the footer).

A WINDOW THAT HAS RESET IS NO READING (#1854). A session that has had no response since a window reset still holds the old window's figure, which once read 90-96% on a week that
/usage showed at 6%. A window whose `resets_at` is at or before now is left out; one with no usable `resets_at` cannot be shown stale and is kept.

AMBER FROM 80%: a window or the context fill at or past 80 is drawn in amber (ANSI 33) unless `NO_COLOR` is set. The `statusLine` setting that runs it carries `refreshInterval`
(the page: "The minimum is `1`"); setup-flow's snippet uses 30 so the figures stay current while the session is idle.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

AMBER_AT = 80
AMBER = "\033[33m"
RESET = "\033[0m"


def pct(value) -> int | None:
    """A whole percent from a number, or None (bool, string and null are not a percent)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value + 0.5)


def tint(text: str, value: int | None, color: bool) -> str:
    return f"{AMBER}{text}{RESET}" if color and value is not None and value >= AMBER_AT else text


def window(data: dict, kind: str, now: float):
    """`used_percentage` of one rate-limit window, or None when absent or already reset (#1854)."""
    w = (data.get("rate_limits") or {}).get(kind) if isinstance(data.get("rate_limits"), dict) else None
    if not isinstance(w, dict):
        return None
    used = pct(w.get("used_percentage"))
    if used is None:
        return None
    resets = w.get("resets_at")
    if isinstance(resets, (int, float)) and not isinstance(resets, bool) and resets <= now:
        return None
    return used


def branch(cwd: str | None = None) -> str | None:
    """The current git branch of `cwd`, or None (no repository, detached, git missing, or slow)."""
    try:
        done = subprocess.run(["git", "branch", "--show-current"], cwd=cwd or None, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    name = done.stdout.strip()
    return name if done.returncode == 0 and name else None


def cwd_of(data) -> str | None:
    """The session's working directory: `workspace.current_dir`, which the page prefers, else `cwd`; None when neither is a string."""
    if not isinstance(data, dict):
        return None
    ws = data.get("workspace")
    for value in ((ws.get("current_dir") if isinstance(ws, dict) else None), data.get("cwd")):
        if isinstance(value, str) and value:
            return value
    return None


def render(data, now: float, git_branch: str | None, color: bool = True) -> str:
    """The one line, or "" when there is nothing to say."""
    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    for label, kind in (("5h", "five_hour"), ("7d", "seven_day")):
        used = window(data, kind, now)
        if used is not None:
            parts.append(tint(f"{label} {used}%", used, color))
    ctx = pct((data.get("context_window") or {}).get("used_percentage")) if isinstance(data.get("context_window"), dict) else None
    if ctx is not None:
        parts.append(tint(f"ctx {ctx}%", ctx, color))
    cost = (data.get("cost") or {}).get("total_cost_usd") if isinstance(data.get("cost"), dict) else None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        parts.append(f"${cost:.2f}")
    effort = (data.get("effort") or {}).get("level") if isinstance(data.get("effort"), dict) else None
    if isinstance(effort, str) and effort:
        parts.append(effort)
    where = git_branch or ""
    tree = (data.get("workspace") or {}).get("git_worktree") if isinstance(data.get("workspace"), dict) else None
    if isinstance(tree, str) and tree:
        where = f"{where} ({tree})" if where else f"({tree})"
    if where:
        parts.append(where)
    return " · ".join(parts)


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return 0
    line = render(data, time.time(), branch(cwd_of(data)), color="NO_COLOR" not in os.environ)
    if line:
        print(line)
    return 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    NOW = 1_800_000_000
    full = {"rate_limits": {"five_hour": {"used_percentage": 34.2, "resets_at": NOW + 3600}, "seven_day": {"used_percentage": 6, "resets_at": NOW + 86400}},
            "context_window": {"used_percentage": 21}, "cost": {"total_cost_usd": 1.2}, "effort": {"level": "high"}}
    check("the full payload renders every part in order", render(full, NOW, "feature-x", False) == "5h 34% · 7d 6% · ctx 21% · $1.20 · high · feature-x",
          render(full, NOW, "feature-x", False))
    check("a linked worktree is named beside the branch", render({**full, "workspace": {"git_worktree": "wt-1"}}, NOW, "feature-x", False).endswith("feature-x (wt-1)"))
    check("a worktree with no branch is still shown", render({"workspace": {"git_worktree": "wt-1"}}, NOW, None, False) == "(wt-1)")
    check("no worktree field and no branch leaves the location out", "feature" not in render(full, NOW, None, False))
    check("an empty payload prints nothing", render({}, NOW, None, False) == "")
    check("a payload that is not an object prints nothing", render([1, 2], NOW, "x", False) == "" and render("x", NOW, "x", False) == "" and render(None, NOW, None, False) == "")
    # every absent field is left out, never an error
    for key in ("rate_limits", "context_window", "cost", "effort"):
        d = {k: v for k, v in full.items() if k != key}
        out = render(d, NOW, None, False)
        check(f"without {key} the rest still renders", bool(out) and {"rate_limits": "5h", "context_window": "ctx", "cost": "$", "effort": "high"}[key] not in out, out)
    check("a null context percentage (early in a session) is left out", "ctx" not in render({**full, "context_window": {"used_percentage": None}}, NOW, None, False))
    check("a window absent from rate_limits is left out, the other kept", render({"rate_limits": {"seven_day": {"used_percentage": 6}}}, NOW, None, False) == "7d 6%")
    check("rate_limits that is not an object is ignored", render({"rate_limits": "x", "cost": {"total_cost_usd": 2}}, NOW, None, False) == "$2.00")
    check("a percentage that is a string or a bool is not a percent", render({"context_window": {"used_percentage": "21"}, "rate_limits": {"five_hour": {"used_percentage": True}}}, NOW, None, False) == "")
    check("a fractional percentage rounds half up", render({"context_window": {"used_percentage": 23.5}}, NOW, None, False) == "ctx 24%")
    check("cost is two decimals", render({"cost": {"total_cost_usd": 0.5}}, NOW, None, False) == "$0.50" and render({"cost": {"total_cost_usd": 0}}, NOW, None, False) == "$0.00")
    check("a missing or non-string effort is left out", "high" not in render({**full, "effort": {}}, NOW, None, False) and "None" not in render({**full, "effort": {"level": None}}, NOW, None, False))
    # #1854: a window that has already reset is no reading
    expired = {"rate_limits": {"five_hour": {"used_percentage": 96, "resets_at": NOW - 1}, "seven_day": {"used_percentage": 95, "resets_at": NOW}}}
    check("a window whose resets_at has passed is left out (#1854)", render(expired, NOW, None, False) == "", render(expired, NOW, None, False))
    check("a window is expired at exactly resets_at", render({"rate_limits": {"seven_day": {"used_percentage": 95, "resets_at": NOW}}}, NOW, None, False) == "")
    check("a window one second before resets_at is still a reading", render({"rate_limits": {"seven_day": {"used_percentage": 95, "resets_at": NOW + 1}}}, NOW, None, False) == "7d 95%")
    check("a window with no resets_at cannot be shown stale and is kept", render({"rate_limits": {"seven_day": {"used_percentage": 95}}}, NOW, None, False) == "7d 95%")
    check("a window with a non-numeric resets_at cannot be shown stale and is kept", render({"rate_limits": {"seven_day": {"used_percentage": 95, "resets_at": "soon"}}}, NOW, None, False) == "7d 95%")
    # amber from 80%
    amber = render({"rate_limits": {"five_hour": {"used_percentage": 80}}, "context_window": {"used_percentage": 79.4}}, NOW, None, True)
    check("a window at 80% is amber, and 79% is not", amber == f"{AMBER}5h 80%{RESET} · ctx 79%", repr(amber))
    check("the context fill is amber from 80% too", render({"context_window": {"used_percentage": 85}}, NOW, None, True) == f"{AMBER}ctx 85%{RESET}")
    check("with colour off nothing is tinted", "\033" not in render({"context_window": {"used_percentage": 99}}, NOW, None, False))
    check("cost and effort are never tinted", "\033" not in render({"cost": {"total_cost_usd": 99}, "effort": {"level": "max"}}, NOW, None, True))
    # the real git branch of a temp repository
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["git", "init", "-q", "-b", "feat-1", td], check=True, capture_output=True)
        check("the branch is read from the working directory's repository", branch(td) == "feat-1", repr(branch(td)))
    with tempfile.TemporaryDirectory() as td:
        check("a directory that is not a repository has no branch", branch(td) is None)
    check("a directory that does not exist has no branch", branch("/nonexistent-statusline-dir") is None)
    check("the working directory is workspace.current_dir, which the page prefers over cwd", cwd_of({"workspace": {"current_dir": "/a"}, "cwd": "/b"}) == "/a")
    check("cwd is the fallback", cwd_of({"cwd": "/b"}) == "/b" and cwd_of({"workspace": {}, "cwd": "/b"}) == "/b")
    check("no working directory, or one that is not a string, is None", cwd_of({}) is None and cwd_of({"cwd": 3}) is None and cwd_of(None) is None and cwd_of({"cwd": ""}) is None)
    # the entry point: not JSON prints nothing and exits 0
    for bad in ("", "not json", "{"):
        done = subprocess.run([sys.executable, os.path.abspath(__file__)], input=bad, capture_output=True, text=True)
        check(f"stdin {bad!r} prints nothing and exits 0", done.returncode == 0 and done.stdout == "" and done.stderr == "", repr((done.returncode, done.stdout, done.stderr)))
    done = subprocess.run([sys.executable, os.path.abspath(__file__)], input=json.dumps({"context_window": {"used_percentage": 85}}), capture_output=True, text=True,
                          env={**os.environ, "NO_COLOR": "1"})
    check("NO_COLOR turns the colour off", done.returncode == 0 and "\033" not in done.stdout and done.stdout.startswith("ctx 85%"), repr(done.stdout))
    done = subprocess.run([sys.executable, os.path.abspath(__file__)], input=json.dumps({"context_window": {"used_percentage": 85}}), capture_output=True, text=True,
                          env={k: v for k, v in os.environ.items() if k != "NO_COLOR"})
    check("without NO_COLOR the entry point colours an amber figure", AMBER in done.stdout, repr(done.stdout))
    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"statusline selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
