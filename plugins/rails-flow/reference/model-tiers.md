# Model tiers — which agent runs on which model, and why

This is the decision record behind the `model:` line in every rails-flow agent. It exists because
`#127` found the field being set **accidentally**: seven agents pinned `sonnet`, three pinned
`haiku`, and no document anywhere said why — so we neither saved cost deliberately nor protected
quality deliberately. A field nobody decided is a field nobody can review.

**Everything here about Claude Code's behaviour is quoted from its own documentation**, fetched
**2026-07-31**. That half is externally verifiable and is cited inline. The *policy* built on top —
which of our agents counts as judgement work — is **ours**, recorded on
[#127](https://github.com/fmanimashaun/claude-skills/issues/127).

[cc-agents]: https://code.claude.com/docs/en/sub-agents
[cc-model]: https://code.claude.com/docs/en/model-config
[cc-skills]: https://code.claude.com/docs/en/skills
[cc-settings]: https://code.claude.com/docs/en/settings

---

## What the field actually does (verified, and it changes the answer)

Six facts decide this whole document, and four of them contradict the shape #127 proposed.

1. **The default is `inherit`, not a model.** The field accepts *"`sonnet`, `opus`, `haiku`,
   `fable`, a full model ID (for example, `claude-opus-5`), or `inherit`. Defaults to `inherit`"*
   ([cc-agents]). So an agent with **no** `model:` line already follows the user's session.
2. **A pin is a cap, in both directions.** Resolution is *"1. The `CLAUDE_CODE_SUBAGENT_MODEL`
   environment variable … 2. The per-invocation `model` parameter 3. The subagent definition's
   `model` frontmatter 4. The main conversation's model"* ([cc-agents]). Frontmatter beats the
   session. Pinning `sonnet` on a reviewer means a user who deliberately started an Opus session
   gets a **Sonnet** reviewer — we spent their upgrade for them, downwards.
3. **An alias is not a tier; it is a per-provider lookup that moves over time.** `sonnet` is
   Sonnet 5 on the Anthropic API but **Sonnet 4.5** on Amazon Bedrock, Google Cloud's Agent
   Platform and Microsoft Foundry, where `opus` is **Opus 4.6** ([cc-model]). And *"Aliases point
   to the recommended version for your provider and update over time"* ([cc-model]). A shipped
   plugin cannot know which model its own frontmatter selects.
4. **Pinning *up* mostly buys nothing.** *"Claude Code checks the environment variable,
   per-invocation parameter, and frontmatter values against your organization's `availableModels`
   allowlist. It skips a value that resolves to an excluded model and runs the subagent on the
   inherited model instead"* ([cc-agents]). So `model: opus` in a plugin we ship either spends a
   stranger's money on our say-so, or is silently ignored. Neither is a strategy.
5. **`model` is honoured for plugin agents.** Only three fields are not: *"For security reasons,
   plugin subagents don't support the `hooks`, `mcpServers`, or `permissionMode` frontmatter
   fields"* ([cc-agents]). `model`, `effort`, `maxTurns` and `tools` all apply — so this is a real
   lever, not a no-op.
6. **Claude Code made this exact change to its own built-in agent.** *"As of v2.1.198, Explore
   inherits the main conversation's model instead of always running on Haiku"*, and it is now
   *"capped at Opus on the Claude API, so Explore never runs on a more expensive model than the one
   you already chose for the session"* ([cc-agents]). The platform moved a built-in from a cheap
   pin to inherit-with-a-ceiling. Our seven `sonnet` pins are the pattern it left behind.

**So the axis is not "which model is this agent worth".** It is: *does this agent need whatever
judgement the user is paying for, or is its output proven by something outside itself?*

## The policy (ours)

Two tiers, because two is what the mechanism can express honestly.

- **judgement → `model: inherit`.** The session model is the user's declared ceiling. `inherit`
  tracks it up when they upgrade and never overrides it downward. Anything whose output is a
  *verdict*, a *design*, or code with blast radius lives here.
- **mechanical → `model: haiku`.** Deterministic, tightly constrained work whose result is proven
  by something external — a suite's exit status, a grep that must come back empty, a diff.
  *"Control costs by routing tasks to faster, cheaper models like Haiku"* ([cc-agents]) is the
  documented purpose, and this is the case that fits it.

**The dependency #127 asks us to state plainly:** a mechanical pin is only safe while the proof is
**external to the executor**. Cheap execution against *acceptance criteria the executor cannot
edit* is delegation; cheap execution against its own judgement is a discount on the judgement. That
is why `docs/acceptance/<slug>.md` is a precondition of the work order (`/rails-flow:handoff`) and
not a nicety — and why the mechanical column below has to name the proof for every row.

<!-- rails-flow:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `code-reviewer` | judgement | `inherit` | — |
| `pr-reviewer` | judgement | `inherit` | — |
| `security-auditor` | judgement | `inherit` | — |
| `migration-writer` | judgement | `inherit` | — |
| `rails-developer` | judgement | `inherit` | — |
| `skill-curator` | judgement | `inherit` | — |
| `claude-skills-reporter` | judgement | `inherit` | — |
| `test-runner` | mechanical | `haiku` | `bundle exec rspec` exit status — 0 failures or the gate blocks |
| `design-auditor` | mechanical | `haiku` | the mandated greps must come back empty (`form_with`, `f.label`) |
| `doc-updater` | mechanical | `haiku` | `architecture_graph.py` regenerates and its digest guard fails on drift |
<!-- rails-flow:tiers:end -->

The markers are load-bearing: `check_handoff.py --agents <dir> --tiers <this file>` parses **that**
table and fails when an agent's frontmatter disagrees with it, so this document cannot quietly
become folklore again. A stale row naming an agent that no longer exists fails too.

**Why the three mechanical agents are the only three.** `test-runner` reports a suite it did not
write; `design-auditor` runs greps whose expected result is "empty"; `doc-updater` syncs prose to a
diff and regenerates a digest-guarded graph. Each is graded by something it cannot argue with. The
other seven all end in a judgement — `VERDICT: CLEAN`, a migration's production safety, a
distillation, what belongs in an upstream report — and a wrong judgement there is expensive and
propagates, which is exactly #127's own argument for the strongest tier.

`rails-developer` is the one people will want to move, and #127 proposed exactly that ("mid" tier
for implementation against explicit criteria). It stays on `inherit` because the criteria bound
*what* must be true, not *how much damage the code does on the way there* — tenancy scoping,
callback ownership, N+1s and authorization gaps all pass a green suite. The gates that catch them
(`code-reviewer`, `security-auditor`) are judgement agents; putting the writer below the reviewers
just moves the cost to the review loop.

## The other axis: `effort`, which is where #127's "mid tier" actually lives

#127's three-row table (strongest / mid / cheapest) is right about the *work* and wrong about the
*mechanism*: there is no "mid" model to select, only a different model family per provider. But
Claude Code has a separate dial that does what "mid" means — *"`effort`: Effort level when this
subagent is active. Overrides the session effort level. Default: inherits from session. Options:
`low`, `medium`, `high`, `xhigh`, `max`; available levels depend on the model"* ([cc-agents]).

`effort` composes with `inherit` in a way `model` cannot: it lowers *how hard* an agent thinks
without capping *what* it can be. That is the honest home for "constrained execution, cheaper".

**We do not set it in this pass, deliberately.** *"available levels depend on the model"* and
Claude Code does not publish which levels each model accepts, so we cannot tell what
`effort: low` on a Haiku agent resolves to — or whether it is accepted at all. Shipping an
unverifiable value into ten downstream projects to save tokens is the wrong trade. Recorded here as
the next lever, with the reason it is not pulled yet, so it is a decision rather than an omission.

## Overriding this in a project (both mechanisms are documented)

**Per agent — a same-named file in `.claude/agents/`.** Plugin agents are the *lowest* priority
scope: managed settings 1, `--agents` 2, `.claude/agents/` **3**, `~/.claude/agents/` 4,
*"Plugin's `agents/` directory … 5 (lowest)"* ([cc-agents]), and *"When multiple subagents share
the same name, Claude Code uses the one from the higher-priority location"*. So a project that
wants `test-runner` on its session model copies the file to `.claude/agents/test-runner.md` and
edits one line. Nothing here is locked.

**Session-wide — one env var.** `CLAUDE_CODE_SUBAGENT_MODEL` is *"The model Claude Code uses for
all subagents … and overrides the per-invocation `model` parameter and the subagent definition's
`model` frontmatter. Set to `inherit` to use normal model resolution instead"* ([cc-model]), and
`settings.json`'s `env` holds *"Environment variables applied to every session"* ([cc-settings]):

```json
{
  "env": { "CLAUDE_CODE_SUBAGENT_MODEL": "haiku" }
}
```

Say plainly what that does, because it is blunt: it overrides **every** agent's frontmatter, the
three mechanical ones and the seven judgement ones alike. It is the right tool for "this whole
repo is a spike, spend nothing" and the wrong tool for "make one agent cheaper" — that is the
per-agent file above.

## What we declined, and why

- **`model:` on the commands.** Skills and commands take the same field, but *"The override
  applies for the rest of the current turn and is not saved to settings; the session model resumes
  on your next prompt"* ([cc-skills]). Pinning `/rails-flow:feature` would seize the model for the
  whole orchestration — including every gate — from a user who already chose one. The orchestrator
  is the user's session, by decision.
- **`model: opus` (or `fable`, or `best`) anywhere we ship.** Fact 4: it is either their money on
  our authority, or silently dropped. `inherit` expresses "as good as this user is paying for"
  without either failure.
- **A full model ID.** It pins a version that ages, and `claude-opus-5` is meaningless on Bedrock,
  Google Cloud's Agent Platform, and Microsoft Foundry, which *"use provider-specific deployment
  IDs rather than Anthropic model IDs"* ([cc-model]).
- **A third tier.** The two values the table permits are the two the mechanism can defend. A
  project that wants more forks the table and points the checker at its own copy.

## What this does not cover

**rails-flow's ten agents, and nothing else.** `qa-flow`, `design-flow` and `pipeline` ship their own
agents, and every one of them still pins an alias — so the "a pin is a cap" argument applies to them
verbatim and is *not* yet applied. That is a known gap with its own issue
([#299](https://github.com/fmanimashaun/claude-skills/issues/299)), not an implied exemption:
each plugin resolves its own `${CLAUDE_PLUGIN_ROOT}` and would need its own table, and the same
`check_handoff.py --agents … --tiers …` reconciles it once written.

## What this does not claim

It does not claim a cost saving in numbers. Token pricing, and how much of a run is subagent work,
are the user's provider's business and vary per project; the saving here is *structural* (cheap
where the proof is external, the session's model everywhere else), not measured. Any number would
be invented, and #127 asked for a strategy rather than a benchmark.
