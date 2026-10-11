# The `mcp` gem's tool annotations and tool registration, verified for the gate (#1882, umbrella #1306)

**Verifier.** The real `doctrine-verifier`, run by `claude-skills-a0` on 2026-10-11 against `modelcontextprotocol/ruby-sdk` **v1.6.0 and v1.7.0** (raw `lib/mcp/tool.rb`, `lib/mcp/tool/annotations.rb`, `lib/mcp/server.rb`, README) and the MCP schema. An earlier run by a general-purpose stand-in disagreed with it on two points (below); the verdicts here are the real verifier's. Nothing annotation- or registration-related differs between v1.6.0 and v1.7.0 (`tool.rb` differs only at line 89, icons; `annotations.rb` is byte-identical; `server.rb` only icons and a +5 line drift after about line 186).

## Verdicts

**Claim 1, how a Ruby tool declares annotations. PARTLY REFUTED, corrected.**
- The macro is `def annotations(hash = NOT_SET)` → `@annotations_value = Annotations.new(**hash)` (`tool.rb:121-127`): ONE positional Hash, splatted, not one keyword per hint. `Annotations#initialize(destructive_hint: true, idempotent_hint: false, open_world_hint: true, read_only_hint: false, title: nil)` (`annotations.rb:8`) accepts **five** keys and raises `ArgumentError` on any other. A braceless `annotations(read_only_hint: true)` binds to `hash`.
- `MCP::Tool.define(name:, title:, description:, icons:, input_schema:, output_schema:, meta:, annotations: nil, &block)` (`tool.rb:129`, `self.annotations(annotations) if annotations` at `:138`) and `server.define_tool(…, annotations: nil, meta:, &block)` (`server.rb:297` at v1.6.0, `:302` at v1.7.0) both take `annotations:`.
- `Tool.inherited` (`tool.rb:37-47`) resets `@annotations_value`, so annotations are not inherited (I read this one myself in the first run; a0's run did not contradict it).

**Claim 2, unset defaults and what the gem emits. CONFIRMED.**
- Spec defaults: `readOnlyHint` false, `destructiveHint` true, `idempotentHint` false, `openWorldHint` true, plus `title`. a0 read the **draft** `schema/draft/schema.ts` (`interface ToolAnnotations`, about lines 1912-1954; `LATEST_PROTOCOL_VERSION` "2026-07-28"). I read the **tagged 2025-11-25** schema, `schema/2025-11-25/schema.ts` at tag `2025-11-25`, `interface ToolAnnotations` at line 1178: `readOnlyHint` Default false (line 1187), `destructiveHint` true (1197), `idempotentHint` false (1207), `openWorldHint` true (1217). The same four defaults in both. The gate does not depend on which revision a project targets.
- Gem, nothing declared: `@annotations_value` is nil, `Tool.to_h` (`tool.rb:24-35`) emits `annotations: annotations_value&.to_h` and `.compact` drops it, so `tools/list` omits the key.
- Gem, anything declared: `Annotations#to_h` (`annotations.rb:16-24`) emits all four hints with the gem's defaults, which equal the spec's, and drops only a nil `title`. `annotations(read_only_hint: true)` therefore yields `destructiveHint: true, idempotentHint: false, openWorldHint: true, readOnlyHint: true` (harmless: the spec makes `destructiveHint` meaningful only when `readOnlyHint` is false). **Consequence for the gate: the wire cannot tell "stated" from "defaulted", so the gate reads the source.**
- `server.rb:570-575` (v1.6.0) / `574-580` (v1.7.0) sends annotations only for protocol 2025-03-26 or later.

**Claim 3, how tools are registered, so a static scan can find them. PARTLY CONFIRMED, corrected.**
- Real in both versions: `class X < MCP::Tool` (`inherited`, `tool.rb:37`); `MCP::Tool.define(` (`tool.rb:129`); `.define_tool(` (`server.rb:297`/`:302`); `tools: [` as the `Server.new` keyword (`server.rb:195` v1.6.0 / `:200` v1.7.0, `@tools = tools.to_h { |t| [t.name_value, t] }`).
- **A scan on those four misses:** `Class.new(MCP::Tool)`; `Sub.define(` on a subclass; `tools:` with a non-literal value (`tools: TOOLS`, `tools: Foo.tools`); `server.tools = [...]` and `server.tools << t` (`attr_accessor :tools`, `server.rb:184` v1.6.0 / `:185` v1.7.0; there is no `add_tool` or `register_tool`; read from the code, not run).
- False positive to avoid: another `tools:` keyword at `server.rb:499`/`:523` (v1.6.0), `504`/`:528` (v1.7.0), in an internal method.
- Not read: `lib/mcp/server/transports` and other files.

## What the gate does with it (`plugins/rails-flow/scripts/check_mcp_annotations.py`)

- Requires `read_only_hint` and `open_world_hint` to be **literal keys** of the tool's own `annotations` hash (two of the five).
- Finds `class X < MCP::Tool` and its subclasses, `MCP::Tool.define(` and `Sub.define(`, `.define_tool(`, and `Class.new(MCP::Tool)`. Each has a fixture and a mutant.
- A tool list it cannot read (`tools:` not a literal `[...]`, `server.tools =`, `<<`, `.push`, `.concat`) is **could not check, exit 2**, never a pass. Each has a fixture and a mutant.
- Not claimed: that the declared value is true. A tool that writes while declaring `read_only_hint: true` is the request spec's job (`mcp-server.md` §4).
