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

  UNMINTABLE   A dynamic segment holding an integer where the OWNING MODEL overrides `to_param`.
        IDS    The app is deterministic ground truth: `to_param` is Rails' own URL-generation
               contract, so a model that overrides it emits a minted id from every `link_to`,
               `redirect_to`, `url_for` and path helper, and an integer can never resolve.

ASKED PER MODEL, NEVER PER PROJECT. The first version inferred the shape from the project's OTHER
evidence files, and with two files covering one pattern each was the other's entire authority: they
accused each other symmetrically, and the genuine tracked file was the one called fabricated
(#1141). It also degraded the wrong way -- with several genuine files plus one fake the real ones
intersect and fall silent, so it was right in the easy case and confidently wrong in the case that
mattered. A project-wide rule read off the app would rebuild the same defect from a different
source: 12 of 20 models adopting the convention is the realistic case, and the 8 that did not would
be flagged for legitimate integer ids. So the question goes to the model that owns the segment, and
a model declaring nothing yields silence.

WHY IT IS A WHOLE-SEGMENT VERDICT. One odd id is a data point -- a fixture, a legacy row, a
redirect. Every id in a segment being an integer the model cannot mint is not a data point, it is a
file that was not driven. A partial mismatch is deliberately silent and left to a person.

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


# Statuses that assert NOTHING about the app. A row in one of these is not claiming a result, so
# there is no claim for these ties to contradict.
NO_CLAIM_STATUSES = ("blocked", "out of scope")


def makes_a_claim(row: dict[str, str]) -> bool:
    """Is this row asserting something about the app, or recording that it could not?

    HONOURING THE REMEDY THE TOOL ALREADY NAMES (#1141). `validate_evidence` ends every failure with
    "a row that cannot carry a validated status/URL/assertion is a Blocked row" -- and these ties
    read every row regardless of status, so marking one Blocked changed nothing and the advice was
    false. Reported downstream by someone who took the advice, marked the row, and watched it fail
    anyway.

    It cannot be gamed into silence: a Blocked row is not evidence of a pass, so the escape turns a
    false claim into NO claim, which is the outcome these ties want. `validate_evidence`'s own rules
    still require a Blocked row to record what it saw, so it cannot become a way to record nothing.
    """
    return (row.get("Status", "") or "").strip().lower() not in NO_CLAIM_STATUSES


def urls_in(rows: list[dict[str, str]]) -> list[str]:
    out = []
    for row in rows:
        if not makes_a_claim(row):
            continue
        for column in URL_COLUMNS:
            p = path_of(row.get(column, "") or "")
            if p:
                out.append(p)
    return out


# A Rails route is `(.:format)`-bearing, and `route_coverage.normalise()` strips that from the
# PATTERN -- so `/capacity` in the inventory is the same route as `/capacity.csv` on the wire. The
# observed path had nothing stripped, so every CSV export a sweep legitimately fetched was reported
# as unroutable: seven of eight findings in one downstream file.
FORMAT_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,6}$")

# A `Requested URL` cell carrying an annotation -- `/dashboard (scope EG)` -- is a defect in the
# ARTIFACT, but it is not the same defect as a path the app cannot serve, and saying so wrongly
# sends someone to look for a missing route that exists.
NOT_A_URL = re.compile(r"\s")


def unroutable(paths: list[str], patterns: list[str]) -> list[str]:
    """Paths matching no route pattern. A path no route serves cannot have returned anything."""
    compiled = [compile_pattern(p) for p in patterns]

    def routed(path: str) -> bool:
        if any(rx.fullmatch(path) for rx in compiled):
            return True
        # Try again without a format suffix, and ONLY then: `/capacity.csv` is `/capacity` rendered
        # as CSV. Stripping unconditionally would make `/report.2024` match `/report`, so the bare
        # form has to be a real route before the suffix is forgiven.
        bare = FORMAT_SUFFIX.sub("", path)
        return bare != path and any(rx.fullmatch(bare) for rx in compiled)

    return sorted({p for p in paths if not routed(p)})


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


# A model overriding `to_param` has told Rails what its URLs carry. That is the CONTRACT -- every
# `link_to`, `redirect_to`, `url_for` and path helper for that model emits it -- which is exactly
# what an evidence URL can contain. Matching controller lookups instead measures CONSUMPTION, which
# can be spelled many ways: counted downstream, `find_by!(public_id: params[:id])` caught 32 of 43
# real call sites and missed six that differ only by the bang, plus five nested `:page_id`-style
# segments a check scoped to `:id` would never look at (#1141).
TO_PARAM = re.compile(r"^\s*def\s+to_param\b", re.M)
INCLUDES = re.compile(r"^\s*include\s+([A-Z][A-Za-z0-9:]*)", re.M)
# `Foo::Bar` -> foo/bar, `HasPublicId` -> has_public_id: Rails' own file-naming rule.
def _underscore(name: str) -> str:
    name = name.replace("::", "/")
    name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
    return name.lower()


def _singular(segment: str) -> list[str]:
    """Candidate model file stems for a path segment. Naive on purpose -- an unresolved segment is
    NOT APPLICABLE, never a finding, so a miss costs silence rather than a false accusation."""
    out = [segment]
    if segment.endswith("ies"):
        out.append(segment[:-3] + "y")
    if segment.endswith("sses") or segment.endswith("ches") or segment.endswith("shes"):
        out.append(segment[:-2])
    if segment.endswith("s"):
        out.append(segment[:-1])
    return out


def models_with_url_ids(root: Path) -> set[str]:
    """Model file stems whose URLs carry a minted id, because they override `to_param`.

    PER MODEL, NEVER PER PROJECT (#1141). A project where 12 of 20 models adopt the convention is
    the realistic case, and one project-wide rule derived from "some models override it" flags
    legitimate integer ids on the 8 that did not -- the same false accusation as the peer-consensus
    version this replaces, with a different source. So the answer is asked of the model that owns
    the segment, and a model that declares nothing yields silence.
    """
    models = root / "app" / "models"
    if not models.is_dir():
        return set()
    sources = {p: p.read_text(encoding="utf-8", errors="replace")
               for p in models.rglob("*.rb") if p.is_file()}
    # A concern that defines `to_param` confers it on every model including it -- which is how a
    # real app spells this: 36 of 36 models here, none of them writing `def to_param` themselves.
    # KEYED BY STEM, not by path. `app/models/concerns/has_public_id.rb` is included as
    # `HasPublicId`, which underscores to `has_public_id` -- keying on the relative path gave
    # `concerns/has_public_id`, which matched no include, so every model fell through and only the
    # concern itself was reported. Caught by the fixture that asserts the MODEL is in the set.
    concerns = {p.stem for p, text in sources.items() if TO_PARAM.search(text)}
    out: set[str] = set()
    for path, text in sources.items():
        stem = path.stem
        if TO_PARAM.search(text):
            out.add(stem)
            continue
        if any(_underscore(name) in concerns for name in INCLUDES.findall(text)):
            out.add(stem)
    return out


def segment_model(pattern: str, index: int) -> str | None:
    """Which model a dynamic segment names: `:page_id` -> page, `:id` -> the segment before it."""
    pieces = pattern.strip("/").split("/")
    if index >= len(pieces) or not pieces[index].startswith(":"):
        return None
    name = pieces[index][1:]
    if name != "id" and name.endswith("_id"):
        return name[:-3]
    return pieces[index - 1] if index > 0 else None


def impossible_ids(mine: list[str], patterns: list[str], root: Path,
                   min_rows: int = MIN_ROWS_FOR_ALIEN) -> list[str]:
    """Segments whose ids the OWNING MODEL cannot mint. Ground truth is the app, never a peer file.

    The replaced version inferred the shape from this project's other evidence files, so two files
    covering one pattern were each other's entire authority and accused each other symmetrically --
    with the genuine, tracked file called fabricated in the strongest language the tool has
    (#1141). Worse, it degraded the wrong way: with several genuine files plus one fake the real
    ones intersect and fall silent, so it was right in the easy case and confidently wrong in the
    case that matters.
    """
    minted = models_with_url_ids(root)
    if not minted:
        return []
    findings = []
    for (pattern, index), shapes in sorted(segment_shapes(mine, patterns).items()):
        model = segment_model(pattern, index)
        if not model:
            continue
        owner = next((c for c in _singular(model) if c in minted), None)
        if owner is None:
            continue                     # this MODEL declares no URL-id convention; say nothing
        if shapes != {"integer"}:
            continue                     # only a wholly integer segment is provably unmintable
        count = sum(1 for p in mine if compile_pattern(pattern).fullmatch(p))
        if count < min_rows:
            continue                     # too few to call a pattern rather than an oddity
        findings.append(
            f"{pattern} segment {index + 1}: all {count} id(s) here are integers, and `{owner}` "
            f"overrides `to_param`, so every URL this app generates for it carries a minted id. "
            f"An integer cannot resolve, so these rows were not driven against the app.")
    return findings


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


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
        if NOT_A_URL.search(path):
            # A DIFFERENT DEFECT, NAMED AS ITSELF. This cell holds a URL plus a note; the route may
            # well exist. Reporting it as an unroutable path sends a reader hunting for a missing
            # route that is there.
            findings.append(
                f"{path!r}: the `Requested URL` cell is not a URL — it carries text alongside the "
                f"path, so nothing can be resolved against the route table. Put the annotation in "
                f"`Notes`; the column is machine-read.")
            continue
        findings.append(
            f"{path}: matches no route in {ROUTES_JSON}. A path the app does not route cannot "
            f"have returned a status, so this row describes something that did not happen. If the "
            f"inventory is stale, regenerate it — a stale inventory and an invented path are "
            f"indistinguishable here, and that is why this fails rather than warns.")

    # GROUND TRUTH IS THE APP, NOT THE NEIGHBOURS (#1141). No corpus is read any more: a peer file
    # cannot arbitrate, and when only two cover a pattern each was the other's whole authority.
    if not (root / "app" / "models").is_dir():
        notes.append(
            "no app/models — the id tie is unrun, not passed. It reads which models override "
            "`to_param`, which is what decides whether an integer id could ever appear in a URL.")
    else:
        findings.extend(impossible_ids(mine, patterns, root))
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

    PATTERNS = ["/lives/:id", "/pages/:id/exclude", "/about", "/pages/:id",
                "/reviews/:id", "/pages/:page_id/lives"]

    # --- UNROUTABLE
    expect("a path matching no route is reported",
           unroutable(["/invented"], PATTERNS) == ["/invented"])
    # The control on the same input: a path that DOES match must not be reported, or the rule
    # would "catch" the fabrication by failing everything.
    expect("...and a path that matches a route is not",
           unroutable(["/lives/1", "/about"], PATTERNS) == [])
    expect("a dynamic segment matches one segment only, not a deeper path",
           unroutable(["/lives/1/edit"], PATTERNS) == ["/lives/1/edit"])

    # --- A FORMAT SUFFIX IS THE SAME ROUTE (#1152-adjacent) --------------------------------
    # Rails routes are `(.:format)`-bearing and `normalise()` strips that from the PATTERN, so
    # `/capacity` in the inventory IS `/capacity.csv` on the wire. Nothing stripped it from the
    # observed path, so every CSV export a sweep legitimately fetched read as unroutable --
    # seven of eight findings in one downstream file.
    expect("a `.csv` rendering of a real route is routable",
           unroutable(["/capacity.csv"], ["/capacity"]) == [])
    expect("...and so is the bare path, unchanged",
           unroutable(["/capacity"], ["/capacity"]) == [])
    # THE CONTROL: the suffix is forgiven only when the BARE path is a real route. Stripping
    # unconditionally would make an invented path match by losing its last segment.
    expect("a suffix on a path that routes nowhere is still reported",
           unroutable(["/invented.csv"], ["/capacity"]) == ["/invented.csv"])
    expect("...and a dotted segment is not mistaken for a format",
           unroutable(["/report.2024"], ["/report.2024"]) == [])

    # --- SHAPE CLASSES. Coarse on purpose: the app decides which class is right, not this file.
    expect("an integer id is classed integer", shape_of("1") == "integer")
    expect("a prefixed public id is classed prefixed", shape_of("lif_5NfUMgfPGWG3") == "prefixed")
    expect("a uuid is classed uuid",
           shape_of("3f2504e0-4f89-11d3-9a0c-0305e82c3301") == "uuid")
    expect("a slug is neither", shape_of("about-us") == "other")

    # --- UNMINTABLE IDS, ground truth = the app (#1141) ------------------------------------
    import shutil
    import tempfile

    def app(models: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="app-tie-app-"))
        (root / "app/models/concerns").mkdir(parents=True)
        for rel, body in models.items():
            (root / "app/models" / rel).write_text(body, encoding="utf-8")
        return root

    CONCERN = "module HasPublicId\n  def to_param = public_id\nend\n"
    root = app({"concerns/has_public_id.rb": CONCERN,
                "page.rb": "class Page < ApplicationRecord\n  include HasPublicId\nend\n"})
    try:
        expect("a model including a `to_param` concern is known to mint URL ids",
               models_with_url_ids(root) == {"has_public_id", "page"})
        f = impossible_ids(["/pages/1", "/pages/2", "/pages/3"], PATTERNS, root)
        expect("integers where the owning model overrides `to_param` are reported", len(f) == 1)
        expect("...and the finding names the model and the count",
               bool(f) and "`page`" in f[0] and "all 3 id(s)" in f[0])
        # THE MIRROR THIS REPLACES. The same real file that the peer-consensus version called
        # fabricated -- because one fake neighbour was its entire ground truth -- is silent here,
        # and no neighbour is consulted at all.
        expect("minted ids on that model are silent",
               not impossible_ids(["/pages/pag_aaaaaaaaaaaa", "/pages/pag_bbbbbbbbbbbb",
                                   "/pages/pag_cccccccccccc"], PATTERNS, root))
        # A nested `:page_id` segment resolves to the same model, which a check scoped to `:id`
        # would never look at -- five such sites exist in the app this came from.
        expect("a nested `:page_id` segment resolves to its model",
               segment_model("/pages/:page_id/lives", 1) == "page")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # PARTIAL ADOPTION is the realistic case and the one that would rebuild the old defect: a
    # project-wide rule read off "some models override `to_param`" flags legitimate integer ids on
    # every model that never adopted it.
    root = app({"concerns/has_public_id.rb": CONCERN,
                "page.rb": "class Page < ApplicationRecord\n  include HasPublicId\nend\n",
                "review.rb": "class Review < ApplicationRecord\nend\n"})
    try:
        expect("a model that adopted nothing is not in the minted set",
               "review" not in models_with_url_ids(root))
        expect("...so integer ids on IT are not a finding",
               not impossible_ids(["/reviews/1", "/reviews/2", "/reviews/3"], PATTERNS, root))
        # The control on the same app: the model that DID adopt is still reported, or the carve-out
        # above has simply turned the check off.
        expect("...while the model that DID adopt is still reported",
               impossible_ids(["/pages/1", "/pages/2", "/pages/3"], PATTERNS, root))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # An app that uses integer ids everywhere is CORRECT and must be entirely silent.
    root = app({"page.rb": "class Page < ApplicationRecord\nend\n"})
    try:
        expect("an app with no `to_param` anywhere reports nothing",
               not impossible_ids(["/pages/1", "/pages/2", "/pages/3"], PATTERNS, root))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    root = app({"concerns/has_public_id.rb": CONCERN,
                "page.rb": "class Page < ApplicationRecord\n  include HasPublicId\nend\n"})
    try:
        # A MIXED segment stays silent: one odd id is a fixture or a legacy row, not a verdict.
        expect("one minted id among integers is not a whole-segment verdict",
               not impossible_ids(["/pages/1", "/pages/2", "/pages/pag_aaaaaaaaaaaa"],
                                  PATTERNS, root))
        expect("a single row is not enough to call a segment unmintable",
               not impossible_ids(["/pages/1"], PATTERNS, root))
        # A segment whose model cannot be resolved at all is silence, never a finding.
        expect("an unresolvable segment is not judged",
               not impossible_ids(["/about/1", "/about/2", "/about/3"],
                                  ["/about/:id"], root))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # --- A BLOCKED ROW MAKES NO CLAIM (#1141) ----------------------------------------------
    # `validate_evidence` ends every failure with "a row that cannot carry a validated
    # status/URL/assertion is a Blocked row". These ties read every row regardless of status, so
    # taking that advice changed nothing -- reported by someone who marked the row and watched it
    # fail anyway. The remedy the tool names has to work, or it is not a remedy.
    claim = {"Status": "Observed", "Requested URL": "/nope", "Final URL": "/nope"}
    expect("a row that CLAIMS a result is still read", urls_in([claim]) == ["/nope", "/nope"])
    for status in ("Blocked", "blocked", "Out Of Scope", "out of scope"):
        expect(f"a `{status}` row asserts nothing, so no path is taken from it",
               urls_in([{**claim, "Status": status}]) == [])
    # THE CONTROL: it cannot be gamed into blanket silence -- a sibling row on the SAME path that
    # does claim a result is still read, so marking ONE row Blocked hides only that row.
    expect("...and a claiming row beside it is still read",
           urls_in([{**claim, "Status": "Blocked"}, claim]) == ["/nope", "/nope"])
    # A row with no Status column at all is a claim: absence is not an exemption.
    expect("a row with no Status column is treated as claiming",
           urls_in([{"Requested URL": "/nope", "Final URL": "/nope"}]) == ["/nope", "/nope"])

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
        expect("with routes but no app/models, the id tie is a NOTE, not a pass",
               not findings and any("id tie is unrun" in n for n in notes))

        # Give the tree an app, and the invented artifact becomes a finding -- decided by the
        # app alone, with no second evidence file anywhere in the project.
        (root / "app/models/concerns").mkdir(parents=True)
        (root / "app/models/concerns/has_public_id.rb").write_text(
            "module HasPublicId\n  def to_param = public_id\nend\n", encoding="utf-8")
        (root / "app/models/live.rb").write_text(
            "class Live < ApplicationRecord\n  include HasPublicId\nend\n", encoding="utf-8")
        art.write_text("Requested URL,Final URL\n/lives/1,/lives/1\n/lives/2,/lives/2\n"
                       "/lives/3,/lives/3\n", encoding="utf-8")
        findings, notes = check(art)
        expect("with the app present the invented artifact is a FINDING",
               any("were not driven against the app" in f for f in findings))
        expect("...and nothing is left as an unrun note", not notes)

        # The control on the same tree: a genuine artifact passes both ties.
        art.write_text("Requested URL,Final URL\n"
                       "/lives/lif_5NfUMgfPGWG3,/lives/lif_5NfUMgfPGWG3\n"
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
