# An MCP server for agents (reporting)

People now ask an agent for a report instead of opening a dashboard: *"how many tasks are overdue
this month, by team?"* An app that answers that should expose an **MCP server over HTTP**, the way
Atlassian exposes Jira and Confluence to claude.ai connectors. This file states what that server
must guarantee. How you build it is up to you.

**Why MCP, and not a CLI (#1277).** Any MCP client can reach an HTTP MCP server: claude.ai custom
connectors, Claude Code, other agent frameworks. Each connects **as its own signed-in user**, so the
app's authorization applies to every call. A CLI reaches only people with a shell on the server, and
it runs with database access, so it bypasses that authorization. Maintainers already have
`bin/rails runner`. Put the queries in **report objects under `app/models`** and have the MCP tools
call them, so a CLI could be a thin client of the same layer later if a real need appears.

## 1. What the platform gives you (verified 2026-09-24, MCP spec revision 2026-07-28; the `mcp` gem re-verified 2026-10-14)

- **The official Ruby SDK is the `mcp` gem** (1.7.0, released 2026-10-05, [modelcontextprotocol/ruby-sdk][sdk];
  verified 2026-10-14 on rubygems.org). It
  serves tools, prompts and resources, over stdio or **Streamable HTTP**, "including mounted inside a
  Rails application". The mount is shown in the repo's `examples/rails` and in the
  [SDK docs][sdk-docs], so follow those rather than a tutorial.
- **The gem supports spec revision 2026-07-28**, and serves it statelessly since 1.2.0 (verified 2026-10-14 in the CHANGELOG
  and in `lib/mcp/configuration.rb` at v1.7.0: `LATEST_STABLE_PROTOCOL_VERSION = "2026-07-28"`). 1.1.0 (2026-08-01) only listed
  it as the latest; 1.2.0 (2026-08-15) "completes the SEP-2575 stateless lifecycle of the 2026-07-28 specification": the
  per-request envelope, sessionless Streamable HTTP and `server/discover`. The SDK docs page does not say so; the source does.
  One boundary: the legacy `initialize` handshake still defaults to `2025-03-26` and never negotiates `2026-07-28`, which is
  the stateless revision where each request carries its own version in `_meta`; a client reaches it through `server/discover`
  and that per-request envelope, not through the handshake.
- **Use Streamable HTTP.** The older HTTP+SSE transport is deprecated since protocol `2025-03-26`,
  and the spec says new implementations SHOULD NOT adopt it ([transports][spec-transport]).
- **claude.ai custom connectors** reach a remote MCP server over the internet, with OAuth, on Free,
  Pro, Max, Team and Enterprise plans ([Anthropic help][connectors]).

## 2. Authorization is the spec's, and it is not optional

The MCP server is an **OAuth 2.1 resource server** ([authorization][spec-auth]):

- It **MUST** publish OAuth 2.0 Protected Resource Metadata (RFC 9728), so a client can discover
  which authorization server to use. That server may be the app itself or a separate entity.
- It **MUST** accept only tokens issued for itself, and reject a token whose audience is not this
  server.
- It **MUST NOT** pass the client's token through to another service.
- Authorization **MUST** be on every HTTP request, not remembered from an earlier one.

So the agent is **never** a shared API key that sees everything. It holds a token for one person, and
that person's permissions are the ceiling.

**The gem does not do this part for you.** The `mcp` gem's OAuth support is **client-side only**:
everything is under `lib/mcp/client/oauth/` at v1.7.0 (verified 2026-10-14: no server-side OAuth code in `lib/`). It covers the case where your code is the
client of someone else's protected server. When the app is the server, the app writes, for example as
Rack middleware in front of the mount:
- the validation of the incoming bearer token, including its audience;
- the Protected Resource Metadata route;
- the `401` with its `WWW-Authenticate` challenge.

**If the app is also the authorization server**, note that Doorkeeper's support for RFC 8707 resource
indicators (tokens bound to one audience) and RFC 8414 server metadata exists only in its 6.0.0
pre-releases (`6.0.0.beta1` onwards; the latest stable is 5.9.9). On 5.9.x the audience binding is
yours to write, or the tokens come from an external identity provider.

## 3. Our rules (maintainer decision, #1277)

1. **The agent acts as a real signed-in user.** Every tool call resolves the token to a user and runs
   through the same authorization and tenant scoping as a web request (`multi-tenancy.md`). A tool
   that would show a person something the web app would not show them is the defect.
2. **Read-only first, enforced by the server.** Reporting tools read; they never write. **Set the
   annotations explicitly, because the defaults describe the opposite tool.** Unset, a tool is
   `readOnlyHint: false`, `destructiveHint: true` and `openWorldHint: true` (the 2026-07-28 schema's
   `ToolAnnotations`). A reporting tool therefore declares `readOnlyHint: true` and
   `openWorldHint: false`. Do not rely on either: the rails-flow `mcp-annotations` check fails a tool
   whose source does not state both (it reads the source, because the gem emits all four hints once any
   one is set). The spec says clients **MUST** treat tool
   annotations as untrusted ([tools][spec-tools]), so the hint describes the tool and guarantees
   nothing. The guarantee is that no tool's code path writes. **Write tools are out of scope for
   now** (maintainer ruling, #2034; future work tracked in #2049); this file covers reporting (read-only) tools.
3. **One tool per report, with typed arguments**, for example `overdue_tasks_by_team(period:)`. No
   query language, no SQL, and no "run this scope". A tool's arguments are the only thing an agent
   controls, so they are validated like form params.
4. **Every call is audited**: who asked, which tool, which arguments, and when. The audit is how you
   answer "which agent saw this, for whom".
5. **Sensitive data is excluded by default.** Results carry aggregates and display numbers
   (`TSK-0001`, `models.md` §12), each a link to the record. A category the app marks sensitive (for
   example Retask's enrollee data) reaches a result only from a tool explicitly allowed to return it,
   and that allowance is recorded in the project's CLAUDE.md.

## 4. Proving it

Request specs against the MCP endpoint, each paired with a control that succeeds:

- **No token → 401**, and a token issued for another audience → rejected. Control: a valid token
  succeeds.
- **Another tenant's user** calling the same tool gets only their own tenant's numbers. Control: the
  first user's numbers are non-zero, so an empty answer is not a vacuous pass.
- **A user without the web permission** for a report cannot run its tool.
- **Every call writes one audit row** naming the user, tool and arguments.
- **No tool writes:** run every registered tool and assert that no table's row count changed.
- **A sensitive field is absent** from every tool's result unless that tool is on the allow-list.

## 5. Designing the tools for an agent, and testing them (verified 2026-10-14)

Sections 3 and 4 say what the server must guarantee. This one is about whether an agent uses the tools well. Each rule
names its source; a rule marked *advice* is vendor guidance, not a requirement of the spec.

**Descriptions and names**

- Describe a tool as you would to a new hire on your team, name arguments unambiguously (`user_id`, not `user`), and
  consider namespacing tool names by service (`asana_search`). *Advice* ([Anthropic, 2025-09-11][anthropic-tools]).
- The spec (revision 2026-07-28, [tools][spec-tools]): tool names **SHOULD** be 1 to 128 characters of `A-Z a-z 0-9 _ - .`,
  and **SHOULD** be unique within a server; servers **SHOULD** return `tools/list` in a deterministic order (the same
  across requests while the set is unchanged), so clients can cache it and prompt caches hit. All three are SHOULD, not MUST.

**Bounded output**

- Bound what a tool returns: pagination, range selection, filtering or truncation, and when you truncate, tell the agent
  how to narrow the request. Letting the agent pick a concise or a detailed response is one way. *Advice* (the Anthropic post).
- Claude Code limits an MCP tool's output to 25,000 tokens by default and warns above 10,000. `MAX_MCP_OUTPUT_TOKENS` raises
  it, and a tool can set its own with `anthropic/maxResultSizeChars`. What happens past the limit depends on the result: a
  **successful result with no image content** over the token limit is saved to a file and replaced in the conversation by
  its path, and for a tool without its own limit that result is saved once it is longer than 50,000 characters, whatever its
  token count; **error text** longer than about 11,000 characters keeps only its first 5,000 and last 5,000 characters, so it
  is truncated, not saved ([Claude Code MCP docs][cc-mcp], read 2026-10-14, an undated page). So the server bounds its own
  output, errors included.

**Structured output and errors**

- A tool that declares `outputSchema`: the server **MUST** return `structuredContent` that conforms to it, and clients
  **SHOULD** validate it; a tool that returns structured content **SHOULD** also return the serialized JSON in a text block.
  In this revision `structuredContent` may be any JSON value, not only an object ([tools][spec-tools]).
- Report a tool's *execution* failure (an invalid argument, an upstream API failure, a business rule) in the result with
  `isError: true`, with feedback the model can use to correct itself and retry. *Protocol* errors (an unknown tool, a malformed
  request) are JSON-RPC errors, a separate channel ([tools][spec-tools]).
- In the Ruby SDK (`mcp` 1.7.0, [SDK tools page][sdk-tools]): `output_schema`, `structured_content:` and `error: true` (sent
  as `isError`). **`validate_tool_call_results` is off by default** (opt-in since 0.16.0), so the gem does not enforce the
  MUST above unless the app turns it on.

**Annotations beyond the two this file requires (§3 rule 2)**

- `ToolAnnotations` also has `title` and `idempotentHint` (default `false`). `destructiveHint` and `idempotentHint` are
  meaningful only when `readOnlyHint` is `false`, so a read-only reporting tool needs neither. All of them are hints
  ([schema.ts, 2026-07-28][schema-ts]).

**Testing**

- Beyond section 4: run MCP Inspector's CLI mode in CI, `npx @modelcontextprotocol/inspector --cli <server> --method tools/list`,
  and `--method tools/call --tool-name <name> --tool-arg key=value` ([Inspector docs][inspector]; it needs Node 22.19.0 or
  newer, per the page read 2026-10-14).
- When a tool's name or description changes, run an evaluation: realistic tasks that need several tool calls, each paired
  with a verifiable outcome, recording the total runtime of individual tool calls and tasks, the total number of tool calls, the total token consumption and tool errors, and refine the descriptions from what it shows.
  *Advice* (the Anthropic post). Re-running it on every description change is this project's advice; no official source states it.

[sdk]: https://github.com/modelcontextprotocol/ruby-sdk
[sdk-docs]: https://ruby.sdk.modelcontextprotocol.io/server/transports/
[spec-transport]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
[spec-auth]: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
[spec-tools]: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
[sdk-tools]: https://ruby.sdk.modelcontextprotocol.io/server/tools/
[schema-ts]: https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2026-07-28/schema.ts
[anthropic-tools]: https://www.anthropic.com/engineering/writing-tools-for-agents
[cc-mcp]: https://code.claude.com/docs/en/mcp
[inspector]: https://modelcontextprotocol.io/docs/tools/inspector
[connectors]: https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp
