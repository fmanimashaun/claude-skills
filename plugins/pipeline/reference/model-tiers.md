# Model tiers — which pipeline agent runs on what, and why

**A `model:` pin is a cap, so we only pin where something outside the agent grades its output.**
Everything else inherits the session model the user deliberately chose.

The full argument and citations live in `plugins/rails-flow/reference/model-tiers.md`. The decisive
facts, verified against [the sub-agents docs](https://code.claude.com/docs/en/sub-agents): `model`
*"Defaults to `inherit`"*; frontmatter resolves **above** *"the main conversation's model"*, so a
`sonnet` pin hands an Opus session a Sonnet agent; and pinning up is *"skipped"* when outside the
org's `availableModels`, so it buys nothing.

<!-- pipeline:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `pipeline-coordinator` | judgement | `inherit` | — |
| `kamal-configurator` | judgement | `inherit` | — |
<!-- pipeline:tiers:end -->

## Why both are judgement

Neither agent's *output* is graded by anything outside it, which is the only thing that makes the
cheap tier safe:

- **`pipeline-coordinator`** routes a repo to a lifecycle stage by reading its state. A misrouted
  repo does not fail anything; it runs the wrong stage successfully, which is precisely the failure
  no exit status catches.
- **`kamal-configurator`** performs an **autonomous cloud deployment** from a briefing sheet. The
  blast radius is a production environment, and a deploy that succeeds against the wrong
  configuration reports success. This is the last agent in the marketplace that should be capped
  below the model a user deliberately selected.

**`scripts/breaker.py` is not that proof, and saying so matters.** This section used to rest the
whole argument on *"this plugin ships no deterministic scripts at all"*; #128 shipped one, so that
sentence would now be false — and a tier table justified by a false premise is the
`doctrine-contradiction` class, whatever the conclusion. The breaker grades a **run** (attempts,
signatures, ordering, budget), never a **judgement**: it cannot tell that the coordinator picked
the wrong stage, or that a deploy succeeded against the wrong host. The conclusion is unchanged;
its reason is now the honest one.

If a checker ever grades either agent's judgement — a config validator, a stage-routing
cross-check — revisit this table then, and name the proof in the row. Until then, an empty proof
cell is exactly right, and `check_handoff.py` enforces that a `haiku` row cannot have one.

## `effort` is deliberately unset

It *"Overrides the session effort level"* and its levels *"depend on the model"*, which is
unpublished per model — a shipped default would degrade silently somewhere. Left to the session.
