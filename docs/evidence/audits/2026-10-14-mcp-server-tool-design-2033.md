# mcp-server.md: tool design, structured output and testing, verified for #2033 (umbrella #1277)

**Verifier.** An independent `doctrine-verifier`-role read on 2026-10-14, run by `claude-skills-5d` (Retask session f1) and given the agent's rules (`.claude/agents/doctrine-verifier.md`) and the issue's five gaps, plus a0's correction: the Ruby SDK docs page states `mcp` 1.7.0 against the file's 1.6.0 and never mentions revision 2026-07-28. Sources: the MCP spec revision 2026-07-28 (`server/tools`), `schema/2026-07-28/schema.ts`, the Anthropic post of 2025-09-11, the Claude Code MCP docs, the Inspector docs, rubygems.org, and the gem's own source and CHANGELOG at v1.7.0.

## Verdicts, and what the file now says

| Item | Verdict | In the file (section 5 unless noted) |
|---|---|---|
| A1 latest `mcp` is 1.7.0 (2026-10-05), "v1.6.0" is stale | CONFIRMED | section 1: 1.7.0, verified 2026-10-14; the `lib/mcp/client/oauth/` statement re-checked at v1.7.0 (no server-side OAuth code in `lib/`) |
| A2 the gem supports revision 2026-07-28 | CONFIRMED, with a boundary (corrected by a0's review of #2059) | section 1: `LATEST_STABLE_PROTOCOL_VERSION = "2026-07-28"` in `lib/mcp/configuration.rb`. 1.1.0 (2026-08-01) only listed it as the latest (CHANGELOG "Support 2026-07-28 as the Latest Protocol Version (#476)"); 1.2.0 (2026-08-15) "completes the SEP-2575 stateless lifecycle of the 2026-07-28 specification" (per-request envelope #475, sessionless Streamable HTTP #479, `server/discover` #480), so the revision is served statelessly since 1.2.0; the legacy `initialize` handshake still defaults to `2025-03-26` and never negotiates it (the revision is stateless, each request carries its version in `_meta`) |
| B1 descriptions and names, advice | CONFIRMED as advice | "new hire" description, unambiguous argument names, namespacing: *advice* |
| B2 name and `tools/list` order | CONFIRMED, all SHOULD | 1 to 128 characters of `A-Z a-z 0-9 _ - .`, unique per server, deterministic order: SHOULD, never MUST |
| C bounded output | CONFIRMED as advice | pagination, range selection, filtering, truncation with guidance. The literal argument name `response_format` was NOT seen in the fetched text, so the file says "a concise or a detailed response" |
| C Claude Code 25,000-token default | CONFIRMED (official page, undated) | default 25,000, warning above 10,000, `MAX_MCP_OUTPUT_TOKENS`, `anthropic/maxResultSizeChars`; with the page's qualifiers (corrected by a0's review): only a successful result with no image content over the limit is saved to a file; for a tool without its own limit a successful result is saved above 50,000 characters whatever its token count; error text longer than about 11,000 characters keeps its first 5,000 and last 5,000 characters (truncated) |
| D structured output and errors, spec | CONFIRMED | `outputSchema` => server MUST return conforming `structuredContent`; text block SHOULD; `isError: true` for execution errors, JSON-RPC errors for protocol errors; `structuredContent` may be any JSON value |
| D Ruby SDK surface | CONFIRMED | `output_schema`, `structured_content:`, `error: true` (sent as `isError`); `validate_tool_call_results` is OFF by default (opt-in since 0.16.0), so the gem does not enforce the MUST. NOT included: how a raised exception maps to a JSON-RPC error (not traced: INCONCLUSIVE) |
| E annotations | CONFIRMED | `title`, `idempotentHint` (default false); `destructiveHint` and `idempotentHint` meaningful only when `readOnlyHint` is false |
| F1 Inspector CLI in CI | CONFIRMED | `--cli`, `--method tools/list`, `--method tools/call --tool-name --tool-arg`; Node 22.19.0 or newer |
| F2 evaluation step | CONFIRMED | realistic multi-call tasks, verifiable outcomes, refining descriptions, and the metrics sentence, quoted verbatim on a second read (2026-10-14, after a0's review): "we recommend collecting other metrics like the total runtime of individual tool calls and tasks, the total number of tool calls, the total token consumption, and tool errors." |
| F "regression-test descriptions on every change" | not in any official source | stated in the file as this project's advice, with that attribution |

## Registered for re-reading

The Claude Code limit and the over-limit behaviour are four rows in `docs/evidence/upstream/claude-code.json` (`mcp-output-token-limit`, `mcp-output-over-limit-saved-to-file`, `mcp-output-50000-characters`, `mcp-error-text-truncated`), so the weekly re-read names `mcp-server.md` if the page changes; `check_upstream_docs.py --coverage` passes and the live re-read finds all four quotes (its one `quote-gone` is an unrelated, pre-existing row).

## Not claimed

- The exact literal `response_format` as a tool argument name; the mapping of a raised exception to a JSON-RPC error. Each stays out of the file until a source is quoted. (The evaluation-metrics sentence was in this list and is now quoted and in the file.)
- `schema.ts` was read from the `main` branch path for the 2026-07-28 directory, not diffed against a tagged release.
- The Claude Code page was read for its first 100,000 of 122,755 characters; the quoted material was in the part read.

## Our own design decision, kept separate

The owner's ruling on #2034 (relayed by the coordinator, 2026-10-14): MCP doctrine is read-only for now, so write tools are out of scope for now (maintainer ruling, #2034; future work tracked in #2049). The first wording, "until a project needs them", carried a trigger the owner later replaced with their own call on timing (a0's review of #2059). It is a maintainer decision with no upstream, not a framework claim, and section 3 rule 2 now says so.
