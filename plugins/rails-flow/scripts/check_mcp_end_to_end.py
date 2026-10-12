#!/usr/bin/env python3
"""check_mcp_end_to_end.py -- an app with an MCP server has a spec that drives it end to end (#1930, gate 4 of #1885).

A tool whose definition loads in a unit spec can still fail at the transport, the auth or the JSON-RPC layer, and only a spec
that talks to the real endpoint shows it. So when the Gemfile declares the `mcp` gem, the project names that spec in
`.rails-flow/mcp.json` (`{"end_to_end_spec": "spec/requests/mcp/end_to_end_spec.rb"}`), and this check holds the name to:

  * the file exists, under `spec/requests/`, `spec/system/` or `spec/integration/`, or says `type: :request`;
  * it reaches both JSON-RPC methods a client needs, `tools/list` and `tools/call` (MCP specification 2025-06-18 and 2026-07-28;
    `mcp` gem 1.7.0 `lib/mcp/methods.rb`), either literally or through a `spec/support` helper whose body sends it.

Declared, never guessed: a project with the gem and no declaration is a FINDING, because "nobody decided which spec proves the
server works" is not "nothing to check". No `mcp` gem is not applicable. The claude.ai connector check a person runs at
certification is not this gate.

What it cannot see: whether the declared spec PASSES (the suite does that), or a helper reached through another helper.

Exit: 0 clean · 1 findings · 3 not applicable (no `mcp` gem).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DECLARATION = Path(".rails-flow/mcp.json")
MCP_GEM = re.compile(r"""^\s*gem\s+["']mcp["']""", re.M)
METHODS = ("tools/list", "tools/call")
REQUEST_DIRS = ("spec/requests/", "spec/system/", "spec/integration/")
REQUEST_TYPE = re.compile(r"type:\s*:(?:request|system|feature)\b")
DEF = re.compile(r"^\s*def\s+([a-z_][A-Za-z0-9_]*[?!]?)", re.M)


def uses_mcp(root: Path) -> bool:
    gemfile = root / "Gemfile"
    return gemfile.is_file() and bool(MCP_GEM.search(gemfile.read_text(encoding="utf-8", errors="replace")))


def helpers_sending(root: Path) -> dict[str, set[str]]:
    """{method: {helper names}}: a `def` in spec/support whose body (to the next `def`) names the JSON-RPC method."""
    out: dict[str, set[str]] = {m: set() for m in METHODS}
    for f in sorted((root / "spec" / "support").rglob("*.rb")) if (root / "spec" / "support").is_dir() else []:
        text = f.read_text(encoding="utf-8", errors="replace")
        starts = [(m.start(), m.group(1)) for m in DEF.finditer(text)] + [(len(text), "")]
        for (start, name), (end, _) in zip(starts, starts[1:]):
            for method in METHODS:
                if method in text[start:end]:
                    out[method].add(name)
    return out


def check(root: Path) -> tuple[int, list[str]]:
    if not uses_mcp(root):
        return 3, ["n/a: the Gemfile declares no `mcp` gem, so there is no MCP server to drive"]
    decl = root / DECLARATION
    if not decl.is_file():
        return 1, [f"the Gemfile declares the `mcp` gem and {DECLARATION} does not exist: name the spec that drives the server "
                   f'end to end, {{"end_to_end_spec": "spec/requests/mcp/end_to_end_spec.rb"}} (#1930)']
    try:
        rel = json.loads(decl.read_text(encoding="utf-8")).get("end_to_end_spec")
    except (json.JSONDecodeError, AttributeError) as exc:
        return 1, [f"{DECLARATION} is not a JSON object with `end_to_end_spec` ({exc})"]
    if not isinstance(rel, str) or not rel:
        return 1, [f"{DECLARATION} names no `end_to_end_spec`"]
    spec = root / rel
    if not spec.is_file():
        return 1, [f"{DECLARATION} names {rel}, which does not exist"]
    text = spec.read_text(encoding="utf-8", errors="replace")
    findings = []
    if not (rel.startswith(REQUEST_DIRS) or REQUEST_TYPE.search(text)):
        findings.append(f"{rel} is not a request-level spec (under {', '.join(REQUEST_DIRS)} or `type: :request`): "
                        "a unit spec of the tools does not reach the transport or the auth")
    helpers = helpers_sending(root)
    for method in METHODS:
        if method in text or any(re.search(rf"\b{re.escape(h)}\b", text) for h in helpers[method]):
            continue
        findings.append(f"{rel} never reaches `{method}`, literally or through a spec/support helper that sends it")
    return (1 if findings else 0), findings


def selftest() -> int:
    import tempfile
    failures: list[str] = []
    gem = 'source "https://rubygems.org"\ngem "mcp", "= 1.7.0"\n'
    helper = ('module McpFlow\n  def mcp_post(method, token: nil)\n    post "/mcp", params: { method: method }\n  end\n\n'
              '  def call_tool(name, args = {}, token:)\n    mcp_post("tools/call", token:)\n  end\nend\n')
    good = 'RSpec.describe "MCP", type: :request do\n  it { mcp_post("tools/list", token: t); call_tool("x", token: t) }\nend\n'
    decl = '{"end_to_end_spec": "spec/requests/mcp/end_to_end_spec.rb"}'
    E2E = "spec/requests/mcp/end_to_end_spec.rb"

    def run(files: dict[str, str]) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body, encoding="utf-8")
            return check(root)

    base = {"Gemfile": gem, ".rails-flow/mcp.json": decl, "spec/support/mcp_flow.rb": helper, E2E: good}
    for label, files, want in (
        ("no mcp gem is n/a (exit 3), never a pass", {"Gemfile": 'gem "rails"\n'}, 3),
        ("no Gemfile at all is n/a (exit 3)", {}, 3),
        ("a commented-out mcp gem is n/a (exit 3)", {"Gemfile": '# gem "mcp"\n'}, 3),
        ("CONTROL: the reference shape (Retask's) is clean: tools/list literal, tools/call through a helper", base, 0),
        ("the mcp gem with no declaration is a finding, not n/a", {**base, ".rails-flow/mcp.json": None}, 1),
        ("a declaration naming no spec is a finding", {**base, ".rails-flow/mcp.json": "{}"}, 1),
        ("a declaration that is not JSON is a finding", {**base, ".rails-flow/mcp.json": "spec/x"}, 1),
        ("a declared spec that does not exist is a finding", {**base, E2E: None}, 1),
        ("a unit spec (spec/models, no request type) is a finding",
         {**base, ".rails-flow/mcp.json": '{"end_to_end_spec": "spec/models/tools_spec.rb"}',
          "spec/models/tools_spec.rb": 'RSpec.describe "tools" do\n  it { mcp_post("tools/list"); call_tool("x", token: 1) }\nend\n'}, 1),
        ("CONTROL: a spec outside spec/requests that says type: :request is request-level",
         {**base, ".rails-flow/mcp.json": '{"end_to_end_spec": "spec/mcp/e2e_spec.rb"}',
          "spec/mcp/e2e_spec.rb": good}, 0),
        ("a spec that never lists the tools is a finding",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  it { call_tool("x", token: t) }\nend\n'}, 1),
        ("a spec that never calls a tool is a finding",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  it { mcp_post("tools/list") }\nend\n'}, 1),
        ("a helper that does not send tools/call does not count",
         {**base, "spec/support/mcp_flow.rb": helper.replace('mcp_post("tools/call", token:)', "nil")}, 1),
        ("CONTROL: both methods named literally need no helper",
         {**base, "spec/support/mcp_flow.rb": None,
          E2E: 'RSpec.describe "MCP", type: :request do\n  it { post "/mcp", params: { method: "tools/list" }; post "/mcp", params: { method: "tools/call" } }\nend\n'}, 0),
    ):
        code, found = run({k: v for k, v in files.items() if v is not None})
        if code != want:
            failures.append(f"{label}: wanted exit {want}, got {code} {found!r}")
    # The exit code the runner grades, asserted outright (#1873): no `mcp` gem is not applicable.
    if run({"Gemfile": 'gem "rails"\n'})[0] != 3:
        failures.append("no mcp gem must be n/a (exit 3), never a pass and never a finding")
    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_mcp_end_to_end selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
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
        print(line if code == 3 else f"- {line}")
    if code == 0:
        print("check_mcp_end_to_end: the declared spec drives the MCP server end to end")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
