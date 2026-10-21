# Model tiers — which rails-stack agent runs on what, and why

**A `model:` pin is a cap, so we only pin where something outside the agent grades its output.**
Everything else inherits the session model the user deliberately chose. The full argument and citations
live in `plugins/rails-flow/reference/model-tiers.md`.

<!-- rails-stack:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `kamal-configurator` | judgement | `inherit` | — |
<!-- rails-stack:tiers:end -->

## Why it is judgement

`kamal-configurator` performs an **autonomous cloud deployment** from a briefing sheet. The blast radius is a
production environment, and a deploy that succeeds against the wrong configuration reports success. Nothing outside
the agent grades that judgement: the attempt ledger grades the run (attempts, signatures, ordering), never whether the
host was the right one. This is the last agent in the marketplace that should be capped below the model a user
deliberately selected, so an empty proof cell is exactly right, and `check_handoff.py` enforces that a `haiku` row
cannot have one.

## `effort` is deliberately unset

It *"Overrides the session effort level"* and its levels *"depend on the model"*, which is unpublished per model.
Left to the session.
