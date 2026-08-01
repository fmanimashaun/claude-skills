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

REACH IS THE SECOND NUMBER, AND IT IS THE ONE DECISIONS REST ON (#398). A total file count says how
much duplication exists; it does not say how much of it a shared module could ever remove. Each
plugin is a separate `source:` in `marketplace.json` and every plugin script is invoked through
`${CLAUDE_PLUGIN_ROOT}`, which resolves to that plugin's own root -- so a copy can only be shared
with copies under the SAME root. `reach` is therefore the size of the largest single install root
holding the shape: the ceiling on what any extraction is worth. #398 was answered with it -- the
harness row's two columns are far apart, and it is the CEILING that moves when someone adds a copy
somewhere new. (Deliberately no digits here. This module is the arbiter for those numbers; quoting
them in its own docstring would create a second copy with nothing reading it, which is the class
the checker exists to refuse. The table is the only place they live.)

Exit codes:  0 the doctrine matches the repo · 1 it does not · 2 the doc could not be read

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "skills" / "quality-pass" / "references" / "worked-example.md"
# What defines an install root. Read rather than assumed: `reach` groups copies by the directory a
# plugin is installed FROM, so the manifest naming those directories is the arbiter, and a layout
# change that this file's path grouping stopped matching would otherwise rot in silence.
MANIFEST = Path(".claude-plugin") / "marketplace.json"

# Where the shapes are counted. `scripts/` is included deliberately: it is maintainer tooling that
# never ships, and half the worked example's point is that a copy on the far side of a distribution
# boundary is legitimate. Excluding it would hide the very evidence the example rests on.
ROOTS = ("plugins", "scripts")

BEGIN = "<!-- shared-shapes:begin -->"
END = "<!-- shared-shapes:end -->"

# A row of the marked table: `| label | 4 | 4 | where |`. The digit columns are what reject the
# header and the `|---|` separator, so no extra parsing state is needed.
ROW = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<files>\d+)\s*\|\s*(?P<reach>\d+)\s*\|")


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


def unit(path: Path, root: Path) -> str:
    """The install root `path` would be shared FROM, as a repo-relative directory.

    `plugins/<name>/...` is that plugin's root, because `marketplace.json` gives each plugin its own
    `source:` and `${CLAUDE_PLUGIN_ROOT}` resolves to it. Everything else under ROOTS is `scripts/`,
    maintainer tooling that is one directory and therefore one unit.

    Grouping is by PATH and then cross-checked against the manifest (`undeclared_units`) rather than
    resolved from it directly: the mutation checker runs this module's selftest from a temp
    directory containing nothing else, so a function that had to read the manifest could not be
    exercised against the synthetic corpus at all.
    """
    parts = path.relative_to(root).parts
    if parts[0] == "plugins" and len(parts) > 1:
        return f"plugins/{parts[1]}"
    return f"{parts[0]}/"


def reach(hits: list[Path], root: Path) -> int:
    """The most copies of a shape sharing one install root -- the ceiling on any extraction."""
    counts = Counter(unit(p, root) for p in hits)
    return max(counts.values()) if counts else 0


def plugin_roots(manifest_text: str) -> set[str]:
    """Every `plugins/<name>` a marketplace entry names as its `source`, or raise."""
    try:
        data = json.loads(manifest_text)
    except ValueError as exc:
        raise Unreadable(f"{MANIFEST}: not readable as JSON ({exc}), so no install root is known "
                         "and `reach` would be grouping by a boundary nothing confirms") from exc
    roots = set()
    for entry in data.get("plugins", []):
        source = str(entry.get("source", "")).strip().rstrip("/")
        while source.startswith("./"):
            source = source[2:]
        if source.startswith("plugins/"):
            roots.add(source)
    if not roots:
        raise Unreadable(f"{MANIFEST}: no entry declares a `plugins/<name>` source. Either the "
                         "layout moved or the key was renamed; grouping by `plugins/<name>` would "
                         "then be a boundary the manifest no longer draws.")
    return roots


def undeclared_units(files: list[Path], root: Path, roots: set[str]) -> list[str]:
    """Measured `plugins/<name>` directories the manifest does not install as a plugin.

    This is what keeps `reach` honest. Grouping by path is only the right grouping while
    `plugins/<name>` IS an install root; a new nesting level, or a plugin dropped from the
    manifest, would silently make `reach` a count over directories nobody installs.
    """
    seen = {unit(p, root) for p in files}
    return sorted(u for u in seen if u.startswith("plugins/") and u not in roots)


def declared(text: str) -> dict[str, tuple[int, int]]:
    """{label: (file count, reach)} from the marked table, or raise."""
    if BEGIN not in text or END not in text:
        raise Unreadable(
            f"{DOC.name}: no {BEGIN} / {END} markers. Without them this check would parse whatever "
            "table it found first, which is how a gate starts reading the wrong input.")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    rows: dict[str, tuple[int, int]] = {}
    for line in block.splitlines():
        m = ROW.match(line.strip())
        if m:
            rows[m.group("label").strip()] = (int(m.group("files")), int(m.group("reach")))
    if not rows:
        raise Unreadable(f"{DOC.name}: the marked table has no rows with a file count and a reach")
    return rows


def reconcile(text: str, root: Path, manifest_text: str,
              shapes: tuple[Shape, ...] = SHAPES) -> list[str]:
    """Findings, one string each. Empty means the doctrine matches the repo.

    `shapes` is a parameter rather than a read of the module global so the selftest can add a
    deliberately-dead shape without mutating state the next fixture would inherit. `manifest_text`
    is passed in for the same reason the corpus root is: every fixture must run with this module
    and nothing else on disk.
    """
    rows = declared(text)
    files = sources(root)
    roots = plugin_roots(manifest_text)
    findings: list[str] = []

    for stray in undeclared_units(files, root, roots):
        findings.append(
            f"{stray}: measured as an install root, but no marketplace entry has it as a `source`. "
            f"`reach` groups by `plugins/<name>`; if that is no longer where a plugin is installed "
            f"from, every reach below is a count over the wrong boundary.")

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
        want_files, want_reach = rows[shape.label]
        where = ", ".join(str(p.relative_to(root)) for p in hits)
        if want_files != len(hits):
            findings.append(
                f"{shape.label}: the table says {want_files}, the repo has {len(hits)} -- {where}")
        got_reach = reach(hits, root)
        if want_reach != got_reach:
            spread = ", ".join(f"{u} x{c}" for u, c in
                               sorted(Counter(unit(p, root) for p in hits).items()))
            findings.append(
                f"{shape.label}: the table says a reach of {want_reach}, the largest install root "
                f"holds {got_reach} -- {spread}. Reach is the ceiling on what extracting this "
                f"shape could remove, so a decision resting on the old number needs re-reading.")

    for label in rows:
        if label not in {s.label for s in shapes}:
            findings.append(
                f"{label}: a table row naming a shape nothing here measures. Add it to SHAPES or "
                f"remove the row; prose with no measurement behind it is the class this guards.")
    return findings


def run() -> int:
    try:
        findings = reconcile(DOC.read_text(encoding="utf-8"), REPO,
                             (REPO / MANIFEST).read_text(encoding="utf-8"))
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


def _table(rows: dict[str, tuple[int, int]]) -> str:
    body = "\n".join(f"| {label} | {n} | {r} | somewhere |" for label, (n, r) in rows.items())
    return f"{BEGIN}\n\n| shape | files | reach | where |\n|---|---|---|---|\n{body}\n\n{END}\n"


# The corpus's own manifest, in the shape the real one has. Synthetic for the same reason the
# corpus is: `reach` must be exercisable with nothing but this module on disk. TWO plugins, because
# the corpus needs to distinguish "grouped by plugin" from "grouped by `plugins/` as one lump" --
# with a single plugin those two answers are the same and the grouping could break unnoticed.
_MANIFEST = ('{"plugins": [{"name": "demo", "source": "./plugins/demo"},'
             ' {"name": "other", "source": "./plugins/other"}]}')


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

# A third harness copy, under a SECOND plugin. It is what makes the harness row's reach differ from
# both its file count AND from a grouping that lumps all of `plugins/` together, so a broken
# `unit()` cannot produce the expected reach by accident.
_D = '''\
def selftest():
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        return None
'''

# What `_corpus` below must measure to, as (files, reach). Written out rather than derived from the
# corpus by the same code under test: a fixture derived from its subject cannot witness that subject
# shrinking. The harness row is the one that matters -- 4 files but a reach of 2, because the other
# two copies sit in `scripts/` and in a second plugin, and no module reaches either from
# `plugins/demo`. That gap is the whole reason the column exists, so the corpus is built to contain
# it, and to contain it in BOTH the ways it can close: the reach is neither the file count nor the
# count of everything under `plugins/`.
_CORPUS_TRUTH = {
    "`class Unusable(RuntimeError)`": (2, 2),
    "the `json.loads` -> `Unusable` prologue": (1, 1),
    "the `check(label, ok, detail)` selftest harness": (4, 2),
    "the `SELFTEST FAILED --` reporter": (1, 1),
    "WCAG relative luminance": (1, 1),
}


def _corpus(tmp: Path) -> Path:
    for rel, body in (("plugins/demo/scripts/a.py", _A),
                      ("plugins/demo/scripts/b.py", _B),
                      ("plugins/other/scripts/d.py", _D),
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
        check("the source walk finds the corpus files", len(files) == 4,
              f"found {[str(p) for p in files]}")

        truth = dict(_CORPUS_TRUTH)
        measured = {s.label: (len(measure(s, files)), reach(measure(s, files), root))
                    for s in SHAPES}
        check("every declared shape is measured at its known count and reach in the corpus",
              measured == truth, f"{measured} != {truth}")

        # The grouping itself, stated separately from the counts above. Without this, a `unit()`
        # that returned one constant would still satisfy every reach in a corpus whose largest
        # unit happens to be the whole corpus.
        check("a plugins/<name> path groups under that plugin's install root",
              unit(root / "plugins/demo/scripts/a.py", root) == "plugins/demo",
              unit(root / "plugins/demo/scripts/a.py", root))
        check("a scripts/ path groups apart from every plugin",
              unit(root / "scripts/c.py", root) == "scripts/",
              unit(root / "scripts/c.py", root))

        # SILENCE, and it is the half that matters: a table stating the true counts must be
        # clean. A checker that fires on correct input is a checker that gets switched off.
        out = reconcile(_table(truth), root, _MANIFEST)
        check("a table stating the true counts is silent", out == [], f"{out}")

        # FIRES: a count that disagrees.
        first = SHAPES[0].label
        bumped = (truth[first][0] + 1, truth[first][1])
        out = reconcile(_table({**truth, first: bumped}), root, _MANIFEST)
        check("a wrong count in the table is DRIFT",
              any(first in f and "the table says" in f for f in out), f"{out}")

        # FIRES: the reach disagrees while the file count is right. The two are separate claims --
        # a copy moving from `scripts/` into a plugin changes what extraction is worth without
        # changing how many copies exist, and that is exactly the move #398 turns on.
        harness = "the `check(label, ok, detail)` selftest harness"
        widened = (truth[harness][0], truth[harness][1] + 1)
        out = reconcile(_table({**truth, harness: widened}), root, _MANIFEST)
        check("a wrong reach in the table is DRIFT",
              any(harness in f and "a reach of" in f for f in out), f"{out}")

        # FIRES: a shape with no row at all. Distinct from a wrong count -- a dropped row would
        # otherwise vanish silently, which is the failure the two-way join exists to stop.
        out = reconcile(_table({k: v for k, v in truth.items() if k != first}), root, _MANIFEST)
        check("a shape with no row is reported",
              any(first in f and "NO row" in f for f in out), f"{out}")

        # FIRES: a row naming something nothing measures.
        out = reconcile(_table({**truth, "`class Imaginary(RuntimeError)`": (3, 3)}),
                        root, _MANIFEST)
        check("a table row nothing measures is reported",
              any("Imaginary" in f for f in out), f"{out}")

        # FIRES: a pattern that matches nothing, even when the table agrees it is zero. `0 == 0`
        # is exactly how a rotted regex reads as a pass, so zero is reported before the compare.
        dead = Shape("`class NeverWritten(RuntimeError)`",
                     r"^class NeverWritten\(RuntimeError\):", "x")
        out = reconcile(_table({**truth, dead.label: (0, 0)}), root, shapes=SHAPES + (dead,),
                        manifest_text=_MANIFEST)
        check("a pattern that matches nothing is reported",
              any("matches NOTHING" in f for f in out), f"{out}")

        # FIRES: a plugin directory holding measured copies that the manifest does not install.
        # Reach would then be grouping by a boundary nobody ships, which is the one way this
        # column can be wrong while every number in it stays internally consistent.
        out = reconcile(_table(truth), root,
                        '{"plugins": [{"name": "other", "source": "./plugins/other"}]}')
        check("a copy under an undeclared plugin directory is reported",
              any("plugins/demo" in f and "no marketplace entry" in f for f in out), f"{out}")

        # SILENCE: a manifest declaring MORE plugins than the corpus holds stays quiet, as does a
        # skills-only entry whose source is the repo root. Without this the fixture above could be
        # passing because the rule fires on everything, and the rule reads one direction only --
        # a declared plugin with no copies is not a finding.
        out = reconcile(_table(truth), root,
                        '{"plugins": [{"name": "demo", "source": "./plugins/demo"},'
                        ' {"name": "other", "source": "./plugins/other"},'
                        ' {"name": "unused", "source": "./plugins/unused"},'
                        ' {"name": "skills-only", "source": "./"}]}')
        check("declared plugins with no copies are not findings", out == [], f"{out}")

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
        declared(f"{BEGIN}\n\n| shape | files | reach |\n|---|---|---|\n\n{END}\n")
        failures.append("an empty marked table parsed instead of raising")
    except Unreadable:
        pass

    # The manifest is the arbiter for `reach`, so an unreadable one must RAISE. Returning an empty
    # set would make `undeclared_units` report every plugin, and a rule that fires on everything
    # gets switched off; returning "no constraint" would make it report nothing, which is worse.
    check("a manifest naming plugin sources yields their roots",
          plugin_roots(_MANIFEST) == {"plugins/demo", "plugins/other"}, f"{plugin_roots(_MANIFEST)}")
    n += 1
    try:
        plugin_roots("{not json")
        failures.append("an unparseable manifest returned instead of raising")
    except Unreadable:
        pass
    n += 1
    try:
        plugin_roots('{"plugins": [{"name": "rails-stack", "source": "./"}]}')
        failures.append("a manifest declaring no plugins/<name> source returned instead of raising")
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
