#!/usr/bin/env python3
"""Every plugin hook command must survive an install path that contains a space.

Run:  python3 scripts/check_hook_commands.py            # every plugins/*/hooks/hooks.json
      python3 scripts/check_hook_commands.py --selftest # prove the rules fire AND stay silent

WHY (#1334). All four plugins failed `claude plugin validate --strict`: 13 hook commands ran
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/<x>.sh` with the placeholder unquoted. Claude Code's own
warning: "If the expanded path contains a space the command can split into several words and fail."
On such a path every hook fails to start, including the four gates that are meant to fail closed:
a PreToolUse command that exits non-zero without exit code 2 does not block, so the guards would
stop guarding. We never ran the validator against the plugins, only against marketplace.json.

TWO CHECKS, because the first can be satisfied by accident and the second cannot:
  1. static: `${CLAUDE_PLUGIN_ROOT}` in a shell command sits inside double quotes;
  2. dynamic: each command is expanded by bash with CLAUDE_PLUGIN_ROOT set to a copy of the plugin
     under a directory whose name contains a space. `bash` is swapped for `printf` so NOTHING runs;
     only the word splitting happens. The script argument must arrive as ONE word naming a real file.

This does not need the `claude` CLI, which CI may not have. `claude plugin validate --strict` remains
the authority; this is the part of it we can pin locally.

Exit codes:  0 clean · 1 a finding · 2 nothing to check (never reported clean)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
QUOTED = re.compile(r'"[^"]*\$\{CLAUDE_PLUGIN_ROOT\}[^"]*"')


def commands(manifest: Path) -> list[tuple[str, str]]:
    """(event, command) for every command hook in a hooks.json."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    out = []
    for event, entries in data.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command" and "args" not in hook:
                    out.append((event, hook.get("command", "")))
    return out


def unquoted(command: str) -> bool:
    return PLACEHOLDER in QUOTED.sub("", command)


def expands_to_one_file(command: str, plugin: Path) -> tuple[bool, str]:
    """Expand the command's words under bash from a spaced copy of the plugin; run nothing."""
    if not command.startswith("bash "):
        return True, "not a bash command"
    with tempfile.TemporaryDirectory() as td:
        spaced = Path(td) / "Application Support" / plugin.name
        shutil.copytree(plugin, spaced)
        probe = "printf '%s\\n' " + command[len("bash "):]
        proc = subprocess.run(["bash", "-c", probe], capture_output=True, text=True,
                              env={"CLAUDE_PLUGIN_ROOT": str(spaced), "PATH": "/usr/bin:/bin"})
        words = proc.stdout.splitlines()
        ok = bool(words) and Path(words[0]).is_file()
        return ok, (words[0] if words else proc.stderr.strip())


def check(root: Path) -> tuple[int, list[str]]:
    manifests = sorted(root.glob("plugins/*/hooks/hooks.json"))
    if not manifests:
        return 2, ["UNUSABLE: no plugins/*/hooks/hooks.json to check"]
    findings, total = [], 0
    for manifest in manifests:
        plugin = manifest.parent.parent
        rel = manifest.relative_to(root)
        for event, command in commands(manifest):
            if PLACEHOLDER not in command:
                continue
            total += 1
            if unquoted(command):
                findings.append(f"  [unquoted-plugin-root] {rel} {event}: {command}")
            ok, first = expands_to_one_file(command, plugin)
            if not ok:
                findings.append(f"  [splits-on-space] {rel} {event}: from a spaced install path the "
                                f"script argument became {first!r}, not one existing file")
    if findings:
        return 1, [f"{len(findings)} finding(s) across {total} plugin hook command(s):", *findings]
    return 0, [f"all {total} plugin hook commands survive an install path containing a space"]


def selftest() -> int:
    failures: list[str] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    good = 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/a.sh"'
    bad = "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/a.sh"
    expect("CONTROL: a quoted placeholder is not flagged", not unquoted(good))
    expect("an unquoted placeholder is flagged", unquoted(bad))
    expect("one quoted and one bare use is still flagged", unquoted(good + " ${CLAUDE_PLUGIN_ROOT}/x"))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plugin = root / "plugins" / "p"
        (plugin / "hooks" / "scripts").mkdir(parents=True)
        (plugin / "hooks" / "scripts" / "a.sh").write_text("exit 0\n", encoding="utf-8")
        manifest = plugin / "hooks" / "hooks.json"

        def write(cmd: str) -> None:
            manifest.write_text(json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]}]}}), encoding="utf-8")

        write(good)
        code, out = check(root)
        expect("CONTROL: a quoted command survives a spaced path", code == 0, str(out))
        write(bad)
        code, out = check(root)
        expect("an unquoted command is refused statically",
               code == 1 and any("[unquoted-plugin-root]" in l for l in out), str(out))
        expect("...and the spaced-path expansion catches it on its own",
               any("[splits-on-space]" in l for l in out), str(out))
        write('bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/missing.sh"')
        expect("a quoted path to a script that does not exist is refused",
               any("[splits-on-space]" in l for l in check(root)[1]))
        manifest.unlink()
        expect("no hooks.json anywhere is UNUSABLE, never clean", check(root)[0] == 2)

    for f in failures:
        print(f"FAIL: {f}")
    print(f"check_hook_commands selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    code, lines = check(ROOT)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
