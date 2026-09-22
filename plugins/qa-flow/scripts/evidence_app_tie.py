#!/usr/bin/env python3
"""Tie an evidence artifact to the application it claims to describe (#1133).

Run:  python3 evidence_app_tie.py qa/manual-tests/<file>.csv
      python3 evidence_app_tie.py --selftest

WHY THIS EXISTS. `validate_evidence.py` proves a row is INTERNALLY consistent -- a status, an HTTP
code, two URLs, an assertion, an arithmetic denominator. Nothing in it came from the application. A
fabricated artifact was found downstream carrying 21 rows of `HTTP 200` against URLs the app is
structurally incapable of serving; the validator reported 21 findings and **every one of them was
the column name** (`Status 'pass' is not one of Blocked / Exercised / Out Of Scope`). Renaming the
column satisfies that gate in ten seconds and leaves an invented file that now passes.

**A generator writing plausible rows produces exactly the shape the profile checks for.** So the
profile cannot be the whole gate: something in the file has to have come from the app.

THE TWO TIES, and neither needs a browser or a running server beyond what the run already had.

  UNROUTABLE   A `Requested URL` matching no pattern in the app's own route inventory. A path that
               resolves to no route cannot have returned 200. Catches invented SECTIONS.

  ALIEN IDS    A dynamic segment whose value is of a shape the app never produces. The app's shape
               is not hard-coded here and must not be: a project keyed on integers is correct, and
               a check that preferred one format would be wrong for it. The shape is read from THE
               SAME PROJECT'S OTHER ARTIFACTS, which were driven against the app -- the contrast the
               reporter used by eye ("/pages/pag_uf4BMshTJEQS/exclude" beside "/pages/1/exclude").

WHY ALIEN IDS IS A WHOLE-FILE VERDICT. One odd id is a data point -- a fixture, a legacy row, a
redirect. **Every** id in **every** row of a shape the corpus never contains is not a data point,
it is a file that was not driven. So the finding requires the disagreement to be total for a route
pattern, and says how many rows it counted; a partial mismatch is deliberately silent here and is
left to a person.

NOT APPLICABLE IS NOT A PASS. Both ties need an input the run may not have produced: the route
inventory (`qa/reports/routes.json`, generated, deliberately not committed) and at least one other
artifact covering a shared route pattern. When either is missing this says so and names the command
that produces it. A tie that could not run must never read as a tie that held.

Stdlib only, no network, no database.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _rc():
    """`route_coverage`, imported LAZILY to break a cycle -- it is not optional.

    `route_coverage` imports `validate_evidence`, which imports this module, so importing it at
    module scope closes the loop and every entry point but this file's own `__main__` dies with
    ImportError. Running THIS file directly hid that, because then it is `__main__` and the second
    import makes a fresh module object. The selftest drives the other entry points for that reason.

    The pattern compiler is not reimplemented here: `route_coverage` owns route parsing, and a
    second copy of `:id matches exactly one segment` would drift from the coverage numbers.
    """
    import route_coverage
    return route_coverage


def compile_pattern(pattern: str):
    return _rc().compile_pattern(pattern)


def normalise(pattern: str) -> str:
    return _rc().normalise(pattern)

ROUTES_JSON = Path("qa") / "reports" / "routes.json"
URL_COLUMNS = ("Requested URL", "Final URL")

# Enough rows that "every one disagrees" means something. Below this a uniform shape is ordinary.
MIN_ROWS_FOR_ALIEN = 3


def project_root(start: Path) -> Path | None:
    """The app an artifact lives inside, found by walking up for `qa/`.

    Evidence is written INTO the project, so the app is discoverable without a new flag for every
    caller -- and a flag would be one more thing a fabricated run could point somewhere else.
    """
    for candidate in [start.resolve()] + list(start.resolve().parents):
        if (candidate / "qa").is_dir():
            return candidate
    return None


def load_routes(root: Path) -> list[str] | None:
    """Route patterns from the app's own inventory, or None when it has not been generated."""
    path = root / ROUTES_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    routes = data.get("routes")
    if not isinstance(routes, list):
        return None
    return [normalise(str(r.get("pattern", ""))) for r in routes if r.get("pattern")]


def path_of(url: str) -> str:
    """The path part of a recorded URL, absolute or not, normalised the way routes are."""
    url = url.strip()
    if not url:
        return ""
    url = re.sub(r"^[a-z]+://[^/]+", "", url, flags=re.I)
    return normalise(url) if url.startswith("/") else ""


def urls_in(rows: list[dict[str, str]]) -> list[str]:
    out = []
    for row in rows:
        for column in URL_COLUMNS:
            p = path_of(row.get(column, "") or "")
            if p:
                out.append(p)
    return out


def unroutable(paths: list[str], patterns: list[str]) -> list[str]:
    """Paths matching no route pattern. A path no route serves cannot have returned anything."""
    compiled = [compile_pattern(p) for p in patterns]
    return sorted({p for p in paths if not any(rx.fullmatch(p) for rx in compiled)})


def shape_of(value: str) -> str:
    """A coarse CLASS of id, never a format judgement -- the app decides which class is right."""
    if re.fullmatch(r"\d+", value):
        return "integer"
    if re.fullmatch(r"[a-z]{2,6}_[A-Za-z0-9]{6,}", value):
        return "prefixed"
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value, re.I):
        return "uuid"
    return "other"


def segment_shapes(paths: list[str], patterns: list[str]) -> dict[tuple[str, int], set[str]]:
    """{(route pattern, segment index): shapes seen there}, over the paths given."""
    out: dict[tuple[str, int], set[str]] = defaultdict(set)
    compiled = [(p, compile_pattern(p)) for p in patterns]
    for path in paths:
        for pattern, rx in compiled:
            if not rx.fullmatch(path):
                continue
            pieces, actual = pattern.strip("/").split("/"), path.strip("/").split("/")
            if len(pieces) != len(actual):
                continue                 # a `*glob` pattern; segment positions do not line up
            for i, piece in enumerate(pieces):
                if piece.startswith(":"):
                    out[(pattern, i)].add(shape_of(actual[i]))
            break
    return out


def alien_ids(mine: list[str], corpus: list[str], patterns: list[str],
              min_rows: int = MIN_ROWS_FOR_ALIEN) -> list[str]:
    """Segments where EVERY value I used is of a shape the rest of the corpus never produced."""
    if not corpus:
        return []
    theirs = segment_shapes(corpus, patterns)
    ours = segment_shapes(mine, patterns)
    findings = []
    for key, shapes in sorted(ours.items()):
        # `, set()` so a mutation removing the guard below reports a finding rather than raising
        # TypeError: a crash reads to the harness as "something went wrong", which hides WHICH
        # fixture was meant to notice.
        known = theirs.get(key, set())
        if not known:
            continue                     # no corroboration for this segment; say nothing
        if shapes & known:
            continue                     # at least one value is of a shape the app does produce
        pattern, index = key
        count = sum(1 for p in mine if compile_pattern(pattern).fullmatch(p))
        if count < min_rows:
            continue                     # too few to call a pattern rather than an oddity
        findings.append(
            f"{pattern} segment {index + 1}: every one of the {count} id(s) here is "
            f"{'/'.join(sorted(shapes))}, and this project's other evidence only ever shows "
            f"{'/'.join(sorted(known))} in that position. An id the app cannot mint cannot have "
            f"been fetched, so these rows were not driven against the app.")
    return findings


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def corpus_paths(root: Path, exclude: Path) -> list[str]:
    """Paths from every OTHER evidence CSV in the project -- the app's own observed shape."""
    out: list[str] = []
    for directory in ("qa/manual-tests", "qa/reports"):
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.csv")):
            if path.resolve() == exclude.resolve():
                continue
            try:
                out.extend(urls_in(read_rows(path)))
            except (OSError, UnicodeDecodeError, csv.Error):
                continue                 # an unreadable neighbour is not this artifact's fault
    return out


def check(csv_path: Path) -> tuple[list[str], list[str]]:
    """(findings, notes). A note is a tie that COULD NOT RUN -- never counted as a pass."""
    findings: list[str] = []
    notes: list[str] = []
    root = project_root(csv_path.parent)
    if root is None:
        return [], [f"no project root above {csv_path} (no `qa/` directory) — neither tie ran"]

    patterns = load_routes(root)
    if patterns is None:
        notes.append(
            f"no {ROUTES_JSON} under {root} — BOTH ties are unrun, not passed. Generate it: "
            f"`python3 route_coverage.py enumerate --rails qa/reports/routes.txt`")
        return findings, notes

    mine = urls_in(read_rows(csv_path))
    if not mine:
        notes.append("no URL columns carried a path — nothing to tie to the app")
        return findings, notes

    for path in unroutable(mine, patterns):
        findings.append(
            f"{path}: matches no route in {ROUTES_JSON}. A path the app does not route cannot "
            f"have returned a status, so this row describes something that did not happen. If the "
            f"inventory is stale, regenerate it — a stale inventory and an invented path are "
            f"indistinguishable here, and that is why this fails rather than warns.")

    corpus = corpus_paths(root, csv_path)
    if not corpus:
        notes.append(
            "no other evidence CSV in this project — the id-shape tie is unrun, not passed. It "
            "needs one artifact known to have been driven, to read this app's own id shape from.")
    else:
        findings.extend(alien_ids(mine, corpus, patterns))
    return findings, notes


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    import shutil
    import tempfile

    PATTERNS = ["/lives/:id", "/pages/:id/exclude", "/about"]

    # --- UNROUTABLE
    expect("a path matching no route is reported",
           unroutable(["/invented"], PATTERNS) == ["/invented"])
    # The control on the same input: a path that DOES match must not be reported, or the rule
    # would "catch" the fabrication by failing everything.
    expect("...and a path that matches a route is not",
           unroutable(["/lives/1", "/about"], PATTERNS) == [])
    expect("a dynamic segment matches one segment only, not a deeper path",
           unroutable(["/lives/1/edit"], PATTERNS) == ["/lives/1/edit"])

    # --- SHAPE CLASSES. Coarse on purpose: the app decides which class is right, not this file.
    expect("an integer id is classed integer", shape_of("1") == "integer")
    expect("a prefixed public id is classed prefixed", shape_of("lif_5NfUMgfPGWG3") == "prefixed")
    expect("a uuid is classed uuid",
           shape_of("3f2504e0-4f89-11d3-9a0c-0305e82c3301") == "uuid")
    expect("a slug is neither", shape_of("about-us") == "other")

    # --- ALIEN IDS: the reported fabrication. Corpus says prefixed; the artifact is all integers.
    corpus = ["/lives/lif_5NfUMgfPGWG3", "/lives/lif_aaaaaaaaaaaa", "/pages/pag_uf4BMshTJEQS/exclude"]
    mine = ["/lives/1", "/lives/2", "/lives/3"]
    f = alien_ids(mine, corpus, PATTERNS)
    expect("an id shape this app never produces is reported", len(f) == 1)
    expect("...and the finding names both shapes and the row count",
           bool(f) and "integer" in f[0] and "prefixed" in f[0] and "3 id(s)" in f[0])

    # THE CONTROL THAT MATTERS MOST: an app keyed on integers must be silent. A check that
    # preferred one id format would be wrong for every such project, and would be switched off.
    int_corpus = ["/lives/7", "/lives/8", "/lives/9"]
    expect("an app whose OWN evidence uses integers is not reported for using integers",
           alien_ids(["/lives/1", "/lives/2", "/lives/3"], int_corpus, PATTERNS) == [])

    # A MIXED artifact is deliberately silent: one odd id is a data point, not a fabrication.
    expect("one real id among invented ones is not a whole-file verdict",
           alien_ids(["/lives/1", "/lives/2", "/lives/lif_real00000000"], corpus, PATTERNS) == [])

    # Too few rows to call it a pattern.
    expect("a single row is not enough to call a shape alien",
           alien_ids(["/lives/1"], corpus, PATTERNS) == [])

    # No corroboration at all => say nothing here; `check()` turns this into a NOTE.
    expect("with no corpus the id tie reports nothing", alien_ids(mine, [], PATTERNS) == [])
    expect("a segment the corpus never covered is not judged",
           alien_ids(["/pages/1/exclude", "/pages/2/exclude", "/pages/3/exclude"],
                     ["/lives/lif_aaaaaaaaaaaa"], PATTERNS) == [])

    # --- URL PARSING
    expect("an absolute URL is reduced to its path",
           path_of("https://example.test/lives/1?x=2#f") == "/lives/1")
    expect("a blank cell yields no path", path_of("  ") == "")

    # --- NOT APPLICABLE IS NOT A PASS
    root = Path(tempfile.mkdtemp(prefix="app-tie-"))
    try:
        (root / "qa/manual-tests").mkdir(parents=True)
        art = root / "qa/manual-tests/run-summary.csv"
        art.write_text("Requested URL,Final URL\n/lives/1,/lives/1\n", encoding="utf-8")
        findings, notes = check(art)
        expect("with no routes.json BOTH ties are notes, not findings",
               not findings and len(notes) == 1 and "unrun, not passed" in notes[0])
        expect("...and the note names the command that produces it",
               bool(notes) and "route_coverage.py enumerate" in notes[0])

        (root / "qa/reports").mkdir(parents=True)
        (root / ROUTES_JSON).write_text(
            json.dumps({"routes": [{"verb": "GET", "pattern": p} for p in PATTERNS]}),
            encoding="utf-8")
        findings, notes = check(art)
        expect("with routes but no other artifact, the id tie is a note",
               not findings and any("id-shape tie is unrun" in n for n in notes))

        # Now give it a corroborating artifact -- and the fabrication becomes a finding.
        (root / "qa/reports/sweep.csv").write_text(
            "Requested URL,Final URL\n/lives/lif_5NfUMgfPGWG3,/lives/lif_5NfUMgfPGWG3\n"
            "/lives/lif_bbbbbbbbbbbb,/lives/lif_bbbbbbbbbbbb\n", encoding="utf-8")
        art.write_text("Requested URL,Final URL\n/lives/1,/lives/1\n/lives/2,/lives/2\n"
                       "/lives/3,/lives/3\n", encoding="utf-8")
        findings, notes = check(art)
        expect("with both inputs present the invented artifact is a FINDING",
               any("cannot have been fetched" in f for f in findings))
        expect("...and nothing is left as an unrun note", not notes)

        # The control on the same tree: a genuine artifact passes both ties.
        art.write_text("Requested URL,Final URL\n/lives/lif_5NfUMgfPGWG3,/lives/lif_5NfUMgfPGWG3\n"
                       "/lives/lif_cccccccccccc,/lives/lif_cccccccccccc\n"
                       "/about,/about\n", encoding="utf-8")
        findings, notes = check(art)
        expect("a genuine artifact passes both ties", not findings)

        # An unroutable path fails even with a perfect id shape.
        art.write_text("Requested URL,Final URL\n/invented/lif_5NfUMgfPGWG3,/invented\n",
                       encoding="utf-8")
        findings, _ = check(art)
        expect("an invented SECTION fails on the route tie",
               any("matches no route" in f for f in findings))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # THE CYCLE. `route_coverage` imports `validate_evidence`, which imports this module. Running
    # this file directly cannot detect that -- it is `__main__` here -- so drive the two entry
    # points that do close the loop, as subprocesses, the way a caller really invokes them.
    import subprocess
    here = Path(__file__).resolve().parent
    for module, flag in (("route_coverage.py", "--help"), ("validate_evidence.py", "--contracts")):
        proc = subprocess.run([sys.executable, str(here / module), flag],
                              capture_output=True, text=True, timeout=60)
        expect(f"{module} still imports (no cycle through this module)",
               proc.returncode == 0 and "ImportError" not in proc.stderr)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("an unroutable path and a wholly alien id shape fail; an integer-keyed app, a mixed "
          "artifact and a missing input do not")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", nargs="?", help="an evidence CSV inside the project it describes")
    ap.add_argument("--selftest", action="store_true", help="prove these ties can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.csv_path:
        ap.error("a csv_path is required unless --selftest")

    findings, notes = check(Path(args.csv_path))
    for note in notes:
        print(f"  note: {note}")
    for finding in findings:
        print(f"  {finding}")
    print(f"\n{len(findings)} finding(s), {len(notes)} unrun tie(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
