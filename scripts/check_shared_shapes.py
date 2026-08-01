#!/usr/bin/env python3
"""Reconcile the duplication counts in shipped doctrine against the repo they describe.

Run:  python3 scripts/check_shared_shapes.py            # measure, fail on a stale count
      python3 scripts/check_shared_shapes.py --selftest  # prove the rules fire AND stay silent

WHY (#360). `skills/quality-pass/references/worked-example.md` is a worked example of the reuse
dimension applied to this repo's own Python. It states how many files carry each shared shape, and
it records an extraction decision that rests on those numbers. A count written in prose rots the
moment someone adds a fifth copy -- and it rots SILENTLY, because nothing reads it. That is the
`claims-vs-enforcement` class the `code-review` skill is built around, sitting inside the skill
next door to it.

WHAT THIS IS NOT. It is **not** a duplication gate. Nothing here blocks a change for copying code;
the quality pass is advisory by design and a gate on taste would contradict the doctrine it guards.
The only thing that can fail here is a **number in shipped doctrine disagreeing with the repo** --
exactly what `check_handoff.py` does for the model-tier tables. Fix the doc, or remove the copy;
the check does not care which, it only refuses to let the two drift.

THE TABLE IS THE JOIN. Each row's first column must name a shape this file measures, and each shape
must have a row. Both directions, because a shape with no row is a measurement nobody reads and a
row with no shape is prose nothing measures.

Exit codes:  0 the doctrine matches the repo · 1 it does not · 2 the doc could not be read

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "skills" / "quality-pass" / "references" / "worked-example.md"

# Where the shapes are counted. `scripts/` is included deliberately: it is maintainer tooling that
# never ships, and half the worked example's point is that a copy on the far side of a distribution
# boundary is legitimate. Excluding it would hide the very evidence the example rests on.
ROOTS = ("plugins", "scripts")

BEGIN = "<!-- shared-shapes:begin -->"
END = "<!-- shared-shapes:end -->"

# A row of the marked table: `| label | 4 | where |`. The digit column is what rejects the header
# and the `|---|` separator, so no extra parsing state is needed.
ROW = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<files>\d+)\s*\|")


@dataclass(frozen=True)
class Shape:
    """One duplicated shape the worked example names, and how to count it."""

    label: str      # must equal the table row's first column, verbatim
    pattern: str    # matched per-file, MULTILINE, against the whole source
    # What the shape IS, in words -- printed when the pattern stops matching, which is the one
    # moment a reader needs it and the source is no help. A field nothing reads is the
    # `dead-declaration` class; this one is read on the path that matters.
    why: str


SHAPES: tuple[Shape, ...] = (
    Shape(
        "`class Unusable(RuntimeError)`",
        r"^class Unusable\(RuntimeError\):",
        "the refusal type every qa-flow judge declares for itself",
    ),
    Shape(
        "the `json.loads` -> `Unusable` prologue",
        r'raise Unusable\(f"\{path\}: \{exc\}"\) from exc',
        "the five lines each judge's `load()` opens with before its own validation diverges",
    ),
    Shape(
        "the `check(label, ok, detail)` selftest harness",
        r'^\s+def check\(label: str, ok: bool, detail: str = ""\) -> None:',
        "the nested fixture recorder; the largest single shared unit in the repo",
    ),
    Shape(
        "the `SELFTEST FAILED --` reporter",
        r'print\(f"SELFTEST FAILED -- \{len\(failures\)\} of \{\w+\} checks:", file=sys\.stderr\)',
        "the six-line failure report that closes every selftest",
    ),
    Shape(
        "WCAG relative luminance",
        r"0\.2126 \*",
        "the sRGB-to-linear formula, implemented once in a shipped plugin and once in tooling",
    ),
)


class Unreadable(RuntimeError):
    """The doctrine file did not yield a table -- reported, never a silent pass."""


def sources(root: Path) -> list[Path]:
    """Every Python file under the measured roots of `root`.

    `root` is required rather than defaulted to REPO so the selftest can point every rule at a
    synthetic corpus. That is not a convenience: the mutation checker runs this file's selftest
    from a temp directory containing the module and nothing else, and a fixture that needs the
    real tree would die there on a missing corpus -- reading as a caught mutation when it is only
    a crash, and a crash is not a verdict.
    """
    out: list[Path] = []
    for top in ROOTS:
        top_dir = root / top
        if top_dir.is_dir():
            out.extend(sorted(top_dir.rglob("*.py")))
    return out


def measure(shape: Shape, files: list[Path]) -> list[Path]:
    rx = re.compile(shape.pattern, re.M)
    return [p for p in files if rx.search(p.read_text(encoding="utf-8"))]


def declared(text: str) -> dict[str, int]:
    """{label: file count} from the marked table, or raise."""
    if BEGIN not in text or END not in text:
        raise Unreadable(
            f"{DOC.name}: no {BEGIN} / {END} markers. Without them this check would parse whatever "
            "table it found first, which is how a gate starts reading the wrong input.")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    rows: dict[str, int] = {}
    for line in block.splitlines():
        m = ROW.match(line.strip())
        if m:
            rows[m.group("label").strip()] = int(m.group("files"))
    if not rows:
        raise Unreadable(f"{DOC.name}: the marked table has no rows with a file count")
    return rows


def reconcile(text: str, root: Path,
              shapes: tuple[Shape, ...] = SHAPES) -> list[str]:
    """Findings, one string each. Empty means the doctrine matches the repo.

    `shapes` is a parameter rather than a read of the module global so the selftest can add a
    deliberately-dead shape without mutating state the next fixture would inherit.
    """
    rows = declared(text)
    files = sources(root)
    findings: list[str] = []

    for shape in shapes:
        hits = measure(shape, files)
        # A pattern that matches nothing is a rule that went quiet. Reported even if the table
        # happens to say 0, because "0 == 0" is exactly how a rotted regex reads as a pass.
        if not hits:
            findings.append(
                f"{shape.label}: the pattern matches NOTHING under {'/, '.join(ROOTS)}/. It counts "
                f"{shape.why}. Either the shape is gone (delete the row) or the pattern rotted "
                f"(fix it) -- a measurement that counts zero is not a measurement.")
            continue
        if shape.label not in rows:
            findings.append(
                f"{shape.label}: measured in {len(hits)} file(s) and has NO row in the table. A "
                f"count nobody reads is not doctrine.")
            continue
        if rows[shape.label] != len(hits):
            where = ", ".join(str(p.relative_to(root)) for p in hits)
            findings.append(
                f"{shape.label}: the table says {rows[shape.label]}, the repo has {len(hits)} "
                f"-- {where}")

    for label in rows:
        if label not in {s.label for s in shapes}:
            findings.append(
                f"{label}: a table row naming a shape nothing here measures. Add it to SHAPES or "
                f"remove the row; prose with no measurement behind it is the class this guards.")
    return findings


def run() -> int:
    try:
        findings = reconcile(DOC.read_text(encoding="utf-8"), REPO)
    except (OSError, Unreadable) as exc:
        print(f"CANNOT RECONCILE: {exc}", file=sys.stderr)
        return 2
    if findings:
        print(f"{len(findings)} stale claim(s) in {DOC.relative_to(REPO)}:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print("\nThis is not a duplication gate. Either the copy is new and the number needs "
              "updating, or the copy went away and the number needs updating.", file=sys.stderr)
        return 1
    print(f"{len(SHAPES)} shared shapes; {DOC.relative_to(REPO)} matches the repo.")
    return 0


def _table(rows: dict[str, int]) -> str:
    body = "\n".join(f"| {label} | {n} | somewhere |" for label, n in rows.items())
    return f"{BEGIN}\n\n| shape | files | where |\n|---|---|---|\n{body}\n\n{END}\n"


# A corpus carrying known copies of the real SHAPES, laid out as the real roots are. Synthetic on
# purpose: every fixture below must run with nothing but this module on disk, because that is the
# condition the mutation checker runs it under.
#
# WHY THE PLACEHOLDERS. `scripts/` is inside the measured roots, so this file is part of its own
# corpus -- and a fixture written literally would make the measuring file a phantom member of the
# shapes it measures. The first run proved it: `Unusable` jumped 4 -> 5 and luminance 2 -> 3, all
# three of them string literals in this comment's neighbourhood. Substituting at write time (the
# same trick `lint_markdown_shell.py` uses on its templates) keeps the fixture honest without
# exempting this file from the walk -- a self-exemption is the carve-out class, and it would also
# hide a genuine copy landing here later.
_SUBS = {"@EXC@": "Unusable", "@COEF@": "0.2126"}

_A = '''\
class @EXC@(RuntimeError):
    """x"""


def load(path):
    try:
        data = 1
    except ValueError as exc:
        raise @EXC@(f"{path}: {exc}") from exc
    return data


def selftest():
    failures = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(label)

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
    return 0


LUM = @COEF@ * 1.0
'''

_B = '''\
class @EXC@(RuntimeError):
    """y"""


def selftest():
    failures = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
'''

_C = '''\
def selftest():
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
'''

# What `_corpus` below must measure to. Written out rather than derived from the corpus by the
# same code under test: a fixture derived from its subject cannot witness that subject shrinking.
_CORPUS_TRUTH = {
    "`class Unusable(RuntimeError)`": 2,
    "the `json.loads` -> `Unusable` prologue": 1,
    "the `check(label, ok, detail)` selftest harness": 3,
    "the `SELFTEST FAILED --` reporter": 1,
    "WCAG relative luminance": 1,
}


def _corpus(tmp: Path) -> Path:
    for rel, body in (("plugins/demo/scripts/a.py", _A),
                      ("plugins/demo/scripts/b.py", _B),
                      ("scripts/c.py", _C)):
        for token, value in _SUBS.items():
            body = body.replace(token, value)
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="shared-shapes-") as tmpdir:
        root = _corpus(Path(tmpdir))
        files = sources(root)
        check("the source walk finds the corpus files", len(files) == 3,
              f"found {[str(p) for p in files]}")

        truth = dict(_CORPUS_TRUTH)
        measured = {s.label: len(measure(s, files)) for s in SHAPES}
        check("every declared shape is measured at its known count in the corpus",
              measured == truth, f"{measured} != {truth}")

        # SILENCE, and it is the half that matters: a table stating the true counts must be
        # clean. A checker that fires on correct input is a checker that gets switched off.
        out = reconcile(_table(truth), root)
        check("a table stating the true counts is silent", out == [], f"{out}")

        # FIRES: a count that disagrees.
        first = SHAPES[0].label
        out = reconcile(_table({**truth, first: truth[first] + 1}), root)
        check("a wrong count in the table is DRIFT",
              any(first in f and "the table says" in f for f in out), f"{out}")

        # FIRES: a shape with no row at all. Distinct from a wrong count -- a dropped row would
        # otherwise vanish silently, which is the failure the two-way join exists to stop.
        out = reconcile(_table({k: v for k, v in truth.items() if k != first}), root)
        check("a shape with no row is reported",
              any(first in f and "NO row" in f for f in out), f"{out}")

        # FIRES: a row naming something nothing measures.
        out = reconcile(_table({**truth, "`class Imaginary(RuntimeError)`": 3}), root)
        check("a table row nothing measures is reported",
              any("Imaginary" in f for f in out), f"{out}")

        # FIRES: a pattern that matches nothing, even when the table agrees it is zero. `0 == 0`
        # is exactly how a rotted regex reads as a pass, so zero is reported before the compare.
        dead = Shape("`class NeverWritten(RuntimeError)`",
                     r"^class NeverWritten\(RuntimeError\):", "x")
        out = reconcile(_table({**truth, dead.label: 0}), root, shapes=SHAPES + (dead,))
        check("a pattern that matches nothing is reported",
              any("matches NOTHING" in f for f in out), f"{out}")

    # An unmarked document must RAISE rather than parse the nearest table. A gate that silently
    # reads the wrong input reports clean over something it never examined.
    n += 1
    try:
        declared("| a | 1 | b |\n")
        failures.append("a document with no markers parsed instead of raising")
    except Unreadable:
        pass
    n += 1
    try:
        declared(f"{BEGIN}\n\n| shape | files |\n|---|---|\n\n{END}\n")
        failures.append("an empty marked table parsed instead of raising")
    except Unreadable:
        pass

    check("SHAPES is not empty", len(SHAPES) >= 4, f"{len(SHAPES)}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_shared_shapes selftest: {n} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile the quality-pass worked example's counts against the repo.")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
