#!/usr/bin/env python3
"""Prove the blast-radius derivation is right -- in BOTH directions.

Run:  python3 blast_radius.py --selftest   (or execute this file directly)

A derived scope is trusted more than a guessed one, which makes UNDER-inclusion the dangerous
failure: a report that omits the dependent nobody thought of is worse than the judgement it
replaced, because it retires the question with a machine's authority. So the fires-half attacks
under-inclusion (the reverse walk, the risk axes, the depth report, the missing-spec line).

The silence-half matters more, and gets equal weight. Three rules here are only useful if they
stay quiet: a dependency must not be reported as a dependent; a plain authenticated controller
must not fire the auth axis (Rails 8's auth is opt-out, so it is the default state of every
controller); and a spec-only change must not force the wide selection. A classifier that always
fires is one a team switches off, and then it catches nothing at all.

Stdlib only; no graph tool, no network, no app.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blast_radius as br  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def ok(label: str, condition: bool, detail: str = "") -> None:
    _tick()
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def check(label: str, got, want) -> None:
    _tick()
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


# ---------------------------------------------------------------------------------------------
# Fixture project
# ---------------------------------------------------------------------------------------------
GRAPH = {
    "schema": "rails-flow/architecture-graph@1",
    "content_digest": "sha256:fixture",
    "notes": ["metaprogrammed: 1 model defined dynamically was not indexed."],
    "nodes": [
        {"id": "Invoice", "type": "model", "file": "app/models/invoice.rb",
         "layer": "domain", "tags": []},
        {"id": "Widget", "type": "model", "file": "app/models/widget.rb",
         "layer": "domain", "tags": []},
        {"id": "Membership", "type": "model", "file": "app/models/membership.rb",
         "layer": "domain", "tags": ["tenant-scoped"]},
        {"id": "InvoicesController", "type": "controller",
         "file": "app/controllers/invoices_controller.rb", "layer": "web",
         "tags": ["authenticated"]},
        {"id": "WidgetsController", "type": "controller",
         "file": "app/controllers/widgets_controller.rb", "layer": "web",
         "tags": ["authenticated"]},
        {"id": "ReportsController", "type": "controller",
         "file": "app/controllers/reports_controller.rb", "layer": "web",
         "tags": ["authenticated"]},
        {"id": "GET /invoices", "type": "route",
         "file": "app/controllers/invoices_controller.rb", "layer": "web", "tags": ["get"]},
        {"id": "DELETE /invoices", "type": "route",
         "file": "app/controllers/invoices_controller.rb", "layer": "web", "tags": ["delete"]},
        {"id": "GET /widgets", "type": "route",
         "file": "app/controllers/widgets_controller.rb", "layer": "web", "tags": ["get"]},
        {"id": "invoices", "type": "table", "file": None, "layer": "domain", "tags": []},
    ],
    "edges": [
        {"from": "InvoicesController", "to": "Invoice", "kind": "references"},
        {"from": "Invoice", "to": "invoices", "kind": "persists"},
        {"from": "GET /invoices", "to": "InvoicesController", "kind": "references"},
        {"from": "DELETE /invoices", "to": "InvoicesController", "kind": "references"},
        {"from": "WidgetsController", "to": "Widget", "kind": "references"},
        {"from": "GET /widgets", "to": "WidgetsController", "kind": "references"},
    ],
    "flows": [
        {"id": "GET /invoices -> InvoicesController#index", "name": "List invoices",
         "trigger": "GET /invoices", "entry": "InvoicesController", "action": "index",
         "steps": [{"node": "InvoicesController", "does": "index"},
                   {"node": "Invoice", "does": "load"}]},
        {"id": "GET /widgets -> WidgetsController#index", "name": "List widgets",
         "trigger": "GET /widgets", "entry": "WidgetsController", "action": "index",
         "steps": [{"node": "WidgetsController", "does": "index"},
                   {"node": "Widget", "does": "load"}]},
    ],
    "enrichment": {
        "source": "graphify",
        "note": "excluded from content_digest",
        "edges": [{"from": "ReportsController", "to": "Invoice", "kind": "references"}],
        "unmatched_endpoints": 0,
    },
}

ROUTES = {"routes": [
    {"verb": "GET", "pattern": "/invoices", "controller": "invoices#index", "area": "invoices"},
    {"verb": "POST", "pattern": "/invoices", "controller": "invoices#create", "area": "invoices"},
    {"verb": "GET", "pattern": "/widgets", "controller": "widgets#index", "area": "widgets"},
]}

# Only ONE conventional spec exists, so the "no spec found" line has something to prove.
EXISTING_SPECS = ("spec/models/invoice_spec.rb", "spec/models/widget_spec.rb")


def project(config: str = "", minitest: bool = False) -> Path:
    root = Path(tempfile.mkdtemp(prefix="qaflow-blast-"))
    (root / "docs" / "architecture").mkdir(parents=True)
    (root / "docs" / "architecture" / "graph.json").write_text(
        json.dumps(GRAPH), encoding="utf-8")
    (root / "qa" / "reports").mkdir(parents=True)
    (root / "qa" / "reports" / "routes.json").write_text(json.dumps(ROUTES), encoding="utf-8")
    (root / "spec" / "models").mkdir(parents=True)
    for spec in EXISTING_SPECS:
        (root / spec).write_text("# fixture\n", encoding="utf-8")
    if minitest:
        (root / "test" / "models").mkdir(parents=True)
    if config:
        (root / "qa" / "qa.config.yml").write_text(config, encoding="utf-8")
    return root


def run_derive(root: Path, changed: list[str], *, graph: bool = True, routes: bool = True,
               depth: int = 2, extra: list[str] | None = None) -> tuple[int, dict, str]:
    """Drive the real CLI, so exit codes are exercised rather than assumed."""
    argv = ["derive", "--root", str(root), "--depth", str(depth),
            "--graph", str(root / "docs" / "architecture" / "graph.json") if graph else "/nope",
            "--routes", str(root / "qa" / "reports" / "routes.json") if routes else "/nope",
            "--config", str(root / "qa" / "qa.config.yml")]
    for path in changed:
        argv += ["--changed", path]
    argv += extra or []

    with contextlib.redirect_stdout(io.StringIO()) as text_out:
        text_code = br.main(argv)
    with contextlib.redirect_stdout(io.StringIO()) as json_out:
        json_code = br.main(argv + ["--json"])
    if text_code != json_code:
        FAILURES.append(f"--json changed the exit code: {text_code} vs {json_code}")
    return text_code, json.loads(json_out.getvalue()), text_out.getvalue()


def units(payload: dict) -> set[str]:
    return {a["unit"] for a in payload["affected"]}


def run() -> int:  # noqa: C901 -- a fixture list, deliberately flat and readable
    root = project()

    # ---- the reverse walk FIRES ---------------------------------------------------------------
    code, out, _ = run_derive(root, ["app/models/invoice.rb"])
    ok("a dependent is included by an incoming references edge",
       "InvoicesController" in units(out), f"{sorted(units(out))}")
    ok("the justifying edge is printed, not just the unit",
       any(a["unit"] == "InvoicesController"
           and "InvoicesController --references--> Invoice" in a["because"]
           for a in out["affected"]),
       f"{[a['because'] for a in out['affected']]}")
    ok("the walk is transitive to --depth",
       "GET /invoices" in units(out), f"{sorted(units(out))}")

    # ---- the reverse walk STAYS SILENT --------------------------------------------------------
    # The direction is the whole correctness claim. A controller's own dependencies are NOT
    # affected by changing the controller; only its dependents are.
    code, out, _ = run_derive(root, ["app/controllers/invoices_controller.rb"])
    ok("a dependency is not a dependent",
       "Invoice" not in units(out), f"Invoice must not be pulled in: {sorted(units(out))}")
    ok("an unrelated subgraph is untouched",
       "WidgetsController" not in units(out) and "Widget" not in units(out),
       f"{sorted(units(out))}")

    # ---- depth ---------------------------------------------------------------------------------
    code, shallow, text = run_derive(root, ["app/models/invoice.rb"], depth=1)
    ok("the depth cutoff excludes",
       "GET /invoices" not in units(shallow), f"{sorted(units(shallow))}")
    ok("the depth cutoff is reported, not silent",
       any("GET /invoices" == e["what"] and "beyond --depth 1" in e["reason"]
           for e in shallow["excluded"]),
       f"{shallow['excluded']}")

    # ---- flows ----------------------------------------------------------------------------------
    code, out, _ = run_derive(root, ["app/models/invoice.rb"])
    ok("a user-visible flow through the radius is named",
       any(f["flow"] == "List invoices" for f in out["flows"]), f"{out['flows']}")
    ok("a flow outside the radius is not claimed",
       not any(f["flow"] == "List widgets" for f in out["flows"]), f"{out['flows']}")

    # ---- routes come from the #119 route table -------------------------------------------------
    ok("a graph route present in the route table is marked as such",
       any(r["route"] == "GET /invoices" and r["in_route_table"] for r in out["routes"]),
       f"{out['routes']}")
    ok("a graph route absent from the route table is flagged",
       any(r["route"] == "DELETE /invoices" and not r["in_route_table"] for r in out["routes"]),
       f"{out['routes']}")
    ok("the route table contributes routes the graph did not name",
       any(r["route"] == "POST /invoices" for r in out["routes"]), f"{out['routes']}")

    # ---- tests -----------------------------------------------------------------------------------
    ok("an existing conventional spec is selected",
       any(t["path"] == "spec/models/invoice_spec.rb" and t["present"] for t in out["tests"]),
       f"{[t['path'] for t in out['tests'] if t['present']]}")
    ok("a missing spec is reported, not dropped",
       any(t["path"] == "spec/requests/invoices_spec.rb" and not t["present"]
           for t in out["tests"]),
       f"{[t['path'] for t in out['tests']]}")

    # ---- graph honesty ----------------------------------------------------------------------------
    ok("the graph's own blind spots are surfaced verbatim",
       any("metaprogrammed" in n for n in out["graph_notes"]), f"{out['graph_notes']}")
    ok("the report states the floor-not-ceiling rule", "FLOOR, not a ceiling" in text, text[:200])

    # ---- enrichment --------------------------------------------------------------------------------
    code, enriched, _ = run_derive(root, ["app/models/invoice.rb"])
    ok("an enrichment edge widens the radius",
       "ReportsController" in units(enriched), f"{sorted(units(enriched))}")
    ok("an enriched edge names the tool that produced it",
       any(a["unit"] == "ReportsController" and "graphify" in a["because"]
           for a in enriched["affected"]),
       f"{[a['because'] for a in enriched['affected']]}")
    ok("the tool is named in the report's sources",
       any("graphify" in s for s in enriched["sources"]), f"{enriched['sources']}")

    bare_code, bare, _ = run_derive(root, ["app/models/invoice.rb"], extra=["--no-enrichment"])
    ok("--no-enrichment reproduces a bare-runner walk",
       "ReportsController" not in units(bare), f"{sorted(units(bare))}")
    ok("--no-enrichment prints what it dropped and why",
       any("graphify" in e["what"] and "machine-local" in e["reason"] for e in bare["excluded"]),
       f"{bare['excluded']}")
    # The verdict must be reproducible without the machine-local tool, or CI and a laptop disagree
    # about whether to stop -- which is the one thing enrichment must never be able to do.
    check("the verdict is identical with and without enrichment",
          (code, enriched["verdict"]), (bare_code, bare["verdict"]))

    # ---- the convention fallback, with no graph at all -----------------------------------------------
    code, clean, _ = run_derive(root, ["app/models/widget.rb"], graph=False)
    ok("the fallback works with no graph tool installed", code == 0, f"exit {code}")
    ok("the fallback names Rails conventions as its source",
       any("Rails conventions" in s for s in clean["sources"]), f"{clean['sources']}")

    # `invoice` also exercises the risk classifier with no graph present: the money name hint is
    # path-based, so it fires identically in both modes. Hence exit 1 here, on purpose.
    code, fallback, _ = run_derive(root, ["app/models/invoice.rb"], graph=False)
    check("the fallback classifies risk too, with no graph at all",
          (code, sorted({h["axis"] for h in fallback["risk"]})), (1, ["money"]))
    ok("the fallback reaches the conventional controller",
       any("invoices (controller)" in a["unit"] for a in fallback["affected"]),
       f"{sorted(units(fallback))}")
    ok("the fallback selects routes from the route table, not from a re-derivation",
       {r["route"] for r in fallback["routes"]} == {"GET /invoices", "POST /invoices"},
       f"{[r['route'] for r in fallback['routes']]}")
    ok("the fallback still finds the unit spec",
       any(t["path"] == "spec/models/invoice_spec.rb" and t["present"]
           for t in fallback["tests"]),
       f"{[t['path'] for t in fallback['tests']]}")

    # A graph that has never heard of a file must not make that file invisible.
    code, hybrid, _ = run_derive(root, ["app/models/invoice.rb", "app/jobs/dunning_job.rb"])
    check("a file the graph does not know still gets convention coverage",
          hybrid["changed"][1]["resolution"], "Rails convention")
    ok("and the file the graph DOES know is resolved by the graph",
       hybrid["changed"][0]["resolution"].startswith("graph node"),
       f"{hybrid['changed'][0]}")

    # ---- risk axes FIRE ---------------------------------------------------------------------------
    for path, axis in (("db/migrate/20240101_create_invoices.rb", "migration"),
                       ("app/models/concerns/archivable.rb", "shared-concern"),
                       ("app/views/layouts/application.html.erb", "shared-concern"),
                       ("app/models/payment.rb", "money"),
                       ("app/controllers/sessions_controller.rb", "auth"),
                       ("app/models/tenant.rb", "tenancy")):
        code, out, _ = run_derive(root, [path])
        ok(f"a change to {path} fires the {axis} axis",
           axis in {h["axis"] for h in out["risk"]}, f"{out['risk']}")
        ok(f"the {axis} axis forces the wide selection",
           out["verdict"] == "wide" and code == 1, f"verdict={out['verdict']} exit={code}")

    # A tag derived from SOURCE beats a filename guess, and `Membership` hits no name hint.
    code, out, _ = run_derive(root, ["app/models/membership.rb"])
    ok("a tenant-scoped graph tag fires the tenancy axis",
       any(h["axis"] == "tenancy" and "tenant-scoped" in h["because"] for h in out["risk"]),
       f"{out['risk']}")

    # ---- risk axes STAY SILENT -----------------------------------------------------------------------
    code, out, _ = run_derive(root, ["app/models/widget.rb"])
    check("a plain model change fires no axis", out["risk"], [])
    check("and is therefore targeted, not wide", (out["verdict"], code), ("targeted", 0))

    # Rails 8's generated auth is opt-out, so `authenticated` is the DEFAULT state of every
    # controller. Treating it as an auth signal would make every controller change wide.
    code, out, _ = run_derive(root, ["app/controllers/widgets_controller.rb"])
    ok("an authenticated controller is not on its own an auth hit",
       out["risk"] == [] and out["verdict"] == "targeted", f"{out['risk']}")

    code, out, _ = run_derive(root, ["spec/models/invoice_spec.rb"])
    ok("a spec-only change is never wide", out["verdict"] == "targeted" and code == 0,
       f"verdict={out['verdict']} risk={out['risk']}")
    # ...and the carve-out is narrow: real app code alongside a spec still fires.
    code, out, _ = run_derive(root, ["spec/models/invoice_spec.rb", "app/models/payment.rb"])
    ok("an app change alongside a spec change still fires",
       out["verdict"] == "wide", f"{out['risk']}")

    # ---- config is ADDITIVE, never a switch ------------------------------------------------------------
    declared = project("blast_radius:\n"
                       "  exclude:\n"
                       "    - vendor/\n"
                       "  high_risk:\n"
                       "    money:\n"
                       "      - app/models/widget.rb\n")
    code, out, _ = run_derive(declared, ["app/models/widget.rb"])
    ok("a declared high-risk path fires its axis",
       any(h["axis"] == "money" and "qa.config.yml" in h["because"] for h in out["risk"]),
       f"{out['risk']}")

    disabler = project("blast_radius:\n"
                       "  high_risk:\n"
                       "    migration: []\n"
                       "    shared-concern: []\n")
    code, out, _ = run_derive(disabler, ["db/migrate/20240101_create_invoices.rb"])
    ok("config cannot switch a non-negotiable axis off",
       out["verdict"] == "wide" and "migration" in {h["axis"] for h in out["risk"]},
       f"{out['risk']}")

    code, out, _ = run_derive(declared, ["app/models/widget.rb", "vendor/gem/lib/thing.rb"])
    ok("a declared exclusion is printed with its reason",
       any("vendor/gem/lib/thing.rb" == e["what"] and "blast_radius.exclude" in e["reason"]
           for e in out["excluded"]),
       f"{out['excluded']}")

    # ---- accounting for every changed file ----------------------------------------------------------
    code, out, _ = run_derive(root, ["docs/adr/0001-thing.md"])
    ok("a docs-only change is excluded with a reason, not unresolved",
       out["unresolved"] == [] and any("not app code" in e["reason"] for e in out["excluded"]),
       f"unresolved={out['unresolved']} excluded={out['excluded']}")
    check("and a docs-only change is targeted", (out["verdict"], code), ("targeted", 0))

    code, out, _ = run_derive(root, ["config/initializers/rack_attack.rb"])
    ok("an unaccounted-for app file forces wide",
       out["unresolved"] == ["config/initializers/rack_attack.rb"]
       and out["verdict"] == "wide" and code == 1,
       f"unresolved={out['unresolved']} verdict={out['verdict']} exit={code}")
    ok("...and says so, rather than reporting an empty radius",
       out["risk"] == [], "this file must be wide on the UNRESOLVED ground alone")

    # ---- test-framework narrowing is observed, not guessed, and it is printed ------------------------
    code, out, _ = run_derive(root, ["app/models/widget.rb"])
    ok("Minitest candidates are dropped in a project with no test/ directory",
       not any(t["path"].startswith("test/") for t in out["tests"]),
       f"{[t['path'] for t in out['tests']]}")
    ok("and the drop is printed once, with its reason",
       any("`test/`" in e["what"] and "no `test/` directory" in e["reason"]
           for e in out["excluded"]),
       f"{out['excluded']}")

    both = project(minitest=True)
    code, out, _ = run_derive(both, ["app/models/widget.rb"])
    ok("nothing is dropped when the project has both frameworks",
       any(t["path"] == "test/models/widget_test.rb" for t in out["tests"])
       and not any("candidate paths under" in e["what"] for e in out["excluded"]),
       f"tests={[t['path'] for t in out['tests']]} excluded={out['excluded']}")

    # ---- the excluded section prints even when it is empty --------------------------------------------
    code, out, text = run_derive(both, ["app/models/widget.rb"], depth=5)
    check("the depth-5 walk leaves nothing deferred", out["excluded"], [])
    ok("the excluded section prints even when empty",
       "excluded from the radius -> 0" in text, text)

    # ---- exit codes: 0 clean, 1 findings, 2 unusable ---------------------------------------------------
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        check("no changed files is UNUSABLE (2), not clean (0)",
              br.main(["derive", "--root", str(root)]), 2)

        empty = root / "qa" / "reports" / "empty.txt"
        empty.write_text("\n# only a comment\n", encoding="utf-8")
        check("an empty changed-file list is UNUSABLE (2)",
              br.main(["derive", "--root", str(root), "--changed-from", str(empty)]), 2)

        broken = root / "docs" / "architecture" / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        check("a malformed graph is UNUSABLE (2), not a finding (1)",
              br.main(["derive", "--root", str(root), "--changed", "app/models/widget.rb",
                       "--graph", str(broken)]), 2)

        check("--require-graph with no graph is UNUSABLE (2), never a silent fallback",
              br.main(["derive", "--root", str(root), "--changed", "app/models/widget.rb",
                       "--graph", "/nope/graph.json", "--require-graph"]), 2)

        listed = root / "qa" / "reports" / "changed.txt"
        listed.write_text("app/models/widget.rb\napp/models/widget.rb\n", encoding="utf-8")
        code = br.main(["derive", "--root", str(root), "--changed-from", str(listed),
                        "--graph", str(root / "docs/architecture/graph.json"),
                        "--routes", str(root / "qa/reports/routes.json")])
    check("a readable changed-file list is clean (0)", code, 0)

    # A duplicated path must not double every inclusion downstream.
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        br.main(["derive", "--root", str(root), "--changed-from", str(listed), "--json",
                 "--graph", str(root / "docs/architecture/graph.json"),
                 "--routes", str(root / "qa/reports/routes.json")])
    check("a repeated changed path is counted once",
          [c["path"] for c in json.loads(captured.getvalue())["changed"]],
          ["app/models/widget.rb"])

    # `-` reads stdin, which is the form the docstring advertises for a piped `git diff`.
    stdin = sys.stdin
    sys.stdin = io.StringIO("app/models/widget.rb\n")
    try:
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = br.main(["derive", "--root", str(root), "--changed-from", "-", "--json",
                            "--graph", str(root / "docs/architecture/graph.json"),
                            "--routes", str(root / "qa/reports/routes.json")])
    finally:
        sys.stdin = stdin
    check("--changed-from - reads stdin",
          (code, [c["path"] for c in json.loads(captured.getvalue())["changed"]]),
          (0, ["app/models/widget.rb"]))

    # ---- inflection ------------------------------------------------------------------------------------
    check("pluralize: regular", br.pluralize("invoice"), "invoices")
    check("pluralize: consonant + y", br.pluralize("company"), "companies")
    check("pluralize: sibilant", br.pluralize("address"), "addresses")
    check("pluralize: irregular", br.pluralize("person"), "people")
    check("pluralize: uncountable", br.pluralize("news"), "news")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"blast_radius selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
