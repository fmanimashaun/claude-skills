#!/usr/bin/env python3
"""A multi-tenant project's tenancy cop is installed, on in every controller, and covers its tables (#1361).

    python3 check_tenancy_cop.py              # from the project root
    python3 check_tenancy_cop.py --selftest

Runs only when the project has declared its tenancy in `.rails-flow/tenancy.json` (checks.json's
`applies_when`); `/rails-flow:setup-flow` asks and writes it:

    {"multi_tenant": true, "tenant_foreign_key": "organization_id",
     "unscoped_tables": {"audit_events": "written by the staff plane only"},
     "unchecked_controllers": {"app/controllers/admin/*": "the staff plane reads across tenants"}}

`{"multi_tenant": false}` exits 3 (not applicable), saying so.

RUBOCOP AND THE APP ARE THE AUTHORITIES, never a copy of their rules. Review of #1403 BLOCKED twice on
that: a first draft re-derived RuboCop's config in Python (a department disable, `Enabled: pending`, an
`Exclude` swallowing controllers each left the cop off while the check said clean); the second probed
one stand-in path, so a non-recursive `Include`, a nested `app/controllers/api/.rubocop.yml`, or a nested
`SafeAutoCorrect: true` left real controllers unchecked -- or silently rewritten by `rubocop -a`. So:
  * EVERY real `app/controllers/**/*.rb` path is probed: `Key.find(1)` for each tenant-owned model, fed
    through `rubocop --force-exclusion --autocorrect --stdin <that path>`. Each key must draw an offense
    AT THAT PATH, and the offense must come back NOT corrected (so `-a` leaves it alone there). That is
    RuboCop's own answer for that file, whatever the Include, Exclude, nesting or inheritance. A path
    that deliberately goes unchecked is declared in `unchecked_controllers`, with a reason.
  * `rubocop --show-cops` gives the root config's `TenantScope`, keys and association values.
  * Each model key's table comes from the app (`Key.constantize.table_name` through `rails runner`),
    so `Invocie` is refused as no model, and `Billing::Invoice` counts only for its own table.

WHAT IT REFUSES: the cop missing or edited; a controller where a key is not flagged, or would be
autocorrected; an unknown key under the cop (RuboCop validates none of a local cop's keys); a blank
`TenantScope`; an association that is not an identifier; a key that is no loadable model, or whose table
does not carry the tenant key; a tenant-keyed table (db/schema.rb or db/structure.sql) no key reaches and
`unscoped_tables` does not excuse; a foreign key no table carries; a RuboCop or app that will not start.

Exit 0 clean, 1 findings (a project that will not boot is the project's to fix), 2 could not judge (this
plugin is broken), 3 not applicable.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SHIPPED_COP = PLUGIN / "scaffold" / "tenancy" / "scoped_lookup.rb"
DECLARATION = Path(".rails-flow/tenancy.json")
COP_PATH = Path("lib/rubocop/cop/tenancy/scoped_lookup.rb")
COP_NAME = "Tenancy/ScopedLookup"
PROBE_PATH = "app/controllers/tenancy_probe_controller.rb"   # only when the app has no controllers yet
PROBE_WORKERS = 8
SHOW_AT_MOST = 10

# The cop's own keys, plus the parameters RuboCop gives every cop. Anything else is a typo that
# RuboCop swallows silently.
KNOWN_KEYS = {"TenantScope", "TenantOwnedModels",
              "Enabled", "SafeAutoCorrect", "AutoCorrect", "Include", "Exclude", "Severity",
              "Details", "Description", "StyleGuide", "Reference", "References", "Safe",
              "VersionAdded", "VersionChanged", "inherit_mode"}
IDENTIFIER = re.compile(r"\A[a-z_][a-z0-9_]*\Z")

SCHEMA_TABLE = re.compile(r'^\s*create_table\s+"(?P<table>[^"]+)".*?^\s*end\s*$', re.S | re.M)
# pg_dump shapes: `CREATE UNLOGGED TABLE`, `CREATE TABLE IF NOT EXISTS`, and a partitioned table whose
# column list closes with `)` on its own line and is followed by `PARTITION BY ...;`. The body ends at
# the first line that starts with `)`, never at `);`, or a partitioned table swallows the next one.
STRUCTURE_TABLE = re.compile(
    r'^CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>[\w."]+)\s*\((?P<body>.*?)^\)',
    re.S | re.M | re.I)


class ProjectBroken(RuntimeError):
    """The project's RuboCop or app would not run -- a finding, the project's to fix."""


# ---- reading the project ---------------------------------------------------------------------
def _run(project: Path, argv: list[str], stdin: str = "", env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, cwd=project, input=stdin, capture_output=True, text=True, timeout=300,
                              env={**os.environ, **(env or {})})
    except FileNotFoundError as exc:
        raise ProjectBroken(f"`{argv[0]}` is not on PATH ({exc})") from exc


def _rails(project: Path) -> list[str]:
    return ["bin/rails"] if (project / "bin" / "rails").is_file() else ["bundle", "exec", "rails"]


YAML_TO_JSON = ('require "yaml"; data = YAML.safe_load(STDIN.read, permitted_classes: [Regexp, Symbol], '
                'aliases: true) || {}; puts JSON.generate(data) { |o| o.to_s }')


def resolved_cop_config(project: Path) -> dict | None:
    """The root config's section for the cop, as RuboCop resolves it; None when RuboCop does not know it."""
    done = _run(project, ["bundle", "exec", "rubocop", "--show-cops", COP_NAME])
    if done.returncode != 0:
        raise ProjectBroken(f"`rubocop --show-cops` failed: {done.stderr.strip()[-300:]}")
    if f"{COP_NAME}:" not in done.stdout:
        return None
    parsed = _run(project, ["bundle", "exec", "ruby", "-rjson", "-e", YAML_TO_JSON], done.stdout)
    if parsed.returncode != 0:
        raise ProjectBroken(f"could not read `--show-cops`: {parsed.stderr.strip()[-300:]}")
    section = json.loads(parsed.stdout).get(COP_NAME)
    return section if isinstance(section, dict) else None


def controller_paths(project: Path) -> list[str]:
    found = sorted(p.relative_to(project).as_posix() for p in (project / "app" / "controllers").rglob("*.rb"))
    return found or [PROBE_PATH]


def probe_verdict(report: dict, keys: list[str]) -> dict:
    """Which keys THIS path does not flag, and which it would autocorrect, from one `-a --stdin` report."""
    offenses = [o for f in report.get("files", []) for o in f.get("offenses", []) if o.get("cop_name") == COP_NAME]
    flagged = {o["location"]["line"] for o in offenses}
    corrected = {o["location"]["line"] for o in offenses if o.get("corrected")}
    return {"unflagged": [k for i, k in enumerate(keys, 1) if i not in flagged],
            "autocorrected": [k for i, k in enumerate(keys, 1) if i in corrected]}


def probe_path(project: Path, path: str, keys: list[str]) -> dict:
    source = "".join(f"{k}.find(1)\n" for k in keys)
    done = _run(project, ["bundle", "exec", "rubocop", "--force-exclusion", "--autocorrect", "--format", "json",
                          "--stdin", path], source)
    try:
        report = json.loads(done.stdout.strip().splitlines()[0]) if done.stdout.strip() else None
    except ValueError:
        report = None
    if report is None:
        raise ProjectBroken(f"rubocop produced no report for {path}: {done.stderr.strip()[-300:]}")
    return probe_verdict(report, keys)


def probe_all(project: Path, paths: list[str], keys: list[str]) -> dict[str, dict]:
    if not keys:
        return {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_WORKERS) as pool:
        return dict(zip(paths, pool.map(lambda p: probe_path(project, p, keys), paths)))


MODEL_TABLES = ('keys = JSON.parse(ENV.fetch("TENANCY_KEYS")); '
                'puts JSON.generate(keys.to_h { |k| begin; [k, {"table" => k.constantize.table_name}]; '
                'rescue NameError => e; [k, {"missing" => e.message.lines.first.to_s.strip}]; end })')


def model_tables(project: Path, keys: list[str]) -> dict[str, dict]:
    """Each key's real table, from the app: {"table": name} or {"missing": why}."""
    if not keys:
        return {}
    done = _run(project, [*_rails(project), "runner", MODEL_TABLES], env={"TENANCY_KEYS": json.dumps(keys)})
    if done.returncode != 0:
        raise ProjectBroken(f"`rails runner` failed, so the models' tables cannot be read: {done.stderr.strip()[-300:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def tenant_tables(project: Path, foreign_key: str) -> list[str] | None:
    """Tables carrying the tenant foreign key, from db/schema.rb or db/structure.sql; None if neither."""
    schema, structure = project / "db" / "schema.rb", project / "db" / "structure.sql"
    if schema.is_file():
        return tables_in_schema(schema.read_text(encoding="utf-8"), foreign_key)
    if structure.is_file():
        return tables_in_structure(structure.read_text(encoding="utf-8"), foreign_key)
    return None


def _bare(table: str) -> str:
    """`billing.invoices` and `public."invoices"` are the table `invoices`."""
    return table.replace('"', "").rsplit(".", 1)[-1]


def tables_in_schema(text: str, fk: str) -> list[str]:
    column = re.compile(r'^\s*t\.\w+\s+"' + re.escape(fk) + r'"', re.M)
    return [_bare(m.group("table")) for m in SCHEMA_TABLE.finditer(text) if column.search(m.group(0))]


def tables_in_structure(text: str, fk: str) -> list[str]:
    column = re.compile(r'^\s*"?' + re.escape(fk) + r'"?\s', re.M)
    return [_bare(m.group("table")) for m in STRUCTURE_TABLE.finditer(text) if column.search(m.group("body"))]


# ---- judging --------------------------------------------------------------------------------
def _reasons(decl: dict, key: str) -> tuple[dict, list[str]]:
    value = decl.get(key, {})
    if not isinstance(value, dict) or not all(isinstance(r, str) and r.strip() for r in value.values()):
        return {}, [f'{DECLARATION}: "{key}" maps each entry to the REASON it is excused']
    return value, []


def declaration(project: Path) -> tuple[dict | None, list[str]]:
    try:
        decl = json.loads((project / DECLARATION).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"{DECLARATION}: unreadable ({exc}) -- rewrite it with /rails-flow:setup-flow"]
    if not isinstance(decl, dict) or not isinstance(decl.get("multi_tenant"), bool):
        return None, [f'{DECLARATION}: needs "multi_tenant": true or false']
    out = []
    fk = decl.get("tenant_foreign_key")
    if decl["multi_tenant"] and not (isinstance(fk, str) and fk):
        out.append(f'{DECLARATION}: a multi-tenant project names its "tenant_foreign_key", e.g. "organization_id"')
    for key in ("unscoped_tables", "unchecked_controllers"):
        out += _reasons(decl, key)[1]
    return decl, out


def judge_config(section: dict | None) -> list[str]:
    if section is None:
        return [f"RuboCop does not know `{COP_NAME}` -- `.rubocop.yml` does not `require:` "
                f"./{COP_PATH} (or loads it from the wrong path)"]
    out = []
    for key in sorted(set(section) - KNOWN_KEYS):
        out.append(f"`{COP_NAME}` has unknown key `{key}` -- RuboCop ignores it silently, so it configures nothing")
    if not (isinstance(section.get("TenantScope"), str) and section["TenantScope"].strip()):
        out.append(f"`{COP_NAME}` needs a `TenantScope`, e.g. Current.organization")
    models = section.get("TenantOwnedModels")
    if not (isinstance(models, dict) and models):
        out.append(f"`{COP_NAME}` lists no `TenantOwnedModels` as `Model: association` -- it can flag nothing")
    else:
        for model, assoc in models.items():
            if not (isinstance(assoc, str) and IDENTIFIER.match(assoc)):
                out.append(f"`{COP_NAME}`: `{model}` maps to {assoc!r}, not an association name -- "
                           f"it would autocorrect to broken Ruby")
    return out


def judge_paths(verdicts: dict[str, dict], unchecked: dict) -> list[str]:
    """Per real controller: every key flagged there, none autocorrected, unless the path is declared."""
    def excused(path: str) -> bool:
        return any(fnmatch.fnmatch(path, glob) for glob in unchecked)

    off = [(p, v["unflagged"]) for p, v in verdicts.items() if v["unflagged"] and not excused(p)]
    fixed = [(p, v["autocorrected"]) for p, v in verdicts.items() if v["autocorrected"]]
    out = []
    for p, keys in off[:SHOW_AT_MOST]:
        out.append(f"{p}: `{keys[0]}.find(1)` draws no `{COP_NAME}` offense here -- the cop is off, excluded "
                   f"or not included for this file. If that is deliberate, declare it in {DECLARATION} "
                   f"`unchecked_controllers` with a reason")
    if len(off) > SHOW_AT_MOST:
        out.append(f"...and {len(off) - SHOW_AT_MOST} more controller(s) the cop does not check")
    for p, keys in fixed[:SHOW_AT_MOST]:
        out.append(f"{p}: `rubocop -a` would REWRITE `{keys[0]}.find` here -- `SafeAutoCorrect` is not false "
                   f"for this file (a nested config?), so an edit hook changes queries silently")
    if len(fixed) > SHOW_AT_MOST:
        out.append(f"...and {len(fixed) - SHOW_AT_MOST} more controller(s) where `-a` would rewrite")
    return out


def judge_coverage(tables: list[str] | None, fk: str, owned: dict[str, dict], unscoped: dict) -> list[str]:
    if tables is None:
        return ["no db/schema.rb or db/structure.sql, so the tenant-owned tables cannot be listed"]
    if not tables:
        # Zero is not a pass: a misspelt key (`organisation_id`) matches nothing, and the coverage
        # below would then pass over input it never read.
        return [f"no table carries `{fk}` -- is {DECLARATION}'s tenant_foreign_key the column the app really uses?"]
    out = []
    reached = {v["table"] for v in owned.values() if "table" in v}
    for key, v in owned.items():
        if "missing" in v:
            out.append(f"`TenantOwnedModels` key `{key}` is no model this app loads ({v['missing']}) -- "
                       f"a misspelt or wrong constant flags nothing")
        elif v.get("table") not in tables:
            out.append(f"`TenantOwnedModels` key `{key}` uses table `{v.get('table')}`, which does not carry {fk}")
    for table in tables:
        if table not in unscoped and table not in reached:
            out.append(f"`{table}` carries {fk} but no `TenantOwnedModels` key uses it -- add its model, or list "
                       f"it in {DECLARATION} `unscoped_tables` with a reason")
    return out


def findings(project: Path, shipped: str, *, config=resolved_cop_config, paths=controller_paths,
             probe=probe_all, owned=model_tables, tables=tenant_tables) -> list[str]:
    decl, out = declaration(project)
    if decl is None:
        return out
    installed = project / COP_PATH
    if not installed.is_file():
        return out + [f"{COP_PATH}: missing -- install it with /rails-flow:setup-flow"]
    if installed.read_text(encoding="utf-8") != shipped:
        out.append(f"{COP_PATH}: differs from the cop rails-flow ships -- a hand-edited copy is "
                   f"doctrine nobody reviews; reinstall it with /rails-flow:setup-flow")
    try:
        section = config(project)
        out += judge_config(section)
        models = (section or {}).get("TenantOwnedModels")
        keys = [str(k) for k in models] if isinstance(models, dict) else []
        if section is not None and keys:
            out += judge_paths(probe(project, paths(project), keys), _reasons(decl, "unchecked_controllers")[0])
        fk = decl.get("tenant_foreign_key")
        if isinstance(fk, str) and fk:
            out += judge_coverage(tables(project, fk), fk, owned(project, keys), _reasons(decl, "unscoped_tables")[0])
    except ProjectBroken as exc:
        out.append(f"cannot run the project's RuboCop/app: {exc}")
    return out


def run(project: Path, **collectors) -> int:
    try:
        if json.loads((project / DECLARATION).read_text(encoding="utf-8")).get("multi_tenant") is False:
            print(f"not applicable: {DECLARATION} declares the app single-tenant")
            return 3
    except (OSError, ValueError, AttributeError):
        pass  # `declaration()` reports an unreadable file
    if not SHIPPED_COP.is_file():
        print(f"cannot judge: the shipped cop is missing from this plugin ({SHIPPED_COP})")
        return 2
    found = findings(project, SHIPPED_COP.read_text(encoding="utf-8"), **collectors)
    if not found:
        print("tenancy cop: installed, on in every controller, and covering every tenant-owned table")
        return 0
    print(f"{len(found)} tenancy-cop finding(s):")
    for f in found:
        print(f"  - {f}")
    return 1


# ---- selftest -----------------------------------------------------------------------------------
SCHEMA = '''ActiveRecord::Schema[8.0].define(version: 2026_09_27_000000) do
  create_table "organizations", force: :cascade do |t|
    t.string "name", null: false
  end

  create_table "invoices", force: :cascade do |t|
    t.bigint "organization_id", null: false
  end

  create_table "billing_credit_notes", id: :uuid, force: :cascade do |t|
    t.uuid "organization_id", null: false
  end

  create_table "users", force: :cascade do |t|
    t.string "email_address", null: false
  end
end
'''
STRUCTURE = '''CREATE TABLE public.invoices (
    id bigint NOT NULL,
    organization_id bigint NOT NULL
);

CREATE TABLE public.events (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    at timestamp NOT NULL
)
PARTITION BY RANGE (at);

CREATE UNLOGGED TABLE public.cache_rows (
    organization_id bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS public.notes (
    organization_id bigint NOT NULL
);

CREATE TABLE public.users (
    id bigint NOT NULL,
    email_address character varying NOT NULL
);
'''
GOOD = {"Enabled": True, "SafeAutoCorrect": False, "Include": ["app/controllers/**/*.rb"],
        "TenantScope": "Current.organization",
        "TenantOwnedModels": {"Invoice": "invoices", "Billing::CreditNote": "credit_notes"}}
OWNED = {"Invoice": {"table": "invoices"}, "Billing::CreditNote": {"table": "billing_credit_notes"}}
PATHS = ["app/controllers/invoices_controller.rb", "app/controllers/api/invoices_controller.rb"]


def selftest() -> int:
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    shipped = "# the shipped cop\n"
    CLEAN = {"unflagged": [], "autocorrected": []}

    def judge(*, config=GOOD, verdicts=None, owned=None, schema=SCHEMA, decl=None, cop="SHIPPED",
              broken=None, paths=PATHS) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / ".rails-flow").mkdir()
            (p / DECLARATION).write_text(json.dumps(decl if decl is not None else {
                "multi_tenant": True, "tenant_foreign_key": "organization_id"}), encoding="utf-8")
            if cop is not None:
                (p / COP_PATH).parent.mkdir(parents=True)
                (p / COP_PATH).write_text(shipped if cop == "SHIPPED" else cop, encoding="utf-8")

            def cfg(_):
                if broken:
                    raise ProjectBroken(broken)
                return config
            v = verdicts if verdicts is not None else {}
            return findings(p, shipped, config=cfg, paths=lambda _: paths,
                            probe=lambda _, ps, keys: {x: v.get(x, CLEAN) for x in ps},
                            owned=lambda _, keys: {k: (owned or OWNED).get(k, {"missing": "uninitialized constant"})
                                                   for k in keys},
                            tables=lambda _, fk: None if schema is None else tables_in_schema(schema, fk))

    def with_(**over) -> dict:
        return {**GOOD, **over}

    # CONTROL: the conforming project is clean. Every refusal below differs from it in ONE thing.
    got = judge()
    check("a conforming project is clean", got == [], f"{got}")
    check("a missing cop is refused", any("missing" in f for f in judge(cop=None)))
    check("a hand-edited cop is refused", any("differs" in f for f in judge(cop=shipped + "# x\n")))
    got = judge(config=None)
    check("a cop RuboCop does not know (require missing) is refused", any("does not know" in f for f in got), f"{got}")

    # ROUND 2'S BLOCKERS: the probe is PER REAL PATH. A nested config, a non-recursive Include or an
    # Exclude that leaves ONE controller unchecked is refused by that path, not averaged away.
    api = "app/controllers/api/invoices_controller.rb"
    got = judge(verdicts={api: {"unflagged": ["Invoice", "Billing::CreditNote"], "autocorrected": []}})
    check("a controller where the cop is off (nested config / non-recursive Include) is refused BY PATH",
          any(f.startswith(api) and "draws no" in f for f in got), f"{got}")
    check("...and the top-level controller, which IS checked, is not named", not any(
          f.startswith("app/controllers/invoices_controller.rb") for f in got), f"{got}")
    got = judge(verdicts={api: {"unflagged": ["Invoice"], "autocorrected": []}},
                decl={"multi_tenant": True, "tenant_foreign_key": "organization_id",
                      "unchecked_controllers": {"app/controllers/api/*": "the partner API reads across tenants"}})
    check("CONTROL: the same path declared in unchecked_controllers WITH a reason is accepted", got == [], f"{got}")
    got = judge(decl={"multi_tenant": True, "tenant_foreign_key": "organization_id",
                      "unchecked_controllers": {"app/controllers/api/*": ""}})
    check("...but WITHOUT a reason it is refused", any("REASON" in f for f in got), f"{got}")
    got = judge(verdicts={api: {"unflagged": [], "autocorrected": ["Invoice"]}})
    check("a controller where `-a` would rewrite (nested SafeAutoCorrect: true) is refused BY PATH",
          any(f.startswith(api) and "REWRITE" in f for f in got), f"{got}")
    many = {f"app/controllers/c{i}_controller.rb": {"unflagged": ["Invoice"], "autocorrected": []} for i in range(15)}
    got = judge(paths=list(many), verdicts=many)
    check("many unchecked controllers are capped, not printed without bound",
          sum("draws no" in f for f in got) == SHOW_AT_MOST and any("5 more" in f for f in got), f"{len(got)}")
    report = {"files": [{"offenses": [
        {"cop_name": COP_NAME, "location": {"line": 1}, "corrected": False},
        {"cop_name": COP_NAME, "location": {"line": 2}, "corrected": True},
        {"cop_name": "Style/FrozenStringLiteralComment", "location": {"line": 3}, "corrected": False}]}]}
    got = probe_verdict(report, ["Invoice", "Billing::CreditNote", "Order"])
    check("a probe report: only THIS cop counts; line 3 is unflagged, line 2 was autocorrected",
          got == {"unflagged": ["Order"], "autocorrected": ["Billing::CreditNote"]}, f"{got}")

    # CONFIG, from --show-cops.
    typo = {k: v for k, v in GOOD.items() if k != "TenantOwnedModels"} | {"TenantOwnedModel": GOOD["TenantOwnedModels"]}
    got = judge(config=typo)
    check("an unknown (typo'd) key is refused by name", any("`TenantOwnedModel`" in f for f in got), f"{got}")
    check("...and the real key's absence is refused too", any("lists no" in f for f in got), f"{got}")
    got = judge(config=with_(Exclude=["app/controllers/admin/**/*.rb"], Severity="warning"))
    check("CONTROL: RuboCop's own common parameters are not unknown keys", got == [], f"{got}")
    check("an empty TenantScope is refused", any("TenantScope" in f for f in judge(config=with_(TenantScope=" "))))
    got = judge(config=with_(TenantOwnedModels={"Invoice": None, "Billing::CreditNote": "credit_notes"}))
    check("a blank association is refused (it would autocorrect to broken Ruby)",
          any("not an association name" in f for f in got), f"{got}")

    # COVERAGE, by the tables the APP reports.
    got = judge(config=with_(TenantOwnedModels={"Invocie": "invoices", "Billing::CreditNote": "credit_notes"}))
    check("a misspelt model KEY is refused as no model the app loads", any("`Invocie` is no model" in f for f in got), f"{got}")
    check("...and the table it failed to reach is named too", any("`invoices` carries" in f for f in got), f"{got}")
    got = judge(owned={"Invoice": {"table": "invoices"}, "Billing::CreditNote": {"table": "users"}})
    check("a key whose table does not carry the tenant key is refused", any("`users`, which does not" in f for f in got), f"{got}")
    got = judge(config=with_(TenantOwnedModels={"Invoice": "invoices"}))
    check("a tenant-FK table no key uses is refused", any("`billing_credit_notes` carries" in f for f in got), f"{got}")
    check("...and a table with no tenant FK is never demanded", not any("users" in f for f in got), f"{got}")
    got = judge(config=with_(TenantOwnedModels={"Invoice": "invoices"}), decl={
        "multi_tenant": True, "tenant_foreign_key": "organization_id",
        "unscoped_tables": {"billing_credit_notes": "written by the staff plane only"}})
    check("CONTROL: the same table declared unscoped WITH a reason is accepted", got == [], f"{got}")
    got = judge(decl={"multi_tenant": True, "tenant_foreign_key": "organization_id",
                      "unscoped_tables": {"billing_credit_notes": " "}})
    check("...but WITHOUT a reason it is refused", any("REASON" in f for f in got), f"{got}")
    got = judge(decl={"multi_tenant": True, "tenant_foreign_key": "organisation_id"})
    check("a foreign key no table carries is refused -- zero tables is not a pass",
          any("no table carries" in f for f in got), f"{got}")
    check("no schema at all cannot be passed over", any("cannot be listed" in f for f in judge(schema=None)))
    check("a multi-tenant declaration with no foreign key is refused",
          any("tenant_foreign_key" in f for f in judge(decl={"multi_tenant": True})))
    got = judge(broken="cannot load such file -- ./lib/x")
    check("a RuboCop that will not run is a FINDING, not a silent pass", any("cannot run" in f for f in got), f"{got}")

    # THE READERS, on the shapes they really meet.
    check("schema.rb: uuid ids and a schema-qualified name are read",
          tables_in_schema(SCHEMA.replace('"invoices"', '"billing.invoices"'), "organization_id")
          == ["invoices", "billing_credit_notes"])
    got = tables_in_structure(STRUCTURE, "organization_id")
    check("structure.sql: partitioned, UNLOGGED and IF NOT EXISTS tables are each read, and none swallows the next",
          got == ["invoices", "events", "cache_rows", "notes"], f"{got}")

    # THE ENTRY POINT: single-tenant is n/a (3), findings are 1.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / ".rails-flow").mkdir()
        (p / DECLARATION).write_text('{"multi_tenant": false}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = run(p)
        check("a declared single-tenant app is not applicable (exit 3)", rc == 3, f"exit {rc}")
        (p / DECLARATION).write_text('{"multi_tenant": true, "tenant_foreign_key": "organization_id"}',
                                     encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = run(p)
        check("run() exits 1 on a finding", rc == 1, f"exit {rc}")

    if SHIPPED_COP.is_file():
        check("the shipped cop is present in this plugin", "class ScopedLookup < Base" in
              SHIPPED_COP.read_text(encoding="utf-8"))

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} check-tenancy-cop assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    return selftest() if a.selftest else run(Path.cwd())


if __name__ == "__main__":
    sys.exit(main())
