#!/usr/bin/env python3
"""Run the herb ERB linter at the version the project locked, and say which one ran (#1285).

WHY THIS EXISTS. The `erb-lint` gate ran `bundle exec herb lint app/views`. The locked herb gem
(0.10.3, `lib/herb/cli.rb` `run_node_tool`) runs a project-local `node_modules/.bin/herb-lint` if
there is one, then any `herb-lint` on PATH, and otherwise `npx @herb-tools/linter` WITH NO VERSION,
so npx resolves the newest release on npm. The gem was pinned in Gemfile.lock, and the linter
deciding the verdict was not. When `@herb-tools/linter` 0.11.0 was published (2026-09-24T14:32:54Z),
a downstream `bin/ci` went from ok to FAIL between two runs 19 minutes apart with nothing the
project controls changed: on the same tree, 0.10.3 exits 0 and 0.11.0 exits 1.

THE PIN. herb releases the gem and the npm linter in lockstep (0.9.0 to 0.11.0 all exist as both,
checked against rubygems and npm). So the locked gem version is the linter version. Resolution:
  1. `node_modules/.bin/herb-lint` -- the project pinned it in package.json;
  2. otherwise `npx -y @herb-tools/linter@<herb version in Gemfile.lock>`.
A global `herb-lint` on PATH is deliberately NOT used: it is unpinned too.

Run:  herb_lint.py [--root DIR] [PATHS...]      (default: every template dir that exists, #1296)

WHAT IT LINTS BY DEFAULT (#1296). `app/views` AND `app/components`: design-system puts every UI
component under app/components, and a gate that linted only app/views never saw one. Downstream,
29 component templates went unlinted and one carried a parser error for weeks.
      herb_lint.py --selftest
Exit: the linter's own exit status; 2 when herb is not in Gemfile.lock (never reported as clean).
Every run prints `NOTE: herb linter <version> (<source>)`, so a verdict names the linter that gave it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# A spec line in Gemfile.lock sits at four spaces; a dependency constraint sits at six, so anchoring
# the indent keeps `      herb (>= 0.10)` under another gem from reading as the locked version.
TEMPLATE_DIRS = ("app/views", "app/components")
LOCKED = re.compile(r"^ {4}herb \((\d+\.\d+\.\d+)(?:[-.][^)]*)?\)$", re.M)


def locked_version(root: Path) -> str | None:
    lock = root / "Gemfile.lock"
    if not lock.is_file():
        return None
    found = LOCKED.findall(lock.read_text(encoding="utf-8"))
    return found[0] if found else None


def default_paths(root: Path) -> list[str]:
    """Every template directory this project has, so a component template is never skipped."""
    found = [d for d in TEMPLATE_DIRS if (root / d).is_dir()]
    return found or ["app/views"]


def command(root: Path, paths: list[str]) -> tuple[list[str] | None, str]:
    """`(argv, note)`, or `(None, reason)` when no pinned linter can be named."""
    local = root / "node_modules" / ".bin" / "herb-lint"
    if local.is_file() and os.access(local, os.X_OK):
        return [str(local), *paths], "herb linter from node_modules/.bin (pinned by package.json)"
    version = locked_version(root)
    if version is None:
        return None, ("herb is not in Gemfile.lock, so there is no version to pin the linter to -- "
                      "add the herb gem, or install @herb-tools/linter in package.json")
    return (["npx", "-y", f"@herb-tools/linter@{version}", *paths],
            f"herb linter {version} (matches the herb gem locked in Gemfile.lock)")


SEVERITY_ORDER = ("error", "warning", "info", "hint")


def render(stdout: str) -> list[str] | None:
    """herb's `--format json` as our summary line, then every offence, MOST SEVERE FIRST (#1318).

    herb prints offences in file order, so the first `file:line:col` in its text was often a HINT,
    and `project_gates` named that as the FAIL row while the errors sat further down. Our own
    `N herb finding(s):` line is what the aggregate anchors on, so the row now carries the counts,
    and the errors come first. None when the output is not herb's JSON: the caller prints it raw.
    """
    try:
        data = json.loads(stdout)
        offenses = data["offenses"]
        summary = data.get("summary") or {}
    except (ValueError, KeyError, TypeError):
        return None
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    ordered = sorted(offenses, key=lambda o: (rank.get(o.get("severity"), len(rank)),
                                              o.get("filename", ""), o.get("location", {}).get("start", {}).get("line", 0)))
    counts = {s: sum(1 for o in offenses if o.get("severity") == s) for s in SEVERITY_ORDER}
    lines = [f"{len(offenses)} herb finding(s): {counts['error']} error, {counts['warning']} warning, "
             f"{counts['info']} info, {counts['hint']} hint -- most severe first"
             + (f" ({summary.get('filesChecked')} files checked)" if summary.get("filesChecked") is not None else "")]
    for o in ordered:
        start = o.get("location", {}).get("start", {})
        lines.append(f"  {o.get('filename', '?')}:{start.get('line', '?')}:{start.get('column', '?')} "
                     f"[{o.get('severity', '?')}] {o.get('code', '?')} -- {o.get('message', '')}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="herb_lint.py", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("paths", nargs="*")
    a = parser.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root).resolve()
    argv_, note = command(root, a.paths or default_paths(root))
    if argv_ is None:
        print(f"FAIL: {note}", file=sys.stderr)
        return 2
    print(f"NOTE: {note}")
    sys.stdout.flush()
    proc = subprocess.run([*argv_, "--format", "json"], cwd=root, capture_output=True, text=True)
    lines = render(proc.stdout)
    if lines is None:
        # Not herb's JSON (an older linter, a crash): the raw output, and the linter's own verdict.
        sys.stdout.write(proc.stdout)
    else:
        print("\n".join(lines))
    sys.stderr.write(proc.stderr)
    return proc.returncode


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    lock = ("GEM\n  remote: https://rubygems.org/\n  specs:\n"
            "    erb_lint (0.9.0)\n      herb (>= 0.9)\n"
            "    herb (0.10.3-aarch64-linux-gnu)\n    herb (0.10.3-arm64-darwin)\n"
            "    i18n (1.15.2)\n\nPLATFORMS\n  arm64-darwin\n")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check("no Gemfile.lock -> no version", locked_version(root) is None)
        argv_, note = command(root, ["app/views"])
        check("no herb locked -> no command, and it says why", argv_ is None and "not in Gemfile.lock" in note, note)

        (root / "Gemfile.lock").write_text(lock, encoding="utf-8")
        check("the platform-suffixed spec line gives 0.10.3", locked_version(root) == "0.10.3", str(locked_version(root)))
        argv_, note = command(root, ["app/views"])
        check("npx is pinned to the locked version",
              argv_ == ["npx", "-y", "@herb-tools/linter@0.10.3", "app/views"], str(argv_))
        check("...and the note names that version", "0.10.3" in note, note)

        # A dependency constraint under another gem must not read as the lock.
        (root / "Gemfile.lock").write_text(
            "GEM\n  specs:\n    erb_lint (0.9.0)\n      herb (>= 0.9)\n", encoding="utf-8")
        check("a six-space constraint is not a locked version", locked_version(root) is None,
              str(locked_version(root)))
        (root / "Gemfile.lock").write_text("GEM\n  specs:\n    herb (0.11.0)\n", encoding="utf-8")
        check("a plain spec line gives its version", locked_version(root) == "0.11.0", str(locked_version(root)))

        # A project-local binary wins: package.json pinned it.
        bin_dir = root / "node_modules" / ".bin"
        bin_dir.mkdir(parents=True)
        local = bin_dir / "herb-lint"
        local.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        local.chmod(0o755)
        argv_, note = command(root, ["app/views"])
        check("a local node_modules binary is preferred", argv_ == [str(local), "app/views"], str(argv_))
        check("...and the note says it came from package.json", "package.json" in note, note)

        # THE ENTRY POINT: main exits with the linter's status and prints the note first.
        local.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True)
        check("main passes the linter's exit status through", proc.returncode == 7, f"rc={proc.returncode}")
        check("main prints the NOTE naming the linter", proc.stdout.startswith("NOTE: herb linter"), proc.stdout)
        # #1296 THE SCOPE, through main: a fake linter records the paths it was handed. Only while the fake
        # is the binary in use -- otherwise main would reach a REAL npx, which hangs the selftest and hides
        # the fixture above that should have caught the break.
        record = root / "args.txt"

        def _paths(rec: Path) -> list[str]:
            """The paths the linter was handed, without the `--format json` the wrapper adds."""
            return [a for a in rec.read_text().split() if a not in ("--format", "json")]
        local.write_text(f'#!/bin/sh\necho "$@" > {record}\nexit 0\n', encoding="utf-8")
        (root / "app" / "views").mkdir(parents=True)
        if (command(root, [])[0] or [""])[0] == str(local):
            subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True)
            check("CONTROL: with only app/views, only app/views is linted",
                  _paths(record) == ["app/views"], record.read_text())
            (root / "app" / "components").mkdir()
            subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True)
            check("with app/components present, component templates are linted too",
                  _paths(record) == ["app/views", "app/components"], record.read_text())
            subprocess.run([sys.executable, __file__, "--root", str(root), "app/views"], capture_output=True, text=True)
            check("explicit paths still override the default", _paths(record) == ["app/views"],
                  record.read_text())

        # #1318 THE ORDER: herb prints a HINT before an ERROR (file order); the row must lead with counts
        # and the error must come first. The fake linter emits real 0.10.3 JSON and fails at error.
        sample = {"offenses": [
            {"filename": "app/views/a.html.erb", "message": "Empty if block", "severity": "hint",
             "code": "erb-no-empty-control-flow", "location": {"start": {"line": 8, "column": 0}}},
            {"filename": "app/views/b.html.erb", "message": "Bad comment", "severity": "error",
             "code": "erb-comment-syntax", "location": {"start": {"line": 46, "column": 2}}}],
            "summary": {"filesChecked": 2, "totalErrors": 1, "totalHints": 1}}
        payload = root / "herb.json"
        payload.write_text(json.dumps(sample), encoding="utf-8")
        local.write_text(f"#!/bin/sh\ncat {payload}\nexit 1\n", encoding="utf-8")
        if (command(root, [])[0] or [""])[0] == str(local):
            proc = subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True)
            out = [l for l in proc.stdout.splitlines() if not l.startswith("NOTE:")]
            check("the summary line leads, with counts per severity",
                  bool(out) and out[0].startswith("2 herb finding(s): 1 error, 0 warning, 0 info, 1 hint"), repr(out[:1]))
            check("the ERROR is listed before the hint that herb printed first",
                  len(out) >= 3 and "[error]" in out[1] and "[hint]" in out[2], repr(out[1:3]))
            check("...and the linter's failure still fails", proc.returncode == 1, f"rc={proc.returncode}")
        check("render: output that is not herb's JSON is left to the caller", render("not json") is None)

        (root / "Gemfile.lock").unlink()
        local.unlink()
        proc = subprocess.run([sys.executable, __file__, "--root", str(root)], capture_output=True, text=True)
        check("main exits 2 when no version can be pinned, never 0", proc.returncode == 2, f"rc={proc.returncode}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"herb_lint selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
