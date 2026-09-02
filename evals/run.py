#!/usr/bin/env python3
"""Interim runner for the doctrine-effect benchmark (issue #156).

THIS FILE IS DELIBERATELY DISPOSABLE
------------------------------------
`claude plugin eval` already implements this properly -- `--ablation
with-without` for the baseline arm, `--runs`, `--threshold`, `--json`,
`--max-cost-usd`, HTML reports. It is in early access and unavailable on this
account, so this script covers the gap.

The durable assets are `cases/*/prompt.md`, `gates.py`, and `selftest.py`. When
early access opens, point `claude plugin eval` at `evals/` and delete this file.
Do not grow it into a framework.

WHAT IT MEASURES vs WHAT IT GATES
---------------------------------
Gate:        the deterministic rules in gates.py -- pass/fail, grep/parse only.
Measurement: cost, wall-clock, output tokens, turn count -- recorded, never judged.

Conflating them is how a benchmark gets gamed: "less code" is trivially achieved
by emitting something broken, so volume is only meaningful next to a gate.

VALID vs FAILED
---------------
A run that errored, hit the API's error path, or was blocked by a permission
prompt is INVALID -- excluded from scoring, not counted as a failure. Scoring an
infrastructure problem as a doctrine failure is how you invent a regression.

Stdlib only. Never wired into CI; it costs money and must never gate a release.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gates  # noqa: E402
import scaffold  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
SUITE_PATH = EVALS_DIR / "suite.json"

# File operations only. No Bash and no network: it removes permission prompts
# (which would invalidate runs), removes a large source of nondeterminism, and
# the gates only ever read files, so nothing is lost.
TOOLS = "Read,Write,Edit,Glob,Grep"

# Skills bundled by the rails-stack plugin, per .claude-plugin/marketplace.json.
RAILS_STACK_SKILLS = ("rails-8", "hotwire", "design-system")


@dataclass
class RunRecord:
    case_id: str
    arm: str
    run_index: int
    valid: bool
    passed: bool | None
    findings: list[str] = field(default_factory=list)
    invalid_reason: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    output_tokens: int | None = None
    num_turns: int | None = None
    model: str | None = None
    session_id: str | None = None


def claude_exe() -> str:
    """Resolve the `claude` launcher to a path subprocess can actually execute.

    On Windows npm installs three shims -- `claude` (a POSIX shell script),
    `claude.cmd`, and `claude.ps1`. CreateProcess cannot run the extensionless
    one, so passing the bare string "claude" to subprocess raises
    FileNotFoundError even though the command works fine in a shell.
    `shutil.which` picks the right shim via PATHEXT.
    """
    resolved = shutil.which("claude")
    if resolved is None:
        raise FileNotFoundError(
            "`claude` is not on PATH. Install Claude Code, or use --dry-run."
        )
    return resolved


def load_suite() -> dict:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


def stage_rails_stack(destination: Path) -> Path:
    """Assemble what a user actually installs -- and nothing else.

    rails-stack is declared with `"source": "./"`, i.e. the repo root. Pointing
    --plugin-dir at the root would risk pulling in this repo's `.claude/`
    maintainer tooling, which CLAUDE.md says is explicitly NOT distributed. So we
    stage a clean plugin: plugin.json plus the three bundled skills. That is a
    faithful reproduction of `/plugin marketplace add` output, not a shortcut.
    """
    plugin_root = destination / "rails-stack"
    (plugin_root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin_root / "skills").mkdir(parents=True, exist_ok=True)

    marketplace = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    entry = next(p for p in marketplace["plugins"] if p["name"] == "rails-stack")

    (plugin_root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "rails-stack",
                "version": entry["version"],
                "description": entry["description"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for skill in RAILS_STACK_SKILLS:
        source = REPO_ROOT / "skills" / skill
        if not source.is_dir():
            raise FileNotFoundError(f"expected skill directory missing: {source}")
        shutil.copytree(source, plugin_root / "skills" / skill)
    return plugin_root


def resolve_plugin_dirs(arms: list[str], suite: dict, staging: Path) -> dict[str, Path | None]:
    """Resolve each arm's plugin directory ONCE for the whole sweep.

    Staging per (case, arm) would re-copy into an existing directory and raise
    FileExistsError on the second case. It would also be wasteful: the plugin is
    identical for every run, so build it once and reuse the path.
    """
    resolved: dict[str, Path | None] = {}
    for arm in arms:
        raw = suite["arms"][arm]["plugin_dir"]
        if raw is None:
            resolved[arm] = None
        elif raw == "__staged__":
            resolved[arm] = stage_rails_stack(staging)
        else:
            path = REPO_ROOT / raw
            if not path.is_dir():
                raise FileNotFoundError(f"arm {arm!r} plugin_dir missing: {path}")
            resolved[arm] = path
    return resolved


def build_command(prompt_path: Path, plugin_dir: Path | None, model: str,
                  budget: float | None, exe: str) -> list[str]:
    cmd = [
        exe, "--print",
        "--output-format", "json",
        "--model", model,
        # Exclude user/project/local settings so a run does not inherit whatever
        # plugins or memory the operator happens to have enabled. Without this
        # the benchmark is unreproducible across machines.
        "--setting-sources", "",
        "--no-session-persistence",
        "--permission-mode", "acceptEdits",
        "--tools", TOOLS,
    ]
    if budget is not None:
        cmd += ["--max-budget-usd", f"{budget:.4f}"]
    if plugin_dir is not None:
        cmd += ["--plugin-dir", str(plugin_dir)]
    cmd.append(prompt_path.read_text(encoding="utf-8").strip())
    return cmd


def classify(payload: dict) -> tuple[bool, str | None]:
    """Decide whether a completed invocation produced a scoreable run."""
    if payload.get("is_error"):
        return False, f"claude reported is_error (subtype={payload.get('subtype')})"
    if payload.get("api_error_status"):
        return False, f"api_error_status={payload['api_error_status']}"
    denials = payload.get("permission_denials") or []
    if denials:
        return False, f"{len(denials)} permission denial(s) -- agent was blocked from writing"
    if payload.get("subtype") != "success":
        return False, f"subtype={payload.get('subtype')}"
    return True, None


def execute(cmd: list[str], workspace: Path, timeout: int) -> tuple[dict | None, str | None]:
    try:
        completed = subprocess.run(
            cmd, cwd=workspace, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    except OSError as exc:
        return None, f"failed to launch claude: {exc}"

    stdout = (completed.stdout or "").strip()
    if not stdout:
        return None, f"no stdout (exit {completed.returncode}): {(completed.stderr or '')[:300]}"
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError:
        # `plugin eval`-style gating messages and auth errors arrive as plain text.
        return None, f"unparseable output (exit {completed.returncode}): {stdout[:300]}"


def summarise(records: list[RunRecord]) -> str:
    """Per-(case, arm) pass rate over VALID runs only."""
    buckets: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        buckets.setdefault((record.case_id, record.arm), []).append(record)

    lines = [
        f"{'case':<20} {'arm':<6} {'valid':>5} {'pass':>5} {'rate':>6} "
        f"{'cost$':>8} {'ms':>7} {'out_tok':>8}",
        "-" * 72,
    ]
    for (case_id, arm), runs in sorted(buckets.items()):
        valid = [r for r in runs if r.valid]
        passed = [r for r in valid if r.passed]
        rate = f"{len(passed) / len(valid):.0%}" if valid else "n/a"
        costs = [r.cost_usd for r in valid if r.cost_usd is not None]
        times = [r.duration_ms for r in valid if r.duration_ms is not None]
        toks = [r.output_tokens for r in valid if r.output_tokens is not None]
        lines.append(
            f"{case_id:<20} {arm:<6} {len(valid):>5} {len(passed):>5} {rate:>6} "
            f"{(sum(costs) / len(costs) if costs else 0):>8.4f} "
            f"{(sum(times) // len(times) if times else 0):>7} "
            f"{(sum(toks) // len(toks) if toks else 0):>8}"
        )
    invalid = [r for r in records if not r.valid]
    if invalid:
        lines.append("")
        lines.append(f"{len(invalid)} INVALID run(s) excluded from scoring:")
        for record in invalid[:10]:
            lines.append(f"  {record.case_id}/{record.arm}#{record.run_index}: "
                         f"{record.invalid_reason}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    suite = load_suite()
    defaults = suite["defaults"]

    parser = argparse.ArgumentParser(
        description="Run the doctrine-effect benchmark. COSTS MONEY unless --dry-run.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact commands and run no inference (free)")
    parser.add_argument("--arms", default="none,weak,real",
                        help="comma-separated subset of arms (default: all three)")
    parser.add_argument("--case", action="append", dest="cases", default=None,
                        help="case id to run (repeatable; default: all)")
    parser.add_argument("--runs", type=int, default=defaults["runs"])
    parser.add_argument("--model", default=defaults["model"])
    parser.add_argument("--timeout", type=int, default=defaults["timeout_seconds"])
    parser.add_argument("--per-run-budget-usd", type=float, default=None,
                        help="hard per-run ceiling passed to claude --max-budget-usd")
    parser.add_argument("--max-total-usd", type=float, default=None,
                        help="REQUIRED for live runs: abort the sweep once "
                             "accumulated cost exceeds this")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--keep-workspaces", action="store_true",
                        help="preserve each run's workspace for inspection")
    args = parser.parse_args(argv[1:])

    # The README said "always pass --max-total-usd" and the code merely hoped you
    # would. A rule enforced only in prose is the exact failure this repo keeps
    # relearning: put the guarantee in the deterministic layer. Forgetting the cap
    # on a 3-arm sweep is a real, unbounded bill.
    if not args.dry_run and args.max_total_usd is None:
        parser.error(
            "--max-total-usd is required for a live run (this spends real money). "
            "Use --dry-run to preview the sweep for free, or pass an explicit "
            "ceiling, e.g. --max-total-usd 5.00"
        )
    if args.max_total_usd is not None and args.max_total_usd <= 0:
        parser.error("--max-total-usd must be greater than 0")

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in suite["arms"]]
    if unknown:
        parser.error(f"unknown arm(s) {unknown}; known: {sorted(suite['arms'])}")

    cases = suite["cases"]
    if args.cases:
        wanted = set(args.cases)
        cases = [c for c in cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in cases}
        if missing:
            parser.error(f"unknown case id(s): {sorted(missing)}")

    # --dry-run must work on a machine without Claude Code installed, so the
    # launcher is only resolved when we actually intend to invoke it.
    try:
        exe = claude_exe() if not args.dry_run else "claude"
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    staging = Path(tempfile.mkdtemp(prefix="bench-plugins-"))
    try:
        plugin_dirs = resolve_plugin_dirs(arms, suite, staging)
    except FileNotFoundError as error:
        shutil.rmtree(staging, ignore_errors=True)
        print(f"error: {error}", file=sys.stderr)
        return 2

    records: list[RunRecord] = []
    total_cost = 0.0
    started = time.time()

    print(f"arms={arms} cases={[c['id'] for c in cases]} runs={args.runs} "
          f"model={args.model}"
          f"{'  [DRY RUN -- no inference, no cost]' if args.dry_run else ''}\n")

    try:
        for case in cases:
            prompt_path = EVALS_DIR / case["prompt"]
            if not prompt_path.is_file():
                print(f"error: missing prompt {prompt_path}", file=sys.stderr)
                return 2
            for arm in arms:
                plugin_dir = plugin_dirs[arm]
                for run_index in range(1, args.runs + 1):
                    if (args.max_total_usd is not None
                            and total_cost >= args.max_total_usd):
                        print(f"\nbudget reached (${total_cost:.4f} >= "
                              f"${args.max_total_usd:.4f}) -- stopping early")
                        raise KeyboardInterrupt

                    workspace = scaffold.build()
                    cmd = build_command(prompt_path, plugin_dir, args.model,
                                        args.per_run_budget_usd, exe)

                    if args.dry_run:
                        print(f"{case['id']}/{arm}#{run_index}")
                        print(f"  cwd: {workspace}")
                        print(f"  cmd: {' '.join(cmd[:-1])} <prompt>")
                        print(f"  gates: {', '.join(case['rules'])}")
                        records.append(RunRecord(case["id"], arm, run_index,
                                                 valid=False, passed=None,
                                                 invalid_reason="dry run"))
                        if not args.keep_workspaces:
                            shutil.rmtree(workspace, ignore_errors=True)
                        continue

                    payload, launch_error = execute(cmd, workspace, args.timeout)
                    if payload is None:
                        records.append(RunRecord(case["id"], arm, run_index,
                                                 valid=False, passed=None,
                                                 invalid_reason=launch_error))
                        print(f"{case['id']}/{arm}#{run_index}: INVALID -- {launch_error}")
                        if not args.keep_workspaces:
                            shutil.rmtree(workspace, ignore_errors=True)
                        continue

                    valid, reason = classify(payload)
                    usage = payload.get("usage") or {}
                    record = RunRecord(
                        case_id=case["id"], arm=arm, run_index=run_index,
                        valid=valid, passed=None, invalid_reason=reason,
                        cost_usd=payload.get("total_cost_usd"),
                        duration_ms=payload.get("duration_ms"),
                        output_tokens=usage.get("output_tokens"),
                        num_turns=payload.get("num_turns"),
                        model=args.model,
                        session_id=payload.get("session_id"),
                    )
                    total_cost += record.cost_usd or 0.0

                    if valid:
                        passed, findings = gates.run_rules(workspace, case["rules"])
                        record.passed = passed
                        record.findings = [str(f) for f in findings]
                        status = "PASS" if passed else "FAIL"
                        print(f"{case['id']}/{arm}#{run_index}: {status} "
                              f"(${record.cost_usd or 0:.4f}, "
                              f"{record.duration_ms or 0}ms, "
                              f"{len(findings)} finding(s))")
                    else:
                        print(f"{case['id']}/{arm}#{run_index}: INVALID -- {reason}")

                    records.append(record)
                    if args.keep_workspaces:
                        print(f"    workspace: {workspace}")
                    else:
                        shutil.rmtree(workspace, ignore_errors=True)
    except KeyboardInterrupt:
        print("\ninterrupted -- writing partial results")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print()
    print(summarise(records))

    if args.dry_run:
        print("\ndry run complete -- nothing was executed and nothing was spent.")
        return 0

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(started))
    out_dir = Path(args.output_dir) if args.output_dir else EVALS_DIR / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    # Conditions are part of the result. A number without them is not evidence.
    (out_dir / "aggregate-result.json").write_text(
        json.dumps(
            {
                "generated_at_utc": stamp,
                "conditions": {
                    "model": args.model,
                    "runs_per_case": args.runs,
                    "arms": arms,
                    "tools": TOOLS,
                    "max_total_usd": args.max_total_usd,
                    "per_run_budget_usd": args.per_run_budget_usd,
                    "timeout_seconds": args.timeout,
                    # The CLI exposes no --max-turns, so turn count is MEASURED
                    # (see runs[].num_turns) and not capped. Spend is bounded by
                    # the budget ceilings and the per-run timeout instead.
                    "turn_cap": None,
                    "claude_version": subprocess.run(
                        [exe, "--version"], capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                    ).stdout.strip() or "unknown",
                    "marketplace_version": json.loads(
                        (REPO_ROOT / ".claude-plugin" / "marketplace.json")
                        .read_text(encoding="utf-8")
                    )["metadata"]["version"],
                },
                "total_cost_usd": round(total_cost, 4),
                "runs": [asdict(r) for r in records],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out_dir / 'aggregate-result.json'}  "
          f"(total ${total_cost:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
