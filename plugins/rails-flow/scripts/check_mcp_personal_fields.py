#!/usr/bin/env python3
"""check_mcp_personal_fields.py -- no MCP tool result carries a personal category it was not allowed (#1931, gate 3 of #1885).

Read from DECLARATIONS, never from a run (coordinator's decision on #1931: deterministic, and it needs no app booted). The
convention is the app's, generalised from Retask; it is not `mcp` gem API (gem 1.7.0 has `MCP::Tool.output_schema` and nothing
naming sources):

  * a TOOL is a Ruby class under `app/` that inherits `MCP::Tool`, directly or through an app class that does, and calls
    `tool_name`;
  * its own file declares what its result is built from: `sources: %w[table.column ...]` or `sources: ["table.column", ...]`.
    `count(...)` and `derived(...)` carry no row value and are skipped. A bare `table.column` reaches the result, and so does
    `sum(...)`, `avg(...)`, `min(...)` or `max(...)` of one: those are held to the inner column's category.

Each tool is held to `config/privacy_inventory.yml` (read by check_privacy_inventory.py's own reader):
  1. a tool that declares no `sources` is a finding -- an undeclared tool can return anything;
  2. a `table.column` the inventory does not list is a finding -- a column with no category cannot be shown safe;
  3. a `table.column` whose category is not `none` is a finding, unless `.rails-flow/mcp.json` allows that category for that
     tool: `{"allow": {"<tool_name>": ["<category>", ...]}}`.

What it cannot see: whether `sources` tells the truth about what the code returns; the app's own spec holds that half.

Exit: 0 clean · 1 findings · 2 could not check (an unreadable Gemfile, inventory or declaration) · 3 not applicable (no `mcp`
gem, or no privacy inventory).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_privacy_inventory import INVENTORY, Unusable, load_inventory  # noqa: E402  one inventory reader, not two

DECLARATION = Path(".rails-flow/mcp.json")
MCP_GEM = re.compile(r"""^\s*gem\s+["']mcp["']""", re.M)
CLASS = re.compile(r"^\s*class\s+(?P<name>[A-Z][\w:]*)\s*<\s*(?P<parent>(?:::)?[A-Z][\w:]*)", re.M)
TOOL_NAME = re.compile(r"^\s*tool_name\s*\(?\s*[\"'](?P<name>[^\"']+)[\"']", re.M)
SOURCES_W = re.compile(r"sources:\s*%w\[(?P<body>[^\]]*)\]")
SOURCES_A = re.compile(r"sources:\s*\[(?P<body>[^\]]*)\]")
COLUMN = re.compile(r"\A[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\Z")
# An aggregate that RETURNS a value derived from the column (a sum of one person's pay is their pay when the group is one).
VALUE_AGGREGATE = re.compile(r"\A(?:sum|avg|min|max)\((?P<col>[^()]+)\)\Z")
GEM_BASE = "MCP::Tool"


class CouldNotCheck(Exception):
    pass


def _short(const: str) -> str:
    return const.removeprefix("::")


def code_only(text: str) -> str:
    """Ruby without comment lines, trailing `# ...` and `=begin ... =end` blocks: a commented-out `sources:` declares nothing."""
    out, block = [], False
    for line in text.splitlines():
        if block or line.startswith("=begin"):
            block = not line.startswith("=end")
            continue
        quote, kept = None, []
        for ch in line:
            if quote:
                kept.append(ch)
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                kept.append(ch)
            elif ch == "#" and not (kept and kept[-1] == "%"):
                break
            else:
                kept.append(ch)
        out.append("".join(kept))
    return "\n".join(out)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CouldNotCheck(f"{path.name} could not be read ({exc})") from exc


def tools(root: Path) -> list[tuple[str, Path, list[str]]]:
    """[(tool_name, file, [source tokens])] for every class under app/ that reaches MCP::Tool and calls `tool_name`."""
    classes: dict[str, tuple[str, Path, str]] = {}            # short name -> (parent, file, code)
    for f in sorted((root / "app").rglob("*.rb")) if (root / "app").is_dir() else []:
        code = code_only(_read(f))
        for m in CLASS.finditer(code):
            name = _short(m.group("name")).split("::")[-1]
            classes[name] = (_short(m.group("parent")), f, code)

    def reaches_gem(name: str, seen: frozenset = frozenset()) -> bool:
        parent = classes[name][0]
        if parent == GEM_BASE:
            return True
        short = parent.split("::")[-1]
        return short in classes and short not in seen and reaches_gem(short, seen | {name})

    out = []
    for name, (_parent, f, code) in sorted(classes.items()):
        tn = TOOL_NAME.search(code)
        if not tn or not reaches_gem(name):
            continue
        tokens: list[str] = []
        for m in SOURCES_W.finditer(code):
            tokens += m.group("body").split()
        for m in SOURCES_A.finditer(code):
            tokens += re.findall(r"""["']([^"']+)["']""", m.group("body"))
        out.append((tn.group("name"), f, tokens))
    return out


def check(root: Path) -> tuple[int, list[str]]:
    gemfile = root / "Gemfile"
    try:
        if not (gemfile.exists() and MCP_GEM.search(_read(gemfile))):
            return 3, ["n/a: the Gemfile declares no `mcp` gem, so there are no MCP tools"]
        try:
            inventory = load_inventory(root)
        except (Unusable, OSError) as exc:
            raise CouldNotCheck(f"{INVENTORY} could not be read ({exc})") from exc
        if inventory is None:
            return 3, [f"n/a: no {INVENTORY}; the privacy-inventory gate asks for it, and this gate has nothing to hold tools to"]
        allow: dict = {}
        if (root / DECLARATION).is_file():
            try:
                allow = json.loads(_read(root / DECLARATION)).get("allow", {}) or {}
            except (json.JSONDecodeError, AttributeError) as exc:
                raise CouldNotCheck(f"{DECLARATION} is not a JSON object ({exc})") from exc
        found_tools = tools(root)
    except CouldNotCheck as exc:
        return 2, [f"could not check: {exc}"]
    findings = []
    for name, f, tokens in found_tools:
        rel = f.relative_to(root)
        if not tokens:
            findings.append(f"{name} ({rel}) declares no `sources`: an undeclared tool can return any column")
            continue
        allowed = set(allow.get(name, []))
        for tok in tokens:
            if tok.startswith(("count(", "derived(")):
                continue
            agg = VALUE_AGGREGATE.match(tok)
            if agg:
                tok = agg.group("col")
            if not COLUMN.match(tok):
                findings.append(f"{name} ({rel}): source `{tok}` is not `table.column`, an aggregate of one, count(...) or derived(...)")
                continue
            table, column = tok.split(".")
            entry = inventory.get(table, {}).get(column)
            if entry is None:
                findings.append(f"{name} ({rel}): {tok} is not in {INVENTORY}, so its category is unknown")
                continue
            category = entry.get("category", "")
            if category and category != "none" and category not in allowed:
                findings.append(f"{name} ({rel}): {tok} is `{category}`; allow it for this tool in {DECLARATION} "
                                f'({{"allow": {{"{name}": ["{category}"]}}}}) or stop returning it')
    findings = list(dict.fromkeys(findings))          # one line per tool and column, however many fields read it
    return (1 if findings else 0), findings


def selftest() -> int:
    import tempfile
    failures: list[str] = []
    gem = 'gem "mcp", "= 1.7.0"\n'
    inv = ("users:\n  email_address: { category: contact }\n  id: { category: none }\n"
           "requests:\n  country: { category: none }\n")
    base_tool = 'module Mcp\n  class Report < MCP::Tool\n  end\nend\n'

    def tool(name: str, sources: str) -> str:
        return f'module Mcp\n  class {name.title().replace("_", "")} < Report\n    tool_name "{name}"\n    fields("a" => {{ sources: {sources} }})\n  end\nend\n'

    def run(files: dict[str, str | None]) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, body in files.items():
                if body is None:
                    continue
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body, encoding="utf-8")
            return check(root)

    base = {"Gemfile": gem, "config/privacy_inventory.yml": inv, "app/models/mcp/report.rb": base_tool,
            "app/models/mcp/tools/countries.rb": tool("countries", "%w[requests.country count(users.id)]")}
    T = "app/models/mcp/tools/countries.rb"
    for label, files, want in (
        ("no mcp gem is n/a (exit 3), never a pass", {"Gemfile": 'gem "rails"\n'}, 3),
        ("no privacy inventory is n/a (exit 3)", {**base, "config/privacy_inventory.yml": None}, 3),
        ("CONTROL: a tool returning only `none` columns and aggregates is clean", base, 0),
        ("CONTROL: the array form of sources is read too", {**base, T: tool("countries", '["requests.country"]')}, 0),
        ("a tool returning a personal column is a finding", {**base, T: tool("countries", "%w[users.email_address]")}, 1),
        ("CONTROL: the personal column, allow-listed for that tool and category, is clean",
         {**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": '{"allow": {"countries": ["contact"]}}'}, 0),
        ("an allow-list for ANOTHER tool does not cover this one",
         {**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": '{"allow": {"other": ["contact"]}}'}, 1),
        ("an allow-list for another CATEGORY does not cover this one",
         {**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": '{"allow": {"countries": ["health"]}}'}, 1),
        ("a tool that declares no sources is a finding",
         {**base, T: 'class Countries < Mcp::Report\n  tool_name "countries"\nend\n'}, 1),
        ("a commented-out sources line declares nothing",
         {**base, T: 'class Countries < Mcp::Report\n  tool_name "countries"\n  # fields("a" => { sources: %w[requests.country] })\nend\n'}, 1),
        ("a sum of a personal column is held to that column's category", {**base, T: tool("countries", "%w[sum(users.email_address)]")}, 1),
        ("CONTROL: a sum of a `none` column is clean", {**base, T: tool("countries", "%w[sum(requests.country)]")}, 0),
        ("a column the inventory does not list is a finding", {**base, T: tool("countries", "%w[requests.secret]")}, 1),
        ("a source that is not table.column is a finding", {**base, T: tool("countries", "%w[country]")}, 1),
        ("CONTROL: a class that is not a tool (no MCP::Tool ancestor) is not checked",
         {**base, "app/models/other.rb": 'class Other < ApplicationRecord\n  tool_name "x"\nend\n'}, 0),
        ("CONTROL: a direct MCP::Tool subclass is a tool",
         {**base, "app/models/direct.rb": 'class Direct < ::MCP::Tool\n  tool_name "direct"\n  fields("a" => { sources: %w[requests.country] })\nend\n'}, 0),
        ("a direct MCP::Tool subclass with a personal column is a finding",
         {**base, "app/models/direct.rb": 'class Direct < ::MCP::Tool\n  tool_name "direct"\n  fields("a" => { sources: %w[users.email_address] })\nend\n'}, 1),
    ):
        code, found = run(files)
        if code != want:
            failures.append(f"{label}: wanted exit {want}, got {code} {found!r}")
    # The exit codes the runner grades, asserted outright (#1873).
    if run({"Gemfile": 'gem "rails"\n'})[0] != 3:
        failures.append("no mcp gem must be n/a (exit 3), never a pass and never a finding")
    if run({**base, "config/privacy_inventory.yml": None})[0] != 3:
        failures.append("no privacy inventory must be n/a (exit 3): nothing to hold the tools to")
    if run({**base, ".rails-flow/mcp.json": "not json"})[0] != 2:
        failures.append("a declaration that is not JSON is could-not-check (exit 2), never a pass")
    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_mcp_personal_fields selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="the project root (default: the current directory)")
    ap.add_argument("--selftest", action="store_true", help="prove each rule fires and stays silent")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, found = check(Path(a.root))
    for line in found:
        print(line if code in (2, 3) else f"- {line}")
    if code == 0:
        print("check_mcp_personal_fields: every MCP tool's declared sources are none, aggregates, or allowed")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
