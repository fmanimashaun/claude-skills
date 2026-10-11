#!/usr/bin/env python3
"""Flag Claude Code settings that do nothing where they are set (#1827, slice 1 of #1685).

    python3 check_project_settings.py                       # the project at the current directory
    python3 check_project_settings.py --root DIR            # a project elsewhere
    python3 check_project_settings.py --markdown FILE|DIR   # also read the fenced json blocks of markdown (templates)
    python3 check_project_settings.py --selftest

Exit codes: 0 nothing dead . 1 a dead setting found . 2 unusable (a settings file that is not JSON, a path that cannot be read): never
reported as clean.

WHAT IS DEAD, from the official pages (read live by `doctrine-verifier` on 2026-10-10, verdict CONFIRMED; registry rows
`project-settings-automode-not-read` and `project-settings-defaultmode-auto` in `docs/evidence/upstream/claude-code.json` re-read the sentences weekly):

  * `autoMode` in a project's `.claude/settings.json` or `.claude/settings.local.json`. https://code.claude.com/docs/en/auto-mode-config:
    "The classifier doesn't read `autoMode` from project settings in `.claude/settings.json` or `.claude/settings.local.json`. Both files
    live in the repo directory, so a checked-in repo or a build step could otherwise inject its own allow rules. Move any `autoMode` block in
    `.claude/settings.local.json` to `~/.claude/settings.json`."
  * `permissions.defaultMode` of `auto` or `bypassPermissions` in those two files. https://code.claude.com/docs/en/permission-modes:
    "If you set `"auto"` in `.claude/settings.json` or `.claude/settings.local.json`, the value doesn't take effect ... If you set
    `"bypassPermissions"` in those two files, it doesn't take effect either, and the session starts in Manual mode. The other values apply
    from any settings file."

The pages say "doesn't read" and "doesn't take effect", not "ignored", and so do the messages here. `.claude/settings.example.json` is read too: it
is the file teammates copy to `.claude/settings.local.json`, so a dead key there is dead once copied. The check reads files only; it never writes
one, and the selftest uses temp directories, never a real settings file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

SETTINGS_FILES = (".claude/settings.json", ".claude/settings.local.json", ".claude/settings.example.json")
DEAD_MODES = ("auto", "bypassPermissions")
FIX = "Move it to ~/.claude/settings.json (your user settings), which is where the page says it is read."
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)^[ \t]{0,3}\1[ \t]*$", re.S | re.M)


class Unusable(Exception):
    pass


def findings_in(data: object, where: str) -> list[str]:
    """The dead settings in one parsed settings object."""
    out: list[str] = []
    if not isinstance(data, dict):
        return out
    if "autoMode" in data:
        out.append(f"{where}: `autoMode` is here, but the classifier doesn't read `autoMode` from project settings. {FIX}")
    perms = data.get("permissions")
    if isinstance(perms, dict):
        mode = perms.get("defaultMode")
        if isinstance(mode, str) and mode in DEAD_MODES:
            effect = ("it doesn't take effect, and Claude Code uses the built-in default" if mode == "auto"
                      else "it doesn't take effect, and the session starts in Manual mode")
            out.append(f"{where}: `permissions.defaultMode` is \"{mode}\" here, and {effect}. {FIX}")
    return out


def check_settings_file(path: Path, label: str) -> tuple[list[str], int]:
    """(findings, files read) for one settings file; a missing file is not an error (the project may not have one)."""
    if not path.exists():
        return [], 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unusable(f"{label}: cannot be read: {exc}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Unusable(f"{label}: is not valid JSON ({exc}), so it cannot be judged")
    return findings_in(data, label), 1


def check_markdown(path: Path) -> tuple[list[str], int]:
    """(findings, json blocks read) for the fenced json blocks of one markdown file: templates a project would copy."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unusable(f"{path}: cannot be read: {exc}")
    out: list[str] = []
    read = 0
    for m in FENCE.finditer(text):
        lang, body = m.group(2).lower(), m.group(3)
        if lang not in ("json", "jsonc", ""):
            continue
        line = text.count("\n", 0, m.start()) + 1
        where = f"{path}:{line}"
        try:
            data = json.loads(body)
        except ValueError:
            # A template with elisions (`...`) is not JSON; judge it by the two keys' text, so it is never read as clean.
            if re.search(r'"autoMode"\s*:', body):
                out.append(f"{where}: a template with `autoMode` in it: the classifier doesn't read `autoMode` from project settings. {FIX}")
            m2 = re.search(r'"defaultMode"\s*:\s*"(auto|bypassPermissions)"', body)
            if m2:
                out.append(f"{where}: a template with `defaultMode` \"{m2.group(1)}\": it doesn't take effect in project settings. {FIX}")
            read += 1
            continue
        read += 1
        out.extend(findings_in(data, where))
    return out, read


def markdown_files(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(p for p in target.rglob("*.md") if p.is_file())
    if target.is_file():
        return [target]
    raise Unusable(f"{target}: not a file or a directory")


def run(root: Path, markdown: list[Path]) -> tuple[int, list[str], str]:
    found: list[str] = []
    files = 0
    for rel in SETTINGS_FILES:
        f, n = check_settings_file(root / rel, rel)
        found += f
        files += n
    blocks = 0
    for target in markdown:
        for md in markdown_files(target):
            f, n = check_markdown(md)
            found += f
            blocks += n
    return (1 if found else 0), found, f"{files} settings file(s) and {blocks} markdown json block(s) read"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_project_settings.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--markdown", type=Path, action="append", default=[], help="a markdown file or directory whose fenced json blocks are read")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        code, found, note = run(args.root, args.markdown)
    except Unusable as exc:
        print(f"unusable: {exc}", file=sys.stderr)
        return 2
    if found:
        print(f"{len(found)} dead setting(s) ({note}):")
        for line in found:
            print(f"  - {line}")
    else:
        print(f"ok: nothing dead ({note})")
    return code


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    def project(files: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="cps-"))
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return root

    def go(files: dict[str, str], md: list[Path] | None = None):
        root = project(files)
        try:
            return run(root, md or [])
        finally:
            for p in sorted(root.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            root.rmdir()

    S = ".claude/settings.json"
    L = ".claude/settings.local.json"
    E = ".claude/settings.example.json"
    code, found, note = go({S: '{"permissions": {"allow": ["Bash(git:*)"]}}'})
    check("a clean settings file is ok", code == 0 and not found and note.startswith("1 settings"), f"{code} {found} {note}")
    code, found, note = go({})
    check("a project with no settings file is ok, and says it read none", code == 0 and not found and note.startswith("0 settings"), f"{code} {found} {note}")
    code, found, _ = go({S: '{"autoMode": {"environment": ["x"]}}'})
    check("autoMode in settings.json is dead", code == 1 and len(found) == 1 and "doesn't read" in found[0] and S in found[0], str(found))
    code, found, _ = go({L: '{"autoMode": {}}'})
    check("autoMode in settings.local.json is dead", code == 1 and len(found) == 1 and L in found[0], str(found))
    code, found, _ = go({E: '{"autoMode": {}}'})
    check("autoMode in the example file is dead once copied", code == 1 and len(found) == 1 and E in found[0], str(found))
    code, found, _ = go({S: '{"permissions": {"defaultMode": "auto"}}'})
    check("defaultMode auto in project settings is dead", code == 1 and len(found) == 1 and "doesn't take effect" in found[0] and "built-in default" in found[0], str(found))
    code, found, _ = go({L: '{"permissions": {"defaultMode": "bypassPermissions"}}'})
    check("defaultMode bypassPermissions is dead, and the message says the session starts in Manual mode", code == 1 and len(found) == 1 and "Manual mode" in found[0], str(found))
    for mode in ("default", "acceptEdits", "plan", "dontAsk"):
        code, found, _ = go({S: json.dumps({"permissions": {"defaultMode": mode}})})
        check(f"CONTROL: defaultMode {mode} applies from any settings file, so it passes", code == 0 and not found, str(found))
    code, found, _ = go({S: '{"defaultMode": "auto"}'})
    check("CONTROL: a top-level defaultMode key is not the documented setting, so it is not judged", code == 0 and not found, str(found))
    code, found, _ = go({S: '{"permissions": {"defaultMode": ["auto"]}}'})
    check("CONTROL: a non-string defaultMode is not read as auto", code == 0 and not found, str(found))
    code, found, _ = go({S: '{"autoMode": {}, "permissions": {"defaultMode": "auto"}}', L: '{"autoMode": {}}'})
    check("every dead setting is reported, across files", code == 1 and len(found) == 3, str(found))
    root = project({S: "{not json"})
    try:
        try:
            run(root, [])
            check("a settings file that is not JSON is unusable, never clean", False, "no Unusable raised")
        except Unusable:
            check("a settings file that is not JSON is unusable, never clean", True)
    finally:
        (root / S).unlink(); (root / ".claude").rmdir(); root.rmdir()
    md_root = Path(tempfile.mkdtemp(prefix="cps-md-"))
    try:
        (md_root / "a.md").write_text('# t\n\n```json\n{"permissions": {"defaultMode": "auto"}}\n```\n\n```json\n{"autoMode": {}}\n```\n', encoding="utf-8")
        (md_root / "b.md").write_text('```json\n{"permissions": {"defaultMode": "plan"}}\n```\n\n```sh\necho {"autoMode": {}}\n```\n', encoding="utf-8")
        (md_root / "c.md").write_text('```json\n{"permissions": {"defaultMode": "auto", ...}}\n```\n', encoding="utf-8")
        code, found, note = go({}, [md_root / "a.md"])
        check("a markdown template with defaultMode auto or autoMode is dead", code == 1 and len(found) == 2 and "2 markdown" in note, f"{found} {note}")
        code, found, _ = go({}, [md_root / "b.md"])
        check("CONTROL: a template with another mode, and a shell block that only echoes an autoMode snippet, pass", code == 0 and not found, str(found))
        code, found, _ = go({}, [md_root / "c.md"])
        check("a template with elisions is judged by its text, never read as clean", code == 1 and len(found) == 1, str(found))
        code, found, note = go({}, [md_root])
        check("a directory of markdown is read recursively", code == 1 and len(found) == 3 and "4 markdown" in note, f"{found} {note}")
    finally:
        for p in md_root.iterdir():
            p.unlink()
        md_root.rmdir()
    try:
        run(Path(tempfile.gettempdir()), [Path("/nonexistent-cps-path")])
        check("a markdown path that does not exist is unusable", False, "no Unusable raised")
    except Unusable:
        check("a markdown path that does not exist is unusable", True)
    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_project_settings selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
