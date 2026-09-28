#!/usr/bin/env python3
"""A multi-tenant project's tenancy cop is installed, on, and covers its tables (#1361).

    python3 check_tenancy_cop.py              # from the project root
    python3 check_tenancy_cop.py --selftest

Runs only when the project has declared its tenancy in `.rails-flow/tenancy.json` (checks.json's
`applies_when`); `/rails-flow:setup-flow` asks and writes it:

    {"multi_tenant": true, "tenant_foreign_key": "organization_id",
     "unscoped_tables": {"audit_events": "written by the staff plane only"}}

`{"multi_tenant": false}` exits 3 (not applicable), saying so.

RUBOCOP IS THE AUTHORITY ON ITS OWN CONFIG. An earlier draft re-derived RuboCop's configuration in
Python, and every gap in that copy was a hole: a department-level disable, `Enabled: pending`, an
`Exclude` that swallowed controllers, `inherit_gem`, a remote `inherit_from` -- each left the cop off
while this check said clean. So this asks the project's own RuboCop twice:
  * `rubocop --show-cops Tenancy/ScopedLookup` for the RESOLVED config, and
  * a probe: `Key.find(1)` for every tenant-owned model, fed through `--stdin` as a controller with
    `--force-exclusion` (so `AllCops: Exclude` applies, as it does under `bin/ci`). Each key must
    produce an offense. That one run proves the cop is loaded, enabled, included, and recognises the
    key, whatever the inheritance.

WHAT IT REFUSES:
  * the cop missing, or different from the one rails-flow ships (`scaffold/tenancy/scoped_lookup.rb`,
    derived from rails-8's `multi-tenancy.md` §7).
  * a key the probe does not flag; `SafeAutoCorrect` not false (an edit hook runs `rubocop -a`); an
    unknown key under the cop (RuboCop validates none of a local cop's keys); a blank `TenantScope`;
    an association that is not an identifier (it would autocorrect to `Current.organization..find`).
  * a tenant-owned table -- one carrying the tenant foreign key in `db/schema.rb` or
    `db/structure.sql` -- that no key maps to (by the project's own inflector) and `unscoped_tables`
    does not excuse with a reason; a key that maps to no such table (`Invocie`); and a foreign key no
    table carries at all, because zero tables is not a pass.

Exit 0 clean, 1 findings (including a RuboCop that will not run -- that is the project's to fix),
2 could not judge (this plugin is broken), 3 not applicable.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
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
PROBE_PATH = "app/controllers/tenancy_probe_controller.rb"

# The cop's own keys, plus the parameters RuboCop gives every cop. Anything else is a typo that
# RuboCop swallows silently.
KNOWN_KEYS = {"TenantScope", "TenantOwnedModels",
              "Enabled", "SafeAutoCorrect", "AutoCorrect", "Include", "Exclude", "Severity",
              "Details", "Description", "StyleGuide", "Reference", "References", "Safe",
              "VersionAdded", "VersionChanged", "inherit_mode"}
IDENTIFIER = re.compile(r"\A[a-z_][a-z0-9_]*\Z")

SCHEMA_TABLE = re.compile(r'^\s*create_table\s+"(?P<table>[^"]+)".*?^\s*end\s*$', re.S | re.M)
STRUCTURE_TABLE = re.compile(r'^CREATE TABLE\s+(?P<table>[\w."]+)\s*\((?P<body>.*?)^\);', re.S | re.M | re.I)


class ProjectBroken(RuntimeError):
    """The project's RuboCop or Ruby would not run -- a finding, the project's to fix."""


# ---- reading the project ---------------------------------------------------------------------
def _run(project: Path, argv: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, cwd=project, input=stdin, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        raise ProjectBroken(f"`{argv[0]}` is not on PATH ({exc})") from exc


def _ruby_json(project: Path, script: str, stdin: str = ""):
    done = _run(project, ["bundle", "exec", "ruby", "-rjson", "-e", script], stdin)
    if done.returncode != 0:
        raise ProjectBroken(f"`bundle exec ruby` failed: {done.stderr.strip()[-300:]}")
    return json.loads(done.stdout)


YAML_TO_JSON = ('require "yaml"; data = YAML.safe_load(STDIN.read, permitted_classes: [Regexp, Symbol], '
                'aliases: true) || {}; puts JSON.generate(data) { |o| o.to_s }')


def resolved_cop_config(project: Path) -> dict | None:
    """The cop's config as RuboCop resolves it, or None when RuboCop does not know the cop."""
    done = _run(project, ["bundle", "exec", "rubocop", "--show-cops", COP_NAME])
    if done.returncode != 0:
        raise ProjectBroken(f"`rubocop --show-cops` failed: {done.stderr.strip()[-300:]}")
    if f"{COP_NAME}:" not in done.stdout:
        return None
    data = _ruby_json(project, YAML_TO_JSON, done.stdout)
    section = data.get(COP_NAME) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else None


def probe_unflagged(project: Path, keys: list[str]) -> list[str]:
    """The keys whose `Key.find(1)`, read as a controller, draws NO Tenancy/ScopedLookup offense."""
    if not keys:
        return []
    source = "".join(f"{k}.find(1)\n" for k in keys)
    done = _run(project, ["bundle", "exec", "rubocop", "--force-exclusion", "--format", "json",
                          "--stdin", PROBE_PATH], source)
    try:
        report = json.loads(done.stdout)
    except ValueError as exc:
        raise ProjectBroken(f"rubocop produced no report: {done.stderr.strip()[-300:]}") from exc
    return unflagged_in(report, keys)


def unflagged_in(report: dict, keys: list[str]) -> list[str]:
    lines = {o["location"]["line"] for f in report.get("files", []) for o in f.get("offenses", [])
             if o.get("cop_name") == COP_NAME}
    return [k for i, k in enumerate(keys, start=1) if i not in lines]


KEY_TABLES = ('ns = ARGV; require "active_support"; require "active_support/core_ext/string/inflections"; '
              'f = "config/initializers/inflections.rb"; begin; load f if File.exist?(f); rescue StandardError, '
              'ScriptError; end; puts JSON.generate(ns.to_h { |k| n = k.split("::"); '
              't = n.last.underscore.pluralize; pre = n[0..-2].map(&:underscore).join("_"); '
              '[k, pre.empty? ? [t] : [t, "#{pre}_#{t}"]] })')


def key_tables(project: Path, keys: list[str]) -> dict[str, list[str]]:
    """Each model key's candidate table names, by the project's own inflector."""
    if not keys:
        return {}
    done = _run(project, ["bundle", "exec", "ruby", "-rjson", "-e", KEY_TABLES, "--", *keys])
    if done.returncode != 0:
        raise ProjectBroken(f"could not inflect the model keys: {done.stderr.strip()[-300:]}")
    return json.loads(done.stdout)


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
        out.append(f'{DECLARATION}: a multi-tenant project names its "tenant_foreign_key", '
                   f'e.g. "organization_id"')
    unscoped = decl.get("unscoped_tables", {})
    if not isinstance(unscoped, dict) or not all(isinstance(r, str) and r.strip() for r in unscoped.values()):
        out.append(f'{DECLARATION}: "unscoped_tables" maps each table to the REASON it is unscoped')
    return decl, out


def judge_config(section: dict | None) -> list[str]:
    if section is None:
        return [f"RuboCop does not know `{COP_NAME}` -- `.rubocop.yml` does not `require:` "
                f"./{COP_PATH} (or loads it from the wrong path)"]
    out = []
    if section.get("SafeAutoCorrect") is not False:
        out.append(f"`{COP_NAME}` needs `SafeAutoCorrect: false` -- an edit hook runs `rubocop -a`, "
                   f"which would otherwise rewrite queries silently")
    for key in sorted(set(section) - KNOWN_KEYS):
        out.append(f"`{COP_NAME}` has unknown key `{key}` -- RuboCop ignores it silently, so it "
                   f"configures nothing")
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


def judge_coverage(tables: list[str] | None, fk: str, candidates: dict[str, list[str]],
                   unscoped: dict) -> list[str]:
    if tables is None:
        return ["no db/schema.rb or db/structure.sql, so the tenant-owned tables cannot be listed"]
    if not tables:
        # Zero is not a pass: a misspelt key (`organisation_id`) matches nothing, and the coverage
        # below would then pass over input it never read.
        return [f"no table carries `{fk}` -- is {DECLARATION}'s tenant_foreign_key the column the "
                f"app really uses?"]
    out = []
    reached = {t for names in candidates.values() for t in names}
    for table in tables:
        if table not in unscoped and table not in reached:
            out.append(f"`{table}` carries {fk} but no `TenantOwnedModels` key maps to it -- add its "
                       f"model, or list it in {DECLARATION} `unscoped_tables` with a reason")
    for key, names in candidates.items():
        if not set(names) & set(tables):
            out.append(f"`TenantOwnedModels` key `{key}` maps to no table carrying {fk} (looked for "
                       f"{', '.join(names)}) -- a misspelt or wrong constant flags nothing")
    return out


def findings(project: Path, shipped: str, *, config=resolved_cop_config, probe=probe_unflagged,
             inflect=key_tables, tables=tenant_tables) -> list[str]:
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
        for key in probe(project, keys) if section is not None else []:
            out.append(f"`{key}.find(1)` in {PROBE_PATH} draws no `{COP_NAME}` offense -- the cop is "
                       f"off, excluded from controllers, or does not recognise `{key}`")
        fk = decl.get("tenant_foreign_key")
        if isinstance(fk, str) and fk:
            unscoped = decl.get("unscoped_tables") if isinstance(decl.get("unscoped_tables"), dict) else {}
            out += judge_coverage(tables(project, fk), fk, inflect(project, keys), unscoped)
    except ProjectBroken as exc:
        out.append(f"cannot run the project's RuboCop/Ruby: {exc}")
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
        print("tenancy cop: installed, on for controllers, and covering every tenant-owned table")
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

CREATE TABLE public.users (
    id bigint NOT NULL,
    email_address character varying NOT NULL
);
'''
GOOD = {"Enabled": True, "SafeAutoCorrect": False, "Include": ["app/controllers/**/*.rb"],
        "TenantScope": "Current.organization",
        "TenantOwnedModels": {"Invoice": "invoices", "Billing::CreditNote": "credit_notes"}}
INFLECTED = {"Invoice": ["invoices"], "Billing::CreditNote": ["credit_notes", "billing_credit_notes"]}


def selftest() -> int:
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    shipped = "# the shipped cop\n"

    def judge(*, config=GOOD, unflagged=(), inflected=INFLECTED, schema=SCHEMA, decl=None, cop="SHIPPED",
              broken=None) -> list[str]:
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
            return findings(p, shipped, config=cfg, probe=lambda _, keys: [k for k in keys if k in unflagged],
                            inflect=lambda _, keys: {k: inflected.get(k, [k.lower() + "s"]) for k in keys},
                            tables=lambda _, fk: None if schema is None else tables_in_schema(schema, fk))

    def with_(**over) -> dict:
        return {**GOOD, **over}

    # CONTROL: the conforming project is clean. Every refusal below differs from it in ONE thing.
    got = judge()
    check("a conforming project is clean", got == [], f"{got}")

    check("a missing cop is refused", any("missing" in f for f in judge(cop=None)))
    check("a hand-edited cop is refused", any("differs" in f for f in judge(cop=shipped + "# x\n")))

    # THE REVIEWER'S BLOCKERS, each as it reached the old checker.
    got = judge(config=None)
    check("a cop RuboCop does not know (require missing) is refused", any("does not know" in f for f in got), f"{got}")
    got = judge(unflagged=("Invoice",))
    check("a key the PROBE does not flag (cop off / excluded / pending) is refused",
          any("`Invoice.find(1)`" in f and "draws no" in f for f in got), f"{got}")
    got = judge(config=with_(TenantOwnedModels={"Invocie": "invoices", "Billing::CreditNote": "credit_notes"}),
                inflected={**INFLECTED, "Invocie": ["invocies"]})
    check("a misspelt model KEY is refused -- the value alone proves nothing",
          any("`Invocie` maps to no table" in f for f in got), f"{got}")
    check("...and the table it failed to reach is named too", any("`invoices` carries" in f for f in got), f"{got}")
    got = judge(broken="cannot load such file -- ./lib/x")
    check("a RuboCop that will not run is a FINDING, not a silent pass", any("cannot run" in f for f in got), f"{got}")

    got = judge(config={k: v for k, v in GOOD.items() if k != "SafeAutoCorrect"})
    check("a missing SafeAutoCorrect: false is refused", any("SafeAutoCorrect" in f for f in got), f"{got}")
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

    # COVERAGE.
    got = judge(config=with_(TenantOwnedModels={"Invoice": "invoices"}))
    check("a tenant-FK table no key maps to is refused", any("`billing_credit_notes` carries" in f for f in got), f"{got}")
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

    # THE READERS, on the shapes they really meet.
    check("schema.rb: uuid ids and a schema-qualified name are read",
          tables_in_schema(SCHEMA.replace('"invoices"', '"billing.invoices"'), "organization_id")
          == ["invoices", "billing_credit_notes"])
    check("structure.sql: the tenant tables are read, and a table without the key is not",
          tables_in_structure(STRUCTURE, "organization_id") == ["invoices"],
          f"{tables_in_structure(STRUCTURE, 'organization_id')}")
    report = {"files": [{"offenses": [{"cop_name": COP_NAME, "location": {"line": 2}},
                                      {"cop_name": "Style/StringLiterals", "location": {"line": 1}}]}]}
    check("the probe report: only THIS cop's offenses count, by line",
          unflagged_in(report, ["Invoice", "Billing::CreditNote"]) == ["Invoice"],
          f"{unflagged_in(report, ['Invoice', 'Billing::CreditNote'])}")

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
