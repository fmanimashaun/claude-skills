#!/usr/bin/env python3
"""check_mcp_personal_fields.py -- no MCP tool result carries a personal category it was not allowed (#1931, gate 3 of #1885).

Read from DECLARATIONS, never from a run (coordinator's decision on #1931: deterministic, and it needs no app booted). The
convention is the app's, generalised from Retask; it is not `mcp` gem API (gem 1.7.0 has `MCP::Tool.output_schema` and nothing
naming sources):

  * a TOOL is every class-form MCP tool check_mcp_annotations.py finds (under `app/` or `lib/`, inheriting `MCP::Tool`
    directly or through an app class), named by its `tool_name` or, as `mcp` 1.7.0 names it when there is none, by its class
    name demodulized and underscored (`lib/mcp/tool.rb` `name_value`, `string_utils.rb` `handle_from_class_name`). The one
    class not judged is an ABSTRACT BASE: the parent of another tool, with no `tool_name` and no `sources`. A tool
    built by `MCP::Tool.define`, `define_tool` or `Class.new(MCP::Tool)` cannot carry a `sources` declaration here, so each
    is a finding of its own rather than silently unjudged;
  * its own file declares what its result is built from: `sources: %w[table.column ...]` or `sources: ["table.column", ...]`.
    `count(...)` carries no row value and is skipped; `derived(...)` is skipped on the AUTHOR'S WORD that what it returns is
    not a row value -- the gate does not read inside it. A bare `table.column` reaches the result, and so does
    `sum(...)`, `avg(...)`, `min(...)` or `max(...)` of one: those are held to the inner column's category.

Each tool is held to `config/privacy_inventory.yml` (read by check_privacy_inventory.py's own reader):
  1. a tool that declares no `sources` is a finding -- an undeclared tool can return anything;
  2. a `table.column` the inventory does not list, or lists with no category, is a finding -- a column with no category cannot
     be shown safe;
  3. a `table.column` whose category is not `none` is a finding, unless `.rails-flow/mcp.json` allows it for that tool, by
     category or by the column alone (#1940): `{"allow": {"<tool_name>": ["<category>" | "<table.column>", ...]}}`. A column
     entry admits that one column, so one `work_record` column can be returned without admitting the whole category.

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
import check_mcp_annotations as annotations  # noqa: E402  one definition of "what is an MCP tool class", not two

DECLARATION = Path(".rails-flow/mcp.json")
MCP_GEM = re.compile(r"""^\s*gem\s+["']mcp["']""", re.M)
TOOL_NAME = re.compile(r"^\s*tool_name\s*\(?\s*[\"'](?P<name>[^\"']+)[\"']", re.M)
SOURCES_W = re.compile(r"sources:\s*%w\[(?P<body>[^\]]*)\]")
SOURCES_A = re.compile(r"sources:\s*\[(?P<body>[^\]]*)\]")
COLUMN = re.compile(r"\A[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\Z")
# An aggregate that RETURNS a value derived from the column (a sum of one person's pay is their pay when the group is one).
VALUE_AGGREGATE = re.compile(r"\A(?:sum|avg|min|max)\((?P<col>[^()]+)\)\Z")


class CouldNotCheck(Exception):
    pass


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


def gem_name(class_name: str) -> str:
    """The name mcp 1.7.0 gives a tool with no `tool_name`: StringUtils.handle_from_class_name (demodulize, then underscore)."""
    word = class_name.split("::")[-1]
    word = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", word)
    word = re.sub(r"(?<=[a-z\d])(?=[A-Z])", "_", word)
    return word.replace("-", "_").lower()


def unjudged_forms(root: Path) -> list[str]:
    """One line per tool built by `define`, `define_tool` or `Class.new(MCP::Tool)`: it has no class body to declare sources in."""
    try:
        parsed = annotations._parsed(root)
    except annotations.Unusable as exc:
        raise CouldNotCheck(str(exc)) from exc
    tools_set, _bases = annotations._tool_names(parsed)
    out = []
    for path, text, _lines in parsed:
        rel = path.relative_to(root)
        for m in annotations.CALL.finditer(text):
            if m["recv"] and not annotations._is_tool(m["recv"], tools_set):
                continue
            out.append(f"{rel}:{annotations._line_of(text, m.start())}: a tool built by {m.group(0).strip('( ')} declares no "
                       "`sources` a gate can read; define it as a class with `sources:` so its result can be held to the inventory")
        for m in annotations.CLASS_NEW.finditer(text):
            if annotations._is_tool(m["base"], tools_set):
                out.append(f"{rel}:{annotations._line_of(text, m.start())}: a tool built by Class.new({m['base']}) declares no "
                           "`sources` a gate can read; define it as a named class with `sources:`")
    return out


def tools(root: Path) -> list[tuple[str, Path, list[str]]]:
    """[(name, file, [source tokens])] for EVERY concrete class-form MCP tool check_mcp_annotations.class_tools returns, named
    by its `tool_name` or, failing that, as the gem names it (gem_name). None is skipped: a tool with no `tool_name` is served."""
    try:
        found = annotations.class_tools(root)
    except annotations.Unusable as exc:
        raise CouldNotCheck(str(exc)) from exc
    # A PARENT of another tool that names itself nowhere and declares nothing is an abstract base (Retask's Mcp::Tools::Report,
    # which defines a template `call` but is not in the served list): not judged. A leaf with no tool_name IS judged.
    parents = {annotations.CLASS.match(body.splitlines()[0])["base"].split("::")[-1] for _p, _l, _n, body in found}
    out = []
    for path, _line, class_name, body in found:
        code = code_only(body)
        tn = TOOL_NAME.search(code)
        if not tn and class_name.split("::")[-1] in parents and not (SOURCES_W.search(code) or SOURCES_A.search(code)):
            continue
        tokens: list[str] = []
        for m in SOURCES_W.finditer(code):
            tokens += m.group("body").split()
        for m in SOURCES_A.finditer(code):
            tokens += re.findall(r"""["']([^"']+)["']""", m.group("body"))
        out.append((tn.group("name") if tn else gem_name(class_name), path, tokens))
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
            # an allow-list it cannot read is could-not-check, never a traceback and never a silent string-of-characters (#1941 review)
            if not isinstance(allow, dict) or not all(isinstance(v, list) and all(isinstance(e, str) for e in v) for v in allow.values()):
                raise CouldNotCheck(f'{DECLARATION}: `allow` must map each tool to a list of strings, {{"tool": ["category" | "table.column"]}}')
        found_tools = tools(root)
        unjudged = unjudged_forms(root)
    except CouldNotCheck as exc:
        return 2, [f"could not check: {exc}"]
    findings = list(unjudged)
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
            if not category:
                findings.append(f"{name} ({rel}): {tok} is in {INVENTORY} with no category, so it cannot be shown safe")
                continue
            # #1940: an entry shaped `table.column` admits that column alone; any other entry is a category.
            if category != "none" and category not in allowed and f"{table}.{column}" not in allowed:
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
        # #1940: a column entry admits that column, and only that column.
        ("CONTROL: a column entry admits that personal column",
         {**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": '{"allow": {"countries": ["users.email_address"]}}'}, 0),
        ("a column entry admits ONLY that column, not another of the same category",
         {**base, "config/privacy_inventory.yml": inv.replace("  id: { category: none }", "  id: { category: none }\n  phone: { category: contact }"),
          T: tool("countries", "%w[users.email_address users.phone]"), ".rails-flow/mcp.json": '{"allow": {"countries": ["users.email_address"]}}'}, 1),
        ("a column entry for ANOTHER tool does not cover this one",
         {**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": '{"allow": {"other": ["users.email_address"]}}'}, 1),
        ("CONTROL: a category entry still admits the whole category",
         {**base, "config/privacy_inventory.yml": inv.replace("  id: { category: none }", "  id: { category: none }\n  phone: { category: contact }"),
          T: tool("countries", "%w[users.email_address users.phone]"), ".rails-flow/mcp.json": '{"allow": {"countries": ["contact"]}}'}, 0),
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
        ("CONTROL: a trailing comment's sources are not a declaration",
         {**base, T: 'class Countries < Mcp::Report\n  tool_name "countries"\n  fields("a" => { sources: %w[requests.country] }) # was sources: %w[users.email_address]\nend\n'}, 0),
        # #1935 review: a tool with no tool_name is served under its class name, so it is judged too.
        ("a tool with no tool_name returning a personal column is a finding",
         {**base, T: 'class Countries < Mcp::Report\n  fields("a" => { sources: %w[users.email_address] })\nend\n'}, 1),
        ("CONTROL: a tool with no tool_name returning only none columns is clean",
         {**base, T: 'class Countries < Mcp::Report\n  fields("a" => { sources: %w[requests.country] })\nend\n'}, 0),
        ("CONTROL: the allow-list names a tool with no tool_name as the gem does (ClientCost -> client_cost)",
         {**base, T: 'class ClientCost < Mcp::Report\n  fields("a" => { sources: %w[users.email_address] })\nend\n',
          ".rails-flow/mcp.json": '{"allow": {"client_cost": ["contact"]}}'}, 0),
        ("CONTROL: an abstract base (parent of a tool, no tool_name, no sources) is not judged",
         {**base, "app/models/mcp/report.rb": 'module Mcp\n  class Report < MCP::Tool\n    def self.call(**) = nil\n  end\nend\n'}, 0),
        ("a tool built by MCP::Tool.define is a finding (no sources a gate can read)",
         {**base, "app/models/defined.rb": 'Lookup = MCP::Tool.define(name: "lookup", description: "x") { |**| nil }\n'}, 1),
        ("a tool built by Class.new(MCP::Tool) is a finding",
         {**base, "app/models/anon.rb": 'ANON = Class.new(MCP::Tool) do\n  tool_name "anon"\nend\n'}, 1),
        ("an inventory entry with no category is a finding",
         {**base, "config/privacy_inventory.yml": inv + "  kind: { basis: contract }\n", T: tool("countries", "%w[requests.kind]")}, 1),
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
    # A malformed allow-list is could-not-check (exit 2), not a crash and not a quiet string of characters (#1941 review).
    for bad in ('{"allow": {"countries": [["users.email_address"]]}}', '{"allow": {"countries": null}}',
                '{"allow": {"countries": "users.email_address"}}', '{"allow": ["countries"]}'):
        try:
            got = run({**base, T: tool("countries", "%w[users.email_address]"), ".rails-flow/mcp.json": bad})[0]
        except Exception as exc:  # noqa: BLE001  a traceback is the defect this row exists for
            got = f"crashed: {exc!r}"
        if got != 2:
            failures.append(f"a malformed allow-list {bad} is could-not-check (exit 2), got {got}")
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
