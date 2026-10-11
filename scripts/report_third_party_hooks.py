#!/usr/bin/env python3
"""What the THIRD-PARTY SessionStart hooks on this machine add to every session and every compaction (#1887, slice 5 of #1683).

    python3 scripts/report_third_party_hooks.py            # a table, largest first
    python3 scripts/report_third_party_hooks.py --json
    python3 scripts/report_third_party_hooks.py --selftest

`check_hook_output_budget.py` ratchets OUR SessionStart hooks, because we ship them. The hooks other plugins install fire in the
same sessions and are paid the same way -- again after every compaction -- but we do not ship them, so this is a REPORT for the
maintainer, not a gate: it cannot be made red by a change in this repository, and a gate that goes red for a reason nobody here can
act on gets switched off.

It reads the plugins this user has enabled (`enabledPlugins` in `~/.claude/settings.json`) other than this marketplace's, takes the
newest installed version of each under `~/.claude/plugins/cache/<marketplace>/<plugin>/` (a numbered directory such as 0.33.0;
a commit-hash directory is never taken for a version), and runs each SessionStart command from its `hooks/hooks.json` inside the
same fixed fixture project the ratchet uses, once for EACH source its matcher selects (startup, resume, clear, compact), with
`CLAUDE_PLUGIN_ROOT` set, that source's payload on stdin, a 20-second limit, and its own process group, killed whole on timeout. It measures the bytes printed on stdout -- what the hook injects -- and reports a token estimate at 4
bytes per token (an estimate, labelled as one). It RUNS THIRD-PARTY CODE: only plugins you already enabled, in a temp project.
A hook that fails, times out or needs something the fixture lacks is reported with its status, never as 0 bytes.

WHAT IT CANNOT SEE: a hook whose output depends on state outside the project -- `remember` prints the user's stored memories --
measures what it prints for an EMPTY fixture project. On 2026-10-12 `remember` 0.33.0 printed 550 bytes here, against the ~5.7k
tokens #1683 recorded in a real session on 2026-09-22. Read the figures as a floor, and as a comparison between versions.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OURS = "claude-skills"
BYTES_PER_TOKEN = 4
TIMEOUT = 20
SOURCES = ("startup", "resume", "clear", "compact")   # the SessionStart `source` values a matcher selects among
VERSION = re.compile(r"^\d+(\.\d+)+$")               # 0.33.0, not a commit-hash directory such as 5bf4e7801107


def _version_key(name: str) -> tuple:
    parts = re.findall(r"\d+|[A-Za-z]+", name)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def enabled_plugins(settings: Path) -> list[tuple[str, str]]:
    """(plugin, marketplace) for every enabled plugin that is not this marketplace's."""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for key, on in (data.get("enabledPlugins") or {}).items():
        if on is True and "@" in key:
            plugin, market = key.rsplit("@", 1)
            if market != OURS:
                out.append((plugin, market))
    return sorted(out)


def newest_install(cache: Path, plugin: str, market: str) -> Path | None:
    base = cache / market / plugin
    versions = [d for d in base.iterdir() if d.is_dir()] if base.is_dir() else []
    numbered = [d for d in versions if VERSION.match(d.name)]
    pick = sorted(numbered or versions, key=lambda d: (_version_key(d.name), d.stat().st_mtime))
    return pick[-1] if pick else None


def fires_on(matcher: object) -> tuple[str, ...]:
    """The SessionStart sources an entry's matcher selects: none, "" or "*" means all; otherwise a regex matched in full."""
    if matcher in (None, "", "*"):
        return SOURCES
    try:
        rx = re.compile(str(matcher))
    except re.error:
        return SOURCES
    return tuple(s for s in SOURCES if rx.fullmatch(s))


def session_start_commands(install: Path) -> list[tuple[str, tuple[str, ...]]]:
    """(command, sources it fires on) for each SessionStart command hook."""
    try:
        data = json.loads((install / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(h["command"], fires_on(e.get("matcher"))) for e in data.get("hooks", {}).get("SessionStart", [])
            for h in e.get("hooks", []) if h.get("type", "command") == "command" and h.get("command")]


def run_one(command: str, install: Path, project: Path, source: str = "startup") -> dict:
    """Run one hook for one SessionStart source. It gets its own process group, and a timeout kills the whole group, so a
    grandchild the hook started (a daemon, a backgrounded fetch) is never left running."""
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(install), "CLAUDE_PROJECT_DIR": str(project)}
    payload = json.dumps({"hook_event_name": "SessionStart", "source": source, "cwd": str(project), "session_id": "report"}).encode()
    proc = subprocess.Popen(["bash", "-c", command], cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = proc.communicate(payload, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return {"status": f"timed out after {TIMEOUT}s", "bytes": None}
    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}: {err.decode(errors='replace').strip()[:120]}"
    return {"status": status, "bytes": len(out) if proc.returncode == 0 else None}


def report(settings: Path, cache: Path, project_factory) -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        project = project_factory(Path(td))
        for plugin, market in enabled_plugins(settings):
            install = newest_install(cache, plugin, market)
            if install is None:
                continue
            for cmd, sources in session_start_commands(install):
                for source in sources:
                    rows.append({"plugin": f"{plugin}@{market}", "version": install.name, "source": source, "command": cmd,
                                 **run_one(cmd, install, project, source)})
    return sorted(rows, key=lambda r: -(r["bytes"] or 0))


def _fixture(tmp: Path) -> Path:
    sys.path.insert(0, str(REPO / "scripts"))
    import check_hook_output_budget as ratchet  # the ratchet's own fixed project, so the two reports measure alike
    return ratchet._fixture(tmp)


def selftest() -> int:
    bad: list[str] = []

    def check(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            bad.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        cache = t / "cache"
        marker = t / "orphan-alive"

        def plugin(market, name, version, script, matcher=None):
            d = cache / market / name / version
            (d / "hooks").mkdir(parents=True)
            entry = {"hooks": [{"type": "command", "command": 'bash "${CLAUDE_PLUGIN_ROOT}/s.sh"'}]}
            if matcher is not None:
                entry["matcher"] = matcher
            (d / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"SessionStart": [entry]}}))
            (d / "s.sh").write_text(script)
        plugin("mk", "loud", "0.9.0", "printf old\n")
        plugin("mk", "loud", "0.10.0", "head -c 4000 /dev/zero | tr '\\0' x\n")
        plugin("mk", "loud", "9f3e1c2a7b55", "printf hash-dir\n")            # a commit-hash cache dir must never win
        plugin("mk", "picky", "1.0.0", 'case "$(cat)" in *\"compact\"*) printf cc ;; *) printf startup-text ;; esac\n', "startup|compact")
        plugin("mk", "broken", "1.0.0", "echo nope >&2; exit 3\n")
        plugin("mk", "slow", "1.0.0", f"(sleep 4; touch '{marker}') & sleep 30\n")
        plugin("mk", "off", "1.0.0", "printf zzz\n")
        plugin(OURS, "rails-flow", "1.0.0", "printf ours\n")
        settings = t / "settings.json"
        settings.write_text(json.dumps({"enabledPlugins": {"loud@mk": True, "picky@mk": True, "broken@mk": True, "slow@mk": True,
                                                           "off@mk": False, "rails-flow@" + OURS: True, "missing@mk": True}}))
        global TIMEOUT
        saved, TIMEOUT = TIMEOUT, 2
        try:
            rows = report(settings, cache, lambda p: (p / "proj").mkdir() or (p / "proj"))
        finally:
            TIMEOUT = saved
        by = {(r["plugin"], r["source"]): r for r in rows}
        plugins = {r["plugin"] for r in rows}
        check("report: a disabled plugin, our own marketplace and a plugin not installed are left out",
              plugins == {"loud@mk", "picky@mk", "broken@mk", "slow@mk"}, sorted(plugins))
        loud = by.get(("loud@mk", "startup"), {})
        check("report: the NEWEST numbered version is run (0.10.0 over 0.9.0), never a sha-named dir starting with 9",
              loud.get("version") == "0.10.0", loud)
        check("report: bytes printed on stdout are measured", loud.get("bytes") == 4000, loud)
        check("report: a hook with no matcher fires on all four sources", {s for (p, s) in by if p == "loud@mk"} == set(SOURCES), "")
        check("report: a matcher limits the sources, and each source gets its own payload",
              {s for (p, s) in by if p == "picky@mk"} == {"startup", "compact"}
              and by[("picky@mk", "compact")]["bytes"] == 2 and by[("picky@mk", "startup")]["bytes"] == len("startup-text"),
              {k: v.get("bytes") for k, v in by.items() if k[0] == "picky@mk"})
        broken = by.get(("broken@mk", "startup"), {})
        check("report: a failing hook is reported with its status, never as 0 bytes",
              broken.get("bytes") is None and "exit 3" in broken.get("status", ""), broken)
        slow = by.get(("slow@mk", "startup"), {})
        check("report: a hung hook is stopped and reported, never as 0 bytes",
              slow.get("bytes") is None and "timed out" in slow.get("status", ""), slow)
        import time
        time.sleep(5)
        check("report: a timed-out hook's grandchild is killed with its process group, not orphaned", not marker.exists(), "marker written")
        check("report: largest first", rows[0]["plugin"] == "loud@mk", rows[0])
        totals = per_source(rows)
        check("report: start and compaction are totalled separately",
              totals["startup"] == 4000 + len("startup-text") and totals["compact"] == 4000 + 2, totals)
    for b in bad:
        print(f"FAIL {b}")
    print(f"report_third_party_hooks selftest: {'FAILED ' + str(len(bad)) if bad else 'ok'}")
    return 1 if bad else 0


def per_source(rows: list[dict]) -> dict[str, int]:
    return {src: sum(r["bytes"] or 0 for r in rows if r["source"] == src) for src in SOURCES}


def main() -> int:
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    rows = report(Path.home() / ".claude" / "settings.json", Path.home() / ".claude" / "plugins" / "cache", _fixture)
    if args == ["--json"]:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no enabled third-party plugin declares a SessionStart hook")
        return 0
    totals = per_source(rows)
    print("third-party SessionStart hooks, bytes added per event (~tokens at 4 bytes each, an estimate):")
    for src in SOURCES:
        print(f"  {src:8} {totals[src]:>7} B  ~{totals[src] // BYTES_PER_TOKEN:>5} tok")
    for r in rows:
        size = f"{r['bytes']:>7} B ~{r['bytes'] // BYTES_PER_TOKEN:>5} tok" if r["bytes"] is not None else f"{'?':>7}   {'':>9}"
        print(f"  {size}  {r['source']:8} {r['plugin']} {r['version']}  [{r['status']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
