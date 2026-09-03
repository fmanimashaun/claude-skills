#!/usr/bin/env python3
"""Derive a regression scope from the change instead of guessing it (#134).

Run:  python3 blast_radius.py derive --changed-from qa/reports/changed.txt
      python3 blast_radius.py derive --changed-from - --graph docs/architecture/graph.json
      python3 blast_radius.py --selftest

THE PROBLEM. `/qa-flow:verify` selects its regression scope "by blast radius", and that selection
was the agent's judgement with nothing under it. Judgement is simultaneously at risk of being too
narrow (a dependent path nobody thought of) and too wide (re-run everything to feel safe), and
neither is defensible at a `dev -> main` gate. Two artefacts that make it derivable already ship
and nothing consumed them: the **route table** (#119, `route_coverage.py enumerate`) and the
**architecture graph** (#141, `rails-flow/scripts/architecture_graph.py`).

So this is a CONSUMER, not a second extractor. It reads `{nodes, edges}` and reverse-walks:

    radius(node) = { e.from : e in edges, e.to == node }   # then transitively, to --depth

and it reads `routes.json` rather than re-deriving routes from anything.

A FLOOR, NEVER A CEILING. The graph's extractor is regex-based, not an AST, so structure created
by metaprogramming is invisible to it and is reported in the graph's own `notes` (surfaced here,
verbatim). A computed radius may therefore justify EXPANDING a scope; it may never be cited to
shrink one below the certification baseline. That sentence is the whole safety argument and it is
printed on every report, not just written here.

WHY THIS GUESSES AT RISK WHEN `route_coverage.py` REFUSES TO GUESS AT AUTH. The sibling tool
declines to infer whether a route is authenticated, because a heuristic would be wrong on exactly
the routes that matter. The direction of the error is what differs. Over-crediting COVERAGE fails
unsafe -- it retires a question nobody then asks. Over-including a RISK axis fails safe -- it
widens the test scope and asks for approval. So the name hints below are deliberately
over-inclusive, every hit prints the pattern that fired it, and config may only ADD to them:
a project cannot switch an axis off, because "auth, tenancy, money, migrations, or a shared
concern force the wider selection" is stated as non-negotiable in `/qa-flow:verify` and a
configurable non-negotiable is not one.

NO SILENT NARROWING. Every route not selected, every node past the depth cutoff and every changed
file this tool could not account for is PRINTED with its reason -- including when the list is
empty. A scope that shrank for a reason nobody recorded is how a regression escapes a gate that
looked green.

Exit codes:
  0  a targeted scope was derived and every changed file was accounted for
  1  findings -- a risk axis fired (wide selection, approval required) and/or an app-relevant
     changed file could not be accounted for, so the radius is under-determined
  2  unusable -- no changed files, or an input that could not be read

Stdlib only, no network, no git, no app boot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_config  # noqa: E402 -- sibling module, one reader for qa.config.yml (#792)

# --------------------------------------------------------------------------------------------
# Risk axes
# --------------------------------------------------------------------------------------------
# The five named in `/qa-flow:verify` and `qa-lead`, in the order they are reported.
RISK_AXES = ("auth", "tenancy", "money", "migration", "shared-concern")

# Structurally certain: these are Rails layout, not a guess about naming. A file under
# `db/migrate/` IS a migration; a file under any `concerns/` directory IS shared by definition.
STRUCTURAL_RISK: dict[str, tuple[str, ...]] = {
    "migration": ("db/migrate/", "db/schema.rb", "db/structure.sql"),
    "shared-concern": ("/concerns/", "app/views/layouts/", "app/helpers/application_helper.rb"),
}

# Name hints: over-inclusive on purpose (see the module docstring). Matched as substrings against
# the lowercased POSIX path, so `app/models/invoice.rb` and `app/jobs/invoice_mailer_job.rb` both
# hit `money`.
NAME_RISK: dict[str, tuple[str, ...]] = {
    "auth": ("auth", "session", "password", "login", "sign_in", "signin", "devise",
             "permission", "policy", "policies", "role", "ability", "credential", "token"),
    "tenancy": ("tenant", "account", "organization", "organisation", "workspace", "company",
                "app/models/current.rb"),
    "money": ("payment", "invoice", "billing", "charge", "subscription", "price", "pricing",
              "order", "ledger", "refund", "wallet", "transaction", "checkout", "coupon",
              "discount", "payout", "tax"),
}

# Graph tags that carry a risk claim derived from SOURCE rather than from a filename. Strictly
# better evidence than a name hint, so it is used when the graph is present.
#
# `authenticated` is deliberately NOT here. Rails 8's generated auth is opt-out, so
# `architecture_graph.py` tags every controller `authenticated` unless it declares otherwise --
# consuming it would classify every controller change as an auth change, and a classifier that
# always fires is one a team switches off. `authorized` is the opposite: it means the source
# actually calls `authorize`/`policy`/`can?`, which is a real claim about a real line.
TAG_RISK: dict[str, str] = {
    "tenant-scoped": "tenancy",
    "authorized": "auth",
}

# --------------------------------------------------------------------------------------------
# What counts as app code
# --------------------------------------------------------------------------------------------
# A changed file OUTSIDE these roots cannot affect app behaviour, so it is excluded WITH ITS
# REASON rather than treated as an unaccounted-for file. A changed file INSIDE them that no rule
# explains is UNRESOLVED -- a finding, and it forces the wide selection, because "I could not work
# out what this touches" must never read the same as "this touches nothing".
APP_ROOTS = ("app/", "lib/", "db/", "config/", "spec/", "test/")
APP_FILES = ("Gemfile", "Gemfile.lock", "Rakefile", "config.ru", "package.json",
             "yarn.lock", "package-lock.json")

TEST_ROOTS = ("spec/", "test/")


class Unusable(Exception):
    """Input this tool cannot read -- exit 2, never 1.

    Same split as `findings.py` and `validate_evidence.py`: 1 means "your change has a property
    you must act on", 2 means "this check could not run". Collapsing them sends someone hunting a
    scope problem that does not exist.
    """


# --------------------------------------------------------------------------------------------
# Minimal inflection
# --------------------------------------------------------------------------------------------
IRREGULAR = {"person": "people", "child": "children", "man": "men", "woman": "women",
             "leaf": "leaves", "life": "lives", "knife": "knives", "wife": "wives",
             "datum": "data", "medium": "media", "criterion": "criteria"}
UNCOUNTABLE = {"money", "information", "equipment", "series", "species", "news"}


def pluralize(word: str) -> str:
    """Enough Rails inflection for the convention fallback, and no more.

    A wrong plural costs a *missing candidate*, which surfaces as "no spec found at ..." in the
    report -- visible, not silent. That is why a 20-line table is the right size here and a gem
    would be the wrong dependency.
    """
    if word in UNCOUNTABLE:
        return word
    if word in IRREGULAR:
        return IRREGULAR[word]
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


# --------------------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Inclusion:
    """One affected unit and the edge that justifies its inclusion.

    `because` is the point of the whole tool. A scope list with no justification is a different
    guess, not a derivation.
    """

    unit: str
    because: str
    depth: int
    via: str          # "changed" | "graph" | "graph:<tool>" | "convention"


@dataclass(frozen=True)
class RiskHit:
    axis: str
    path: str
    because: str


@dataclass(frozen=True)
class TestTarget:
    path: str
    because: str
    present: bool


@dataclass(frozen=True)
class RouteTarget:
    key: str
    because: str
    in_route_table: bool


@dataclass(frozen=True)
class Exclusion:
    what: str
    reason: str


@dataclass
class Report:
    changed: list[str] = field(default_factory=list)
    resolution: dict[str, str] = field(default_factory=dict)   # path -> how it was accounted for
    unresolved: list[str] = field(default_factory=list)
    affected: list[Inclusion] = field(default_factory=list)
    routes: list[RouteTarget] = field(default_factory=list)
    tests: list[TestTarget] = field(default_factory=list)
    flows: list[Inclusion] = field(default_factory=list)
    risk: list[RiskHit] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)
    graph_notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def wide(self) -> bool:
        """The verdict. Either trigger forces the wider selection; both are reported separately."""
        return bool(self.risk) or bool(self.unresolved)


# --------------------------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------------------------
def read_changed(paths: list[str], from_file: str | None) -> list[str]:
    """Changed paths, one per line, from a file or `-` for stdin. Never derived by running git.

    Keeping git out means the tool is testable with a fixture and the input is a plain file the
    reviewer can read -- `docs/doctrine/harness-doctrine.md` §9. The caller writes
    `git diff --name-only <base>...HEAD > qa/reports/changed.txt` and that file is the evidence.
    """
    out: list[str] = list(paths)
    if from_file == "-":
        out += [line.strip() for line in sys.stdin.read().splitlines()]
    elif from_file:
        handle = Path(from_file)
        if not handle.is_file():
            raise Unusable(f"cannot read changed-file list: {from_file}")
        out += [line.strip() for line in handle.read_text(encoding="utf-8").splitlines()]
    cleaned = []
    for line in out:
        line = line.strip().replace("\\", "/")
        if line and not line.startswith("#"):
            cleaned.append(line)
    # Order-stable dedupe: two `--changed` flags naming one file must not double every inclusion.
    seen: set[str] = set()
    unique = []
    for path in cleaned:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    if not unique:
        raise Unusable("no changed files supplied -- pass --changed or --changed-from")
    return unique


def load_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Unusable(f"cannot read {what} at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Unusable(f"{what} at {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise Unusable(f"{what} at {path} is a {type(data).__name__}, not an object")
    return data


def load_config(path: Path) -> dict[str, object]:
    """Read the `blast_radius:` block, via the ONE shared reader (#792).

        blast_radius:
          exclude:
            - vendor/
          high_risk:
            money:
              - app/models/ledger_entry.rb

    Additive only: `high_risk` extends the built-in axes and can never empty one. The selftest pins
    that, because a config key that silently disables a non-negotiable rule is the whole loophole
    this tool exists to close.

    This was a local parser sharing a defect with `route_coverage`'s: the key pattern was anchored
    to end-of-line, so a key with a trailing comment was dropped -- and every key in the scaffolded
    block carries one, so the whole section parsed to `{}`. Two separately-written copies of one
    parser is how the same defect existed twice.
    """
    return qa_config.load_section(path, "blast_radius")


# --------------------------------------------------------------------------------------------
# Risk classification
# --------------------------------------------------------------------------------------------
def classify_risk(changed: list[str], node_tags: dict[str, list[str]],
                  config: dict[str, object]) -> list[RiskHit]:
    """Which of the five non-negotiable axes the change touches, and what said so.

    Four independent sources, unioned. Each hit names its source so a reader can tell a structural
    certainty from a name hint and argue with the latter.
    """
    declared: dict[str, list[str]] = {}
    raw = config.get("high_risk")
    if isinstance(raw, dict):
        for axis, patterns in raw.items():
            if isinstance(patterns, list):
                declared[axis] = [str(p) for p in patterns]

    hits: list[RiskHit] = []
    seen: set[tuple[str, str]] = set()

    def record(axis: str, path: str, because: str) -> None:
        if (axis, path) not in seen:
            seen.add((axis, path))
            hits.append(RiskHit(axis, path, because))

    for path in changed:
        low = path.lower()
        for axis, markers in STRUCTURAL_RISK.items():
            for marker in markers:
                if marker in low:
                    record(axis, path, f"structural: path contains `{marker}`")
        for axis, hints in NAME_RISK.items():
            for hint in hints:
                if hint in low:
                    record(axis, path, f"name hint: path contains `{hint}`")
        for axis, patterns in declared.items():
            for pattern in patterns:
                if pattern and pattern.lower() in low:
                    record(axis, path, f"declared in qa.config.yml: `{pattern}`")
        for tag in node_tags.get(path, []):
            axis = TAG_RISK.get(tag)
            if axis:
                record(axis, path, f"graph tag `{tag}` on a node in this file")

    return sorted(hits, key=lambda h: (RISK_AXES.index(h.axis) if h.axis in RISK_AXES else 99,
                                       h.path, h.because))


# --------------------------------------------------------------------------------------------
# Graph mode -- the reverse walk
# --------------------------------------------------------------------------------------------
def graph_edges(graph: dict, use_enrichment: bool) -> tuple[list[dict], str | None]:
    """Base edges, plus the optional machine-local enrichment block, and the tool that wrote it.

    The enrichment block is deliberately excluded from the graph's `content_digest` because a
    graphify/code-review-graph install is machine-local. It is included here by default and every
    edge it contributes is LABELLED with the tool, so a reader can see which inclusions would not
    reproduce on a bare runner; `--no-enrichment` reproduces that bare run exactly. The VERDICT is
    unaffected either way -- enrichment adds affected nodes, never risk axes -- and the selftest
    pins that, so a CI run and a laptop run can never disagree about whether to stop.
    """
    edges = [e for e in graph.get("edges", []) if isinstance(e, dict)]
    block = graph.get("enrichment")
    tool = block.get("source") if isinstance(block, dict) else None
    if use_enrichment and isinstance(block, dict):
        for edge in block.get("edges", []) or []:
            if isinstance(edge, dict):
                marked = dict(edge)
                marked["_enriched"] = tool or "unknown tool"
                edges.append(marked)
    return edges, tool


def reverse_walk(edges: list[dict], seeds: dict[str, str], depth: int
                 ) -> tuple[list[Inclusion], list[Exclusion]]:
    """Walk INCOMING edges from the seed nodes: `e.to in frontier` yields `e.from`.

    One uniform edge direction (subject -> object) is what makes this legal as a one-liner: an
    incoming edge is exactly "who depends on this". Returns the inclusions in BFS order and the
    nodes the depth cutoff dropped, because a cutoff nobody printed is silent narrowing.
    """
    incoming: dict[str, list[dict]] = {}
    for edge in edges:
        target = edge.get("to")
        if target:
            incoming.setdefault(target, []).append(edge)

    found: dict[str, Inclusion] = {}
    for node, why in seeds.items():
        found[node] = Inclusion(node, why, 0, "changed")

    frontier = list(seeds)
    deferred: dict[str, str] = {}
    for level in range(1, max(depth, 0) + 1):
        nxt: list[str] = []
        for node in sorted(frontier):
            for edge in sorted(incoming.get(node, []),
                               key=lambda e: (e.get("from", ""), e.get("kind", ""))):
                dependent = edge.get("from")
                if not dependent or dependent in found:
                    continue
                tool = edge.get("_enriched")
                found[dependent] = Inclusion(
                    dependent,
                    f"{dependent} --{edge.get('kind', 'references')}--> {node}"
                    + (f"  [via {tool}]" if tool else ""),
                    level,
                    f"graph:{tool}" if tool else "graph",
                )
                nxt.append(dependent)
        frontier = nxt
        if not frontier:
            break

    # One level past the cutoff, so the report can say what a deeper walk would have added.
    for node in frontier:
        for edge in incoming.get(node, []):
            dependent = edge.get("from")
            if dependent and dependent not in found:
                deferred.setdefault(
                    dependent,
                    f"beyond --depth {depth} (reached via {edge.get('kind', 'references')} "
                    f"from {node})")

    ordered = sorted(found.values(), key=lambda i: (i.depth, i.unit))
    dropped = [Exclusion(node, reason) for node, reason in sorted(deferred.items())]
    return ordered, dropped


# --------------------------------------------------------------------------------------------
# Convention mode -- the fallback that must work with no graph at all
# --------------------------------------------------------------------------------------------
_MODEL = re.compile(r"^app/models/(?!concerns/)(.+)\.rb$")
_CONTROLLER = re.compile(r"^app/controllers/(?!concerns/)(.+)_controller\.rb$")
_VIEW = re.compile(r"^app/views/(?!layouts/)(.+)/([^/]+)\.[\w.]*erb$")
_UNIT = re.compile(r"^app/(jobs|mailers|services|channels|components|helpers|policies|"
                   r"serializers|models/concerns|controllers/concerns)/(.+)\.rb$")
_STIMULUS = re.compile(r"^app/javascript/controllers/(.+)_controller\.js$")
_LIB = re.compile(r"^lib/(.+)\.rb$")
_MIGRATION = re.compile(r"^db/migrate/\d+_(.+)\.rb$")


def convention_units(path: str) -> list[Inclusion]:
    """Rails layout, applied to one changed path. Stack-agnostic within Rails, no graph needed."""
    out: list[Inclusion] = []

    def add(unit: str, why: str) -> None:
        out.append(Inclusion(unit, why, 1, "convention"))

    model = _MODEL.match(path)
    if model:
        name = model.group(1)
        plural = pluralize(name.rsplit("/", 1)[-1])
        prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
        add(f"{prefix}{plural} (controller)",
            f"Rails convention: `{prefix}{plural}` is the conventional controller for model "
            f"`{name}` -- verify it exists; the graph would resolve real callers instead")
        return out

    controller = _CONTROLLER.match(path)
    if controller:
        add(f"{controller.group(1)} (routes)",
            f"Rails convention: routes served by `{controller.group(1)}`")
        return out

    view = _VIEW.match(path)
    if view:
        add(f"{view.group(1)}#{view.group(2)} (action)",
            f"Rails convention: `{path}` is the template for `{view.group(1)}#{view.group(2)}`")
        return out

    migration = _MIGRATION.match(path)
    if migration:
        slug = migration.group(1)
        table = re.search(r"(?:_to|_from|^create)_([a-z0-9_]+)$", slug)
        if table:
            add(f"{table.group(1)} (table)",
                f"Rails convention: migration `{slug}` names table `{table.group(1)}`")
        else:
            add("(schema)", f"migration `{slug}` does not name its table conventionally")
        return out

    unit = _UNIT.match(path)
    if unit:
        add(f"{unit.group(1)}/{unit.group(2)}", f"the changed unit itself (`{path}`)")
        return out

    stimulus = _STIMULUS.match(path)
    if stimulus:
        add(f"{stimulus.group(1)} (Stimulus controller)",
            f"the changed unit itself (`{path}`); its consumers are in markup and are NOT "
            f"derivable by convention -- the graph resolves them")
        return out

    lib = _LIB.match(path)
    if lib:
        add(f"lib/{lib.group(1)}", f"the changed unit itself (`{path}`)")
    return out


def controller_selector(path: str) -> str | None:
    """The `controller#` prefix a changed path implies, for matching against the route table."""
    controller = _CONTROLLER.match(path)
    if controller:
        return controller.group(1)
    view = _VIEW.match(path)
    if view:
        return view.group(1)
    model = _MODEL.match(path)
    if model:
        name = model.group(1)
        plural = pluralize(name.rsplit("/", 1)[-1])
        prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
        return f"{prefix}{plural}"
    return None


SPEC_DIRS = ("models", "jobs", "mailers", "services", "channels", "components", "helpers",
             "policies", "serializers")


def spec_candidates(path: str) -> list[tuple[str, str]]:
    """(candidate spec path, why). Path conventions only -- never a claim that the spec exists."""
    out: list[tuple[str, str]] = []
    if path.startswith(TEST_ROOTS):
        return [(path, "the changed file is itself a test")]

    controller = _CONTROLLER.match(path)
    if controller:
        name = controller.group(1)
        return [(f"spec/requests/{name}_spec.rb", f"request specs for `{name}`"),
                (f"spec/controllers/{name}_controller_spec.rb", f"controller specs for `{name}`"),
                (f"spec/system/{name}_spec.rb", f"system specs for `{name}`"),
                (f"test/controllers/{name}_controller_test.rb", f"Minitest for `{name}`")]

    view = _VIEW.match(path)
    if view:
        return [(f"spec/system/{view.group(1)}_spec.rb",
                 f"system specs exercise the `{view.group(1)}` templates"),
                (f"spec/views/{view.group(1)}/{view.group(2)}.html.erb_spec.rb",
                 f"view spec for `{path}`")]

    # Checked BEFORE the generic unit rule, which would otherwise swallow `models/concerns/...`
    # and lose the "this reaches every includer" half.
    concern = re.match(r"^app/(models|controllers)/concerns/(.+)\.rb$", path)
    if concern:
        return [(f"spec/{concern.group(1)}/concerns/{concern.group(2)}_spec.rb",
                 "the concern's own spec"),
                ("spec/", "a shared concern reaches every includer -- the wide selection applies")]

    unit = re.match(r"^app/(" + "|".join(SPEC_DIRS) + r")/(.+)\.rb$", path)
    if unit:
        kind, name = unit.group(1), unit.group(2)
        return [(f"spec/{kind}/{name}_spec.rb", f"the unit spec for `{path}`"),
                (f"test/{kind}/{name}_test.rb", f"the Minitest for `{path}`")]

    lib = _LIB.match(path)
    if lib:
        return [(f"spec/lib/{lib.group(1)}_spec.rb", f"the unit spec for `{path}`")]

    component = re.match(r"^app/components/(.+)\.html\.erb$", path)
    if component:
        return [(f"spec/components/{component.group(1)}_spec.rb",
                 f"the component spec for `{path}`")]
    return out


# --------------------------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------------------------
def derive(changed: list[str], graph: dict | None, route_table: list[dict],
           config: dict[str, object], root: Path, depth: int,
           use_enrichment: bool) -> Report:
    report = Report(changed=list(changed))

    raw_exclude = config.get("exclude")
    declared_exclusions = [str(x) for x in raw_exclude] if isinstance(raw_exclude, list) else []

    # ---- partition the changed set --------------------------------------------------------
    considered: list[str] = []
    for path in changed:
        if any(pattern and pattern in path for pattern in declared_exclusions):
            report.excluded.append(Exclusion(path, "declared in qa.config.yml `blast_radius.exclude`"))
            report.resolution[path] = "excluded (declared)"
            continue
        if not (path.startswith(APP_ROOTS) or path in APP_FILES):
            report.excluded.append(
                Exclusion(path, "not app code (outside " + ", ".join(APP_ROOTS) + ")"))
            report.resolution[path] = "excluded (not app code)"
            continue
        considered.append(path)

    # ---- graph resolution -------------------------------------------------------------------
    nodes_by_file: dict[str, list[dict]] = {}
    node_tags: dict[str, list[str]] = {}
    seeds: dict[str, str] = {}
    graph_ids: dict[str, dict] = {}
    if graph is not None:
        for node in graph.get("nodes", []):
            if not isinstance(node, dict) or not node.get("id"):
                continue
            graph_ids[node["id"]] = node
            file_path = node.get("file")
            if file_path:
                nodes_by_file.setdefault(file_path, []).append(node)
        for path in considered:
            for node in nodes_by_file.get(path, []):
                seeds[node["id"]] = f"`{path}` changed (graph node `{node['id']}`)"
                node_tags.setdefault(path, []).extend(node.get("tags") or [])

    # ---- risk (independent of which derivation ran) -------------------------------------------
    # Test files are excluded from RISK classification and from nothing else. A change to
    # `spec/models/invoice_spec.rb` does not alter what the app does, so forcing the wide
    # selection on it would fire the gate on every test-only PR -- and a gate that always fires is
    # one a team switches off. The carve-out is narrow by construction: a spec change cannot hide
    # a migration, and an app change alongside a spec change still fires. Both halves are pinned
    # by fixtures, because a carve-out with no negative test is how one silently widens.
    report.risk = classify_risk([p for p in considered if not p.startswith(TEST_ROOTS)],
                                node_tags, config)

    # ---- affected units -----------------------------------------------------------------------
    covered_by_graph: set[str] = set()
    if seeds:
        edges, tool = graph_edges(graph or {}, use_enrichment)
        walked, dropped = reverse_walk(edges, seeds, depth)
        report.affected.extend(walked)
        report.excluded.extend(dropped)
        report.sources.append(
            f"architecture graph ({len(graph.get('nodes', []))} nodes, "
            f"{len(graph.get('edges', []))} edges, digest "
            f"{graph.get('content_digest', 'unknown')})")
        if tool:
            report.sources.append(
                f"graph enrichment from **{tool}** — "
                + ("reverse-dependency edges INCLUDED and labelled `[via " + tool + "]`"
                   if use_enrichment
                   else "present but EXCLUDED by --no-enrichment"))
            if not use_enrichment:
                report.excluded.append(Exclusion(
                    f"enrichment edges from {tool}",
                    "--no-enrichment: reproducing a bare-runner walk (this block is outside the "
                    "graph's content_digest, so it is machine-local by design)"))
        for path in considered:
            if nodes_by_file.get(path):
                covered_by_graph.add(path)
                report.resolution[path] = "graph node(s): " + ", ".join(
                    n["id"] for n in nodes_by_file[path])
        for note in graph.get("notes", []) or []:
            report.graph_notes.append(str(note))

    # Convention fallback covers every considered path the graph did not resolve -- including
    # every path when there is no graph at all. Hybrid on purpose: a graph that has never heard of
    # a file must not make that file invisible.
    for path in considered:
        if path in covered_by_graph:
            continue
        units = convention_units(path)
        for unit in units:
            report.affected.append(unit)
        if units:
            report.resolution[path] = "Rails convention"
        elif path.startswith(TEST_ROOTS):
            report.resolution[path] = "a test file -- selected directly"
        else:
            report.resolution[path] = "UNRESOLVED"
            report.unresolved.append(path)
    if not graph:
        report.sources.append("Rails conventions (no architecture graph supplied)")
    elif not seeds:
        report.sources.append(
            "Rails conventions (a graph was supplied but matched none of the changed files)")

    # ---- routes, from the #119 route table ---------------------------------------------------
    report.routes = select_routes(considered, report.affected, route_table, graph_ids)
    if route_table:
        report.sources.append(f"route table ({len(route_table)} routes, #119)")
    else:
        report.excluded.append(Exclusion(
            "route selection",
            "no route table supplied — run `route_coverage.py enumerate` and pass --routes, or "
            "route names come from the graph alone"))

    # ---- tests -------------------------------------------------------------------------------
    report.tests, framework_drops = select_tests(considered, report.affected, graph_ids, root)
    report.excluded.extend(framework_drops)

    # ---- flows -------------------------------------------------------------------------------
    if graph:
        affected_ids = {i.unit for i in report.affected}
        for flow in graph.get("flows", []) or []:
            if not isinstance(flow, dict):
                continue
            touched = sorted({step.get("node") for step in flow.get("steps", []) or []
                              if isinstance(step, dict) and step.get("node") in affected_ids})
            if touched:
                report.flows.append(Inclusion(
                    str(flow.get("name") or flow.get("id")),
                    f"flow `{flow.get('trigger')}` passes through {', '.join(touched)}",
                    0, "graph"))

    return report


def select_routes(changed: list[str], affected: list[Inclusion], route_table: list[dict],
                  graph_ids: dict[str, dict]) -> list[RouteTarget]:
    """Routes reached by the change, drawn from the #119 route table -- never re-derived here."""
    by_key = {f"{r.get('verb')} {r.get('pattern')}": r for r in route_table}
    out: dict[str, RouteTarget] = {}

    # Graph mode: an affected node of type `route` IS a route id of the form "VERB /pattern".
    for inclusion in affected:
        node = graph_ids.get(inclusion.unit)
        if node and node.get("type") == "route":
            out[inclusion.unit] = RouteTarget(inclusion.unit, inclusion.because,
                                              inclusion.unit in by_key)

    # Both modes: match the route table's `controller` column against the controllers implied by
    # the change. This is what makes the fallback useful with no graph at all.
    selectors = {s for s in (controller_selector(p) for p in changed) if s}
    for key, route in by_key.items():
        controller = str(route.get("controller") or "")
        base = controller.split("#", 1)[0]
        if base and base in selectors and key not in out:
            out[key] = RouteTarget(key, f"route table: `{controller}` is implied by the change",
                                   True)
    return sorted(out.values(), key=lambda r: r.key)


def select_tests(changed: list[str], affected: list[Inclusion], graph_ids: dict[str, dict],
                 root: Path) -> tuple[list[TestTarget], list[Exclusion]]:
    """Spec paths implied by every changed and affected source file, with existence checked.

    A candidate that does not exist is NOT dropped. "No spec found at spec/models/invoice_spec.rb"
    is the most actionable line the report can carry -- it says the affected code has no
    regression net at all -- and dropping it is exactly the silent narrowing this tool forbids.

    The ONE narrowing allowed is by test framework, and it is observed rather than guessed: a
    project with no `test/` directory is not a Minitest project, so listing `test/...` candidates
    would bury the real gaps under a second, always-absent naming scheme. It is reported as one
    exclusion line, never per candidate -- and when neither directory exists, nothing is dropped.
    """
    sources: dict[str, str] = {}
    for path in changed:
        sources[path] = "changed"
    for inclusion in affected:
        node = graph_ids.get(inclusion.unit)
        if node and node.get("file"):
            sources.setdefault(node["file"], f"affected: {inclusion.because}")

    present_frameworks = {d for d in TEST_ROOTS if (root / d.rstrip("/")).is_dir()}
    dropped: list[Exclusion] = []
    if present_frameworks:
        for framework in sorted(set(TEST_ROOTS) - present_frameworks):
            dropped.append(Exclusion(
                f"candidate paths under `{framework}`",
                f"this project has no `{framework}` directory, so its naming scheme cannot "
                f"produce a real spec path"))

    out: dict[str, TestTarget] = {}
    for path, why in sorted(sources.items()):
        for candidate, reason in spec_candidates(path):
            if present_frameworks and candidate.startswith(TEST_ROOTS) \
                    and not candidate.startswith(tuple(present_frameworks)):
                continue
            if candidate in out and out[candidate].present:
                continue
            present = (root / candidate).exists()
            out[candidate] = TestTarget(candidate, f"{reason} ({why})", present)
    return sorted(out.values(), key=lambda t: (not t.present, t.path)), dropped


# --------------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------------
FLOOR = ("A computed radius is a FLOOR, not a ceiling: the graph extractor is regex-based, so "
         "metaprogrammed structure is invisible to it. Use this to justify WIDENING a scope, "
         "never to shrink one below the certification baseline.")


def render(report: Report, depth: int) -> str:
    lines: list[str] = []
    verdict = "WIDE — approval required before executing" if report.wide else "TARGETED"
    lines.append(f"blast radius: {verdict}")
    lines.append(f"  derived from: {'; '.join(report.sources) or 'nothing'}")
    lines.append(f"  reverse-walk depth: {depth}")
    lines.append("")

    lines.append(f"changed -> {len(report.changed)} file(s)")
    for path in report.changed:
        lines.append(f"  {path}  [{report.resolution.get(path, 'UNRESOLVED')}]")
    lines.append("")

    lines.append(f"affected -> {len(report.affected)} unit(s), each with the edge that included it")
    for inclusion in report.affected:
        lines.append(f"  d{inclusion.depth} {inclusion.unit}")
        lines.append(f"       because: {inclusion.because}")
    lines.append("")

    lines.append(f"routes -> {len(report.routes)}")
    for route in report.routes:
        flag = "" if route.in_route_table else "   (not in the route table — tables disagree)"
        lines.append(f"  {route.key}{flag}")
        lines.append(f"       because: {route.because}")
    lines.append("")

    present = [t for t in report.tests if t.present]
    missing = [t for t in report.tests if not t.present]
    lines.append(f"tests -> {len(present)} selected, {len(missing)} conventional path(s) absent")
    for target in present:
        lines.append(f"  {target.path}")
        lines.append(f"       because: {target.because}")
    for target in missing:
        lines.append(f"  NO SPEC FOUND: {target.path}")
        lines.append(f"       expected: {target.because}")
    lines.append("")

    if report.flows:
        lines.append(f"user-visible flows through the radius -> {len(report.flows)}")
        for flow in report.flows:
            lines.append(f"  {flow.unit}")
            lines.append(f"       because: {flow.because}")
        lines.append("")

    lines.append(f"risk axes fired -> {len(report.risk)}"
                 + ("  (these force the wide selection; not configurable off)" if report.risk
                    else ""))
    for hit in report.risk:
        lines.append(f"  [{hit.axis}] {hit.path}")
        lines.append(f"       because: {hit.because}")
    lines.append("")

    lines.append(f"unresolved changed files -> {len(report.unresolved)}")
    for path in report.unresolved:
        lines.append(f"  {path}   (app code no rule explains — the radius is under-determined, "
                     f"so the wide selection applies)")
    lines.append("")

    # Printed even when empty, always. A suppression that leaves no trace is how a coverage
    # number quietly becomes a lie -- the same rule route_coverage.py holds itself to.
    lines.append(f"excluded from the radius -> {len(report.excluded)}")
    for exclusion in report.excluded:
        lines.append(f"  {exclusion.what}")
        lines.append(f"       reason: {exclusion.reason}")
    lines.append("")

    if report.graph_notes:
        lines.append(f"the graph's own stated blind spots -> {len(report.graph_notes)}")
        for note in report.graph_notes:
            lines.append(f"  {note}")
        lines.append("")

    lines.append(FLOOR)
    return "\n".join(lines)


def as_json(report: Report, depth: int) -> str:
    return json.dumps({
        "verdict": "wide" if report.wide else "targeted",
        "depth": depth,
        "sources": report.sources,
        "changed": [{"path": p, "resolution": report.resolution.get(p, "UNRESOLVED")}
                    for p in report.changed],
        "affected": [{"unit": i.unit, "because": i.because, "depth": i.depth, "via": i.via}
                     for i in report.affected],
        "routes": [{"route": r.key, "because": r.because, "in_route_table": r.in_route_table}
                   for r in report.routes],
        "tests": [{"path": t.path, "because": t.because, "present": t.present}
                  for t in report.tests],
        "flows": [{"flow": f.unit, "because": f.because} for f in report.flows],
        "risk": [{"axis": h.axis, "path": h.path, "because": h.because} for h in report.risk],
        "unresolved": report.unresolved,
        "excluded": [{"what": e.what, "reason": e.reason} for e in report.excluded],
        "graph_notes": report.graph_notes,
        "floor_not_ceiling": FLOOR,
    }, indent=2)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def cmd_derive(args: argparse.Namespace) -> int:
    changed = read_changed(args.changed, args.changed_from)

    graph: dict | None = None
    graph_path = Path(args.graph)
    if graph_path.is_file():
        graph = load_json(graph_path, "architecture graph")
    elif args.require_graph:
        raise Unusable(f"--require-graph was passed and {graph_path} does not exist")

    route_table: list[dict] = []
    routes_path = Path(args.routes)
    if routes_path.is_file():
        payload = load_json(routes_path, "route table")
        raw = payload.get("routes")
        if not isinstance(raw, list):
            raise Unusable(f"route table at {routes_path} has no `routes` array")
        route_table = [r for r in raw if isinstance(r, dict)]

    report = derive(changed, graph, route_table, load_config(Path(args.config)),
                    Path(args.root), args.depth, not args.no_enrichment)

    print(as_json(report, args.depth) if args.json else render(report, args.depth))
    return 1 if report.wide else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive a regression blast radius from a change (#134).")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the rules fire and stay silent")
    sub = parser.add_subparsers(dest="command")

    d = sub.add_parser("derive", help="changed -> affected -> routes -> tests, with justification")
    d.add_argument("--changed", action="append", default=[], help="a changed path (repeatable)")
    d.add_argument("--changed-from", help="file of changed paths, one per line; `-` for stdin")
    d.add_argument("--graph", default="docs/architecture/graph.json",
                   help="architecture graph; absent means the convention fallback")
    d.add_argument("--require-graph", action="store_true",
                   help="exit 2 rather than falling back, for a project that has opted in")
    d.add_argument("--routes", default="qa/reports/routes.json", help="the #119 route table")
    d.add_argument("--config", default="qa/qa.config.yml")
    d.add_argument("--root", default=".", help="repo root, for checking whether a spec exists")
    d.add_argument("--depth", type=int, default=2, help="reverse-walk depth (default 2)")
    d.add_argument("--no-enrichment", action="store_true",
                   help="ignore machine-local enrichment edges, reproducing a bare-runner walk")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_derive)

    args = parser.parse_args(argv)
    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import blast_radius_selftest as st

        return st.run()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
