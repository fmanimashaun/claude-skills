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

## 1. What the platform gives you (verified 2026-09-24, MCP spec revision 2026-07-28)

- **The official Ruby SDK is the `mcp` gem** (v1.6.0, [modelcontextprotocol/ruby-sdk][sdk]). It
  serves tools, prompts and resources, over stdio or **Streamable HTTP**, "including mounted inside a
  Rails application". The mount is shown in the repo's `examples/rails` and in the
  [SDK docs][sdk-docs], so follow those rather than a tutorial.
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
- **Say which scope is missing.** The `401`'s `WWW-Authenticate` **SHOULD** carry `scope` (RFC 6750 §3).
  A token whose scope is too narrow for the call it makes **SHOULD** get `403 Forbidden` with
  `error="insufficient_scope"`, the `scope` the operation needs and `resource_metadata`
  (`error_description` is optional), so the client can step up rather than start over.
- **`tools/list` follows the token, never the connection.** The set **MAY** vary by the authorization
  presented on the request (only the tools the granted scopes permit), and **MUST NOT** vary
  per-connection or as a side effect of other requests on the connection ([tools][spec-tools]; new in
  2026-07-28, which removed protocol-level sessions).

**Registering clients, and the mix-up defence** (both new in 2026-07-28, [changelog][spec-changelog]), for
the authorization server, whether that is the app or an identity provider in front of it:

- Clients are identified by **OAuth Client ID Metadata Documents**, which authorization servers and
  clients **SHOULD** support. Dynamic Client Registration (RFC 7591) is now a **MAY**: deprecated and
  kept only for authorization servers that lack Client ID Metadata Documents. It is not removed, and a
  deprecated feature keeps a twelve-month window.
- **RFC 9207 `iss`.** The authorization server **SHOULD** include `iss` in authorization responses,
  error responses included, and one that does **MUST** advertise it with
  `authorization_response_iss_parameter_supported: true`. A client **MUST** validate a present `iss`
  against the issuer it recorded (RFC 9207 §2.4) before sending the code to any token endpoint. A
  missing `iss` is rejected only where the metadata advertised it. The spec expects a future revision to
  make the server's `iss` a **MUST**, so emit it now.

So the agent is **never** a shared API key that sees everything. It holds a token for one person, and
that person's permissions are the ceiling.

**The gem does not do this part for you.** The `mcp` gem's OAuth support is **client-side only**:
everything is under `lib/mcp/client/oauth/` at v1.6.0. It covers the case where your code is the
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
   nothing. The guarantee is that no tool's code path writes. Write tools are a separate, later
   decision.
3. **One tool per report, with typed arguments**, for example `overdue_tasks_by_team(period:)`. No
   query language, no SQL, and no "run this scope". A tool's arguments are the only thing an agent
   controls, so they are validated like form params.
4. **Every call is audited**: who asked, which tool, which arguments, and when. The audit is how you
   answer "which agent saw this, for whom".
5. **Tool calls are rate limited, and tool output is sanitized: both are the spec's MUSTs, not ours.**
   Servers **MUST** rate limit tool invocations and **MUST** sanitize tool outputs ([tools][spec-tools],
   Security Considerations, with "validate all tool inputs" and "implement proper access controls").
   Key the limiter by the **token's user**, not the address, for the reason and the `:null_store` trap in
   `auth-security.md`'s "Rate limiting, and a trap". Sanitizing matters most for a read tool that returns
   text people typed (titles, comments). The spec names no concrete mitigation beyond the MUST, so how
   far to go for write tools is decision #2034's, not this file's.
6. **Sensitive data is excluded by default.** Results carry aggregates and display numbers
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
- **Over the limit, a call is refused:** one user's calls past the tool limit get the refusal. Control: the
  same user's first call, under the limit, succeeds, and another user's call at the same moment
  succeeds, so the limiter is keyed per user and not globally.

[sdk]: https://github.com/modelcontextprotocol/ruby-sdk
[sdk-docs]: https://ruby.sdk.modelcontextprotocol.io/server/transports/
[spec-transport]: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
[spec-auth]: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
[spec-tools]: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
[spec-changelog]: https://modelcontextprotocol.io/specification/2026-07-28/changelog
[connectors]: https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp
