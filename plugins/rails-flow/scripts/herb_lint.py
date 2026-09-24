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

Run:  herb_lint.py [--root DIR] [PATHS...]      (default path: app/views)
      herb_lint.py --selftest
Exit: the linter's own exit status; 2 when herb is not in Gemfile.lock (never reported as clean).
Every run prints `NOTE: herb linter <version> (<source>)`, so a verdict names the linter that gave it.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# A spec line in Gemfile.lock sits at four spaces; a dependency constraint sits at six, so anchoring
# the indent keeps `      herb (>= 0.10)` under another gem from reading as the locked version.
LOCKED = re.compile(r"^ {4}herb \((\d+\.\d+\.\d+)(?:[-.][^)]*)?\)$", re.M)


def locked_version(root: Path) -> str | None:
    lock = root / "Gemfile.lock"
    if not lock.is_file():
        return None
    found = LOCKED.findall(lock.read_text(encoding="utf-8"))
    return found[0] if found else None


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="herb_lint.py", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("paths", nargs="*")
    a = parser.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root).resolve()
    argv_, note = command(root, a.paths or ["app/views"])
    if argv_ is None:
        print(f"FAIL: {note}", file=sys.stderr)
        return 2
    print(f"NOTE: {note}")
    sys.stdout.flush()
    return subprocess.run(argv_, cwd=root).returncode


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
