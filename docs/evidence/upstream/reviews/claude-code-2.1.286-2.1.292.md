# Claude Code upstream review: 2.1.286 to 2.1.292

_Reviewed 2026-10-07 for #1622 · CLI 2.1.292 · no `[quote-gone]` rows._

**Scope, stated exactly.** `scripts/check_upstream_docs.py` listed **292** unreviewed entries past 2.1.285 (40 + 53 + 44 + 13 + 91 + 1 + 50 for 2.1.286 to 2.1.292). All 292 were read. About 50 touch something our doctrine quotes or relies on (hooks, plugin mods, agents and models, skills and rules, MCP, marketplace install, permissions, settings). Each of those was checked against our files and the current docs in five buckets, by read-only verifiers applying `.claude/agents/doctrine-verifier.md`. The rest are terminal, desktop, VS Code, cloud, Claude Tag and agents-view UI, screen-reader and telemetry items that no shipped file names.

**Result.** 3 issues filed, no doctrine edited:

| issue | finding |
|---|---|
| #1665 | `setup-flow.md` and `claude_md_structure.py` say a `paths:` rule loads only on Read; since 2.1.288 Write and Edit load it too (CONFIRMED against the memory page). |
| #1666 | `model-tiers.md:179` misquotes the advisor page ("cannot" for "can't"); found while checking the 2.1.287 advisor-pairing entry. |
| #1670 | `check_handoff.py:69-71` and `model-tiers.md:156-161` contradict each other on whether per-model effort levels are published; found while checking the 2.1.292 Agent-tool `effort` entry. |

**Checked, no effect on what we ship or say** (each ran a grep or the CLI; the evidence is in the verifier reports):
- Hooks (2.1.286 to 2.1.292): PreToolUse matching failure now blocks (our guards only block; the only "does not block" statement is about exit codes other than 2, still true); async Stop hook with a spaced path (every command is `bash "${CLAUDE_PLUGIN_ROOT}/..."`, enforced by `check_hook_commands.py`); `asyncRewake`, `updatedInput`, `idle_prompt`, `InstructionsLoaded`, `<system-reminder>` escaping (none used or emitted). All six `hook-*` registry quotes still verbatim.
- Plugin mods: `claude plugin validate plugins/rails-flow --json` and the marketplace root are clean on 2.1.292; `claude plugin test` is 12 pass, 0 fail; the one gating hook (`prompt.submit`) has no `.catch` by design (fail-open nudge). Two `mods-*` rows differ from the page only in markdown backticks.
- Agents and models: the new Agent-tool `effort` parameter is not yet in the docs (no precedence claim added; re-check next release); `permissionMode: auto`, the 256-character name limit, agent-team spawn by name, advisor pairings (Sonnet 5.5 can advise Opus 4.7/4.8; our text relies only on the Haiku row), effort after a fallback.
- Skills and commands: control characters and CRLF in `!` blocks (none), skill name vs folder (identical), `disable-model-invocation` leaks (more true now), the `verify` commit guidance (applies to project and user skills only; our `verify` is a plugin command).
- MCP and install: stdio protocol negotiation default (2.1.292) touches the two stdio servers in `.mcp.json` (`chrome-devtools-mcp`, `@playwright/mcp`); worst case is one slow first connect, remembered for 7 days; no claim of ours. Marketplace sources are local paths, so the npm-source refusal does not apply.
- Settings: `CLAUDE_CODE_SUBAGENT_MODEL(_FORCE)` in `model-tiers.md` are model-selection variables, not on the list project settings cannot set.

**Contradiction filed.** `check_handoff.py:69-71` says Claude Code does not publish per-model effort levels while `model-tiers.md:156-161` says it does (filed as #1670; it predates 2.1.292 and is not from a CHANGELOG entry).

**Open points.** The Agent-tool `effort` parameter (2.1.292) is not in the docs yet, so no precedence claim was added. **[Inferred], not CLI-verified:** the 2.1.290 entries that make `rg` and `git grep` with wildcard arguments prompt need no change from us. The tracked `.claude/settings.json` has no `rg`, `ps` or `pyright` rule; the only `Bash(rg:*)` is in the inert `.claude/settings.example.json`; and the 2.1.290 entry concerns the built-in read-only command set, which the permissions page calls "not configurable".
