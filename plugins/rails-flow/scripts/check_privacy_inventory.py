#!/usr/bin/env python3
"""Every db/schema.rb column is classified in config/privacy_inventory.yml (#1310).

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
  * every column of every `create_table` in db/schema.rb is listed (the implicit `id` key is exempt);
  * `category: none` is an explicit "not personal"; any other category needs `basis` and `retention`;
  * an entry for a table or column that no longer exists is a finding (it would mislead the policy);
  * no inventory at all is a finding that names how many columns are unclassified, never clean.

The schema is read with `build_project_wiki.parse_schema` -- one schema.rb reader, not two.

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


def check(root: Path) -> tuple[int, list[str]]:
    schema_path = root / SCHEMA
    if not schema_path.is_file():
        return 3, [f"not applicable: no {SCHEMA}"]
    tables = parse_schema(schema_path.read_text(encoding="utf-8"))["tables"]
    columns = {(t, c[0]) for t, spec in tables.items() for c in spec["columns"]}
    try:
        inv = load_inventory(root)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    if inv is None:
        return 1, [f"no {INVENTORY}: all {len(columns)} column(s) across {len(tables)} table(s) are "
                   "unclassified. /rails-flow:setup-flow drafts it; each column gets a category, or "
                   "`category: none`."]
    findings = []
    for t, c in sorted(columns):
        entry = inv.get(t, {}).get(c)
        if entry is None:
            findings.append(f"  [unclassified] {t}.{c} -- not in {INVENTORY}")
            continue
        category = entry.get("category", "")
        if not category:
            findings.append(f"  [no-category] {t}.{c} -- every entry needs a category (`none` if not personal)")
        elif category != "none":
            for key in ("basis", "retention"):
                if not entry.get(key):
                    findings.append(f"  [no-{key}] {t}.{c} -- personal ({category}) with no {key}")
    for t, cols in sorted(inv.items()):
        if t not in tables:
            findings.append(f"  [stale-table] {t} -- in {INVENTORY} but not in {SCHEMA}")
            continue
        for c in sorted(cols):
            if (t, c) not in columns:
                findings.append(f"  [stale-column] {t}.{c} -- in {INVENTORY} but not in {SCHEMA}")
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

    def app(tmp: Path, inventory: str | None, schema_text: str = schema) -> Path:
        (tmp / "db").mkdir(parents=True, exist_ok=True)
        (tmp / "db" / "schema.rb").write_text(schema_text, encoding="utf-8")
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

        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--root", str(t / "missing")])
        check_("main returns the check's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"check_privacy_inventory selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
