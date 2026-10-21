#!/usr/bin/env python3
"""Say which of the detected stack's tools are missing, with the steps to get each one (#2168). Advisory.

Each stack declares what a project of it needs in its descriptor's `toolchain` block (`stacks.json`): the Claude Code plugins
(`name@marketplace`, and the line that installs it) and the CLIs (a binary on PATH, the line that installs it, and optionally a
`ready` command that exits 0 only when the tool is usable, such as Docker's daemon answering). This script names no stack: it
asks the detector which stacks matched and reads their blocks, so a new stack adds its tools without editing this file.

A plugin counts as present when it is ENABLED: the documented record is the `enabledPlugins` key of the settings files, read
here at user (`~/.claude/settings.json`), project (`.claude/settings.json`) and local (`.claude/settings.local.json`) scope, the
most specific scope that names it winning. `installed_plugins.json` is not documented, so it is not read (#2168 verification).

Exit: 0 every declared tool is present and ready
      1 something is missing or not ready (each on its own line, with the steps)
      2 cannot judge: the stack could not be detected, or a settings file could not be read. Never folded into 0.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import detect_stack  # noqa: E402

READY_TIMEOUT = 20  # seconds: a readiness probe that hangs is "not ready", never a pass


def settings_files(project: Path, home: Path) -> list[Path]:
    """The settings files that hold `enabledPlugins`, least specific first, so a later one overrides an earlier one."""
    return [home / ".claude" / "settings.json", project / ".claude" / "settings.json", project / ".claude" / "settings.local.json"]


def enabled_plugins(project: Path, home: Path) -> tuple[dict[str, bool], list[str]]:
    """`{id: enabled}` with the most specific scope winning, and the problems met reading the files."""
    state: dict[str, bool] = {}
    problems: list[str] = []
    for path in settings_files(project, home):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as err:
            problems.append(f"{path}: cannot be read: {err}")
            continue
        value = data.get("enabledPlugins") if isinstance(data, dict) else None
        if value is None:
            continue
        if not isinstance(value, dict):
            problems.append(f"{path}: enabledPlugins is not an object")
            continue
        for plugin_id, on in value.items():
            if isinstance(on, bool):
                state[plugin_id] = on
    return state, problems


def ready(command: list[str]) -> tuple[bool, str]:
    """Run a readiness probe: ready only on exit 0 within the timeout."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=READY_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {READY_TIMEOUT}s"
    except OSError as err:
        return False, str(err)
    return done.returncode == 0, f"exit {done.returncode}"


def audit(project: Path, home: Path, dirs: list[Path] | None = None) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes). A finding is something missing, with its steps; a note says what was checked."""
    code, report = detect_stack.run(project, dirs if dirs is not None else detect_stack.manifest_dirs(Path(__file__).resolve()))
    if code == 2:
        return 2, [f"cannot judge the stack: {p}" for p in report.get("problems") or []], []
    blocks = report.get("toolchain") or []
    if not blocks:
        stacks = ", ".join(s["id"] for s in report.get("stacks") or []) or "none detected"
        return 0, [], [f"no detected stack declares a toolchain (stacks: {stacks}); nothing to check"]
    enabled, problems = enabled_plugins(project, home)
    if problems:
        return 2, [f"cannot read which plugins are enabled: {p}" for p in problems], []
    findings: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        label = f"{block['plugin']}:{block['stack']}"
        for row in block.get("plugins") or []:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            if enabled.get(row["id"]):
                notes.append(f"ok   plugin {row['id']} is enabled ({label})")
            else:
                why = "is disabled" if row["id"] in enabled else "is not enabled"
                findings.append(f"MISSING plugin {row['id']} {why} ({label}): {row['install']}, then restart Claude Code")
        for row in block.get("clis") or []:
            if row["bin"] in seen:
                continue
            seen.add(row["bin"])
            if not shutil.which(row["bin"]):
                findings.append(f"MISSING cli {row['bin']} is not on PATH ({label}): {row['install']}")
                continue
            if row.get("ready"):
                ok, how = ready(row["ready"])
                if not ok:
                    findings.append(f"NOT READY cli {row['bin']}: `{' '.join(row['ready'])}` failed ({how}) ({label}): {row['ready_hint']}")
                    continue
            notes.append(f"ok   cli {row['bin']} ({label})")
    return (1 if findings else 0), findings, notes


def selftest() -> int:
    import os
    import tempfile
    bad = 0

    def case(ok: bool, message: str) -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL {message}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plug = root / "plugins" / "tc"
        (plug / ".claude-plugin").mkdir(parents=True)
        (plug / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        bindir = root / "bin"
        bindir.mkdir()
        for name, rc in (("okcli", 0), ("downcli", 1)):
            (bindir / name).write_text(f"#!/bin/sh\nexit {rc}\n", encoding="utf-8")
            (bindir / name).chmod(0o755)
        toolchain = {"plugins": [{"id": "tc-stack@m", "install": "/plugin install tc-stack@m"},
                                 {"id": "extra@official", "install": "/plugin install extra@official"}],
                     "clis": [{"bin": "okcli", "install": "get okcli", "ready": ["okcli"], "ready_hint": "log in to okcli"},
                              {"bin": "downcli", "install": "get downcli", "ready": ["downcli"], "ready_hint": "start downcli"},
                              {"bin": "absentcli", "install": "brew install absentcli"}]}
        (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
            {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
        home, proj = root / "home", root / "proj"
        (home / ".claude").mkdir(parents=True)
        (proj / ".claude").mkdir(parents=True)
        (proj / "marker.txt").write_text("x", encoding="utf-8")
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
        try:
            def run_with(user: dict | None, project: dict | None, local: dict | None):
                for path, data in ((home / ".claude" / "settings.json", user), (proj / ".claude" / "settings.json", project),
                                   (proj / ".claude" / "settings.local.json", local)):
                    if data is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_text(json.dumps(data), encoding="utf-8")
                return audit(proj, home, [plug])

            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            text = "\n".join(findings)
            case(rc == 1, f"a missing tool is exit 1: rc={rc}")
            case("MISSING plugin extra@official is not enabled" in text and "/plugin install extra@official" in text,
                 f"a plugin no settings file enables is flagged with its install line: {findings}")
            case("MISSING cli absentcli is not on PATH" in text and "brew install absentcli" in text,
                 f"a CLI not on PATH is flagged with its install line: {findings}")
            case("NOT READY cli downcli" in text and "start downcli" in text,
                 f"a CLI whose ready check fails is flagged with its hint: {findings}")
            case(not any("okcli" in f for f in findings) and any("ok   cli okcli" in n for n in notes),
                 f"a present, ready CLI is not flagged: {findings} {notes}")
            case(not any("tc-stack@m" in f for f in findings), f"a plugin the user scope enables is not flagged: {findings}")
            rc, findings, _ = run_with({"enabledPlugins": {"tc-stack@m": True, "extra@official": True}},
                                       {"enabledPlugins": {"tc-stack@m": False}}, None)
            case(any("tc-stack@m is disabled" in f for f in findings), f"a project scope that disables a user plugin wins: {findings}")
            rc, findings, _ = run_with({"enabledPlugins": {"tc-stack@m": True, "extra@official": True}},
                                       {"enabledPlugins": {"tc-stack@m": False}}, {"enabledPlugins": {"tc-stack@m": True}})
            case(not any("tc-stack@m" in f for f in findings), f"the local scope wins over the project scope: {findings}")
            (home / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
            rc, findings, _ = audit(proj, home, [plug])
            case(rc == 2 and "cannot read which plugins are enabled" in "\n".join(findings),
                 f"an unreadable settings file is exit 2, not a list of missing plugins: rc={rc} {findings}")
            (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": ["tc-stack@m"]}), encoding="utf-8")
            rc, findings, _ = audit(proj, home, [plug])
            case(rc == 2, f"an enabledPlugins that is not an object is exit 2: rc={rc} {findings}")
            (bindir / "absentcli").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (bindir / "absentcli").chmod(0o755)
            (bindir / "downcli").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True, "extra@official": True}}, None, None)
            case(rc == 0 and not findings, f"everything present and ready is exit 0: rc={rc} {findings}")
            (proj / "marker.txt").unlink()
            rc, findings, notes = audit(proj, home, [plug])
            case(rc == 0 and not findings and "nothing to check" in "\n".join(notes),
                 f"a project no toolchain stack matches has nothing to check: rc={rc} {notes}")
            rc, findings, _ = audit(root / "no-such-project", home, [plug])
            case(rc == 2, f"a project that cannot be judged is exit 2, never 0: rc={rc} {findings}")
        finally:
            os.environ["PATH"] = old_path
    print(f"stack_toolchain selftest: {'FAILED ' + str(bad) if bad else 'all'} cases {'failed' if bad else 'pass'}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=".", help="the project to audit (default: .)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    code, findings, notes = audit(Path(args.project).resolve(), Path.home())
    for line in [*notes, *findings]:
        print(line)
    if code == 0 and not findings:
        print("toolchain: every tool the detected stack declares is present")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
