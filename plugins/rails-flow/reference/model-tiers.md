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
[cc-settings-ref]: https://code.claude.com/docs/en/settings-reference
[cc-advisor]: https://code.claude.com/docs/en/advisor

---

## What the field actually does (verified, and it changes the answer)

Six facts decide this whole document, and four of them contradict the shape #127 proposed.

1. **The default is `inherit`, not a model.** The field accepts *"one of the available aliases:
   `sonnet`, `opus`, `haiku`, or `fable`"*, *"a full model ID such as `claude-opus-5-5`"*, or
   `inherit`, which *"use[s] the same model as the main conversation"* ([cc-agents], re-read 2026-09-25,
   #1326). So an agent with **no** `model:` line already follows the user's session.
2. **A pin is a cap, in both directions.** Resolution is *"1. The per-invocation `model` parameter
   2. The subagent definition's `model` frontmatter, where `inherit` selects the main conversation's
   model 3. The `CLAUDE_CODE_SUBAGENT_MODEL` environment variable, when you set it to a model alias or
   model ID 4. The main conversation's model"* ([cc-agents]). Frontmatter beats the session **and the
   env var**. *"Before v2.1.251, `CLAUDE_CODE_SUBAGENT_MODEL` came first in this order and overrode
   both the per-invocation parameter and the frontmatter, including `model: inherit`"* ([cc-agents]);
   this paragraph quoted that older order until #1326. Pinning `sonnet` on a reviewer means a user who deliberately started an Opus session
   gets a **Sonnet** reviewer — we spent their upgrade for them, downwards.
3. **An alias is not a tier; it is a per-provider lookup that moves over time.** `sonnet` resolves
   to **three different versions** depending on the provider — Sonnet 5 on the Anthropic API,
   **Sonnet 4.6** on Claude Platform on AWS, **Sonnet 4.5** on Amazon Bedrock and Google Cloud's
   Agent Platform *and* on Microsoft Foundry. `opus` is **Opus 5.5** on every one of those
   **except Microsoft Foundry**, where it is **Opus 4.6** ([cc-model], re-read 2026-09-25; it was Opus 5
   when this was first written, which is the point of the next sentence). And *"Aliases point to the
   recommended version for your provider and update over time"* ([cc-model]). A shipped plugin
   cannot know which model its own frontmatter selects.

   Read that table by row, not by group. An earlier version of this paragraph named three providers
   for `sonnet` — correctly, all three are 4.5 — and then attached `opus` **= Opus 4.6** to the same
   group, where two of the three are Opus **5**. The argument was right and the illustration was
   wrong, which is the more dangerous shape: nothing about the conclusion looks off.
4. **Pinning *up* spends the user's money, even when their org blocks it.** *"Claude Code checks the
   per-invocation parameter, frontmatter, and environment variable values against your organization's
   `availableModels` allowlist. For a blocked value, it substitutes another model"*: *"When the blocked
   value is a family alias such as `opus`, Claude Code runs the subagent on the newest version of that
   family the allowlist permits … Before v2.1.222, Claude Code ran the subagent on the inherited model
   for a blocked family alias as well"*, and only *"For any other blocked value, on providers where that
   substitution doesn't operate, or when the allowlist permits no version of the family"* does it fall
   back to the inherited model ([cc-agents], re-read 2026-09-25, #1329). So `model: opus` in a plugin
   we ship runs the most expensive Opus the user's org permits, on our say-so. It is no longer silently
   ignored either: *"In interactive sessions, Claude Code shows a warning naming the requested model and
   the model the subagent runs on"*. This fact said "skips … and runs the subagent on the inherited model
   instead" until #1329, which was true before v2.1.222. The policy it supports is unchanged.
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
| `claim-verifier` | judgement | `inherit` | — |
| `test-runner` | mechanical | `haiku` | `bundle exec rspec` exit status — 0 failures or the gate blocks |
| `design-auditor` | mechanical | `haiku` | the mandated greps must come back empty (`form_with`, `f.label`) |
| `doc-updater` | mechanical | `haiku` | `architecture_graph.py` regenerates and its digest guard fails on drift |
<!-- rails-flow:tiers:end -->

The markers are load-bearing: `check_handoff.py --agents <dir> --tiers <this file>` parses **that**
table and fails when an agent's frontmatter disagrees with it, so this document cannot quietly
become folklore again. A stale row naming an agent that no longer exists fails too.

**`claim-verifier` is `inherit`, and that deserves a sentence because it looks wrong.** Its whole
value is being a *different* model from the one that wrote the change — a second opinion that shares
the author's blind spot is just a slower review. So the obvious move is to pin it to something else.

We do not, for the reason in fact 4 above: pinning a **shipped** agent to an expensive alias spends a
stranger's money on our authority, and since v2.1.222 a blocked `opus` is substituted with the newest
Opus they permit rather than dropped. A pin cannot buy a second opinion here; it can only impose a cost.

So getting one is the **caller's** act — a per-invocation `model`, or `CLAUDE_CODE_SUBAGENT_MODEL` with
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (the env var alone no longer reaches an agent that has a `model:`
line, and every shipped agent has one — see *Session-wide* below) —
and the agent is required to **say which model it ran as**, and to state plainly when that matches the
session, so a reader can tell whether the second opinion was actually second. That is the honest
alternative to a pin that pretends to be free, and it is why the tier vocabulary did **not** need a
third value: the mechanism was never the frontmatter.

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

**No shipped agent sets it, and `check_handoff.py --tiers` refuses one that does (#1326).** This
section first deferred the lever because Claude Code did not say which levels each model accepts. It
now does: its effort table lists Fable, Opus and Sonnet models, and *"Models not listed here do not
support effort"* ([cc-model], re-read 2026-09-25) — Haiku 4.5 is not listed. That settles it:

- The **6 `haiku` agents** cannot take an effort level at all.
- The **23 `inherit` agents** are the judgement agents, and a pin *below* the session is the same cap
  as a model pin: *"Frontmatter effort applies when that skill or subagent is active, overriding the
  session level but not the environment variable"* ([cc-model]). A user who ran `/effort high` for a
  security review would get our `medium`.

So there is no agent in the catalogue the lever fits. Every agent inherits the session's effort,
which on Opus 5.5 is `medium` unless the user chose otherwise ([cc-model]). A project that wants one
agent at another level overrides it in `.claude/agents/`, as below.

### The advisor rides along, and that is the user's call

*"Subagents inherit the configured advisor and apply the same pairing check against their own
model"* ([cc-advisor]), and Haiku 4.5 accepts a Fable, Opus or Sonnet advisor. So with `/advisor`
on, our mechanical agents can consult it too, and *"Each advisor call processes the full transcript
anew"*. There is no per-agent opt-out and *"no setting to cap or force advisor calls"*.

We do **not** tell agents to avoid it. Choosing an advisor is a session decision like choosing a
model, and an instruction baked into a shipped prompt would be another hidden cap on it. The cost is
also small where we could reach it: a subagent's transcript is short, and the long transcripts belong
to the user's own session. The controls are the user's: `/advisor off`, or
`CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` to remove the tool.

## Overriding this in a project (both mechanisms are documented)

**Per agent — a same-named file in `.claude/agents/`.** Plugin agents are the *lowest* priority
scope: managed settings 1, `--agents` 2, `.claude/agents/` **3**, `~/.claude/agents/` 4,
*"Plugin's `agents/` directory … 5 (lowest)"* ([cc-agents]), and *"When multiple subagents share
the same name, Claude Code uses the one from the higher-priority location"*. So a project that
wants `test-runner` on its session model copies the file to `.claude/agents/test-runner.md` and
edits one line. Nothing here is locked.

**Session-wide — two env vars.** `CLAUDE_CODE_SUBAGENT_MODEL` alone is now a *default*: *"a
subagent's definition or a model Claude passes still takes precedence over it"* ([cc-agents]). Every
agent we ship has a `model:` line (`inherit` included), so **on its own it changes none of them**. *"To
apply one model to every subagent … also set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` to `1`. Requires Claude
Code v2.1.257 or later"* ([cc-agents]). `settings.json`'s `env` key is there to *"Set environment variables for
every session and its subprocesses"* ([cc-settings-ref], re-read 2026-09-25, #1328; the description moved
there from the settings page):

```json
{
  "env": { "CLAUDE_CODE_SUBAGENT_MODEL": "haiku", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1" }
}
```

Before v2.1.251 the first variable alone did this; this section said so until #1326, and a user
following it on a current Claude Code got no change and no error.

Say plainly what that does, because it is blunt: it overrides **every** agent's frontmatter, the
three mechanical ones and the seven judgement ones alike. It is the right tool for "this whole
repo is a spike, spend nothing" and the wrong tool for "make one agent cheaper" — that is the
per-agent file above.

## What we declined, and why

- **`model:` on the commands.** Skills and commands take the same field, but *"The override
  applies for the rest of the current turn and isn't saved to settings. The session model resumes
  when you send your next prompt"* ([cc-skills], re-read 2026-09-25, #1328). Pinning `/rails-flow:feature` would seize the model for the
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
