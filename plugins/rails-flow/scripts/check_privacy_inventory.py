#!/usr/bin/env python3
"""Every column in db/schema.rb, and in each other db/*_schema.rb, is classified in config/privacy_inventory.yml (#1310, #1695).

WHY. #1289 has an agent draft the privacy policy from the app's data inventory, and the inventory
lived in prose: nothing noticed a new personal-data column. The inventory is now a file, and this
gate makes a new column fail until someone decides what it holds.

THE FILE (the shape one consumer designed, adopted as the standard):
    users:
      email_address: { category: staff_contact, basis: contract, retention: account lifetime + 2 years }
      created_at: { category: none }
      notes:
        category: staff_contact
        basis: legitimate interest
        retention: 1 year

RULES
  * every column of every `create_table` in db/schema.rb, and in every other `db/*_schema.rb` a second database dumps
    (`schema_dump: observability_schema.rb` -> db/observability_schema.rb), is listed. The implicit `id` key is exempt, and
    it is PRESENT: an inventory may list it, and that entry is stale only when the table says `id: false` (#1732);
    the Rails 8 Solid trio (db/cache_schema.rb, db/queue_schema.rb, db/cable_schema.rb) is framework-owned and is NOT read
    WHEN EVERY ONE OF ITS TABLES IS `solid_*` (a file of that name holding anything else is the project's own and is read), so a
    project that never classified `solid_*` tables does not turn red (their job arguments are a separate question). A table of
    such a file that the inventory NAMES is read, and only that table: the entries listed for it are judged (they exist, they
    carry a category) rather than reported stale, its unlisted columns are not required, and the file's other Solid tables stay the
    framework's (#1732);
  * a table that appears in two schema files is a finding: the inventory is keyed by table name, so it could not say which;
  * `category: none` is an explicit "not personal"; any other category needs `basis` and `retention`;
  * an entry for a table or column that no schema file has any more is a finding (it would mislead the policy);
  * no inventory at all is a finding that names how many columns are unclassified, never clean.

Each schema is read with `build_project_wiki.parse_schema` -- one schema reader, not two.

Run:  check_privacy_inventory.py [--root DIR]
      check_privacy_inventory.py --selftest
Exit: 0 clean · 1 finding(s) · 2 unusable (inventory unreadable) · 3 not applicable (no db/schema.rb)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_project_wiki import parse_schema, parse_yaml_subset  # noqa: E402  -- one reader each

SCHEMA = Path("db/schema.rb")
# The Solid trio: a Rails 8 app has all three by default and never classified their tables; reading them would turn the gate red for
# every consumer, and only a file that holds nothing but `solid_*` tables is skipped. Decided in #1695; classifying `solid_*` (the queue holds job arguments) is a separate question.
FRAMEWORK_SCHEMAS = frozenset({"cache_schema.rb", "queue_schema.rb", "cable_schema.rb"})
INVENTORY = Path("config/privacy_inventory.yml")
FLOW = re.compile(r"^\{(?P<body>.*)\}$")


class Unusable(RuntimeError):
    pass


def _entry(value) -> dict:
    """A column's entry as a dict, whether written block-style or as an inline `{ k: v }` map."""
    if isinstance(value, dict):
        return {k: str(v).strip().strip("'\"") for k, v in value.items()}
    m = FLOW.match(str(value).strip())
    if not m:
        raise Unusable(f"expected `{{ category: ... }}` or a nested block, got {value!r}")
    out = {}
    for part in _split_flow(m.group("body")):
        if not part.strip():
            continue
        k, sep, v = part.partition(":")
        if not sep:
            raise Unusable(f"cannot read `{part.strip()}` in {value!r}")
        out[k.strip()] = v.strip().strip("'\"")
    return out


def _split_flow(body: str) -> list[str]:
    """Split a flow map's body on commas OUTSIDE quotes, so a quoted value may contain a comma."""
    parts, cur, quote = [], [], None
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def load_inventory(root: Path) -> dict[str, dict[str, dict]] | None:
    path = root / INVENTORY
    if not path.is_file():
        return None
    raw = parse_yaml_subset(path.read_text(encoding="utf-8"))
    inv: dict[str, dict[str, dict]] = {}
    for table, cols in raw.items():
        if not isinstance(cols, dict):
            raise Unusable(f"{INVENTORY}: `{table}` must map columns, got {cols!r}")
        inv[table] = {col: _entry(v) for col, v in cols.items()}
    return inv


def _solid_only(path: Path) -> bool:
    """True when a framework-named schema file holds nothing but Solid tables: only then is it the framework's, not the project's."""
    return all(table.startswith("solid_") for table in parse_schema(path.read_text(encoding="utf-8"))["tables"])


def schema_files(root: Path) -> list[Path]:
    """db/schema.rb first, then every other db/*_schema.rb a second database dumps, in name order."""
    return [root / SCHEMA, *sorted((root / "db").glob("*_schema.rb"))]


def framework_owned(path: Path) -> bool:
    """A Solid trio file holding only `solid_*` tables. A cache_schema.rb with a table of the project's own is the project's: the
    name alone decides nothing."""
    return path.name in FRAMEWORK_SCHEMAS and _solid_only(path)


def check(root: Path) -> tuple[int, list[str]]:
    if not (root / SCHEMA).is_file():
        return 3, [f"not applicable: no {SCHEMA}"]
    try:
        inv = load_inventory(root)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    tables: dict = {}
    source: dict[str, str] = {}
    duplicates: list[str] = []
    named = frozenset(inv or ())
    framework: set[str] = set()   # Solid tables the inventory names: listed entries judged, unlisted columns not required (#1732)
    for path in schema_files(root):
        name = path.relative_to(root).as_posix()
        owned = framework_owned(path)
        for table, spec in parse_schema(path.read_text(encoding="utf-8"))["tables"].items():
            if owned and table not in named:
                continue   # the framework's, and the project never classified it (#1695); a named one is judged (#1732)
            if owned:
                framework.add(table)
            if table in tables:
                duplicates.append(f"  [duplicate-table] {table} -- in {source[table]} and in {name}; the inventory is keyed by table name")
                continue
            tables[table], source[table] = spec, name
    columns = {(t, c[0]) for t, spec in tables.items() for c in spec["columns"]}
    # What an inventory entry may name: the listed columns, plus the `id` Rails adds unless the table says `id: false` (#1732). Never
    # required (an unlisted implicit id is not unclassified), only allowed.
    present = columns | {(t, "id") for t, spec in tables.items() if spec["implicit_id"]}

    def where(table: str) -> str:
        """Only a table from a second schema file is named; db/schema.rb stays unmentioned, as before."""
        return "" if source[table] == SCHEMA.as_posix() else f" (in {source[table]})"

    files = ", ".join(sorted({*source.values()}))
    if inv is None:
        return 1, [f"no {INVENTORY}: all {len(columns)} column(s) across {len(tables)} table(s) are "
                   "unclassified. /rails-flow:setup-flow drafts it; each column gets a category, or "
                   "`category: none`."]
    findings = []
    for t, c in sorted(columns):
        entry = inv.get(t, {}).get(c)
        if entry is None and t in framework:
            continue
        if entry is None:
            findings.append(f"  [unclassified] {t}.{c}{where(t)} -- not in {INVENTORY}")
            continue
        category = entry.get("category", "")
        if not category:
            findings.append(f"  [no-category] {t}.{c}{where(t)} -- every entry needs a category (`none` if not personal)")
        elif category != "none":
            for key in ("basis", "retention"):
                if not entry.get(key):
                    findings.append(f"  [no-{key}] {t}.{c}{where(t)} -- personal ({category}) with no {key}")
    for t, cols in sorted(inv.items()):
        if t not in tables:
            findings.append(f"  [stale-table] {t} -- in {INVENTORY} but in no schema file ({files})")
            continue
        for c in sorted(cols):
            if (t, c) not in present:
                findings.append(f"  [stale-column] {t}.{c} -- in {INVENTORY} but not in {source[t]}")
    findings = duplicates + findings
    if findings:
        return 1, [f"{len(findings)} privacy-inventory finding(s) across {len(columns)} column(s):", *findings]
    personal = sum(1 for t, c in columns if inv.get(t, {}).get(c, {}).get("category") != "none")
    return 0, [f"all {len(columns)} column(s) classified; {personal} hold personal data"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_privacy_inventory.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = check(a.root.resolve())
    print("\n".join(lines))
    return code


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    fails: list[str] = []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    schema = ('ActiveRecord::Schema[8.1].define(version: 2026_09_25_000000) do\n'
              '  create_table "users", force: :cascade do |t|\n'
              '    t.string "email_address", null: false\n'
              '    t.string "password_digest"\n'
              '    t.datetime "created_at", null: false\n'
              '    t.index ["email_address"], name: "index_users_on_email_address", unique: true\n'
              '  end\n'
              '  create_table "widgets", force: :cascade do |t|\n'
              '    t.string "name"\n'
              '  end\n'
              'end\n')
    good = ("users:\n"
            "  email_address: { category: staff_contact, basis: contract, retention: account lifetime + 2 years }\n"
            "  password_digest:\n"
            "    category: credential\n"
            "    basis: contract\n"
            "    retention: account lifetime\n"
            "  created_at: { category: none }\n"
            "widgets:\n"
            "  name: { category: none }   # a product name, not a person\n")

    def app(tmp: Path, inventory: str | None, schema_text: str = schema, extra: dict[str, str] | None = None) -> Path:
        (tmp / "db").mkdir(parents=True, exist_ok=True)
        (tmp / "db" / "schema.rb").write_text(schema_text, encoding="utf-8")
        for name, text in (extra or {}).items():
            (tmp / "db" / name).write_text(text, encoding="utf-8")
        (tmp / "config").mkdir(exist_ok=True)
        if inventory is not None:
            (tmp / INVENTORY).write_text(inventory, encoding="utf-8")
        return tmp

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        code, out = check(app(t / "good", good))
        check_("CONTROL: a complete inventory is clean", code == 0 and "2 hold personal data" in out[0], f"{code} {out}")
        check_("the index line is not read as a column", code == 0)

        code, out = check(app(t / "missing", None))
        check_("no inventory is a finding naming the count, never clean",
               code == 1 and "all 4 column(s)" in out[0], f"{code} {out}")

        grown = schema.replace('    t.string "name"\n', '    t.string "name"\n    t.string "owner_phone"\n')
        code, out = check(app(t / "grown", good, grown))
        check_("a new column fails until it is classified",
               code == 1 and any("[unclassified] widgets.owner_phone" in l for l in out), f"{out}")

        code, out = check(app(t / "nobasis", good.replace(", basis: contract, retention: account lifetime + 2 years", "")))
        check_("a personal column with no basis or retention is a finding",
               any("[no-basis] users.email_address" in l for l in out)
               and any("[no-retention] users.email_address" in l for l in out), f"{out}")
        code, out = check(app(t / "none", good))
        check_("`category: none` needs no basis or retention", code == 0)

        code, out = check(app(t / "stale", good + "  retired_col: { category: none }\ngone_table:\n  x: { category: none }\n"))
        check_("an entry for a vanished column is a finding", any("[stale-column] widgets.retired_col" in l for l in out), f"{out}")
        check_("an entry for a vanished table is a finding", any("[stale-table] gone_table" in l for l in out), f"{out}")

        code, out = check(app(t / "bad", "users:\n  email_address: category staff\n"))
        check_("an unreadable entry is UNUSABLE (exit 2)", code == 2, f"{code} {out}")
        empty = t / "noschema"
        empty.mkdir()
        check_("no db/schema.rb: not applicable (exit 3)", check(empty)[0] == 3)

        def entry_of(root: Path) -> dict:
            """The users.email_address entry, or {} when the file cannot be read -- so a parser break
            is reported by the fixture that names it, never by a crash that hides the rest."""
            try:
                return load_inventory(root)["users"]["email_address"]
            except (Unusable, KeyError, TypeError):
                return {}

        # THREE PARSER DEFECTS, from a real schema and inventory (a check constraint with `::`, a `#`
        # inside a value, a comma inside a quoted value). Each once read as a column or truncated.
        constrained = schema.replace('    t.string "name"\n',
                                     '    t.string "name"\n'
                                     "    t.check_constraint \"(name)::text ~ '^[A-Z]{3}$'::text\", name: \"widgets_name_code\"\n")
        code, out = check(app(t / "constraint", good, constrained))
        check_("a check constraint is not a column", code == 0, f"{code} {out}")
        # `#` FOLLOWS YAML: after whitespace it starts a comment, even mid-value, as every other reader
        # of this file sees it. So the gate never truncates SILENTLY: inside an inline map the cut leaves
        # the brace unclosed and is refused; a `#` with no space before it, or inside quotes, is kept.
        tmp = app(t / "hash", good.replace("retention: account lifetime + 2 years", "retention: until the #893 rate review"))
        code, out = check(tmp)
        check_("an unquoted ` #` that cuts an inline entry is refused, not silently truncated", code == 2, f"{code} {out}")
        tmp = app(t / "hashq", good.replace("retention: account lifetime + 2 years", 'retention: "until the #893 rate review"'))
        check_("a quoted `#` is kept",
               entry_of(tmp).get("retention") == "until the #893 rate review", repr(entry_of(tmp)))
        tmp = app(t / "hashn", good.replace("retention: account lifetime + 2 years", "retention: rate#893 review"))
        check_("a `#` with no space before it is part of the value",
               entry_of(tmp).get("retention") == "rate#893 review", repr(entry_of(tmp)))
        comma = good.replace("retention: account lifetime + 2 years", 'retention: "account lifetime, then 2 years"')
        tmp = app(t / "comma", comma)
        check_("a quoted value may contain a comma",
               entry_of(tmp).get("retention") == "account lifetime, then 2 years", repr(entry_of(tmp)))
        try:
            trailing = load_inventory(app(t / "good2", good))["widgets"]["name"]
        except (Unusable, KeyError):
            trailing = None
        check_("CONTROL: a trailing comment is still a comment", trailing == {"category": "none"}, repr(trailing))

        # A SECOND DATABASE'S SCHEMA (#1695): `schema_dump: observability_schema.rb` dumps to db/observability_schema.rb.
        second = ('ActiveRecord::Schema[8.1].define(version: 2026_10_08_120000) do\n'
                  '  create_table "error_groups", force: :cascade do |t|\n'
                  '    t.string "message", default: "", null: false\n'
                  '    t.string "public_id", null: false\n'
                  '  end\n'
                  'end\n')
        both = good + ("error_groups:\n"
                       "  message:\n    category: free_text\n    basis: legitimate interest\n    retention: 90 days\n"
                       "  public_id: { category: none }\n")
        extra = {"observability_schema.rb": second}
        code, out = check(app(t / "two", both, extra=extra))
        check_("CONTROL: a second schema file's columns, classified, are clean and counted",
               code == 0 and "all 6 column(s)" in out[0] and "3 hold personal data" in out[0], f"{code} {out}")

        code, out = check(app(t / "twogrown", both, extra={"observability_schema.rb": second.replace(
            '    t.string "public_id", null: false\n', '    t.string "public_id", null: false\n    t.string "owner_email"\n')}))
        check_("a new column in the SECOND schema fails until it is classified, and the finding names its file",
               code == 1 and any("[unclassified] error_groups.owner_email (in db/observability_schema.rb)" in l for l in out), f"{code} {out}")

        code, out = check(app(t / "twostale", both + "  gone_column: { category: none }\n", extra=extra))
        check_("a stale column of a second-schema table is a finding naming that file",
               any("[stale-column] error_groups.gone_column" in l and "db/observability_schema.rb" in l for l in out), f"{out}")

        code, out = check(app(t / "twostaletable", both + "ghost_table:\n  x: { category: none }\n", extra=extra))
        check_("an entry for a table in NO schema file is stale, and the finding lists the files it looked in",
               any("[stale-table] ghost_table" in l and "db/observability_schema.rb" in l and "db/schema.rb" in l for l in out), f"{out}")
        check_("a table that lives in the second schema is not stale",
               not any("[stale-table] error_groups" in l for l in check(app(t / "twokeep", both, extra=extra))[1]))

        code, out = check(app(t / "twomissing", good, extra=extra))
        check_("a second schema's tables with no inventory entry at all are unclassified, never skipped",
               code == 1 and any("[unclassified] error_groups.message" in l for l in out), f"{code} {out}")

        def solid(table: str, column: str) -> str:
            return ('ActiveRecord::Schema[8.1].define(version: 1) do\n'
                    f'  create_table "{table}", force: :cascade do |t|\n    t.text "{column}"\n  end\nend\n')

        trio = {"cache_schema.rb": solid("solid_cache_entries", "value"), "queue_schema.rb": solid("solid_queue_jobs", "arguments"),
                "cable_schema.rb": solid("solid_cable_messages", "payload")}
        code, out = check(app(t / "solid", good, extra=trio))
        check_("the Solid trio is framework-owned: a solid_* table in cache_schema.rb, queue_schema.rb or cable_schema.rb is not reported",
               code == 0 and not any("solid_" in l for l in out), f"{code} {out}")
        code, out = check(app(t / "solidone", good, extra={"cache_schema.rb": trio["cache_schema.rb"]}))
        check_("a solid_* table in cache_schema.rb alone is not reported", code == 0, f"{code} {out}")

        # A FILE NAMED LIKE THE TRIO BUT HOLDING THE PROJECT'S OWN TABLE is the project's: the name alone decides nothing.
        own = second.replace("error_groups", "page_cache")
        code, out = check(app(t / "ownnamed", both, extra={"cache_schema.rb": own}))
        check_("a cache_schema.rb holding a non-solid_* table is read, not skipped by its name",
               any("[unclassified] page_cache.message (in db/cache_schema.rb)" in l for l in out), f"{code} {out}")
        mixed = solid("solid_cache_entries", "value").replace("  end\nend\n", '  end\n  create_table "page_cache", force: :cascade do |t|\n    t.string "key"\n  end\nend\n')
        code, out = check(app(t / "mixedtrio", both, extra={"queue_schema.rb": mixed}))
        check_("a Solid-trio file with ONE non-solid_* table is read",
               any("[unclassified] page_cache.key (in db/queue_schema.rb)" in l for l in out), f"{code} {out}")

        code, out = check(app(t / "othername", both, extra={"analytics_schema.rb": second.replace("error_groups", "page_views")}))
        check_("any other db/*_schema.rb is read: an unclassified table in it is a finding",
               any("[unclassified] page_views.message (in db/analytics_schema.rb)" in l for l in out), f"{out}")

        code, out = check(app(t / "dup", both, extra={"observability_schema.rb": second.replace("error_groups", "widgets")}))
        check_("a table in two schema files is a finding, not a silent pick",
               any("[duplicate-table] widgets" in l for l in out), f"{out}")

        # #1732 (a): THE IMPLICIT `id`. Rails adds it unless the table says `id: false`; the dump never lists it as a column, so an
        # inventory that classifies it was read as stale. Allowed when implicit; still stale when the table has no id at all.
        code, out = check(app(t / "listedid", good + "  id: { category: none }\n"))
        check_("a listed implicit id is not stale", code == 0, f"{code} {out}")
        noid = schema.replace('create_table "widgets", force: :cascade do', 'create_table "widgets", id: false, force: :cascade do')
        code, out = check(app(t / "noid", good + "  id: { category: none }\n", noid))
        check_("a listed id on an `id: false` table is still stale",
               code == 1 and any("[stale-column] widgets.id" in l for l in out), f"{code} {out}")
        coded = schema.replace('create_table "widgets", force: :cascade do', 'create_table "widgets", primary_key: "code", force: :cascade do')
        code, out = check(app(t / "pkcode", good + "  id: { category: none }\n", coded))
        check_("a listed id on a table whose primary key is another column is still stale",
               code == 1 and any("[stale-column] widgets.id" in l for l in out), f"{code} {out}")
        code, out = check(app(t / "pkid", good + "  id: { category: none }\n",
                              schema.replace('create_table "widgets", force: :cascade do', 'create_table "widgets", primary_key: "id", force: :cascade do')))
        check_("CONTROL: `primary_key: \"id\"` keeps the implicit id", code == 0, f"{code} {out}")

        # #1732 (b): A SOLID TABLE THE INVENTORY NAMES. The project classified it, so its file is read and the entry judged, not
        # reported as a table in no schema file; a Solid file nobody named is still skipped (the trio fixtures above).
        named = good + "solid_queue_jobs:\n  arguments: { category: none }\n"
        code, out = check(app(t / "namedsolid", named, extra={"queue_schema.rb": trio["queue_schema.rb"]}))
        check_("a Solid table the inventory names is read: its entry is not stale", code == 0, f"{code} {out}")
        code, out = check(app(t / "namedsolidgrown", named, extra={"queue_schema.rb": trio["queue_schema.rb"].replace(
            '    t.text "arguments"\n', '    t.text "arguments"\n    t.string "concurrency_key"\n')}))
        check_("a named Solid table's unlisted columns are not required (the framework's), only its listed entries judged",
               code == 0 and not any("concurrency_key" in l for l in out), f"{code} {out}")
        code, out = check(app(t / "namedsolidstale", named + "  gone_col: { category: none }\n",
                              extra={"queue_schema.rb": trio["queue_schema.rb"]}))
        check_("a listed column a named Solid table no longer has is still stale",
               any("[stale-column] solid_queue_jobs.gone_col" in l for l in out), f"{code} {out}")
        code, out = check(app(t / "namedsolidnocat", good + "solid_queue_jobs:\n  arguments: { basis: x }\n",
                              extra={"queue_schema.rb": trio["queue_schema.rb"]}))
        check_("a named Solid table's entry still needs a category",
               any("[no-category] solid_queue_jobs.arguments" in l for l in out), f"{code} {out}")
        sibling = trio["queue_schema.rb"].replace("  end\nend\n", '  end\n  create_table "solid_queue_processes", force: :cascade do |t|\n'
                                                  '    t.string "hostname"\n  end\nend\n')
        code, out = check(app(t / "namedsibling", named, extra={"queue_schema.rb": sibling}))
        check_("an unnamed Solid table beside a named one stays the framework's: not read at all (5 columns, not 6)",
               code == 0 and "all 5 column(s)" in out[0] and not any("solid_queue_processes" in l for l in out), f"{code} {out}")

        code, out = check(app(t / "nosecond", good))
        check_("CONTROL: a project with only db/schema.rb is judged exactly as before", code == 0, f"{code} {out}")

        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--root", str(t / "missing")])
        check_("main returns the check's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"check_privacy_inventory selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
