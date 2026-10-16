# Making a product usable by AI agents (MCP and agent-facing CLI) — research, 2026-10-14

> **Evidence, not doctrine.** Read-side research behind #2033, #2035 and #2036: how a product built with this stack lets AI agents use it through an MCP server or an agent-facing CLI. Nothing here is a claim a skill relies on; each source carries its own VERIFIED / SECONDARY / RECALL / NOT FOUND label. Moved on 2026-10-14 from `claude-skills-wt/_logs/agent-ready-research/research-agent-ready.md` (#2061); the text below is unchanged.


Labels: VERIFIED = page read this session (WebFetch, 2026-10-14). SECONDARY = read via search
snippets only (vendor/practitioner blogs, not authoritative). RECALL = training memory, not checked.
MCP spec revision read: 2026-07-28 (the revision our mcp-server.md cites). Some pages say "latest".

## 1. Tool design for agents

Tool selection and shape
- Do not wrap each API endpoint 1:1; build few tools for high-impact workflows, consolidate multi-step
  operations (example: `search_contacts` over `list_contacts`); avoid overlapping tools.
  VERIFIED — https://www.anthropic.com/engineering/writing-tools-for-agents (published 2025-09-11).
- Namespace by service/resource (`asana_search`, `asana_projects_search`); test prefix vs suffix per
  model. VERIFIED — same URL.
- Return high-signal fields (names, not UUIDs/MIME types); resolve cryptic ids to readable terms; offer a
  `response_format` (concise/detailed) param (article's example: ~1/3 the tokens). VERIFIED — same URL.
- Descriptions: write like onboarding a new teammate; make implicit context explicit; unambiguous param
  names (`user_id` not `user`); strict input and output schemas. VERIFIED — same URL.
- Spec naming: tool names SHOULD be 1-128 chars, case-sensitive, only A-Z a-z 0-9 `_` `-` `.`, unique per
  server; clients/proxies may collide on `search`, so prefixing is the client's disambiguation.
  VERIFIED — https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- Servers SHOULD return tools in deterministic order (client cache + LLM prompt-cache hits); tools/list
  MAY vary by the authorization on the request (e.g. only tools the granted scopes permit), MUST NOT vary
  per connection. VERIFIED — same spec URL.

Bounded / paginated output
- Use pagination, range selection, filtering, truncation with sensible defaults; when truncating, tell the
  agent how to narrow the query; Claude Code caps tool responses at 25,000 tokens by default.
  VERIFIED — Anthropic engineering post above. (tools/list itself is paginated by cursor — VERIFIED, spec URL.)

Structured output
- `outputSchema` optional; if given, servers MUST return conforming `structuredContent`, clients SHOULD
  validate; a tool returning structured content SHOULD also return the serialized JSON in a TextContent
  block. VERIFIED — spec tools URL.
- 2026-07-28 allows any JSON value (array, primitive) as structuredContent, not only objects. VERIFIED — same.
- Ruby SDK: `output_schema` helper, `structured_content:` on `MCP::Tool::Response.new`, opt-in server-side
  checking `MCP::Configuration.new(validate_tool_call_results: true)`; error responses are not validated.
  VERIFIED — https://ruby.sdk.modelcontextprotocol.io/server/tools/ (version not stated on page).

Errors agents can act on
- Two channels: protocol errors (unknown tool, malformed request; JSON-RPC error, models rarely recover) vs
  tool execution errors in the result with `isError: true` (validation, business-logic, API failures;
  "actionable feedback ... to self-correct"). Clients SHOULD pass execution errors to the model.
  VERIFIED — spec tools URL. Spec example: "Invalid departure date: must be in the future. Current date is ...".
- Anthropic: say what went wrong, how to fix it, include an example of correct input; no tracebacks/opaque
  codes. VERIFIED — Anthropic post.
- Ruby SDK keyword is `error: true` (reported as `isError`). VERIFIED — Ruby SDK tools page.

Annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, `title`)
- Defaults: readOnly false; destructive true (only meaningful when readOnly false); idempotent false (same);
  openWorld true. "all properties in ToolAnnotations are hints"; "Clients should never make tool use
  decisions based on ToolAnnotations received from untrusted servers." VERIFIED —
  https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2026-07-28/schema.ts
- Spec: "clients MUST consider tool annotations to be untrusted unless they come from trusted servers."
  VERIFIED — spec tools URL. Note this is a client obligation; the hint is metadata, not enforcement.
- Ruby SDK exposes them as `read_only_hint`, `destructive_hint`, `idempotent_hint`, `open_world_hint`,
  `title`; supported from protocol 2025-03-26. VERIFIED — Ruby SDK tools page.

Human in the loop / confirmation / elicitation
- Spec: "there SHOULD always be a human in the loop with the ability to deny tool invocations"; clients
  SHOULD show tool inputs before calling and prompt for confirmation on sensitive operations. VERIFIED —
  spec tools URL (User Interaction Model + Security Considerations).
- Elicitation (2026-07-28): server returns `InputRequiredResult` containing `elicitation/create`; client
  retries `tools/call` with `inputResponses` (+ `requestState`). Response actions accept/decline/cancel.
  Modes: form (flat primitive schema only) and url. VERIFIED —
  https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation and tools page.
- Form mode MUST NOT request passwords, API keys, tokens, payment credentials; use URL mode (data bypasses
  client and LLM). URL mode introduced in 2025-11-25 and flagged "may change". VERIFIED — elicitation URL.
- Servers MUST NOT trust client-supplied user identity; derive it from authorization. VERIFIED — same.
- Caveat: elicitation is optional client capability; a server cannot assume a confirm dialog exists.
  [Inferred from capability declaration text, VERIFIED page; the inference is mine.]
- Confirmation for destructive tools as a server pattern (e.g. dry-run/preview tool + `confirm` arg):
  no primary source found. RECALL / design choice; do not state as best practice.

## 2. Authorization and security for write tools

OAuth resource server (spec 2026-07-28, VERIFIED — https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Authorization is OPTIONAL in the protocol; for HTTP transports implementations SHOULD conform; stdio
  SHOULD NOT use it (credentials from environment).
- MCP server is an OAuth 2.1 resource server; MUST implement RFC 9728 Protected Resource Metadata; AS must
  offer RFC 8414 or OIDC discovery.
- Client registration: Client ID Metadata Documents SHOULD be supported; Dynamic Client Registration is
  now "deprecated and retained for backwards compatibility". (Our file does not mention this.)
- Clients MUST send RFC 8707 `resource`; servers MUST validate the token was issued for them (audience);
  MUST NOT "accept or transit any other tokens"; token on every HTTP request; never in the query string;
  invalid/expired token gets 401.
- Scopes: servers SHOULD put `scope` in `WWW-Authenticate` on 401; runtime insufficient scope SHOULD be
  403 with `error="insufficient_scope"`, `scope=...`, `resource_metadata`; include ALL scopes needed for the
  operation in one challenge; clients do step-up and union scopes; servers MUST honour scope hierarchies.
- RFC 9207 `iss` validation (mix-up defence): AS SHOULD emit `iss`, clients MUST validate; spec says a
  future revision is expected to make AS emission MUST.

Scopes per tool
- Security best practices: progressive least privilege — minimal initial read scope (e.g. `mcp:tools-basic`),
  elevate via targeted `WWW-Authenticate scope` challenges when a privileged tool is first used; common
  mistakes: publishing all scopes, wildcard/omnibus scopes (`*`, `all`, `full-access`), "treating claimed
  scopes in token as sufficient without server-side authorization logic"; log elevation events with
  correlation ids. VERIFIED — https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- The spec describes mechanism, not a scope-per-tool naming scheme. A `reports:read` / `tasks:write` split
  mapped per tool is therefore OUR design (it fits the spec's tools/list-by-scope allowance), not a mandate.

Confused deputy, token passthrough
- Confused deputy (spec sense) concerns MCP PROXY servers fronting a third-party API with a static client id
  + dynamic registration + consent cookie; mitigation: per-client consent registry, exact redirect_uri
  match, state validation, `__Host-` cookies. Token passthrough "MUST NOT accept any tokens that were not
  explicitly issued for the MCP server"; passthrough defeats rate limits and audit trail. VERIFIED —
  security best practices URL. Relevance to a Rails app that is its own AS and calls no third party: mostly
  the audience rule; the proxy attack applies only if the app proxies a third-party OAuth. [Inferred]
- State handles (carts, workflow ids): possession is not authentication; bind to the verified user, random
  ids, expiry. VERIFIED — same URL and spec tools "Stateful Tools" section.

Prompt injection through tool results
- The spec's tool Security Considerations say servers MUST validate inputs, implement access controls, rate
  limit invocations, sanitize outputs; clients SHOULD validate results before the LLM and log tool usage
  for audit. VERIFIED — spec tools URL. It gives no concrete injection mitigation beyond "sanitize".
- Lethal trifecta (private data + untrusted content + external communication): "avoid that lethal trifecta
  combination entirely"; once an agent ingested untrusted input it should be unable to trigger consequential
  actions. VERIFIED — https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ (2025-06-16).
- Applied to us: user-authored text (task titles, comments) returned by a reporting tool is untrusted
  content; a server that also exposes write tools adds the action half. [Inferred]
- Output filtering / guardrail model scanning: SECONDARY only (practical-devsecops, codersera blogs from
  search). No authoritative standard found. Do not cite as doctrine.

Audit log, rate limits
- Rate limiting: spec MUST (above). VERIFIED. Audit: spec says clients SHOULD log; server-side audit is not
  mandated by the spec; token passthrough text says audit trails need server-visible identity. VERIFIED.
  Field list for an audit row (user, tool, args, time, outcome, scopes) is our design.

## 3. Agent-facing CLI conventions; CLI vs MCP

Conventions
- Prompt only when stdin is a TTY; `--no-input` means never prompt and fail naming the flag; no animation
  off-TTY; primary/machine output to stdout, logs and errors to stderr; `--json`; `--plain` for line
  output; exit 0 on success, non-zero on failure with codes mapped to failure modes; `-n/--dry-run`;
  confirmation scaled by severity, `--force` for scripts, `--confirm="name"` for severe actions.
  VERIFIED — https://clig.dev/ (no date/version on page; repo cli-guidelines/cli-guidelines).
- gh: `--json <fields>` + `--jq` + `--template`; omit the field list to see available fields; env
  `GH_PROMPT_DISABLED`, `GH_TOKEN`, `NO_COLOR`, `GH_SPINNER_DISABLED`, `GH_NO_UPDATE_NOTIFIER`. VERIFIED —
  https://cli.github.com/manual/gh_help_formatting and /gh_help_environment (versions not stated).
- Agent-specific extras (stable documented exit codes, `schemaVersion` in JSON, command/schema
  introspection, `--fields`, `--limit/--cursor`, NDJSON, reject unknown flags): SECONDARY — community
  skill pages (layer5.io blog, skills.sh agentic-cli-design). No authoritative standard exists; treat as
  practitioner guidance. Stripe and Vercel CLI patterns: NOT checked; RECALL only, so not asserted.
- MCP Inspector itself has a CLI mode "for CI, shell pipelines, and coding agents" with `--format json`.
  VERIFIED — https://modelcontextprotocol.io/docs/tools/inspector (2026-07-28 docs). Shows the MCP and
  CLI worlds converging on machine-readable CLIs.

CLI vs MCP vs both; one service layer
- No primary source found that states a rule for choosing. The security argument that matters is
  authorization identity: the spec's model gives every HTTP MCP call a per-request token and an
  audience-checked resource server (VERIFIED, above); a CLI run on the server with database access has no
  such token unless it authenticates and calls the same layer. Our #1277 rests on this and is consistent
  with the spec. A CLI that is a thin HTTP/API client with a user token (as gh is) does not bypass
  authorization; that case is NOT addressed in #1277's wording. [Inferred — flag, not fact]
- "One service layer feeding both surfaces" as the accepted pattern: no authoritative source found in
  this session. RECALL: widely practised, and Anthropic's post says tools should be designed for agents
  rather than mirror endpoints (VERIFIED), which argues the shared layer is domain operations (report
  objects), not the controller/API shape. Label this Inferred.

## 4. Discoverability, docs, testing

- llms.txt: a proposal by Jeremy Howard (Answer.AI), published 2024-09-03, modified 2026-08-10; Markdown
  file at `/llms.txt` (H1, blockquote summary, H2 link lists, "Optional" section), companion `.md` versions
  of pages. "Not a formal standard", informal proposal. VERIFIED — https://llmstxt.org/
  The MCP docs themselves publish https://modelcontextprotocol.io/llms.txt (each fetched page says so). VERIFIED.
  Whether AI crawlers/agents actually read llms.txt: not measured; do not claim.
- AGENTS.md: open Markdown format for coding-agent instructions, stewarded by the Agentic AI Foundation
  (Linux Foundation); suggests overview, build/test commands, code style, testing, security, PR conventions;
  nested files, closest wins. VERIFIED — https://agents.md/ . It targets agents working IN a repo, not
  agents USING a deployed product; for the latter it is an analogy only. [Inferred]
- OpenAPI as agent doc: RECALL only (not fetched). Not asserted.
- Testing an MCP server:
  - MCP Inspector (web, CLI, TUI; Node 22.19+; `--cli --method tools/list`, `tools/call`) for protocol-level
    checks and CI scripts. VERIFIED — Inspector URL above.
  - Evals: Anthropic's 6-step process — prototype, realistic multi-call tasks, verifiable outcomes, simple
    agent loop, track accuracy/runtime/tool-call count/tokens/errors, iterate with held-out set. VERIFIED —
    Anthropic post. Redundant calls signal pagination/limit problems (same).
  - Vendor guidance (Braintrust and others): deterministic tests + reviewed schema snapshots every commit;
    model-based evals when tool names/descriptions change. SECONDARY only (search snippets).
- Ruby SDK doc pages read did not cover testing; README fetch (github) failed once, raw README gave no
  testing/annotation/revision details. SDK version this session: NOT established (our file says 1.6.0,
  2026-09-24; not re-verified here).

## Gaps vs skills/rails-8/references/mcp-server.md

Read the file first (96 lines). It is reporting-only, read-only first, #1277. Compared with what was
verified above:

1. Write tools are deferred ("a separate, later decision") — no doctrine at all. Missing: per-tool scopes
   with `insufficient_scope` step-up (spec VERIFIED), `destructiveHint`/`idempotentHint` guidance, a
   confirmation pattern, an audit field list for writes, the trifecta rule when a tool returns untrusted
   user text. This is the biggest gap and needs OUR maintainer decision, not a framework claim.
2. Prompt injection through results is absent. Reporting tools return user-authored strings (titles,
   comments); spec says sanitize outputs; trifecta source above. Add a rule: aggregates and display
   numbers by default is already rule 5; extend to "free text is untrusted and never makes a tool call
   decision".
3. Tool-design guidance beyond "one tool per report, typed args" is missing: descriptions as onboarding
   text, namespacing, concise/detailed `response_format`, bounded/paginated results with a truncation hint,
   result caps (25k token default in Claude Code), deterministic tool order.
4. `outputSchema` / `structuredContent` and the `isError` channel are not mentioned. Spec: MUST conform if
   declared; also return JSON as text. Ruby SDK has `output_schema`, `error: true`, opt-in
   `validate_tool_call_results`. Error text should say what to change, with an example.
5. Auth section: dated points to add/refresh — Client ID Metadata Documents preferred and DCR deprecated
   (2026-07-28 spec); `scope` in `WWW-Authenticate` and 403 `insufficient_scope`; RFC 9207 `iss`; tools/list
   MAY vary by scope. Our file's MUSTs (RFC 9728, audience, no passthrough, auth every request) all match
   the spec text read today. No contradiction found in what the file asserts about the spec.
6. Annotations: file is correct on defaults and the untrusted rule (both match schema.ts and tools page).
   Add: `idempotentHint` and `title`, and that the hints only matter when `readOnlyHint` is false.
7. Elicitation, rate limiting (spec MUST on servers), and an explicit rate-limit proof are not in the file
   or its "Proving it" list. Rate limiting is a MUST that our test list does not cover.
8. CLI decision #1277 is stated as "a CLI bypasses authorization". Accurate for a server-side runner; but a
   CLI that is a thin client of the HTTP API with the user's token (gh model) does not. Wording is narrower
   than the claim; no source found that a CLI-vs-MCP rule exists, so keep it as our decision.
9. Discoverability for agents (llms.txt for product docs, AGENTS.md-style product notes) is absent;
   llms.txt is only a proposal (not standard) — at most `advice`, never a guarantee.
10. Testing: "Proving it" is security-only. Missing: MCP Inspector CLI in CI, and an eval step (realistic
    multi-call tasks, verifiable outcomes, tool-call count/token tracking) when tool names or descriptions
    change. Eval method is Anthropic-sourced (VERIFIED); description-change regression advice is vendor
    SECONDARY.
11. Not re-verified this session: `mcp` gem v1.6.0 and Doorkeeper 6.0.0.beta statements in the file (out of
    scope here); Streamable HTTP transport page and the claude.ai connectors help page.

Not found / unresolved: authoritative source for "CLI vs MCP vs both"; for Stripe/Vercel agent-CLI patterns;
for OpenAPI-as-agent-doc; for server-side confirmation pattern for destructive MCP tools.
