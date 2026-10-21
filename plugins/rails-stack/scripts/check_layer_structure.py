#!/usr/bin/env python3
"""Where a file lives: report the per-layer table, fail on a path that contradicts its route (#1072).

Run:  python3 check_layer_structure.py              # app/
      python3 check_layer_structure.py --root path
      python3 check_layer_structure.py --selftest

WHY THIS EXISTS. `rails-flow` gates what is IN a file — style, authorization, query safety, form
anatomy, token drift. Nothing said where a file should LIVE, so nothing drifted: **a flat
`app/controllers` root is not a violation, it is an absence.** That is why the doctrine
(`directory-structure.md`) matters at least as much as this check.

WHAT IT REPORTS, AND WHY THAT IS ADVISORY. Run it: the per-layer table IS the output. There are
deliberately NO example counts in this docstring (#1124). A hand-copied figure duplicating a number
this script already computes is wrong by construction and only the interval varies — the first
version carried five rows, three of them were wrong within a day, and a sixth layer was missing
because a frozen list cannot notice what it omitted. The argument is what teaches; the digits date it.

**Read across the rows, not down: the finding is that no two layers agree with each other.** Models
drift toward the domain because a model's path binds only to its class name — it is free. Controllers
stay flat because a controller's path binds to its URL and grouping LOOKS like it rewrites every
route — it does under `namespace`, and does NOT under `scope module:`. Views have one directory per
CONTROLLER, not per domain; Rails forces that and it is not organisation.

Projects legitimately differ, so the table is **reported, never failed**. It is also the whole
finding: nothing in the toolchain made the disagreement BETWEEN layers visible, and once it is, it
is hard to unsee.

WHAT IT FAILS ON, and only this. A controller whose file path contradicts the module it is actually
routed as — `app/controllers/billing/invoices_controller.rb` reached through a route declaring
`scope module: :accounts`. That is derivable from `config/routes.rb` and the file tree with no
configuration, and it is real drift rather than a matter of taste.

THE THIRD GATE IN THE ISSUE IS NOT HERE, deliberately: "a namespace present in one layer and absent
in another" needs the project to have DECLARED its taxonomy first. Failing a project for a structure
nobody told it to adopt is a gate red on code that was never given a rule, which is how a gate gets
switched off. It belongs after a project records its choice.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# `app/javascript` HOLDS layers rather than being one: Rails' own generator puts Stimulus at
# `app/javascript/controllers`, so counting `javascript` as a layer would report `controllers/` as
# one of its namespaces, which inverts the reading. Every OTHER directory under `app/` is discovered,
# never enumerated -- a hard-coded list is what hid Stimulus from the first version (#1124).
CONTAINERS = ("javascript",)
CODE_SUFFIXES = (".rb", ".erb", ".js")

# THREE ways a controller module is declared, not two. `scope module:` and `namespace` are the
# block forms; `to: "sessions/omniauth#create"` names the module inline on a single route and is the
# one the first version missed -- which made every correctly-organised controller routed that way
# read as drift, in the FAILING half of the check. A false positive in a gate that fails is how the
# gate gets switched off, so this is parsed, not documented.
SCOPE_MODULE = re.compile(r"scope\s+module:\s*[:'\"]([a-z_]+)['\"]?")
NAMESPACE = re.compile(r"namespace\s+[:'\"]([a-z_]+)['\"]?")
EXPLICIT_TO = re.compile(r"""to:\s*["']([a-z0-9_/]+)#""")


def discover_layers(root: Path) -> list[tuple[str, Path]]:
    """Every layer under `app/`, found by walking the tree -- NEVER a fixed list.

    Returns (name, directory) sorted by name. A directory in CONTAINERS contributes its children
    instead of itself, so `app/javascript/controllers` is a layer and `app/javascript` is not.
    """
    app = root / "app"
    if not app.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for entry in sorted(app.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in CONTAINERS:
            out.extend((f"{entry.name}/{c.name}", c) for c in sorted(entry.iterdir()) if c.is_dir())
        else:
            out.append((entry.name, entry))
    return out


def layer_table(root: Path) -> dict[str, tuple[int, int, int]]:
    """{layer: (flat at root, namespaced dirs, total files)}."""
    table: dict[str, tuple[int, int, int]] = {}
    for name, base in discover_layers(root):
        files = [p for p in base.rglob("*") if p.is_file() and p.suffix in CODE_SUFFIXES]
        if not files:
            continue
        flat = sum(1 for p in files if p.parent == base)
        dirs = len({p.parent for p in files if p.parent != base})
        table[name] = (flat, dirs, len(files))
    return table


def routed_modules(root: Path) -> set[str]:
    """Modules `config/routes.rb` declares, via `scope module:`, `namespace`, or an explicit `to:`."""
    routes = root / "config" / "routes.rb"
    if not routes.is_file():
        return set()
    body = routes.read_text(encoding="utf-8", errors="replace")
    declared = set(SCOPE_MODULE.findall(body)) | set(NAMESPACE.findall(body))
    for target in EXPLICIT_TO.findall(body):
        segments = target.split("/")[:-1]          # the last segment is the CONTROLLER, not a module
        for i in range(1, len(segments) + 1):      # every prefix, so a nested module declares its parent
            declared.add("/".join(segments[:i]))
    return declared


def contradictions(root: Path) -> list[str]:
    """Controllers in a directory no route declares as a module."""
    base = root / "app" / "controllers"
    if not base.is_dir():
        return []
    declared = routed_modules(root)
    if not declared:
        return []                    # no grouping declared anywhere; nothing to contradict
    out = []
    for path in sorted(base.rglob("*_controller.rb")):
        rel = path.relative_to(base)
        if len(rel.parts) < 2:
            continue                 # flat: an absence, not a contradiction
        directory = rel.parts[0]
        if directory in declared:
            continue
        out.append(
            f"app/controllers/{rel}: sits under `{directory}/`, and no route declares that module — "
            f"routes name {sorted(declared)}. A controller's directory IS its module, so either the "
            f"route needs `scope module: :{directory}` or the file is in the wrong place. This is "
            f"drift, not taste: the path and the routing table disagree about the same class.")
    return out


def run(root: Path) -> tuple[list[str], dict[str, tuple[int, int, int]]]:
    return contradictions(root), layer_table(root)


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
    root = Path(tempfile.mkdtemp(prefix="layer-structure-"))
    try:
        (root / "config").mkdir(parents=True)
        (root / "app/controllers/billing").mkdir(parents=True)
        (root / "app/models/billing").mkdir(parents=True)
        (root / "config/routes.rb").write_text(
            "Rails.application.routes.draw do\n"
            "  scope module: :billing do\n    resources :invoices\n  end\nend\n", encoding="utf-8")
        (root / "app/controllers/billing/invoices_controller.rb").write_text("x\n", encoding="utf-8")
        (root / "app/controllers/home_controller.rb").write_text("x\n", encoding="utf-8")
        (root / "app/models/billing/invoice.rb").write_text("x\n", encoding="utf-8")
        (root / "app/models/user.rb").write_text("x\n", encoding="utf-8")

        expect("`scope module:` is read from routes", "billing" in routed_modules(root))
        f, table = run(root)
        # MUST PASS: the directory matches a declared module.
        expect("a controller whose directory IS a routed module is silent", not f)
        # MUST PASS: a FLAT controller is an absence, never a contradiction — failing it would fail
        # every project that was never told what shape to aim for.
        expect("a flat controller is not a finding", not any("home_controller" in x for x in f))

        # MUST FAIL: the path says one module, the routing table says another.
        (root / "app/controllers/accounts").mkdir()
        (root / "app/controllers/accounts/ledgers_controller.rb").write_text("x\n", encoding="utf-8")
        f, _ = run(root)
        expect("a controller under an undeclared module is reported",
               len(f) == 1 and "accounts/ledgers_controller" in f[0])
        # `f and` so an EMPTY list fails this assertion rather than raising IndexError -- a
        # traceback is caught by the harness as "something went wrong", which hides WHICH fixture
        # was meant to notice, and the mutation check says so by name.
        expect("...and the finding names what the routes DO declare",
               bool(f) and "billing" in f[0])

        # `namespace` counts as a declaration too -- it sets the module and changes the URL.
        (root / "config/routes.rb").write_text(
            "Rails.application.routes.draw do\n  namespace :accounts do\n    resources :ledgers\n"
            "  end\n  scope module: :billing do\n    resources :invoices\n  end\nend\n",
            encoding="utf-8")
        f, _ = run(root)
        expect("`namespace` also declares a module, so the same file is now silent", not f)

        expect("the table counts flat and namespaced per layer",
               table["controllers"][0] == 1 and table["models"][0] == 1
               and table["models"][1] == 1)

        # THE OMISSION TEST (#1124). The first version enumerated eight layer names, so Stimulus --
        # `app/javascript/controllers`, the largest FLAT layer in the app that motivated this check --
        # was never counted, and no assertion could notice because the fixture only built layers the
        # author had already listed. These two build layers that appear in NO list in this file.
        (root / "app/queries").mkdir()
        (root / "app/queries/overdue_invoices.rb").write_text("x\n", encoding="utf-8")
        (root / "app/javascript/controllers").mkdir(parents=True)
        (root / "app/javascript/application.js").write_text("x\n", encoding="utf-8")
        (root / "app/javascript/controllers/dropdown_controller.js").write_text("x\n",
                                                                               encoding="utf-8")
        _, table = run(root)
        expect("a layer nobody enumerated is discovered, not skipped", "queries" in table)
        # A control on the SAME input: discovery that merely globbed `app/*` would put Stimulus under
        # a `javascript` layer and report `controllers/` as one of its namespace dirs -- inverted.
        expect("Stimulus is its own layer", table.get("javascript/controllers") == (1, 0, 1))
        expect("...and `javascript` is NOT a layer, so its child is not read as a namespace",
               "javascript" not in table)

        # EXPLICIT `to:` DECLARES A MODULE. Real routes do this and the first version did not read
        # it, so a correctly-organised controller was reported as drift.
        (root / "app/controllers/sessions").mkdir()
        (root / "app/controllers/sessions/omniauth_controller.rb").write_text("x\n",
                                                                             encoding="utf-8")
        (root / "app/controllers/reports").mkdir()
        (root / "app/controllers/reports/monthly_controller.rb").write_text("x\n", encoding="utf-8")
        (root / "config/routes.rb").write_text(
            "Rails.application.routes.draw do\n"
            '  get "/auth/:provider/callback", to: "sessions/omniauth#create"\n'
            '  get "/", to: "home#index"\n'
            "end\n", encoding="utf-8")
        declared = routed_modules(root)
        expect("an explicit `to:` declares its module", "sessions" in declared)
        # Without this, `to: "home#index"` would declare a module named after the CONTROLLER, and
        # every flat route would silence a directory of the same name.
        expect("...but the last segment is the controller, not a module", "home" not in declared)
        f, _ = run(root)
        # THE CONTROL, on the same routes file: `reports/` is declared nowhere, in any of the three
        # forms. If reading `to:` had silenced the check wholesale, this assertion is what notices.
        # Three directories are undeclared under these routes -- billing/ and accounts/ survive from
        # the fixture above -- so name the one under test rather than counting.
        expect("a directory no route declares in ANY form is still reported",
               any("reports/monthly_controller" in x for x in f))
        expect("...and the other undeclared directories are still reported too, so reading `to:` "
               "narrowed nothing", len(f) == 3)
        expect("...and the `to:`-declared one is silent", not any("omniauth" in x for x in f))

        # A tree with routes that declare NOTHING cannot contradict anything.
        (root / "config/routes.rb").write_text("Rails.application.routes.draw do\nend\n",
                                               encoding="utf-8")
        f, _ = run(root)
        expect("with no module declared anywhere, nothing is a contradiction", not f)

        empty = Path(tempfile.mkdtemp(prefix="layer-empty-"))
        try:
            f2, t2 = run(empty)
            expect("a tree with no app/ reports nothing AND an empty table", not f2 and not t2)
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a path contradicting its route fails; a flat controller and an undeclared tree do not")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    root = Path(args.root).resolve()
    findings, table = run(root)
    if not table:
        # NOT a pass. Zero findings over zero layers reads exactly like a tidy app.
        print(f"NOT APPLICABLE: no app/ layers under {root} — this check examined nothing.")
        return 0

    print("  layer         flat  dirs  total")
    for layer, (flat, dirs, total) in table.items():
        print(f"  {layer:<12} {flat:>5} {dirs:>5} {total:>6}")
    print("\nRead ACROSS the rows. Layers that disagree with each other are the finding: for one "
          "flow, its job, its controller, its views and its models end up in unrelated places and "
          "no layer tells you where the others are. This table is ADVISORY — projects differ.")
    for f in findings:
        print(f"\n  {f}")
    print(f"\n{len(table)} layer(s) measured; {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
