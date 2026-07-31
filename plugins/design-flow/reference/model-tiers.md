# Model tiers — which design-flow agent runs on what, and why

**A `model:` pin is a cap, so we only pin where something outside the agent grades its output.**
Everything else inherits the session model the user deliberately chose.

The full argument and citations live in `plugins/rails-flow/reference/model-tiers.md`. The decisive
facts, verified against [the sub-agents docs](https://code.claude.com/docs/en/sub-agents): `model`
*"Defaults to `inherit`"*; frontmatter resolves **above** *"the main conversation's model"*, so a
`sonnet` pin hands an Opus session a Sonnet agent; and pinning up is *"skipped"* when outside the
org's `availableModels`, so it buys nothing.

<!-- design-flow:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `ui-composer` | judgement | `inherit` | — |
| `design-auditor` | judgement | `inherit` | — |
| `brand-guardian` | judgement | `inherit` | — |
<!-- design-flow:tiers:end -->

## Why nothing here is mechanical, despite the plugin owning three linters

This plugin has more deterministic tooling than any other — `brand_pack_lint.py`,
`rendered_conformance.py`, `setup_doctrine_crosscheck.py` — so the temptation to cheapen an agent on
their strength is real. It does not hold, and the distinction is worth stating because it is the one
this whole table turns on:

**Those scripts grade the artefact, not the agent.** `rendered_conformance.py` judges a *rendered
page* against 11 named rules; it says nothing about whether `design-auditor` reviewed the right
components, weighed a deliberate deviation correctly, or missed the thing no rule encodes. An agent
is mechanical only when a script can **reject its output as wrong** — not when a script happens to
inspect the same subject matter.

Two of the three are explicit about this. `design-auditor` reviews *"against the Fidara design
system"*, which requires deciding when a deviation is intentional; that judgement is what the
rendered-conformance linter deliberately does **not** make, which is why the linter reports
forced-colors findings as counted facts rather than failures. `brand-guardian` enforces logo and
mark rules that are stated in prose in `brand.md`, with no checker.

Note that **rails-flow's table lists its own `design-auditor` as mechanical**, on the proof that
*"the mandated greps must come back empty"*. That is a different, narrower agent with the same name:
grep-driven, pass/fail, no deviation weighing. Same name, different contract — do not reconcile one
against the other's row.

## `effort` is deliberately unset

It *"Overrides the session effort level"* and its levels *"depend on the model"*, which is
unpublished per model — a shipped default would degrade silently somewhere. Left to the session.
