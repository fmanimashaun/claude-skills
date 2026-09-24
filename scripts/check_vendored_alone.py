#!/usr/bin/env python3
"""A script a project vendors ALONE must pass its own --selftest alone (#1261).

Run:  python3 scripts/check_vendored_alone.py
      python3 scripts/check_vendored_alone.py --selftest

WHAT BROKE. `architecture_graph.py` and `build_project_wiki.py` read an optional sibling,
`generated_docs.py`, and say in their docstrings that a copy vendored ALONE keeps working. Their
runtime paths did. Their selftests did not: each asserted the with-sibling result unconditionally,
so a project that vendored one file and ran its selftest in CI (Retask) went red on a plain sync.

WHY NOTHING HERE SAW IT. Every selftest in this repo runs from `plugins/<name>/scripts/`, where the
sibling always exists. The state a project is told to create -- one file copied into
`.claude/scripts/` -- was never the state anything ran in.

WHICH SCRIPTS. Derived, never listed by hand, from two places:
  1. every `.claude/scripts/<name>.py` a shipped command, skill or reference tells a project to create;
  2. every plugin script whose own source promises to work "vendored ALONE".
Each is copied by itself into an empty directory, with PYTHONPATH cleared, and its `--selftest` run
there. A script named in (1) that no plugin ships is a finding too: the doc points at nothing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDORED_PATH = re.compile(r"\.claude/scripts/([a-z_]+\.py)")
ALONE_PROMISE = "vendored ALONE"
DOC_ROOTS = ("plugins", "skills")


def discover(repo: Path) -> tuple[list[Path], list[str]]:
    """The vendorable scripts, and a finding for each vendoring instruction naming no shipped script."""
    named: set[str] = set()
    for root in DOC_ROOTS:
        for doc in sorted((repo / root).rglob("*.md")):
            named.update(VENDORED_PATH.findall(doc.read_text(encoding="utf-8", errors="replace")))
    shipped = {p.name: p for p in sorted(repo.glob("plugins/*/scripts/*.py"))}
    found: dict[str, Path] = {}
    problems: list[str] = []
    for name in sorted(named):
        if name in shipped:
            found[name] = shipped[name]
        else:
            problems.append(f"a doc tells projects to vendor .claude/scripts/{name}, and no plugin ships it")
    for name, path in shipped.items():
        if ALONE_PROMISE in path.read_text(encoding="utf-8", errors="replace"):
            found[name] = path
    return [found[n] for n in sorted(found)], problems


def run_alone(script: Path) -> tuple[int, str]:
    """Run `script --selftest` as the only file in an empty directory."""
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / script.name
        shutil.copy2(script, copy)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run([sys.executable, copy.name, "--selftest"], cwd=td, env=env,
                              capture_output=True, text=True, timeout=600)
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-3:])
        return proc.returncode, tail


def findings(repo: Path) -> tuple[list[str], int]:
    scripts, problems = discover(repo)
    for script in scripts:
        rc, tail = run_alone(script)
        if rc != 0:
            problems.append(f"{script.relative_to(repo)} fails --selftest when vendored alone (rc={rc}): {tail}")
    return problems, len(scripts)


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{name} {detail}".rstrip())

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        scripts = repo / "plugins" / "p" / "scripts"
        scripts.mkdir(parents=True)
        (repo / "skills").mkdir()
        (scripts / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
        # Needs its sibling unconditionally: passes in the plugin dir, fails alone.
        (scripts / "needy.py").write_text(
            "import sys\nimport helper\nsys.exit(0 if helper.VALUE == 1 else 1)\n", encoding="utf-8")
        # Reads the sibling only when present, as #1261's fix does.
        (scripts / "tolerant.py").write_text(
            '"""Works vendored ALONE."""\nimport sys\ntry:\n    import helper\nexcept ImportError:\n'
            "    helper = None\nsys.exit(0)\n", encoding="utf-8")
        (scripts / "unrelated.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        (repo / "plugins" / "p" / "setup.md").write_text(
            "Copy it to `.claude/scripts/needy.py`.\n", encoding="utf-8")
        (repo / "skills" / "s.md").write_text("Vendor `.claude/scripts/ghost.py`.\n", encoding="utf-8")

        # THE CONTROL: needy.py passes where the plugin runs it, so only isolation can catch it.
        control = subprocess.run([sys.executable, "needy.py"], cwd=scripts, capture_output=True)
        check("control: the needy fixture passes beside its sibling", control.returncode == 0)

        found, problems = discover(repo)
        names = [p.name for p in found]
        check("a script a doc tells projects to vendor is discovered", "needy.py" in names, str(names))
        check("a script that promises to work vendored alone is discovered", "tolerant.py" in names, str(names))
        check("a script neither named nor promising is not run", "unrelated.py" not in names, str(names))
        check("a vendoring instruction naming no shipped script is a finding",
              any("ghost.py" in p for p in problems), str(problems))

        rc, _ = run_alone(scripts / "needy.py")
        check("a script that needs its sibling fails when run alone", rc != 0, f"rc={rc}")
        rc, _ = run_alone(scripts / "tolerant.py")
        check("a script that tolerates a missing sibling passes alone", rc == 0, f"rc={rc}")

        all_problems, count = findings(repo)
        check("the needy script is reported", any("needy.py fails" in p for p in all_problems), str(all_problems))
        check("the tolerant script is not reported", not any("tolerant.py" in p for p in all_problems))
        check("both discovered scripts were run", count == 2, f"count={count}")

    if failures:
        print(f"check_vendored_alone selftest: {len(failures)} failure(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("check_vendored_alone selftest: all checks passed")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    if argv[1:] in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    problems, count = findings(REPO)
    if count == 0:
        print("FAIL: no vendorable script was discovered, so nothing was checked")
        return 1
    if problems:
        print(f"FAIL: {len(problems)} vendored-alone finding(s) across {count} script(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"ok: {count} vendorable script(s) pass --selftest alone")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
