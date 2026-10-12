#!/usr/bin/env python3
"""check_mcp_end_to_end.py -- an app with an MCP server has a spec that drives it end to end (#1930, gate 4 of #1885).

A tool whose definition loads in a unit spec can still fail at the transport, the auth or the JSON-RPC layer, and only a spec
that talks to the real endpoint shows it. So when the Gemfile declares the `mcp` gem, the project names that spec in
`.rails-flow/mcp.json` (`{"end_to_end_spec": "spec/requests/mcp/end_to_end_spec.rb"}`), and this check holds the name to:

  * the file exists inside the project, and is a REQUEST spec: under `spec/requests/` or `type: :request` (a system or
    feature spec drives a browser, not the JSON-RPC endpoint);
  * it reaches both JSON-RPC methods a client needs, `tools/list` and `tools/call` (MCP specification 2025-06-18 and 2026-07-28;
    `mcp` gem 1.7.0 `lib/mcp/methods.rb`), inside a STRING LITERAL in code (comments are stripped first), or by CALLING a
    `spec/support` helper (`name(` or `name ` at the start of a statement) whose body sends it the same way.

Declared, never guessed: a project with the gem and no declaration is a FINDING, because "nobody decided which spec proves the
server works" is not "nothing to check". No `mcp` gem is not applicable. The claude.ai connector check a person runs at
certification is not this gate.

What it cannot see: whether the declared spec PASSES (the suite does that), or a helper reached through another helper.

Exit: 0 clean · 1 findings · 2 could not check (an unreadable Gemfile) · 3 not applicable (no `mcp` gem).
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
REQUEST_DIRS = ("spec/requests/",)
REQUEST_TYPE = re.compile(r"type:\s*:request\b")
DEF = re.compile(r"^\s*def\s+([a-z_][A-Za-z0-9_]*[?!]?)", re.M)


class Unreadable(Exception):
    """The Gemfile exists and could not be read: could not check, exit 2 -- never n/a, never a pass."""


def uses_mcp(root: Path) -> bool:
    gemfile = root / "Gemfile"
    if not gemfile.exists():
        return False
    try:
        return bool(MCP_GEM.search(gemfile.read_text(encoding="utf-8", errors="replace")))
    except OSError as exc:
        raise Unreadable(f"Gemfile could not be read ({exc})") from exc


def code_only(text: str) -> str:
    """Ruby with comment lines and trailing `# ...` removed (a `#` inside a quote is kept). A method named in a comment is no call."""
    out = []
    for line in text.splitlines():
        quote, kept = None, []
        for ch in line:
            if quote:
                kept.append(ch)
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                kept.append(ch)
            elif ch == "#":
                break
            else:
                kept.append(ch)
        out.append("".join(kept))
    return "\n".join(out)


def names_method(code: str, method: str) -> bool:
    """The method inside a string literal: "tools/list" or 'tools/list'."""
    return bool(re.search(rf"""["']{re.escape(method)}["']""", code))


def calls(code: str, name: str) -> bool:
    """A CALL of the helper: `name(` anywhere, or `name ` / `name` at the start of a statement -- not a mention."""
    return bool(re.search(rf"(?<![\w.]){re.escape(name)}\(|(?:^|;)\s*{re.escape(name)}(?:\s|$)", code, re.M))


def helpers_sending(root: Path) -> dict[str, set[str]]:
    """{method: {helper names}}: a `def` in spec/support whose body (to the next `def`) names the JSON-RPC method."""
    out: dict[str, set[str]] = {m: set() for m in METHODS}
    for f in sorted((root / "spec" / "support").rglob("*.rb")) if (root / "spec" / "support").is_dir() else []:
        text = code_only(f.read_text(encoding="utf-8", errors="replace"))
        starts = [(m.start(), m.group(1)) for m in DEF.finditer(text)] + [(len(text), "")]
        for (start, name), (end, _) in zip(starts, starts[1:]):
            for method in METHODS:
                if names_method(text[start:end], method):
                    out[method].add(name)
    return out


def check(root: Path) -> tuple[int, list[str]]:
    try:
        mcp = uses_mcp(root)
    except Unreadable as exc:
        return 2, [f"could not check: {exc}"]
    if not mcp:
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
    spec = (root / rel).resolve()
    if Path(rel).is_absolute() or not spec.is_relative_to(root.resolve()):
        return 1, [f"{DECLARATION} names {rel}, which is outside the project: name a spec under it"]
    if not spec.is_file():
        return 1, [f"{DECLARATION} names {rel}, which does not exist"]
    text = code_only(spec.read_text(encoding="utf-8", errors="replace"))
    findings = []
    if not (rel.startswith(REQUEST_DIRS) or REQUEST_TYPE.search(text)):
        findings.append(f"{rel} is not a request-level spec (under {', '.join(REQUEST_DIRS)} or `type: :request`): "
                        "a unit spec of the tools does not reach the transport or the auth")
    helpers = helpers_sending(root)
    for method in METHODS:
        if names_method(text, method) or any(calls(text, h) for h in helpers[method]):
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
            root = Path(td) / "project"                # a subdirectory, so a `../` path lands somewhere real outside it
            root.mkdir()
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
        # #1934 review: what the gate reads must be a CALL, in CODE, inside the project.
        ("a spec that names both methods only in a comment, with an empty example, is a finding",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  # mcp_post("tools/list"); call_tool("x", token: t)\n  it "works" do\n  end\nend\n'}, 1),
        ("a trailing comment naming a method does not count",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  it { mcp_post("tools/list") } # call_tool("x") sends "tools/call"\nend\n'}, 1),
        ("a method named outside a string literal does not count",
         {**base, "spec/support/mcp_flow.rb": None,
          E2E: 'RSpec.describe "MCP", type: :request do\n  it { tools/list; tools/call }\nend\n'}, 1),
        ("a helper named but not called (a string mentioning it) does not count",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  it { mcp_post("tools/list"); puts "see call_tool docs" }\nend\n'}, 1),
        ("a system spec is not a request spec (a browser, not the endpoint)",
         {**base, ".rails-flow/mcp.json": '{"end_to_end_spec": "spec/system/mcp_spec.rb"}',
          "spec/system/mcp_spec.rb": good.replace("type: :request", "type: :system")}, 1),
        ("a spec path that climbs out of the project is a finding, even to a valid spec",
         {**base, ".rails-flow/mcp.json": '{"end_to_end_spec": "../outside/spec/requests/e2e_spec.rb"}',
          "../outside/spec/requests/e2e_spec.rb": good}, 1),
        ("an absolute spec path is a finding",
         {**base, ".rails-flow/mcp.json": '{"end_to_end_spec": "/etc/passwd"}'}, 1),
        ("CONTROL: a # inside a string literal is not a comment",
         {**base, E2E: 'RSpec.describe "MCP", type: :request do\n  it { mcp_post("tools/list", id: "#1"); call_tool("x", token: t) }\nend\n'}, 0),
        ("CONTROL: both methods named literally need no helper",
         {**base, "spec/support/mcp_flow.rb": None,
          E2E: 'RSpec.describe "MCP", type: :request do\n  it { post "/mcp", params: { method: "tools/list" }; post "/mcp", params: { method: "tools/call" } }\nend\n'}, 0),
    ):
        code, found = run({k: v for k, v in files.items() if v is not None})
        if code != want:
            failures.append(f"{label}: wanted exit {want}, got {code} {found!r}")
    # A Gemfile that exists and cannot be read is could-not-check (exit 2): never n/a, never a crash (#1934 review).
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "Gemfile").mkdir()                 # a directory where the file should be: read_text raises
        if check(Path(td))[0] != 2:
            failures.append("an unreadable Gemfile is could-not-check (exit 2), not n/a and not a crash")
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
