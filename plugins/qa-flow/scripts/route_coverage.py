#!/usr/bin/env python3
"""Answer the coverage question qa-flow could not: which routes has nothing ever tested?

Run:  python3 route_coverage.py enumerate --rails qa/reports/routes.txt
      python3 route_coverage.py enumerate --sitemap public/sitemap.xml
      python3 route_coverage.py enumerate --fs app/views/pages
      python3 route_coverage.py report  --evidence qa/manual-tests --evidence qa/reports
      python3 route_coverage.py --selftest

THE PROBLEM (#119). qa-flow drove from a case catalogue and a menu scope, so the most basic
coverage question had no answer: *which routes has nothing ever tested?* Blast-radius selection
in `/qa-flow:verify` was therefore judgement over an unknown denominator -- you cannot select
"affected untested routes" without knowing what the routes are. Enumerate, then intersect with
what the passes actually visited, and the denominator becomes concrete.

WHY COVERAGE IS READ FROM THE EVIDENCE ARTIFACTS. Attribution does not invent a new schema. It
reads the CSVs `validate_evidence.py` already validates, and uses that module's own profiles to
know which columns carry a URL. So a route counts as covered only when a row that passed
validation says a pass went there -- coverage inherits the page-identity guarantees rather than
trusting a second, unchecked record. It also means a new browser pass gets coverage attribution
for free, and the selftest asserts no profile can be silently forgotten.

WHAT IS DELIBERATELY NOT INFERRED. Whether a route needs authentication is not guessable from
its path; a heuristic would be wrong on exactly the routes that matter. It comes from config
(`coverage.authenticated_prefixes`) so the claim is the team's, not a guess. Same for
exclusions: they are declared, and the excluded set is always PRINTED, because a suppression
that leaves no trace is how a coverage number quietly becomes a lie.

COVERAGE HAS A SECOND AXIS, AND IT IS NOT A PERCENTAGE OF THE FIRST (#953). "Covered" means a
validated pass asserted something about the route. It says nothing about the WIDTH that pass ran at,
and downstream that gap was total: a suite reported 49/49 routes covered while 71-83% of every data
table was hidden at a phone width, because the one browser sweep the flow owned was pinned to
1280x900 and the responsive spec's page list was five hand-maintained entries against 86 routes.

So a route is also either MEASURED AT A SMALL VIEWPORT or not, and the maintainer's decision is that
every page built must be in that list: "each page built should be included into the QA test list so
it get tested". The list is therefore not hand-maintained anywhere -- it is the route table, and a
route absent from the small-viewport evidence is reported as a gap exactly the way an unasserted
route already is.

NOT FOLDED INTO `covered`, for the same reason a crawl visit is not. They answer different
questions, and one number that averaged them would hide both: a route asserted at 1280px and never
seen at 390px is fully covered on axis one and absent from axis two, which is the exact state that
shipped the defect. Evidence is `layout.json` (`layout_fit.py`'s input), and only rows the probe
actually measured on the route requested count -- a route whose probe threw, or that redirected to a
sign-in page, was not measured small however many times it appears.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_evidence as ve  # noqa: E402
import qa_config  # noqa: E402 -- sibling module, one reader for qa.config.yml (#792)

# Which validated profile carries a visited URL, and in which columns. Keyed by profile name so
# a new pass is wired in one line.
ROUTE_SOURCES: dict[str, tuple[str, ...]] = {
    "functional": ("Requested URL", "Final URL"),
    "a11y": ("Requested URL", "Final URL"),
    "runtime": ("Route", "Requested URL", "Final URL"),
    "keyboard": ("Route", "Requested URL", "Final URL"),
    "forms": ("Route", "Requested URL", "Final URL"),
    "emulation": ("Route", "Requested URL", "Final URL"),
    "perf": ("Route", "Requested URL", "Final URL"),
}

# Artifacts that record a VISIT but no assertion (#108 residual). Route coverage only ever read
# the CSV evidence profiles, so a route the crawler loaded, judged and found clean counted as
# "never touched" -- and that omission was nowhere stated, which is the part that made it a defect
# rather than a decision.
#
# The fix is NOT to fold these into `covered`. A crawl loads a route and grades it for HTTP status,
# console errors and uncaught exceptions; nothing asserts the page did its job. Counting that as
# coverage is SKIP-is-not-a-PASS wearing a percentage: it would inflate the one number this tool
# exists to keep honest, and inflate it exactly on the routes nobody wrote a test for. So they form
# a THIRD state, reported beside the gaps and never merged into them.
VISIT_ONLY_ARTIFACTS: dict[str, str] = {
    "crawl.json": "loaded and graded for errors, but nothing asserted the page works",
    "links.json": "visited to inventory its links",
}

# Profiles credited by (VERB, route pattern) rather than by matching a URL against a pattern
# (#1039). A THIRD category, and it has to be a third rather than an entry in ROUTE_SOURCES: those
# profiles are read by resolving a URL, and this one is read by taking the route the artifact
# NAMES. Folding it in would mean one dict whose values meant two different things depending on
# the key, which is how the next reader credits a state-changing route from a page view again.
VERB_SOURCES: dict[str, tuple[str, str]] = {
    "actions": ("Method", "Route"),
}

# Profiles that must NOT contribute coverage, and why. `findings` carries `Example Routes`, but
# those are up to three EXAMPLES of a deduplicated defect -- counting them would credit coverage
# for routes nobody visited and inflate the number this tool exists to make honest.
ROUTE_LESS: dict[str, str] = {
    "findings": "Example Routes lists up to 3 examples of a deduped finding, not a visit log",
    # #993. A journey walk records every page it visits in pages.csv (the functional profile), which
    # credits coverage once. Its hand-off rows revisit the recipient's page to record a CONSEQUENCE,
    # so crediting them would count one visit twice; its notification rows are read in the dev
    # inbox, which is not a route under test.
    "handoffs": "the recipient's page is already credited by the same walk's pages.csv; this row records the consequence",
    "notifications": "read in the dev inbox against the catalogue, not on a route under test",
}

# Evidence for the second axis. `layout_fit.py` grades this file; here it is read only for WHICH
# routes were measured and at what width.
SMALL_VIEWPORT_ARTIFACT = "layout.json"
SMALL_VIEWPORT_SCHEMA = "qa-flow/layout-fit/1"

# The width at or below which a measurement counts as "small", unless the project declares its own
# in `coverage.small_viewport_max`. 480 sits above every phone in the responsive corpus (320-430)
# and below every tablet, so it is a boundary rather than a target: this tool never asks whether the
# page LOOKED right, only whether anything ever measured it at a width where it could not.
DEFAULT_SMALL_VIEWPORT_MAX = 480

GET_LIKE = {"GET", "HEAD"}


@dataclass(frozen=True)
class Route:
    verb: str
    pattern: str
    controller: str
    area: str

    @property
    def destructive(self) -> bool:
        """Non-GET: it changes state, so untested is worse."""
        return self.verb.upper() not in GET_LIKE

    @property
    def key(self) -> str:
        return f"{self.verb} {self.pattern}"


def _area(controller: str, pattern: str) -> str:
    """Group for the report: the controller namespace, else the first path segment."""
    if controller and "/" in controller:
        return controller.split("/")[0]
    if controller:
        return controller.split("#")[0]
    segments = [s for s in pattern.split("/") if s and not s.startswith((":", "*"))]
    return segments[0] if segments else "root"


# ---------------------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------------------
# `bin/rails routes` output:  prefix VERB uri_pattern controller#action
# THE CONTROLLER IS NOT ALWAYS THE LAST TOKEN, and requiring it to be dropped 45% of a real route
# table in silence (#953). Rails prints a route's `defaults:` after the controller —
#
#   requests GET /requests(.:format) placeholders#show {screen: "All requests", feature: "F-06"}
#
# — and `(?P<controller>\S+)\s*$` cannot match a row with anything after it. Measured on the app
# that prompted this: 143 verb-bearing rows, 79 matched, **64 silently dropped**, and the dropped set
# was the entire admin surface, because that shell routes every screen through one action with the
# screen name in `defaults`. Route coverage then reported "49/49 (100%)" over a denominator that did
# not contain a single page the defects were found on. A parser that drops a row it does not
# recognise, without saying so, turns every number downstream of it into a claim about a different
# application.
_RAILS_ROW = re.compile(
    r"^\s*(?P<prefix>[a-z0-9_]*)\s+"
    r"(?P<verb>GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)(?:\|[A-Z|]+)?\s+"
    r"(?P<pattern>/\S*)\s+"
    r"(?P<controller>\S+)"
    # The `defaults:` hash, when there is one. Captured as "ignore the rest of the line" rather than
    # parsed: nothing here needs its contents, and a partial parse of it would be a second claim.
    r"(?:\s+\{.*\})?\s*$"
)


def from_rails(text: str) -> list[Route]:
    """Parse `bin/rails routes`. Multi-verb rows (`GET|POST`) yield the first verb listed."""
    routes: list[Route] = []
    for line in text.splitlines():
        m = _RAILS_ROW.match(line)
        if not m:
            continue  # header, blank, or a mounted-engine banner
        pattern = normalise(m.group("pattern"))
        controller = m.group("controller")
        routes.append(Route(m.group("verb"), pattern, controller, _area(controller, pattern)))
    return routes


# A line that names an HTTP verb is a route row, whatever else is on it. Used only to find rows the
# parser did NOT understand, so a future Rails format change is loud instead of a 45% silent drop.
_VERB_BEARING = re.compile(r"\s(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)[|\s]")


def unparsed_rails_rows(text: str) -> list[str]:
    """Verb-bearing rows `_RAILS_ROW` could not parse. Empty is the only acceptable answer.

    The old parser dropped 64 of 143 rows on a real app and said nothing, so route coverage reported
    100% over a denominator missing every page the defects were on. Silence on an unrecognised row
    is the defect; the regex was only how it got in.
    """
    return [line.rstrip() for line in text.splitlines()
            if _VERB_BEARING.search(line) and not _RAILS_ROW.match(line)]


def from_sitemap(text: str) -> list[Route]:
    """Parse <loc> entries. A sitemap is only ever GET, and carries no controller."""
    routes: list[Route] = []
    for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", text, flags=re.I | re.S):
        pattern = normalise(re.sub(r"^[a-z]+://[^/]+", "", loc.strip()) or "/")
        routes.append(Route("GET", pattern, "", _area("", pattern)))
    return routes


def from_fs(root: Path) -> list[Route]:
    """Filesystem routing (JS frameworks, static site sections): a page file is a route."""
    routes: list[Route] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".md", ".jsx", ".tsx", ".vue", ".svelte"}:
            continue
        rel = path.relative_to(root).with_suffix("")
        parts = [p for p in rel.parts if p not in {"index", "page"}]
        pattern = "/" + "/".join(parts)
        # `[id]` / `[...slug]` are the filesystem spelling of a dynamic segment.
        pattern = re.sub(r"\[\.\.\.[^\]]+\]", "*glob", pattern)
        pattern = re.sub(r"\[([^\]]+)\]", r":\1", pattern)
        pattern = normalise(pattern or "/")
        routes.append(Route("GET", pattern, "", _area("", pattern)))
    return routes


def normalise(pattern: str) -> str:
    """One spelling per route, so enumeration and visits can be compared at all.

    Strips Rails' `(.:format)` suffix and any query/fragment, and drops a trailing slash
    (except for the root). Without this, `/about`, `/about/` and `/about(.:format)` are three
    routes and coverage is understated by construction.
    """
    pattern = pattern.split("?", 1)[0].split("#", 1)[0]
    pattern = re.sub(r"\(\.:format\)$", "", pattern)
    if len(pattern) > 1:
        pattern = pattern.rstrip("/")
    return pattern or "/"


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """A route pattern as a regex. `:id` matches ONE segment; `*glob` matches the rest.

    The single-segment rule is what stops `/users/:id` from claiming coverage for
    `/users/42/edit` -- a distinct route, usually a distinct controller action, and exactly the
    kind of silent over-credit that makes a coverage number worthless.
    """
    out = ["^"]
    for segment in pattern.split("/"):
        if not segment:
            continue
        out.append("/")
        if segment.startswith(":"):
            out.append(r"[^/]+")
        elif segment.startswith("*"):
            out.append(r".+")
        else:
            out.append(re.escape(segment))
    if pattern == "/":
        out.append("/")
    out.append("/?$")
    return re.compile("".join(out))


# ---------------------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------------------
def visited_paths(evidence_dirs: list[Path]) -> dict[str, set[str]]:
    """path -> the artifacts that visited it, read only from VALIDATED evidence CSVs."""
    seen: dict[str, set[str]] = {}
    for directory in evidence_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.csv")):
            try:
                profile, rows = ve.load_rows(path)
            except ve.Unusable:
                continue  # not an evidence artifact, or unreadable -- never guessed at
            columns = ROUTE_SOURCES.get(profile.name)
            if not columns:
                continue
            for row in rows:
                if row["Status"].lower() in {ve.OUT_OF_SCOPE_STATUS}:
                    continue  # never visited, and not claimed to be
                for column in columns:
                    raw = row.get(column, "")
                    if not raw:
                        continue
                    p = normalise(re.sub(r"^[a-z]+://[^/]+", "", raw.strip()))
                    if p.startswith("/"):
                        seen.setdefault(p, set()).add(f"{profile.name}:{path.name}")
    return seen


def verb_paths(evidence_dirs: list[Path]) -> dict[tuple[str, str], set[str]]:
    """(VERB, route pattern) -> the artifacts that DROVE it. The only verb-bearing read (#1039).

    Every other evidence read in this file resolves a URL and matches it against a compiled route
    pattern, because a navigation records where the browser went and the route has to be inferred.
    This one does not, and the difference is deliberate: the `actions` profile carries the `Route`
    column, so the agent STATES which route it drove, and an exact string match against
    `bin/rails routes` needs no inference at all.

    That matters here more than elsewhere. Inferring `DELETE /users/:id` from a URL would mean
    deciding that `/users/42` "is" that route -- and `/users/42` is also `GET /users/:id` and
    `PATCH /users/:id`. Getting it wrong credits a state-changing route that was never exercised,
    which is the entire defect #1037 removed. An exact match on the declared pattern cannot make
    that mistake: a pattern that does not match any route credits NOTHING, so a typo under-claims.
    Under-claiming is the safe direction for a coverage gate and the one this file takes
    everywhere else.

    `validate_evidence` has already refused any GET-like verb in this profile, so nothing here can
    launder a page view into verb-bearing evidence.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    for directory in evidence_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.csv")):
            try:
                profile, rows = ve.load_rows(path)
            except ve.Unusable:
                continue  # reported by `unusable_artifacts`, never guessed at
            columns = VERB_SOURCES.get(profile.name)
            if not columns:
                continue
            verb_column, route_column = columns
            for row in rows:
                if row["Status"].lower() in {ve.OUT_OF_SCOPE_STATUS}:
                    continue  # never driven, and not claimed to be
                verb = (row.get(verb_column) or "").strip().upper()
                pattern = (row.get(route_column) or "").strip()
                if not verb or not pattern.startswith("/"):
                    continue
                seen.setdefault((verb, pattern), set()).add(f"{profile.name}:{path.name}")
    return seen


def unusable_artifacts(evidence_dirs: list[Path]) -> list[tuple[str, str]]:
    """Every CSV under `evidence_dirs` that does NOT match an evidence contract, and why.

    THE SILENT-SKIP HAZARD, WHICH IS WHY THIS IS SEPARATE FROM THE COVERAGE READ (#1039).
    `visited_paths` catches `Unusable` and continues, so an artifact that fails to parse contributes
    nothing -- and contributing nothing is **indistinguishable from an artifact with no matching
    rows**. The coverage number simply comes out lower, with no error anywhere.

    That is tolerable only while the contracts never move. The moment one does -- and #1039 exists
    because one has to, to record an HTTP verb -- `detect_profile`'s exact `header ==
    list(profile.columns)` makes every already-written artifact match nothing, and the whole corpus
    goes quiet at once. A project would read that as a coverage collapse and go looking for a
    regression that is not there.

    So the condition gets a name and a report of its own BEFORE any contract moves, rather than
    alongside the change that would first exploit it. Reported unconditionally, including the zero
    case: "no evidence failed to parse" and "nobody looked" must not print the same line.

    This does not change what counts as coverage. `visited_paths` still skips what it cannot read --
    guessing at a malformed artifact is worse than ignoring it. What changes is that the skip is now
    visible, and it is visible in the one place a number is quoted from.
    """
    problems: list[tuple[str, str]] = []
    for directory in evidence_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.csv")):
            try:
                ve.load_rows(path)
            except ve.Unusable as exc:
                problems.append((str(path), str(exc)))
    return problems


def visit_only_paths(evidence_dirs: list[Path]) -> dict[str, set[str]]:
    """Routes a crawl artifact records having LOADED. Never merged with `visited_paths`."""
    seen: dict[str, set[str]] = {}
    for directory in evidence_dirs:
        if not directory.is_dir():
            continue
        for name in VISIT_ONLY_ARTIFACTS:
            for path in sorted(directory.rglob(name)):
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue  # not a crawl artifact, or unreadable -- never guessed at
                if not isinstance(doc, dict):
                    continue
                for page in doc.get("pages") or []:
                    if not isinstance(page, dict):
                        continue
                    raw = str(page.get("route") or "")
                    candidate = normalise(re.sub(r"^[a-z]+://[^/]+", "", raw.strip()))
                    if candidate.startswith("/"):
                        seen.setdefault(candidate, set()).add(name)
    return seen


def small_viewport_paths(evidence_dirs: list[Path], max_width: int) -> dict[str, set[str]]:
    """Routes a layout run MEASURED at or below `max_width`. Never merged with `visited_paths`.

    Three ways a row is present and still does not count, and each is the difference between a
    measured route and an unmeasured one reported as measured:

      * `elements: null` -- the probe threw. Not measured.
      * `landedOn` different from `route` -- the browser was somewhere else, so the measurement
        belongs to that somewhere else. On a signed-in crawl this is usually the interaction sweep
        having clicked sign-out.
      * a viewport wider than `max_width` -- a desktop measurement, which is the state this axis
        exists to distinguish from no measurement at all.
    """
    seen: dict[str, set[str]] = {}
    for directory in evidence_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob(SMALL_VIEWPORT_ARTIFACT)):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # unreadable, or not a layout run -- never guessed at
            if not isinstance(doc, dict) or doc.get("schema") != SMALL_VIEWPORT_SCHEMA:
                continue
            for entry in doc.get("routes") or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("elements") is None:
                    continue
                raw = str(entry.get("route") or "")
                candidate = normalise(re.sub(r"^[a-z]+://[^/]+", "", raw.strip()))
                if not candidate.startswith("/"):
                    continue
                landed = entry.get("landedOn")
                if isinstance(landed, str) and landed.strip() and normalise(landed) != candidate:
                    continue
                width = _viewport_width(entry.get("viewport") or doc.get("viewport"))
                if width is None or width > max_width:
                    continue
                seen.setdefault(candidate, set()).add(f"{SMALL_VIEWPORT_ARTIFACT}@{width}px")
    return seen


def _viewport_width(raw: object) -> int | None:
    """`"390x844"` -> 390. None when it is absent or unparseable, which is not a measurement."""
    match = re.fullmatch(r"\s*(\d{2,5})\s*x\s*(\d{2,5})\s*", str(raw or ""))
    return int(match.group(1)) if match else None


@dataclass
class Coverage:
    route: Route
    by: list[str]

    @property
    def covered(self) -> bool:
        return bool(self.by)


def attribute(routes: list[Route], seen: dict[str, set[str]],
              verb_seen: dict[tuple[str, str], set[str]] | None = None,
              ) -> list[Coverage]:
    """Credit each route with the artifacts that reached it. PATH IS NOT ENOUGH -- THE VERB
    DECIDES TOO.

    Every `seen` map this tool builds comes from a browser NAVIGATION -- an evidence CSV's
    Requested/Final URL, a crawl's `page.goto`, a layout probe's -- and a navigation is a GET.
    So a path match says "some GET reached this URL", which is no evidence at all about
    `DELETE /users/:id`. Crediting it anyway is a false claim about the riskiest routes on the
    list, and it is loudest exactly where it is least affordable: measured against Retask,
    78 of 201 routes counted as covered were non-GET routes credited from a GET: the tool
    reported 76% coverage over 263 routes where the honest figure is 46%. `DELETE /logout` was
    "covered" by a route sweep that only ever navigated; `PUT` and `PATCH /passwords/:token` were
    both "covered" by one page view.

    This rule was already stated and enforced twice below -- on the crawl axis and on the
    responsive axis, each with its own fixture -- and missing here, on the one axis whose
    percentage anybody quotes (#1037). It lives in this function now so there is ONE home for it.

    No evidence profile records an HTTP method (checked: none of the 90-odd declared columns is
    a verb, and `detect_profile` matches headers exactly, so one cannot be added without
    migrating every existing artifact). Until such a channel exists, a non-GET route CANNOT be
    covered, and the honest report is that it is a gap -- already flagged `non-GET` in the
    listing. Giving it credit does not make it tested; it makes the number wrong.
    """
    verb_seen = verb_seen or {}
    out: list[Coverage] = []
    for route in routes:
        rx = compile_pattern(route.pattern)
        artifacts: set[str] = set()
        if not route.destructive:
            for path, sources in seen.items():
                if rx.match(path):
                    artifacts |= sources
        # THE ONLY WAY A NON-GET ROUTE IS EVER CREDITED (#1039). Exact on both halves: the verb
        # and the route pattern as `bin/rails routes` prints them. No regex, because there is
        # nothing to infer -- the artifact names the route it drove. Applied to GET-like routes
        # too rather than being gated on `destructive`: `validate_evidence` already refuses a
        # GET row in this profile, so gating here would be a second place enforcing one rule,
        # and the second one is what goes stale.
        for (verb, pattern), sources in verb_seen.items():
            if verb == route.verb.upper() and pattern == route.pattern:
                artifacts |= sources
        out.append(Coverage(route, sorted(artifacts)))
    return out


def excluded(routes: list[Route], patterns: list[str]) -> tuple[list[Route], list[Route]]:
    """Split into (kept, dropped). Declared exclusions only -- nothing is guessed."""
    if not patterns:
        return routes, []
    kept, dropped = [], []
    for route in routes:
        if any(p in route.pattern or p in route.controller for p in patterns):
            dropped.append(route)
        else:
            kept.append(route)
    return kept, dropped


def priority(cov: Coverage, auth_prefixes: list[str]) -> tuple[int, str]:
    """Sort key for the gap report: destructive first, then authenticated, then the rest."""
    authenticated = any(cov.route.pattern.startswith(p) for p in auth_prefixes)
    if cov.route.destructive:
        return (0, cov.route.key)
    if authenticated:
        return (1, cov.route.key)
    return (2, cov.route.key)


# ---------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------
def load_config(path: Path) -> dict[str, object]:
    """Read the `coverage:` block, via the ONE shared reader (#792).

    This was a local parser whose key pattern was anchored to end-of-line, so every key carrying a
    trailing comment -- the exact form `/qa-flow:setup-qa` scaffolds -- was silently dropped, and a
    real project's block parsed to `{}`. It also accepted only an EMPTY inline list, so
    `exclude: ["/up"]` was lost with no comment in sight. `blast_radius` had a second copy with the
    same defect; two parsers is how one defect existed twice, so there is one now.
    """
    return qa_config.load_section(path, "coverage")

# ---------------------------------------------------------------------------------------
# Provenance -- what tree, and under what environment, the route inventory was taken from
# ---------------------------------------------------------------------------------------
# `qa/reports/routes.json` is GENERATED and deliberately not committed, regenerated per tree from
# `bin/rails routes`. So the denominator of every percentage this tool prints is a property of the
# tree and the shell that enumerated it -- and until now nothing in the output said which.
#
# Measured, across one downstream project in one afternoon (#1047): five different denominators --
# 263 (a raw line count under RAILS_ENV=test through an unpinned invocation), 275 (the same tree
# under RAILS_ENV=development), 227 (correct, through the wrapper), and 226 and 223 from two older
# commits. **None of them was wrong.** Each correctly measured a different object, and four sessions
# quoted them to each other as though they were one number that had to be reconciled. Two spent
# real effort trying before anyone established that they could not be.
#
# COMMITTING THE FILE IS NOT THE FIX and the wrapper already refuses it, for the right reason: a
# committed inventory is a different stale object, not a fixed one. What was missing is that the
# report could not say what it had measured.
#
# THE PRINTED SUMMARY CARRIES THIS AS WELL AS THE JSON, and that is the load-bearing half: the
# summary is what gets pasted into an issue comment, and a number pasted without its provenance is
# exactly how all five of those figures travelled.
def _git(*args: str) -> str | None:
    """A git value, or None outside a repository. Never raises -- provenance is never the failure."""
    try:
        r = subprocess.run(("git", *args), capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def enumeration_provenance() -> dict:
    """What tree and environment this enumeration is a measurement of."""
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "commit": commit,
        # A dirty tree means the inventory may include routes that are in no commit, so the
        # `commit` above does not fully identify it. Recorded rather than refused: enumerating
        # mid-change is normal, and a tool that refused it would be routed around.
        "dirty": None if status is None else bool(status.strip()),
        # The single biggest cause of the spread above. `rails routes` emits a different route set
        # per environment, and nothing about a bare number reveals which one produced it.
        "rails_env": os.environ.get("RAILS_ENV"),
        "enumerated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def provenance_lines(prov: dict | None) -> list[str]:
    """The human-readable provenance block, printed under every coverage number."""
    if not prov:
        # An inventory written before #1047 has no provenance block at all. That is NOT an error
        # and must never be one -- it is what every already-written file looks like, and refusing
        # it would make the upgrade indistinguishable from a broken tool. Say the honest thing:
        # the number is unattributable, which is the state this whole change is about.
        return ["  route inventory provenance: UNKNOWN — enumerated before provenance was "
                "recorded, so this percentage cannot be attributed to a tree. Re-run `enumerate`."]
    recorded = prov.get("commit")
    # TRUNCATE ONLY A SHA (#1062). `[:9]` was applied to the fallback too, so a tree with no git
    # printed `route inventory: not a git` -- which reads like a truncated or corrupted SHA rather
    # than the deliberate "there is no git tree here" the code means. On a PROVENANCE line, the one
    # a reader consults to decide whether a percentage can be attributed to a tree, that is the
    # opposite of the job. Same class as the abbreviated-SHA defect in `same_commit`: a RENDERING
    # treated as the value.
    commit = str(recorded)[:9] if recorded else "not a git tree"
    dirty = prov.get("dirty")
    env = prov.get("rails_env") or "unset"
    mark = "" if not dirty else " +dirty"
    return [f"  route inventory: {commit}{mark} · RAILS_ENV={env} · enumerated "
            f"{prov.get('enumerated_at') or 'at an unrecorded time'}"]


# Distinguishes "caller did not supply a HEAD, look one up" from "there is NO HEAD" -- which
# are different states with different answers, and `None` cannot mean both. Collapsing them is
# the same mistake this whole issue is about: an instrument that cannot tell two states apart.
_LOOKUP_HEAD = object()


def same_commit(a: str | None, b: str | None) -> bool:
    """Do these two strings name the same commit, at whatever length each was written?

    THE REGRESSION THIS EXISTS FOR. `stale_inventory` compared the recorded commit to `HEAD` with
    `==`, which is a comparison of two RENDERINGS rather than of two commits. Shipped in v1.133.0
    and it refused a downstream `doctrine` job on the first run after the bump:

        REFUSING to report coverage: the route inventory was enumerated from 978814d
        but the working tree is at 978814d29.

    **Those are the same commit.** The enumerate and the report ran in the same CI job, seconds
    apart, on the same tree -- so the gate refused the one state it must always accept, an
    inventory enumerated from the tree being measured. And it refused with a well-formed message
    naming a real concern, which is what made it convincing rather than obviously broken.

    Git abbreviates to an unambiguous prefix and the length is not fixed -- it grows with the
    repository and is configurable (`core.abbrev`), so any two renderings of one SHA may differ in
    length. Seven hex characters is git's own floor for a short SHA, so a prefix match at or above
    that is treated as the same commit. Below it, refuse to guess: a 4-character "prefix" is not
    identification, and silently accepting it would rebuild the defect this whole check exists to
    catch.
    """
    if not a or not b:
        return False
    x, y = a.strip().lower(), b.strip().lower()
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return len(short) >= 7 and long_.startswith(short)


# Paths that DEFINE routes. Anything else can change without moving a single route, and a commit
# touching only those is the overwhelming majority of commits on a working branch -- which is why
# refusing on `HEAD != recorded` alone left this gate permanently dark (#1129).
# NOT `ROUTE_SOURCES` -- that name is already a dict mapping an evidence profile to its columns,
# and shadowing it broke `visited_paths` on the first selftest run.
ROUTE_SOURCE_PATHS = ("config/routes.rb", "config/routes/")


def route_sources_changed(recorded: str, head: str) -> bool | None:
    """Did anything that DEFINES routes change between these two commits? None = cannot tell.

    THE NARROWING THIS EXISTS FOR (#1129). The inventory is stamped with the commit that produced
    it, and any later commit invalidated it -- so on a branch with active work the gate was ERROR
    from the first commit until someone re-enumerated, and measured 11 commits without ever once
    producing a figure. **The gate was dark exactly where it is needed**, because a branch that
    adds a route is the branch whose coverage matters, and a red verdict on every run stops being
    read at all.

    A commit that touches no route source cannot have moved a route, so the inventory still
    describes the tree. Asking git which files changed is exact and needs no application boot.

    CANNOT TELL IS NOT CAN (None): a shallow clone, a commit this clone does not have, or no git at
    all, and the caller refuses as before. Guessing "probably fine" here would rebuild the defect
    the refusal exists to prevent.

    THE LIMIT, stated because it is real: routes drawn from code OUTSIDE these paths -- a constant
    in an initializer, a gem that mounts an engine on a version bump -- change the route set
    without touching them, and this returns False for such a commit. That is a narrower instrument
    than "any commit at all", not a blind one, and the alternative measured at 0 verdicts in 11
    commits.
    """
    changed = _git("diff", "--name-only", f"{recorded}..{head}")
    if changed is None:
        return None
    return names_a_route_source(changed.splitlines())


def names_a_route_source(paths: list[str]) -> bool:
    """Does any of these paths DEFINE routes? Pure, so it is decidable with no git tree.

    Split out for the same reason `head` is injectable on `stale_inventory`: the mutation harness
    stages the subject into a plain tempdir that is not a repository, and a rule that could only be
    reached through a live `git diff` would pass vacuously there.
    """
    for path in paths:
        path = path.strip()
        if any(path == src or path.startswith(src) or path.endswith("/" + src)
               for src in ROUTE_SOURCE_PATHS):
            return True
    return False


def stale_inventory(prov: dict | None, head: str | None | object = _LOOKUP_HEAD,
                    moved: bool | None | object = _LOOKUP_HEAD) -> str | None:
    """Why this inventory does not describe the working tree, or None if it does (or cannot tell).

    REFUSES rather than warns, and only when it can PROVE the mismatch. This number feeds a
    ratchet: a floor recorded from one tree and compared against a run in another is comparing two
    different measurements and calling the difference a regression -- or calling a real regression
    no change. A warning on that is one people learn to scroll past, which is the same argument
    #1039 makes about a gap nobody can clear.

    Three states, and only the first is a refusal:

      * the recorded commit differs from HEAD          -> REFUSE, the inventory is another tree's
      * no provenance, or not a git tree, or unknown   -> proceed; reported as UNKNOWN above
      * recorded commit == HEAD                        -> proceed

    A DIRTY tree is deliberately not a refusal on its own. Enumerating mid-change is normal, and
    `git status --porcelain` says nothing about whether the change touched `routes.rb`.
    """
    if not prov:
        return None
    recorded = prov.get("commit")
    if not recorded:
        return None
    # `head` is injectable so this is decidable without an ambient git tree. It is not a
    # convenience: the mutation harness stages the subject into a plain tempdir that is NOT a
    # repository, so a version reading HEAD internally answered None there and every assertion
    # about staleness passed vacuously. The harness's own INERT-baseline check caught that, which
    # is the same class this rule is about -- an instrument that cannot see the thing it measures.
    head = _git("rev-parse", "HEAD") if head is _LOOKUP_HEAD else head
    # `same_commit`, never `==`. The two sides are written by different callers at different
    # times and need not be the same LENGTH to be the same commit.
    if not head or same_commit(head, recorded):
        return None
    # A DIFFERENT COMMIT IS NOT YET A DIFFERENT ROUTE SET (#1129). Refusing on the sha alone made
    # this permanently dark on every working branch; ask git whether a route source actually moved.
    if moved is _LOOKUP_HEAD:
        moved = route_sources_changed(recorded, head)
    if moved is False:
        return None
    cannot_tell = " (and this clone cannot diff the two commits, so it is assumed)" if moved is None else ""
    return (f"the route inventory was enumerated from {recorded[:9]} but the working tree is at "
            f"{head[:9]}, and a route source changed between them{cannot_tell}. The denominator "
            f"would be one tree's route set measured against another tree's evidence, and the "
            f"difference between them would read as coverage.\n"
            f"  Clear it by re-enumerating in this tree:\n"
            f"    bin/rails routes > qa/reports/routes.txt\n"
            f"    python3 route_coverage.py enumerate --rails qa/reports/routes.txt")


def cmd_enumerate(args: argparse.Namespace) -> int:
    routes: list[Route] = []
    unparsed: list[str] = []
    if args.rails:
        text = Path(args.rails).read_text(encoding="utf-8")
        routes += from_rails(text)
        unparsed = unparsed_rails_rows(text)
    if args.sitemap:
        routes += from_sitemap(Path(args.sitemap).read_text(encoding="utf-8"))
    if args.fs:
        routes += from_fs(Path(args.fs))
    if not routes:
        print("no routes enumerated -- pass --rails, --sitemap or --fs", file=sys.stderr)
        return 2

    unique = {r.key: r for r in routes}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prov = enumeration_provenance()
    out.write_text(
        json.dumps({"provenance": prov, "routes": [asdict(r) for r in unique.values()]},
                   indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"enumerated {len(unique)} route(s) -> {out}")
    for line in provenance_lines(prov):
        print(line)
    if unparsed:
        # EXIT 2, and loudly. Every number downstream of this file is a claim about the routes in
        # it, so a partial enumeration is worse than none: it produces a confident percentage over
        # an application that does not exist. Printing a few rows rather than a count, because the
        # shape of the row is what tells you which format changed (#820's rule: findings, not a
        # tally).
        print(f"\nREFUSING a partial enumeration: {len(unparsed)} verb-bearing row(s) in "
              f"{args.rails} did not parse. Coverage over this file would be a percentage of a "
              "different application.", file=sys.stderr)
        for line in unparsed[:5]:
            print(f"  ? {line[:160]}", file=sys.stderr)
        if len(unparsed) > 5:
            print(f"  … and {len(unparsed) - 5} more", file=sys.stderr)
        return 2
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    routes = [Route(**r) for r in payload["routes"]]
    prov = payload.get("provenance")
    # REFUSED BEFORE ANY NUMBER IS COMPUTED, let alone printed. A percentage over another tree's
    # route set is not a worse number, it is a number about nothing -- and printing it alongside
    # the refusal would let it be pasted onward, which is how the five figures in #1047 travelled.
    stale = stale_inventory(prov)
    if stale:
        # EXIT 3, NOT 2 (#1129). The refusal is right -- a percentage over another tree's route set
        # is a number about nothing -- but the STATE is ordinary: a derived input went stale on a
        # moving branch, which is not a defect in this check. `project_gates.py` reads 2 as ERROR
        # and routes it to the toolchain's own tracker, so every run on every working branch filed
        # a normal condition as our bug. 3 is the code that runner already has for "the check read
        # the project and says it does not apply", and it carries this reason with it.
        print(f"NOT APPLICABLE — coverage cannot be reported: {stale}", file=sys.stderr)
        return 3
    config = load_config(Path(args.config))
    exclusions = [str(x) for x in config.get("exclude", [])]
    auth_prefixes = [str(x) for x in config.get("authenticated_prefixes", [])]
    small_max = _small_max(config)
    responsive_exclusions = [str(x) for x in config.get("responsive_exclude", [])]

    kept, dropped = excluded(routes, exclusions)
    evidence = [Path(d) for d in args.evidence]
    unreadable = unusable_artifacts(evidence)
    seen = visited_paths(evidence)
    coverage = attribute(kept, seen, verb_paths(evidence))
    gaps = sorted((c for c in coverage if not c.covered), key=lambda c: priority(c, auth_prefixes))
    covered = [c for c in coverage if c.covered]

    # THE THIRD STATE. A gap that a crawl loaded is still a gap -- `crawled` is a strict subset
    # of `gaps`, never added to `covered` -- but it is a different KIND of gap, and saying so is
    # what stops "untested" reading as "unvisited".
    # `destructive` routes are excluded, but no longer HERE: a crawler navigates with `page.goto`,
    # which is a GET, and `attribute` now refuses that credit for every navigation-derived map
    # (#1037). This site kept its own copy of the rule while the `covered` axis had none; the rule
    # has one home now, and the fixture below -- which crawled `/users/7` and saw
    # `DELETE /users/:id` light up -- still proves it from there.
    visit_only = {c.route.key for c in attribute(kept, visit_only_paths(evidence))
                  if c.covered}
    crawled = [c for c in gaps if c.route.key in visit_only]

    # ---- AXIS TWO. Orthogonal to `covered`, never averaged with it. -----------------------
    # A route asserted at 1280px and never seen at 390px is fully covered on axis one and absent
    # here, which is precisely the state that shipped 71-83% of a table hidden (#953).
    # NON-GET ROUTES ARE NOT IN THE DENOMINATOR, for the same reason they are not in `visit_only`:
    # a layout probe navigates with `page.goto`, which is a GET, so a `DELETE /users/:id` cannot be
    # measured at any width. Counting it as unmeasured would make the axis permanently unreachable
    # and put the loudest gap on the routes a browser is not the instrument for. Caught by this
    # tool's own fixture, which measured two pages and still reported `DELETE /users/:id` missing.
    responsive_kept, responsive_dropped = excluded(
        [r for r in kept if not r.destructive], responsive_exclusions)
    small_seen = small_viewport_paths(evidence, small_max)
    measured_small = [c for c in attribute(responsive_kept, small_seen) if c.covered]
    unmeasured = sorted((c for c in attribute(responsive_kept, small_seen) if not c.covered),
                        key=lambda c: priority(c, auth_prefixes))
    small_pct = (len(measured_small) * 100 // len(responsive_kept)) if responsive_kept else 0

    pct = (len(covered) * 100 // len(kept)) if kept else 0
    print(f"route coverage: {len(covered)}/{len(kept)} ({pct}%) — {len(gaps)} untested")
    # Printed unconditionally, including the 0 case: a number that appears only when non-zero
    # cannot be read as "the crawler reached nothing" versus "nobody looked".
    print(f"  of those, {len(crawled)} visited by a crawl but never asserted, "
          f"{len(gaps) - len(crawled)} never reached at all")

    # #1039. Printed unconditionally, next to the number it qualifies. An artifact that failed to
    # parse contributed nothing, and "contributed nothing" looks exactly like "had no matching
    # rows" in every figure above -- so the count has to appear beside them or it is not a warning,
    # it is a footnote nobody reaches. The zero line is the load-bearing one: it is what makes a
    # NON-zero line mean something on the day a contract moves.
    # Printed directly under the percentage, not in a footer. The summary is what gets pasted
    # into an issue comment, and a number that travels without its provenance is the whole defect.
    for line in provenance_lines(prov):
        print(line)
    print(f"  {len(unreadable)} evidence artifact(s) could not be read against any contract")
    for where, why in unreadable:
        print(f"    ! {where}: {why}")

    # Printed unconditionally, including 0/0: "nothing was measured small" and "there is no
    # small-viewport evidence at all" must not look like the same clean line, and neither may look
    # like a pass. A route absent here is a gap, reported the way an unasserted route is.
    print(f"responsive coverage: {len(measured_small)}/{len(responsive_kept)} ({small_pct}%) "
          f"measured at ≤{small_max}px — {len(unmeasured)} never measured small "
          f"(GET-like routes only)")
    if not small_seen:
        print(f"  no {SMALL_VIEWPORT_ARTIFACT} evidence found — run "
              f"`crawl_collector.js --layout --viewport 390x844`. Nothing was measured small, "
              "which is not the same as nothing being wrong.")

    # Suppression stays visible, always -- including when nothing was excluded.
    print(f"excluded by config: {len(dropped)}")
    for route in dropped:
        print(f"  - {route.key}")
    print(f"excluded from the responsive axis by config: {len(responsive_dropped)}")
    for route in responsive_dropped:
        print(f"  - {route.key}")

    if gaps:
        print("\nuntested routes, highest risk first:")
        area = None
        for cov in gaps:
            if cov.route.area != area:
                area = cov.route.area
                print(f"  [{area}]")
            flags = []
            if cov.route.destructive:
                flags.append("non-GET")
            if any(cov.route.pattern.startswith(p) for p in auth_prefixes):
                flags.append("authenticated")
            if cov.route.key in visit_only:
                flags.append("crawled, unasserted")
            suffix = f"  ({', '.join(flags)})" if flags else ""
            print(f"    {cov.route.key}{suffix}")

    if unmeasured:
        print(f"\nnever measured below {small_max}px, highest risk first:")
        area = None
        for cov in unmeasured:
            if cov.route.area != area:
                area = cov.route.area
                print(f"  [{area}]")
            # A route nothing asserted AND nothing measured small is the worst of both, and
            # saying so is what stops the two lists reading as one long backlog.
            flags = ["also untested"] if not cov.covered and cov.route.key in {
                g.route.key for g in gaps} else []
            suffix = f"  ({', '.join(flags)})" if flags else ""
            print(f"    {cov.route.key}{suffix}")

    if args.trend:
        trend = Path(args.trend)
        trend.parent.mkdir(parents=True, exist_ok=True)
        with trend.open("a", encoding="utf-8") as handle:
            # THE RATCHET READS THIS FILE. A floor recorded from one tree and compared against
            # a run in another is two different measurements being called a regression, so the
            # provenance has to survive into the record, not just the screen.
            handle.write(json.dumps({
                "provenance": prov,
                "routes": len(kept), "covered": len(covered),
                "untested": len(gaps), "crawled_unasserted": len(crawled),
                "excluded": len(dropped), "percent": pct,
                "measured_small": len(measured_small), "unmeasured_small": len(unmeasured),
                "small_percent": small_pct, "small_viewport_max": small_max,
            }) + "\n")

    if args.json:
        print(json.dumps({
            "provenance": prov,
            "total": len(kept), "covered": len(covered), "untested": len(gaps),
            "excluded": [r.key for r in dropped], "percent": pct,
            "crawled_unasserted": sorted(visit_only),
            "small_viewport_max": small_max,
            "measured_small": len(measured_small),
            "unmeasured_small": [c.route.key for c in unmeasured],
            "small_percent": small_pct,
            "responsive_excluded": [r.key for r in responsive_dropped],
            "gaps": [{"route": c.route.key, "area": c.route.area,
                      "crawled": c.route.key in visit_only} for c in gaps],
            "attribution": {c.route.key: c.by for c in covered},
        }, indent=2))

    # Reporting a gap is not a failure: the gap IS the deliverable. `--fail-on-untested` and
    # `--fail-on-unmeasured` are for a team that has reached full coverage on an axis and wants to
    # keep it. Two flags rather than one, because the axes are reached at different times and a
    # single flag would make the easier one hostage to the harder.
    #
    # AND THE CHOICE IS THE PROJECT'S (#1029). `checks.json` hardcoded `--fail-on-untested`, so
    # every project adopting qa-flow before reaching total coverage got a permanently red gate it
    # could not opt out of -- the flag lived in the plugin, not in `qa/qa.config.yml`. One
    # downstream project had written the opposite decision into its own CI ("that flag is for a
    # project at full coverage; this one is at 197/224, so arming it would paint the promotion red
    # on a backlog rather than on a regression") and the plugin overrode it. Worse, the red step
    # aborted the job before the ratchet that project actually intended, so the plugin's opinion
    # MASKED the project's own gate.
    untested, unmeasured_axis = fail_axes(args, config)
    failed = (untested and gaps) or (unmeasured_axis and unmeasured)
    return 1 if failed else 0


# `coverage.fail_on` in the project's own config. `none` is the DEFAULT because a partial-coverage
# project is the normal case and the gap is the deliverable — a gate red for a known reason is a
# gate people learn to merge past, which costs more than the gap it names.
FAIL_ON = {"none": (False, False), "untested": (True, False),
           "unmeasured": (False, True), "both": (True, True)}


def fail_axes(args: argparse.Namespace, config: dict[str, object]) -> tuple[bool, bool]:
    """Which axes turn a gap into an exit 1: the project's `coverage.fail_on`, or the CLI flags.

    An explicit flag WINS, so a project that has reached full coverage can still arm one axis in its
    own CI without editing config, and so this change breaks nobody who was passing the flag on
    purpose. An unknown value is refused rather than silently treated as `none`: a typo in
    `fail_on: untetsed` would otherwise disarm the gate and read exactly like a passing one.
    """
    if args.fail_on_untested or args.fail_on_unmeasured:
        return bool(args.fail_on_untested), bool(args.fail_on_unmeasured)
    raw = str(config.get("fail_on", "none")).strip().lower() or "none"
    if raw not in FAIL_ON:
        raise SystemExit(f"coverage.fail_on is {raw!r}, not one of "
                         f"{', '.join(sorted(FAIL_ON))} — a value this reader does not know would "
                         "silently disarm the gate, which reads exactly like passing")
    return FAIL_ON[raw]


def _small_max(config: dict[str, object]) -> int:
    """`coverage.small_viewport_max`, or the built-in boundary. Refuses a value that is not a width."""
    raw = config.get("small_viewport_max")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_SMALL_VIEWPORT_MAX
    try:
        width = int(str(raw).strip())
    except ValueError:
        raise SystemExit(f"coverage.small_viewport_max is {raw!r}, which is not a pixel width")
    if width < 200:
        raise SystemExit(f"coverage.small_viewport_max is {width}, narrower than any real device — "
                         "a boundary below every viewport makes the axis unreachable rather than "
                         "strict")
    return width


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route enumeration and QA coverage attribution.")
    parser.add_argument("--selftest", action="store_true", help="prove the rules fire and stay silent")
    sub = parser.add_subparsers(dest="command")

    e = sub.add_parser("enumerate", help="build routes.json from a stack-native source")
    e.add_argument("--rails", help="output of `bin/rails routes`")
    e.add_argument("--sitemap", help="a sitemap.xml")
    e.add_argument("--fs", help="a filesystem-routed directory")
    e.add_argument("--out", default="qa/reports/routes.json")
    e.set_defaults(func=cmd_enumerate)

    r = sub.add_parser("report", help="attribute coverage and report the gap")
    r.add_argument("--routes", default="qa/reports/routes.json")
    r.add_argument("--evidence", action="append", default=[], help="dir of evidence CSVs (repeatable)")
    r.add_argument("--config", default="qa/qa.config.yml")
    r.add_argument("--trend", default="qa/reports/route-coverage-trend.jsonl")
    r.add_argument("--json", action="store_true")
    r.add_argument("--fail-on-untested", action="store_true")
    r.add_argument("--fail-on-unmeasured", action="store_true",
                   help="fail when a route was never measured at a small viewport")
    r.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    if args.selftest:
        import route_coverage_selftest as st

        return st.run()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
