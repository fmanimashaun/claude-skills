#!/usr/bin/env python3
"""Run `claude plugin validate --strict --json` over the marketplace and over every plugin directory it lists (#1684).

The CLI is the authority on what Claude Code accepts: unrecognised manifest fields, missing metadata and bad component files that the runtime
tolerates fail `--strict`. It does NOT replace `check_frontmatter.py`: measured on 2.1.292 it also passed an agent file with an unterminated
`tools: [Read` list (#1679), so both run.

Exit codes (the doctor reads 3 as SKIP, never as a pass):
  0  every target validated, `--strict` applied, a manifest was read, no errors and no warnings
  1  at least one target has an error or a warning (printed with its file)
  2  the validator itself failed or printed something that is not the report we need (an unreadable result is not a pass)
  3  could not check: no `claude` on PATH, or one older than 2.1.259 (the first with `--json`)

Docs: https://code.claude.com/docs/en/plugins/cli-reference#plugin-validate (flags, exit codes, report fields).
Targets: the repository root (its `.claude-plugin/marketplace.json`) and each `plugins/*` source named in it. A marketplace run does not open
the component files of plugins in other directories, so each plugin directory is validated on its own. `skills/` is not a target: a run
over it reads no manifest and returns `contents: []` however the files look, which would be a pass over input it never read.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MIN_VERSION = (2, 1, 259)
TIMEOUT = 120


def version_of(claude: str) -> tuple[int, ...] | None:
    try:
        out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else None


def targets(root: Path) -> list[str]:
    """`.` for the marketplace, then each directory source the marketplace lists, in manifest order. A source that is not a local directory
    (a URL, an object) is not ours to validate here and is left out; one that points nowhere raises, so a typo is a failure, not a skip."""
    data = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    found = ["."]
    for entry in data.get("plugins", []):
        source = entry.get("source")
        if isinstance(source, str) and source.startswith("./") and source.rstrip("/") != ".":
            if not (root / source / ".claude-plugin" / "plugin.json").is_file():
                raise FileNotFoundError(f"{entry.get('name')}: {source} has no .claude-plugin/plugin.json")
            found.append(source.rstrip("/"))
    return found


def findings(report: dict) -> list[str]:
    """Every error and warning in a report, each with where it is."""
    lines: list[str] = []
    manifest = report.get("manifest") or {}
    for kind in ("errors", "warnings"):
        for item in manifest.get(kind, []) or []:
            lines.append(f"  {kind[:-1]}: {manifest.get('file', 'manifest')}: {item if isinstance(item, str) else json.dumps(item)}")
    for entry in report.get("contents", []) or []:
        for kind in ("errors", "warnings"):
            for item in entry.get(kind, []) or []:
                lines.append(f"  {kind[:-1]}: {entry.get('file', '?')}: {item if isinstance(item, str) else json.dumps(item)}")
    return lines


def validate_one(claude: str, root: Path, target: str) -> tuple[int, list[str]]:
    """(verdict, lines): 0 passed, 1 findings, 2 the validator failed or its answer cannot be trusted."""
    try:
        done = subprocess.run([claude, "plugin", "validate", str((root / target).resolve()), "--strict", "--json"], capture_output=True, text=True,
                              timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, [f"  could not run the validator on {target}: {exc}"]
    try:
        report = json.loads(done.stdout)
    except ValueError:
        return 2, [f"  {target}: exit {done.returncode} and no JSON report on stdout: {(done.stderr or done.stdout).strip()[:200]!r}"]
    if not isinstance(report, dict) or "success" not in report or "strict" not in report:
        return 2, [f"  {target}: the report has no `success` and `strict` fields"]
    # A DIAGNOSTIC OBJECT IS NOT A PASS: the verdict needs the exit code AND the report to agree, `--strict` actually applied, and a manifest read.
    if done.returncode == 1 or report["success"] is False:
        return 1, findings(report) or [f"  {target}: the validator failed with no finding listed (exit {done.returncode})"]
    if done.returncode != 0:
        return 2, [f"  {target}: unexpected exit {done.returncode}"]
    if report["success"] is not True or report["strict"] is not True:
        return 2, [f"  {target}: exit 0 but success={report['success']!r} strict={report['strict']!r}"]
    if not isinstance(report.get("manifest"), dict):
        return 2, [f"  {target}: exit 0 but no manifest was read, so nothing was checked"]
    if findings(report):
        return 1, findings(report)
    return 0, []


def run(root: Path, claude: str | None = None) -> int:
    claude = claude or shutil.which("claude")
    if not claude:
        print("could not check: no `claude` on PATH (exit 3, not a pass)", file=sys.stderr)
        return 3
    version = version_of(claude)
    if version is None or version < MIN_VERSION:
        print(f"could not check: claude {'.'.join(map(str, version)) if version else '?'} is older than 2.1.259 or unreadable, the first with `plugin validate --json` (exit 3, not a pass)",
              file=sys.stderr)
        return 3
    try:
        names = targets(root)
    except (OSError, ValueError) as exc:
        print(f"plugin validate: cannot read the marketplace targets: {exc}", file=sys.stderr)
        return 2
    worst = 0
    for target in names:
        verdict, lines = validate_one(claude, root, target)
        print(f"{'ok ' if verdict == 0 else 'FAIL'} claude plugin validate --strict {target}")
        for line in lines:
            print(line)
        worst = max(worst, verdict)
    print(f"plugin validate: {len(names)} target(s) checked, {'all passed' if worst == 0 else 'see above'}")
    return worst


# ---- selftest: a stub `claude` on disk, so every branch above is driven without the real CLI --------------------------------------------------


def stub(td: Path, *, version: str = "2.1.296", report: dict | None = None, code: int = 0, raw: str | None = None) -> str:
    """An executable that answers `--version` and `plugin validate` as told."""
    body = report if report is not None else {"success": True, "strict": True, "target": "x", "manifest": {"file": "m", "errors": [], "warnings": []},
                                              "contents": [], "advice": []}
    out = raw if raw is not None else json.dumps(body)
    path = td / "claude"
    path.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '%s (Claude Code)'; exit 0; fi\ncat <<'EOF_STUB'\n%s\nEOF_STUB\nexit %d\n" % (version, out, code))
    path.chmod(0o755)
    return str(path)


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool) -> None:
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as raw:
        td = Path(raw)
        root = td / "repo"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / "plugins/a/.claude-plugin").mkdir(parents=True)
        (root / "plugins/a/.claude-plugin/plugin.json").write_text("{}")
        (root / ".claude-plugin/marketplace.json").write_text(json.dumps({"plugins": [
            {"name": "stack", "source": "./"}, {"name": "a", "source": "./plugins/a"}, {"name": "remote", "source": {"source": "github"}}]}))
        quiet = lambda fn, *a, **k: _quiet(fn, *a, **k)  # noqa: E731
        check("targets: the marketplace first, then each local directory source, never a URL object or `./`", targets(root) == [".", "./plugins/a"])
        (root / ".claude-plugin/marketplace.json").write_text(json.dumps({"plugins": [{"name": "gone", "source": "./plugins/gone"}]}))
        try:
            targets(root)
            check("targets: a source with no plugin.json raises, so a typo is not a skip", False)
        except FileNotFoundError:
            pass
        (root / ".claude-plugin/marketplace.json").write_text(json.dumps({"plugins": [{"name": "a", "source": "./plugins/a"}]}))

        def code_for(**kw) -> int:
            return quiet(run, root, stub(td, **kw))

        check("passes: success, strict, a manifest and no findings", code_for() == 0)
        check("a warning in the manifest fails", code_for(code=1, report={"success": False, "strict": True, "manifest": {"file": "m", "errors": [],
              "warnings": ["unknown field"]}, "contents": []}) == 1)
        check("an error in a content file fails", code_for(code=1, report={"success": False, "strict": True, "manifest": {"errors": [], "warnings": []},
              "contents": [{"file": "agents/x.md", "errors": ["bad"], "warnings": []}]}) == 1)
        check("exit 0 with a warning still listed is a failure, not a pass", code_for(report={"success": True, "strict": True, "manifest": {"errors": [],
              "warnings": ["w"]}, "contents": []}) == 1)
        check("exit 0 but `strict` false means the flag did not apply: not a pass", code_for(report={"success": True, "strict": False,
              "manifest": {"errors": [], "warnings": []}, "contents": []}) == 2)
        check("exit 0 but a null manifest means nothing was read: not a pass", code_for(report={"success": True, "strict": True, "manifest": None,
              "contents": []}) == 2)
        check("exit 0 but success false is not a pass", code_for(report={"success": False, "strict": True, "manifest": {"errors": [], "warnings": []},
              "contents": []}) == 1)
        check("output that is not JSON is exit 2, never a pass", code_for(raw="Validation passed") == 2)
        check("a report without success and strict is exit 2", code_for(report={"manifest": {}}) == 2)
        check("an unexpected exit code is exit 2", code_for(code=7) == 2)
        check("an older claude is a skip (3), not a pass", code_for(version="2.1.258") == 3)
        check("an unreadable version is a skip (3)", quiet(run, root, stub(td, version="none")) == 3)
        old_path = shutil.which
        try:
            shutil.which = lambda name: None  # type: ignore[assignment]
            check("no claude on PATH is a skip (3), not a pass", quiet(run, root) == 3)
        finally:
            shutil.which = old_path  # type: ignore[assignment]
        check("a marketplace file that cannot be read is exit 2", quiet(run, td / "nowhere", stub(td)) == 2)
    if failures:
        print("plugin validate selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("plugin validate selftest: ok (0 failure(s))")
    return 0


def _quiet(fn, *args, **kwargs):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv:
        print(__doc__)
        return 2
    return run(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
