#!/usr/bin/env python3
"""Refuse a coverage setup that cannot catch a regression (#800).

WHY THIS EXISTS. `testing.md` shipped `minimum_coverage 90` **commented out**, with *"enable once
realistic"*, and §11 repeated *"once the number is honest"*. Nothing ever makes it realistic, so it
stays commented for the life of the project and coverage is unenforced from the first commit to the
last. A downstream project reasoned it out correctly -- *"one set above where a repo sits turns every
run red and gets switched off in a week"* -- which is true of a FIXED threshold, and left nothing in
its place.

THE RATCHET IS THE INSTRUMENT. `refuse_coverage_drop` compares against `coverage/.last_run.json`, so
the floor is wherever the repo already sits: never red on day one, never sliding, and rising by
itself as specs are written.

AND IT CAN GATE HONESTLY, which a threshold cannot. "Is 83% good?" is judgement, and `quality-pass`
is right that gating judgement gets it switched off. A **drop** is not judgement -- it is a measured
regression against a recorded baseline, the same class as this repo's own drift gates. Maintainer
decision on #800: *"gate is the key, advise can be ignored."*

THREE CLAUSES, all STATIC so they hold on a fresh scaffold before any suite has run. Deliberately NOT
"does `coverage/.last_run.json` exist" -- it appears only after the first run, and demanding it would
fail a correct project for not having run yet. What is checked is the configuration that decides
whether the ratchet works at all.

NOT APPLICABLE when `simplecov` is not declared. A project that never adopted it has nothing here to
get wrong, and demanding coverage tooling from one that chose otherwise is the false positive that
gets a gate switched off (#476).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

GEMFILE = Path("Gemfile")
GITIGNORE = Path(".gitignore")
SPEC = Path("spec")

GEM = re.compile(r"""^\s*gem\s+(?P<q>['"])(?P<name>[A-Za-z0-9_\-]+)(?P=q)""")
RATCHET = re.compile(r"\brefuse_coverage_drop\b")
# A NUMBER is required. `minimum_coverage_by_file line: 0` is prescribed and must not be flagged, and
# neither must a bare mention in prose -- only the fixed-threshold form the doctrine now forbids.
FIXED_THRESHOLD = re.compile(r"\bminimum_coverage\s+\d")
IGNORES_COVERAGE = re.compile(r"^\s*/?coverage/?\s*$")
KEEPS_LAST_RUN = re.compile(r"^\s*!\s*/?coverage/\.last_run\.json\s*$")


def uncommented(text: str, pattern: re.Pattern) -> bool:
    """Match on a line that is not commented out.

    Line by line: the defect this replaces was a line shipped COMMENTED, and a whole-file search
    would match it and report the exact problem as solved.
    """
    return any(pattern.search(line) for line in text.splitlines()
               if not line.lstrip().startswith("#"))


def declared_gems(gemfile: str) -> set[str]:
    return {m.group("name") for m in (GEM.match(l) for l in gemfile.splitlines()) if m}


def problems(spec_text: str, gitignore: str | None) -> list[str]:
    found: list[str] = []
    if not uncommented(spec_text, RATCHET):
        found.append(
            "no `refuse_coverage_drop` in the SimpleCov config, so a change that lowers coverage "
            "passes.\n"
            "    A fixed threshold is the wrong instrument in both directions — below where the "
            "repo sits it is inert, above it every run is red and it gets switched off.\n"
            "    Add:  refuse_coverage_drop :line, :branch")
    if uncommented(spec_text, FIXED_THRESHOLD):
        found.append(
            "`minimum_coverage <n>` is set. testing.md §11 forbids it: it is either below the repo "
            "(inert) or above it (red on day one).\n"
            "    Gate the DROP instead — `refuse_coverage_drop`. `minimum_coverage_by_file line: 0` "
            "is fine and is not this.")
    if gitignore is not None:
        lines = gitignore.splitlines()
        if any(IGNORES_COVERAGE.match(l) for l in lines) and not any(
                KEEPS_LAST_RUN.match(l) for l in lines):
            found.append(
                ".gitignore excludes `coverage/` with no exception for `.last_run.json`, so the "
                "ratchet has no memory in CI — every run compares against nothing.\n"
                "    Add:  !/coverage/.last_run.json")
    return found


def run(root: Path = Path(".")) -> tuple[int, str]:
    """(exit, message). 0 pass, 1 fail, 3 not-applicable."""
    gemfile = root / GEMFILE
    if not gemfile.is_file() or "simplecov" not in declared_gems(
            gemfile.read_text(encoding="utf-8")):
        return 3, ("not applicable — `simplecov` is not declared in this project "
                   "(nothing to check, NOT a pass)")
    spec_text = "\n".join(p.read_text(encoding="utf-8")
                          for p in (root / SPEC).glob("**/*.rb")) if (root / SPEC).is_dir() else ""
    gi = root / GITIGNORE
    found = problems(spec_text, gi.read_text(encoding="utf-8") if gi.is_file() else None)
    if not found:
        return 0, "coverage ratchets — a drop fails the suite"
    return 1, f"{len(found)} finding(s):\n" + "\n".join(f"  - {f}" for f in found)


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def verdict(spec: str | None, *, gemfile: str = 'gem "simplecov"\n',
                gitignore: str | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Gemfile").write_text(gemfile, encoding="utf-8")
            if spec is not None:
                (root / "spec").mkdir()
                (root / "spec" / "spec_helper.rb").write_text(spec, encoding="utf-8")
            if gitignore is not None:
                (root / ".gitignore").write_text(gitignore, encoding="utf-8")
            return run(root)

    RATCHETED = 'SimpleCov.start "rails" do\n  refuse_coverage_drop :line, :branch\nend\n'

    # ---- CLAUSE 1: no ratchet ------------------------------------------------------------------
    code, msg = verdict('SimpleCov.start "rails" do\n  enable_coverage :branch\nend\n')
    check("a SimpleCov config with no ratchet FAILS", code == 1, f"exit {code}")
    check("...saying a drop would pass", "lowers coverage" in msg, msg[:130])

    # THE REPORTED SHAPE: shipped COMMENTED with "enable once realistic". A whole-file search would
    # match it and call the exact defect solved.
    code, _ = verdict('SimpleCov.start "rails" do\n  # refuse_coverage_drop :line, :branch\nend\n')
    check("a COMMENTED ratchet still fails", code == 1)

    # THE PASS, or clause 1 could be "always fail".
    code, _ = verdict(RATCHETED)
    check("a ratcheted config passes", code == 0)

    # ---- CLAUSE 2: the forbidden instrument ----------------------------------------------------
    code, msg = verdict(RATCHETED.replace("end\n", "  minimum_coverage 90\nend\n"))
    check("a fixed minimum_coverage FAILS even with the ratchet", code == 1, f"exit {code}")
    check("...saying it is inert or red on day one", "red on day one" in msg, msg[:150])
    # A COMMENTED one is inert and not the defect -- flagging it would fire on a project that left
    # a note explaining why it is not used.
    code, _ = verdict(RATCHETED.replace("end\n", "  # minimum_coverage 90\nend\n"))
    check("a commented minimum_coverage is not flagged", code == 0)
    # AND the prescribed per-file floor must NOT be mistaken for it: it carries no bare number.
    code, _ = verdict(RATCHETED.replace("end\n", "  minimum_coverage_by_file line: 0\nend\n"))
    check("minimum_coverage_by_file is not the forbidden form", code == 0)

    # ---- CLAUSE 3: the ratchet's memory --------------------------------------------------------
    code, msg = verdict(RATCHETED, gitignore="/coverage/\n")
    check("ignoring coverage/ with no exception FAILS", code == 1, f"exit {code}")
    check("...saying the ratchet has no memory", "no memory in CI" in msg, msg[:140])
    code, _ = verdict(RATCHETED, gitignore="/coverage/\n!/coverage/.last_run.json\n")
    check("...and passes with the exception", code == 0)
    code, _ = verdict(RATCHETED, gitignore="log/\ntmp/\n")
    check("a .gitignore not mentioning coverage is fine", code == 0)

    # ---- NOT APPLICABLE, never a pass ----------------------------------------------------------
    code, msg = verdict(RATCHETED, gemfile='gem "rails"\n')
    check("no simplecov is not-applicable, not a pass", code == 3, f"exit {code}")
    check("...and says so rather than reporting clean", "NOT a pass" in msg, msg)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} coverage-ratchet assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, msg = run()
    print(msg, file=sys.stderr if code == 1 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
