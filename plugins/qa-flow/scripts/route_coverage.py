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

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_evidence as ve  # noqa: E402

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

# Profiles that must NOT contribute coverage, and why. `findings` carries `Example Routes`, but
# those are up to three EXAMPLES of a deduplicated defect -- counting them would credit coverage
# for routes nobody visited and inflate the number this tool exists to make honest.
ROUTE_LESS: dict[str, str] = {
    "findings": "Example Routes lists up to 3 examples of a deduped finding, not a visit log",
}

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
_RAILS_ROW = re.compile(
    r"^\s*(?P<prefix>[a-z0-9_]*)\s+"
    r"(?P<verb>GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)(?:\|[A-Z|]+)?\s+"
    r"(?P<pattern>/\S*)\s+"
    r"(?P<controller>\S+)\s*$"
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
                if row["Status"].lower() in {ve.SKIPPED_STATUS}:
                    continue  # never visited, and not claimed to be
                for column in columns:
                    raw = row.get(column, "")
                    if not raw:
                        continue
                    p = normalise(re.sub(r"^[a-z]+://[^/]+", "", raw.strip()))
                    if p.startswith("/"):
                        seen.setdefault(p, set()).add(f"{profile.name}:{path.name}")
    return seen


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


@dataclass
class Coverage:
    route: Route
    by: list[str]

    @property
    def covered(self) -> bool:
        return bool(self.by)


def attribute(routes: list[Route], seen: dict[str, set[str]]) -> list[Coverage]:
    out: list[Coverage] = []
    for route in routes:
        rx = compile_pattern(route.pattern)
        artifacts: set[str] = set()
        for path, sources in seen.items():
            if rx.match(path):
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
    """Read the `coverage:` block. Deliberately a tiny parser, not a YAML dependency."""
    if not path.is_file():
        return {}
    block: dict[str, list[str]] = {}
    current: str | None = None
    in_coverage = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^coverage:", line):
            in_coverage = True
            continue
        if in_coverage and re.match(r"^\S", line):
            break  # dedented out of the block
        if not in_coverage:
            continue
        key = re.match(r"^\s{2}(\w+):\s*(\[\s*\])?\s*$", line)
        if key:
            current = key.group(1)
            block[current] = []
            continue
        item = re.match(r"^\s{4}-\s*['\"]?([^'\"#]+?)['\"]?\s*(?:#.*)?$", line)
        if item and current:
            block[current].append(item.group(1).strip())
    return dict(block)


def cmd_enumerate(args: argparse.Namespace) -> int:
    routes: list[Route] = []
    if args.rails:
        routes += from_rails(Path(args.rails).read_text(encoding="utf-8"))
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
    out.write_text(
        json.dumps({"routes": [asdict(r) for r in unique.values()]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"enumerated {len(unique)} route(s) -> {out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    routes = [Route(**r) for r in payload["routes"]]
    config = load_config(Path(args.config))
    exclusions = [str(x) for x in config.get("exclude", [])]
    auth_prefixes = [str(x) for x in config.get("authenticated_prefixes", [])]

    kept, dropped = excluded(routes, exclusions)
    evidence = [Path(d) for d in args.evidence]
    seen = visited_paths(evidence)
    coverage = attribute(kept, seen)
    gaps = sorted((c for c in coverage if not c.covered), key=lambda c: priority(c, auth_prefixes))
    covered = [c for c in coverage if c.covered]

    # THE THIRD STATE. A gap that a crawl loaded is still a gap -- `crawled` is a strict subset
    # of `gaps`, never added to `covered` -- but it is a different KIND of gap, and saying so is
    # what stops "untested" reading as "unvisited".
    # `destructive` is excluded: a crawler navigates with `page.goto`, which is a GET. A DELETE
    # route whose path happens to match a crawled URL was NOT visited, and saying it was would be
    # a false claim about the riskiest routes on the list. Caught by this tool's own fixture,
    # which crawled `/users/7` and saw `DELETE /users/:id` light up.
    visit_only = {c.route.key for c in attribute(kept, visit_only_paths(evidence))
                  if c.covered and not c.route.destructive}
    crawled = [c for c in gaps if c.route.key in visit_only]

    pct = (len(covered) * 100 // len(kept)) if kept else 0
    print(f"route coverage: {len(covered)}/{len(kept)} ({pct}%) — {len(gaps)} untested")
    # Printed unconditionally, including the 0 case: a number that appears only when non-zero
    # cannot be read as "the crawler reached nothing" versus "nobody looked".
    print(f"  of those, {len(crawled)} visited by a crawl but never asserted, "
          f"{len(gaps) - len(crawled)} never reached at all")

    # Suppression stays visible, always -- including when nothing was excluded.
    print(f"excluded by config: {len(dropped)}")
    for route in dropped:
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

    if args.trend:
        trend = Path(args.trend)
        trend.parent.mkdir(parents=True, exist_ok=True)
        with trend.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "routes": len(kept), "covered": len(covered),
                "untested": len(gaps), "crawled_unasserted": len(crawled),
                "excluded": len(dropped), "percent": pct,
            }) + "\n")

    if args.json:
        print(json.dumps({
            "total": len(kept), "covered": len(covered), "untested": len(gaps),
            "excluded": [r.key for r in dropped], "percent": pct,
            "crawled_unasserted": sorted(visit_only),
            "gaps": [{"route": c.route.key, "area": c.route.area,
                      "crawled": c.route.key in visit_only} for c in gaps],
            "attribution": {c.route.key: c.by for c in covered},
        }, indent=2))

    # Reporting a gap is not a failure: the gap IS the deliverable. `--fail-on-untested` is for
    # a team that has reached full coverage and wants to keep it.
    return 1 if (args.fail_on_untested and gaps) else 0


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
