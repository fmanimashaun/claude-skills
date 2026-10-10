#!/usr/bin/env python3
"""Judge one `gh pr ready` against the sweep record for HEAD (#1565). Called by guard-pr-ready.sh only.

Usage: pr_ready_guard.py ARGS. stdin is the PreToolUse JSON payload; ARGS is what followed `gh pr ready` in
the command, echoed back in the refusal. Exit 0 allows; exit 2 refuses, with the reason on stderr.

The record is written by `scripts/project_gates.py` to `<git dir>/rails-flow/sweep/<HEAD sha>.json`. It is
read, never written, here, and nothing in the command's other segments is interpreted (the coordinator's
decision on #1565, in line with epic #1793): a sweep chained before `gh pr ready` in ONE command has not run
when this judges, so it does not count.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SWEEP_DIR = "rails-flow/sweep"
MARKER = "<!-- rails-flow:begin"
EXPLICIT = ("an explicit repository target (-R/--repo/GH_REPO/URL) cannot be matched to a local sweep record; "
            "run `gh pr ready` from the PR's own checkout, after its sweep")
SWEEP_CMD = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_gates.py"'


def git(where: str, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", where, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def sweep_dir(root: str) -> Path | None:
    where = git(root, "rev-parse", "--git-path", SWEEP_DIR)
    if not where:
        return None
    return Path(where) if os.path.isabs(where) else Path(root) / where


def in_force(root: str) -> bool:
    """The repository runs project_gates: a workflow names it, CLAUDE.md carries the rails-flow managed
    marker, or a sweep record directory already exists. Otherwise the hook does not apply (point 4)."""
    wf = Path(root) / ".github" / "workflows"
    for f in sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml")) if wf.is_dir() else []:
        try:
            if "project_gates.py" in f.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    try:
        if MARKER in (Path(root) / "CLAUDE.md").read_text(encoding="utf-8", errors="replace"):
            return True
    except OSError:
        pass
    d = sweep_dir(root)
    return bool(d and d.is_dir())


def refuse(reason: str, args: str) -> int:
    print(f"BLOCKED by rails-flow pr-ready guard: {reason}", file=sys.stderr)
    print("`gh pr ready` needs a GREEN sweep record with zero skips for the current HEAD (#1565). Run these as "
          "TWO separate commands (a sweep chained before it in one command has not run when this is judged):",
          file=sys.stderr)
    print(f"  1. {SWEEP_CMD}", file=sys.stderr)
    print(f"  2. gh pr ready{(' ' + args.strip()) if args.strip() else ''}", file=sys.stderr)
    return 2


def resolve_dir(payload: dict, start: str) -> tuple[str | None, str]:
    """(directory, why-not). The command's own `cd`s are followed by lib/command_cwd.py, as guard-claims does."""
    cmd = str(payload.get("tool_input", {}).get("command", ""))
    helper = Path(__file__).with_name("command_cwd.py")
    try:
        done = subprocess.run([sys.executable, str(helper), "--pr-ready", start], input=cmd,
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"lib/command_cwd.py could not run ({exc})"
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip(), ""
    return None, (done.stderr.strip() or f"lib/command_cwd.py exited {done.returncode}")[:200]


def explicit_target(segment: str, raw: str) -> bool:
    """The PR is named by repository, not by this checkout: its HEAD says nothing about that PR (#1565 review)."""
    words = segment.split()
    if any(w in ("-R", "--repo") or w.startswith(("--repo=", "-R")) for w in words):
        return True
    if re.search(r"(^|[^A-Za-z0-9_])GH_REPO=", raw):
        return True
    return any(re.match(r"https?://\S+/pull/\d+", w.strip("'\"")) for w in words)


def main() -> int:
    args = sys.argv[1] if len(sys.argv) > 1 else ""
    segment = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except ValueError as exc:
        return refuse(f"the hook payload could not be read ({exc}).", args)
    start = str(payload.get("cwd") or os.getcwd())
    if not os.path.isdir(start):
        start = os.getcwd()
    where, why = resolve_dir(payload, start)
    if explicit_target(segment, str(payload.get("tool_input", {}).get("command", ""))):
        roots = {git(d, "rev-parse", "--show-toplevel") for d in (where, start) if d}
        if any(r and in_force(r) for r in roots):
            return refuse(EXPLICIT + ".", args)
        return 0
    if where is None:
        # Which repository the command targets cannot be told. Refuse only where the session's own repository
        # is in force; a project that does not run project_gates is left alone (stated in the hook header).
        root = git(start, "rev-parse", "--show-toplevel")
        if root and in_force(root):
            return refuse(f"which repository this `gh pr ready` targets cannot be told ({why}).", args)
        return 0
    root = git(where, "rev-parse", "--show-toplevel")
    if not root or not in_force(root):
        return 0
    head = git(root, "rev-parse", "HEAD")
    if not head:
        return refuse(f"HEAD of {root} could not be read.", args)
    d = sweep_dir(root)
    if d is None:
        return refuse(f"the git directory of {root} could not be read.", args)
    record = d / f"{head}.json"
    if not record.is_file():
        return refuse(f"no sweep record for HEAD {head[:12]} (looked for {record}).", args)
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        verdict, skips = data["verdict"], data["skips"]
        failed, errored = data.get("failed", "?"), data.get("errored", "?")
        if data["head"] != head:
            return refuse(f"the record {record} names HEAD {str(data['head'])[:12]}, not {head[:12]}.", args)
        if verdict not in ("green", "red") or type(skips) is not int:
            raise ValueError(f"verdict {verdict!r}, skips {skips!r}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return refuse(f"the sweep record {record} is unreadable or malformed ({type(exc).__name__}: {exc}).", args)
    summary = f"record {record}: verdict {verdict}, failed {failed}, errored {errored}, skips {skips}"
    if verdict != "green":
        return refuse(f"the sweep for HEAD {head[:12]} was RED ({summary}).", args)
    if skips != 0:
        return refuse(f"the sweep for HEAD {head[:12]} skipped checks that applied ({summary}).", args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
