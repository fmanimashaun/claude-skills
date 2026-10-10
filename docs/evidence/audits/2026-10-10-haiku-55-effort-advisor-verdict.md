# Verdict for claude-skills #1691 / #1670 (verified live 2026-10-10; no repo file edited)

Sources: MC=https://code.claude.com/docs/en/model-config  SA=https://code.claude.com/docs/en/sub-agents
ADV=https://code.claude.com/docs/en/advisor  ENV=https://code.claude.com/docs/en/env-vars
SET=https://code.claude.com/docs/en/settings-reference  CLI=https://code.claude.com/docs/en/cli-reference
PRC=https://platform.claude.com/docs/en/about-claude/pricing  H55=https://platform.claude.com/docs/en/models/haiku-5-5/overview
MIG=https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide  EFF=https://platform.claude.com/docs/en/build-with-claude/effort
CHG=https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (the source the docs changelog page renders)

## A. haiku alias -> Haiku 5.5 on Anthropic API; 4.5 elsewhere; v2.1.293+  -- CONFIRMED
MC provider table: "| Anthropic API | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 |"; "| Claude Platform on AWS | Opus 5.5 | Sonnet 4.6 | Haiku 4.5 |";
"| Amazon Bedrock, Google Cloud's Agent Platform | Opus 5.5 | Sonnet 4.5 | Haiku 4.5 |"; "| Microsoft Foundry | Opus 4.6 | Sonnet 4.5 | Haiku 4.5 |".
MC: "Use v2.1.293 or later with Haiku 5.5."  CHG v2.1.293 (Oct 7 2026): "Added Claude Haiku 5.5 (`claude-haiku-5-5`), now the default Haiku model on the Anthropic API".
Boundary: v2.1.293. Side effect (MC): a saved Haiku 4.5 session on `haiku` resumes on 5.5. Note Sonnet/Opus rows differ per provider; only record Haiku.

## B. Haiku 5.5 effort levels, default, sub-facts  -- CONFIRMED (each)
- effort low..max, default medium: EFF "Claude Haiku 5.5 supports all five effort levels, and `medium` is the default."; MC table lists Haiku 5.5 with low,medium,high,xhigh,max.
- 1M context / 128K output: H55 "Context window: 1M tokens - Max output: 128K tokens".
- adaptive thinking on by default: H55 "Adaptive thinking is on by default."
- sampling params (NUANCE, issue wording too loose): MIG "If a request includes `temperature`, it must be `1`. If it includes `top_p`, it must be `0.99`... Any other `temperature` or `top_p` value returns a 400 error... So does any `top_k` value, and so does a request that includes both `temperature` and `top_p`." (any top_k = 400.)
- tokenizer: MIG "the same input text produces approximately 30% more tokens on Claude Haiku 5.5 than on Claude Haiku 4.5."
Also: thinking:{type:enabled,budget_tokens} -> 400; assistant prefill -> 400; Priority Tier unsupported (MIG).

## C. Pricing  -- CONFIRMED (PRICING page)
PRC rows: "Claude Haiku 5.5 (for prompts up to 100,000 tokens) | $0.10 / MTok ... $0.50 / MTok"; "(for prompts over 100,000 tokens) | $0.50 / MTok ... $2.50 / MTok"; "Claude Haiku 4.5 | $1 / MTok ... $5 / MTok".
PRC long-context: "Claude Haiku 5.5 is priced by prompt length... A request's prompt length counts all of its input tokens, including cache reads and cache writes." and "Claude 4.6 and later models (except Claude Haiku 5.5)... include the full 1M... at standard pricing" (Haiku 5.5 is the exception; do not write "1M at flat price"). Batch: 5.5 $0.05/$0.25 (<=100k), $0.25/$1.25 (>100k). Cache read $0.01/$0.05. CHG v2.1.293 agrees.

## D. Advisor  -- CONFIRMED (two soft spots)
CLI: "`--advisor <model>` | Enable the server-side advisor tool for this session with a model alias, `fable`, `opus`, or `sonnet`, or a full model ID." ADV: `/advisor opus`, `/advisor off`, settings `advisorModel`; "The advisor tool is experimental and requires the Anthropic API. It is not available on Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, or Microsoft Foundry."
Off-switches: ADV "In a session where a variable that turns flag fetching off is set, such as `DISABLE_TELEMETRY`, the advisor stays off."; ENV DISABLE_TELEMETRY "Also disables feature-flag fetching"; ENV "Features that need feature-flag fetching" lists "Use the advisor tool"; DISABLE_GROWTHBOOK also. ENV CLAUDE_CODE_DISABLE_ADVISOR_TOOL: "`/advisor` command becomes unavailable, any configured `advisorModel` is ignored, and the `--advisor` flag is accepted but has no effect".
Soft spots: (1) "silently" is not a docs word; for DISABLE_ADVISOR_TOOL /advisor is unavailable (not silent). Say "stays off", not "silently". (2) "blocked feature-flag fetches" is inferred from the flag-fetching requirement (no page says "blocked network"); safe wording is "when feature-flag fetching is off".
Versions: /advisor in -p/SDK needs v2.1.260; Fable 5.1 advisor v2.1.257; Haiku 5.5 as main or advisor v2.1.293. --advisor is not listed in `claude --help`. Advisor must rank >= main model; Haiku 4.5 cannot advise; Fable needs Fable access.

## E. Subagent frontmatter effort  -- CONFIRMED
SA: "`effort` | No | Effort level when this subagent is active. Overrides the session effort level, but not the `CLAUDE_CODE_EFFORT_LEVEL` environment variable. Options: `low`, `medium`, `high`, `xhigh`, `max`; available levels depend on the model."
Extra: per-invocation `effort` param overrides the field, "requires Claude Code v2.1.292 or later"; env var wins over both. ENV: CLAUDE_CODE_EFFORT_LEVEL "Takes precedence over `--effort`, `/effort`, and the `modelSettings` and `effortLevel` settings."

## F. CLAUDE_CODE_SUBAGENT_MODEL_FORCE  -- CONFIRMED with a precision fix
ENV: "Set to `1` to force one model onto subagents, teammates, and workflow agents... Requires Claude Code v2.1.257 or later". SA: "To apply one model to every subagent, teammate, and workflow agent, also set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` to `1`."
Fix: it does NOT make Claude Code "ignore model: fields" by itself. SA: "If you set both variables, subagents run on the model in `CLAUDE_CODE_SUBAGENT_MODEL`." "If you set only `..._FORCE`, subagents run on the main conversation's model, except that the built-in Explore subagent runs on the model listed for it under Built-in subagents." CLAUDE_CODE_SUBAGENT_MODEL alone is only a default (ENV: "Before v2.1.251, this variable overrode both the per-invocation model and the definition's `model` field").

## G. CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS  -- CONFIRMED
ENV: "(default: 20). Accepts a positive whole number in plain digits; anything else is ignored, so the variable can adjust the cap but can't disable it. Requires Claude Code v2.1.217 or later". SA: at the limit the Agent tool fails with `Concurrent subagent limit reached`; ultracode sessions exempt.

## H. Explore override and built-in Explore model  -- CONFIRMED
SA: "A user or project subagent named `Explore` overrides the built-in and keeps its own `model` field".
SA built-in Explore: "Model: the main conversation's model. When the main conversation runs Fable... With a Claude subscription, an Anthropic Console account, or an LLM gateway reached through `ANTHROPIC_BASE_URL`, Explore runs on the Opus model that the `opus` alias resolves to. On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, Claude Platform on AWS, or a Claude apps gateway, Explore stays on the main conversation's model."

## I. modelSettings.<model>.effortLevel; top-level effortLevel and Opus 5.5  -- CONFIRMED
SET modelSettings: "Save an effort level for each model you use. Requires Claude Code v2.1.251 or later." effortLevel values "low","medium","high","xhigh" (`max` NOT accepted in either key; maxEffortLevel per-model cap needs v2.1.267). Keys are canonical names e.g. `claude-opus-5-5`.
SET effortLevel: "In your user settings file... this key is the older form `/effort` wrote before it saved levels per model... on Opus 5, Fable 5.1, and earlier models. Opus 5.5 and models released after it ignore it and start at their own default until you save a level for them". "In project, local, and managed settings, and with `--settings`, this key applies to every model." MC says the same. Boundary: user-settings only; Opus 5.5 and later (Haiku 5.5 / Sonnet 5.5 are also "released after" Opus 5.5? MC says "Opus 5.5 and models released after it" - Haiku 5.5 released Oct 7; Opus 5.5 date not checked; do not assert Haiku 5.5 behaviour without that).

## J. (#1670) Effort table in model-config  -- CONFIRMED, Haiku 5.5 IS listed
MC table: "| Opus 5.5, Sonnet 5.5, Haiku 5.5, Opus 5, Sonnet 5, Opus 4.8, and Opus 4.7 | `low`, `medium`, `high`, `xhigh`, `max` |"; "| Fable 5.1 and Fable 5 | low..max |"; "| Opus 4.6 and Sonnet 4.6 | `low`, `medium`, `high`, `max` |". Decisive sentence: "The available effort levels depend on the model. Models not listed here do not support effort:" (page text then shows the table). Fallback: "Claude Code falls back to the highest supported level at or below the one you set. For example, `xhigh` runs as `high` on Opus 4.6." Haiku 4.5 is NOT in the table (does not support effort in Claude Code). Table is exact-as-fetched; Sonnet 4.6 / Opus 4.6 lack xhigh.

## K. --subagents CLI flag  -- REFUTED (not documented; no such flag)
CLI flag table (full) has no `--subagents`. Nearest: `--agents` ("Define custom subagents dynamically via JSON"), `--agent`, `--append-subagent-system-prompt` (v2.1.205), `--append-subagent-system-prompt-file` (v2.1.261), `--forward-subagent-text` (v2.1.211). SA page also has none. Caveat: CLI page says "`claude --help` does not list every flag", so docs absence is strong but not proof; changelog scan covered only first ~100k of 1M chars. Do not add a --subagents flag to doctrine.

## Blockers / notes for editing
1. Fix wording on F (FORCE alone != ignore model fields) and D ("silently", "blocked fetches") and B (sampling: only temperature=1/top_p=0.99 allowed; any top_k = 400).
2. Fable-main Explore->opus is plan/provider-conditional (H); not unconditional.
3. I: top-level effortLevel exclusion is user-settings only and documented for "Opus 5.5 and models released after it".
4. Repo files (model-tiers.md, check_handoff.py, claude-code.json) were NOT read by me; the verdict is on the external claims only. Registry rows still need version pins: v2.1.293 (A,D), v2.1.292 (E), v2.1.257 (F), v2.1.217 (G), v2.1.251 (I), v2.1.260 (D).
