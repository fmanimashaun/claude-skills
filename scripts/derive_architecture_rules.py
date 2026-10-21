#!/usr/bin/env python3
"""Derive design-flow's architecture-rule registry from the framework page that declares it (#2221).

WHY THIS IS AN ARTIFACT AND NOT A RUNTIME READ. The rules live in
`plugins/rails-stack/skills/design-system/references/architecture.md` (rails-stack); the interface
audit that cites them ships in **design-flow**, and a plugin reaches only its own files. So the
registry is COMMITTED beside the audit, at a fixed offset, and this script re-derives it from the
page and fails on any disagreement: the same shape as `derive_mandated_gems.py`. Nothing at runtime
crosses a plugin boundary and there is no second copy to forget.

WHAT IS DERIVED: one entry per rule row, `id`, `layer`, `rule`, `basis` (`check`/`claim`/`decision`),
`ref`, `source`, and `authority`. **`authority` is computed, never written**: a `claim:` basis is a
`standard` (a published standard or pattern, confirmed by `doctrine-verifier`); a `decision:` or a
`check:` basis is a `house` rule. That is the whole point of the registry: the audit takes the
authority of a finding from here, so an agent cannot report a house rule as a standards failure.

Run:  python3 scripts/derive_architecture_rules.py             # write the artifact
      python3 scripts/derive_architecture_rules.py --check     # fail if page and artifact disagree
      python3 scripts/derive_architecture_rules.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_architecture_rules as car  # noqa: E402  (one parser for the table, not two)

OUT = "plugins/design-flow/reference/architecture-rules.json"


class Unusable(Exception):
    pass


def derive(page_text: str) -> list[dict]:
    rules = []
    for line in page_text.splitlines():
        m = car.ROW.match(line)
        if not m:
            continue
        rid, layer, rule, basis, source = m.groups()
        b = car.BASIS.match(basis)
        if not b:
            raise Unusable(f"{rid}: basis {basis!r} is not check:/claim:/decision:; run check_architecture_rules.py")
        kind, ref = b.groups()
        rules.append({"id": rid, "layer": layer, "rule": rule, "basis": kind, "ref": ref, "source": source,
                      "authority": "standard" if kind == "claim" else "house"})
    if not rules:
        raise Unusable("no rule rows were read from the page (a registry of nothing is not a pass)")
    ids = [r["id"] for r in rules]
    if len(set(ids)) != len(ids):
        raise Unusable("duplicate rule ids")
    return rules


def render(rules: list[dict]) -> str:
    return json.dumps({"derived_from": "rails-stack: skills/design-system/references/architecture.md", "rules": rules}, indent=1, ensure_ascii=False) + "\n"


def current() -> str:
    return render(derive((ROOT / car.PAGE).read_text(encoding="utf-8")))


def write() -> int:
    (ROOT / OUT).write_text(current(), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


def disagrees(on_disk: str, derived: str) -> bool:
    return on_disk != derived


def check() -> int:
    path = ROOT / OUT
    if not path.is_file():
        print(f"FAIL: {OUT} does not exist; run scripts/derive_architecture_rules.py")
        return 1
    if disagrees(path.read_text(encoding="utf-8"), current()):
        print(f"FAIL: {OUT} disagrees with {car.PAGE}; run scripts/derive_architecture_rules.py")
        return 1
    print(f"architecture rules registry matches the page ({len(json.loads(path.read_text())['rules'])} rules)")
    return 0


def selftest() -> int:
    page = ("| id | layer | rule | basis | source |\n|---|---|---|---|---|\n"
            "| A1 | shell | one main | claim: C2 | HTML spec |\n"
            "| A2 | shell | skip link | decision: D7 | ours |\n"
            "| A3 | regions | tables | check: scripts/x.py | ours |\n")
    rules = derive(page)
    cases = [
        ("a claim basis derives as a standard", rules[0]["authority"] == "standard"),
        ("a decision basis derives as a house rule", rules[1]["authority"] == "house"),
        ("a check basis derives as a house rule", rules[2]["authority"] == "house"),
        ("every row is read", [r["id"] for r in rules] == ["A1", "A2", "A3"]),
    ]
    for label, doing in (
        ("a page with no rule rows is refused", lambda: derive("no table\n")),
        ("a duplicate id is refused", lambda: derive(page + "| A1 | shell | again | decision: D7 | ours |\n")),
        ("a row with no basis is refused", lambda: derive(page + "| A9 | shell | r | advice | ours |\n")),
    ):
        try:
            doing()
            cases.append((label, False))
        except Unusable:
            cases.append((label, True))
    cases.append(("an artifact that differs from the page is a disagreement", disagrees("a", "b") and not disagrees("a", "a")))
    cases.append(("the real page derives and matches the committed artifact", check() == 0))
    bad = 0
    for label, ok in cases:
        bad += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"derive_architecture_rules selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the artifact and the page disagree")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.selftest:
            return selftest()
        return check() if a.check else write()
    except Unusable as exc:
        print(f"CANNOT DERIVE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
