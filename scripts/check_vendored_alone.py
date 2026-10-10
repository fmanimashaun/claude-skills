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

WHICH SCRIPTS. Derived, never listed by hand, from three places (#1767 widened it from two, which missed `generated_docs.py`: a
doc said "Vendor `generated_docs.py` beside `architecture_graph.py`", by bare name, and its own source said "vendors this file"):
  1. every `.claude/scripts/<name>.py` a shipped command, skill or reference tells a project to create;
  2. every shipped script a doc paragraph names in backticks next to a vendoring verb ("Vendor `x.py` beside ..."), or that a doc tells a
     project to copy or drop in with the verb right beside the name ("Copy `x.py` into ...", "Drop in `x.py`");
  3. every plugin script whose own source promises to work "vendored ALONE", or says it is vendored or vendors this file.
Each is copied by itself into an empty directory, with PYTHONPATH cleared, and its `--selftest` run
there. A script named in (1) that no plugin ships is a finding too: the doc points at nothing.
THE LIMIT: this repo can only know a script is vendored from what its docs and sources say. The way to put the next one under the gate is
to say so where a project is told to vendor it (a paragraph with "vendor" and the name in backticks), which this reads.
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
VENDORED_PATH = re.compile(r"\.claude/scripts/([a-z0-9_]+\.py)")
ALONE_PROMISE = "vendored ALONE"
# A script saying of ITSELF that it is vendored, or that a project vendors this file ("until it vendors this file too").
PROMISE_WORDING = re.compile(r"vendor(?:ed|s|ing)?\s+(?:alone|this\s+file)|vendorable", re.I)
# A vendoring VERB, not the `vendor/` directory ("skips vendor/", "the vendor directory").
VENDOR_VERB = re.compile(r"(?<![/\w])vendor(?:s|ed|ing)?\b(?!/)(?!\s+(?:dir|folder))", re.I)
BACKTICKED_SCRIPT = re.compile(r"`([a-z0-9_]+\.py)`")
# "Copy `x.py` ...", "drop in `x.py`", "drop `x.py` in ...": the verb must sit RIGHT BESIDE the name (an article may sit between). NOT a paragraph
# window like `vendor`: "copy" is an everyday word, and measured on the real docs a paragraph rule would pull in five scripts that are only
# mentioned (blast_radius, brand_pack_lint, check_criteria, check_surface_layout, validate_evidence); the adjacent form adds none.
_ARTICLE = r"(?:the\s+|a\s+|your\s+)?"
INSTRUCTED_COPY = (
    re.compile(r"\b(?:copy|copies|copied|copying)\s+" + _ARTICLE + r"`([a-z0-9_]+\.py)`", re.I),
    re.compile(r"\bdrop\s+in\s+" + _ARTICLE + r"`([a-z0-9_]+\.py)`", re.I),
    re.compile(r"\bdrop(?:s|ped|ping)?\s+" + _ARTICLE + r"`([a-z0-9_]+\.py)`\s+in\b", re.I),
)
DOC_ROOTS = ("plugins", "skills")


def discover(repo: Path) -> tuple[list[Path], list[str]]:
    """The vendorable scripts, and a finding for each vendoring instruction naming no shipped script."""
    named: set[str] = set()
    told: set[str] = set()
    for root in DOC_ROOTS:
        for doc in sorted((repo / root).rglob("*.md")):
            text = doc.read_text(encoding="utf-8", errors="replace")
            named.update(VENDORED_PATH.findall(text))
            for instructed in INSTRUCTED_COPY:
                told.update(instructed.findall(text))
            for paragraph in re.split(r"\n\s*\n", text):
                if VENDOR_VERB.search(paragraph):
                    told.update(BACKTICKED_SCRIPT.findall(paragraph))
    shipped = {p.name: p for p in sorted(repo.glob("plugins/*/scripts/*.py"))}
    found: dict[str, Path] = {}
    problems: list[str] = []
    for name in sorted(told):
        if name in shipped:
            found[name] = shipped[name]
    for name in sorted(named):
        if name in shipped:
            found[name] = shipped[name]
        else:
            problems.append(f"a doc tells projects to vendor .claude/scripts/{name}, and no plugin ships it")
    for name, path in shipped.items():
        source = path.read_text(encoding="utf-8", errors="replace")
        if ALONE_PROMISE in source or PROMISE_WORDING.search(source):
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
        # #1767: THREE MORE SHAPES THE FIRST TWO MISSED. `barely.py` is named by a doc by its BARE name next to a vendoring verb;
        # `wording.py` says of itself that a project vendors it, in words other than "vendored ALONE". Both need `helper.py`, so only
        # isolation can catch them. `ignored.py` sits beside the vendor DIRECTORY and `mentioned.py` beside no vendoring verb: neither is run.
        needy = "import sys\nimport helper\nsys.exit(0 if helper.VALUE == 1 else 1)\n"
        (scripts / "barely.py").write_text(needy, encoding="utf-8")
        (scripts / "wording.py").write_text('"""A project that vendors this file keeps working."""\n' + needy, encoding="utf-8")
        (scripts / "ignored.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        (scripts / "mentioned.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        # #1773 review: a DIGIT in a script's name (`check_i18n_setup.py` exists), reached by both name patterns; "copy" and "drop in" as the verb
        # right beside the name; and two scripts that only sit near the word copy, which must NOT be run.
        for name in ("step2", "path3", "copyme", "dropme", "dropme2"):
            (scripts / f"{name}.py").write_text(needy, encoding="utf-8")
        for name in ("copied_only", "far"):
            (scripts / f"{name}.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        (repo / "plugins" / "p" / "setup2.md").write_text("Put it at `.claude/scripts/path3.py`.\n", encoding="utf-8")
        (repo / "plugins" / "p" / "vendoring.md").write_text(
            "Vendor `barely.py` by itself, and nothing else.\n\n"
            "The vendor directory is skipped by `ignored.py`.\n\n"
            "Run `mentioned.py` after every change.\n\n"
            "Vendor `step2.py` as well.\n\n"
            "Copy `copyme.py` into your project.\n\n"
            "Drop in `dropme.py` beside your hooks.\n\n"
            "Drop `dropme2.py` in your project.\n\n"
            "Keep a copy of `copied_only.py` in the notes.\n\n"
            "Copy the report, then run `far.py`.\n", encoding="utf-8")

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
        check("a script a doc tells projects to vendor by its bare name is discovered", "barely.py" in names, str(names))
        check("a script whose source says a project vendors it is discovered", "wording.py" in names, str(names))
        check("a script named only beside the vendor DIRECTORY is not run", "ignored.py" not in names, str(names))
        check("a script a doc names without a vendoring verb is not run", "mentioned.py" not in names, str(names))
        check("a script with a digit in its name, named beside a vendoring verb, is discovered", "step2.py" in names, str(names))
        check("a script under .claude/scripts with a digit in its name is discovered", "path3.py" in names, str(names))
        check("a script a doc tells projects to copy, with the verb beside its name, is discovered", "copyme.py" in names, str(names))
        check("a script a doc tells projects to drop in is discovered", "dropme.py" in names, str(names))
        check("a script a doc tells projects to drop in, the verb before its name and in after it, is discovered", "dropme2.py" in names, str(names))
        check("a script only near the word copy, not beside it as a verb, is not run", "copied_only.py" not in names and "far.py" not in names, str(names))

        rc, _ = run_alone(scripts / "needy.py")
        check("a script that needs its sibling fails when run alone", rc != 0, f"rc={rc}")
        rc, _ = run_alone(scripts / "tolerant.py")
        check("a script that tolerates a missing sibling passes alone", rc == 0, f"rc={rc}")

        all_problems, count = findings(repo)
        check("the needy script is reported", any("needy.py fails" in p for p in all_problems), str(all_problems))
        check("the tolerant script is not reported", not any("tolerant.py" in p for p in all_problems))
        check("the bare-name script is reported", any("barely.py fails" in p for p in all_problems), str(all_problems))
        check("the script that says a project vendors it is reported", any("wording.py fails" in p for p in all_problems), str(all_problems))
        check("every discovered script was run", count == 9, f"count={count}")

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
