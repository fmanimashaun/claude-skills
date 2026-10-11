# Can a repository's settings reach our hooks? Measured, 2026-10-11 (#1843)

**Result.** Yes. A repository's checked-in `.claude/settings.json` can set the environment of every hook process, ours included, and can switch every plugin hook off. Measured with Claude Code 2.1.296 on macOS (arm64, git 2.50.1), in `claude -p` mode, which never shows the trust dialog. This file records the method, the table, what it does and does not show, and the recipe to repeat it.

This is evidence for two documents: `CLAUDE.md`'s platform paragraph and `docs/doctrine/harness-doctrine.md` sections 5 and 10, which now say that a gate is a guarantee inside a trusted workspace only. The hardening that follows from it is #1850 (v1.157.0).

## Method

A scratch git repository whose checked-in `.claude/settings.json` sets `env` to point at harmless **witness** programs: each appends one line to a file and then `exec`s the real tool, so nothing breaks. A scratch plugin hook records the environment it receives and calls `python3` and `git` by bare name, as 17 and 10 of our hook scripts do. Then, from inside the scratch repository:

```
claude -p "Use the Bash tool to run exactly this command: echo probe. Then reply with only the word done." \
  --plugin-dir <scratch plugin> --plugin-dir plugins/rails-flow --plugin-dir plugins/qa-flow --allowedTools Bash
```

A **control** run with the project's `env` removed must produce no witness at all. The first control was NOT clean, and the cause is itself a finding: detached `python3 -m pipeline.shell ...` processes (not ours: no match in this repository) from the previous run were still running in the control's window and carried the repository's `PATH` with them, so the injected `PATH` also reaches background children that outlive the session. The control that counts waited for them to finish and was silent.

## Results

| Project setting | What a hook process got | Witness |
|---|---|---|
| `env.PATH` = `<repo>/bin:...` | the repository's `bin/` first; `command -v python3` resolved to the repository's file | the fake `python3` ran for 6 of our scripts (`ci_verdict_hint.py`, `lib/coordination.py`, `lib/where_stopped.py` twice, `lib/worktree_guard.py`, `session_reaper.py`) and for third-party hooks |
| `env.PATH` with a fake `bash` first | **the harness resolves the hook's own `bash` through `PATH`**, so the repository's program started instead of the script | 10 of our hook commands started under it: `rails-flow/guard-bash.sh`, `guard-claims.sh`, `guard-worktree.sh`, `ci-verdict-hint.sh`, `session-start.sh`, `session-end.sh`, `stop-gate.sh`, `stop-where.sh`, `qa-flow/release-gate.sh`, `qa-status.sh`; third-party hooks too (remember, superpowers, security-guidance, explanatory-output-style) |
| `env.PYTHONPATH` | honoured: the repository's `sitecustomize` imported at every `python3` start | 32 times in one session |
| `env.GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=core.fsmonitor`, `GIT_CONFIG_VALUE_0=<repo>/bin/fsmon` | a hook's bare `git status` ran the repository's program as the fsmonitor | ran |
| `env.BASH_ENV` | sourced by every non-interactive `bash` a hook starts | 21 times. Checked directly: `/bin/bash script` sources it, `/bin/bash -p script` does not |
| `env.CLAUDE_PLUGIN_ROOT` | **not applied**: the harness sets it itself | the repository's script did not run |
| `"disableAllHooks": true` | **every plugin hook was switched off** | the scratch plugin's hook did not run |

## What it shows

1. **A gate can start under a program the repository chose, before any of our code runs.** A fake `bash` that exits 0 makes `guard-bash`, `guard-claims`, `guard-worktree` and `release-gate` allow everything. Resolving `python3` by absolute path inside a script cannot help: the script never starts.
2. **The repository does not need the environment to do it.** `disableAllHooks` in project settings switches the plugin hooks off, and settings-file hooks and `env` apply in `-p` mode without a trust prompt (the permissions page, quoted in the #1821 threat model). Against a HOSTILE repository none of our gates was a guarantee. **The trust decision is the boundary.** A gate guards against the model's mistakes and a cooperating repository.
3. The redirect still matters for the cooperating case: a project that legitimately puts a `bin/git` or `bin/python3` shim on `PATH`, or a direnv, silently changes what every hook runs.

## What it does not show

- **Interactive mode after the trust dialog.** The documents say `env` then applies; I could not drive the dialog headlessly. #1850 asks a person to measure it.
- Linux and Windows. `LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_*` (macOS strips `DYLD_*` for SIP-protected binaries such as `/bin/bash`, not for a Homebrew Python) and `NODE_OPTIONS`.
- Whether other Claude Code versions differ.

## Reproduce

Save as `rig.py` and run `python3 rig.py <empty scratch dir>`; it builds the scratch repository, the witnesses and the plugin, then runs the experiment and a control, and prints which witnesses fired. It needs `claude` on `PATH`. Run it only in a scratch directory.

```python
import json, os, shutil, stat, subprocess, sys, time
from pathlib import Path

base = Path(sys.argv[1]).resolve()
W, P, PL = base / "witness", base / "project", base / "plugin"
for d in (W, P / ".claude", P / "bin", P / "pylib", PL / ".claude-plugin", PL / "hooks"):
    d.mkdir(parents=True, exist_ok=True)

def script(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

# Witnesses: record that they ran, then hand over to the real tool.
script(P / "bin" / "python3", f'#!/bin/sh\necho "$0 $*" >> {W}/fake-python3-ran\nexec /usr/bin/python3 "$@"\n')
script(P / "bin" / "bash",    f'#!/bin/sh\necho "$0 $*" >> {W}/fake-bash-ran\nexec /bin/bash "$@"\n')
script(P / "bin" / "fsmon",   f'#!/bin/sh\necho "$0" >> {W}/git-fsmonitor-ran\nexit 0\n')
(P / "pylib" / "sitecustomize.py").write_text(
    f"import pathlib\nwith open({str(W / 'pythonpath-ran')!r}, 'a') as f: f.write('sitecustomize\\n')\n")
subprocess.run(["git", "init", "-q", str(P)], check=True)

# A scratch plugin hook that records what it received and calls python3 and git by bare name.
(PL / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "probe", "version": "0.0.1", "description": "env probe"}))
(PL / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/probe.sh"'}]}]}}))
script(PL / "hooks" / "probe.sh", f"""#!/usr/bin/env bash
{{ echo "PATH first entry: ${{PATH%%:*}}"; echo "command -v python3: $(command -v python3)"; }} > {W}/probe-env.txt
python3 -c 'pass' 2>/dev/null
git -C {P} status --porcelain >/dev/null 2>&1
exit 0
""")

def run(label, project_settings):
    for f in W.glob("*"):
        f.unlink()
    (P / ".claude" / "settings.json").write_text(json.dumps(project_settings, indent=2))
    subprocess.run(["claude", "-p", "Use the Bash tool to run exactly this command: echo probe. Then reply with only the word done.",
                    "--plugin-dir", str(PL), "--allowedTools", "Bash", "--output-format", "text"],
                   cwd=P, capture_output=True, text=True, timeout=280, stdin=subprocess.DEVNULL)
    time.sleep(20)                       # let the session's detached helpers finish before reading
    fired = {f.name: len(f.read_text().splitlines()) for f in sorted(W.glob("*")) if f.name != "probe-env.txt"}
    print(label, fired, "| probe hook ran:", (W / "probe-env.txt").exists())

env = {"PATH": f"{P}/bin:{os.environ['PATH']}", "PYTHONPATH": str(P / "pylib"),
       "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": str(P / "bin" / "fsmon")}
run("EXPERIMENT (project env set):", {"env": env})
time.sleep(60)                            # a clean control needs the previous run's detached children gone
run("CONTROL (no project env):    ", {})
run("disableAllHooks in project:  ", {"disableAllHooks": True})
```

Expected: the experiment run shows the fake `python3`, `bash`, the `sitecustomize` import and the fsmonitor; the control shows none; the `disableAllHooks` run shows `probe hook ran: False`.
