#!/usr/bin/env python3
"""Say which of the detected stack's tools are missing, with the steps to get each one (#2168). Advisory.

Each stack declares what a project of it needs in its descriptor's `toolchain` block (`stacks.json`): the Claude Code plugins
(`name@marketplace`, and the line that installs it) and the CLIs (a binary on PATH, the line that installs it, and optionally a
`ready` command that exits 0 only when the tool is usable, such as Docker's daemon answering). This script names no stack: it
asks the detector which stacks matched and reads their blocks, so a new stack adds its tools without editing this file.

A plugin counts as present when it is ENABLED: the documented record is the `enabledPlugins` key of the settings files, read
here at user (`~/.claude/settings.json`), project (`.claude/settings.json`) and local (`.claude/settings.local.json`) scope, the
most specific scope that names it winning. `installed_plugins.json` is not documented, so it is not read (#2168 verification).
The project scope is taken at its word, as Claude Code takes it: a project's own `.claude/settings.json` enabling a plugin that is
not installed reads as present here too.

Exit: 0 every declared tool is present and ready
      1 something is missing or not ready (each on its own line, with the steps)
      2 cannot judge: the stack could not be detected, or a settings file could not be read. Never folded into 0.
"""
from __future__ import annotations

import argparse
import re
import json
import os
import subprocess
import sys
import tempfile
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


def inside(path: Path, project: Path) -> bool:
    """Whether `path` lives in `project`, judged by FILE IDENTITY (device and inode), not by spelling: a path string can name the
    project through letter case on a case-insensitive volume, or through an alias such as macOS's /System/Volumes/Data, and
    `resolve()` unifies only symlinks (#2291 adversary)."""
    try:
        root = os.stat(project)
    except OSError:
        return False
    for p in (path, *path.parents):
        try:
            if os.path.samestat(os.stat(p), root):
                return True
        except OSError:
            continue
    return False


# What a version or ready probe inherits: an ALLOWLIST, never the whole environment. direnv or a repository's settings can set
# BASH_ENV, NODE_OPTIONS, RUBYOPT, PYTHONPATH and their kind from the project, and each makes an interpreter load a file before
# the CLI prints anything (#2291 adversary; the same reason the hooks unset them, lib/trusted-env.sh). Docker keeps its own
# connection settings: they choose which daemon answers, not what code runs.
PROBE_ENV_KEYS = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "TERM", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR",
                  "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY")


def probe_env(project: Path) -> tuple[dict[str, str], str]:
    """(environment, working directory) for running a CLI on PATH. Its PATH keeps only absolute entries outside the project, so a
    `#!/usr/bin/env node` script cannot pick up the project's own `node`; the rest of its environment is PROBE_ENV_KEYS and the
    `LC_*` locale only; it runs from a neutral directory, so nothing reads the project's config by being started inside it.
    A project file hard-linked into a global directory is not caught (its parents never meet the project): a clone cannot create
    one, only the user or code already running can."""
    keep = [e for e in os.environ.get("PATH", "").split(os.pathsep) if e and os.path.isabs(e) and not inside(Path(e), project)]
    env = {k: v for k, v in os.environ.items() if k in PROBE_ENV_KEYS or k.startswith("LC_")}
    return {**env, "PATH": os.pathsep.join(keep)}, tempfile.gettempdir()


def ready(command: list[str], env: dict[str, str], cwd: str) -> tuple[bool, str]:
    """Run a readiness probe: ready only on exit 0 within the timeout."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=READY_TIMEOUT, stdin=subprocess.DEVNULL, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {READY_TIMEOUT}s"
    except OSError as err:
        return False, str(err)
    return done.returncode == 0, f"exit {done.returncode}"


def on_path(name: str) -> Path | None:
    """`name` on PATH, resolved through symlinks. Only absolute PATH entries count: a relative one (`.`, `bin`, an empty entry)
    names whatever directory the audit happens to run in, which is the project's own (#2291 review)."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        candidate = Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def locate(row: dict, project: Path) -> tuple[str | None, bool]:
    """(the CLI's path, whether it is the project's own copy). The descriptor's `project_paths` come first, so a global CLI
    never hides the one the project pins; then PATH. Every hit is RESOLVED and judged by where it really lives: anything under
    the project is the project's copy, never executed, however it was reached (a node_modules/.bin that direnv, `npm run` or a
    shell rc put on PATH). A project path that resolves outside the project (a symlink out) is not the project's copy."""
    for rel in row.get("project_paths") or []:
        candidate = (project / rel).resolve()
        if inside(candidate, project) and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate), True
    found = on_path(row["bin"])
    if found:
        return str(found), inside(found, project)
    return None, False


def version(row: dict, path: str, env: dict[str, str], cwd: str) -> str:
    """The first line a CLI on PATH prints for its `version` arguments, or why there is none: reported, never judged."""
    if not row.get("version"):
        return ""
    try:
        done = subprocess.run([path, *row["version"]], capture_output=True, text=True, timeout=READY_TIMEOUT, stdin=subprocess.DEVNULL,
                              env=env, cwd=cwd)
    except (subprocess.TimeoutExpired, OSError) as err:
        return f" (version unknown: {type(err).__name__})"
    first = (done.stdout or done.stderr).strip().splitlines()
    return f" ({first[0][:80]})" if done.returncode == 0 and first else f" (version unknown: exit {done.returncode})"


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
    env, cwd = probe_env(project)
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
            path, in_project = locate(row, project)
            if not path:
                where = " or in the project" if row.get("project_paths") else ""
                findings.append(f"MISSING cli {row['bin']} is not on PATH{where} ({label}): {row['install']}")
                continue
            if in_project:
                # A diagnostic never runs what the repository ships: node_modules/.bin in a cloned project can be anything, so
                # its copy is reported present and is not executed for its version or a ready check (#2168 security review).
                notes.append(f"ok   cli {row['bin']} at {os.path.relpath(path, project.resolve())} (the project's own copy: not run) ({label})")
                continue
            if row.get("ready"):
                probe = Path(path) if row["ready"][0] == row["bin"] else on_path(row["ready"][0])
                if probe is None or inside(probe, project):
                    # the probe binary is missing from PATH, or is the project's own: it is not run, so readiness is unknown
                    findings.append(f"NOT READY cli {row['bin']}: `{row['ready'][0]}` is not a binary outside the project, so "
                                    f"`{' '.join(row['ready'])}` was not run ({label}): {row['ready_hint']}")
                    continue
                ok, how = ready([str(probe), *row["ready"][1:]], env, cwd)
                if not ok:
                    findings.append(f"NOT READY cli {row['bin']}: `{' '.join(row['ready'])}` failed ({how}) ({label}): {row['ready_hint']}")
                    continue
            notes.append(f"ok   cli {row['bin']}{version(row, path, env, cwd)} ({label})")
    return (1 if findings else 0), findings, notes


def selftest() -> int:
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
                              {"bin": "absentcli", "install": "brew install absentcli"},
                              {"bin": "localcli", "install": "npm install localcli --save-dev",
                               "project_paths": ["node_modules/.bin/localcli"], "version": ["--version"]}]}
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
            case("MISSING cli localcli is not on PATH or in the project" in text and "npm install localcli --save-dev" in text,
                 f"a project-local CLI that is absent is flagged with its install line: {findings}")
            local = proj / "node_modules" / ".bin" / "localcli"
            local.parent.mkdir(parents=True)
            local.write_text("#!/bin/sh\necho 'localcli 9.8.7'\n", encoding="utf-8")
            local.chmod(0o755)
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not any("localcli" in f for f in findings) and any("ok   cli localcli at node_modules/.bin/localcli (the project's own copy: not run)" in n for n in notes),
                 f"a CLI in the project's node_modules/.bin is found and reported present: {findings} {notes}")
            ran = proj / "ran.txt"
            local.write_text(f"#!/bin/sh\necho ran > '{ran}'\n", encoding="utf-8")
            run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not ran.exists(), "the project's own copy of a CLI is never executed by the audit")
            local.unlink()
            outside = root / "outside-cli"
            outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            outside.chmod(0o755)
            local.symlink_to(outside)
            rc, findings, _ = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(any("MISSING cli localcli" in f for f in findings), f"a project path that is a symlink out of the project is not the CLI: {findings}")
            local.unlink()
            local.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            local.chmod(0o755)
            # #2291 review: the project's node_modules/.bin on PATH (direnv, `npm run`, a shell rc) is still the project's copy.
            pwned = proj / "PWNED"
            local.write_text(f"#!/bin/sh\ntouch '{pwned}'\n", encoding="utf-8")
            os.environ["PATH"] = f"{local.parent}{os.pathsep}{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            toolchain["clis"].append({"bin": "localcli2", "install": "get localcli2", "version": ["--version"]})
            (local.parent / "localcli2").write_text(f"#!/bin/sh\ntouch '{pwned}'\n", encoding="utf-8")
            (local.parent / "localcli2").chmod(0o755)
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not pwned.exists(), "a project binary reached through PATH is never executed")
            case(any("ok   cli localcli2 at node_modules/.bin/localcli2 (the project's own copy: not run)" in n for n in notes),
                 f"a project binary reached through PATH is reported as the project's copy: {notes} {findings}")
            # a relative PATH entry names the directory the audit runs in: skipped
            os.environ["PATH"] = f".{os.pathsep}{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            here = os.getcwd()
            os.chdir(local.parent)
            try:
                rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            finally:
                os.chdir(here)
            case(not pwned.exists() and any("MISSING cli localcli2" in f for f in findings),
                 f"a relative PATH entry is not searched: {findings}")
            # project_paths come before PATH: a global copy never hides the project-pinned one
            os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            (bindir / "localcli").write_text("#!/bin/sh\necho 'global 1.0'\n", encoding="utf-8")
            (bindir / "localcli").chmod(0o755)
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(any("ok   cli localcli at node_modules/.bin/localcli (the project's own copy: not run)" in n for n in notes),
                 f"the project-pinned CLI is found before a global one: {notes}")
            (bindir / "localcli").unlink()
            # a ready command naming another binary that is the project's own is not run either
            toolchain["clis"].append({"bin": "okcli2", "install": "get okcli2", "ready": ["localcli2", "status"], "ready_hint": "h2"})
            (bindir / "okcli2").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (bindir / "okcli2").chmod(0o755)
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
            os.environ["PATH"] = f"{bindir}{os.pathsep}{local.parent}{os.pathsep}/usr/bin{os.pathsep}/bin"
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not pwned.exists() and any("NOT READY cli okcli2" in f and "was not run" in f for f in findings),
                 f"a ready probe that is the project's own binary is not run: {findings}")
            toolchain["clis"] = [c for c in toolchain["clis"] if c["bin"] not in ("localcli2", "okcli2")]
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
            (local.parent / "localcli2").unlink()
            local.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            # #2291 adversary: containment is judged by file identity, so a PATH entry spelling the project in other letter case
            # (a case-insensitive volume) is still the project. On a case-sensitive volume that spelling does not exist.
            (local.parent / "casecli").write_text(f"#!/bin/sh\ntouch '{pwned}'\n", encoding="utf-8")
            (local.parent / "casecli").chmod(0o755)
            alias = Path(str(local.parent).replace(proj.name, proj.name.upper()))
            toolchain["clis"].append({"bin": "casecli", "install": "get casecli", "version": ["--version"]})
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
            os.environ["PATH"] = f"{alias}{os.pathsep}{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not pwned.exists(), f"a PATH entry naming the project in other letter case does not run its binary (alias exists: {alias.exists()})")
            # a global script whose interpreter comes from PATH cannot pick up the project's own interpreter
            (local.parent / "casecli").unlink()
            (local.parent / "fakeinterp").write_text(f"#!/bin/sh\ntouch '{pwned}'\n", encoding="utf-8")
            (local.parent / "fakeinterp").chmod(0o755)
            where = root / "probe-cwd.txt"
            (bindir / "casecli").write_text(f"#!/usr/bin/env fakeinterp\n", encoding="utf-8")
            (bindir / "casecli").chmod(0o755)
            os.environ["PATH"] = f"{bindir}{os.pathsep}{local.parent}{os.pathsep}/usr/bin{os.pathsep}/bin"
            rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            case(not pwned.exists(), "a global CLI's `#!/usr/bin/env` interpreter is never resolved from the project")
            # the probe runs outside the project, so nothing reads the project's config by being started in it
            (bindir / "casecli").write_text(f"#!/bin/sh\npwd > '{where}'\n", encoding="utf-8")
            here = os.getcwd()
            os.chdir(proj)
            try:
                run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            finally:
                os.chdir(here)
            probed = Path(where.read_text(encoding="utf-8").strip()) if where.exists() else None
            case(probed is not None and not inside(probed, proj), f"a probe runs outside the project, not in it: {probed}")
            # an interpreter-option variable from the user's environment (direnv can set it from the project) never reaches a probe
            evil = proj / "evil.sh"
            evil.write_text(f"touch '{pwned}'\n", encoding="utf-8")
            (bindir / "casecli").write_text("#!/bin/bash\necho 'casecli 1.0'\n", encoding="utf-8")
            os.environ["BASH_ENV"] = str(evil)
            os.environ["NODE_OPTIONS"] = f"--require {evil}"
            try:
                rc, findings, notes = run_with({"enabledPlugins": {"tc-stack@m": True}}, None, None)
            finally:
                os.environ.pop("BASH_ENV", None)
                os.environ.pop("NODE_OPTIONS", None)
            case(not pwned.exists(), "BASH_ENV from the environment does not make a bash-script CLI load a project file")
            env_seen, _ = probe_env(proj)
            os.environ["NODE_OPTIONS"] = "--require x"
            os.environ["LC_ALL"] = "C"
            try:
                env_seen, _ = probe_env(proj)
            finally:
                os.environ.pop("NODE_OPTIONS", None)
                os.environ.pop("LC_ALL", None)
            case("NODE_OPTIONS" not in env_seen and env_seen.get("LC_ALL") == "C" and "HOME" in env_seen,
                 f"a probe's environment is the allowlist plus locale: {sorted(env_seen)}")
            toolchain["clis"] = [c for c in toolchain["clis"] if c["bin"] != "casecli"]
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")
            (bindir / "casecli").unlink()
            (local.parent / "fakeinterp").unlink()
            os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            text = "\n".join(findings)
            case(rc == 1, f"a missing tool is exit 1: rc={rc}")
            case("MISSING plugin extra@official is not enabled" in text and "/plugin install extra@official" in text,
                 f"a plugin no settings file enables is flagged with its install line: {findings}")
            case("MISSING cli absentcli is not on PATH" in text and "brew install absentcli" in text,
                 f"a CLI not on PATH is flagged with its install line: {findings}")
            case("NOT READY cli downcli" in text and "start downcli" in text,
                 f"a CLI whose ready check fails is flagged with its hint: {findings}")
            case(not any(re.search(r"\bcli okcli\b(?!2)", f) for f in findings) and any("ok   cli okcli (" in n for n in notes),
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
