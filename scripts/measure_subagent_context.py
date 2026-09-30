#!/usr/bin/env python3
"""Measure how large our subagents' transcripts get, from the user's own stored runs (#1505).

The advisor rereads a subagent's whole transcript on every call (*"Each advisor call processes the full
transcript anew, with no reuse between calls"*, https://code.claude.com/docs/en/advisor), so what a call
costs is the subagent's context size. `model-tiers.md` states that size; this makes it re-checkable.

It reads `~/.claude/projects/*/*/subagents/*.jsonl` with its `.meta.json` (`agentType`) and takes, per
run, the PEAK request context: input + cache-read + cache-creation tokens. It needs the user's own
transcripts, so it cannot run in CI and is not a gate -- a maintainer diagnostic, like the corpora.

    python3 scripts/measure_subagent_context.py [--root DIR] [--shipped-only]
    python3 scripts/measure_subagent_context.py --selftest
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def peak_context(transcript: Path) -> int:
    """The largest request context in one run, in tokens; 0 when no line carries usage."""
    peak = 0
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if isinstance(usage, dict):
            peak = max(peak, sum(int(usage.get(k) or 0) for k in
                                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
    return peak


def measure(root: Path) -> dict[str, list[int]]:
    """agentType -> the peak context of each stored run that recorded usage."""
    runs: dict[str, list[int]] = {}
    for meta in sorted(root.glob("*/*/subagents/*.meta.json")):
        transcript = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        try:
            agent = json.loads(meta.read_text(encoding="utf-8")).get("agentType") or "?"
        except (OSError, json.JSONDecodeError):
            continue
        if transcript.is_file() and (peak := peak_context(transcript)):
            runs.setdefault(agent, []).append(peak)
    return runs


def shipped_agents() -> set[str]:
    """`<plugin>:<name>` for every agent this repository ships."""
    return {f"{p.parent.parent.name}:{p.stem}" for p in (REPO / "plugins").glob("*/agents/*.md")}


def report(runs: dict[str, list[int]], only: set[str] | None) -> str:
    rows = sorted(((a, v) for a, v in runs.items() if only is None or a in only),
                  key=lambda av: -statistics.median(av[1]))
    lines = [f"{sum(len(v) for v in runs.values())} stored run(s) with usage; "
             f"{sum(len(v) for _, v in rows)} shown", "",
             "| agent | runs | median peak context | max |", "|---|---:|---:|---:|"]
    lines += [f"| {a} | {len(v)} | {int(statistics.median(v)):,} | {max(v):,} |" for a, v in rows]
    return "\n".join(lines)


def selftest() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sub = root / "proj" / "session" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-a.meta.json").write_text(json.dumps({"agentType": "rails-flow:test-runner"}))
        (sub / "agent-a.jsonl").write_text("\n".join(json.dumps(r) for r in [
            # The peak comes FIRST, so "the last request" and "the peak" disagree.
            {"message": {"usage": {"input_tokens": 5, "cache_read_input_tokens": 200,
                                   "cache_creation_input_tokens": 45}}},
            {"message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": 90}}},
            {"message": "not a dict"}, "{broken",
        ]) + "\nnot json\n")
        (sub / "agent-b.meta.json").write_text(json.dumps({"agentType": "rails-flow:test-runner"}))
        (sub / "agent-b.jsonl").write_text(json.dumps({"message": {"usage": {"input_tokens": 50}}}) + "\n")
        (sub / "agent-c.meta.json").write_text(json.dumps({"agentType": "Explore"}))
        (sub / "agent-c.jsonl").write_text("{}\n")  # no usage: not a run
        runs = measure(root)
        # The PEAK, summing all three fields: 5 + 200 + 45 = 250, not the last line nor one field.
        if runs.get("rails-flow:test-runner") != [250, 50]:
            failures.append(f"peak context summed per request and maximised per run: {runs}")
        if "Explore" in runs:
            failures.append("a run with no usage is not a measurement")
        out = report(runs, {"rails-flow:test-runner"})
        if "| rails-flow:test-runner | 2 | 150 | 250 |" not in out:
            failures.append(f"median and max are reported per agent: {out}")
    if "rails-flow:test-runner" not in shipped_agents():
        failures.append("shipped agents are named <plugin>:<file stem>")
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"measure_subagent_context selftest: {4 - len(failures)} of 4 passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude" / "projects")
    ap.add_argument("--shipped-only", action="store_true", help="only agents this repository ships")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.root.is_dir():
        print(f"no transcripts under {args.root} -- nothing measured, which is not a result", file=sys.stderr)
        return 2
    print(report(measure(args.root), shipped_agents() if args.shipped_only else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
