# model-tiers.md refresh: doctrine-verifier verdicts (#1681)

Verified 2026-10-10 by `doctrine-verifier` against the live pages. Every row below is a framework claim; only CONFIRMED rows were
written into `plugins/rails-flow/reference/model-tiers.md`. The sub-agents and model-config fetches were truncated at 100,000
characters (the sub-agents tail was read separately and held nothing relevant; the model-config tail was not read, and C2 and C8 do
not depend on it).

| # | Claim | Verdict | Source and version boundary | Written into model-tiers.md |
|---|---|---|---|---|
| C1 | Explore uses the main conversation's model; on Fable it runs on the `opus` alias with a subscription, Console or LLM gateway, and stays on the main model on Bedrock, Google Cloud, Foundry, Claude Platform on AWS and a Claude apps gateway | CONFIRMED | sub-agents, Explore "Model" entry; no version | Yes, fact 6 (today's wording) |
| C2 | Opus 5.5, Sonnet 5.5 and Haiku 5.5 default to `medium` effort | CONFIRMED | model-config; Sonnet 5.5 needs v2.1.284+, Opus 5.5 v2.1.280+ | Already stated by an earlier edit; not re-added |
| C3 | `omitClaudeMd` frontmatter field | CONFIRMED | sub-agents; v2.1.271+ | Yes, as an unused lever |
| C4 | `/tasks` names a subagent's model and its effort when set | CONFIRMED | sub-agents; v2.1.242+ | Yes, as an unused lever |
| C5 | A subagent can spawn subagents, up to three layers by default | CONFIRMED | sub-agents; the default moved across v2.1.172 to v2.1.219 | Yes, as an unused lever (default only; the history is not claimed) |
| C6 | `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` applies one model to every subagent, teammate and workflow agent | CONFIRMED | sub-agents; v2.1.257+ | Already stated; not re-added |
| C7 | A workflow script can name `model` / `effort` per `agent()` and `meta.phases[].model` | **INCONCLUSIVE, leaning REFUTED for the option names** | workflows documents only "A model the script names for a stage counts as the per-invocation model"; no option names | **No.** Only the quoted sentence is used, and the section says the option names are not claimed |
| C8 | Switching model or effort mid-session costs a cache miss | CONFIRMED with a qualification: a model switch always does; an effort change does on most models, NOT on Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.1 with an API key or subscription | prompt-caching (https://code.claude.com/docs/en/prompt-caching); effort exemption from v2.1.260 for Fable 5.1 | Yes, with the qualification and the exceptions; "every effort change costs a miss" is explicitly not taught |
| C9 | Workflow agents share a prompt cache when model, effort, agent type, tools, output schema and working directory all match | CONFIRMED | workflows, "Prompt caching in a fan-out"; no version | Yes |

Our own design claim added alongside (not a framework claim): nothing in rails-flow switches the session's model or effort part-way.
Measured 2026-10-10: `grep -rln "^model:\|^effort:" plugins/*/commands skills .claude/commands` returns nothing.

Decisions recorded on the issues (coordinator, owner-delegated tooling choice, 2026-10-10): #1681 comment 6101546360 (decline
`effort: high`; `doctrine-verifier` to `inherit`), #1819 comment 6101546613 (a new `adversary` agent on Fable; it must run and be
recorded on risky diffs, a BLOCKED verdict is a finding for the human).
