section: rails-flow
- **A gate that every MCP tool declares `read_only_hint` and `open_world_hint` — `plugins/rails-flow/scripts/check_mcp_annotations.py`** (#1882, umbrella #1306).
  Unset, the 2026-07-28 schema's defaults describe a destructive, open-world tool, and the `mcp` gem emits all four hints with those
  defaults once any one is declared, so the check reads the Ruby source (`class X < MCP::Tool`, `MCP::Tool.define`, `Sub.define`, `define_tool`,
  `Class.new(MCP::Tool)`) rather than the wire. Annotations are not inherited, so each concrete tool states its own. A tool list it cannot read
  (`tools:` not a literal list, `server.tools =`, `<<`) exits 2, never a pass. Registered as the `mcp-annotations` check in `plugins/rails-flow/checks.json`.
  Verified by the real `doctrine-verifier` against ruby-sdk v1.6.0 and v1.7.0 and the schema defaults at the draft and the tagged 2025-11-25:
  `docs/evidence/audits/2026-10-11-mcp-annotations-gate-1882.md`. Gates 3 and 4 of #1306 wait on a built MCP instance (#1885).
