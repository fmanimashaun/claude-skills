#!/usr/bin/env python3
"""A multi-tenant project's tenancy cop is installed, configured, and covers its tables (#1361).

    python3 check_tenancy_cop.py              # from the project root
    python3 check_tenancy_cop.py --selftest

Runs only when the project has declared its tenancy in `.rails-flow/tenancy.json` (checks.json's
`applies_when`); `/rails-flow:setup-flow` asks and writes it:

    {"multi_tenant": true, "tenant_foreign_key": "organization_id",
     "unscoped_tables": {"audit_events": "written by the staff plane only"}}

`{"multi_tenant": false}` is a real answer, and exits 3 (not applicable) saying so.

WHAT IT REFUSES, and why each one is here:
  * the cop missing, or different from the one rails-flow ships -- `scaffold/tenancy/scoped_lookup.rb`,
    derived from rails-8's `multi-tenancy.md` §7. A hand-edited copy is doctrine nobody reviews.
  * `.rubocop.yml` not loading it, disabling it, or leaving `SafeAutoCorrect` on (an edit hook runs
    `rubocop -a`, which would then silently rewrite a query onto an association).
  * AN UNKNOWN KEY under `Tenancy/ScopedLookup`. RuboCop does not validate a local cop's parameters
    (verified on 1.91.0), so `TenantOwnedModel:` checks nothing and says nothing. This is the only
    thing that notices.
  * a table in `db/schema.rb` carrying the tenant foreign key whose association is not in
    `TenantOwnedModels` and is not declared unscoped with a reason. Without this an empty or stale
    model list is a cop that cannot fail.

Exit 0 clean, 1 findings, 2 could not judge (no ruby to read YAML, no schema), 3 not applicable.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SHIPPED_COP = PLUGIN / "scaffold" / "tenancy" / "scoped_lookup.rb"
DECLARATION = Path(".rails-flow/tenancy.json")
COP_PATH = Path("lib/rubocop/cop/tenancy/scoped_lookup.rb")
COP_NAME = "Tenancy/ScopedLookup"

# The cop's own keys, plus the parameters RuboCop gives every cop. Anything else is a typo that
# RuboCop will swallow silently.
KNOWN_KEYS = {"TenantScope", "TenantOwnedModels",
              "Enabled", "SafeAutoCorrect", "AutoCorrect", "Include", "Exclude", "Severity",
              "Details", "Description", "StyleGuide", "Reference", "References", "Safe",
              "VersionAdded", "VersionChanged", "inherit_mode"}

CREATE_TABLE = re.compile(r'^\s*create_table\s+"(?P<table>[^"]+)".*?^\s*end\s*$', re.S | re.M)


class CannotJudge(RuntimeError):
    """Something this needs to see is not there -- exit 2, never a pass."""


def load_yaml(path: Path) -> dict:
    """`.rubocop.yml` as a dict, read by Ruby's own YAML -- the project has Ruby; stdlib Python has no YAML."""
    if shutil.which("ruby") is None:
        raise CannotJudge("no `ruby` on PATH, so .rubocop.yml cannot be read")
    done = subprocess.run(
        ["ruby", "-ryaml", "-rjson", "-e",
         "puts JSON.generate(YAML.safe_load_file(ARGV[0], aliases: true) || {})", str(path)],
        capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise CannotJudge(f"could not parse {path}: {done.stderr.strip()[:200]}")
    data = json.loads(done.stdout)
    return data if isinstance(data, dict) else {}


def rubocop_config(project: Path, load=load_yaml) -> dict:
    """`.rubocop.yml` merged over its local `inherit_from` files, the way RuboCop layers them."""
    top = project / ".rubocop.yml"
    if not top.is_file():
        return {}
    own = load(top)
    merged: dict = {}
    inherits = own.get("inherit_from") or []
    for rel in [inherits] if isinstance(inherits, str) else inherits:
        if (project / rel).is_file():
            for key, value in load(project / rel).items():
                merged[key] = {**merged[key], **value} if isinstance(value, dict) and isinstance(
                    merged.get(key), dict) else value
    for key, value in own.items():
        merged[key] = {**merged[key], **value} if isinstance(value, dict) and isinstance(
            merged.get(key), dict) else value
    return merged


def tenant_tables(schema: str, foreign_key: str) -> list[str]:
    """Every `create_table` in schema.rb whose body declares the tenant foreign key column."""
    column = re.compile(r'^\s*t\.\w+\s+"' + re.escape(foreign_key) + r'"', re.M)
    return [m.group("table") for m in CREATE_TABLE.finditer(schema) if column.search(m.group(0))]


def covered(table: str, associations: set[str]) -> bool:
    """`invoices` covers `invoices`; it also covers a namespaced table like `billing_invoices`."""
    return table in associations or any(table.endswith("_" + a) for a in associations)


def findings_for(project: Path, config: dict, shipped: str) -> list[str]:
    decl_path = project / DECLARATION
    try:
        decl = json.loads(decl_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{DECLARATION}: unreadable ({exc}) -- rewrite it with /rails-flow:setup-flow"]
    if not isinstance(decl, dict) or not isinstance(decl.get("multi_tenant"), bool):
        return [f'{DECLARATION}: needs "multi_tenant": true or false']
    out: list[str] = []
    fk = decl.get("tenant_foreign_key")
    if not isinstance(fk, str) or not fk:
        out.append(f'{DECLARATION}: a multi-tenant project names its "tenant_foreign_key", '
                   f'e.g. "organization_id"')
    unscoped = decl.get("unscoped_tables", {})
    if not isinstance(unscoped, dict) or not all(isinstance(r, str) and r.strip()
                                                 for r in unscoped.values()):
        out.append(f'{DECLARATION}: "unscoped_tables" maps each table to the REASON it is unscoped')
        unscoped = {}

    installed = project / COP_PATH
    if not installed.is_file():
        out.append(f"{COP_PATH}: missing -- install it with /rails-flow:setup-flow")
    elif installed.read_text(encoding="utf-8") != shipped:
        out.append(f"{COP_PATH}: differs from the cop rails-flow ships -- a hand-edited copy is "
                   f"doctrine nobody reviews; reinstall it with /rails-flow:setup-flow")

    requires = config.get("require") or []
    requires = [requires] if isinstance(requires, str) else requires
    if not any(str(r).endswith(COP_PATH.as_posix()) for r in requires):
        out.append(f".rubocop.yml: `require:` does not load ./{COP_PATH}, so RuboCop never runs it")
    section = config.get(COP_NAME)
    if not isinstance(section, dict):
        out.append(f".rubocop.yml: no `{COP_NAME}:` section")
        section = {}
    if section.get("Enabled") is False:
        out.append(f".rubocop.yml: `{COP_NAME}` is disabled")
    if section and section.get("SafeAutoCorrect") is not False:
        out.append(f".rubocop.yml: `{COP_NAME}` needs `SafeAutoCorrect: false` -- an edit hook runs "
                   f"`rubocop -a`, which would otherwise rewrite queries silently")
    for key in sorted(set(section) - KNOWN_KEYS):
        out.append(f".rubocop.yml: `{COP_NAME}` has unknown key `{key}` -- RuboCop ignores it "
                   f"silently, so it configures nothing")
    if section and not (isinstance(section.get("TenantScope"), str) and section["TenantScope"].strip()):
        out.append(f".rubocop.yml: `{COP_NAME}` needs a `TenantScope`, e.g. Current.organization")
    models = section.get("TenantOwnedModels")
    if section and not (isinstance(models, dict) and models):
        out.append(f".rubocop.yml: `{COP_NAME}` lists no `TenantOwnedModels` -- it can flag nothing")
        models = {}
    associations = {str(v) for v in (models or {}).values()}

    if isinstance(fk, str) and fk:
        schema = project / "db" / "schema.rb"
        if not schema.is_file():
            raise CannotJudge("no db/schema.rb, so the tenant-owned tables cannot be listed")
        for table in tenant_tables(schema.read_text(encoding="utf-8"), fk):
            if table not in unscoped and not covered(table, associations):
                out.append(f"db/schema.rb: `{table}` carries {fk} but no `TenantOwnedModels` entry "
                           f"scopes it -- add it, or list it in {DECLARATION} `unscoped_tables` with a reason")
    return out


def run(project: Path, load=load_yaml) -> int:
    decl_path = project / DECLARATION
    try:
        if json.loads(decl_path.read_text(encoding="utf-8")).get("multi_tenant") is False:
            print(f"not applicable: {DECLARATION} declares the app single-tenant")
            return 3
    except (OSError, ValueError, AttributeError):
        pass  # findings_for reports an unreadable declaration
    if not SHIPPED_COP.is_file():
        print(f"cannot judge: the shipped cop is missing from this plugin ({SHIPPED_COP})")
        return 2
    try:
        found = findings_for(project, rubocop_config(project, load), SHIPPED_COP.read_text(encoding="utf-8"))
    except CannotJudge as exc:
        print(f"cannot judge: {exc}")
        return 2
    if not found:
        print("tenancy cop: installed, configured, and covering every tenant-owned table")
        return 0
    print(f"{len(found)} tenancy-cop finding(s):")
    for f in found:
        print(f"  - {f}")
    return 1


# ---- selftest -------------------------------------------------------------------------------------
SCHEMA = '''ActiveRecord::Schema[8.0].define(version: 2026_09_27_000000) do
  create_table "organizations", force: :cascade do |t|
    t.string "name", null: false
  end

  create_table "invoices", force: :cascade do |t|
    t.bigint "organization_id", null: false
    t.string "number"
  end

  create_table "billing_credit_notes", force: :cascade do |t|
    t.bigint "organization_id", null: false
  end

  create_table "users", force: :cascade do |t|
    t.string "email_address", null: false
  end
end
'''


def _project(td: str, *, decl=None, cop: str | None = "SHIPPED", schema: str | None = SCHEMA) -> Path:
    p = Path(td)
    (p / ".rails-flow").mkdir(parents=True, exist_ok=True)
    (p / ".rails-flow" / "tenancy.json").write_text(json.dumps(decl if decl is not None else {
        "multi_tenant": True, "tenant_foreign_key": "organization_id"}), encoding="utf-8")
    if cop is not None:
        (p / COP_PATH).parent.mkdir(parents=True, exist_ok=True)
        (p / COP_PATH).write_text(cop, encoding="utf-8")
    if schema is not None:
        (p / "db").mkdir(exist_ok=True)
        (p / "db" / "schema.rb").write_text(schema, encoding="utf-8")
    return p


GOOD = {"require": ["./lib/rubocop/cop/tenancy/scoped_lookup.rb"],
        COP_NAME: {"Enabled": True, "SafeAutoCorrect": False, "Include": ["app/controllers/**/*.rb"],
                   "TenantScope": "Current.organization",
                   "TenantOwnedModels": {"Invoice": "invoices", "Billing::CreditNote": "credit_notes"}}}


def selftest() -> int:
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    shipped = "# the shipped cop\n"

    def judge(config: dict, **kw) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            cop = kw.pop("cop", "SHIPPED")
            return findings_for(_project(td, cop=shipped if cop == "SHIPPED" else cop, **kw), config, shipped)

    def with_(**over) -> dict:
        return {**GOOD, COP_NAME: {**GOOD[COP_NAME], **over}}

    # CONTROL: the conforming project is clean. Every refusal below differs from it in ONE thing.
    got = judge(GOOD)
    check("a conforming project is clean", got == [], f"{got}")

    got = judge(GOOD, cop=None)
    check("a missing cop is refused", any("missing" in f for f in got), f"{got}")
    got = judge(GOOD, cop=shipped + "# tweaked\n")
    check("a hand-edited cop is refused", any("differs" in f for f in got), f"{got}")

    got = judge({**GOOD, "require": []})
    check("a cop .rubocop.yml does not require is refused", any("require" in f for f in got), f"{got}")
    got = judge({**GOOD, "require": "./lib/rubocop/cop/tenancy/scoped_lookup.rb"})
    check("CONTROL: `require:` as a single string is accepted", got == [], f"{got}")
    got = judge(with_(Enabled=False))
    check("a disabled cop is refused", any("disabled" in f for f in got), f"{got}")
    got = judge({**GOOD, COP_NAME: {k: v for k, v in GOOD[COP_NAME].items() if k != "SafeAutoCorrect"}})
    check("a missing SafeAutoCorrect: false is refused", any("SafeAutoCorrect" in f for f in got), f"{got}")

    # THE KEY RUBOCOP SWALLOWS. A typo'd key and the real key absent: both must be named.
    typo = {k: v for k, v in GOOD[COP_NAME].items() if k != "TenantOwnedModels"}
    typo["TenantOwnedModel"] = GOOD[COP_NAME]["TenantOwnedModels"]
    got = judge({**GOOD, COP_NAME: typo})
    check("an unknown (typo'd) key is refused by name", any("`TenantOwnedModel`" in f for f in got), f"{got}")
    check("...and the real key's absence is refused too", any("lists no" in f for f in got), f"{got}")
    got = judge(with_(Exclude=["app/controllers/admin/**/*.rb"], Severity="warning"))
    check("CONTROL: RuboCop's own common parameters are not unknown keys", got == [], f"{got}")
    got = judge(with_(TenantScope=""))
    check("an empty TenantScope is refused", any("TenantScope" in f for f in got), f"{got}")

    # COVERAGE: a tenant table the model list does not reach.
    got = judge(with_(TenantOwnedModels={"Invoice": "invoices"}))
    check("a tenant-FK table outside TenantOwnedModels is refused",
          any("billing_credit_notes" in f for f in got), f"{got}")
    check("...and a table with no tenant FK is never demanded", not any("users" in f for f in got), f"{got}")
    got = judge(with_(TenantOwnedModels={"Invoice": "invoices"}), decl={
        "multi_tenant": True, "tenant_foreign_key": "organization_id",
        "unscoped_tables": {"billing_credit_notes": "written by the staff plane only"}})
    check("CONTROL: the same table declared unscoped WITH a reason is accepted", got == [], f"{got}")
    got = judge(with_(TenantOwnedModels={"Invoice": "invoices"}), decl={
        "multi_tenant": True, "tenant_foreign_key": "organization_id",
        "unscoped_tables": {"billing_credit_notes": " "}})
    check("...but WITHOUT a reason it is refused", any("REASON" in f for f in got), f"{got}")

    got = judge(GOOD, decl={"multi_tenant": True})
    check("a multi-tenant declaration with no foreign key is refused",
          any("tenant_foreign_key" in f for f in got), f"{got}")
    try:
        judge(GOOD, schema=None)
        check("no db/schema.rb cannot be judged (exit 2), never a pass", False, "no CannotJudge")
    except CannotJudge:
        check("no db/schema.rb cannot be judged (exit 2), never a pass", True)

    # THE ENTRY POINT, not just the helper: single-tenant is n/a (3), findings are 1.
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = run(_project(td, decl={"multi_tenant": False}), load=lambda p: GOOD)
        check("a declared single-tenant app is not applicable (exit 3)", rc == 3, f"exit {rc}")
    with tempfile.TemporaryDirectory() as td:
        p = _project(td, cop=None)
        (p / ".rubocop.yml").write_text("x", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = run(p, load=lambda path: GOOD)
        check("run() exits 1 on a finding", rc == 1, f"exit {rc}")

    # INHERITANCE: the cop configured in an inherited file still counts, and .rubocop.yml wins.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / ".rubocop.yml").write_text("top", encoding="utf-8")
        (p / ".rubocop").mkdir()
        (p / ".rubocop" / "tenancy.yml").write_text("inherited", encoding="utf-8")
        files = {"top": {"inherit_from": [".rubocop/tenancy.yml"], COP_NAME: {"Enabled": True}},
                 "inherited": {**GOOD, COP_NAME: {**GOOD[COP_NAME], "Enabled": False}}}
        merged = rubocop_config(p, load=lambda path: files[path.read_text(encoding="utf-8")])
        check("an inherited file's cop section is merged", merged.get(COP_NAME, {}).get(
            "TenantScope") == "Current.organization", f"{merged.get(COP_NAME)}")
        check("...and .rubocop.yml's own keys win", merged[COP_NAME]["Enabled"] is True, f"{merged[COP_NAME]}")

    # THE REAL READER, when Ruby is here: YAML through `ruby -ryaml`, not a fake loader.
    if shutil.which("ruby"):
        with tempfile.TemporaryDirectory() as td:
            y = Path(td) / ".rubocop.yml"
            y.write_text("require:\n  - ./lib/rubocop/cop/tenancy/scoped_lookup.rb\n"
                         "Tenancy/ScopedLookup:\n  SafeAutoCorrect: false\n"
                         "  TenantOwnedModels:\n    Billing::Invoice: invoices\n", encoding="utf-8")
            data = load_yaml(y)
            check("ruby reads a namespaced model key and a boolean faithfully",
                  data.get(COP_NAME, {}).get("TenantOwnedModels") == {"Billing::Invoice": "invoices"}
                  and data[COP_NAME]["SafeAutoCorrect"] is False, f"{data}")
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
